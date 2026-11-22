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
    assert estimated_weekly_wage(84, 41, 95, "Cristiano Ronaldo") == 53_000
    assert estimated_weekly_wage(84, 41, 95, "Cristiano Ronaldo dos Santos Aveiro") == 53_000
    assert estimated_weekly_wage(83, 35, 95, "Iñigo Martínez") == 245_000
    assert estimated_weekly_wage(83, 35, 95, "Iñigo Martínez Berridi") == 245_000
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
            "name_key": "zubimendi",
            "first_name": "Martín",
            "last_name": "Zubimendi Ibáñez",
            "nationality_code": "ESP",
            "club_name": "Arsenal",
            "position": "CDM",
        },
        {
            "ea_player_id": 263578,
            "name_key": "balde",
            "first_name": "Alejandro",
            "last_name": "Balde Martínez",
            "nationality_code": "ESP",
            "club_name": "FC Barcelona",
            "position": "LB",
        },
        {
            "ea_player_id": 277179,
            "name_key": "fermin",
            "first_name": "Fermín",
            "last_name": "López Marín",
            "nationality_code": "ESP",
            "club_name": "FC Barcelona",
            "position": "CAM",
        },
        {
            "ea_player_id": 231936,
            "name_key": "benjaminwhite",
            "first_name": "Benjamin",
            "last_name": "White",
            "nationality_code": "ENG",
            "club_name": "Arsenal",
            "position": "RB",
        },
    ]
    index = match_candidates(records)
    assert choose_match("Martín Zubimendi", "ESP", "Arsenal", "CAM", index)["ea_player_id"] == 248148
    assert choose_match("Alejandro Balde", "ESP", "FC Barcelona", "RWB", index)["ea_player_id"] == 263578
    assert choose_match("Fermín López", "ESP", "FC Barcelona", "CAM", index)["ea_player_id"] == 277179
    assert choose_match("Ben White", "ENG", "Arsenal", "RB", index)["ea_player_id"] == 231936
