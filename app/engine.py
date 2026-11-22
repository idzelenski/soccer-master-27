from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def poisson(lam: float, rng: random.Random) -> int:
    """Knuth's Poisson sampler; lambdas are deliberately kept small for football scores."""
    lam = clamp(lam, 0.05, 5.0)
    limit = math.exp(-lam)
    product = 1.0
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1


def expected_goals(
    home_reputation: float,
    away_reputation: float,
    home_overall: float = 60,
    away_overall: float = 60,
    home_advantage: float = 0.22,
) -> tuple[float, float]:
    # Club reputation is derived from the FIFA-style 0.5–5.0 star tier;
    # average squad OVR has the larger weight, so individual quality still matters.
    home_strength = (home_reputation * 0.60 + home_overall * 0.40) / 100
    away_strength = (away_reputation * 0.60 + away_overall * 0.40) / 100
    difference = clamp(home_strength - away_strength, -0.70, 0.70)
    # Reputation protects elite clubs from implausible collapses while retaining match variance.
    home_xg = clamp(1.42 * math.exp(difference * 1.55) + home_advantage, 0.18, 3.6)
    away_xg = clamp(1.18 * math.exp(-difference * 1.55), 0.12, 3.1)
    return round(home_xg, 2), round(away_xg, 2)


def simulate_score(
    home_reputation: float,
    away_reputation: float,
    home_overall: float = 60,
    away_overall: float = 60,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    home_xg, away_xg = expected_goals(
        home_reputation, away_reputation, home_overall, away_overall
    )
    home_score = poisson(home_xg, rng)
    away_score = poisson(away_xg, rng)
    combined_gap = (home_reputation - away_reputation) * 0.35 + (home_overall - away_overall) * 0.65
    possession_base = 50 + combined_gap * 0.20
    possession_home = int(round(clamp(possession_base + rng.uniform(-6, 6), 35, 65)))
    shots_home = max(home_score, int(round(home_xg * 3.4 + rng.uniform(2, 5))))
    shots_away = max(away_score, int(round(away_xg * 3.4 + rng.uniform(2, 5))))
    return {
        "home_score": home_score,
        "away_score": away_score,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "home_possession": possession_home,
        "away_possession": 100 - possession_home,
        "home_shots": shots_home,
        "away_shots": shots_away,
        "home_shots_on_target": min(shots_home, home_score + rng.randint(1, 3)),
        "away_shots_on_target": min(shots_away, away_score + rng.randint(1, 3)),
    }


def round_robin(team_ids: list[str]) -> list[list[tuple[str, str]]]:
    """Return a double round-robin schedule; first match of each pair is one leg."""
    teams = list(team_ids)
    if len(teams) < 2:
        return []
    if len(teams) % 2:
        teams.append(None)  # type: ignore[arg-type]
    size = len(teams)
    first_leg: list[list[tuple[str, str]]] = []
    rotating = teams[:]
    for round_no in range(size - 1):
        games: list[tuple[str, str]] = []
        for index in range(size // 2):
            left, right = rotating[index], rotating[size - 1 - index]
            if left is None or right is None:
                continue
            home, away = (left, right) if (round_no + index) % 2 == 0 else (right, left)
            games.append((home, away))
        first_leg.append(games)
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    second_leg = [[(away, home) for home, away in games] for games in first_leg]
    return first_leg + second_leg


def schedule_dates(start: date, rounds: int, interval_days: int = 7) -> list[date]:
    return [start + timedelta(days=interval_days * index) for index in range(rounds)]


def overall_from_market_value(
    value_eur: int, age: int | None, reputation: int, seed: int = 0
) -> int:
    """Fallback rating estimate for players without an FC 27 database match."""
    age = age or 24
    rng = random.Random(seed)
    age_component = (
        5 if age <= 21 else
        3 if age <= 24 else
        0 if age <= 29 else
        -min(12, (age - 29) * 0.75)
    )
    if value_eur > 0:
        # One market-value decade changes OVR by 15 points, not 40–50.
        score = 60 + 15 * math.log10(max(value_eur, 25_000) / 1_000_000)
        score += age_component + rng.randint(-1, 1)
    else:
        score = 42 + reputation * 0.29 + age_component + rng.randint(-3, 3)
    return int(round(clamp(score, 35, 90)))


def potential_from_overall(overall: int, age: int | None, seed: int) -> int:
    rng = random.Random(seed)
    age = age or 24
    upside = rng.randint(1, 10) if age <= 21 else rng.randint(0, 6) if age <= 24 else rng.randint(0, 2)
    return int(clamp(overall + upside, overall, 96))
