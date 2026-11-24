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
    home_advantage: float = 0.16,
) -> tuple[float, float]:
    # Reputation is a long-term baseline; the actual starting XI drives match strength.
    # A 10-point OVR gap must matter even when a source assigns every club the same stars.
    home_strength = (home_reputation * 0.15 + home_overall * 0.85) / 100
    away_strength = (away_reputation * 0.15 + away_overall * 0.85) / 100
    difference = clamp(home_strength - away_strength, -0.70, 0.70)
    home_xg = clamp(1.42 * math.exp(difference * 2.8) + home_advantage, 0.18, 3.6)
    away_xg = clamp(1.18 * math.exp(-difference * 2.8), 0.12, 3.1)
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

def estimate_transfer_value(
    overall: int,
    potential: int,
    age: int,
    league: str = "",
    country: str = "",
    attributes: dict[str, Any] | None = None,
) -> int:
    """Estimate a player's market value in euros from age, league, OVR and role traits."""
    ovr = clamp(float(overall), 35, 99)
    pot = clamp(float(potential), ovr, 99)
    years = max(16, min(43, int(age or 24)))
    league_key = (league or "").casefold()
    country_key = (country or "").casefold()

    if "premier league" in league_key and ("england" in country_key or "royaume" in country_key or "united kingdom" in country_key):
        league_factor = 1.40
    elif "la liga" in league_key or "laliga" in league_key:
        league_factor = 1.23
    elif "bundesliga" in league_key:
        league_factor = 1.20
    elif "serie a" in league_key:
        league_factor = 1.16
    elif "ligue 1" in league_key:
        league_factor = 1.12
    elif "russian premier" in league_key or "российская премьер" in league_key:
        league_factor = 0.78
    elif "saudi" in league_key or "pro league" in league_key:
        league_factor = 0.92
    elif "championship" in league_key or "segunda" in league_key or "2. bundesliga" in league_key:
        league_factor = 0.72
    else:
        league_factor = 0.86

    if years <= 19:
        age_factor = 1.58
    elif years <= 21:
        age_factor = 1.45
    elif years <= 23:
        age_factor = 1.28
    elif years <= 25:
        age_factor = 1.12
    elif years <= 29:
        age_factor = 1.0
    elif years == 30:
        age_factor = 0.88
    elif years == 31:
        age_factor = 0.76
    elif years == 32:
        age_factor = 0.64
    elif years == 33:
        age_factor = 0.52
    elif years <= 35:
        age_factor = 0.40
    else:
        age_factor = 0.28

    traits = attributes or {}
    keeper = any(str(key).upper() in {"DIV", "HAN", "REF", "POS"} for key in traits)
    relevant = ("DIV", "HAN", "REF", "POS", "KIC", "SPE") if keeper else (
        "PAC", "SHO", "PAS", "DRI", "DEF", "PHY"
    )
    values = []
    for key in relevant:
        try:
            value = float(traits.get(key, ovr))
            if math.isfinite(value):
                values.append(clamp(value, 1, 99))
        except (TypeError, ValueError):
            continue
    trait_average = sum(values) / len(values) if values else ovr
    trait_factor = clamp(0.78 + trait_average / 280, 0.82, 1.16)
    potential_factor = 1.0 + max(0.0, pot - ovr) * (0.018 if years >= 27 else 0.026)
    base = 25_000 * math.exp((ovr - 45) * 0.16)
    value = clamp(base * league_factor * age_factor * trait_factor * potential_factor, 10_000, 200_000_000)
    return int(round(value / 10_000) * 10_000)


