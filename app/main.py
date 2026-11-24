from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random
import re
import uuid
import unicodedata
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.auth import (
    clear_session,
    current_manager,
    hash_password,
    issue_session,
    verify_password,
)
from app.config import settings
from app.db import close_pool, connection, migrate
from app.engine import (
    INJURY_CATALOG,
    estimate_transfer_value,
    league_schedule_dates,
    overall_from_market_value,
    potential_from_overall,
    round_robin,
    simulate_score,
)
from app.schemas import CreateSaveIn, LoginIn, PositionTrainingIn, RegisterIn, TacticIn
from app.researched_profiles import get_researched_profile

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger("sm27")


def _json_safe_date(value: Any) -> Any:
    """Convert Python date values to JSON-compatible ISO strings."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _round_kickoff(anchor: date, game_index: int) -> datetime:
    """Spread fixtures across Fri/Sat/Sun, or Tue/Wed/Thu for a midweek round."""
    slot = game_index % 3
    if anchor.weekday() == 4:
        match_day, hours = anchor + timedelta(days=(0, 1, 2)[slot]), (20, 17, 15)
    elif anchor.weekday() == 5:
        match_day, hours = anchor + timedelta(days=(-1, 0, 1)[slot]), (17, 14, 16)
    elif anchor.weekday() == 6:
        match_day, hours = anchor + timedelta(days=(-2, -1, 0)[slot]), (17, 14, 16)
    else:
        match_day, hours = anchor + timedelta(days=(-1, 0, 1)[slot]), (19, 19, 20)
    return datetime.combine(match_day, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=hours[slot])


def repair_legacy_schedules(conn: Connection) -> int:
    """Re-date untouched legacy seasons that put every matchday on the same weekday."""
    legacy = conn.execute(
        """SELECT f.game_state_id,f.tournament_id,f.season,t.name,t.country,
                  count(*) FILTER (WHERE f.status='completed')::int AS completed,
                  count(*) FILTER (WHERE f.status='scheduled')::int AS scheduled,
                  count(DISTINCT extract(dow FROM f.match_date)) FILTER (WHERE f.status='scheduled')::int AS weekdays,
                  count(DISTINCT f.matchday)::int AS rounds,
                  count(DISTINCT f.home_club_id)::int AS teams
           FROM fixtures f
           JOIN game_states gs ON gs.id=f.game_state_id
           JOIN tournaments t ON t.id=f.tournament_id
           WHERE gs.status='active' AND t.tournament_type='league'
           GROUP BY f.game_state_id,f.tournament_id,f.season,t.name,t.country
           HAVING count(*) FILTER (WHERE f.status='completed')=0
              AND count(*) FILTER (WHERE f.status='scheduled')>0
              AND count(DISTINCT extract(dow FROM f.match_date)) FILTER (WHERE f.status='scheduled')=1
              AND count(DISTINCT f.home_club_id)>=6
           ORDER BY f.game_state_id,t.name"""
    ).fetchall()
    updated = 0
    for competition in legacy:
        # The league must still have a complete untouched round-robin schedule.
        round_rows = conn.execute(
            """SELECT matchday,min(match_date)::date AS old_date,
                      array_agg(id ORDER BY home_club_id,away_club_id) AS fixture_ids
               FROM fixtures
               WHERE game_state_id=%s AND tournament_id=%s AND season=%s AND status='scheduled'
               GROUP BY matchday ORDER BY matchday""",
            (competition["game_state_id"],competition["tournament_id"],competition["season"]),
        ).fetchall()
        if len(round_rows) != int(competition["rounds"]):
            continue
        season_year = int(str(competition["season"])[:4])
        anchors = league_schedule_dates(
            competition["name"],competition["country"] or "",season_year,len(round_rows)
        )
        if len(anchors) != len(round_rows):
            continue
        updates: list[tuple[datetime,str]] = []
        for round_index,(round_row,anchor) in enumerate(zip(round_rows,anchors)):
            fixture_ids = [str(item) for item in round_row["fixture_ids"]]
            for game_index,fixture_id in enumerate(fixture_ids):
                updates.append((_round_kickoff(anchor,game_index),fixture_id))
        if updates:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """UPDATE fixtures SET match_date=%s
                       WHERE id=%s AND game_state_id=%s AND status='scheduled'""",
                    [(kickoff,fixture_id,competition["game_state_id"]) for kickoff,fixture_id in updates],
                )
            updated += len(updates)
            LOGGER.info(
                "Repaired legacy calendar for save %s, competition %s: %s scheduled fixtures",
                competition["game_state_id"],competition["name"],len(updates),
            )
    return updated


def _run_fc27_rating_import() -> None:
    try:
        from scripts.import_fc27_ratings import main as import_ratings
        import_ratings(settings.database_url)
        refreshed_lineups = refresh_ai_lineups()
        with connection() as conn:
            conn.execute(
                """UPDATE fc27_import_state SET status='succeeded',finished_at=now(),error_message=NULL
                   WHERE import_key='ratings'"""
            )
        LOGGER.info(
            "One-time FC 27 rating import completed; refreshed %s AI lineups",
            refreshed_lineups,
        )
    except Exception as error:
        LOGGER.exception("FC 27 rating import failed; the app will keep using labelled SM27 estimates")
        try:
            with connection() as conn:
                conn.execute(
                    """UPDATE fc27_import_state SET status='failed',finished_at=now(),error_message=%s
                       WHERE import_key='ratings'""",
                    (str(error)[:500],),
                )
        except Exception:
            LOGGER.exception("Could not record FC 27 import failure state")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url:
        start_fc27_import = False
        with connection() as conn:
            migrate(conn)
            repaired_fixtures = repair_legacy_schedules(conn)
            if repaired_fixtures:
                LOGGER.info("Repaired %s legacy scheduled fixtures", repaired_fixtures)
            state = conn.execute(
                """SELECT status,(attempted_at < now()-interval '30 minutes') AS retryable
                   FROM fc27_import_state WHERE import_key='ratings'"""
            ).fetchone()
            if not state or (state["status"] != "succeeded" and state["retryable"]):
                conn.execute(
                    """INSERT INTO fc27_import_state (import_key,status,attempted_at,finished_at,error_message)
                       VALUES ('ratings','running',now(),NULL,NULL)
                       ON CONFLICT (import_key) DO UPDATE SET status='running',
                           attempted_at=now(),finished_at=NULL,error_message=NULL"""
                )
                start_fc27_import = True
        if start_fc27_import:
            LOGGER.info("FC 27 rating catalog is empty; starting one-time import in the app process")
            asyncio.create_task(asyncio.to_thread(_run_fc27_rating_import))
    yield
    close_pool()


app = FastAPI(title="Soccer Master 27 API", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def db_dep():
    with connection() as conn:
        yield conn


def manager_dep(request: Request, conn: Connection = Depends(db_dep)) -> dict:
    return current_manager(request, conn)


def serialise(row: Any) -> Any:
    if isinstance(row, dict):
        return {key: serialise(value) for key, value in row.items()}
    if isinstance(row, (date, datetime)):
        return row.isoformat()
    if isinstance(row, uuid.UUID):
        return str(row)
    if isinstance(row, list):
        return [serialise(item) for item in row]
    return row




POSITION_CODES = {"GK", "RB", "CB", "LB", "RWB", "LWB", "CDM", "CM", "CAM", "RM", "LM", "RW", "LW", "ST", "CF"}
SECONDARY_POSITIONS = {
    "GK": (), "RB": ("LB", "RWB"), "LB": ("RB", "LWB"),
    "CB": ("CDM",), "RWB": ("RB", "RM"), "LWB": ("LB", "LM"),
    "CDM": ("CM", "CB"), "CM": ("CDM", "CAM"),
    "CAM": ("CM", "CF"), "RM": ("RW", "CM"),
    "LM": ("LW", "CM"), "RW": ("RM", "ST"),
    "LW": ("LM", "ST"), "ST": ("CF", "LW"), "CF": ("ST", "CAM"),
}
FLAG_SPECIAL_CODES = {
    "england": "gb-eng", "eng": "gb-eng", "bul": "bg", "bgr": "bg", "kos": "xk",
    "scotland": "gb-sct", "sco": "gb-sct",
    "wales": "gb-wls", "wal": "gb-wls",
    "northern ireland": "gb-nir", "nir": "gb-nir",
    "kosovo": "xk", "xk": "xk",
    "russia": "ru", "turkey": "tr", "south korea": "kr",
    "north korea": "kp", "iran": "ir", "ivory coast": "ci",
    "czech republic": "cz", "bolivia": "bo", "vietnam": "vn",
    "syria": "sy", "taiwan": "tw",
    "por": "pt", "prt": "pt", "ned": "nl", "nld": "nl", "ger": "de", "deu": "de", "sui": "ch", "che": "ch",
    "rsa": "za", "crc": "cr", "uru": "uy", "ury": "uy", "cro": "hr", "hrv": "hr",
    "gre": "gr", "grc": "gr", "den": "dk", "dnk": "dk", "ksa": "sa", "uae": "ae", "civ": "ci", "slo": "si", "svn": "si", "rom": "ro", "rou": "ro", "chi": "cl", "par": "py", "nig": "ne", "ner": "ne", "ang": "ao", "zam": "zm", "hai": "ht", "hon": "hn", "gam": "gm", "ngr": "ng", "swi": "ch", "ire": "ie", "wal": "gb-wls", "sco": "gb-sct", "inglaterra": "gb-eng", "españa": "es", "francia": "fr", "brasil": "br", "turquía": "tr", "uruguay": "uy", "marruecos": "ma", "bélgica": "be", "países bajos": "nl", "ucrania": "ua", "alemania": "de", "costa de marfil": "ci", "portugal": "pt",
}


def flag_for_nationality(value: str | None) -> str:
    """Return an ISO flag-icon code for a rectangular SVG flag, never an emoji."""
    key = (value or "").strip().casefold()
    if not key:
        return ""
    if key in FLAG_SPECIAL_CODES:
        return FLAG_SPECIAL_CODES[key]
    try:
        import pycountry
        country = pycountry.countries.get(alpha_3=key.upper()) if len(key) == 3 else None
        if country is None:
            country = pycountry.countries.lookup(value or "")
        return (country.alpha_2 or "").lower()
    except (ImportError, LookupError, AttributeError):
        return ""


def normalise_player_position(position: str | None, source_id: str = "") -> str:
    """Keep exact positions; expand only broad source roles into stable SM27 estimates."""
    value = (position or "").strip().upper()
    if value in POSITION_CODES:
        return value
    if value in {"GK", "GOALKEEPER", "G"}:
        return "GK"
    broad_roles = {
        "DF": ("CB", "CB", "CB", "LB", "RB", "LWB", "RWB"),
        "MF": ("CM", "CM", "CM", "CDM", "CAM", "LM", "RM"),
        "FW": ("ST", "ST", "ST", "CF", "LW", "RW"),
    }
    group = {
        "DEFENDER": "DF", "DEFENCE": "DF", "D": "DF",
        "MIDFIELDER": "MF", "MIDFIELD": "MF", "M": "MF",
        "FORWARD": "FW", "ATTACKER": "FW", "STRIKER": "FW", "F": "FW",
    }.get(value, value)
    choices = broad_roles.get(group)
    if choices:
        key = source_id or value
        seed = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
        return choices[seed % len(choices)]
    return "CM"


def player_attributes(overall: int, position: str, source_id: str = "") -> dict[str, int]:
    """Deterministic SM27 fallback attributes; matched FC 27 data always takes priority."""
    rating = max(35, min(90, int(overall)))
    if position == "GK":
        offsets = {"DIV": 1, "HAN": 0, "KIC": -3, "REF": 4, "SPE": -2, "POS": 2}
    else:
        group = "DF" if position in {"CB", "RB", "LB", "RWB", "LWB"} else "FW" if position in {"ST", "CF", "RW", "LW"} else "MF"
        offsets = {
            "PAC": 3 if group == "FW" else -1 if group == "DF" else 1,
            "SHO": 6 if group == "FW" else -7 if group == "DF" else -1,
            "PAS": 4 if group == "MF" else 0 if group == "DF" else -3,
            "DRI": 5 if group == "FW" else 2 if group == "MF" else -4,
            "DEF": 7 if group == "DF" else 0 if group == "MF" else -12,
            "PHY": 4 if group == "DF" else 1 if group == "FW" else -1,
        }
    return {key: max(20, min(99, rating + offset)) for key, offset in offsets.items()}


def estimated_market_value(
    overall: int,
    potential: int,
    age: int,
    league: str = "",
    country: str = "",
    attributes: dict[str, Any] | None = None,
) -> int:
    """SM27 transfer-value estimate calibrated by competition, age, OVR and role traits."""
    return estimate_transfer_value(overall, potential, age, league, country, attributes)


INJURY_BY_KEY = {item["key"]: item for item in INJURY_CATALOG}


def tournament_logo_url(name: str | None, country: str | None = None) -> str | None:
    title = (name or "").casefold()
    nation = (country or "").casefold()
    if "russian premier" in title or "российская премьер" in title or "рпл" in title:
        return "https://fc-ural.ru/uploads/main/01d/a5b552980d57e977e8e3ab4d4c175d7f672e1ac8822ad6cc2892ff7a2f25f387/mir_rpl_01.png"
    if "premier league" in title and ("royaume" in nation or "kingdom" in nation or "england" in nation):
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Premier%20League.svg"
    if "champions league" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/UEFA%20Champions%20League%20logo.svg"
    if "conference league" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/UEFA%20Conference%20League%20logo.svg"
    if "europa league" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Europa%20League%202021.svg"
    if "la liga" in title or "laliga" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/LaLiga%20logo%202023.svg"
    if "bundesliga" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Bundesliga%20logo.svg"
    if "serie a" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Serie%20A%20logo%202022.svg"
    if "ligue 1" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Ligue%201%20McDonald%27s%20logo.svg"
    if "eredivisie" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Eredivisie%20nieuw%20logo%202017-.svg"
    if "primeira liga" in title or "liga portugal" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Liga%20Portugal%20Betclic%20logo.svg"
    if "major league soccer" in title or title == "mls":
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Major%20League%20Soccer%20Crest%20Logo%20Black%20Transparent%202024.svg"
    if "campeonato brasileiro" in title or "série a" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Campeonato_Brasileiro_S%C3%A9rie_A_logo_%282026%29.svg"
    if "liga profesional" in title or "argentine primera" in title or "primera división" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Liga_Profesional_de_F%C3%BAtbol_%28Argentina%29_wordmark.svg"
    if "championship" in title or "efl championship" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/EFL_Championship_Wordmark.svg"
    if "j1 league" in title or "j league" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/J1_league_logo_2026.svg"
    if "saudi" in title:
        return "https://commons.wikimedia.org/wiki/Special:FilePath/Saudi%20Pro%20League%20Logo.svg"
    return None


FC27_WAGE_OVERRIDES = {
    "cristiano ronaldo": 53_000,
    "iñigo martínez": 245_000,
    "inigo martinez": 245_000,
}


def normalise_player_name(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "").casefold()
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", plain)


def estimated_weekly_wage(
    overall: int,
    age: int = 24,
    reputation: int = 50,
    player_name: str | None = None,
    generated: bool = False,
) -> int:
    """Weekly wage estimate calibrated against FC 27 Career Mode squad data."""
    name_key = normalise_player_name(player_name)
    if name_key.startswith("cristianoronaldo"):
        return 4_007_692
    if name_key.startswith("inigomartinez"):
        return 196_154
    if generated:
        return int(max(250, min(2_500, round((overall * 14 + max(0, 82 - age) * 8) / 50) * 50)))
    base = 600 * math.exp((max(35, min(95, overall)) - 60) * 0.21)
    if age <= 22:
        age_factor = 0.55
    elif age <= 25:
        age_factor = 0.75
    elif age <= 29:
        age_factor = 1.0
    elif age <= 34:
        age_factor = 1.20
    elif age <= 37:
        age_factor = 1.45
    elif age <= 40:
        age_factor = 0.90
    else:
        age_factor = 0.25
    club_factor = 0.70 + max(10, min(100, reputation)) * 0.0175
    return int(max(250, min(1_500_000, round(base * age_factor * club_factor / 100) * 100)))

def estimated_contract_end(age: int, source_id: str) -> date:
    seed = int(hashlib.sha1(source_id.encode()).hexdigest()[:8], 16)
    max_years = 2 if age >= 34 else 3 if age >= 30 else 5
    years = 1 + seed % max_years
    return date(2027 + years, 6, 30)


def require_save(conn: Connection, manager_id: str) -> dict:
    row = conn.execute(
        """SELECT gs.id, gs.game_date, gs.season, gs.save_name, gs.managed_club_id, gs.game_settings,
                  c.name AS club_name, c.league, c.country, c.logo_url, c.reputation,
                  m.manager_name
           FROM game_states gs
           JOIN managers m ON m.id = gs.manager_id
           LEFT JOIN clubs c ON c.id = gs.managed_club_id
           WHERE gs.manager_id = %s AND gs.status = 'active'
           ORDER BY gs.updated_at DESC LIMIT 1""",
        (manager_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Сохранение не найдено. Выберите клуб.")
    return dict(row)


def display_club_name(value: str | None) -> str:
    name = (value or "").strip()
    return re.sub(r"\s+F\.C\.$", "", name, flags=re.IGNORECASE).strip()


def make_club(conn: Connection, game_state_id: str, pool_row: dict) -> str:
    stars = float(pool_row.get("fifa_stars") or 2.5)
    reputation = max(10, min(100, int(pool_row.get("team_strength") or round(stars * 20))))
    capacity = pool_row.get("stadium_capacity") or 20000
    budget = int(max(350_000, min(220_000_000, (reputation**2) * 22_000)))
    row = conn.execute(
        """INSERT INTO clubs (
             game_state_id, external_id, name, short_name, country, league, original_league,
             continent, star_rating, budget, stadium_name, stadium_capacity, logo_url,
             primary_color, secondary_color, reputation
           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (game_state_id, external_id) DO UPDATE SET name = EXCLUDED.name
           RETURNING id""",
        (
            game_state_id,
            pool_row["source_id"],
            display_club_name(pool_row["club_name"]),
            (display_club_name(pool_row["club_name"]) or "SM27")[:20],
            pool_row.get("country") or "—",
            pool_row.get("league_name") or "Лига",
            pool_row.get("league_name") or "Лига",
            pool_row.get("continent") or "UEFA",
            stars,
            budget,
            pool_row.get("stadium"),
            capacity,
            pool_row.get("logo_url"),
            (pool_row.get("colors_hex") or "").split(" | ")[0] or "#16A36A",
            (pool_row.get("colors_hex") or "").split(" | ")[1] if " | " in (pool_row.get("colors_hex") or "") else "#102B22",
            reputation,
        ),
    ).fetchone()
    return str(row["id"])


def ensure_demo_roster(
    conn: Connection,
    game_state_id: str,
    club_id: str,
    club_name: str,
    reputation: int,
    league: str = "",
    country: str = "",
) -> None:
    existing = conn.execute(
        "SELECT count(*) AS n FROM players WHERE game_state_id=%s AND club_id=%s",
        (game_state_id, club_id),
    ).fetchone()["n"]
    positions = ["GK", "GK", "RB", "CB", "CB", "LB", "CB", "RB", "CDM", "CM", "CM", "CAM", "CM", "CM", "RW", "LW", "ST", "CF"]
    if existing >= len(positions):
        return
    for index, position in enumerate(positions[existing:], start=existing + 1):
        source_id = f"generated:{club_id}:{index}"
        age = 18 + (index % 12)
        overall = max(40, min(82, reputation - 8 + (index % 7)))
        potential = min(92, overall + 4 + (index % 7))
        attributes = player_attributes(overall, position, source_id)
        market_value = estimated_market_value(overall, potential, age, league, country, attributes)
        conn.execute(
            """INSERT INTO players (
                   game_state_id,club_id,external_id,name,age,position,secondary_positions,
                   overall,potential,market_value,weekly_wage,contract_end,attributes,
                   original_data,source_name,profile_source,market_value_source,form,morale,sharpness
               ) VALUES (%s,%s,%s,%s,%s,%s,ARRAY[]::text[],%s,%s,%s,%s,%s,%s,%s,
                         'SM27 generated roster','SM27 generated academy player','SM27 estimate',50,70,85)""",
            (
                game_state_id, club_id, source_id, f"Игрок академии {index:02d}", age, position,
                overall, potential, market_value,
                estimated_weekly_wage(overall, age, reputation, generated=True),
                estimated_contract_end(age, source_id),
                Jsonb(attributes),
                Jsonb({
                    "generated": True,
                    "note": "Fictional game placeholder, not a real player",
                    "market_value_source": "SM27 estimate",
                    "market_value_model": "league-age-ovr-potential-attributes-v1",
                }),
            ),
        )


def position_penalty(primary: str, secondary: list[str], target: str) -> int:
    if primary == target or target in secondary:
        return 0
    if primary == "GK" or target == "GK":
        return -40
    close = {
        "RB": {"LB": -2, "RWB": 0, "LWB": -5, "CB": -3, "RM": -5, "CDM": -7},
        "LB": {"RB": -2, "LWB": 0, "RWB": -5, "CB": -3, "LM": -5, "CDM": -7},
        "CB": {"LB": -3, "RB": -3, "CDM": -3, "RWB": -5, "LWB": -5, "CM": -7},
        "CDM": {"CM": -2, "CB": -3, "CAM": -5, "RM": -7, "LM": -7},
        "CM": {"CDM": -2, "CAM": -2, "RM": -3, "LM": -3, "CB": -7, "ST": -10},
        "CAM": {"CM": -2, "CF": -3, "ST": -5, "RM": -5, "LM": -5},
        "RM": {"RW": -2, "CM": -3, "RB": -5, "ST": -7, "LM": -7},
        "LM": {"LW": -2, "CM": -3, "LB": -5, "ST": -7, "RM": -7},
        "RW": {"RM": -2, "ST": -3, "CF": -5, "LW": -7, "RB": -7},
        "LW": {"LM": -2, "ST": -3, "CF": -5, "RW": -7, "LB": -7},
        "ST": {"CF": -2, "CAM": -5, "RW": -7, "LW": -7, "CM": -10},
        "CF": {"ST": -2, "CAM": -3, "RW": -5, "LW": -5, "CM": -7},
        "RWB": {"RB": 0, "RM": -3, "LB": -5, "CB": -5},
        "LWB": {"LB": 0, "LM": -3, "RB": -5, "CB": -5},
    }
    return close.get(primary, {}).get(target, -7)


FORMATION_ROLE_MAP = {
    "3-1-4-2": ["GK","CB","CB","CB","CDM","LM","CM","CM","RM","ST","ST"],
    "3-4-1-2": ["GK","CB","CB","CB","LM","CM","CM","RM","CAM","ST","ST"],
    "3-4-2-1": ["GK","CB","CB","CB","LM","CM","CM","RM","CAM","CAM","ST"],
    "3-4-3": ["GK","CB","CB","CB","LM","CM","CM","RM","LW","ST","RW"],
    "3-5-2": ["GK","CB","CB","CB","LM","CDM","CM","CDM","RM","ST","ST"],
    "4-1-2-1-2": ["GK","LB","CB","CB","RB","CDM","CM","CM","CAM","ST","ST"],
    "4-1-2-1-2 (2)": ["GK","LB","CB","CB","RB","CDM","CM","CM","CAM","ST","ST"],
    "4-1-3-2": ["GK","LB","CB","CB","RB","CDM","LM","CM","RM","ST","ST"],
    "4-1-4-1": ["GK","LB","CB","CB","RB","CDM","LM","CM","CM","RM","ST"],
    "4-2-1-3": ["GK","LB","CB","CB","RB","CDM","CM","CAM","LW","ST","RW"],
    "4-2-2-2": ["GK","LB","CB","CB","RB","CDM","CM","CAM","CAM","ST","ST"],
    "4-2-3-1": ["GK","LB","CB","CB","RB","CDM","CM","LM","CAM","RM","ST"],
    "4-2-3-1 (2)": ["GK","LB","CB","CB","RB","CDM","CDM","LM","CAM","RM","ST"],
    "4-2-4": ["GK","LB","CB","CB","RB","CDM","CM","LW","ST","ST","RW"],
    "4-3-1-2": ["GK","LB","CB","CB","RB","CDM","CM","CM","CAM","ST","ST"],
    "4-3-2-1": ["GK","LB","CB","CB","RB","CM","CDM","CM","CAM","CAM","ST"],
    "4-3-3": ["GK","LB","CB","CB","RB","CDM","CM","CAM","LW","ST","RW"],
    "4-3-3 (2)": ["GK","LB","CB","CB","RB","CM","CDM","CM","LW","ST","RW"],
    "4-3-3 (3)": ["GK","LB","CB","CB","RB","CDM","CM","CDM","LW","ST","RW"],
    "4-3-3 (4)": ["GK","LB","CB","CB","RB","CM","CAM","CM","LW","ST","RW"],
    "4-3-3 Attack": ["GK","LB","CB","CB","RB","CDM","CM","CAM","LW","ST","RW"],
    "4-3-3 Defend": ["GK","LB","CB","CB","RB","CDM","CM","CM","LW","ST","RW"],
    "4-3-3 Flat": ["GK","LB","CB","CB","RB","CM","CM","CM","LW","ST","RW"],
    "4-3-3 Holding": ["GK","LB","CB","CB","RB","CDM","CDM","CM","LW","ST","RW"],
    "4-4-1-1 Midfield": ["GK","LB","CB","CB","RB","LM","CM","CM","RM","CAM","ST"],
    "4-4-2": ["GK","LB","CB","CB","RB","LM","CM","CM","RM","ST","ST"],
    "4-4-2 (2)": ["GK","LB","CB","CB","RB","LM","CDM","CDM","RM","ST","ST"],
    "4-4-2 Flat": ["GK","LB","CB","CB","RB","LM","CM","CM","RM","ST","ST"],
    "4-4-2 Holding": ["GK","LB","CB","CB","RB","LM","CDM","CDM","RM","ST","ST"],
    "4-5-1": ["GK","LB","CB","CB","RB","LM","CM","CDM","CM","RM","ST"],
    "4-5-1 (2)": ["GK","LB","CB","CB","RB","LM","CM","CM","CM","RM","ST"],
    "4-5-1 Attack": ["GK","LB","CB","CB","RB","LM","CM","CDM","CM","RM","ST"],
    "4-5-1 Flat": ["GK","LB","CB","CB","RB","LM","CM","CM","CM","RM","ST"],
    "5-2-1-2": ["GK","LWB","CB","CB","CB","RWB","CM","CM","CAM","ST","ST"],
    "5-2-3": ["GK","LWB","CB","CB","CB","RWB","CM","CM","LW","ST","RW"],
    "5-3-2": ["GK","LWB","CB","CB","CB","RWB","CM","CDM","CM","ST","ST"],
    "5-3-2 Holding": ["GK","LWB","CB","CB","CB","RWB","CDM","CDM","CM","ST","ST"],
    "5-4-1": ["GK","LWB","CB","CB","CB","RWB","LM","CM","CM","RM","ST"],
    "5-4-1 Flat": ["GK","LWB","CB","CB","CB","RWB","LM","CM","CM","RM","ST"],
}


def best_lineup(player_rows: list[dict], formation: str = "4-3-3") -> tuple[list[str], list[str], list[str]]:
    roles = FORMATION_ROLE_MAP.get(formation)
    if roles is None:
        base = re.sub(r" (?:Flat|Attack|Defend|Holding|Narrow|Wide|Midfield)$", "", formation)
        roles = FORMATION_ROLE_MAP.get(base, FORMATION_ROLE_MAP["4-3-3"])
    available = [dict(row) for row in player_rows]
    if len(available) < len(roles):
        raise ValueError(f"Для схемы {formation} нужно минимум {len(roles)} игроков")

    # Rectangular Hungarian assignment: O(players * roles^2), instead of the
    # previous exponential bitmask DP with tuple copies for every reachable state.
    ordered = sorted(available, key=lambda row: str(row["id"]))
    player_count = len(ordered)
    slot_count = len(roles)
    ratings = [
        int(player.get("dynamic_overall") or player.get("overall") or 0)
        for player in ordered
    ]
    scores = [
        [
            ratings[player_index] + position_penalty(
                player.get("position") or "CM",
                list(player.get("secondary_positions") or []),
                role,
            )
            for role in roles
        ]
        for player_index, player in enumerate(ordered)
    ]

    # Hungarian algorithm with roles as rows and players as columns.
    # There are always at least as many players as roles.
    u = [0] * (slot_count + 1)
    v = [0] * (player_count + 1)
    matched_slot = [0] * (player_count + 1)
    previous_player = [0] * (player_count + 1)
    infinity = float("inf")
    for slot_index in range(1, slot_count + 1):
        matched_slot[0] = slot_index
        min_cost = [infinity] * (player_count + 1)
        used = [False] * (player_count + 1)
        current_player = 0
        while True:
            used[current_player] = True
            current_slot = matched_slot[current_player]
            delta = infinity
            next_player = 0
            for candidate_player in range(1, player_count + 1):
                if used[candidate_player]:
                    continue
                cost = -scores[candidate_player - 1][current_slot - 1]
                reduced_cost = cost - u[current_slot] - v[candidate_player]
                if reduced_cost < min_cost[candidate_player]:
                    min_cost[candidate_player] = reduced_cost
                    previous_player[candidate_player] = current_player
                if min_cost[candidate_player] < delta:
                    delta = min_cost[candidate_player]
                    next_player = candidate_player
            for candidate_player in range(player_count + 1):
                if used[candidate_player]:
                    u[matched_slot[candidate_player]] += delta
                    v[candidate_player] -= delta
                else:
                    min_cost[candidate_player] -= delta
            current_player = next_player
            if matched_slot[current_player] == 0:
                break
        while True:
            next_player = previous_player[current_player]
            matched_slot[current_player] = matched_slot[next_player]
            current_player = next_player
            if current_player == 0:
                break

    selected_by_slot: list[str | None] = [None] * slot_count
    for player_index in range(1, player_count + 1):
        slot_index = matched_slot[player_index]
        if slot_index:
            selected_by_slot[slot_index - 1] = str(ordered[player_index - 1]["id"])
    if any(player_id is None for player_id in selected_by_slot):
        raise ValueError(f"Не удалось собрать полный состав по схеме {formation}")

    selected = [str(player_id) for player_id in selected_by_slot]
    selected_set = set(selected)
    remaining = [row for row in available if str(row["id"]) not in selected_set]
    bench_rows = sorted(
        remaining,
        key=lambda row: int(row.get("dynamic_overall") or row.get("overall") or 0),
        reverse=True,
    )[:7]
    return selected, [str(row["id"]) for row in bench_rows], list(roles)


def create_schedule(
    conn: Connection,
    game_state_id: str,
    tournament_id: str,
    teams: list[dict],
    season: str = "2026/27",
    start_date: date | None = None,
) -> None:
    """Create a league calendar, keeping reserved midweeks clear for cups and UEFA."""
    ids = [str(team["id"]) for team in teams]
    tournament = conn.execute(
        "SELECT code,name,country FROM tournaments WHERE id=%s",
        (tournament_id,),
    ).fetchone()
    league_name = tournament["name"] if tournament else ""
    league_code = tournament["code"] if tournament else ""
    first_leg_rounds = round_robin(ids)
    leg_split = len(first_leg_rounds) // 2
    rounds = first_leg_rounds

    # MLS has 30 clubs and 34 fixtures per club, not a European home-and-away round robin.
    if "major league soccer" in league_name.casefold() and len(ids) == 30:
        first_leg = first_leg_rounds[:leg_split]
        extra_count = max(0, 34 - len(first_leg))
        repeat_indexes = [
            round(index * (len(first_leg) - 1) / max(1, extra_count - 1))
            for index in range(extra_count)
        ]
        additional = [
            [(away, home) for home, away in first_leg[index]]
            for index in repeat_indexes
        ]
        rounds = first_leg + additional
        leg_split = len(first_leg)

    elif (league_code == "ARG-PD" or "argentine primera" in league_name.casefold()) and len(ids) == 30:
        first_leg = first_leg_rounds[:leg_split]
        additional = [
            [(away, home) for home, away in first_leg[index]]
            for index in (0, 14, 28)
        ]
        rounds = first_leg + additional
        leg_split = len(first_leg)

    season_year = int(str(season)[:4])
    round_dates = league_schedule_dates(league_name, tournament["country"] if tournament else "", season_year, len(rounds))
    if len(round_dates) != len(rounds):
        anchor = start_date or date(season_year, 8, 15)
        round_dates = [anchor + timedelta(days=7 * index) for index in range(len(rounds))]

    rows_to_insert: list[tuple] = []
    for round_index, games in enumerate(rounds):
        anchor = round_dates[round_index]
        for game_index, (home_id, away_id) in enumerate(games):
            kickoff = _round_kickoff(anchor, game_index)
            rows_to_insert.append((
                game_state_id, tournament_id, season, kickoff, round_index + 1,
                "Регулярный чемпионат", 1 if round_index < leg_split else 2,
                home_id, away_id,
            ))
    if rows_to_insert:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO fixtures (
                       game_state_id,tournament_id,season,match_date,matchday,stage,leg,
                       home_club_id,away_club_id,status
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled')
                   ON CONFLICT (game_state_id,tournament_id,season,match_date,home_club_id,away_club_id)
                   DO NOTHING""",
                rows_to_insert,
            )


