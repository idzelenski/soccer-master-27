from app.main import (
    FORMATION_ROLE_MAP,
    SECONDARY_POSITIONS,
    best_lineup,
    estimated_weekly_wage,
    flag_for_nationality,
    normalise_player_position,
    position_penalty,
)


FORMATIONS = [
    "3-1-4-2", "3-4-1-2", "3-4-2-1", "3-4-3", "3-4-3 Flat", "3-5-2",
    "4-1-2-1-2", "4-1-2-1-2 (2)", "4-1-2-1-2 Narrow", "4-1-2-1-2 Wide",
    "4-1-3-2", "4-1-4-1", "4-2-1-3", "4-2-2-2", "4-2-3-1",
    "4-2-3-1 (2)", "4-2-3-1 Narrow", "4-2-3-1 Wide", "4-2-4", "4-3-1-2",
    "4-3-2-1", "4-3-3", "4-3-3 (2)", "4-3-3 (3)", "4-3-3 (4)",
    "4-3-3 Attack", "4-3-3 Defend", "4-3-3 Flat", "4-3-3 Holding",
    "4-4-1-1 Midfield", "4-4-2", "4-4-2 (2)", "4-4-2 Flat", "4-4-2 Holding",
    "4-5-1", "4-5-1 (2)", "4-5-1 Attack", "4-5-1 Flat",
    "5-2-1-2", "5-2-3", "5-3-2", "5-3-2 Holding", "5-4-1", "5-4-1 Flat",
]


def test_all_fc27_formations_produce_eleven_distinct_starters():
    squad = [
        {"id": str(i), "position": pos, "secondary_positions": [], "overall": 88 - i}
        for i, pos in enumerate(
            ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "LM",
             "RM", "LW", "RW", "ST", "CF", "RWB", "LWB", "CM", "CB", "ST", "GK"]
        )
    ]
    for formation in FORMATIONS:
        starters, bench, roles = best_lineup(squad, formation)
        assert len(starters) == 11, formation
        assert len(set(starters)) == 11, formation
        assert len(roles) == 11, formation


def test_player_positions_are_not_randomly_promoted_to_secondary_positions():
    assert normalise_player_position("DF") == "CB"
    assert normalise_player_position("MF") == "CM"
    assert normalise_player_position("FW") == "ST"
    assert SECONDARY_POSITIONS["GK"] == ()
    assert position_penalty("RB", [], "RB") == 0
    assert position_penalty("RB", [], "RWB") == -2
    assert position_penalty("GK", [], "ST") == -40


def test_flags_use_country_codes_for_rectangular_svg_assets():
    assert flag_for_nationality("ESP") == "es"
    assert flag_for_nationality("POR") == "pt"
    assert flag_for_nationality("England") == "gb-eng"
    assert flag_for_nationality("Scotland") == "gb-sct"
    assert flag_for_nationality("unknown nationality") == ""


def test_weekly_wages_are_on_a_realistic_fc27_scale():
    assert estimated_weekly_wage(84, 41, 95, "Cristiano Ronaldo") == 4_007_692
    assert estimated_weekly_wage(84, 41, 95, "Cristiano Ronaldo dos Santos Aveiro") == 4_007_692
    assert estimated_weekly_wage(83, 35, 95, "Iñigo Martínez") == 196_154
    assert estimated_weekly_wage(83, 35, 95, "Iñigo Martínez Berridi") == 196_154
    assert estimated_weekly_wage(65, 24, 35) < 5_000


def test_fc27_import_preserves_trained_secondary_positions():
    from pathlib import Path

    source = Path("scripts/import_fc27_ratings.py").read_text(encoding="utf-8")
    assert "secondary_positions=ARRAY[]::text[]" not in source
    assert "UPDATE players SET secondary_positions" not in source
    assert "wc.name AS club_name" in source

def test_fc27_import_matches_full_and_short_player_names():
    from scripts.import_fc27_ratings import choose_match, match_candidates

    records = [
        {
            "ea_player_id": 248148,
            "overall": 84,
            "name_key": "zubimendi",
            "first_name": "Martín",
            "last_name": "Zubimendi Ibáñez",
            "nationality_code": "ESP",
            "club_name": "Arsenal",
            "position": "CDM",
            "overall": 87,
        },
        {
            "ea_player_id": 263578,
            "overall": 82,
            "name_key": "balde",
            "first_name": "Alejandro",
            "last_name": "Balde Martínez",
            "nationality_code": "ESP",
            "club_name": "FC Barcelona",
            "position": "LB",
            "overall": 84,
        },
        {
            "ea_player_id": 277179,
            "overall": 85,
            "name_key": "fermin",
            "first_name": "Fermín",
            "last_name": "López Marín",
            "nationality_code": "ESP",
            "club_name": "FC Barcelona",
            "position": "CAM",
            "overall": 80,
        },
        {
            "ea_player_id": 231936,
            "overall": 81,
            "name_key": "benjaminwhite",
            "first_name": "Benjamin",
            "last_name": "White",
            "nationality_code": "ENG",
            "club_name": "Arsenal",
            "position": "RB",
            "overall": 83,
        },
    ]
    index = match_candidates(records)
    assert choose_match("Martín Zubimendi", "ESP", "Arsenal", "CAM", index)["ea_player_id"] == 248148
    assert choose_match("Alejandro Balde", "ESP", "FC Barcelona", "RWB", index)["ea_player_id"] == 263578
    assert choose_match("Fermín López", "ESP", "FC Barcelona", "CAM", index)["ea_player_id"] == 277179
    assert choose_match("Ben White", "ENG", "Arsenal", "RB", index)["ea_player_id"] == 231936