INJURY_CATALOG: tuple[dict[str, Any], ...] = (
    {"key": "muscle_tightness", "name": "Мышечное перенапряжение", "min_days": 3, "max_days": 8},
    {"key": "hamstring_strain", "name": "Растяжение задней поверхности бедра", "min_days": 10, "max_days": 35},
    {"key": "hamstring_tear", "name": "Надрыв задней поверхности бедра", "min_days": 35, "max_days": 75},
    {"key": "calf_strain", "name": "Растяжение икроножной мышцы", "min_days": 7, "max_days": 28},
    {"key": "calf_tear", "name": "Надрыв икроножной мышцы", "min_days": 28, "max_days": 60},
    {"key": "quad_strain", "name": "Растяжение квадрицепса", "min_days": 10, "max_days": 35},
    {"key": "groin_strain", "name": "Растяжение паховых мышц", "min_days": 10, "max_days": 40},
    {"key": "hip_flexor_strain", "name": "Травма сгибателя бедра", "min_days": 14, "max_days": 42},
    {"key": "adductor_tear", "name": "Надрыв приводящей мышцы", "min_days": 28, "max_days": 70},
    {"key": "ankle_sprain", "name": "Растяжение голеностопа", "min_days": 7, "max_days": 28},
    {"key": "ankle_ligament", "name": "Повреждение связок голеностопа", "min_days": 35, "max_days": 90},
    {"key": "foot_bruise", "name": "Ушиб стопы", "min_days": 3, "max_days": 12},
    {"key": "metatarsal_fracture", "name": "Перелом плюсневой кости", "min_days": 42, "max_days": 90},
    {"key": "toe_fracture", "name": "Перелом пальца ноги", "min_days": 18, "max_days": 42},
    {"key": "achilles_tendinitis", "name": "Воспаление ахиллова сухожилия", "min_days": 14, "max_days": 45},
    {"key": "achilles_rupture", "name": "Разрыв ахиллова сухожилия", "min_days": 180, "max_days": 300},
    {"key": "knee_bruise", "name": "Ушиб колена", "min_days": 3, "max_days": 14},
    {"key": "knee_sprain", "name": "Растяжение связок колена", "min_days": 14, "max_days": 45},
    {"key": "mcl_injury", "name": "Повреждение медиальной связки колена", "min_days": 28, "max_days": 75},
    {"key": "lcl_injury", "name": "Повреждение боковой связки колена", "min_days": 21, "max_days": 60},
    {"key": "acl_tear", "name": "Разрыв крестообразной связки колена", "min_days": 180, "max_days": 270},
    {"key": "meniscus_tear", "name": "Повреждение мениска", "min_days": 35, "max_days": 120},
    {"key": "patellar_tendinitis", "name": "Воспаление связки надколенника", "min_days": 14, "max_days": 45},
    {"key": "knee_cartilage", "name": "Повреждение хряща колена", "min_days": 60, "max_days": 150},
    {"key": "shoulder_dislocation", "name": "Вывих плеча", "min_days": 28, "max_days": 70},
    {"key": "shoulder_sprain", "name": "Растяжение связок плеча", "min_days": 10, "max_days": 35},
    {"key": "collarbone_fracture", "name": "Перелом ключицы", "min_days": 45, "max_days": 100},
    {"key": "wrist_fracture", "name": "Перелом запястья", "min_days": 35, "max_days": 80},
    {"key": "finger_fracture", "name": "Перелом пальца руки", "min_days": 14, "max_days": 35},
    {"key": "rib_contusion", "name": "Ушиб рёбер", "min_days": 7, "max_days": 28},
    {"key": "rib_fracture", "name": "Перелом ребра", "min_days": 28, "max_days": 70},
    {"key": "concussion", "name": "Сотрясение мозга", "min_days": 14, "max_days": 35},
    {"key": "facial_fracture", "name": "Перелом лицевой кости", "min_days": 28, "max_days": 70},
    {"key": "nose_fracture", "name": "Перелом носа", "min_days": 7, "max_days": 25},
    {"key": "lower_back_pain", "name": "Боль в пояснице", "min_days": 5, "max_days": 21},
    {"key": "back_spasm", "name": "Спазм мышц спины", "min_days": 7, "max_days": 28},
    {"key": "stress_fracture", "name": "Стрессовый перелом", "min_days": 45, "max_days": 120},
    {"key": "plantar_fasciitis", "name": "Плантарный фасциит", "min_days": 14, "max_days": 55},
    {"key": "ankle_fracture", "name": "Перелом лодыжки", "min_days": 75, "max_days": 150},
    {"key": "dislocated_finger", "name": "Вывих пальца", "min_days": 5, "max_days": 18},
)


