from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import duckdb

from app.config import settings
from app.data_policy import is_reusable_license
from app.db import connection, migrate

REPOSITORY = "florentfougeres/OpenFootballBase-Data"
SEASON_LABEL = os.getenv("SM27_DATA_SEASON", "2026/27")
TM_CSV_URL = "https://huggingface.co/datasets/minmaxxxer/transfermarkt-player-market-values-2026-11/resolve/main/transfermarkt_player_market_values_2026_11.csv"


def request_for(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": "SoccerMaster27/0.1 (data import; contact via repository issues)", "Accept": "*/*"},
    )


def http_get(url: str, timeout: int = 90) -> bytes:
    with urllib.request.urlopen(request_for(url), timeout=timeout) as response:
        return response.read()


def download_with_sha256(url: str, target: Path, timeout: int = 180) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(request_for(url), timeout=timeout) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def latest_release() -> dict:
    url = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
    release = json.loads(http_get(url).decode("utf-8"))
    published = release.get("published_at", "")
    asset = next((item for item in release.get("assets", []) if item.get("name") == "openfootballbase-data.tar.gz"), None)
    if not asset:
        raise RuntimeError("Latest OpenFootballBase release has no data archive")
    if asset.get("size", 0) > 150_000_000:
        raise RuntimeError("Source archive exceeds the 150 MB safety limit")
    return {"tag": release["tag_name"], "published_at": published, "asset": asset}


def safe_relative_path(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"Unsafe path in source manifest: {value}")
    return Path(*pure.parts)


def extract_required_files(archive: Path, target: Path, relative_files: list[str]) -> dict[str, Path]:
    wanted = {str(safe_relative_path(item)).replace("\\", "/"): item for item in relative_files}
    extracted: dict[str, Path] = {}
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        manifest_member = next((m for m in members if PurePosixPath(m.name).name == "manifest.json"), None)
        if not manifest_member:
            raise RuntimeError("manifest.json not found in OpenFootballBase archive")
        prefix = str(PurePosixPath(manifest_member.name).parent)
        prefix = "" if prefix == "." else prefix.rstrip("/") + "/"
        manifest_stream = tar.extractfile(manifest_member)
        if manifest_stream is None:
            raise RuntimeError("Cannot read source manifest")
        manifest = json.loads(manifest_stream.read().decode("utf-8"))
        target.mkdir(parents=True, exist_ok=True)
        required_names = {prefix + rel for rel in wanted}
        for member in members:
            if member.name == manifest_member.name or member.name in required_names:
                if not member.isfile():
                    continue
                rel_name = member.name[len(prefix):] if prefix and member.name.startswith(prefix) else member.name
                rel = safe_relative_path(rel_name)
                output = (target / rel).resolve()
                if target.resolve() not in output.parents:
                    raise RuntimeError("Archive path traversal rejected")
                output.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    continue
                with output.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                if rel_name == "manifest.json":
                    extracted["manifest.json"] = output
                else:
                    extracted[rel_name] = output
    return extracted


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def continent_for_iso(country_iso: str | None) -> str:
    code = (country_iso or "").upper()
    africa = set("DZ AO BJ BW BF BI CV CM CF TD KM CG CD CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW".split())
    uefa = set("AD AL AM AT AZ BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GE GR HR HU IE IL IS IT KZ LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SK SM TR UA XK".split())
    asia = set("AF BH BD BT BN KH CN IN ID IR IQ JP JO KW KG LA LB MY MV MN MM NP KP OM PK PS PH QA SA SG KR LK SY TW TJ TM AE UZ VN YE".split())
    north_america = set("AG BS BB BZ CA CR CU DM DO SV GD GT HT HN JM MX NI PA KN LC VC TT US".split())
    south_america = set("AR BO BR CL CO EC GY PY PE SR UY VE".split())
    oceania = set("AU FJ KI MH FM NR NZ PW PG WS SB TO TV VU".split())
    if code in uefa:
        return "UEFA"
    if code in africa:
        return "CAF"
    if code in asia:
        return "AFC"
    if code in north_america:
        return "CONCACAF"
    if code in south_america:
        return "CONMEBOL"
    if code in oceania:
        return "OFC"
    return "UEFA"


def normalise_name(value: str | None) -> str:
    value = (value or "").casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def fetch_market_values() -> dict[tuple[str, str], dict]:
    try:
        payload = http_get(TM_CSV_URL, timeout=45).decode("utf-8-sig")
    except Exception as exc:
        print(f"[WARN] Transfermarkt snapshot not available; market values remain empty: {exc}")
        return {}
    values: dict[tuple[str, str], dict] = {}
    for row in csv.DictReader(io.StringIO(payload)):
        club_id = str(row.get("club_id") or "").strip()
        name = normalise_name(row.get("name"))
        if not club_id or not name:
            continue
        try:
            market_value = int(float(row.get("market_value_eur") or 0))
        except (TypeError, ValueError):
            market_value = 0
        values[(club_id, name)] = {
            "market_value_eur": market_value,
            "market_value_date": row.get("market_value_date") or None,
            "transfermarkt_player_id": row.get("player_id"),
            "transfermarkt_url": row.get("url"),
            "market_value_source": "Transfermarkt snapshot, 2026-11-19, CC BY 4.0 dataset",
        }
    print(f"[INFO] Loaded {len(values)} Transfermarkt market-value records")
    return values


def records(result: Any) -> list[dict]:
    columns = [item[0] for item in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def quote_sql_path(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def main() -> None:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required. Copy .env.example to .env and set it.")

    release = latest_release()
    tag = release["tag"]
    asset = release["asset"]
    snapshot = date.fromisoformat(release["published_at"][:10])
    print(f"[INFO] Source release: {tag} ({snapshot.isoformat()}); target clubs={settings.club_target}")

    with tempfile.TemporaryDirectory(prefix="sm27-import-") as temp:
        root = Path(temp)
        archive = root / "openfootballbase-data.tar.gz"
        digest = download_with_sha256(asset["browser_download_url"], archive, timeout=180)
        expected = (asset.get("digest") or "").removeprefix("sha256:")
        if expected and digest != expected:
            raise RuntimeError("OpenFootballBase archive SHA-256 verification failed")

        # Read manifest once from archive, then extract only six source files used by SM27.
        with tarfile.open(archive, "r:gz") as tar:
            manifest_member = next((m for m in tar.getmembers() if PurePosixPath(m.name).name == "manifest.json"), None)
            if manifest_member is None:
                raise RuntimeError("OpenFootballBase archive has no manifest.json")
            stream = tar.extractfile(manifest_member)
            manifest = json.loads(stream.read().decode("utf-8")) if stream else {}
        season = manifest.get("seasons", {}).get(SEASON_LABEL)
        if not season:
            open_season = next((value for value in manifest.get("seasons", {}).values() if value.get("status") == "open"), None)
            if not open_season:
                raise RuntimeError(f"No open season found for requested {SEASON_LABEL}")
            season = open_season
        table_paths = {name: value["path"] for name, value in manifest.get("tables", {}).items() if value.get("path")}
        season_paths = {name: value["path"] for name, value in season.get("files", {}).items() if value.get("path")}
        required = [table_paths[name] for name in ("club", "competition", "birth", "player_profile") if name in table_paths]
        required += [season_paths[name] for name in ("club_season", "squad") if name in season_paths]
        missing = [name for name in ("club", "competition") if name not in table_paths]
        missing += [name for name in ("club_season", "squad") if name not in season_paths]
        if missing:
            raise RuntimeError(f"Source release is missing required tables: {', '.join(missing)}")
        extracted = extract_required_files(archive, root / "source", required)
        paths = {name: extracted[path] for name, path in {**table_paths, **season_paths}.items() if path in extracted}

        db = duckdb.connect()
        db.execute("SET memory_limit='256MB'")
        db.execute("SET threads=1")
        club_path = quote_sql_path(paths["club"])
        competition_path = quote_sql_path(paths["competition"])
        club_season_path = quote_sql_path(paths["club_season"])
        squad_path = quote_sql_path(paths["squad"])

        # Only clubs participating in the current season enter the playable pool.
        # A club can have a missing squad; that gap is displayed honestly in the game.
        club_cursor = db.execute(f"""
            WITH current_entries AS (
              SELECT cs.club, cs.competition, cs.players,
                     coalesce(co.level, 9) AS level,
                     coalesce(co.name_en, cs.competition) AS competition_name,
                     c.*
              FROM read_parquet({club_season_path}) cs
              JOIN read_parquet({club_path}) c ON c.wikipedia_title = cs.club
              LEFT JOIN read_parquet({competition_path}) co ON co.code = cs.competition
              WHERE lower(coalesce(c.category,'')) NOT LIKE '%women%'
                AND lower(coalesce(c.category,'')) NOT LIKE '%youth%'
            ), ranked AS (
              SELECT *, row_number() OVER (
                PARTITION BY wikidata_qid
                ORDER BY CASE WHEN players > 0 THEN 0 ELSE 1 END,
                         level ASC, players DESC, coalesce(wikipedia_count,0) DESC
              ) AS rn
              FROM current_entries
              WHERE level BETWEEN 1 AND 4
            )
            SELECT * EXCLUDE(rn) FROM ranked
            WHERE rn=1
            ORDER BY CASE WHEN players > 0 THEN 0 ELSE 1 END,
                     level ASC, players DESC, coalesce(wikipedia_count,0) DESC,
                     country, name_en
            LIMIT {int(settings.club_target)}
        """)
        club_rows = records(club_cursor)
        if len(club_rows) < min(700, settings.club_target):
            raise RuntimeError(
                f"Only {len(club_rows)} current-season clubs qualified (minimum target is 700). Refusing to fill the pool with inactive/historical clubs."
            )
        source_to_club: dict[str, dict] = {}
        club_id_to_source: dict[str, str] = {}
        for row in club_rows:
            source_id = str(row.get("wikidata_qid") or "").strip()
            if not source_id:
                continue
            row["source_id"] = source_id
            source_to_club[source_id] = row
            tm_id = str(row.get("transfermarkt_id") or "").strip()
            if tm_id:
                club_id_to_source[tm_id] = source_id

        if not source_to_club:
            raise RuntimeError("Current season did not yield any clubs with stable Wikidata IDs")
        values = fetch_market_values()

        # Import the current-season squads of selected clubs only.
        selected_titles = [str(row.get("wikipedia_title") or "") for row in source_to_club.values()]
        selected_sql = "(" + ",".join("'" + title.replace("'", "''") + "'" for title in selected_titles if title) + ")"
        birth_join = ""
        birth_select = "NULL AS birth_date"
        if "birth" in paths:
            birth_path = quote_sql_path(paths["birth"])
            birth_join = f"LEFT JOIN read_parquet({birth_path}) b ON b.player_qid=s.player_qid AND b.precision=11"
            birth_select = "try_cast(b.birth_date AS DATE) AS birth_date"
        profile_join = ""
        photo_select = "NULL AS photo_url, NULL AS photo_license, NULL AS photo_page"
        if "player_profile" in paths:
            profile_path = quote_sql_path(paths["player_profile"])
            profile_join = f"LEFT JOIN read_parquet({profile_path}) p ON p.player_qid=s.player_qid"
            photo_select = "p.photo_url, p.photo_license, p.photo_page"
        player_cursor = db.execute(f"""
            WITH players AS (
              SELECT s.*, c.wikidata_qid AS club_source_id,
                     {birth_select}, {photo_select},
                     row_number() OVER (
                       PARTITION BY CASE WHEN coalesce(s.player_qid,'') <> '' THEN s.player_qid
                                         ELSE s.player || '|' || s.club END
                       ORDER BY CASE s.stint WHEN 'loan_in' THEN 0 WHEN 'unknown' THEN 1
                                              WHEN 'arrived_mid' THEN 2 ELSE 3 END,
                                CASE WHEN s.confidence='attested' THEN 0 ELSE 1 END
                     ) AS rn
              FROM read_parquet({squad_path}) s
              JOIN read_parquet({club_path}) c ON c.wikipedia_title=s.club
              {birth_join}
              {profile_join}
              WHERE s.club IN {selected_sql}
            )
            SELECT * EXCLUDE(rn) FROM players WHERE rn=1
        """)
        player_rows = records(player_cursor)

        club_payload: list[tuple] = []
        pool_payload: list[tuple] = []
        for row in source_to_club.values():
            lic = str(row.get("logo_license") or "")
            logo = row.get("logo_url") if is_reusable_license(lic) else None
            if not logo and row.get("logo_commons_url"):
                logo = row.get("logo_commons_url")
            league_code = str(row.get("competition") or "UNK")
            league_name = str(row.get("competition_name") or row.get("league") or league_code)
            raw = {
                "wikidata_qid": row.get("wikidata_qid"),
                "wikipedia_title": row.get("wikipedia_title"),
                "name_fr": row.get("name_fr"),
                "name_local": row.get("name_local"),
                "nickname": row.get("nickname"),
                "category": row.get("category"),
                "country_iso": row.get("country_iso"),
                "continent": continent_for_iso(row.get("country_iso")),
                "division": row.get("division"),
                "stadium": row.get("stadium"),
                "stadium_capacity": row.get("stadium_capacity"),
                "founded": row.get("founded"),
                "colors": row.get("colors"),
                "colors_hex": row.get("colors_hex"),
                "website": row.get("website"),
                "logo_license": lic,
                "logo_commons_url": row.get("logo_commons_url"),
                "wikipedia_en_url": row.get("wikipedia_en_url"),
                "wikipedia_local_url": row.get("wikipedia_local_url"),
                "transfermarkt_id": row.get("transfermarkt_id"),
                "has_squads": row.get("has_squads"),
                "source_license": "Wikipedia CC BY-SA 4.0 / Wikidata CC0",
            }
            club_payload.append((
                row["source_id"], row.get("name_en") or row.get("name_local") or row["source_id"],
                league_code, league_name, row.get("country"), continent_for_iso(row.get("country_iso")), logo,
                "Wikimedia Commons/Wikipedia" if logo else None,
                f"OpenFootballBase {tag}", row.get("wikipedia_en_url"), snapshot,
                json.dumps(raw, default=json_default, ensure_ascii=False),
            ))
            pool_payload.append((
                row["source_id"], row.get("name_en") or row.get("name_local") or row["source_id"],
                row.get("country"), row.get("country_iso"), continent_for_iso(row.get("country_iso")), league_name, league_code,
                int(row.get("level") or row.get("division") or 1), row.get("division"),
                row.get("city"), row.get("stadium"), row.get("stadium_capacity"), row.get("founded"),
                row.get("colors_hex"), logo, lic, row.get("logo_commons_url"),
                row.get("wikipedia_en_url"), bool(row.get("players") or 0), int(row.get("players") or 0),
                tag, snapshot, int(row.get("level") or 9) * 10000 - int(row.get("players") or 0),
            ))

        player_payload: list[tuple] = []
        for row in player_rows:
            club_source_id = str(row.get("club_source_id") or "")
            if club_source_id not in source_to_club:
                continue
            name = str(row.get("player") or "").strip()
            if not name:
                continue
            qid = str(row.get("player_qid") or "").strip()
            source_id = qid or "name:" + hashlib.sha1(f"{club_source_id}|{name}".encode()).hexdigest()[:20]
            club_row = source_to_club[club_source_id]
            tm_club_id = str(club_row.get("transfermarkt_id") or "").strip()
            market = values.get((tm_club_id, normalise_name(name)), {}) if tm_club_id else {}
            market_value = int(market.get("market_value_eur") or 0)
            market_date = market.get("market_value_date") or None
            dob = row.get("birth_date")
            raw_player = {
                "player_qid": qid or None,
                "club_source_id": club_source_id,
                "shirt_number": row.get("shirt_number"),
                "stint": row.get("stint"),
                "confidence": row.get("confidence"),
                "source_title": row.get("source_title"),
                "source_revid": row.get("source_revid"),
                "source_lang": row.get("source_lang"),
                "listed_in": row.get("listed_in"),
                "photo_url": row.get("photo_url") if is_reusable_license(row.get("photo_license")) else None,
                "photo_license": row.get("photo_license"),
                "photo_page": row.get("photo_page"),
                "transfermarkt": market or None,
                "squad_source_license": "Wikipedia CC BY-SA 4.0",
            }
            page = row.get("link_title")
            lang = row.get("link_lang") or "en"
            wiki_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(str(page))}" if page else None
            player_payload.append((
                source_id, club_source_id, name, dob, row.get("nationality"), row.get("position"),
                market_value, market_date, f"OpenFootballBase {tag}", wiki_url,
                json.dumps(raw_player, default=json_default, ensure_ascii=False),
            ))

        print(f"[INFO] Selected clubs: {len(club_payload)}; current squad rows: {len(player_payload)}")
        with connection() as conn:
            migrate(conn)
            run = conn.execute(
                """INSERT INTO data_import_runs(source_name,source_version,status,notes)
                   VALUES (%s,%s,'running',%s) RETURNING id""",
                ("OpenFootballBase + Transfermarkt", tag, f"snapshot={snapshot.isoformat()}, season={SEASON_LABEL}"),
            ).fetchone()["id"]
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO world_club_catalog
                       (source_id,name,league_code,league_name,country,continent,logo_url,logo_source,
                        source_name,source_url,source_updated_at,raw_data)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT(source_id) DO UPDATE SET name=EXCLUDED.name,league_code=EXCLUDED.league_code,
                         league_name=EXCLUDED.league_name,country=EXCLUDED.country,logo_url=EXCLUDED.logo_url,
                         logo_source=EXCLUDED.logo_source,source_name=EXCLUDED.source_name,
                         source_url=EXCLUDED.source_url,source_updated_at=EXCLUDED.source_updated_at,
                         raw_data=EXCLUDED.raw_data,updated_at=now()""",
                    club_payload,
                )
                cur.executemany(
                    """INSERT INTO sm27_club_pool
                       (source_id,club_name,country,country_iso,continent,league_name,league_code,league_level,division,
                        city,stadium,stadium_capacity,founded,colors_hex,logo_url,logo_license,logo_commons_url,
                        wikipedia_url,has_squad,squad_count,source_release,source_snapshot,sort_rank)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(source_id) DO UPDATE SET club_name=EXCLUDED.club_name,country=EXCLUDED.country,
                         country_iso=EXCLUDED.country_iso,continent=EXCLUDED.continent,league_name=EXCLUDED.league_name,league_code=EXCLUDED.league_code,
                         league_level=EXCLUDED.league_level,division=EXCLUDED.division,city=EXCLUDED.city,
                         stadium=EXCLUDED.stadium,stadium_capacity=EXCLUDED.stadium_capacity,founded=EXCLUDED.founded,
                         colors_hex=EXCLUDED.colors_hex,logo_url=EXCLUDED.logo_url,logo_license=EXCLUDED.logo_license,
                         logo_commons_url=EXCLUDED.logo_commons_url,wikipedia_url=EXCLUDED.wikipedia_url,
                         has_squad=EXCLUDED.has_squad,squad_count=EXCLUDED.squad_count,
                         source_release=EXCLUDED.source_release,source_snapshot=EXCLUDED.source_snapshot,
                         sort_rank=EXCLUDED.sort_rank,updated_at=now()""",
                    pool_payload,
                )
                if player_payload:
                    cur.executemany(
                        """INSERT INTO world_player_catalog
                           (source_id,club_source_id,name,date_of_birth,nationality,position,market_value_eur,
                            market_value_as_of,source_name,source_url,raw_data)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                           ON CONFLICT(source_id) DO UPDATE SET club_source_id=EXCLUDED.club_source_id,
                             name=EXCLUDED.name,date_of_birth=EXCLUDED.date_of_birth,nationality=EXCLUDED.nationality,
                             position=EXCLUDED.position,market_value_eur=EXCLUDED.market_value_eur,
                             market_value_as_of=EXCLUDED.market_value_as_of,source_name=EXCLUDED.source_name,
                             source_url=EXCLUDED.source_url,raw_data=EXCLUDED.raw_data,updated_at=now()""",
                        player_payload,
                    )
            conn.execute(
                """UPDATE data_import_runs SET imported_clubs=%s,imported_players=%s,
                          status='completed',completed_at=now(),notes=%s WHERE id=%s""",
                (len(club_payload), len(player_payload),
                 f"release={tag}; published={snapshot.isoformat()}; season={SEASON_LABEL}; archive_sha256={digest}", run),
            )
            counts = conn.execute(
                "SELECT count(*) AS clubs, (SELECT count(*) FROM world_player_catalog) AS players, count(*) FILTER (WHERE has_squad) AS with_squads FROM sm27_club_pool"
            ).fetchone()
            print(f"[OK] Catalog committed: {counts['clubs']} clubs; {counts['players']} players total; {counts['with_squads']} clubs with squad data")
        db.close()


if __name__ == "__main__":
    main()
