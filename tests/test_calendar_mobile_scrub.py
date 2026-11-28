from pathlib import Path


def test_mobile_calendar_supports_long_press_drag_to_advance_date():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    styles = Path("app/static/app.css").read_text(encoding="utf-8")

    assert 'event.pointerType !== "touch" || !event.isPrimary' in source
    assert "press.scrubbing = true" in source
    assert "document.elementFromPoint(moveEvent.clientX, moveEvent.clientY)" in source
    assert 'document.addEventListener("pointermove", press.moveHandler)' in source
    assert "advanceCalendarToDate(targetDate)" in source
    assert "suppressCalendarClickUntil" in source
    assert "Зажми дату на полсекунды и веди пальцем по календарю" in source
    assert ".calendar-day { touch-action: none; }" in styles


def test_short_mobile_calendar_tap_still_selects_a_date():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    click_handler = source.split('button.addEventListener("click", event => {', 1)[1].split(
        'button.addEventListener("contextmenu"', 1
    )[0]
    assert "state.selectedCalendarDate = button.dataset.calendarDate" in click_handler
    assert "renderCurrent()" in click_handler