def _dates_between(start: date, end: date, weekday: int) -> list[date]:
    first = start + timedelta(days=(weekday - start.weekday()) % 7)
    result: list[date] = []
    current = first
    while current <= end:
        result.append(current)
        current += timedelta(days=7)
    return result


def _evenly_spaced(values: list[date], amount: int) -> list[date]:
    if amount <= 0 or not values:
        return []
    if len(values) <= amount:
        return values[:]
    if amount == 1:
        return [values[len(values) // 2]]
    indexes = [round(index * (len(values) - 1) / (amount - 1)) for index in range(amount)]
    return [values[index] for index in indexes]


def league_schedule_dates(
    tournament_name: str,
    country: str,
    season_start_year: int,
    round_count: int,
) -> list[date]:
    """Build a league-specific domestic calendar and keep most midweeks free for cups/UEFA."""
    name = (tournament_name or "").casefold()
    nation = (country or "").casefold()
    year = int(season_start_year)
    if round_count <= 0:
        return []

    if "russian premier" in name or "рпл" in name or "российская премьер" in name or nation in {"russia", "россия"}:
        first = _dates_between(date(year, 7, 25), date(year, 12, 6), 5)
        second = _dates_between(date(year + 1, 2, 27), date(year + 1, 5, 29), 5)
        second += [date(year + 1, 3, 17), date(year + 1, 4, 14)]
        second = sorted(set(second))
        first_rounds = round_count // 2
        second_rounds = round_count - first_rounds
        return _evenly_spaced(first, first_rounds) + _evenly_spaced(second, second_rounds)

    if "premier league" in name and ("england" in nation or "royaume" in nation or "kingdom" in nation):
        start, end = date(year, 8, 22), date(year + 1, 5, 29)
        weekends = [
            day for day in _dates_between(start, end, 5)
            if not (date(year, 12, 19) <= day <= date(year + 1, 1, 9))
            and day not in {
                date(year, 9, 5), date(year, 10, 10), date(year, 11, 14), date(year + 1, 3, 20)
            }
        ]
        midweeks = [
            date(year, 9, 16), date(year, 10, 28), date(year, 12, 2),
            date(year + 1, 1, 27), date(year + 1, 4, 21),
        ]
        return sorted(_evenly_spaced(weekends, max(0, round_count - len(midweeks))) + midweeks[:round_count])

    if "la liga" in name or "laliga" in name:
        start, end = date(year, 8, 16), date(year + 1, 5, 30)
        weekends = [
            day for day in _dates_between(start, end, 6)
            if not (date(year, 12, 20) <= day <= date(year + 1, 1, 3))
            and day not in {
                date(year, 9, 6), date(year, 10, 11), date(year, 11, 15), date(year + 1, 3, 28)
            }
        ]
        weekends.append(date(year + 1, 5, 29))
        midweeks = [date(year, 9, 16), date(year + 1, 4, 22)]
        return sorted(_evenly_spaced(sorted(set(weekends)), max(0, round_count - len(midweeks))) + midweeks[:round_count])

    if "saudi" in name or "arabie" in nation or "saudi arabia" in nation:
        start, end = date(year, 8, 14), date(year + 1, 5, 28)
        Fridays = [
            day for day in _dates_between(start, end, 4)
            if not (date(year, 12, 18) <= day <= date(year + 1, 1, 8))
            and not (date(year + 1, 2, 12) <= day <= date(year + 1, 3, 5))
        ]
        return _evenly_spaced(Fridays, round_count)

    start, end = date(year, 8, 15), date(year + 1, 5, 29)
    weekends = [
        day for day in _dates_between(start, end, 5)
        if not (date(year, 12, 19) <= day <= date(year + 1, 1, 9))
    ]
    if len(weekends) < round_count:
        midweek = _dates_between(start, end, 2)
        weekends = sorted(set(weekends + midweek))
    return _evenly_spaced(weekends, round_count)

