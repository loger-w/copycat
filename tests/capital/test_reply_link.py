"""`reply_link.ReplyLink` 純狀態機表驗(pr-review 253 F-10 抽出):退避表、排程去重、出手計數、恢復歸零、
探針值三態。client 端的接線行為(degraded 才排、clear 先於 ConnectByID、log 字面)在 test_reply_reconnect。"""

from __future__ import annotations

import pytest

from copycat.capital.reply_link import REPLY_RECONNECT_BACKOFF_SECS, ReplyLink, reconnect_delay


def test_reconnect_delay_table() -> None:
    """剛斷線等第 0 格,之後每出手一次等下一格,超出取最後一格 → 5, 10, 20, 40, 60, 60, 60。
    釘死索引口徑(改成 `attempt - 1` 或全 0 都會紅)。"""
    assert REPLY_RECONNECT_BACKOFF_SECS == (5.0, 10.0, 20.0, 40.0, 60.0)
    assert [reconnect_delay(n) for n in range(7)] == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0]


def test_schedule_is_idempotent_until_recovered() -> None:
    """事件與探針都會叫 schedule:同一次斷線只排一次(第二次回 None、`next` 不動);恢復後才能再排。"""
    link = ReplyLink()
    assert link.schedule(100.0) == 5.0
    assert link.next == 105.0
    assert link.schedule(101.0) is None
    assert link.next == 105.0
    assert link.recovered() == 0
    assert link.next is None
    assert link.schedule(200.0) == 5.0


def test_attempts_walk_the_table_and_reset_on_recovery() -> None:
    link = ReplyLink()
    link.schedule(0.0)
    assert not link.due(4.9)
    assert link.due(5.0)
    walked = []
    now = 5.0
    for _ in range(6):
        attempt, delay = link.begin_attempt(now)
        walked.append((attempt, delay))
        assert link.next is not None
        assert link.next == now + delay
        now = link.next
    assert walked == [(1, 10.0), (2, 20.0), (3, 40.0), (4, 60.0), (5, 60.0), (6, 60.0)]
    assert link.recovered() == 6
    assert (link.next, link.attempts) == (None, 0)
    assert link.schedule(now) == 5.0  # 歸零後又從第 0 格開始


def test_due_is_false_when_unscheduled() -> None:
    assert not ReplyLink().due(1e9)


@pytest.mark.parametrize(
    ("value", "verdict"),
    [(0, "down"), (1, "up"), (2, None), (3, None), (-1, None)],
)
def test_classify_probe_three_states(value: int, verdict: str | None) -> None:
    """0 = 斷、1 = 連、其他不動(2 = 連線中,2026-09-15 23:59:56 實錄首值)。"""
    assert ReplyLink.classify_probe(value) == verdict
