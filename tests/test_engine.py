from collections import Counter
from datetime import date

from app.engine import (
    estimate_transfer_value,
    expected_goals,
    league_schedule_dates,
    overall_from_market_value,
    round_robin,
    simulate_score,
)


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


def test_equal_reputation_league_still_rewards_a_stronger_starting_xi():
    equal = expected_goals(65, 65, 65, 65)
    stronger = expected_goals(65, 65, 80, 65)
    assert stronger[0] > equal[0]
    assert stronger[1] < equal[1]


def test_strong_xi_is_favoured_even_when_catalog_reputation_is_flat():
    outcomes = []
    for seed in range(400):
        result = simulate_score(65, 65, 80, 65, seed=seed)
        outcomes.append(result["home_score"] > result["away_score"])
    assert sum(outcomes) / len(outcomes) >= 0.58



def test_ten_point_starting_xi_gap_is_meaningful_when_reputation_is_equal():
    equal = expected_goals(65, 65, 70, 70)
    strong_at_home = expected_goals(65, 65, 80, 70)
    strong_away = expected_goals(65, 65, 70, 80)
    assert strong_at_home[0] >= equal[0] + 0.20
    assert strong_at_home[1] < equal[1] - 0.10
    assert strong_away[0] < equal[0] - 0.10
    assert strong_away[1] >= equal[1] + 0.15

def test_transfer_value_uses_age_league_and_player_traits():
    traits = {"PAC": 80, "SHO": 75, "PAS": 72, "DRI": 78, "DEF": 55, "PHY": 70}
    premier = estimate_transfer_value(75, 85, 21, "Premier League", "Royaume-Uni", traits)
    russia = estimate_transfer_value(75, 85, 21, "Russian Premier League", "Russia", traits)
    older = estimate_transfer_value(75, 75, 32, "Premier League", "Royaume-Uni", traits)
    weaker = estimate_transfer_value(
        70, 70, 21, "Premier League", "Royaume-Uni",
        {"PAC": 50, "SHO": 50, "PAS": 50, "DRI": 50, "DEF": 50, "PHY": 50},
    )
    assert premier > russia
    assert premier > older
    assert premier > weaker
    assert premier >= 10_000


def test_russian_premier_league_calendar_has_winter_break():
    dates = league_schedule_dates("Russian Premier League", "Russia", 2026, 30)
    assert len(dates) == 30
    assert max(dates[:15]) <= date(2026, 12, 6)
    assert min(dates[15:]) >= date(2027, 2, 27)
    assert max(dates) <= date(2027, 5, 29)


def test_premier_league_calendar_spans_august_to_may_with_midweeks():
    dates = league_schedule_dates("Premier League", "Royaume-Uni", 2026, 38)
    assert len(dates) == 38
    assert date(2026, 8, 15) <= min(dates) <= date(2026, 8, 29)
    assert date(2027, 5, 15) <= max(dates) <= date(2027, 5, 30)
    assert sum(day.weekday() not in (5, 6) for day in dates) == 5


def test_mls_calendar_respects_2026_world_cup_break_and_34_rounds():
    dates = league_schedule_dates("Major League Soccer", "États-Unis", 2026, 34)
    assert len(dates) == 34
    assert min(dates) >= date(2026, 2, 21)
    assert max(dates) <= date(2026, 11, 7)
    assert all(not (date(2026, 5, 25) <= day <= date(2026, 7, 16)) for day in dates)


def test_brazilian_calendar_finishes_in_december():
    dates = league_schedule_dates("Campeonato Brasileiro Série A", "Brésil", 2026, 38)
    assert len(dates) == 38
    assert min(dates) < date(2026, 3, 1)
    assert max(dates) <= date(2026, 12, 2)
    assert max(dates).year == 2026


def test_northern_european_calendar_is_spring_to_autumn():
    norway = league_schedule_dates("Eliteserien", "Norvège", 2026, 30)
    sweden = league_schedule_dates("Allsvenskan", "Suède", 2026, 30)
    assert len(norway) == len(sweden) == 30
    assert min(norway).month <= 4 and max(norway).month >= 10
    assert min(sweden).month <= 4 and max(sweden).month >= 10

def test_argentine_primera_calendar_fits_32_rounds_in_one_year():
    dates = league_schedule_dates("Argentine Primera División", "Argentine", 2026, 32)
    assert len(dates) == 32
    assert min(dates) >= date(2026, 2, 1)
    assert max(dates) <= date(2026, 12, 6)
    assert sum(day.weekday() == 2 for day in dates) == 2


def test_2_bundesliga_uses_august_to_may_and_keeps_december_weekend():
    dates = league_schedule_dates("2. Bundesliga", "Allemagne", 2026, 34)
    assert len(dates) == 34
    assert min(dates) >= date(2026, 8, 8)
    assert max(dates) <= date(2027, 5, 16)
    assert any(day.month == 12 and day.day == 19 for day in dates)

