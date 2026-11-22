from __future__ import annotations

import hashlib
import logging
import random
import re
import uuid
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
from app.engine import overall_from_market_value, potential_from_overall, round_robin, simulate_score
from app.schemas import CreateSaveIn, LoginIn, RegisterIn, TacticIn

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger("sm27")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url:
        with connection() as conn:
            migrate(conn)
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
POSITION_OPTIONS = {
    "DF": ("CB", "RB", "LB", "RWB", "LWB"),
    "MF": ("CM", "CDM", "CAM", "RM", "LM"),
    "FW": ("ST", "CF", "RW", "LW"),
    "GK": ("GK",),
}
SECONDARY_POSITIONS = {
    "GK": (), "RB": ("LB", "RWB"), "LB": ("RB", "LWB"),
    "CB": ("CDM",), "RWB": ("RB", "RM"), "LWB": ("LB", "LM"),
    "CDM": ("CM", "CB"), "CM": ("CDM", "CAM"),
    "CAM": ("CM", "CF"), "RM": ("RW", "CM"),
    "LM": ("LW", "CM"), "RW": ("RM", "ST"),
    "LW": ("LM", "ST"), "ST": ("CF", "LW"), "CF": ("ST", "CAM"),
}
NATIONALITY_FLAGS = {
    "argentina": "🇦🇷", "australia": "🇦🇺", "austria": "🇦🇹", "belgium": "🇧🇪",
    "brazil": "🇧🇷", "cameroon": "🇨🇲", "canada": "🇨🇦", "chile": "🇨🇱",
    "china": "🇨🇳", "colombia": "🇨🇴", "croatia": "🇭🇷", "czech republic": "🇨🇿",
    "denmark": "🇩🇰", "ecuador": "🇪🇨", "egypt": "🇪🇬", "england": "🏴",
    "finland": "🇫🇮", "france": "🇫🇷", "georgia": "🇬🇪", "germany": "🇩🇪",
    "ghana": "🇬🇭", "greece": "🇬🇷", "ireland": "🇮🇪", "italy": "🇮🇹",
    "ivory coast": "🇨🇮", "japan": "🇯🇵", "mexico": "🇲🇽", "morocco": "🇲🇦",
    "netherlands": "🇳🇱", "new zealand": "🇳🇿", "nigeria": "🇳🇬", "north macedonia": "🇲🇰",
    "norway": "🇳🇴", "poland": "🇵🇱", "portugal": "🇵🇹", "romania": "🇷🇴",
    "russia": "🇷🇺", "scotland": "🏴", "serbia": "🇷🇸", "slovakia": "🇸🇰",
    "slovenia": "🇸🇮", "south korea": "🇰🇷", "spain": "🇪🇸", "sweden": "🇸🇪",
    "switzerland": "🇨🇭", "turkey": "🇹🇷", "ukraine": "🇺🇦", "united states": "🇺🇸",
    "uruguay": "🇺🇾", "venezuela": "🇻🇪", "wales": "🏴", "algeria": "🇩🇿",
    "angola": "🇦🇴", "bosnia and herzegovina": "🇧🇦", "burkina faso": "🇧🇫",
    "cape verde": "🇨🇻", "congo": "🇨🇬", "democratic republic of the congo": "🇨🇩",
    "guinea": "🇬🇳", "iran": "🇮🇷", "israel": "🇮🇱", "jamaica": "🇯🇲",
    "kosovo": "🇽🇰", "mali": "🇲🇱", "montenegro": "🇲🇪", "senegal": "🇸🇳",
    "south africa": "🇿🇦", "togo": "🇹🇬", "tunisia": "🇹🇳", "uzbekistan": "🇺🇿",
}


def flag_for_nationality(value: str | None) -> str:
    key = (value or "").strip().casefold()
    if key in NATIONALITY_FLAGS:
        return NATIONALITY_FLAGS[key]
    try:
        import pycountry
        country = pycountry.countries.lookup(value or "")
        return "".join(chr(127397 + ord(char)) for char in country.alpha_2.upper())
    except (ImportError, LookupError, AttributeError):
        return "🏳️"