def test_fc27_matching_uses_position_groups_and_rejects_wrong_clubs():
    from scripts.import_fc27_ratings import choose_match

    index = {
        "vitinha": [
            {"ea_player_id": 1, "nationality_code": "PRT", "position": "CM", "club_name": "Paris SG", "overall": 90},
            {"ea_player_id": 2, "nationality_code": "PRT", "position": "ST", "club_name": "Genoa", "overall": 75},
        ],
        "marquinhos": [
            {"ea_player_id": 3, "nationality_code": "BRA", "position": "CB", "club_name": "Paris SG", "overall": 87},
            {"ea_player_id": 4, "nationality_code": "BRA", "position": "LM", "club_name": "APOEL FC", "overall": 71},
            {"ea_player_id": 5, "nationality_code": "BRA", "position": "ST", "club_name": "Cruzeiro", "overall": 70},
        ],
        "ederson": [
            {"ea_player_id": 6, "nationality_code": "BRA", "position": "GK", "club_name": "Fenerbahçe", "overall": 82},
            {"ea_player_id": 7, "nationality_code": "BRA", "position": "CM", "club_name": "Bergamo Calcio", "overall": 82},
        ],
    }
    assert choose_match("Vitinha", "Portugal", "Paris Saint-Germain", "MF", index)["ea_player_id"] == 1
    assert choose_match("Marquinhos", "BRA", "Paris Saint-Germain", "DF", index)["ea_player_id"] == 3
    assert choose_match("Marquinhos", "BRA", "FC Spartak Moscow", "MF", index) is None
    assert choose_match("Ederson", "BRA", "Fenerbahçe Istanbul", "GK", index)["ea_player_id"] == 6


def test_researched_profiles_are_source_linked_and_not_labelled_as_ea():
    from app.researched_profiles import get_researched_profile

    profile = get_researched_profile("Esequiel Barco", "FC Spartak Moscow")
    assert profile is not None
    assert profile["overall"] == 80
    assert profile["position"] == "CAM"
    assert profile["profile_source"].startswith("SM27 researched estimate")
    assert profile["research"]["source"] == "FotMob"
    assert profile["research"]["season"] == "2026/27"
    assert profile["source_url"].startswith("https://www.fotmob.com/players/")
    assert get_researched_profile("Esequiel Barco", "Arsenal") is None
    babic = get_researched_profile("Srđan Babić", "FC Spartak Moscow")
    assert babic is not None and babic["overall"] == 76
    zinkovskiy = get_researched_profile("Anton Zinkovskiy", "FC Spartak Moscow")
    assert zinkovskiy["position"] == "LM"
    assert zinkovskiy["research"]["season"] == "2025/26"
    assert zinkovskiy["market_value"] == 2_200_000
    assert zinkovskiy["market_value_source"] == "SofaScore"
    assert zinkovskiy["research"]["sofascore_url"].startswith("https://www.sofascore.com/")
    assert get_researched_profile("An unknown academy player") is None


def test_researched_profile_is_scoped_to_spartak():
    from app.researched_profiles import get_researched_profile

    assert get_researched_profile("Esequiel Barco", "FC Spartak Moscow") is not None
    assert get_researched_profile("Esequiel Barco", "Arsenal") is None


def test_reported_weekly_wages_use_2026_27_salary_estimates():
    from app.main import estimated_weekly_wage

    assert estimated_weekly_wage(90, 41, 80, "Cristiano Ronaldo") == 4_007_692
    assert estimated_weekly_wage(80, 35, 80, "Íñigo Martínez") == 196_154


def test_spartak_research_profiles_use_sofascore_market_values():
    from app.researched_profiles import get_researched_profile

    barco = get_researched_profile("Esequiel Barco", "FC Spartak Moscow")
    ugalde = get_researched_profile("Manfred Ugalde", "FC Spartak Moscow")
    assert barco["market_value"] == 16_700_000
    assert barco["market_value_source"] == "SofaScore"
    assert barco["research"]["sofascore_url"].startswith("https://www.sofascore.com/")
    assert ugalde["market_value"] == 12_400_000


def test_squad_query_qualifies_player_columns_when_joining_fc27_catalog():
    from pathlib import Path

    source = Path("app/main.py").read_text(encoding="utf-8")
    endpoint = source.split('@app.get("/api/squad")', 1)[1].split(
        '@app.post("/api/players/{player_id}/position-training")', 1
    )[0]
    assert "SELECT p.id,p.name,p.nationality,p.birth_date,p.age,p.position,p.secondary_positions" in endpoint
    for column in (
        "overall", "potential", "market_value", "market_value_source", "weekly_wage",
        "contract_end", "fatigue", "form", "morale", "sharpness",
        "position_training_target", "position_training_progress", "fc27_player_id",
        "injury_type", "injury_until", "attributes", "original_data",
        "profile_source", "source_url",
    ):
        assert f"p.{column}" in endpoint
    assert "fc.source_url AS fc27_source_url" in endpoint


def test_generic_server_error_does_not_claim_career_data_was_saved():
    from pathlib import Path

    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "Данные сохранены" not in source
    assert "Результат действия не подтверждён" in source
