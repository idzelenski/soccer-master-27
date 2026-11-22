from __future__ import annotations

import csv
import io
import json
import logging
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

LOGGER = logging.getLogger("sm27.player_sources")
EA_FC27_CSV_URL = (
    "https://raw.githubusercontent.com/LakshmiKanth11/EA_FC_ANALYSIS/main/"
    "EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"
)
SOFASCORE_API = "https://www.sofascore.com/api/v1"
EA_SNAPSHOT_DATE = "2026-09-12"
LATEST_CURATED_DATE = "2026-11-18"

# Confirmed against the FC 27 squad update dated 18 Nov 2026 (update 8).
# The detailed attributes not listed here are kept from the EA public ratings snapshot.
CURATED_FC27 = {
    "cristiano ronaldo": {
        "overall": 84, "potential": 94, "position": "ST",
        "weekly_wage": 74000, "contract_end": "2027-06-30",
        "attributes": {"PAC": 67, "SHO": 88, "PAS": 75, "DRI": 77, "DEF": 33, "PHY": 75,
                       "acceleration": 65, "sprint_speed": 68},
        "source": "EA Sports FC 27 squad update 2026-11-18 (FAFIFA)"
    },
    "inigo martinez": {
        "overall": 83, "potential": 85, "position": "CB",
        "weekly_wage": 280000, "contract_end": "2030-06-30",
        "attributes": {"PAC": 70, "SHO": 57, "PAS": 72, "DRI": 66, "DEF": 82, "PHY": 83,
                       "stamina": 74, "crossing": 57, "reactions": 80, "standing_tackle": 83,
                       "acceleration": 67, "aggression": 86, "agility": 63, "ball_control": 75,
                       "defending_awareness": 81, "interceptions": 83, "sliding_tackle": 82,
                       "strength": 85, "long_passing": 81, "short_passing": 81, "shot_power": 80,
                       "heading_accuracy": 82, "long_shots": 73, "penalties": 40, "sprint_speed": 73},
        "source": "EA Sports FC 27 squad update 2026-11-18 (FAFIFA)"
    },
}

EA_ATTRIBUTE_COLUMNS = {
    "PAC": "pace", "SHO": "shooting", "PAS": "passing",
    "DRI": "dribbling", "DEF": "defending", "PHY": "physicality",
    "crossing": "attacking_crossing", "finishing": "attacking_finishing",
    "heading_accuracy": "attacking_heading_accuracy", "short_passing": "attacking_short_passing",
    "volleys": "attacking_volleys", "dribbling": "skill_dribbling", "curve": "skill_curve",
    "fk_accuracy": "skill_fk_accuracy", "long_passing": "skill_long_passing",
    "ball_control": "skill_ball_control", "acceleration": "movement_acceleration",
    "sprint_speed": "movement_sprint_speed", "agility": "movement_agility",
    "reactions": "movement_reactions", "balance": "movement_balance",
    "shot_power": "power_shot_power", "jumping": "power_jumping", "stamina": "power_stamina",
    "strength": "power_strength", "long_shots": "power_long_shots",
    "aggression": "mentality_aggression", "interceptions": "mentality_interceptions",
    "attacking_position": "mentality_positioning", "vision": "mentality_vision",
    "penalties": "mentality_penalties", "composure": "mentality_composure",
    "defending_awareness": "defending_awareness", "standing_tackle": "defending_standing_tackle",
    "sliding_tackle": "defending_sliding_tackle", "DIV": "goalkeeping_diving",
    "HAN": "goalkeeping_handling", "KIC": "goalkeeping_kicking",
    "POS": "goalkeeping_positioning", "REF": "goalkeeping_reflexes",
}

def normalize_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def _http_json(url: str, timeout: int = 8) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SoccerMaster27/1.0)",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.sofascore.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"External source returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def _http_bytes(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SoccerMaster27/1.0)", "Accept": "text/csv,*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"EA data source returned HTTP {response.status}")
        data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise RuntimeError("EA player snapshot is unexpectedly large")
        return data

def _birth_key(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]

def _parse_int(value: Any) -> int | None:
    try:
        if value in (None, "", "-"):
            return None
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None