def normalise_player_position(position: str | None, source_id: str = "") -> str:
    value = (position or "").strip().upper()
    if value in POSITION_CODES:
        return value
    group = value if value in POSITION_OPTIONS else (
        "GK" if value in {"GOALKEEPER", "G"} else
        "DF" if value in {"DEFENDER", "DEFENCE", "D"} else
        "FW" if value in {"FORWARD", "ATTACKER", "STRIKER", "F"} else
        "MF"
    )
    options = POSITION_OPTIONS[group]
    seed = int(hashlib.sha1((source_id or value or "SM27").encode()).hexdigest()[:8], 16)
    return options[seed % len(options)]


def player_attributes(overall: int, position: str, source_id: str) -> dict[str, int]:
    seed = int(hashlib.sha1(source_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
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
    return {key: int(max(20, min(99, overall + offset + rng.randint(-5, 5)))) for key, offset in offsets.items()}


def estimated_market_value(overall: int, potential: int, age: int) -> int:
    age_factor = 1.22 if age <= 21 else 1.08 if age <= 24 else 1.0 if age <= 29 else max(0.25, 1 - (age - 29) * 0.07)
    potential_factor = 1 + max(0, potential - overall) * 0.012
    value = ((max(0, overall - 35) ** 2) * 12_000) * age_factor * potential_factor
    return int(round(max(25_000, value) / 10_000) * 10_000)


def estimated_weekly_wage(market_value: int) -> int:
    return int(max(250, min(1_500_000, round(max(market_value, 25_000) * 0.00154 / 100) * 100)))


def estimated_contract_end(age: int, source_id: str) -> date:
    seed = int(hashlib.sha1(source_id.encode()).hexdigest()[:8], 16)
    max_years = 2 if age >= 34 else 3 if age >= 30 else 5
    years = 1 + seed % max_years
    return date(2027 + years, 6, 30)


def require_save(conn: Connection, manager_id: str) -> dict:
    row = conn.execute(
        """SELECT gs.id, gs.game_date, gs.season, gs.save_name, gs.managed_club_id,
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
            pool_row["club_name"],
            (pool_row["club_name"] or "SM27")[:20],
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


def ensure_demo_roster(conn: Connection, game_state_id: str, club_id: str, club_name: str, reputation: int) -> None:
    existing = conn.execute(
        "SELECT count(*) AS n FROM players WHERE game_state_id=%s AND club_id=%s",
        (game_state_id, club_id),
    ).fetchone()["n"]
    # Every playable club needs a complete minimum squad. These are always labelled as generated.
    positions = ["GK", "GK", "RB", "CB", "CB", "LB", "CB", "RB", "CDM", "CM", "CM", "CAM", "CM", "CM", "RW", "LW", "ST", "CF"]
    if existing >= len(positions):
        return
    for index, position in enumerate(positions[existing:], start=existing + 1):
        source_id = f"generated:{club_id}:{index}"
        age = 18 + (index % 12)
        overall = max(40, min(82, reputation - 8 + (index % 7)))
        potential = min(92, overall + 4 + (index % 7))
        market_value = estimated_market_value(overall, potential, age)
        conn.execute(
            """INSERT INTO players (
                   game_state_id,club_id,external_id,name,age,position,secondary_positions,
                   overall,potential,market_value,weekly_wage,contract_end,attributes,
                   original_data,source_name,profile_source,form,morale,sharpness
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                         'SM27 generated roster','SM27 estimate — generated academy player',50,70,85)""",
            (
                game_state_id, club_id, source_id, f"Игрок академии {index:02d}", age, position,
                list(SECONDARY_POSITIONS.get(position, ())), overall, potential,
                market_value, estimated_weekly_wage(market_value), estimated_contract_end(age, source_id),
                Jsonb(player_attributes(overall, position, source_id)),
                Jsonb({"generated": True, "note": "Fictional game placeholder, not a real player"}),
            ),
        )


def position_penalty(primary: str, secondary: list[str], target: str) -> int:
    if primary == target or target in secondary:
        return 0
    if primary == "GK" or target == "GK":
        return -40
    close = {
        "RB": {"LB": -2, "RWB": -2, "LWB": -5, "CB": -3, "RM": -5, "CDM": -7},
        "LB": {"RB": -2, "LWB": -2, "RWB": -5, "CB": -3, "LM": -5, "CDM": -7},
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
        "RWB": {"RB": -2, "RM": -3, "LB": -5, "CB": -5},
        "LWB": {"LB": -2, "LM": -3, "RB": -5, "CB": -5},
    }
    return close.get(primary, {}).get(target, -7)


def best_lineup(player_rows: list[dict], formation: str = "4-3-3") -> tuple[list[str], list[str], list[str]]:
    roles_by_formation = {
        "4-3-3": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CAM", "LW", "ST", "RW"],
        "4-2-3-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "LW", "CAM", "RW", "ST"],
        "4-4-2": ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CM", "RM", "ST", "ST"],
        "3-5-2": ["GK", "CB", "CB", "CB", "LWB", "CDM", "CM", "CM", "RWB", "ST", "ST"],
        "3-4-3": ["GK", "CB", "CB", "CB", "LM", "CM", "CM", "RM", "LW", "ST", "RW"],
        "5-3-2": ["GK", "LB", "CB", "CB", "CB", "RB", "CM", "CM", "CDM", "ST", "ST"],
        "4-1-4-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "LM", "CM", "CM", "RM", "ST"],
        "4-2-2-2": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "CAM", "CAM", "ST", "ST"],
        "4-1-2-1-2": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CM", "CAM", "ST", "ST"],
        "4-3-2-1": ["GK", "LB", "CB", "CB", "RB", "CM", "CDM", "CM", "CAM", "CAM", "ST"],
        "5-4-1": ["GK", "LB", "CB", "CB", "CB", "RB", "LM", "CM", "CM", "RM", "ST"],
        "3-4-1-2": ["GK", "CB", "CB", "CB", "LM", "CM", "CM", "RM", "CAM", "ST", "ST"],
        "4-5-1": ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CDM", "CM", "RM", "ST"],
        "4-2-4": ["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "LW", "ST", "ST", "RW"],
    }
    available = [dict(row) for row in player_rows]
    selected: list[str] = []
    selected_roles: list[str] = []
    roles = roles_by_formation.get(formation, roles_by_formation["4-3-3"])
    for role in roles:
        candidates = []
        for player in available:
            primary = player.get("position") or "CM"
            secondary = list(player.get("secondary_positions") or [])
            penalty = position_penalty(primary, secondary, role)
            score = int(player.get("overall") or 0) + penalty
            candidates.append((score, str(player["id"]), player))
        if not candidates:
            break
        _, player_id, chosen = max(candidates, key=lambda item: (item[0], item[1]))
        selected.append(player_id)
        selected_roles.append(role)
        available = [player for player in available if str(player["id"]) != player_id]
    bench_rows = sorted(available, key=lambda row: int(row.get("overall") or 0), reverse=True)[:7]
    bench = [str(row["id"]) for row in bench_rows]
    return selected, bench, selected_roles


def create_schedule(conn: Connection, game_state_id: str, tournament_id: str, teams: list[dict]) -> None:
    ids = [str(team["id"]) for team in teams]
    rounds = round_robin(ids)
    start = date(2026, 8, 15)
    for round_index, fixtures in enumerate(rounds):
        match_date = datetime.combine(start + timedelta(days=7 * round_index), datetime.min.time()).replace(
            tzinfo=timezone.utc
        ) + timedelta(hours=14)
        for home_id, away_id in fixtures:
            conn.execute(
                """INSERT INTO fixtures (game_state_id, tournament_id, season, match_date,
                           matchday, home_club_id, away_club_id, status)
                   VALUES (%s,%s,'2026/27',%s,%s,%s,%s,'scheduled')
                   ON CONFLICT (game_state_id,tournament_id,season,match_date,home_club_id,away_club_id)
                   DO NOTHING""",
                (game_state_id, tournament_id, match_date, round_index + 1, home_id, away_id),
            )



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


@app.get("/api/health")
def health() -> dict:
    if not settings.database_url:
        return {"status": "degraded", "database": "not_configured", "app": "SM27"}
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "database": "connected", "app": "SM27"}
    except Exception as exc:  # pragma: no cover - platform health response
        return {"status": "error", "database": "unavailable", "detail": type(exc).__name__}


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
    result = []
    for row in rows:
        player = dict(row)
        if not player.get("nationality_flag"):
            player["nationality_flag"] = flag_for_nationality(player.get("nationality"))
        if not player.get("secondary_positions"):
            player["secondary_positions"] = list(SECONDARY_POSITIONS.get(player.get("position"), ()))
        result.append(player)
    return serialise(result)


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
        f"""SELECT source_id, club_name, country, country_iso, league_name, league_code,
                   league_level, division, city, stadium, stadium_capacity, colors_hex,
                   logo_url, logo_license, has_squad, squad_count, sort_rank, fifa_stars, team_strength
            FROM sm27_club_pool WHERE {where}
            ORDER BY sort_rank, club_name LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    ).fetchall()
    total = conn.execute(f"SELECT count(*) AS n FROM sm27_club_pool WHERE {where}", params).fetchone()["n"]
    return {"items": serialise([dict(row) for row in rows]), "total": total, "limit": limit, "offset": offset}


@app.post("/api/saves")
def create_save(body: CreateSaveIn, manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    active = conn.execute(
        "SELECT id FROM game_states WHERE manager_id=%s AND status='active' LIMIT 1", (manager["id"],)
    ).fetchone()
    if active:
        raise HTTPException(status_code=409, detail="У вас уже есть активное сохранение. Завершите его перед созданием нового.")
    selected = conn.execute("SELECT * FROM sm27_club_pool WHERE source_id=%s", (body.club_source_id,)).fetchone()
    if not selected:
        raise HTTPException(status_code=404, detail="Клуб не найден в игровом каталоге")
    selected = dict(selected)
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
    tournament_code = f"SM27-{league_code}"[:64]
    tournament = conn.execute(
        """INSERT INTO tournaments (code,name,country,continent,tournament_type,tier,format,active)
           VALUES (%s,%s,%s,%s,'league',%s,%s,true)
           ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name, country=EXCLUDED.country,
             continent=EXCLUDED.continent, tier=EXCLUDED.tier, format=EXCLUDED.format
           RETURNING id""",
        (tournament_code, selected.get("league_name") or "SM27 League", selected.get("country"),
         selected.get("continent") or "UEFA", selected.get("league_level") or 1,
         Jsonb({"points_win": 3, "points_draw": 1, "season": "2026/27"})),
    ).fetchone()
    game_state = conn.execute(
        """INSERT INTO game_states (manager_id,save_slot,game_date,season,difficulty,status,save_name,game_settings)
           VALUES (%s,(SELECT coalesce(max(save_slot),0)+1 FROM game_states WHERE manager_id=%s),DATE '2026-07-01','2026/27','normal','active',%s,%s) RETURNING id""",
        (manager["id"], manager["id"], body.save_name.strip(), Jsonb({"source_snapshot": selected["source_snapshot"].isoformat()})),
    ).fetchone()
    game_state_id = str(game_state["id"])
    team_records: list[dict] = []
    for pool_row in teams:
        club_id = make_club(conn, game_state_id, pool_row)
        team_records.append({"id": club_id, "source_id": pool_row["source_id"], "name": pool_row["club_name"], "reputation": int(pool_row.get("team_strength") or round(float(pool_row.get("fifa_stars") or 2.5) * 20))})
        conn.execute(
            """INSERT INTO club_tournaments (game_state_id,tournament_id,club_id,season)
               VALUES (%s,%s,%s,'2026/27') ON CONFLICT DO NOTHING""",
            (game_state_id, tournament["id"], club_id),
        )
        player_rows = conn.execute(
            """SELECT source_id,name,date_of_birth,nationality,position,market_value_eur,
                      market_value_as_of,source_url,raw_data
               FROM world_player_catalog WHERE club_source_id=%s
               ORDER BY market_value_eur DESC, name LIMIT 30""",
            (pool_row["source_id"],),
        ).fetchall()
        for player in player_rows:
            dob = player["date_of_birth"]
            age = max(16, min(43, int((date(2026, 7, 1) - dob).days / 365.2425))) if dob else 24
            source_id = str(player["source_id"])
            position = normalise_player_position(player["position"], source_id)
            secondary = list(SECONDARY_POSITIONS.get(position, ()))
            overall = overall_from_market_value(
                int(player["market_value_eur"] or 0), age, int(team_records[-1]["reputation"]),
                int(hashlib.sha1(source_id.encode()).hexdigest()[:8], 16)
            )
            potential = potential_from_overall(
                overall, age, int(hashlib.sha1(source_id.encode()).hexdigest()[:8], 16)
            )
            sourced_market_value = int(player["market_value_eur"] or 0)
            market_value = sourced_market_value or estimated_market_value(overall, potential, age)
            profile_source = (
                f"Transfermarkt snapshot ({player['market_value_as_of'].isoformat()})"
                if sourced_market_value and player["market_value_as_of"]
                else "SM27 estimate — no verified market value in source snapshot"
            )
            raw = dict(player["raw_data"] or {})
            raw.update({
                "market_value_source": "Transfermarkt" if sourced_market_value else "SM27 estimate",
                "market_value_as_of": player["market_value_as_of"].isoformat() if player["market_value_as_of"] else None,
                "game_rating_type": "SM27 estimate",
                "contract_source": "SM27 estimate",
                "wage_source": "SM27 estimate",
                "generated": False,
            })
            contract_end = estimated_contract_end(age, source_id)
            weekly_wage = estimated_weekly_wage(market_value)
            conn.execute(
                """INSERT INTO players (
                       game_state_id,club_id,external_id,name,nationality,birth_date,age,position,
                       secondary_positions,overall,potential,market_value,weekly_wage,contract_end,
                       attributes,original_data,source_name,source_url,data_verified_at,
                       form,morale,sharpness,nationality_flag,profile_source
                   ) VALUES (
                       %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                   )
                   ON CONFLICT (game_state_id,external_id) DO NOTHING""",
                (
                    game_state_id, club_id, source_id, player["name"], player["nationality"], dob, age, position,
                    secondary, overall, potential, market_value, weekly_wage, contract_end,
                    Jsonb(player_attributes(overall, position, source_id)),
                    Jsonb(raw), "OpenFootballBase / Transfermarkt", player["source_url"],
                    player["market_value_as_of"], 50, 70, 85,
                    flag_for_nationality(player["nationality"]), profile_source,
                ),
            )
    for team in team_records:
        ensure_demo_roster(conn, game_state_id, team["id"], team["name"], team["reputation"])
    selected_game_club = next(row["id"] for row in team_records if row["source_id"] == selected["source_id"])
    conn.execute("UPDATE game_states SET managed_club_id=%s WHERE id=%s", (selected_game_club, game_state_id))
    create_schedule(conn, game_state_id, str(tournament["id"]), team_records)
    return {"ok": True, "save_id": game_state_id, "club": selected["club_name"], "league": selected.get("league_name"), "teams": len(team_records)}



@app.post("/api/saves/restart")
def restart_save(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    """Delete all career-scoped data for this manager so a new save starts from the immutable baseline."""
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
        """SELECT f.id,f.match_date,f.matchday,f.status,h.name AS home_name,a.name AS away_name,
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
           WHERE ct.game_state_id=%s AND ct.tournament_id=(
             SELECT tournament_id FROM club_tournaments WHERE game_state_id=%s AND club_id=%s LIMIT 1)
           ORDER BY ct.points DESC, coalesce(ct.goal_difference,0) DESC, ct.goals_for DESC, c.name LIMIT 30""",
        (game_state_id, game_state_id, club_id),
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
        """SELECT id,name,nationality,nationality_flag,birth_date,age,position,secondary_positions,
                  overall,GREATEST(1,LEAST(99,overall + ROUND(
                    (form-50)*0.06 + (morale-70)*0.04 + (sharpness-85)*0.04 - fatigue*0.08
                  )::int)) AS dynamic_overall,
                  potential,market_value,weekly_wage,contract_end,fatigue,form,morale,sharpness,
                  injury_type,injury_until,attributes,original_data,profile_source,source_url
           FROM players
           WHERE game_state_id=%s AND club_id=%s
           ORDER BY CASE position WHEN 'GK' THEN 0 WHEN 'CB' THEN 1 WHEN 'RB' THEN 1 WHEN 'LB' THEN 1
                     WHEN 'CDM' THEN 2 WHEN 'CM' THEN 2 WHEN 'CAM' THEN 2 ELSE 3 END,
                    overall DESC, name""",
        (save["id"], save["managed_club_id"]),
    ).fetchall()
    return serialise([dict(row) for row in rows])


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
def fixtures(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep), limit: int = 40) -> list:
    save = require_save(conn, str(manager["id"]))
    limit = max(1, min(limit, 400))
    rows = conn.execute(
        """SELECT f.id,f.match_date,f.matchday,f.status,f.home_score,f.away_score,
                  h.name AS home_name,a.name AS away_name,h.logo_url AS home_logo,a.logo_url AS away_logo
           FROM fixtures f JOIN clubs h ON h.id=f.home_club_id JOIN clubs a ON a.id=f.away_club_id
           WHERE f.game_state_id=%s ORDER BY f.match_date LIMIT %s""",
        (save["id"], limit),
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


def add_goal_events(conn: Connection, fixture: dict, result: dict) -> None:
    for club_id, count in ((fixture["home_club_id"], result["home_score"]), (fixture["away_club_id"], result["away_score"])):
        players = conn.execute(
            "SELECT id FROM players WHERE game_state_id=%s AND club_id=%s ORDER BY overall DESC LIMIT 16",
            (fixture["game_state_id"], club_id),
        ).fetchall()
        ids = [str(row["id"]) for row in players]
        for _ in range(count):
            minute = random.randint(3, 90)
            scorer = random.choice(ids) if ids else None
            conn.execute(
                "INSERT INTO match_events (fixture_id,minute,event_type,club_id,player_id,detail) VALUES (%s,%s,'goal',%s,%s,%s)",
                (fixture["id"], minute, club_id, scorer, Jsonb({"simulated": True})),
            )


@app.post("/api/game/advance")
def advance_game(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> dict:
    save = require_save(conn, str(manager["id"]))
    next_date = conn.execute(
        "SELECT match_date::date AS match_date FROM fixtures WHERE game_state_id=%s AND status='scheduled' ORDER BY match_date LIMIT 1",
        (save["id"],),
    ).fetchone()
    if not next_date:
        raise HTTPException(status_code=409, detail="Все матчи сезона сыграны")
    match_date = next_date["match_date"]
    # One round is normally one week apart; recover players before the next matchday.
    conn.execute(
        """UPDATE players SET fatigue=GREATEST(0,fatigue-20),
                  sharpness=LEAST(100,sharpness+4),updated_at=now()
           WHERE game_state_id=%s""",
        (save["id"],),
    )
    rows = conn.execute(
        """SELECT f.*,h.name AS home_name,a.name AS away_name,h.reputation AS home_rep,a.reputation AS away_rep
           FROM fixtures f JOIN clubs h ON h.id=f.home_club_id JOIN clubs a ON a.id=f.away_club_id
           WHERE f.game_state_id=%s AND f.status='scheduled' AND f.match_date::date=%s ORDER BY f.id""",
        (save["id"], match_date),
    ).fetchall()
    completed = []
    for row in rows:
        fixture = dict(row)
        averages = conn.execute(
            """WITH candidates AS (
                 SELECT p.club_id,
                        GREATEST(1,LEAST(99,p.overall + ROUND(
                          (p.form-50)*0.06 + (p.morale-70)*0.04
                          + (p.sharpness-85)*0.04 - p.fatigue*0.08
                        )::int
                        + CASE
                            WHEN cardinality(coalesce(t.starting_xi,ARRAY[]::uuid[]))=11
                                 AND p.id=ANY(t.starting_xi)
                            THEN CASE
                              WHEN role.target_position IS NULL OR p.position=role.target_position
                                   OR role.target_position=ANY(p.secondary_positions) THEN 0
                              WHEN p.position='GK' OR role.target_position='GK' THEN -40
                              WHEN p.position IN ('RB','LB') AND role.target_position IN ('RB','LB','RWB','LWB','CB') THEN
                                CASE WHEN p.position<>role.target_position THEN -2 ELSE -3 END
                              WHEN p.position='CB' AND role.target_position IN ('RB','LB','CDM') THEN -3
                              WHEN p.position IN ('RWB','LWB') AND role.target_position IN ('RB','LB','RM','LM','CB') THEN -3
                              WHEN p.position IN ('CDM','CM','CAM') AND role.target_position IN ('CDM','CM','CAM','RM','LM') THEN -3
                              WHEN p.position IN ('RW','LW') AND role.target_position IN ('RW','LW','RM','LM','ST','CF') THEN -3
                              WHEN p.position IN ('ST','CF') AND role.target_position IN ('ST','CF','CAM','RW','LW') THEN -3
                              ELSE -7
                            END
                            ELSE 0
                          END
                        )) AS effective_overall,
                        (cardinality(coalesce(t.starting_xi,ARRAY[]::uuid[]))=11) AS has_custom_lineup,
                        (cardinality(coalesce(t.starting_xi,ARRAY[]::uuid[]))=11 AND p.id=ANY(t.starting_xi)) AS in_custom_lineup,
                        row_number() OVER (
                          PARTITION BY p.club_id
                          ORDER BY p.overall + (p.form-50)*0.06 + (p.morale-70)*0.04
                                   + (p.sharpness-85)*0.04 - p.fatigue*0.08 DESC
                        ) AS squad_rank
                 FROM players p
                 LEFT JOIN tactics t
                   ON t.game_state_id=p.game_state_id AND t.club_id=p.club_id
                 LEFT JOIN LATERAL (
                   SELECT item->>'role' AS target_position
                   FROM jsonb_array_elements(coalesce(t.style->'slot_roles','[]'::jsonb)) item
                   WHERE item->>'player_id'=p.id::text
                   LIMIT 1
                 ) role ON true
                 WHERE p.game_state_id=%s AND p.club_id IN (%s,%s)
             )
             SELECT club_id,coalesce(avg(effective_overall),60)::float AS avg_overall
             FROM candidates
             WHERE (has_custom_lineup AND in_custom_lineup)
                OR (NOT has_custom_lineup AND squad_rank<=11)
             GROUP BY club_id""",
            (save["id"], fixture["home_club_id"], fixture["away_club_id"]),
        ).fetchall()
        rating = {str(item["club_id"]): item["avg_overall"] for item in averages}
        seed = int(hashlib.sha256(f"{fixture['id']}:{match_date}".encode()).hexdigest()[:8], 16)
        result = simulate_score(
            fixture["home_rep"], fixture["away_rep"],
            rating.get(str(fixture["home_club_id"]), 60), rating.get(str(fixture["away_club_id"]), 60), seed,
        )
        conn.execute(
            """UPDATE fixtures SET status='completed',home_score=%s,away_score=%s,home_xg=%s,away_xg=%s,
                       home_possession=%s,away_possession=%s,home_shots=%s,away_shots=%s,
                       home_shots_on_target=%s,away_shots_on_target=%s,simulated_at=now()
               WHERE id=%s""",
            (result["home_score"], result["away_score"], result["home_xg"], result["away_xg"],
             result["home_possession"], result["away_possession"], result["home_shots"], result["away_shots"],
             result["home_shots_on_target"], result["away_shots_on_target"], fixture["id"]),
        )
        fixture.update(result)
        update_table(conn, fixture)
        home_condition = "win" if result["home_score"] > result["away_score"] else "loss" if result["home_score"] < result["away_score"] else "draw"
        away_condition = "win" if result["away_score"] > result["home_score"] else "loss" if result["away_score"] < result["home_score"] else "draw"
        update_player_condition(conn, str(save["id"]), str(fixture["home_club_id"]), home_condition)
        update_player_condition(conn, str(save["id"]), str(fixture["away_club_id"]), away_condition)
        add_goal_events(conn, fixture, result)
        completed.append({"home": fixture["home_name"], "away": fixture["away_name"], "home_score": result["home_score"], "away_score": result["away_score"]})
    conn.execute(
        "UPDATE game_states SET game_date=%s,simulation_cursor=%s,last_simulated_at=now(),last_autosave_at=now(),updated_at=now() WHERE id=%s",
        (match_date, match_date, save["id"]),
    )
    return {"ok": True, "matchday_date": match_date.isoformat(), "matches_simulated": len(completed), "results": completed}


@app.get("/api/standings")
def standings(manager: dict = Depends(manager_dep), conn: Connection = Depends(db_dep)) -> list:
    save = require_save(conn, str(manager["id"]))
    rows = conn.execute(
        """SELECT c.name,c.logo_url,ct.played,ct.won,ct.drawn,ct.lost,ct.goals_for,ct.goals_against,
                  ct.goal_difference,ct.points
           FROM club_tournaments ct JOIN clubs c ON c.id=ct.club_id
           WHERE ct.game_state_id=%s ORDER BY ct.points DESC,coalesce(ct.goal_difference,0) DESC,ct.goals_for DESC,c.name""",
        (save["id"],),
    ).fetchall()
    return serialise([dict(row) for row in rows])


@app.get("/api/data-status")
def data_status(conn: Connection = Depends(db_dep)) -> dict:
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM sm27_club_pool) AS clubs,
                  (SELECT count(*) FROM world_player_catalog) AS players,
                  (SELECT count(*) FROM sm27_club_pool WHERE has_squad) AS clubs_with_squads,
                  (SELECT max(source_snapshot) FROM sm27_club_pool) AS snapshot"""
    ).fetchone()
    return serialise({"status": "ready" if counts["clubs"] >= 100 else "needs_import", **dict(counts)})
