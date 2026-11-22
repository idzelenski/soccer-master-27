from __future__ import annotations

import concurrent.futures
from difflib import SequenceMatcher
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row
import pycountry
from psycopg.types.json import Jsonb

ENDPOINT = "https://drop-api.ea.com/rating/ea-sports-fc"
PAGE_SIZE = 100
CONCURRENCY = 5
RETRIES = 3
FC27_HEADERS = {
    "accept": "application/json",
    "drop-referrer": "https://www.ea.com/games/ea-sports-fc/ratings",
    "user-agent": "SoccerMaster27-rating-import/1.0",
}
FC27_SNAPSHOT = date(2026, 9, 10)
POSITION_CODES = {"GK","RB","CB","LB","RWB","LWB","CDM","CM","CAM","RM","LM","RW","LW","ST","CF"}
WAGE_OVERRIDES = {"cristianoronaldo": 53_000, "inigomartinez": 245_000}
SPECIAL_COUNTRIES = {
    "england":"ENG","scotland":"SCO","wales":"WAL",
    "northern ireland":"NIR","kosovo":"XKX",
}
FIFA_TO_ISO3 = {
    "POR":"PRT","NED":"NLD","GER":"DEU","SUI":"CHE","RSA":"ZAF",
    "CRC":"CRI","URU":"URY","CRO":"HRV","GRE":"GRC","DEN":"DNK",
    "KSA":"SAU","UAE":"ARE",
}
POSITION_GROUPS = {
    "GK": {"GK"},
    "DF": {"DF","CB","RB","LB","RWB","LWB"},
    "MF": {"MF","CDM","CM","CAM","RM","LM"},
    "FW": {"FW","ST","CF","RW","LW"},
}
CLUB_ALIASES = {
    "paris saint germain": {"paris sg","psg"},
    "atalanta bc": {"atalanta","bergamo calcio"},
    "bergamo calcio": {"atalanta","atalanta bc"},
    "inter milan": {"inter","internazionale","lombardia fc"},
    "lombardia fc": {"inter","inter milan","internazionale"},
    "ac milan": {"milan","milan fc"},
    "milan fc": {"ac milan","milan"},
    "fc barcelona": {"barcelona"},
    "fc bayern munich": {"bayern","bayern munich"},
    "tottenham hotspur": {"tottenham","spurs"},
    "manchester united": {"man utd","man united"},
    "manchester city": {"man city"},
    "atletico madrid": {"atletico de madrid","atletico"},
    "athletic bilbao": {"athletic club","athletic club bilbao"},
}


def normalise_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def alpha3(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        return ""
    if key.casefold() in SPECIAL_COUNTRIES:
        return SPECIAL_COUNTRIES[key.casefold()]
    upper = key.upper()
    if len(upper) == 3:
        return FIFA_TO_ISO3.get(upper, upper)
    try:
        return pycountry.countries.lookup(key).alpha_3
    except LookupError:
        return ""


def label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("name") or "")
    return str(value or "")


def stat_value(stats: dict[str, Any], key: str) -> int | None:
    raw = stats.get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    try:
        return int(round(float(raw))) if raw is not None else None
    except (TypeError, ValueError):
        return None