def refresh_ai_lineups() -> int:
    """Rebuild AI club XIs after official player matches change; preserve each manager's XI."""
    refreshed = 0
    with connection() as conn:
        saves = conn.execute(
            """SELECT id,managed_club_id
               FROM game_states
               WHERE status='active' AND managed_club_id IS NOT NULL"""
        ).fetchall()
        for save in saves:
            rows = conn.execute(
                """SELECT c.id AS club_id,p.id,p.position,p.secondary_positions,p.overall,
                          GREATEST(1,LEAST(99,p.overall + ROUND(
                            (p.form-50)*0.06 + (p.morale-70)*0.04
                            + (p.sharpness-85)*0.04 - p.fatigue*0.08
                          )::int)) AS dynamic_overall,
                          t.formation,t.mentality,t.style
                   FROM clubs c
                   JOIN players p ON p.game_state_id=c.game_state_id AND p.club_id=c.id
                   LEFT JOIN tactics t ON t.game_state_id=c.game_state_id AND t.club_id=c.id
                   WHERE c.game_state_id=%s AND c.id<>%s
                   ORDER BY c.id,p.overall DESC,p.id""",
                (save["id"], save["managed_club_id"]),
            ).fetchall()
            grouped: dict[str, list[dict]] = {}
            for row in rows:
                player = dict(row)
                grouped.setdefault(str(player["club_id"]), []).append(player)
            for club_id, players in grouped.items():
                if len(players) < 11:
                    continue
                tactic = players[0]
                formation = tactic.get("formation") or "4-3-3"
                mentality = tactic.get("mentality") or "balanced"
                style = dict(tactic.get("style") or {})
                starters, bench, roles = best_lineup(players, formation)
                selected = set(starters) | set(bench)
                style["slot_roles"] = [
                    {"player_id": player_id, "role": role}
                    for player_id, role in zip(starters, roles)
                ]
                style["reserve_order"] = [
                    str(player["id"]) for player in players
                    if str(player["id"]) not in selected
                ]
                conn.execute(
                    """INSERT INTO tactics (
                           game_state_id,club_id,formation,mentality,style,starting_xi,bench
                       ) VALUES (%s,%s,%s,%s,%s,%s::uuid[],%s::uuid[])
                       ON CONFLICT (game_state_id,club_id) DO UPDATE SET
                           formation=EXCLUDED.formation,
                           mentality=EXCLUDED.mentality,
                           style=EXCLUDED.style,
                           starting_xi=EXCLUDED.starting_xi,
                           bench=EXCLUDED.bench,
                           updated_at=now()""",
                    (
                        save["id"], club_id, formation, mentality, Jsonb(style),
                        starters, bench,
                    ),
                )
                refreshed += 1
    return refreshed


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled SM27 request error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Сервис временно не смог выполнить действие. Данные карьеры сохранены; повтори попытку."},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=None)
def health() -> dict | JSONResponse:
    if not settings.database_url:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "not_configured", "app": "SM27"},
        )
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "database": "connected", "app": "SM27"}
    except Exception as exc:  # pragma: no cover - platform health response
        LOGGER.warning("Health check could not reach Neon: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unavailable", "detail": type(exc).__name__},
        )


