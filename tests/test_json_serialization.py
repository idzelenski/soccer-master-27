from datetime import date, datetime, timezone

from app.main import _json_safe_date


def test_json_safe_date_converts_date_to_iso_string():
    assert _json_safe_date(date(2026, 11, 24)) == "2026-11-24"


def test_json_safe_date_converts_datetime_to_iso_string():
    value = datetime(2026, 11, 24, 13, 52, tzinfo=timezone.utc)
    assert _json_safe_date(value) == "2026-11-24T13:52:00+00:00"


def test_json_safe_date_preserves_json_compatible_values():
    assert _json_safe_date(None) is None
    assert _json_safe_date("2026-11-24") == "2026-11-24"
