import datetime as dt

from islamic import run as I


def at(*a):
    return dt.datetime(*a, tzinfo=I.NY)


def test_late_scheduled_run_still_publishes():
    # GitHub started the "midnight" run at 7:56 am New York: it must still publish
    assert I.skip_scheduled(at(2026, 11, 18, 7, 56), "2026-11-16") is None
    assert I.skip_scheduled(at(2026, 11, 18, 0, 10), "2026-11-17") is None


def test_skip_when_done_or_before_midnight():
    assert I.skip_scheduled(at(2026, 11, 18, 8, 40), "2026-11-18") == "Today's update is already published."
    assert "Before midnight" in I.skip_scheduled(at(2026, 11, 17, 23, 5), "2026-11-16")