@app.post("/api/auth/register")
def register(body: RegisterIn, response: Response, conn: Connection = Depends(db_dep)) -> dict:
    if len(body.password) < 8 or not re.search(r"[A-Za-zА-Яа-я]", body.password) or not re.search(r"\d", body.password):
        raise HTTPException(status_code=422, detail="Пароль должен содержать буквы и хотя бы одну цифру")
    try:
        manager = conn.execute(
            """INSERT INTO managers (manager_name, auth_subject, password_hash)
               VALUES (%s,%s,%s) RETURNING id, manager_name, auth_subject""",
            (body.name.strip(), f"sm27:{body.email}", hash_password(body.password)),
        ).fetchone()
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Аккаунт с таким email уже существует") from None
    issue_session(conn, str(manager["id"]), response)
    return {"manager": {"id": str(manager["id"]), "name": manager["manager_name"], "email": body.email}}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, conn: Connection = Depends(db_dep)) -> dict:
    manager = conn.execute(
        "SELECT id, manager_name, auth_subject, password_hash FROM managers WHERE auth_subject=%s",
        (f"sm27:{body.email}",),
    ).fetchone()
    if not manager or not verify_password(body.password, manager.get("password_hash")):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    issue_session(conn, str(manager["id"]), response)
    return {"manager": {"id": str(manager["id"]), "name": manager["manager_name"], "email": body.email}}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn: Connection = Depends(db_dep)) -> dict:
    clear_session(conn, request, response)
    return {"ok": True}


