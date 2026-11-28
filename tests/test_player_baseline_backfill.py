from datetime import date
from pathlib import Path

from app.player_baselines import build_baseline_values


def test_fc27_match_uses_official_ovr_and_attributes_but_marks_potential_as_sm27():
    values = build_baseline_values({
        "source_id":"ea-player-1","name":"Example Player","club_name":"Example FC",
        "country":"Spain","league_name":"La Liga","league_code":"ESP-1","team_strength":80,
        "date_of_birth":date(2000,1,1),"source_position":"MF","fc27_player_id":12345,
        "fc27_position":"CM","fc27_overall":84,
        "fc27_attributes":{"PAC":75,"SHO":70,"PAS":85,"DRI":82,"DEF":68,"PHY":77},
        "market_value_eur":25_000_000,"market_value_as_of":date(2026,11,1),
        "source_url":"https://example.test/player","ea_source_url":"https://ea.com/player/12345",
    })
    assert values["baseline_overall"] == 84
    assert values["baseline_position"] == "CM"
    assert values["baseline_attributes"]["PAS"] == 85
    assert values["baseline_potential"] >= 84
    assert values["baseline_research"]["potential_source"] == "SM27 deterministic potential model"
    assert values["baseline_market_value"] == 25_000_000
    assert values["baseline_market_value_source"] == "Transfermarkt"
    assert values["baseline_source_url"] == "https://ea.com/player/12345"


def test_unmatched_player_profile_is_complete_and_deterministic():
    row = {
        "source_id":"world-player-99","name":"Unknown Midfielder","club_name":"Example FC",
        "country":"Germany","league_name":"Bundesliga","league_code":"GER-1","team_strength":67,
        "date_of_birth":date(2002,3,10),"source_position":"MF","fc27_player_id":None,
        "fc27_position":None,"fc27_overall":None,"fc27_attributes":{},"market_value_eur":0,
        "market_value_as_of":None,"source_url":None,"ea_source_url":None,
    }
    first,second=build_baseline_values(row),build_baseline_values(row)
    assert first == second
    assert 40 <= first["baseline_overall"] <= 90
    assert first["baseline_potential"] >= first["baseline_overall"]
    assert first["baseline_attributes"]
    assert first["baseline_market_value"] > 0
    assert first["baseline_market_value_source"] == "SM27 estimate"
    assert first["baseline_weekly_wage"] > 0
    assert first["baseline_contract_end"] > date(2026,11,28)


def test_researched_spartak_profile_takes_precedence_without_ea_match():
    values=build_baseline_values({
        "source_id":"spartak-roman-zobnin","name":"Roman Zobnin","club_name":"Spartak Moscow",
        "country":"Russia","league_name":"Russian Premier League","league_code":"RUS-1",
        "team_strength":78,"date_of_birth":date(1994,2,11),"source_position":"MF",
        "fc27_player_id":None,"fc27_position":None,"fc27_overall":None,"fc27_attributes":{},
        "market_value_eur":0,"market_value_as_of":None,"source_url":None,"ea_source_url":None,
    })
    assert values["baseline_overall"] == 77
    assert values["baseline_potential"] == 77
    assert values["baseline_profile_source"].startswith("SM27 researched estimate")
    assert values["baseline_market_value_source"] == "SofaScore"
    assert values["baseline_attributes"]["PAS"] == 76


def test_importer_does_not_update_existing_career_players():
    source=Path("scripts/import_fc27_ratings.py").read_text(encoding="utf-8")
    assert "update_career_players" not in source
    assert "UPDATE players SET" not in source
    main=source.split("def main(database_url:",1)[1]
    assert "update_world_player_matches(conn,match_candidates(records))" in main
    assert "backfill_player_baseline_catalog(conn)" in main


def test_app_startup_backfills_baseline_without_touching_live_career_values():
    source=Path("app/main.py").read_text(encoding="utf-8")
    lifespan=source.split("async def lifespan(",1)[1].split("app = FastAPI",1)[0]
    assert "backfill_player_baseline_catalog(conn)" in lifespan
