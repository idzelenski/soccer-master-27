from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import date
from typing import Any

from psycopg.types.json import Jsonb
from app.engine import estimate_transfer_value, overall_from_market_value, potential_from_overall
from app.researched_profiles import get_researched_profile

POSITION_CODES = {"GK","RB","CB","LB","RWB","LWB","CDM","CM","CAM","RM","LM","RW","LW","ST","CF"}

def _seed(source_id: str) -> int:
    return int(hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:8], 16)

def _name_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").casefold()
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if not unicodedata.combining(c)))

def _age(dob: date | None, league_code: str | None) -> int:
    if not dob:
        return 24
    code = (league_code or "").upper()
    reference = date(2026, 2, 1) if code == "USA-MLS" else date(2026, 1, 1) if code in {"BRA-SA","ARG-PD"} else date(2026, 7, 1)
    return max(16, min(43, int((reference - dob).days / 365.2425)))

def _position(value: str | None, source_id: str) -> str:
    code = (value or "").strip().upper()
    if code in POSITION_CODES:
        return code
    roles = {"DF":("CB","CB","CB","LB","RB","LWB","RWB"),"MF":("CM","CM","CM","CDM","CAM","LM","RM"),"FW":("ST","ST","ST","CF","LW","RW")}
    group = {"DEFENDER":"DF","DEFENCE":"DF","D":"DF","MIDFIELDER":"MF","MIDFIELD":"MF","M":"MF","FORWARD":"FW","ATTACKER":"FW","STRIKER":"FW","F":"FW"}.get(code, code)
    choices = roles.get(group)
    return choices[_seed(source_id) % len(choices)] if choices else "CM"

def _attributes(overall: int, position: str) -> dict[str, int]:
    rating = max(35, min(90, int(overall)))
    if position == "GK":
        offsets = {"DIV":1,"HAN":0,"KIC":-3,"REF":4,"SPE":-2,"POS":2}
    else:
        group = "DF" if position in {"CB","RB","LB","RWB","LWB"} else "FW" if position in {"ST","CF","RW","LW"} else "MF"
        offsets = {"PAC":3 if group=="FW" else -1 if group=="DF" else 1,"SHO":6 if group=="FW" else -7 if group=="DF" else -1,"PAS":4 if group=="MF" else 0 if group=="DF" else -3,"DRI":5 if group=="FW" else 2 if group=="MF" else -4,"DEF":7 if group=="DF" else 0 if group=="MF" else -12,"PHY":4 if group=="DF" else 1 if group=="FW" else -1}
    return {key:max(20,min(99,rating+offset)) for key,offset in offsets.items()}

def _weekly_wage(overall: int, age: int, reputation: int, name: str) -> int:
    key = _name_key(name)
    if key.startswith("cristianoronaldo"):
        return 4_007_692
    if key.startswith("inigomartinez"):
        return 196_154
    base = 600 * math.exp((max(35,min(95,overall))-60)*0.21)
    age_factor = 0.55 if age<=22 else 0.75 if age<=25 else 1.0 if age<=29 else 1.20 if age<=34 else 1.45 if age<=37 else 0.90 if age<=40 else 0.25
    club_factor = 0.70 + max(10,min(100,reputation))*0.0175
    return int(max(250,min(1_500_000,round(base*age_factor*club_factor/100)*100)))

def _contract_end(age: int, source_id: str) -> date:
    max_years = 2 if age>=34 else 3 if age>=30 else 5
    return date(2027 + 1 + _seed(source_id)%max_years, 6, 30)