@app.get("/api/me")
def me(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = conn.execute(
        "SELECT id, save_name, season, game_date FROM game_states WHERE manager_id=%s AND status='active' ORDER BY updated_at DESC LIMIT 1",
        (manager["id"],),
    ).fetchone()
    return {
        "manager": {"id": str(manager["id"]), "name": manager["manager_name"], "email": manager["auth_subject"].removeprefix("sm27:")},
        "save": serialise(dict(save)) if save else None,
    }


@app.get("/api/catalog/summary")
def catalog_summary(conn: Connection = Depends(db_dep)) -> dict:
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM sm27_club_pool) AS clubs,
                  (SELECT count(*) FROM world_player_catalog) AS players,
                  (SELECT count(DISTINCT league_code) FROM sm27_club_pool) AS leagues,
                  (SELECT max(source_snapshot) FROM sm27_club_pool) AS snapshot"""
    ).fetchone()
    return serialise(dict(counts))


@app.get("/api/catalog/leagues")
def catalog_leagues(conn: Connection = Depends(db_dep)) -> list:
    rows = conn.execute(
        """SELECT league_code AS code, league_name AS name, min(country) AS country, league_level,
                  count(*)::int AS clubs, count(*) FILTER (WHERE has_squad)::int AS clubs_with_squads
           FROM sm27_club_pool GROUP BY league_code, league_name, league_level
           ORDER BY league_level, league_name"""
    ).fetchall()
    return serialise([dict(row) for row in rows])


@app.get("/api/catalog/clubs")
def catalog_clubs(
    q: str = "", league: str | None = None, country: str | None = None,
    limit: int = 100, offset: int = 0, conn: Connection = Depends(db_dep)
) -> dict:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    clauses = ["TRUE"]
    params: list[Any] = []
    if q.strip():
        clauses.append("(club_name ILIKE %s OR country ILIKE %s OR league_name ILIKE %s)")
        term = f"%{q.strip()}%"
        params.extend([term, term, term])
    if league:
        clauses.append("league_code=%s")
        params.append(league)
    if country:
        clauses.append("country_iso=%s")
        params.append(country.upper())
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""SELECT source_id, regexp_replace(club_name, '[[:space:]]+F[.]C[.]$', '', 'i') AS club_name, country, country_iso, league_name, league_code,
                   league_level, division, city, stadium, stadium_capacity, colors_hex,
                   logo_url, logo_license, has_squad, squad_count, sort_rank, fifa_stars, team_strength
            FROM sm27_club_pool WHERE {where}
            ORDER BY lower(club_name), club_name LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    ).fetchall()
    total = conn.execute(f"SELECT count(*) AS n FROM sm27_club_pool WHERE {where}", params).fetchone()["n"]
    return {"items": serialise([dict(row) for row in rows]), "total": total, "limit": limit, "offset": offset}


@app.post("/api/saves")
def create_save(body: CreateSaveIn, manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    started_at = time.perf_counter()
    stage_started = started_at

    def log_stage(stage: str) -> None:
        nonlocal stage_started
        now = time.perf_counter()
        LOGGER.info(
            "Career creation stage=%s duration=%.3fs total=%.3fs",
            stage, now - stage_started, now - started_at,
        )
        stage_started = now

    # Serialize career creation for this manager to prevent duplicate save slots.
    conn.execute("SELECT id FROM managers WHERE id=%s FOR UPDATE", (manager["id"],)).fetchone()
    active = conn.execute(
        "SELECT id FROM game_states WHERE manager_id=%s AND status='active' LIMIT 1", (manager["id"],)
    ).fetchone()
    if active:
        raise HTTPException(status_code=409, detail="У вас уже есть активное сохранение. Завершите его перед созданием нового.")

    selected_row = conn.execute(
        "SELECT * FROM sm27_club_pool WHERE source_id=%s", (body.club_source_id,)
    ).fetchone()
    if not selected_row:
        raise HTTPException(status_code=404, detail="Клуб не найден в игровом каталоге")
    selected = dict(selected_row)
    league_code = selected["league_code"]
    teams_rows = conn.execute(
        "SELECT * FROM sm27_club_pool WHERE league_code=%s ORDER BY sort_rank, club_name",
        (league_code,),
    ).fetchall()
    teams = [dict(row) for row in teams_rows]
    if len(teams) < 6:
        teams_rows = conn.execute(
            "SELECT * FROM sm27_club_pool WHERE country_iso=%s AND league_level=%s ORDER BY sort_rank, club_name",
            (selected.get("country_iso"), selected.get("league_level")),
        ).fetchall()
        teams = [dict(row) for row in teams_rows]
    if selected["source_id"] not in {team["source_id"] for team in teams}:
        teams.append(selected)
    log_stage(f"catalogue clubs={len(teams)}")

    league_name = selected.get("league_name") or "SM27 League"
    calendar_year_season = league_code in {"USA-MLS", "BRA-SA", "ARG-PD"}
    season_label = "2026" if calendar_year_season else "2026/27"
    career_start_date = (
        date(2026, 2, 1) if league_code == "USA-MLS"
        else date(2026, 1, 1) if calendar_year_season
        else date(2026, 7, 1)
    )
    age_reference_date = career_start_date
    tournament_code = f"SM27-{league_code}"[:64]
    tournament = conn.execute(
        """INSERT INTO tournaments (
               code,name,country,continent,tournament_type,tier,format,active,logo_url
           )
           VALUES (%s,%s,%s,%s,'league',%s,%s,true,%s)
           ON CONFLICT(code) DO UPDATE SET
             name=EXCLUDED.name,country=EXCLUDED.country,continent=EXCLUDED.continent,
             tier=EXCLUDED.tier,format=EXCLUDED.format,
             logo_url=coalesce(tournaments.logo_url,EXCLUDED.logo_url)
           RETURNING id""",
        (
            tournament_code, league_name, selected.get("country"),
            selected.get("continent") or "UEFA", selected.get("league_level") or 1,
            Jsonb({"points_win": 3, "points_draw": 1, "season": season_label, "calendar_year": calendar_year_season}),
            tournament_logo_url(league_name, selected.get("country")),
        ),
    ).fetchone()
    game_state = conn.execute(
        """INSERT INTO game_states (manager_id,save_slot,game_date,season,difficulty,status,save_name,game_settings)
           VALUES (%s,(SELECT coalesce(max(save_slot),0)+1 FROM game_states WHERE manager_id=%s),
                   %s,%s,'normal','active',%s,%s)
           RETURNING id""",
        (
            manager["id"], manager["id"], career_start_date, season_label, body.save_name.strip(),
            Jsonb({
                "source_snapshot": selected["source_snapshot"].isoformat(),
                "calendar_year_season": calendar_year_season,
                "calendar_start_date": career_start_date.isoformat(),
                "calendar_league_code": league_code,
            }),
        ),
    ).fetchone()
    game_state_id = str(game_state["id"])

    # Create all clubs in one round trip rather than inserting each club individually.
    club_insert_rows: list[tuple] = []
    for pool_row in teams:
        stars = float(pool_row.get("fifa_stars") or 2.5)
        reputation = max(10, min(100, int(
            pool_row.get("team_strength") or round(stars * 20)
        )))
        capacity = pool_row.get("stadium_capacity") or 20000
        budget = int(max(350_000, min(220_000_000, (reputation ** 2) * 22_000)))
        colors = (pool_row.get("colors_hex") or "").split(" | ")
        display_name = display_club_name(pool_row["club_name"])
        club_insert_rows.append((
            game_state_id, str(pool_row["source_id"]), display_name,
            (display_name or "SM27")[:20], pool_row.get("country") or "—",
            pool_row.get("league_name") or "Лига", pool_row.get("league_name") or "Лига",
            pool_row.get("continent") or "UEFA", stars, budget, pool_row.get("stadium"),
            capacity, pool_row.get("logo_url"), colors[0] or "#16A36A",
            colors[1] if len(colors) > 1 else "#102B22", reputation,
        ))
    with conn.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO clubs (
                 game_state_id,external_id,name,short_name,country,league,original_league,
                 continent,star_rating,budget,stadium_name,stadium_capacity,logo_url,
                 primary_color,secondary_color,reputation
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (game_state_id,external_id) DO UPDATE SET name=EXCLUDED.name""",
            club_insert_rows,
        )
    log_stage("clubs inserted")
    source_ids = [str(team["source_id"]) for team in teams]
    club_rows = conn.execute(
        """SELECT id,external_id FROM clubs
           WHERE game_state_id=%s AND external_id=ANY(%s)""",
        (game_state_id, source_ids),
    ).fetchall()
    club_id_by_source = {str(row["external_id"]): str(row["id"]) for row in club_rows}

    team_records: list[dict] = []
    for pool_row in teams:
        source_id = str(pool_row["source_id"])
        reputation = int(
            pool_row.get("team_strength")
            or round(float(pool_row.get("fifa_stars") or 2.5) * 20)
        )
        team_records.append({
            "id": club_id_by_source[source_id],
            "source_id": source_id,
            "name": pool_row["club_name"],
            "country": pool_row.get("country"),
            "league": pool_row.get("league_name") or league_name,
            "reputation": reputation,
        })

    with conn.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO club_tournaments (game_state_id,tournament_id,club_id,season)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            [(game_state_id, tournament["id"], team["id"], season_label) for team in team_records],
        )

    # One catalogue query replaces a separate player SELECT per club.
    source_ids = [str(team["source_id"]) for team in team_records]
    player_rows = conn.execute(
        """SELECT wp.club_source_id,wp.source_id,wp.name,wp.date_of_birth,wp.nationality,wp.position,
                  wp.market_value_eur,wp.market_value_as_of,wp.source_url,wp.raw_data,
                  wp.fc27_player_id,fc.position AS fc27_position,fc.overall AS fc27_overall,
                  fc.potential AS fc27_potential,fc.attributes AS fc27_attributes
           FROM world_player_catalog wp
           LEFT JOIN fc27_player_catalog fc ON fc.ea_player_id=wp.fc27_player_id
           WHERE wp.club_source_id=ANY(%s)
           ORDER BY wp.club_source_id,wp.market_value_eur DESC,wp.name""",
        (source_ids,),
    ).fetchall()
    players_by_source: dict[str, list[dict]] = {}
    for row in player_rows:
        players_by_source.setdefault(str(row["club_source_id"]), []).append(dict(row))
    log_stage(f"player catalogue rows={len(player_rows)}")

    player_insert_sql = """INSERT INTO players (
           game_state_id,club_id,external_id,name,nationality,birth_date,age,position,
           secondary_positions,overall,potential,market_value,weekly_wage,contract_end,
           attributes,original_data,source_name,source_url,data_verified_at,
           form,morale,sharpness,nationality_flag,profile_source,fc27_player_id,
           market_value_source
       ) VALUES (
           %s,%s,%s,%s,%s,%s,%s,%s,ARRAY[]::text[],%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
           50,70,85,%s,%s,%s,%s
       )
       ON CONFLICT (game_state_id,external_id) DO NOTHING"""
    player_inserts: list[tuple] = []
    teams_by_source = {str(team["source_id"]): team for team in team_records}

    for source_id, players_for_club in players_by_source.items():
        team = teams_by_source[source_id]
        for player in players_for_club[:30]:
            dob = player["date_of_birth"]
            age = (
                max(16, min(43, int((age_reference_date - dob).days / 365.2425)))
                if dob else 24
            )
            external_id = str(player["source_id"])
            fc27_id = player.get("fc27_player_id")
            researched = get_researched_profile(player["name"], team["name"]) if not fc27_id else None
            position = researched["position"] if researched else normalise_player_position(
                player.get("fc27_position") or player["position"], external_id
            )
            source_market_value = int(player.get("market_value_eur") or 0)
            if player.get("fc27_overall") is not None:
                overall = int(player["fc27_overall"])
            elif researched:
                overall = int(researched["overall"])
            else:
                overall = overall_from_market_value(
                    source_market_value, age, int(team["reputation"]),
                    int(hashlib.sha1(external_id.encode()).hexdigest()[:8], 16)
                )
            if player.get("fc27_potential") is not None:
                potential = int(player["fc27_potential"])
            elif researched:
                potential = int(researched["potential"])
            else:
                potential = max(
                    overall,
                    potential_from_overall(
                        overall, age, int(hashlib.sha1(external_id.encode()).hexdigest()[:8], 16)
                    ),
                )

            attributes = dict(player["fc27_attributes"] or {}) if fc27_id else {}
            if researched:
                attributes = dict(researched["attributes"])
            if not attributes:
                attributes = player_attributes(overall, position, external_id)

            if fc27_id:
                profile_source = "EA SPORTS FC 27 official ratings database"
            elif researched:
                profile_source = researched["profile_source"]
            else:
                profile_source = "SM27 estimate — player not matched in FC 27 ratings database"

            researched_value = int(researched["market_value"]) if researched and researched.get("market_value") else 0
            if researched_value > 0:
                market_value = researched_value
                market_value_source = "SofaScore"
                market_value_as_of = researched.get("market_value_as_of")
            elif source_market_value > 0:
                market_value = source_market_value
                market_value_source = "Transfermarkt"
                market_value_as_of = player.get("market_value_as_of")
            else:
                market_value = estimated_market_value(
                    overall, potential, age, team.get("league") or league_name,
                    team.get("country") or selected.get("country"), attributes,
                )
                market_value_source = "SM27 estimate"
                market_value_as_of = None

            raw = dict(player["raw_data"] or {})
            raw.update({
                "market_value_source": market_value_source,
                "market_value_as_of": _json_safe_date(market_value_as_of),
                "market_value_model": "league-age-ovr-potential-attributes-v1" if market_value_source == "SM27 estimate" else None,
                "game_rating_type": "EA SPORTS FC 27" if fc27_id else "SM27 researched estimate" if researched else "SM27 estimate",
                "contract_source": "SM27 estimate",
                "wage_source": "Capology 2026/27 estimate" if normalise_player_name(player["name"]).startswith(("cristianoronaldo", "inigomartinez")) else "SM27 career wage model",
                "research": researched["research"] if researched else None,
                "generated": False,
            })
            contract_end = estimated_contract_end(age, external_id)
            weekly_wage = estimated_weekly_wage(
                overall, age, int(team["reputation"]), player["name"]
            )
            player_inserts.append((
                game_state_id, team["id"], external_id, player["name"], player["nationality"],
                dob, age, position, overall, potential, market_value, weekly_wage, contract_end,
                Jsonb(attributes), Jsonb(raw),
                "EA FC 27" if fc27_id else "FotMob research / OpenFootballBase" if researched else "OpenFootballBase",
                researched["source_url"] if researched else player["source_url"], market_value_as_of,
                flag_for_nationality(player["nationality"]), profile_source, fc27_id,
                market_value_source,
            ))
    if player_inserts:
        with conn.cursor() as cursor:
            cursor.executemany(player_insert_sql, player_inserts)
    log_stage(f"real players inserted={len(player_inserts)}")

    # Add any missing academy placeholders in one batch.
    positions = ["GK", "GK", "RB", "CB", "CB", "LB", "CB", "RB", "CDM", "CM", "CM", "CAM", "CM", "CM", "RW", "LW", "ST", "CF"]
    club_ids = [team["id"] for team in team_records]
    existing_counts = conn.execute(
        """SELECT club_id,count(*)::int AS player_count
           FROM players WHERE game_state_id=%s AND club_id=ANY(%s)
           GROUP BY club_id""",
        (game_state_id, club_ids),
    ).fetchall()
    player_count_by_club = {str(row["club_id"]): int(row["player_count"]) for row in existing_counts}
    generated_rows: list[tuple] = []
    for team in team_records:
        existing = player_count_by_club.get(team["id"], 0)
        for index, position in enumerate(positions[existing:], start=existing + 1):
            source_id = f"generated:{team['id']}:{index}"
            age = 18 + (index % 12)
            overall = max(40, min(82, team["reputation"] - 8 + (index % 7)))
            potential = min(92, overall + 4 + (index % 7))
            attributes = player_attributes(overall, position, source_id)
            value = estimated_market_value(
                overall, potential, age, team.get("league") or league_name,
                team.get("country") or selected.get("country") or "", attributes,
            )
            generated_rows.append((
                game_state_id, team["id"], source_id, f"Игрок академии {index:02d}", age,
                position, overall, potential, value,
                estimated_weekly_wage(overall, age, team["reputation"], generated=True),
                estimated_contract_end(age, source_id), Jsonb(attributes),
                Jsonb({
                    "generated": True,
                    "note": "Fictional game placeholder, not a real player",
                    "market_value_source": "SM27 estimate",
                    "market_value_model": "league-age-ovr-potential-attributes-v1",
                }),
            ))
    if generated_rows:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO players (
                       game_state_id,club_id,external_id,name,age,position,secondary_positions,
                       overall,potential,market_value,weekly_wage,contract_end,attributes,
                       original_data,source_name,profile_source,market_value_source,form,morale,sharpness
                   ) VALUES (%s,%s,%s,%s,%s,%s,ARRAY[]::text[],%s,%s,%s,%s,%s,%s,%s,
                             'SM27 generated roster','SM27 generated academy player','SM27 estimate',50,70,85)""",
                generated_rows,
            )
    log_stage(f"academy players inserted={len(generated_rows)}")

    # Fetch every squad once, then calculate all starting XIs and persist all tactics in a batch.
    all_player_rows = conn.execute(
        """SELECT id,club_id,position,secondary_positions,overall
           FROM players
           WHERE game_state_id=%s AND club_id=ANY(%s)
           ORDER BY club_id,overall DESC,name""",
        (game_state_id, club_ids),
    ).fetchall()
    players_by_club: dict[str, list[dict]] = {}
    for row in all_player_rows:
        player = dict(row)
        players_by_club.setdefault(str(player["club_id"]), []).append(player)

    tactic_rows: list[tuple] = []
    for team in team_records:
        starters, bench, roles = best_lineup(players_by_club.get(team["id"], []), "4-3-3")
        tactic_rows.append((
            game_state_id, team["id"],
            Jsonb({"slot_roles": [
                {"player_id": player_id, "role": role}
                for player_id, role in zip(starters, roles)
            ]}),
            [uuid.UUID(player_id) for player_id in starters],
            [uuid.UUID(player_id) for player_id in bench],
        ))
    if tactic_rows:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO tactics (game_state_id,club_id,formation,mentality,style,starting_xi,bench)
                   VALUES (%s,%s,'4-3-3','balanced',%s,%s,%s)
                   ON CONFLICT (game_state_id,club_id) DO NOTHING""",
                tactic_rows,
            )
    log_stage(f"AI lineups prepared={len(tactic_rows)}")

    selected_game_club = next(
        row["id"] for row in team_records if str(row["source_id"]) == str(selected["source_id"])
    )
    conn.execute("UPDATE game_states SET managed_club_id=%s WHERE id=%s", (selected_game_club, game_state_id))
    create_schedule(conn, game_state_id, str(tournament["id"]), team_records, season=season_label, start_date=career_start_date)
    log_stage(f"schedule created clubs={len(team_records)}")
    LOGGER.info("Career creation completed total=%.3fs", time.perf_counter() - started_at)
    return {
        "ok": True,
        "save_id": game_state_id,
        "club": selected["club_name"],
        "league": league_name,
        "teams": len(team_records),
        "players_imported": len(player_inserts),
    }