def _ea_row_to_payload(row: dict[str, str]) -> dict[str, Any]:
    attributes: dict[str, int] = {}
    for target, column in EA_ATTRIBUTE_COLUMNS.items():
        value = _parse_int(row.get(column))
        if value is not None:
            attributes[target] = max(1, min(99, value))
    return {
        "ea_player_id": _parse_int(row.get("player_id")),
        "overall": _parse_int(row.get("overall_rating")),
        "position": (row.get("position") or "").upper().strip(),
        # Secondary positions are intentionally not imported. They must be trained in SM27.
        "alternate_positions": [],
        "attributes": attributes,
        "preferred_foot": row.get("preferred_foot"),
        "skill_moves": _parse_int(row.get("skill_moves")),
        "weak_foot": _parse_int(row.get("weak_foot")),
        "height_cm": _parse_int(row.get("height_cm")),
        "weight_kg": _parse_int(row.get("weight_kg")),
        "playstyles": [item.strip() for item in (row.get("playstyles") or "").split(",") if item.strip()],
        "snapshot_date": row.get("snapshot_date") or EA_SNAPSHOT_DATE,
        "source": "EA Sports FC 27 public ratings API snapshot 2026-09-12",
    }

def _load_ea_squad_rows(squad: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    aliases: dict[str, tuple[str, str]] = {}
    for player in squad:
        key = (normalize_name(player.get("name")), _birth_key(player.get("birth_date")))
        if key[0] and key[1]:
            targets[key] = player
            aliases[key[0]] = key
    raw = _http_bytes(EA_FC27_CSV_URL)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    result: dict[str, dict[str, Any]] = {}
    for row in reader:
        if row.get("gender") and row.get("gender") != "Men's Football":
            continue
        common = normalize_name(row.get("common_name"))
        standard = normalize_name(" ".join(x for x in (row.get("first_name"), row.get("last_name")) if x))
        dob = str(row.get("birthdate") or "")[:10]
        for candidate in (common, standard):
            key = aliases.get(candidate)
            if key and key[1] == dob and key in targets:
                result[str(targets[key]["id"])] = _ea_row_to_payload(row)
                break
    for player in squad:
        name_key = normalize_name(player.get("name"))
        curated = CURATED_FC27.get(name_key)
        if curated:
            existing = result.get(str(player["id"]), {})
            payload = {**existing, **curated}
            attrs = dict(existing.get("attributes") or {})
            attrs.update(curated.get("attributes") or {})
            payload["attributes"] = attrs
            payload["alternate_positions"] = []
            result[str(player["id"])] = payload
    return result

def _entity(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("entity") if isinstance(item.get("entity"), dict) else item

def _find_sofascore_team(club_name: str) -> int | None:
    query = urllib.parse.urlencode({"q": club_name})
    data = _http_json(f"{SOFASCORE_API}/search/all?{query}")
    items = data.get("results") or data.get("teams") or []
    target = normalize_name(club_name)
    candidates = []
    for item in items:
        if item.get("type") not in (None, "team"):
            continue
        team = _entity(item)
        name = normalize_name(team.get("name"))
        if not name:
            continue
        score = 3 if name == target else 2 if name in target or target in name else 0
        if score:
            candidates.append((score, int(team.get("id") or 0)))
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates and candidates[0][0] >= 2 else None

def _market_value(player: dict[str, Any]) -> int | None:
    raw = player.get("proposedMarketValueRaw") or player.get("marketValueRaw")
    currency = player.get("marketValueCurrency")
    if isinstance(raw, dict):
        currency = raw.get("currency") or currency
        value = _parse_int(raw.get("value"))
    else:
        value = _parse_int(raw or player.get("proposedMarketValue"))
    if value and (currency or "EUR").upper() == "EUR" and value >= 1000:
        return value
    return None

def _sofa_team_roster(club_name: str) -> list[dict[str, Any]]:
    team_id = _find_sofascore_team(club_name)
    if not team_id:
        return []
    data = _http_json(f"{SOFASCORE_API}/team/{team_id}/players")
    entries = data.get("players") or data.get("teamPlayers") or []
    output = []
    for entry in entries:
        player = entry.get("player") if isinstance(entry.get("player"), dict) else entry
        if player.get("id"):
            output.append(player)
    return output

def _sofa_season_stats(player_id: int) -> dict[str, Any]:
    try:
        data = _http_json(f"{SOFASCORE_API}/player/{player_id}/statistics/seasons")
        seasons = data.get("uniqueTournamentSeasons") or data.get("seasons") or []
        for entry in seasons:
            season = entry.get("season") if isinstance(entry.get("season"), dict) else entry
            tournament = entry.get("uniqueTournament") or entry.get("tournament") or {}
            season_id, tournament_id = season.get("id"), tournament.get("id")
            if not season_id or not tournament_id:
                continue
            stats = _http_json(
                f"{SOFASCORE_API}/player/{player_id}/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall"
            ).get("statistics") or {}
            if stats:
                stats["season_name"] = season.get("name")
                stats["tournament_name"] = tournament.get("name")
                return stats
    except Exception as exc:
        LOGGER.info("Sofascore statistics unavailable for player %s: %s", player_id, exc)
    return {}

def _clamp(value: float, low: int = 35, high: int = 95) -> int:
    return max(low, min(high, int(round(value))))

def _percent_score(value: Any, low: float, high: float) -> int:
    number = None
    try:
        number = float(value)
    except (TypeError, ValueError):
        pass
    if number is None:
        return 60
    return _clamp(45 + 50 * (number - low) / max(high - low, 0.001))

def _estimate_from_sofascore(position: str, age: int, stats: dict[str, Any]) -> tuple[int, dict[str, int]]:
    rating = stats.get("rating") or stats.get("avgRating") or stats.get("averageRating")
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        rating = 6.7
    appearances = max(1, _parse_int(stats.get("appearances")) or _parse_int(stats.get("matches")) or 1)
    minutes = max(1, _parse_int(stats.get("minutesPlayed")) or appearances * 70)
    per90 = lambda key: float(stats.get(key) or 0) * 90 / minutes
    goals = per90("goals")
    assists = per90("assists")
    shots_target = per90("shotsOnTarget")
    key_passes = per90("keyPasses")
    dribbles = per90("successfulDribbles")
    tackles = per90("tackles")
    interceptions = per90("interceptions")
    aerial = stats.get("aerialDuelsWonPercentage")
    duels = stats.get("duelsWonPercentage")
    accurate_passes = stats.get("accuratePassesPercentage")
    base = _clamp(50 + (rating - 6.0) * 17 + min(5, appearances / 8), 42, 88)
    pac = _clamp(68 - max(0, age - 25) * 0.8 + (7 if position in ("LW","RW","ST","RB","LB") else 0))
    sho = _clamp(48 + goals * 18 + shots_target * 8 + (9 if position in ("ST","CF","LW","RW") else 0))
    pas = _clamp(47 + assists * 20 + key_passes * 8 + (_percent_score(accurate_passes,55,95)-60)*0.45)
    dri = _clamp(48 + dribbles * 14 + (_percent_score(duels,35,70)-60)*0.35)
    deff = _clamp(45 + tackles * 10 + interceptions * 8 + (10 if position in ("CB","LB","RB","CDM","GK") else 0))
    phy = _clamp(50 + (aerial if isinstance(aerial,(int,float)) else 50)*0.35 + (duels if isinstance(duels,(int,float)) else 50)*0.25)
    if position == "GK":
        attrs={"DIV":base,"HAN":base,"KIC":_percent_score(accurate_passes,50,95),"REF":_clamp(base+2),"SPE":_clamp(base-4),"POS":_clamp(base+1)}
    else:
        attrs={"PAC":pac,"SHO":sho,"PAS":pas,"DRI":dri,"DEF":deff,"PHY":phy}
    overall = _clamp(base,45,88)
    return overall, attrs

def _sofascore_stats_by_player_id(player: dict[str, Any]) -> dict[str, Any]:
    value = _market_value(player)
    return {"player_id": int(player["id"]), "market_value_eur": value}

def sync_managed_player_data(conn, game_state_id: str, club_id: str) -> dict[str, int]:
    rows = conn.execute(
        """SELECT p.id,p.external_id,p.name,p.birth_date,p.age,p.position,p.overall,p.potential,
                  p.market_value,p.weekly_wage,p.nationality,c.name AS club_name
           FROM players p JOIN clubs c ON c.id=p.club_id
           WHERE p.game_state_id=%s AND p.club_id=%s ORDER BY p.name""",
        (game_state_id, club_id),
    ).fetchall()
    squad = [dict(row) for row in rows]
    if not squad:
        return {"fc27_matched": 0, "sofascore_matched": 0, "unmatched": 0}
    fc_data = _load_ea_squad_rows(squad)
    try:
        sofa_roster = _sofa_team_roster(squad[0]["club_name"])
    except Exception as exc:
        LOGGER.warning("Sofascore team lookup failed for %s: %s", squad[0]["club_name"], exc)
        sofa_roster = []
    sofa_by_name = {normalize_name(item.get("name")): item for item in sofa_roster if item.get("name")}
    fc_matched = sofa_matched = unmatched = 0
    current_date = datetime.now(timezone.utc).date()
    for player in squad:
        player_id = str(player["id"])
        fc = fc_data.get(player_id)
        sofa_player = sofa_by_name.get(normalize_name(player["name"]))
        sofa = _sofascore_stats_by_player_id(sofa_player) if sofa_player else {}
        if sofa_player and sofa.get("market_value_eur") is None:
            try:
                detail = _http_json(f"{SOFASCORE_API}/player/{int(sofa_player['id'])}").get("player") or {}
                sofa.update(_sofascore_stats_by_player_id(detail))
            except Exception as exc:
                LOGGER.info("Sofascore profile unavailable for %s: %s", player["name"], exc)
        stats: dict[str, Any] = {}
        if sofa_player and not fc:
            try:
                stats = _sofa_season_stats(int(sofa_player["id"]))
            except Exception:
                stats = {}
        if fc:
            fc.setdefault("source", "EA Sports FC 27 public ratings API snapshot 2026-09-12")
            fc["alternate_positions"] = []
            fc.setdefault("potential", None)
            fc.setdefault("weekly_wage", None)
            fc.setdefault("contract_end", None)
            if fc.get("potential") is None and fc.get("weekly_wage") is None:
                fc.setdefault("source_snapshot", EA_SNAPSHOT_DATE)
            fc_matched += 1
        if sofa.get("market_value_eur"):
            sofa.update({"market_value_as_of": current_date.isoformat()})
            sofa_matched += 1
        if not fc and stats:
            overall, attrs = _estimate_from_sofascore(player.get("position") or "CM", int(player.get("age") or 25), stats)
            fc = {
                "overall": overall, "potential": overall + (8 if player["age"] <= 22 else 3 if player["age"] <= 27 else 0),
                "position": player.get("position") or "CM", "alternate_positions": [], "attributes": attrs,
                "source": "SM27 estimate from Sofascore season statistics",
            }
        if not fc and not sofa:
            unmatched += 1
            continue
        raw = conn.execute(
            "SELECT raw_data FROM world_player_catalog WHERE source_id=%s",
            (player["external_id"],),
        ).fetchone()
        raw_data = dict((raw or {}).get("raw_data") or {})
        if fc:
            raw_data["fc27"] = fc
        if sofa:
            raw_data["sofascore"] = sofa
        conn.execute(
            "UPDATE world_player_catalog SET raw_data=%s,updated_at=now() WHERE source_id=%s",
            (Jsonb(raw_data), player["external_id"]),
        )
        overall = int(fc.get("overall") or player["overall"]) if fc else player["overall"]
        potential = int(fc.get("potential") or (overall + 3 if player["age"] <= 27 else overall)) if fc else player["potential"]
        position = fc.get("position") or player["position"] if fc else player["position"]
        attrs = fc.get("attributes") if fc else None
        weekly_wage = int(fc.get("weekly_wage") or player["weekly_wage"] or 0) if fc else player["weekly_wage"]
        contract_end = fc.get("contract_end") if fc else None
        market_value = sofa.get("market_value_eur") if sofa.get("market_value_eur") else 0
        rating_source = fc.get("source") if fc else player.get("rating_source") or "SM27 estimate"
        market_source = "Sofascore" if market_value else "SM27 estimate — waiting for SofaScore"
        wage_source = "EA FC 27" if fc and fc.get("weekly_wage") else "SM27 estimate"
        conn.execute(
            """UPDATE players SET overall=%s,potential=%s,position=%s,secondary_positions=ARRAY[]::text[],
                      attributes=coalesce(%s,attributes),weekly_wage=CASE WHEN %s>0 THEN %s ELSE weekly_wage END,
                      contract_end=coalesce(%s::date,contract_end),
                      market_value=CASE WHEN %s>0 THEN %s ELSE market_value END,
                      market_value_source=CASE WHEN %s>0 THEN 'Sofascore' ELSE market_value_source END,
                      market_value_as_of=CASE WHEN %s>0 THEN %s::date ELSE market_value_as_of END,
                      rating_source=%s,wage_source=%s,sofascore_player_id=%s,
                      original_data=coalesce(original_data,'{}'::jsonb)||%s,
                      profile_source=%s,source_sync_attempted_at=now(),updated_at=now()
               WHERE id=%s""",
            (overall,potential,position,Jsonb(attrs) if attrs else None,weekly_wage,weekly_wage,
             contract_end,market_value,market_value,market_value,current_date if market_value else None,
             rating_source,wage_source,sofa.get("player_id"),Jsonb({"fc27":fc,"sofascore":sofa}) if fc or sofa else Jsonb({}),
             rating_source,player_id),
        )
    conn.execute(
        "UPDATE players SET source_sync_attempted_at=now() WHERE game_state_id=%s AND club_id=%s",
        (game_state_id,club_id),
    )
    return {"fc27_matched":fc_matched,"sofascore_matched":sofa_matched,"unmatched":unmatched}