def item_to_record(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        ea_id = int(item["id"])
        overall = int(item.get("overallRating") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if (item.get("gender") or {}).get("id") == 1:
        return None
    first_name = str(item.get("firstName") or "")
    last_name = str(item.get("lastName") or "")
    name = str(item.get("commonName") or f"{first_name} {last_name}").strip()
    if not name or overall <= 0:
        return None
    position = str((item.get("position") or {}).get("shortLabel") or "").upper()
    if position not in POSITION_CODES:
        return None
    nationality = label(item.get("nationality"))
    stats = item.get("stats") or {}
    attributes = {}
    for source, target in (("pac","PAC"),("sho","SHO"),("pas","PAS"),("dri","DRI"),("def","DEF"),("phy","PHY")):
        value = stat_value(stats, source)
        if value is not None:
            attributes[target] = max(20, min(99, value))
    alternate = [
        str((value or {}).get("shortLabel") or "").upper()
        for value in (item.get("alternatePositions") or [])
        if (value or {}).get("shortLabel")
    ]
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii","ignore").decode().lower()).strip("-")
    return {
        "ea_player_id": ea_id,
        "display_name": name,
        "name_key": normalise_name(name),
        "first_name": first_name,
        "last_name": last_name,
        "position": position,
        "alternate_positions": alternate,
        "nationality": nationality,
        "nationality_code": alpha3(nationality),
        "club_name": label(item.get("team")),
        "league_name": str(item.get("leagueName") or ""),
        "overall": overall,
        "potential": None,
        "attributes": attributes,
        "source_url": f"https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/{slug}/{ea_id}",
        "source_snapshot": FC27_SNAPSHOT,
        "raw_data": {
            "preferred_foot": item.get("preferredFoot"),
            "weak_foot": item.get("weakFootAbility"),
            "skill_moves": item.get("skillMoves"),
            "gender": "M",
            "rating_source": "EA SPORTS FC 27 public ratings API",
        },
    }


def page_url(offset: int, cache_key: str = "fc27") -> str:
    query = urllib.parse.urlencode({"locale":"en","limit":PAGE_SIZE,"offset":offset,"_e":cache_key})
    return f"{ENDPOINT}?{query}"


def fetch_page(offset: int, with_header: bool = True) -> dict[str, Any]:
    headers = dict(FC27_HEADERS) if with_header else {"accept":"application/json","user-agent":FC27_HEADERS["user-agent"]}
    url = page_url(offset, "fc27" if with_header else "default")
    last_error: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload.get("items"), list):
                raise ValueError("EA response has no items array")
            return payload
        except Exception as error:
            last_error = error
            if attempt < RETRIES:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"EA ratings API offset {offset} failed: {last_error}")


