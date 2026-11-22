from collections import Counter

from app.engine import expected_goals, overall_from_market_value, round_robin, simulate_score


def test_round_robin_has_every_pair_twice():
    teams = ["a", "b", "c", "d", "e"]
    schedule = round_robin(teams)
    pairs = Counter(tuple(sorted(pair)) for rnd in schedule for pair in rnd)
    assert len(schedule) == 10
    assert len(pairs) == 10
    assert set(pairs.values()) == {2}


def test_round_robin_has_one_game_per_team_per_round():
    teams = ["a", "b", "c", "d", "e", "f"]
    for round_games in round_robin(teams):
        playing = [team for game in round_games for team in game]
        assert len(playing) == len(set(playing)) == len(teams)


def test_simulator_is_reproducible_and_bounded():
    first = simulate_score(80, 60, 78, 65, seed=123)
    second = simulate_score(80, 60, 78, 65, seed=123)
    assert first == second
    assert 0 <= first["home_score"] <= 8
    assert 0 <= first["away_score"] <= 8
    assert first["home_possession"] + first["away_possession"] == 100


def test_stronger_home_team_gets_higher_expected_goals():
    home_xg, away_xg = expected_goals(90, 45, 85, 50)
    assert home_xg > away_xg


def test_market_value_generates_game_rating_not_source_rating():
    low = overall_from_market_value(100_000, 24, 50)
    high = overall_from_market_value(80_000_000, 24, 50)
    assert 35 <= low <= 92
    assert 35 <= high <= 92
    assert high > low



def test_team_strength_creates_meaningful_expected_goal_gap():
    strong = expected_goals(100, 37, 86, 52)
    weak = expected_goals(37, 100, 52, 86)
    assert strong[0] > strong[1]
    assert weak[0] < weak[1]
    assert strong[0] - strong[1] >= 1.0


def test_stronger_team_wins_more_often_over_a_large_sample():
    outcomes = []
    for seed in range(500):
        result = simulate_score(100, 37, 86, 52, seed=seed)
        outcomes.append(result["home_score"] > result["away_score"])
    assert sum(outcomes) / len(outcomes) >= 0.78
