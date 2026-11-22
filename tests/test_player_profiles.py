from app.main import (
    best_lineup,
    estimated_contract_end,
    estimated_market_value,
    estimated_weekly_wage,
    flag_for_nationality,
    normalise_player_position,
    player_attributes,
    position_penalty,
)


def test_source_position_groups_are_expanded_to_specific_roles():
    assert normalise_player_position("DF", "player-1") in {"CB", "RB", "LB", "RWB", "LWB"}
    assert normalise_player_position("MF", "player-2") in {"CM", "CDM", "CAM", "RM", "LM"}
    assert normalise_player_position("FW", "player-3") in {"ST", "CF", "RW", "LW"}
    assert normalise_player_position("MF", "stable-id") == normalise_player_position("MF", "stable-id")


def test_player_attributes_are_position_appropriate_and_bounded():
    field = player_attributes(78, "ST", "player-st")
    keeper = player_attributes(76, "GK", "player-gk")
    assert set(field) == {"PAC", "SHO", "PAS", "DRI", "DEF", "PHY"}
    assert set(keeper) == {"DIV", "HAN", "KIC", "REF", "SPE", "POS"}
    assert all(20 <= value <= 99 for value in field.values())
    assert all(20 <= value <= 99 for value in keeper.values())


def test_market_value_wage_and_contract_estimates_are_valid():
    value = estimated_market_value(79, 87, 22)
    assert value >= 25_000
    assert estimated_weekly_wage(value) >= 250
    assert estimated_contract_end(22, "player-22").year >= 2028


def test_nationality_flags_are_resolved_for_common_and_iso_codes():
    assert flag_for_nationality("Brazil") == "🇧🇷"
    assert flag_for_nationality("Russia") == "🇷🇺"
    assert flag_for_nationality("URY") == "🇺🇾"


def test_position_penalties_follow_requested_distance_rules():
    assert position_penalty("RB", [], "RB") == 0
    assert position_penalty("RB", ["RWB"], "RWB") == 0
    assert position_penalty("RB", [], "LB") == -2
    assert position_penalty("CB", [], "ST") == -7
    assert position_penalty("GK", [], "ST") == -40
    assert position_penalty("ST", [], "GK") == -40


def test_best_lineup_returns_eleven_starters_and_seven_bench_players():
    positions = [
        "GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW",
        "GK", "CB", "CM", "CM", "ST", "RW", "LB"
    ]
    players = [
        {"id": f"p-{index}", "position": position, "secondary_positions": [], "overall": 65 + (index % 20)}
        for index, position in enumerate(positions)
    ]
    starters, bench, roles = best_lineup(players, "4-3-3")
    assert len(starters) == 11
    assert len(bench) == 7
    assert len(set(starters + bench)) == 18
    assert len(roles) == 11