def fetch_all_players() -> list[dict[str, Any]]:
    print("Requesting FC 27 data from the official EA ratings endpoint")
    first = fetch_page(0, True)
    older = None
    try:
        older = fetch_page(0, False)
    except Exception as error:
        print(f"EA default-version comparison unavailable: {error}")
    if older and older.get("items") and older.get("totalItems") == first.get("totalItems"):
        old_page = json.dumps(older["items"][:PAGE_SIZE], sort_keys=True, ensure_ascii=False)
        fc27_page = json.dumps(first["items"][:PAGE_SIZE], sort_keys=True, ensure_ascii=False)
        if old_page == fc27_page:
            raise RuntimeError("EA returned an identical first page with and without the FC 27 referrer header; refusing a possible FC 26 import")
    total = int(first.get("totalItems") or len(first["items"]))
    if total < 10_000:
        raise RuntimeError(f"Unexpectedly small FC 27 database ({total}); refusing import")
    offsets = list(range(PAGE_SIZE, total, PAGE_SIZE))
    items = list(first["items"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for start in range(0, len(offsets), CONCURRENCY):
            batch = offsets[start:start + CONCURRENCY]
            for result in executor.map(fetch_page, batch):
                items.extend(result["items"])
            print(f"Fetched {min(total,len(items))}/{total} records")
    unique: dict[int, dict[str, Any]] = {}
    for item in items:
        record = item_to_record(item)
        if record:
            unique.setdefault(record["ea_player_id"], record)
    records = list(unique.values())
    if len(records) < 8_000:
        raise RuntimeError(f"Only {len(records)} usable men's players received; refusing partial import")
    print(f"Prepared {len(records)} unique men's players")
    return records


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fc27_player_catalog (
            ea_player_id BIGINT PRIMARY KEY, display_name TEXT NOT NULL, name_key TEXT NOT NULL,
            first_name TEXT, last_name TEXT, position TEXT,
            alternate_positions TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
            nationality TEXT, nationality_code TEXT, club_name TEXT, league_name TEXT,
            overall SMALLINT NOT NULL, potential SMALLINT,
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb, source_url TEXT,
            source_snapshot DATE NOT NULL DEFAULT DATE '2026-09-10',
            raw_data JSONB NOT NULL DEFAULT '{}'::jsonb, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS fc27_player_id BIGINT")
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_target TEXT")
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_progress SMALLINT NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_source TEXT NOT NULL DEFAULT 'SM27 estimate'")
    conn.execute("ALTER TABLE world_player_catalog ADD COLUMN IF NOT EXISTS fc27_player_id BIGINT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fc27_player_name_key ON fc27_player_catalog(name_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fc27_player_nationality ON fc27_player_catalog(nationality_code,name_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_players_fc27_id ON players(fc27_player_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_world_player_fc27_id ON world_player_catalog(fc27_player_id)")


def import_catalog(conn: psycopg.Connection, records: list[dict[str, Any]]) -> None:
    query = """
        INSERT INTO fc27_player_catalog (
            ea_player_id,display_name,name_key,first_name,last_name,position,alternate_positions,
            nationality,nationality_code,club_name,league_name,overall,potential,attributes,
            source_url,source_snapshot,raw_data,updated_at
        ) VALUES (
            %(ea_player_id)s,%(display_name)s,%(name_key)s,%(first_name)s,%(last_name)s,
            %(position)s,%(alternate_positions)s,%(nationality)s,%(nationality_code)s,
            %(club_name)s,%(league_name)s,%(overall)s,%(potential)s,%(attributes)s,
            %(source_url)s,%(source_snapshot)s,%(raw_data)s,now()
        )
        ON CONFLICT (ea_player_id) DO UPDATE SET
            display_name=EXCLUDED.display_name,name_key=EXCLUDED.name_key,
            first_name=EXCLUDED.first_name,last_name=EXCLUDED.last_name,
            position=EXCLUDED.position,alternate_positions=EXCLUDED.alternate_positions,
            nationality=EXCLUDED.nationality,nationality_code=EXCLUDED.nationality_code,
            club_name=EXCLUDED.club_name,league_name=EXCLUDED.league_name,
            overall=EXCLUDED.overall,attributes=EXCLUDED.attributes,
            source_url=EXCLUDED.source_url,source_snapshot=EXCLUDED.source_snapshot,
            raw_data=EXCLUDED.raw_data,updated_at=now()
    """
    prepared = []
    for row in records:
        item = dict(row)
        item["attributes"] = Jsonb(item["attributes"])
        item["raw_data"] = Jsonb(item["raw_data"])
        prepared.append(item)
    with conn.cursor() as cursor:
        cursor.executemany(query, prepared)
    print(f"Upserted {len(prepared)} FC 27 ratings")


def match_candidates(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        first_name = record.get("first_name") or ""
        last_name = record.get("last_name") or ""
        first_surname = last_name.split()[0] if last_name else ""
        keys = {
            record.get("name_key") or "",
            normalise_name(first_name + " " + last_name),
            normalise_name(first_name + " " + first_surname),
        }
        # EA sometimes stores a common display name, e.g. "Benjamin White",
        # while the club roster uses the accepted short form "Ben White".
        if normalise_name(first_name + " " + first_surname) == "benjaminwhite":
            keys.add("benwhite")
        for key in keys:
            if key:
                candidates = index.setdefault(key, [])
                if not any(existing["ea_player_id"] == record["ea_player_id"] for existing in candidates):
                    candidates.append(record)
    return index


def position_group(position):
    code = (position or "").upper()
    for group, codes in POSITION_GROUPS.items():
        if code in codes:
            return group
    return ""


def club_match_score(left, right):
    left_key = normalise_name(left)
    right_key = normalise_name(right)
    if not left_key or not right_key:
        return 0
    if left_key == right_key:
        return 5
    if min(len(left_key), len(right_key)) >= 5 and (left_key.startswith(right_key) or right_key.startswith(left_key)):
        return 3
    for canonical, aliases in CLUB_ALIASES.items():
        variants = {normalise_name(canonical), *(normalise_name(alias) for alias in aliases)}
        if left_key in variants and right_key in variants:
            return 5
    similarity = SequenceMatcher(None, left_key, right_key).ratio()
    if similarity >= 0.90:
        return 4
    if similarity >= 0.82:
        return 2
    return 0


def choose_match(name, nationality, club_name, position, index):
    candidates = index.get(normalise_name(name), [])
    if not candidates:
        return None
    nation = alpha3(nationality)
    source_group = position_group(position)
    ranked = []
    for candidate in candidates:
        score = 0
        candidate_nation = candidate["nationality_code"]
        if nation and candidate_nation:
            if nation != candidate_nation:
                continue
            score += 10
        candidate_group = position_group(candidate["position"])
        if source_group and candidate_group:
            if source_group != candidate_group:
                continue
            score += 3
        score += club_match_score(club_name, candidate["club_name"])
        if (position or "").upper() == candidate["position"]:
            score += 1
        ranked.append((score, candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]["overall"]), reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        if ranked[0][1]["overall"] - ranked[1][1]["overall"] < 3:
            return None
    return ranked[0][1]


def update_world_player_matches(conn: psycopg.Connection, index) -> int:
    rows = conn.execute("""
        SELECT wp.source_id,wp.name,wp.nationality,wp.position,wc.name AS club_name
        FROM world_player_catalog wp
        LEFT JOIN world_club_catalog wc ON wc.source_id=wp.club_source_id
    """).fetchall()
    updates = []
    for row in rows:
        match = choose_match(row["name"],row["nationality"],row["club_name"],row["position"],index)
        if match:
            updates.append((match["ea_player_id"],row["source_id"]))
    with conn.cursor() as cursor:
        cursor.executemany("UPDATE world_player_catalog SET fc27_player_id=%s WHERE source_id=%s",updates)
    print(f"Matched {len(updates)} source catalog players to EA FC 27")
    return len(updates)


def fallback_attributes(overall: int, position: str) -> dict[str, int]:
    rating = max(35,min(90,int(overall)))
    if position == "GK":
        offsets={"DIV":1,"HAN":0,"KIC":-3,"REF":4,"SPE":-2,"POS":2}
    else:
        group="DF" if position in {"CB","RB","LB","RWB","LWB"} else "FW" if position in {"ST","CF","RW","LW"} else "MF"
        offsets={
            "PAC":3 if group=="FW" else -1 if group=="DF" else 1,
            "SHO":6 if group=="FW" else -7 if group=="DF" else -1,
            "PAS":4 if group=="MF" else 0 if group=="DF" else -3,
            "DRI":5 if group=="FW" else 2 if group=="MF" else -4,
            "DEF":7 if group=="DF" else 0 if group=="MF" else -12,
            "PHY":4 if group=="DF" else 1 if group=="FW" else -1,
        }
    return {key:max(20,min(99,rating+offset)) for key,offset in offsets.items()}


def estimated_weekly_wage(overall: int, age: int, reputation: int, name: str) -> int:
    key=normalise_name(name)
    for alias, wage in WAGE_OVERRIDES.items():
        if key.startswith(alias):
            return wage
    base=600*math.exp((max(35,min(95,overall))-60)*0.21)
    if age<=22: age_factor=0.55
    elif age<=25: age_factor=0.75
    elif age<=29: age_factor=1.0
    elif age<=34: age_factor=1.20
    elif age<=37: age_factor=1.45
    elif age<=40: age_factor=0.90
    else: age_factor=0.25
    club_factor=0.70+max(10,min(100,reputation))*0.0175
    return int(max(250,min(1_500_000,round(base*age_factor*club_factor/100)*100)))


def update_career_players(conn: psycopg.Connection, records: list[dict[str, Any]]) -> tuple[int,int]:
    index=match_candidates(records)
    update_world_player_matches(conn,index)
    rows=conn.execute("""
        SELECT p.id,p.name,p.nationality,p.age,p.position,p.market_value,p.market_value_source,
               p.potential,p.original_data,p.fc27_player_id,c.reputation,c.name AS club_name
        FROM players p JOIN clubs c ON c.id=p.club_id
        WHERE p.original_data->>'generated' IS DISTINCT FROM 'true'
    """).fetchall()
    record_by_id={row["ea_player_id"]:row for row in records}
    updates=[]
    matched=fallback=0
    for row in rows:
        match=record_by_id.get(row["fc27_player_id"]) if row["fc27_player_id"] else None
        if not match:
            match=choose_match(row["name"],row["nationality"],row["club_name"],row["position"],index)
        age=int(row["age"] or 24)
        reputation=int(row["reputation"] or 50)
        seed=int(hashlib.sha1(str(row["id"]).encode()).hexdigest()[:8],16)
        if match:
            matched+=1
            overall=int(match["overall"])
            position=match["position"]
            attributes=dict(match["attributes"] or {}) or fallback_attributes(overall,position)
            fc_id=match["ea_player_id"]
            profile_source=f"EA SPORTS FC 27 official ratings database · {FC27_SNAPSHOT.strftime('%d.%m.%Y')}"
            market_source=row["market_value_source"] or "not_available"
            if market_source == "SofaScore":
                market_value=int(row["market_value"] or 0)
            else:
                market_value=0
                market_source="not_available"
            potential=max(overall,int(row["potential"] or overall))
        else:
            fallback+=1
            market_source=row["market_value_source"] or "not_available"
            market_value=int(row["market_value"] or 0) if market_source == "SofaScore" else 0
            if market_source != "SofaScore":
                market_source="not_available"
            if market_value>0:
                score=60+15*math.log10(max(market_value,25_000)/1_000_000)
                age_adjust=5 if age<=21 else 3 if age<=24 else 0 if age<=29 else -min(12,(age-29)*0.75)
                overall=max(35,min(90,round(score+age_adjust)))
            else:
                overall=max(35,min(84,round(42+reputation*0.29+(3 if age<=24 else 0))))
            position=row["position"] if row["position"] in POSITION_CODES else (
                "GK" if row["position"] in {"GK","G"} else "CB" if row["position"]=="DF"
                else "ST" if row["position"]=="FW" else "CM"
            )
            attributes=fallback_attributes(overall,position)
            fc_id=None
            profile_source="SM27 model estimate · no EA FC 27 player match"
            potential=max(overall,int(row["potential"] or overall))
        wage=estimated_weekly_wage(overall,age,reputation,row["name"])
        original=dict(row["original_data"] or {})
        original.update({
            "rating_source":"EA FC 27 official ratings API" if match else "SM27 model estimate",
            "rating_snapshot":FC27_SNAPSHOT.isoformat() if match else None,
            "wage_source":"FC 27 Career Mode squad data" if any(normalise_name(row["name"]).startswith(alias) for alias in WAGE_OVERRIDES) else "SM27 wage model",
        })
        updates.append((
            fc_id,position,overall,potential,market_value,market_source,wage,
            Jsonb(attributes),Jsonb(original),profile_source,row["id"],
        ))
    with conn.cursor() as cursor:
        cursor.executemany("""
            UPDATE players SET fc27_player_id=%s,position=%s,overall=%s,potential=%s,
                market_value=%s,market_value_source=%s,weekly_wage=%s,attributes=%s,
                original_data=%s,profile_source=%s,updated_at=now()
            WHERE id=%s
        """,updates)
    print(f"Updated career player rows: {matched} FC 27 matches, {fallback} SM27 estimates")
    return matched,fallback


def main(database_url: str | None = None) -> None:
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    records=fetch_all_players()
    with psycopg.connect(database_url,connect_timeout=20,row_factory=dict_row) as conn:
        ensure_schema(conn)
        import_catalog(conn,records)
        matched,fallback=update_career_players(conn,records)
        conn.commit()
    print(f"FC 27 import complete. matched={matched}, estimated={fallback}, total_catalog={len(records)}")


if __name__ == "__main__":
    main()