@app.post("/api/saves/restart")
def restart_save(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    """Delete all career-scoped data for this manager so a new save starts from the immutable baseline."""
    # Keep reset and creation mutually exclusive for the same manager.
    conn.execute("SELECT id FROM managers WHERE id=%s FOR UPDATE", (manager["id"],)).fetchone()
    result = conn.execute(
        "DELETE FROM game_states WHERE manager_id=%s RETURNING id",
        (manager["id"],),
    ).fetchall()
    return {"ok": True, "reset_careers": len(result)}


@app.get("/api/dashboard")
def dashboard(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = require_save(conn, str(manager["id"]))
    game_state_id = str(save["id"])
    club_id = str(save["managed_club_id"])
    next_match = conn.execute(
        """SELECT f.id,f.match_date,f.matchday,f.status,h.name AS home_name,a.name AS away_name,h.logo_url AS home_logo,a.logo_url AS away_logo,
                  f.home_score,f.away_score,(f.home_club_id=%s) AS is_home
           FROM fixtures f JOIN clubs h ON h.id=f.home_club_id JOIN clubs a ON a.id=f.away_club_id
           WHERE f.game_state_id=%s AND f.status='scheduled'
             AND (f.home_club_id=%s OR f.away_club_id=%s)
           ORDER BY f.match_date LIMIT 1""",
        (club_id, game_state_id, club_id, club_id),
    ).fetchone()
    standings = conn.execute(
        """SELECT c.id,c.name,c.logo_url,ct.played,ct.won,ct.drawn,ct.lost,ct.goals_for,
                  ct.goals_against,ct.goal_difference,ct.points
           FROM club_tournaments ct JOIN clubs c ON c.id=ct.club_id
           WHERE ct.game_state_id=%s AND ct.season=%s AND ct.tournament_id=(
             SELECT tournament_id FROM club_tournaments WHERE game_state_id=%s AND season=%s AND club_id=%s LIMIT 1)
           ORDER BY ct.points DESC, coalesce(ct.goal_difference,0) DESC, ct.goals_for DESC, c.name LIMIT 30""",
        (game_state_id, save["season"], game_state_id, save["season"], club_id),
    ).fetchall()
    squad = conn.execute(
        "SELECT count(*) AS players, coalesce(round(avg(overall)),0)::int AS avg_overall, coalesce(sum(market_value),0)::bigint AS squad_value FROM players WHERE game_state_id=%s AND club_id=%s",
        (game_state_id, club_id),
    ).fetchone()
    my_position = next((index + 1 for index, row in enumerate(standings) if str(row["id"]) == club_id), None)
    return serialise({
        "save": save,
        "next_match": dict(next_match) if next_match else None,
        "standings": [dict(row) for row in standings],
        "my_position": my_position,
        "squad": dict(squad),
    })


@app.get("/api/squad")
def squad(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> list:
    save = require_save(conn, str(manager["id"]))
    rows = conn.execute(
        """SELECT p.id,p.name,p.nationality,p.birth_date,p.age,p.position,p.secondary_positions,
                  p.nationality_flag,
                  p.overall,GREATEST(1,LEAST(99,p.overall + ROUND(
                    (p.form-50)*0.06 + (p.morale-70)*0.04 + (p.sharpness-85)*0.04 - p.fatigue*0.08
                  )::int)) AS dynamic_overall,
                  p.potential,p.market_value,p.market_value_source,p.weekly_wage,p.contract_end,
                  p.fatigue,p.form,p.morale,p.sharpness,p.position_training_target,
                  p.position_training_progress,p.fc27_player_id,p.injury_type,p.injury_until,
                  p.suspension_matches,p.suspension_reason,p.suspension_return_date,
                  p.attributes,p.original_data,p.profile_source,p.source_url,
                  fc.source_url AS fc27_source_url
           FROM players p
           LEFT JOIN fc27_player_catalog fc ON fc.ea_player_id=p.fc27_player_id
           WHERE p.game_state_id=%s AND p.club_id=%s
           ORDER BY CASE p.position WHEN 'GK' THEN 0
                     WHEN 'CB' THEN 1 WHEN 'RB' THEN 1 WHEN 'LB' THEN 1 WHEN 'RWB' THEN 1 WHEN 'LWB' THEN 1
                     WHEN 'CDM' THEN 2 WHEN 'CM' THEN 2 WHEN 'CAM' THEN 2
                     WHEN 'RM' THEN 3 WHEN 'LM' THEN 3 WHEN 'RW' THEN 4 WHEN 'LW' THEN 4 ELSE 5 END,
                    p.overall DESC, p.name""",
        (save["id"], save["managed_club_id"]),
    ).fetchall()
    result = []
    game_date = save["game_date"].date() if isinstance(save["game_date"], datetime) else save["game_date"]
    for row in rows:
        player = dict(row)
        player["nationality_flag"] = player.get("nationality_flag") or flag_for_nationality(player.get("nationality"))
        player["secondary_positions"] = list(player.get("secondary_positions") or [])
        injury_until = player.get("injury_until")
        if isinstance(injury_until, datetime):
            injury_until = injury_until.date()
        player["injury_days_remaining"] = max(0, (injury_until - game_date).days) if injury_until and game_date else 0
        injury = INJURY_BY_KEY.get(player.get("injury_type"))
        player["injury_name"] = injury["name"] if injury else player.get("injury_type")
        player["injury_return_date"] = injury_until.isoformat() if injury_until else None
        player["suspension_matches"] = int(player.get("suspension_matches") or 0)
        result.append(player)
    return serialise(result)


@app.post("/api/players/{player_id}/position-training")
def start_position_training(
    player_id: str,
    body: PositionTrainingIn,
    manager: dict = Depends(manager_dep),
    conn: Connection = Depends(db_dep),
) -> dict:
    save = require_save(conn, str(manager["id"]))
    player = conn.execute(
        """SELECT id,position,secondary_positions,position_training_target
           FROM players WHERE id=%s AND game_state_id=%s AND club_id=%s""",
        (player_id, save["id"], save["managed_club_id"]),
    ).fetchone()
    if not player:
        raise HTTPException(status_code=404, detail="Игрок не найден в вашем составе")
    target = body.position.strip().upper()
    if target not in SECONDARY_POSITIONS.get(player["position"], ()):
        raise HTTPException(status_code=422, detail="Эту позицию нельзя прокачать для выбранной основной позиции")
    if target in list(player["secondary_positions"] or []):
        raise HTTPException(status_code=409, detail="Эта дополнительная позиция уже освоена")
    if player["position_training_target"]:
        raise HTTPException(status_code=409, detail="Игрок уже прокачивает другую позицию")
    conn.execute(
        """UPDATE players
           SET position_training_target=%s,position_training_progress=0,updated_at=now()
           WHERE id=%s""",
        (target, player_id),
    )
    return {"ok": True, "position": target, "progress": 0}


@app.get("/api/tactics")
def get_tactics(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = require_save(conn, str(manager["id"]))
    tactic = conn.execute(
        "SELECT formation,mentality,style,starting_xi,bench FROM tactics WHERE game_state_id=%s AND club_id=%s",
        (save["id"], save["managed_club_id"]),
    ).fetchone()
    if tactic:
        return serialise(dict(tactic))
    squad = conn.execute(
        """SELECT id,position,secondary_positions,
                  GREATEST(1,LEAST(99,overall + ROUND(
                    (form-50)*0.06 + (morale-70)*0.04 + (sharpness-85)*0.04 - fatigue*0.08
                  )::int)) AS overall
           FROM players WHERE game_state_id=%s AND club_id=%s ORDER BY overall DESC""",
        (save["id"], save["managed_club_id"]),
    ).fetchall()
    starters, bench, roles = best_lineup([dict(row) for row in squad], "4-3-3")
    return {
        "formation": "4-3-3", "mentality": "balanced",
        "style": {"build_up": "balanced", "chance_creation": "balanced", "defensive_approach": "balanced",
                  "width": 50, "depth": 55, "pressing": "on_mistake", "focus": "balanced",
                  "slot_roles": roles},
        "starting_xi": starters, "bench": bench,
    }


@app.put("/api/tactics")
def update_tactics(body: TacticIn, manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = require_save(conn, str(manager["id"]))
    valid_ids = {
        str(row["id"]) for row in conn.execute(
            "SELECT id FROM players WHERE game_state_id=%s AND club_id=%s", (save["id"], save["managed_club_id"])
        ).fetchall()
    }
    if len(body.starting_xi) != 11:
        raise HTTPException(status_code=422, detail="В стартовом составе должно быть ровно 11 игроков")
    if not 5 <= len(body.bench) <= 9:
        raise HTTPException(status_code=422, detail="В запасе должно быть от 5 до 9 игроков")
    combined = body.starting_xi + body.bench
    if len(set(combined)) != len(combined):
        raise HTTPException(status_code=422, detail="Один игрок не может одновременно находиться в стартовом составе и запасе")
    if any(player_id not in valid_ids for player_id in combined):
        raise HTTPException(status_code=422, detail="В тактике можно выбрать только игроков своего клуба")
    conn.execute(
        """INSERT INTO tactics (game_state_id,club_id,formation,mentality,style,starting_xi,bench)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (game_state_id,club_id) DO UPDATE SET formation=EXCLUDED.formation,
             mentality=EXCLUDED.mentality,style=EXCLUDED.style,starting_xi=EXCLUDED.starting_xi,
             bench=EXCLUDED.bench,updated_at=now()""",
        (save["id"], save["managed_club_id"], body.formation, body.mentality, Jsonb(body.style),
         [uuid.UUID(player_id) for player_id in body.starting_xi], [uuid.UUID(player_id) for player_id in body.bench]),
    )
    return {"ok": True}


@app.get("/api/fixtures")
def fixtures(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep), limit: int = 400) -> list:
    save = require_save(conn, str(manager["id"]))
    limit = max(1, min(limit, 400))
    managed_club_id = save["managed_club_id"]
    rows = conn.execute(
        """SELECT f.id,f.match_date,f.matchday,f.stage,f.status,f.home_score,f.away_score,
                  h.name AS home_name,a.name AS away_name,h.logo_url AS home_logo,a.logo_url AS away_logo,
                  f.tournament_id,t.logo_url AS tournament_logo,coalesce(t.name,%s) AS tournament_name,
                  CASE WHEN f.stage IS NOT NULL AND btrim(f.stage)<>'' THEN f.stage
                       WHEN f.matchday IS NOT NULL THEN 'ТУР '||f.matchday::text
                       ELSE 'МАТЧ' END AS stage_label,
                  (f.home_club_id=%s) AS is_home,
                  CASE WHEN f.home_club_id=%s THEN a.name ELSE h.name END AS opponent_name,
                  CASE WHEN f.home_club_id=%s THEN a.logo_url ELSE h.logo_url END AS opponent_logo,
                  CASE WHEN f.status<>'completed' THEN NULL
                       WHEN f.home_score=f.away_score THEN 'draw'
                       WHEN (f.home_club_id=%s AND f.home_score>f.away_score)
                         OR (f.away_club_id=%s AND f.away_score>f.home_score) THEN 'win'
                       ELSE 'loss' END AS result
           FROM fixtures f
           JOIN clubs h ON h.id=f.home_club_id
           JOIN clubs a ON a.id=f.away_club_id
           LEFT JOIN tournaments t ON t.id=f.tournament_id
           WHERE f.game_state_id=%s AND (f.home_club_id=%s OR f.away_club_id=%s)
           ORDER BY f.match_date ASC LIMIT %s""",
        (save["league"], managed_club_id, managed_club_id, managed_club_id,
         managed_club_id, managed_club_id, save["id"], managed_club_id, managed_club_id, limit),
    ).fetchall()
    return serialise([dict(row) for row in rows])


def update_table(conn: Connection, fixture: dict) -> None:
    home_score, away_score = fixture["home_score"], fixture["away_score"]
    for club_id, scored, conceded in [
        (fixture["home_club_id"], home_score, away_score),
        (fixture["away_club_id"], away_score, home_score),
    ]:
        won = int(scored > conceded)
        drawn = int(scored == conceded)
        lost = int(scored < conceded)
        points = won * 3 + drawn
        conn.execute(
            """UPDATE club_tournaments SET played=played+1,won=won+%s,drawn=drawn+%s,lost=lost+%s,
                       goals_for=goals_for+%s,goals_against=goals_against+%s
               WHERE game_state_id=%s AND club_id=%s""",
            (won, drawn, lost, scored, conceded, fixture["game_state_id"], club_id),
        )
        conn.execute(
            "UPDATE club_tournaments SET points=points+%s WHERE game_state_id=%s AND club_id=%s",
            (points, fixture["game_state_id"], club_id),
        )



def update_player_condition(conn: Connection, game_state_id: str, club_id: str, result: str) -> None:
    morale_delta = 3 if result == "win" else -3 if result == "loss" else 1
    form_delta = 4 if result == "win" else -3 if result == "loss" else 1
    conn.execute(
        """UPDATE players SET
             fatigue=LEAST(100,fatigue+12),
             sharpness=GREATEST(20,LEAST(100,sharpness+2)),
             form=GREATEST(0,LEAST(100,form+%s)),
             morale=GREATEST(0,LEAST(100,morale+%s)),
             updated_at=now()
           WHERE game_state_id=%s AND club_id=%s""",
        (form_delta,morale_delta,game_state_id,club_id),
    )


def advance_position_training(conn: Connection, game_state_id: str, club_id: str) -> None:
    conn.execute(
        """UPDATE players
           SET secondary_positions=CASE
                 WHEN position_training_progress+5>=100
                   AND position_training_target IS NOT NULL
                   AND NOT (position_training_target=ANY(secondary_positions))
                 THEN array_append(secondary_positions,position_training_target)
                 ELSE secondary_positions
               END,
               position_training_progress=CASE
                 WHEN position_training_progress+5>=100 THEN 0
                 ELSE LEAST(100,position_training_progress+5)
               END,
               position_training_target=CASE
                 WHEN position_training_progress+5>=100 THEN NULL
                 ELSE position_training_target
               END,
               updated_at=now()
           WHERE game_state_id=%s AND club_id=%s AND position_training_target IS NOT NULL""",
        (game_state_id,club_id),
    )


def _allocate_integer(total: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    safe = [max(0.05, float(value)) for value in weights]
    weight_sum = sum(safe)
    exact = [max(0, int(total)) * value / weight_sum for value in safe]
    result = [int(value) for value in exact]
    remainder = max(0, int(total)) - sum(result)
    order = sorted(range(len(exact)), key=lambda index: exact[index] - result[index], reverse=True)
    for index in order[:remainder]:
        result[index] += 1
    return result


def _allocate_bounded(total: int, capacities: list[int], weights: list[float], rng: random.Random) -> list[int]:
    result = [0 for _ in capacities]
    remaining = min(max(0, int(total)), sum(max(0, cap) for cap in capacities))
    while remaining:
        candidates = [index for index, cap in enumerate(capacities) if result[index] < max(0, cap)]
        if not candidates:
            break
        chosen = rng.choices(candidates, weights=[max(0.05, weights[index]) for index in candidates], k=1)[0]
        result[chosen] += 1
        remaining -= 1
    return result


def _position_weight(position: str, group: str) -> float:
    position = (position or "CM").upper()
    if group == "shots":
        return 0.15 if position == "GK" else 2.0 if position in {"ST", "CF"} else 1.55 if position in {"LW", "RW", "CAM"} else 0.95 if position in {"CM", "RM", "LM"} else 0.5
    if group == "passes":
        return 0.75 if position == "GK" else 1.35 if position in {"CB", "LB", "RB", "LWB", "RWB"} else 1.5 if position in {"CDM", "CM", "CAM"} else 1.0 if position in {"RM", "LM", "LW", "RW"} else 0.72
    if group == "tackles":
        return 0.5 if position == "GK" else 1.65 if position in {"CB", "LB", "RB", "LWB", "RWB", "CDM"} else 1.0
    if group == "key_passes":
        return 0.1 if position == "GK" else 1.7 if position in {"CAM", "CM", "RM", "LM", "LW", "RW"} else 1.05 if position in {"ST", "CF"} else 0.45
    return 1.0


def _match_lineups(
    conn: Connection,
    game_state_id: str,
    home_club_id: str,
    away_club_id: str,
    match_date: date,
    tournament_id: str | None = None,
    season: str | None = None,
) -> tuple[dict[str, list[dict]], list[str]]:
    rows = conn.execute(
        """SELECT p.id,p.club_id,p.name,p.position,p.secondary_positions,p.overall,p.attributes,
                  p.injury_until,p.injury_type,
                  coalesce(d.suspension_matches,p.suspension_matches,0) AS suspension_matches,
                  p.form,p.morale,p.sharpness,p.fatigue,
                  coalesce(t.starting_xi,ARRAY[]::uuid[]) AS starting_xi,
                  role.target_position
           FROM players p
           LEFT JOIN tactics t ON t.game_state_id=p.game_state_id AND t.club_id=p.club_id
           LEFT JOIN player_competition_discipline d
             ON d.game_state_id=p.game_state_id AND d.player_id=p.id
            AND d.tournament_id=%s AND d.season=%s
           LEFT JOIN LATERAL (
             SELECT item->>'role' AS target_position
             FROM jsonb_array_elements(coalesce(t.style->'slot_roles','[]'::jsonb)) item
             WHERE item->>'player_id'=p.id::text
             LIMIT 1
           ) role ON true
           WHERE p.game_state_id=%s AND p.club_id IN (%s,%s)
           ORDER BY p.club_id,p.overall DESC,p.name""",
        (tournament_id, season, game_state_id, home_club_id, away_club_id),
    ).fetchall()
    by_club: dict[str, list[dict]] = {str(home_club_id): [], str(away_club_id): []}
    suspended_ids: list[str] = []
    for row in rows:
        player = dict(row)
        club_id = str(player["club_id"])
        player["id"] = str(player["id"])
        player["starting_xi"] = [str(item) for item in (player.get("starting_xi") or [])]
        if int(player.get("suspension_matches") or 0) > 0:
            suspended_ids.append(player["id"])
        by_club.setdefault(club_id, []).append(player)

    selected: dict[str, list[dict]] = {}
    for club_id, squad in by_club.items():
        available = []
        for player in squad:
            until = player.get("injury_until")
            if isinstance(until, datetime):
                until = until.date()
            if until and until > match_date:
                continue
            if int(player.get("suspension_matches") or 0) > 0:
                continue
            available.append(player)
        xi_ids = next((player["starting_xi"] for player in squad if player["starting_xi"]), [])
        by_id = {player["id"]: player for player in available}
        starters = [by_id[player_id] for player_id in xi_ids if player_id in by_id][:11]
        used = {player["id"] for player in starters}
        starters.extend(player for player in available if player["id"] not in used and len(starters) < 11)
        for player in starters:
            condition_delta = round(
                (float(player.get("form") or 50) - 50) * 0.06
                + (float(player.get("morale") or 70) - 70) * 0.04
                + (float(player.get("sharpness") or 85) - 85) * 0.04
                - float(player.get("fatigue") or 0) * 0.08
            )
            role_penalty = position_penalty(
                str(player.get("position") or "CM"),
                list(player.get("secondary_positions") or []),
                str(player.get("target_position") or player.get("position") or "CM"),
            )
            player["effective_overall"] = max(
                1, min(99, int(player["overall"]) + condition_delta + role_penalty)
            )
        selected[club_id] = starters
    return selected, suspended_ids


def _record_match_detail(
    conn: Connection,
    save: dict,
    fixture: dict,
    result: dict,
    lineups: dict[str, list[dict]],
    suspended_at_start: list[str],
    match_date: date,
    rng: random.Random,
) -> dict:
    home_id, away_id = str(fixture["home_club_id"]), str(fixture["away_club_id"])
    player_records: dict[str, dict] = {}
    event_rows: list[tuple] = []
    injury_updates: list[tuple] = []
    yellow_by_player: dict[str, int] = {}
    red_by_player: dict[str, int] = {}
    team_details: dict[str, dict] = {}
    team_cards: dict[str, dict[str, int]] = {
        home_id: {"yellow": 0, "red": 0},
        away_id: {"yellow": 0, "red": 0},
    }
    goal_events: list[dict] = []

    for club_id, opponents_id, prefix in ((home_id, away_id, "home"), (away_id, home_id, "away")):
        starters = lineups.get(club_id, [])
        shots = int(result[f"{prefix}_shots"])
        shots_on_target = int(result[f"{prefix}_shots_on_target"])
        possession = int(result[f"{prefix}_possession"])
        goals = int(result[f"{prefix}_score"])
        positions = [str(player.get("position") or "CM") for player in starters]
        shot_weights = [_position_weight(position, "shots") for position in positions]
        shot_alloc = _allocate_integer(shots, shot_weights)
        sot_alloc = _allocate_bounded(
            shots_on_target, shot_alloc, [value + 0.15 for value in shot_alloc], rng
        )
        pass_total = max(260, min(720, int(345 + possession * 2.5 + rng.randint(-38, 48))))
        pass_alloc = _allocate_integer(
            pass_total,
            [_position_weight(position, "passes") * rng.uniform(0.88, 1.12) for position in positions],
        )
        tackle_total = rng.randint(9, 23)
        tackle_alloc = _allocate_integer(
            tackle_total, [_position_weight(position, "tackles") for position in positions]
        )
        interception_total = rng.randint(5, 16)
        interception_alloc = _allocate_integer(
            interception_total,
            [0.3 if position == "GK" else 1.5 if position in {"CB", "LB", "RB", "CDM"} else 0.8 for position in positions],
        )
        key_total = rng.randint(4, 13)
        key_alloc = _allocate_integer(
            key_total, [_position_weight(position, "key_passes") for position in positions]
        )
        records: list[dict] = []
        for index, player in enumerate(starters):
            passes = pass_alloc[index] if index < len(pass_alloc) else 0
            pass_accuracy = rng.uniform(0.74, 0.94)
            records.append({
                "game_state_id": str(save["id"]),
                "fixture_id": str(fixture["id"]),
                "tournament_id": str(fixture["tournament_id"]) if fixture.get("tournament_id") else None,
                "club_id": club_id,
                "player_id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "minutes_played": 90,
                "rating": 6.05 + (float(player.get("effective_overall") or player["overall"]) - 65) * 0.035 + rng.uniform(-0.34, 0.38),
                "goals": 0,
                "assists": 0,
                "shots": shot_alloc[index] if index < len(shot_alloc) else 0,
                "shots_on_target": sot_alloc[index] if index < len(sot_alloc) else 0,
                "passes": passes,
                "accurate_passes": int(round(passes * pass_accuracy)),
                "tackles": tackle_alloc[index] if index < len(tackle_alloc) else 0,
                "interceptions": interception_alloc[index] if index < len(interception_alloc) else 0,
                "key_passes": key_alloc[index] if index < len(key_alloc) else 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "saves": 0,
                "clean_sheet": False,
                "is_mvp": False,
            })
        record_by_id = {record["player_id"]: record for record in records}
        field_players = [player for player in starters if player.get("position") != "GK"] or starters
        scorer_weights = [_position_weight(str(player.get("position") or "CM"), "shots") for player in field_players]
        for _ in range(goals):
            if not field_players:
                break
            scorer = rng.choices(field_players, weights=scorer_weights, k=1)[0]
            scorer_record = record_by_id[scorer["id"]]
            scorer_record["goals"] += 1
            scorer_record["rating"] += 0.82
            assist_player = None
            if len(field_players) > 1 and rng.random() < 0.76:
                assist_options = [player for player in field_players if player["id"] != scorer["id"]]
                assist_player = rng.choice(assist_options)
                assist_record = record_by_id[assist_player["id"]]
                assist_record["assists"] += 1
                assist_record["rating"] += 0.42
            minute = rng.randint(3, 90)
            goal_events.append({
                "club_id": club_id,
                "player_id": scorer["id"],
                "assist_player_id": assist_player["id"] if assist_player else None,
                "minute": minute,
                "event_type": "goal",
            })
            event_rows.append((
                fixture["id"], minute, "goal", club_id, scorer["id"],
                assist_player["id"] if assist_player else None,
                Jsonb({"simulated": True, "assist": assist_player["name"] if assist_player else None}),
            ))

        yellow_count = rng.choices([0, 1, 2, 3], weights=[0.08, 0.38, 0.40, 0.14], k=1)[0]
        card_candidates = [player for player in field_players]
        rng.shuffle(card_candidates)
        for player in card_candidates[:yellow_count]:
            record = record_by_id[player["id"]]
            record["yellow_cards"] += 1
            record["rating"] -= 0.22
            team_cards[club_id]["yellow"] += 1
            yellow_by_player[player["id"]] = yellow_by_player.get(player["id"], 0) + 1
            minute = rng.randint(12, 88)
            event_rows.append((
                fixture["id"], minute, "yellow_card", club_id, player["id"], None,
                Jsonb({"simulated": True, "reason": rng.choice(["Тактический фол", "Срыв атаки", "Жёсткий подкат", "Спор с арбитром"])}),
            ))

        if field_players and rng.random() < 0.018:
            red_player = rng.choice(field_players)
            record = record_by_id[red_player["id"]]
            record["red_cards"] += 1
            record["rating"] -= 1.1
            team_cards[club_id]["red"] += 1
            red_by_player[red_player["id"]] = 2 if rng.random() < 0.22 else 1
            minute = rng.randint(22, 89)
            event_rows.append((
                fixture["id"], minute, "red_card", club_id, red_player["id"], None,
                Jsonb({"simulated": True, "reason": "Удаление"}),
            ))

        # About two to four time-loss injuries per club across a 30–38 match season.
        for player in starters:
            if rng.random() >= 0.008:
                continue
            injury = rng.choice(INJURY_CATALOG)
            days_out = rng.randint(int(injury["min_days"]), int(injury["max_days"]))
            return_date = match_date + timedelta(days=days_out)
            minute = rng.randint(8, 86)
            injury_updates.append((injury["key"], return_date, player["id"]))
            event_rows.append((
                fixture["id"], minute, "injury", club_id, player["id"], None,
                Jsonb({"simulated": True, "injury": injury["key"], "name": injury["name"], "days_out": days_out, "return_date": return_date.isoformat(), "reason": "Повреждение во время матча"}),
            ))
            record_by_id[player["id"]]["minutes_played"] = minute
            break

        for player in starters:
            record = record_by_id[player["id"]]
            if player.get("position") == "GK":
                opponent_score = int(result[f"{'away' if prefix == 'home' else 'home'}_score"])
                record["saves"] = max(0, int(result[f"{'away' if prefix == 'home' else 'home'}_shots_on_target"]) - opponent_score)
                record["clean_sheet"] = opponent_score == 0
                if record["clean_sheet"]:
                    record["rating"] += 0.42
                record["rating"] += min(0.55, record["saves"] * 0.08)
            record["rating"] = round(max(4.0, min(9.9, record["rating"])), 1)
            player_records[player["id"]] = record

        passes = sum(record["passes"] for record in records)
        accurate = sum(record["accurate_passes"] for record in records)
        team_details[club_id] = {
            "goals": goals,
            "shots": shots,
            "shots_on_target": shots_on_target,
            "passes": passes,
            "accurate_passes": accurate,
            "pass_accuracy": round(accurate * 100 / passes, 1) if passes else 0,
            "xg": float(result[f"{prefix}_xg"]),
            "possession": possession,
            "yellow_cards": team_cards[club_id]["yellow"],
            "red_cards": team_cards[club_id]["red"],
            "offsides": rng.randint(0, 4),
            "corners": rng.randint(2, 10),
            "fouls": rng.randint(8, 18),
        }

    if suspended_at_start:
        conn.execute(
            "UPDATE players SET suspension_matches=GREATEST(0,suspension_matches-1),
               suspension_reason=CASE WHEN suspension_matches<=1 THEN NULL ELSE suspension_reason END,
               suspension_return_date=CASE WHEN suspension_matches<=1 THEN NULL ELSE suspension_return_date END,
               updated_at=now() WHERE id=ANY(%s)",
            (suspended_at_start,),
        )
        if fixture.get("tournament_id"):
            conn.execute(
                """UPDATE player_competition_discipline
                   SET suspension_matches=GREATEST(0,suspension_matches-1),
                       suspension_reason=CASE WHEN suspension_matches<=1 THEN NULL ELSE suspension_reason END,
                       suspension_return_date=CASE WHEN suspension_matches<=1 THEN NULL ELSE suspension_return_date END,
                       updated_at=now()
                   WHERE game_state_id=%s AND tournament_id=%s AND season=%s AND player_id=ANY(%s)""",
                (save["id"], fixture["tournament_id"], fixture["season"], suspended_at_start),
            )

    # Accumulate cards with one batched read, avoiding per-player database round trips.
    discipline_changes: dict[str, dict[str, int]] = {}
    disciplined_ids = sorted(set(yellow_by_player) | set(red_by_player))
    existing_discipline: dict[str, dict] = {}
    if disciplined_ids and fixture.get("tournament_id"):
        existing_rows = conn.execute(
            """SELECT player_id,yellow_cards,red_cards,suspension_matches
               FROM player_competition_discipline
               WHERE game_state_id=%s AND tournament_id=%s AND season=%s
                 AND player_id=ANY(%s)""",
            (save["id"], fixture["tournament_id"], fixture["season"], disciplined_ids),
        ).fetchall()
        existing_discipline = {str(row["player_id"]): dict(row) for row in existing_rows}
    for player_id in disciplined_ids:
        current = existing_discipline.get(player_id)
        old_yellows = int(current["yellow_cards"]) if current else 0
        old_reds = int(current["red_cards"]) if current else 0
        old_suspensions = int(current["suspension_matches"]) if current else 0
        added_yellows = yellow_by_player.get(player_id, 0)
        added_reds = 1 if player_id in red_by_player else 0
        added_ban = max(0, (old_yellows + added_yellows) // 5 - old_yellows // 5) + red_by_player.get(player_id, 0)
        ban_reason = (
            "Красная карточка" if player_id in red_by_player
            else "Пятая жёлтая карточка в турнире" if added_ban else None
        )
        return_row = None
        if added_ban:
            return_row = conn.execute(
                """SELECT match_date::date AS return_date
                   FROM fixtures
                   WHERE game_state_id=%s AND tournament_id=%s AND season=%s AND status='scheduled'
                     AND match_date::date>%s
                     AND (home_club_id=(SELECT club_id FROM players WHERE id=%s)
                          OR away_club_id=(SELECT club_id FROM players WHERE id=%s))
                   ORDER BY match_date OFFSET %s LIMIT 1""",
                (save["id"],fixture["tournament_id"],fixture["season"],match_date,player_id,player_id,added_ban),
            ).fetchone()
        discipline_changes[player_id] = {
            "yellow_cards": old_yellows + added_yellows,
            "red_cards": old_reds + added_reds,
            "suspension_matches": old_suspensions + added_ban,
            "added_ban": added_ban,
            "suspension_reason": ban_reason,
            "suspension_return_date": return_row["return_date"] if return_row else None,
        }
    if discipline_changes:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO player_competition_discipline
                       (game_state_id,tournament_id,season,player_id,yellow_cards,red_cards,suspension_matches,
                        suspension_reason,suspension_return_date)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (game_state_id,tournament_id,season,player_id)
                   DO UPDATE SET yellow_cards=EXCLUDED.yellow_cards,
                                 red_cards=EXCLUDED.red_cards,
                                 suspension_matches=EXCLUDED.suspension_matches,
                                 suspension_reason=coalesce(EXCLUDED.suspension_reason,player_competition_discipline.suspension_reason),
                                 suspension_return_date=coalesce(EXCLUDED.suspension_return_date,player_competition_discipline.suspension_return_date),
                                 updated_at=now()""",
                [
                    (save["id"], fixture["tournament_id"], fixture["season"], player_id,
                     values["yellow_cards"], values["red_cards"], values["suspension_matches"],
                     values["suspension_reason"], values["suspension_return_date"])
                    for player_id, values in discipline_changes.items()
                ],
            )
        ban_updates = [
            (values["added_ban"],values["suspension_reason"],values["suspension_return_date"],player_id)
            for player_id,values in discipline_changes.items() if values["added_ban"]
        ]
        if ban_updates:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """UPDATE players SET suspension_matches=suspension_matches+%s,
                       suspension_reason=%s,suspension_return_date=%s,updated_at=now() WHERE id=%s""",
                    ban_updates,
                )

    if injury_updates:
        with conn.cursor() as cursor:
            cursor.executemany(
                """UPDATE players SET injury_type=%s,injury_until=%s,updated_at=now()
                   WHERE id=%s AND (injury_until IS NULL OR injury_until<=%s)""",
                [(injury, until, player_id, match_date) for injury, until, player_id in injury_updates],
            )

    all_records = list(player_records.values())
    mvp = max(all_records, key=lambda item: item["rating"]) if all_records else None
    if mvp:
        mvp["is_mvp"] = True
    for record in all_records:
        record.setdefault("is_mvp", False)

    insert_player_stats = [
        (
            record["game_state_id"], record["fixture_id"], record["tournament_id"],
            record["club_id"], record["player_id"], record["minutes_played"], record["rating"],
            record["goals"], record["assists"], record["shots"], record["shots_on_target"],
            record["passes"], record["accurate_passes"], record["tackles"], record["interceptions"],
            record["key_passes"], record["yellow_cards"], record["red_cards"], record["saves"],
            record["clean_sheet"], record["is_mvp"], False,
        )
        for record in all_records
    ]
    if insert_player_stats:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO fixture_player_stats (
                       game_state_id,fixture_id,tournament_id,club_id,player_id,minutes_played,rating,
                       goals,assists,shots,shots_on_target,passes,accurate_passes,tackles,interceptions,
                       key_passes,yellow_cards,red_cards,saves,clean_sheet,is_mvp,is_estimate
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (fixture_id,player_id) DO UPDATE SET
                       minutes_played=EXCLUDED.minutes_played,rating=EXCLUDED.rating,
                       goals=EXCLUDED.goals,assists=EXCLUDED.assists,shots=EXCLUDED.shots,
                       shots_on_target=EXCLUDED.shots_on_target,passes=EXCLUDED.passes,
                       accurate_passes=EXCLUDED.accurate_passes,tackles=EXCLUDED.tackles,
                       interceptions=EXCLUDED.interceptions,key_passes=EXCLUDED.key_passes,
                       yellow_cards=EXCLUDED.yellow_cards,red_cards=EXCLUDED.red_cards,
                       saves=EXCLUDED.saves,clean_sheet=EXCLUDED.clean_sheet,is_mvp=EXCLUDED.is_mvp,
                       is_estimate=false""",
                insert_player_stats,
            )
    if event_rows:
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO match_events
                       (fixture_id,minute,event_type,club_id,player_id,assist_player_id,detail)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                event_rows,
            )

    mvp_detail = None
    if mvp:
        mvp_detail = {
            "player_id": mvp["player_id"],
            "name": mvp["name"],
            "club_id": mvp["club_id"],
            "rating": mvp["rating"],
        }
    return {
        "version": 1,
        "historical_estimate": False,
        "home": team_details.get(home_id, {}),
        "away": team_details.get(away_id, {}),
        "mvp": mvp_detail,
        "goal_events": [
            {"minute": item["minute"], "club_id": item["club_id"], "player_id": item["player_id"],
             "assist_player_id": item["assist_player_id"], "event_type": item["event_type"]}
            for item in goal_events
        ],
    }


def simulate_matchday(
    conn: Connection,
    save: dict,
    match_date: date,
    matchday: int | None = None,
    tournament_id: str | None = None,
    through_date: date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Simulate only fixtures through a date; matchdays may span multiple dates."""
    conn.execute(
        """UPDATE players SET fatigue=GREATEST(0,fatigue-20),
                  sharpness=LEAST(100,sharpness+4),updated_at=now()
           WHERE game_state_id=%s""",
        (save["id"],),
    )
    if matchday is not None and tournament_id:
        rows = conn.execute(
            """SELECT f.*,h.name AS home_name,a.name AS away_name,
                      h.reputation AS home_rep,a.reputation AS away_rep
               FROM fixtures f JOIN clubs h ON h.id=f.home_club_id JOIN clubs a ON a.id=f.away_club_id
               WHERE f.game_state_id=%s AND f.status='scheduled'
                 AND f.matchday=%s AND f.tournament_id=%s
                 AND (%s IS NULL OR f.match_date::date<=%s)
               ORDER BY f.match_date,f.id""",
            (save["id"], matchday, tournament_id, through_date, through_date),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT f.*,h.name AS home_name,a.name AS away_name,
                      h.reputation AS home_rep,a.reputation AS away_rep
               FROM fixtures f JOIN clubs h ON h.id=f.home_club_id JOIN clubs a ON a.id=f.away_club_id
               WHERE f.game_state_id=%s AND f.status='scheduled' AND f.match_date::date=%s
               ORDER BY f.match_date,f.id""",
            (save["id"], match_date),
        ).fetchall()

    completed: list[dict] = []
    manager_results: list[dict] = []
    managed_club_id = str(save["managed_club_id"])
    last_match_date = match_date
    for row in rows:
        fixture = dict(row)
        fixture_date = fixture["match_date"].date() if isinstance(fixture["match_date"], datetime) else fixture["match_date"]
        last_match_date = max(last_match_date, fixture_date)
        lineups, suspended_ids = _match_lineups(
            conn, str(save["id"]), str(fixture["home_club_id"]), str(fixture["away_club_id"]),
            fixture_date, str(fixture.get("tournament_id") or ""), str(fixture.get("season") or save.get("season") or "")
        )
        home_players = lineups.get(str(fixture["home_club_id"]), [])
        away_players = lineups.get(str(fixture["away_club_id"]), [])
        home_overall = sum(float(player.get("effective_overall") or player["overall"]) for player in home_players) / len(home_players) if home_players else 60
        away_overall = sum(float(player.get("effective_overall") or player["overall"]) for player in away_players) / len(away_players) if away_players else 60
        seed = int(hashlib.sha256(f"{fixture['id']}:{fixture_date}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed ^ 0x5F27A11)
        result = simulate_score(
            fixture["home_rep"], fixture["away_rep"], home_overall, away_overall, seed
        )
        details = _record_match_detail(
            conn, save, fixture, result, lineups, suspended_ids, fixture_date, rng
        )
        conn.execute(
            """UPDATE fixtures SET status='completed',home_score=%s,away_score=%s,home_xg=%s,away_xg=%s,
                       home_possession=%s,away_possession=%s,home_shots=%s,away_shots=%s,
                       home_shots_on_target=%s,away_shots_on_target=%s,notes=coalesce(notes,'{}'::jsonb)||%s,
                       simulated_at=now()
               WHERE id=%s""",
            (
                result["home_score"], result["away_score"], result["home_xg"], result["away_xg"],
                result["home_possession"], result["away_possession"], result["home_shots"], result["away_shots"],
                result["home_shots_on_target"], result["away_shots_on_target"], Jsonb({"match": details}), fixture["id"],
            ),
        )
        fixture.update(result)
        update_table(conn, fixture)
        home_condition = "win" if result["home_score"] > result["away_score"] else "loss" if result["home_score"] < result["away_score"] else "draw"
        away_condition = "win" if result["away_score"] > result["home_score"] else "loss" if result["away_score"] < result["home_score"] else "draw"
        update_player_condition(conn, str(save["id"]), str(fixture["home_club_id"]), home_condition)
        update_player_condition(conn, str(save["id"]), str(fixture["away_club_id"]), away_condition)
        advance_position_training(conn, str(save["id"]), str(fixture["home_club_id"]))
        advance_position_training(conn, str(save["id"]), str(fixture["away_club_id"]))
        match_result = {
            "fixture_id": str(fixture["id"]),
            "home": fixture["home_name"],
            "away": fixture["away_name"],
            "home_score": result["home_score"],
            "away_score": result["away_score"],
            "match_date": fixture_date.isoformat(),
            "mvp": details.get("mvp"),
        }
        completed.append(match_result)
        if str(fixture["home_club_id"]) == managed_club_id or str(fixture["away_club_id"]) == managed_club_id:
            manager_results.append(match_result)

    if rows:
        conn.execute(
            """UPDATE game_states SET game_date=%s,simulation_cursor=%s,last_simulated_at=now(),
                      last_autosave_at=now(),updated_at=now() WHERE id=%s""",
            (last_match_date, last_match_date, save["id"]),
        )
    return completed, manager_results


@app.post("/api/game/advance")
def advance_game(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = require_save(conn, str(manager["id"]))
    next_round = conn.execute(
        """SELECT tournament_id,matchday,max(match_date::date) AS match_date
           FROM fixtures
           WHERE game_state_id=%s AND status='scheduled'
           GROUP BY tournament_id,matchday
           ORDER BY min(match_date),matchday
           LIMIT 1""",
        (save["id"],),
    ).fetchone()
    if not next_round:
        calendar_year_season = bool((save.get("game_settings") or {}).get("calendar_year_season"))
        current_year = int(str(save.get("season") or "2026/27")[:4])
        next_year = current_year + 1
        next_season = str(next_year) if calendar_year_season else f"{next_year}/{(next_year + 1) % 100:02d}"
        tournament_id = conn.execute(
            """SELECT tournament_id FROM club_tournaments
               WHERE game_state_id=%s AND season=%s
               ORDER BY tournament_id LIMIT 1""",
            (save["id"], save["season"]),
        ).fetchone()
        if not tournament_id:
            raise HTTPException(status_code=409, detail="Не удалось определить турнир для следующего сезона")
        clubs = conn.execute(
            "SELECT id,name,reputation FROM clubs WHERE game_state_id=%s ORDER BY name",
            (save["id"],),
        ).fetchall()
        conn.execute(
            """INSERT INTO club_tournaments (game_state_id,tournament_id,club_id,season)
               SELECT game_state_id,tournament_id,club_id,%s
               FROM club_tournaments WHERE game_state_id=%s AND season=%s
               ON CONFLICT (game_state_id,tournament_id,club_id,season) DO NOTHING""",
            (next_season, save["id"], save["season"]),
        )
        first_day = (
            date(next_year, 2, 1) if calendar_year_season and (save.get("game_settings") or {}).get("calendar_league_code") == "USA-MLS"
            else date(next_year, 1, 1) if calendar_year_season
            else date(next_year, 7, 1)
        )
        create_schedule(
            conn, str(save["id"]), str(tournament_id["tournament_id"]),
            [dict(club) for club in clubs], season=next_season, start_date=first_day,
        )
        conn.execute(
            """UPDATE game_states SET season=%s,game_date=%s,simulation_cursor=%s,
                      last_autosave_at=now(),updated_at=now() WHERE id=%s""",
            (next_season, first_day, first_day, save["id"]),
        )
        return {"ok": True, "new_season": next_season, "matches_simulated": 0, "results": [], "manager_result": None}

    match_date = next_round["match_date"]
    completed, manager_results = simulate_matchday(
        conn, save, match_date, int(next_round["matchday"]), str(next_round["tournament_id"])
    )
    return {
        "ok": True,
        "matchday": int(next_round["matchday"]),
        "matchday_date": match_date.isoformat(),
        "matches_simulated": len(completed),
        "results": manager_results,
        "manager_result": manager_results[0] if manager_results else None,
    }


@app.post("/api/game/advance-to-date")
def advance_game_to_date(
    target_date: date,
    manager: dict = Depends(manager_dep),
    conn: Connection = Depends(db_dep),
) -> dict:
    save = require_save(conn, str(manager["id"]))
    current_date = save["game_date"].date() if isinstance(save["game_date"], datetime) else save["game_date"]
    if target_date < current_date:
        raise HTTPException(status_code=409, detail="Нельзя перемотать карьеру назад")
    calendar_year_season = bool((save.get("game_settings") or {}).get("calendar_year_season"))
    season_start_year = int(str(save.get("season") or "2026/27")[:4])
    season_end = date(season_start_year, 12, 31) if calendar_year_season else date(season_start_year + 1, 6, 30)
    if target_date > season_end:
        raise HTTPException(status_code=422, detail="Выбери дату внутри текущего игрового сезона")
    rounds = conn.execute(
        """SELECT tournament_id,matchday,max(match_date::date) AS match_date,
                  min(match_date::date) AS first_match_date
           FROM fixtures
           WHERE game_state_id=%s AND status='scheduled'
           GROUP BY tournament_id,matchday
           HAVING min(match_date::date)<=%s
           ORDER BY min(match_date),matchday""",
        (save["id"], target_date),
    ).fetchall()
    matches_simulated = 0
    manager_results: list[dict] = []
    for row in rounds:
        completed, own_results = simulate_matchday(
            conn, save, row["match_date"], int(row["matchday"]), str(row["tournament_id"]),
            through_date=target_date
        )
        matches_simulated += len(completed)
        manager_results.extend(own_results)
    conn.execute(
        """UPDATE game_states SET game_date=%s,simulation_cursor=%s,
                  last_autosave_at=now(),updated_at=now() WHERE id=%s""",
        (target_date, target_date, save["id"]),
    )
    return {
        "ok": True,
        "game_date": target_date.isoformat(),
        "matchdays_simulated": len(rounds),
        "matches_simulated": matches_simulated,
        "results": manager_results,
        "manager_result": manager_results[-1] if manager_results else None,
    }

@app.get("/api/matches/{fixture_id}")
def match_details(
    fixture_id: str,
    manager: dict = Depends(manager_dep),
    conn: Connection = Depends(db_dep),
) -> dict:
    save = require_save(conn, str(manager["id"]))
    fixture_row = conn.execute(
        """SELECT f.*,t.name AS tournament_name,t.logo_url AS tournament_logo,
                  h.name AS home_name,h.logo_url AS home_logo,
                  a.name AS away_name,a.logo_url AS away_logo
           FROM fixtures f
           LEFT JOIN tournaments t ON t.id=f.tournament_id
           JOIN clubs h ON h.id=f.home_club_id
           JOIN clubs a ON a.id=f.away_club_id
           WHERE f.id=%s AND f.game_state_id=%s""",
        (fixture_id, save["id"]),
    ).fetchone()
    if not fixture_row:
        raise HTTPException(status_code=404, detail="Матч не найден в текущей карьере")
    fixture = dict(fixture_row)
    match_stats = (fixture.get("notes") or {}).get("match")
    if not isinstance(match_stats, dict):
        match_stats = None

    player_rows = conn.execute(
        """SELECT s.player_id,s.club_id,c.name AS club_name,p.name,p.position,
                  s.minutes_played,s.rating,s.goals,s.assists,s.shots,s.shots_on_target,
                  s.passes,s.accurate_passes,s.tackles,s.interceptions,s.key_passes,
                  s.yellow_cards,s.red_cards,s.saves,s.clean_sheet,s.is_mvp,s.is_estimate
           FROM fixture_player_stats s
           JOIN players p ON p.id=s.player_id
           JOIN clubs c ON c.id=s.club_id
           WHERE s.fixture_id=%s
           ORDER BY s.rating DESC,s.goals DESC,s.assists DESC,p.name""",
        (fixture_id,),
    ).fetchall()
    event_rows = conn.execute(
        """SELECT e.minute,e.added_time,e.event_type,e.detail,c.name AS club_name,
                  p.name AS player_name,a.name AS assist_name
           FROM match_events e
           LEFT JOIN clubs c ON c.id=e.club_id
           LEFT JOIN players p ON p.id=e.player_id
           LEFT JOIN players a ON a.id=e.assist_player_id
           WHERE e.fixture_id=%s
           ORDER BY e.minute,e.added_time,e.id""",
        (fixture_id,),
    ).fetchall()
    return serialise({
        "fixture": fixture,
        "stats": match_stats,
        "players": [dict(row) for row in player_rows],
        "events": [dict(row) for row in event_rows],
        "historical_estimate": bool(match_stats and match_stats.get("historical_estimate")),
        "stats_available": bool(player_rows),
    })


@app.get("/api/tournaments")
def tournaments(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> list:
    save = require_save(conn, str(manager["id"]))
    rows = conn.execute(
        """SELECT t.id,t.code,t.name,t.country,t.continent,t.tournament_type,t.tier,t.logo_url,
                  ct.season,
                  count(DISTINCT ct.club_id)::int AS teams,
                  count(DISTINCT f.id)::int AS fixtures,
                  count(DISTINCT f.id) FILTER (WHERE f.status='completed')::int AS played_fixtures
           FROM club_tournaments ct
           JOIN tournaments t ON t.id=ct.tournament_id
           LEFT JOIN fixtures f
             ON f.game_state_id=ct.game_state_id AND f.tournament_id=ct.tournament_id AND f.season=ct.season
           WHERE ct.game_state_id=%s AND ct.season=%s
           GROUP BY t.id,ct.season
           ORDER BY t.tier,t.name""",
        (save["id"], save["season"]),
    ).fetchall()
    return serialise([dict(row) for row in rows])


@app.get("/api/tournaments/{tournament_id}")
def tournament_details(
    tournament_id: str,
    manager: dict = Depends(manager_dep),
    conn: Connection = Depends(db_dep),
) -> dict:
    save = require_save(conn, str(manager["id"]))
    tournament = conn.execute(
        """SELECT t.id,t.code,t.name,t.country,t.continent,t.tournament_type,t.logo_url,
                  ct.season
           FROM tournaments t
           JOIN club_tournaments ct ON ct.tournament_id=t.id
           WHERE t.id=%s AND ct.game_state_id=%s AND ct.season=%s
           LIMIT 1""",
        (tournament_id, save["id"], save["season"]),
    ).fetchone()
    if not tournament:
        raise HTTPException(status_code=404, detail="Турнир не найден в текущем сезоне")

    standings_rows = conn.execute(
        """SELECT c.id AS club_id,c.name,c.logo_url,ct.played,ct.won,ct.drawn,ct.lost,
                  ct.goals_for,ct.goals_against,ct.goal_difference,ct.points
           FROM club_tournaments ct JOIN clubs c ON c.id=ct.club_id
           WHERE ct.game_state_id=%s AND ct.tournament_id=%s AND ct.season=%s
           ORDER BY ct.points DESC,coalesce(ct.goal_difference,0) DESC,ct.goals_for DESC,c.name""",
        (save["id"], tournament_id, save["season"]),
    ).fetchall()
    player_rows = conn.execute(
        """SELECT p.id AS player_id,p.name,p.position,p.nationality,p.nationality_flag,
                  c.name AS club_name,c.logo_url AS club_logo,
                  count(*)::int AS appearances,
                  round(avg(s.rating)::numeric,2)::float AS average_rating,
                  sum(s.goals)::int AS goals,sum(s.assists)::int AS assists,
                  (sum(s.goals)+sum(s.assists))::int AS goal_contributions,
                  count(*) FILTER (WHERE s.is_mvp)::int AS mvp,
                  sum(s.yellow_cards)::int AS yellow_cards,sum(s.red_cards)::int AS red_cards,
                  count(*) FILTER (WHERE s.clean_sheet)::int AS clean_sheets
           FROM fixture_player_stats s
           JOIN fixtures f ON f.id=s.fixture_id AND f.status='completed'
           JOIN players p ON p.id=s.player_id
           JOIN clubs c ON c.id=s.club_id
           WHERE s.game_state_id=%s AND s.tournament_id=%s AND f.season=%s
           GROUP BY p.id,p.name,p.position,c.name,c.logo_url
           ORDER BY average_rating DESC,goal_contributions DESC,goals DESC,p.name""",
        (save["id"], tournament_id, save["season"]),
    ).fetchall()
    team_rows = conn.execute(
        """SELECT c.id AS club_id,c.name,c.logo_url,
                  coalesce(sum(s.goals),0)::int AS goals,
                  round(avg(s.rating)::numeric,2)::float AS average_rating,
                  count(*) FILTER (WHERE s.is_mvp)::int AS mvp,
                  coalesce(sum(s.yellow_cards),0)::int AS yellow_cards,
                  coalesce(sum(s.red_cards),0)::int AS red_cards,
                  count(*) FILTER (WHERE s.clean_sheet)::int AS clean_sheets
           FROM fixture_player_stats s
           JOIN fixtures f ON f.id=s.fixture_id AND f.status='completed'
           JOIN clubs c ON c.id=s.club_id
           WHERE s.game_state_id=%s AND s.tournament_id=%s AND f.season=%s
           GROUP BY c.id,c.name,c.logo_url
           ORDER BY goals DESC,average_rating DESC,c.name""",
        (save["id"], tournament_id, save["season"]),
    ).fetchall()
    match_rows = conn.execute(
        """SELECT f.id,f.match_date,f.matchday,f.stage,f.status,f.home_score,f.away_score,
                  f.home_xg,f.away_xg,h.name AS home_name,h.logo_url AS home_logo,
                  a.name AS away_name,a.logo_url AS away_logo
           FROM fixtures f
           JOIN clubs h ON h.id=f.home_club_id
           JOIN clubs a ON a.id=f.away_club_id
           WHERE f.game_state_id=%s AND f.tournament_id=%s AND f.season=%s
           ORDER BY f.match_date,f.matchday,f.id
           LIMIT 700""",
        (save["id"],tournament_id,save["season"]),
    ).fetchall()
    totals = conn.execute(
        """SELECT count(*) FILTER (WHERE status='completed')::int AS played_matches,
                  count(*) FILTER (WHERE status='scheduled')::int AS scheduled_matches,
                  count(*)::int AS total_matches,
                  coalesce(sum(home_score+away_score) FILTER (WHERE status='completed'),0)::int AS goals
           FROM fixtures
           WHERE game_state_id=%s AND tournament_id=%s AND season=%s""",
        (save["id"], tournament_id, save["season"]),
    ).fetchone()
    return serialise({
        "tournament": dict(tournament),
        "standings": [dict(row) for row in standings_rows],
        "players": [
            {**dict(row), "nationality_flag": row["nationality_flag"] or flag_for_nationality(row["nationality"])}
            for row in player_rows
        ],
        "teams": [dict(row) for row in team_rows],
        "matches": [dict(row) for row in match_rows],
        "totals": dict(totals),
    })


@app.get("/api/standings")
def standings(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> list:
    save = require_save(conn, str(manager["id"]))
    rows = conn.execute(
        """SELECT c.name,c.logo_url,ct.played,ct.won,ct.drawn,ct.lost,ct.goals_for,ct.goals_against,
                  ct.goal_difference,ct.points
           FROM club_tournaments ct JOIN clubs c ON c.id=ct.club_id
           WHERE ct.game_state_id=%s AND ct.season=%s
           ORDER BY ct.points DESC,coalesce(ct.goal_difference,0) DESC,ct.goals_for DESC,c.name""",
        (save["id"], save["season"]),
    ).fetchall()
    return serialise([dict(row) for row in rows])


@app.get("/api/data-status")
def data_status(conn: Connection = Depends(db_dep)) -> dict:
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM sm27_club_pool) AS clubs,
                  (SELECT count(*) FROM world_player_catalog) AS players,
                  (SELECT count(*) FROM sm27_club_pool WHERE has_squad) AS clubs_with_squads,
                  (SELECT max(source_snapshot) FROM sm27_club_pool) AS snapshot,
                  (SELECT count(*) FROM fc27_player_catalog) AS fc27_catalog_players,
                  (SELECT count(*) FROM players WHERE fc27_player_id IS NOT NULL) AS career_players_with_fc27,
                  (SELECT status FROM fc27_import_state WHERE import_key='ratings') AS fc27_import_status"""
    ).fetchone()
    return serialise({"status": "ready" if counts["clubs"] >= 100 else "needs_import", **dict(counts)})
