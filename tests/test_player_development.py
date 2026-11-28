from pathlib import Path

from app.engine import (
    calculate_season_development,
    develop_attributes_for_season,
    morale_overall_modifier,
    player_match_fitness_modifier,
)
from app.main import player_baseline_snapshot


def test_dynamic_overall_uses_only_morale_and_stays_within_minus_four_plus_two():
    assert morale_overall_modifier(0) == -4
    assert morale_overall_modifier(70) == 0
    assert morale_overall_modifier(100) == 2


def test_match_fitness_can_affect_match_performance_without_changing_dynamic_overall():
    exhausted = {"morale": 70, "sharpness": 0, "fatigue": 100}
    assert morale_overall_modifier(exhausted["morale"]) == 0
    assert player_match_fitness_modifier(exhausted) == -3
    assert player_match_fitness_modifier({"sharpness": 85, "fatigue": 0}) == 0


def test_young_player_with_minutes_and_strong_performances_develops():
    delta, remainder = calculate_season_development(
        overall=70, potential=90, age=20, minutes_played=2_400,
        team_matches=34, average_rating=7.6, form=80, morale=80,
    )
    assert 1 <= delta <= 8
    assert -1 < remainder < 1


def test_season_development_is_capped_and_never_crosses_overall_bounds():
    upward, _ = calculate_season_development(
        overall=99, potential=100, age=18, minutes_played=3_000,
        team_matches=34, average_rating=8.0, form=100, morale=100,
        growth_progress=0.9,
    )
    downward, _ = calculate_season_development(
        overall=41, potential=50, age=40, minutes_played=0,
        team_matches=34, average_rating=5.0, form=0, morale=0,
    )
    assert upward <= 1
    assert 40 <= 41 + downward
    assert -8 <= upward <= 8
    assert -8 <= downward <= 8


def test_unused_player_does_not_accumulate_a_large_single_season_drop():
    delta, _ = calculate_season_development(
        overall=72, potential=80, age=19, minutes_played=0,
        team_matches=38, average_rating=None, form=50, morale=70,
    )
    assert -3 <= delta <= 1


def test_attribute_development_changes_role_relevant_stats_and_keeps_bounds():
    before = {"PAC": 80, "SHO": 80, "PAS": 80, "DRI": 80, "DEF": 80, "PHY": 80}
    after = develop_attributes_for_season("ST", before, 3, "2026/27")
    assert after != before
    assert all(1 <= value <= 99 for value in after.values())
    assert sum(after.values()) == sum(before.values()) + 3


def test_career_baseline_snapshot_captures_all_original_player_values():
    attributes = {"PAC": 81, "SHO": 76, "PAS": 70, "DRI": 78, "DEF": 42, "PHY": 74}
    snapshot = player_baseline_snapshot(82, 88, 42_000_000, attributes)
    assert snapshot == {
        "overall": 82,
        "potential": 88,
        "market_value": 42_000_000,
        "attributes": attributes,
        "captured_at_creation": True,
    }


def test_career_reset_recreates_players_from_catalogs_without_mutating_sources():
    source = Path("app/main.py").read_text(encoding="utf-8")
    reset = source.split('@app.post("/api/saves/restart")', 1)[1].split(
        '@app.get("/api/dashboard")', 1
    )[0]
    creation = source.split('@app.post("/api/saves")', 1)[1].split(
        '@app.post("/api/saves/restart")', 1
    )[0]
    progression = source.split("def update_player_season_development(", 1)[1].split(
        "def _allocate_integer(", 1
    )[0]

    assert "DELETE FROM game_states WHERE manager_id=%s RETURNING id" in reset
    assert "world_player_catalog" not in reset
    assert "fc27_player_catalog" not in reset
    assert "FROM world_player_catalog wp" in creation
    assert "LEFT JOIN fc27_player_catalog fc" in creation
    assert '"sm27_baseline": player_baseline_snapshot(' in creation
    assert "team['source_id']" in creation
    assert "UPDATE players" in progression
    assert "UPDATE world_player_catalog" not in progression
    assert "UPDATE fc27_player_catalog" not in progression
