from datetime import date, datetime, timezone

from app.main import player_available_for_match, player_condition_modifier


def test_zero_condition_values_are_not_replaced_with_neutral_defaults():
    player = {"form": 0, "morale": 0, "sharpness": 0, "fatigue": 100}
    assert player_condition_modifier(player) == -27


def test_missing_condition_values_are_neutral():
    assert player_condition_modifier({}) == 0
    assert player_condition_modifier(
        {"form": None, "morale": None, "sharpness": None, "fatigue": None}
    ) == 0


def test_injured_player_returns_on_the_return_date():
    player = {"injury_until": date(2026, 12, 1), "suspension_matches": 0}
    assert not player_available_for_match(player, date(2026, 11, 30))
    assert player_available_for_match(player, date(2026, 12, 1))


def test_datetime_and_iso_injury_dates_are_supported():
    player_datetime = {
        "injury_until": datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc),
        "suspension_matches": 0,
    }
    player_string = {"injury_until": "2026-12-01", "suspension_matches": 0}
    assert not player_available_for_match(player_datetime, date(2026, 11, 30))
    assert not player_available_for_match(player_string, date(2026, 11, 30))


def test_suspended_player_is_unavailable_even_without_an_injury():
    assert not player_available_for_match(
        {"injury_until": None, "suspension_matches": 1}, date(2026, 11, 24)
    )


def test_available_player_can_return_to_the_lineup():
    assert player_available_for_match(
        {"injury_until": None, "suspension_matches": 0}, date(2026, 11, 24)
    )
