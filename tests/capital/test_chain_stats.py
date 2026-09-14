"""`chain-stats`(#234):從 server log 算回報鏈「乾淨子集」的統計。

這把尺是 Tier 2-6(回報鏈變快)的驗收判準,判準定義寫死在這裡:只算**成交回報在盤中
09:00–13:30 到達**、四段累積值**單調遞增**、**庫存段 ≥ 500 ms**(0.5 s debounce 結構上不可能更短,
更短 = 計時器被重設)的鏈;同時數群益 1019(查詢處理中)出現幾次 —— 每次 +1,060 ms 是尾巴的唯一來源。
合成 log 行逐字沿 prod 格式(`logs/server-*.log`),含 09-14 起「涵蓋 n 筆成交」尾綴。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from copycat import cli
from copycat.capital.chain_stats import format_report, summarize
from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.fake_com import FakeCom

_P = "copycat.capital.client INFO balance 鏈: "


def _chain(hhmmss: str, e: tuple[int, int, int, int], *, fills: int | None = None) -> list[str]:
    """四段一條鏈,同一時刻戳(秒級足夠,判準只看盤中與否)。"""
    tail = f",涵蓋 {fills} 筆成交" if fills is not None else ""
    ts = f"2026-09-14 {hhmmss},000 "
    return [
        f"{ts}{_P}庫存段收齊 4 列(自成交回報到達起 {e[0]} ms)",
        f"{ts}{_P}損益段收齊 5 列(自成交回報到達起 {e[1]} ms)",
        f"{ts}{_P}期貨部位段收齊 0 列(自成交回報到達起 {e[2]} ms)",
        f"{ts}{_P}部位落地 4 列(自成交回報到達起 {e[3]} ms{tail})",
    ]


_1019 = (
    "2026-09-14 10:07:33,177 copycat.capital.client WARNING "
    "GetRealBalanceReport rc=1019: SK_ERROR_QUERY_IN_PROCESSING"
)

LINES = [
    "2026-09-14 09:00:01,000 copycat.server.app INFO 無關的行",
    *_chain("10:07:33", (1061, 1637, 1940, 1941)),  # 乾淨
    _1019,
    *_chain("10:20:00", (1097, 311, 620, 621)),  # 非單調(計時器中途歸零的指紋)
    *_chain("10:30:00", (120, 700, 900, 901)),  # 庫存段 < 500 ms(debounce 不可能被跳過)
    *_chain("15:07:39", (1000, 1500, 1800, 1801)),  # 盤外(開機重播 backlog)
    # 缺庫存段起點(60 s 輪詢中途被成交點亮)
    f"2026-09-14 11:00:00,000 {_P}損益段收齊 5 列(自成交回報到達起 300 ms)",
    f"2026-09-14 11:00:00,000 {_P}期貨部位段收齊 0 列(自成交回報到達起 500 ms)",
    f"2026-09-14 11:00:00,000 {_P}部位落地 4 列(自成交回報到達起 501 ms)",
    _1019,
    *_chain("11:30:00", (2000, 2500, 3000, 3027), fills=2),  # 乾淨(新尾綴)
    # 未落地(log 在鏈中間結束)
    f"2026-09-14 13:29:59,000 {_P}庫存段收齊 4 列(自成交回報到達起 900 ms)",
]


class TestSummarize:
    def test_clean_subset_and_exclusion_reasons(self) -> None:
        s = summarize(LINES)
        assert s.total == 7
        assert s.excluded == {
            "non_monotonic": 1,
            "short_balance": 1,
            "off_session": 1,
            "no_start": 1,
            "unfinished": 1,
        }
        assert s.clean == 2
        assert s.landed_ms == [1941, 3027]
        # nearest-rank:n=2 → p50 第 1 小、p90 / p99 第 2 小
        assert (s.p50, s.p90, s.p99) == (1941, 3027, 3027)
        assert s.count_1019 == 2

    def test_session_gate_uses_fill_arrival_not_landing(self) -> None:
        """13:29:59 到達、13:30:01 落地 = 盤中(判的是成交回報到達時刻 = 段時刻 − 累積值)。"""
        lines = _chain("13:30:01", (1500, 1800, 1990, 2000))  # 到達 13:29:59.0
        s = summarize(lines)
        assert s.clean == 1 and s.excluded == {}
        late = _chain("13:30:03", (1500, 1800, 1990, 2000))  # 到達 13:30:01.0 → 盤外
        assert summarize(late).excluded == {"off_session": 1}

    def test_empty_input(self) -> None:
        s = summarize([])
        assert s.total == 0 and s.clean == 0 and s.p50 is None and s.count_1019 == 0


class TestReport:
    def test_report_lines(self) -> None:
        text = format_report(summarize(LINES))
        assert "鏈 7 條" in text and "乾淨 2 條" in text
        assert "p50 1941 ms" in text and "p90 3027 ms" in text
        assert "1019 × 2" in text
        assert "non_monotonic 1" in text


class TestCli:
    def test_chain_stats_dispatch(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        log = tmp_path / "server-20260914-0905.log"
        log.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        assert cli.main(["chain-stats", "--log", str(log)]) == 0
        out = capsys.readouterr().out
        assert "乾淨 2 條" in out and "1019 × 2" in out


class TestParityWithClientLogFormat:
    """two-axis S-01:`_STAGE_RE` 逐字複製 `_log_chain_stage` 的 log 格式 —— 產生點改一字,
    `chain-stats` 就靜默回「0 條」、驗收尺歸零。這裡不餵合成行:讓真的 `CapitalClient` 走 prod 的
    `basicConfig` format(`__main__.py`)印出四段,再餵給 `summarize`。"""

    def test_real_stage_lines_parse_into_one_clean_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import datetime as _dt
        import time

        from copycat.capital import chain_stats

        monkeypatch.setattr(chain_stats, "SESSION_START", _dt.time(0, 0))
        monkeypatch.setattr(chain_stats, "SESSION_END", _dt.time(23, 59, 59))
        lines: list[str] = []

        class _Sink(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                lines.append(self.format(record))

        sink = _Sink()
        sink.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        log = logging.getLogger("copycat.capital.client")
        log.addHandler(sink)
        log.setLevel(logging.INFO)
        try:
            client = CapitalClient(
                FakeCom(),
                user_id="u",
                password="p",
                full_account="1234567890A",
                env="test",
                safety=SafetyConfig(order_enabled=True, max_qty=5, max_amount=None),
                audit_base=tmp_path / "audit",
            )
            client._fill_seen_at = time.monotonic() - 1.0  # 成交 1 s 前到達
            client._chain_started_at = time.monotonic()  # 本輪鏈起於成交之後
            client._log_chain_stage("庫存段收齊 %d 列", 4)
            client._log_chain_stage("損益段收齊 %d 列", 5)
            client._log_chain_stage("期貨部位段收齊 %d 列", 0)
            client._log_chain_stage("部位落地 %d 列", 4, fills=2)
        finally:
            log.removeHandler(sink)
        assert len(lines) == 4
        s = summarize(lines)
        assert (s.total, s.clean, s.excluded) == (1, 1, {})
        assert s.landed_ms[0] >= 1000