def build_baseline_values(row: dict[str, Any]) -> dict[str, Any]:
    """Build the same deterministic starting profile used by career creation."""
    source_id = str(row["source_id"])
    name = str(row.get("name") or "")
    club = str(row.get("club_name") or "")
    league = str(row.get("league_name") or "")
    country = str(row.get("country") or "")
    reputation = max(10,min(100,int(row.get("team_strength") or 50)))
    age = _age(row.get("date_of_birth"),row.get("league_code"))
    display_name = "Fabián Ruiz" if source_id=="Q18637930" and club=="Paris Saint-Germain" else name
    ea_id = row.get("fc27_player_id")
    researched = get_researched_profile(display_name,club) if not ea_id else None

    if ea_id and row.get("fc27_overall") is not None:
        overall = int(row["fc27_overall"])
        position = str(row.get("fc27_position") or _position(row.get("source_position"),source_id))
        attrs = dict(row.get("fc27_attributes") or {}) or _attributes(overall,position)
        profile = "EA SPORTS FC 27 official ratings database"
        source_name, source_url = "EA FC 27", row.get("ea_source_url") or row.get("source_url")
        rating_source = "EA SPORTS FC 27 official OVR and attributes"
    elif researched:
        overall, position = int(researched["overall"]), str(researched["position"])
        attrs = dict(researched["attributes"])
        profile, source_name, source_url = researched["profile_source"], "FotMob research / OpenFootballBase", researched["source_url"]
        rating_source = "SM27 researched estimate based on FotMob"
    else:
        position = _position(row.get("source_position"),source_id)
        overall = overall_from_market_value(int(row.get("market_value_eur") or 0),age,reputation,_seed(source_id))
        attrs = _attributes(overall,position)
        profile, source_name, source_url = "SM27 model estimate · no EA FC 27 player match", "OpenFootballBase", row.get("source_url")
        rating_source = "SM27 deterministic model estimate"

    if researched and researched.get("potential") is not None and not ea_id:
        potential, potential_source = max(overall,int(researched["potential"])), "SM27 researched estimate"
    else:
        potential, potential_source = max(overall,potential_from_overall(overall,age,_seed(source_id))), "SM27 deterministic potential model"

    research_value = int(researched["market_value"]) if researched and researched.get("market_value") else 0
    source_value = int(row.get("market_value_eur") or 0)
    if research_value:
        value, value_source, value_date = research_value, "SofaScore", researched.get("market_value_as_of")
    elif source_value:
        value, value_source, value_date = source_value, "Transfermarkt", row.get("market_value_as_of")
    else:
        value = estimate_transfer_value(overall,potential,age,league,country,attrs)
        value_source, value_date = "SM27 estimate", None
    if isinstance(value_date,str):
        value_date = date.fromisoformat(value_date[:10])

    research = dict(researched.get("research") or {}) if researched else {}
    research.update({"rating_source":rating_source,"potential_source":potential_source,"market_value_source":value_source})
    wage_source = "Capology 2026/27 estimate" if _name_key(name).startswith(("cristianoronaldo","inigomartinez")) else "SM27 career wage model"

    return {
        "baseline_age":age,"baseline_position":position,"baseline_overall":overall,"baseline_potential":potential,
        "baseline_market_value":value,"baseline_market_value_as_of":value_date,"baseline_market_value_source":value_source,
        "baseline_weekly_wage":_weekly_wage(overall,age,reputation,display_name),
        "baseline_contract_end":_contract_end(age,source_id),"baseline_attributes":attrs,
        "baseline_profile_source":profile,"baseline_source_name":source_name,"baseline_source_url":source_url,
        "baseline_research":research,"baseline_wage_source":wage_source,
        "baseline_model_version":"sm27-full-catalog-baseline-v1",
    }

def backfill_player_baseline_catalog(conn: Any, batch_size: int = 1000) -> int:
    """Initialize uncaptured catalog baselines; preserve every already-frozen/manual row."""
    rows = conn.execute(
        """SELECT b.source_id,b.name,b.date_of_birth,b.nationality,b.source_position,
                  b.market_value_eur,b.market_value_as_of,b.source_url,b.fc27_player_id,
                  b.fc27_overall,b.fc27_attributes,b.fc27_position,fc.source_url AS ea_source_url,
                  c.club_name,c.country,c.league_name,c.league_code,c.team_strength
           FROM sm27_player_baseline_catalog b
           JOIN sm27_club_pool c ON c.source_id=b.club_source_id
           LEFT JOIN fc27_player_catalog fc ON fc.ea_player_id=b.fc27_player_id
           WHERE b.baseline_captured_at IS NULL ORDER BY b.source_id"""
    ).fetchall()
    updates = []
    for row in rows:
        v = build_baseline_values(dict(row))
        updates.append((v["baseline_age"],v["baseline_position"],v["baseline_overall"],v["baseline_potential"],
            v["baseline_market_value"],v["baseline_market_value_as_of"],v["baseline_market_value_source"],
            v["baseline_weekly_wage"],v["baseline_contract_end"],Jsonb(v["baseline_attributes"]),
            v["baseline_profile_source"],v["baseline_source_name"],v["baseline_source_url"],
            Jsonb(v["baseline_research"]),v["baseline_wage_source"],v["baseline_model_version"],row["source_id"]))
    if not updates:
        return 0
    sql = """UPDATE sm27_player_baseline_catalog SET baseline_age=%s,baseline_position=%s,
                 baseline_overall=%s,baseline_potential=%s,baseline_market_value=%s,baseline_market_value_as_of=%s,
                 baseline_market_value_source=%s,baseline_weekly_wage=%s,baseline_contract_end=%s,
                 baseline_attributes=%s,baseline_profile_source=%s,baseline_source_name=%s,baseline_source_url=%s,
                 baseline_research=%s,baseline_wage_source=%s,baseline_model_version=%s,baseline_captured_at=now()
             WHERE source_id=%s AND baseline_captured_at IS NULL"""
    size = max(1,batch_size)
    with conn.cursor() as cursor:
        for start in range(0,len(updates),size):
            cursor.executemany(sql,updates[start:start+size])
    return len(updates)
