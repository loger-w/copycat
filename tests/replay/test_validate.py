from __future__ import annotations

from copycat.replay.validate import _within_pp, _within_rel, format_validate


def test_within_rel() -> None:
    assert _within_rel(actual=100, golden=104, tol=0.05) is True
    assert _within_rel(actual=100, golden=111, tol=0.05) is False


def test_within_pp() -> None:
    assert _within_pp(actual=0.074, golden=0.070, tol=0.005) is True
    assert _within_pp(actual=0.074, golden=0.060, tol=0.005) is False
    assert _within_pp(actual=None, golden=0.06, tol=0.005) is False  # 缺值 = FAIL


def test_format_validate_marks_fail() -> None:
    checks = [
        {"sc": "SC-2", "name": "x", "golden": "175", "actual": "170", "tol": "±5%", "ok": True},
        {
            "sc": "SC-5",
            "name": "y",
            "golden": "+0.72%",
            "actual": "+2.0%",
            "tol": "±0.5pp",
            "ok": False,
        },
    ]
    text = format_validate(checks)
    assert "PASS" in text and "FAIL" in text
