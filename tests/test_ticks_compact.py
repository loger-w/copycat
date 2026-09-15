"""S2 盤後轉檔 + 讀回(spec #257 T4):jsonl fixture → CLI 入口函式 → `load_day` 讀回。

只斷言外部行為:兩個 parquet 在不在、jsonl 刪不刪、讀回的列、計數與 log 字面。
pyarrow 是 dev 依賴,測試**不允許 skip**。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from copycat import cli
from copycat.ticks import TickRow, jsonl_path, load_day
from copycat.ticks_compact import (
    CompactRefused,
    CompactResult,
    compact_day,
    format_compact_line,
)

_DAY = _dt.date(2026, 7, 21)
_TRADING = lambda d: d.weekday() < 5  # noqa: E731 — 測試用最小交易日判定


def _common(code: str, msg_seq: int, *, bid0: int = 2_375_000, kind: str) -> dict:
    return {
        "kind": kind,
        "code": code,
        "trade_date": "2026-07-21",
        "msg_seq": msg_seq,
        "recv_ns": 1_800_000_000_000_000_000 + msg_seq,
        "precise_time": "25751000000",
        "trade_status": "0",
        "bid0": bid0,
        "bid1": None,
        "bid2": None,
        "bid3": None,
        "bid4": None,
        "bidq0": 10,
        "bidq1": None,
        "bidq2": None,
        "bidq3": None,
        "bidq4": None,
        "ask0": 2_380_000,
        "ask1": 0,
        "ask2": None,
        "ask3": None,
        "ask4": None,
        "askq0": 10,
        "askq1": 0,
        "askq2": None,
        "askq3": None,
        "askq4": None,
    }


def _trade(code: str, msg_seq: int, cum: int, *, seq: int = 1, bid0: int = 2_375_000) -> dict:
    return _common(code, msg_seq, bid0=bid0, kind="trade") | {
        "time": "10:57:51.000",
        "ms": 39_471_000,
        "price_milli": 2_380_000,
        "qty": 1,
        "cum_vol": cum,
        "flag": "2",
        "side": "outer",
        "seq": seq,
    }


def _book(code: str, msg_seq: int, *, bid0: int) -> dict:
    return _common(code, msg_seq, bid0=bid0, kind="book")


#: fixture:兩檔交錯、一筆重複成交(2330 cum 2 重送)、兩檔同 cum(去重鍵少 code 會誤殺)、
#: 一行壞 JSON、簿列兩則
def _fixture_lines() -> list[str]:
    rows = [
        _trade("2330", 1, 1),
        _book("2317", 2, bid0=100_000),
        _trade("2317", 3, 5, bid0=100_000),
        _trade("2330", 4, 2, seq=2),
        _book("2330", 5, bid0=2_376_000),
        _trade("2330", 6, 2, seq=2),  # 同日重啟後達錢重送 → 去重
        _trade("2330", 7, 5, seq=3),  # 與 2317 cum 5 同鍵不同檔 → 都要留
    ]
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    lines.insert(3, '{"kind": "trade", "code": "2330", broken')  # 壞行
    return lines


def _write_fixture(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = jsonl_path(data_dir, "2026-07-21")
    p.write_text("\n".join(_fixture_lines()) + "\n", encoding="utf-8")
    return p


class TestCompactDay:
    def test_tracer_two_parquet_dedup_bad_line_and_jsonl_removed(self, tmp_path: Path) -> None:
        jsonl = _write_fixture(tmp_path)
        result = compact_day(_DAY, tmp_path, is_trading_day=_TRADING)

        assert (tmp_path / "20260721.parquet").exists()
        assert (tmp_path / "20260721-book.parquet").exists()
        assert not jsonl.exists()
        assert (result.jsonl_rows, result.trades, result.books, result.dups, result.bad_lines) == (
            8,
            4,
            2,
            1,
            1,
        )
        rows = load_day(_DAY, tmp_path)
        assert all(isinstance(r, TickRow) for r in rows)
        assert [(r.kind, r.code, r.msg_seq) for r in rows] == [
            ("trade", "2330", 1),
            ("book", "2317", 2),
            ("trade", "2317", 3),
            ("trade", "2330", 4),
            ("book", "2330", 5),
            ("trade", "2330", 7),
        ]
        assert rows[0].ms == 39_471_000 and rows[0].to_stock_tick().cum_vol == 1
        assert rows[1].price_milli is None

    def test_parquet_is_sorted_by_code_then_arrival(self, tmp_path: Path) -> None:
        _write_fixture(tmp_path)
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        table = pq.read_table(tmp_path / "20260721.parquet")
        keys = list(zip(table.column("code").to_pylist(), table.column("msg_seq").to_pylist()))
        assert keys == [("2317", 3), ("2330", 1), ("2330", 4), ("2330", 7)]
        book = pq.read_table(tmp_path / "20260721-book.parquet")
        assert book.column("code").to_pylist() == ["2317", "2330"]
        assert "price_milli" not in book.column_names  # 簿檔只有共同欄

    def test_row_count_mismatch_keeps_jsonl_and_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """注入「讀回列數對不上」:寫一半的 parquet 不得把原始資料一起帶走。"""
        from copycat import ticks_compact

        jsonl = _write_fixture(tmp_path)
        monkeypatch.setattr(ticks_compact, "_parquet_rows", lambda path: 0)
        with pytest.raises(ticks_compact.CompactFailed):
            compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert jsonl.exists()
        assert not (tmp_path / "20260721.parquet").exists()
        assert not (tmp_path / "20260721-book.parquet").exists()

    def test_missing_jsonl_is_refused_with_no_files(self, tmp_path: Path) -> None:
        with pytest.raises(CompactRefused):
            compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert not any(tmp_path.iterdir())

    def test_non_trading_day_is_refused_even_if_jsonl_exists(self, tmp_path: Path) -> None:
        sunday = _dt.date(2026, 7, 19)
        p = jsonl_path(tmp_path, sunday.isoformat())
        tmp_path.mkdir(exist_ok=True)
        p.write_text(json.dumps(_trade("2330", 1, 1)) + "\n", encoding="utf-8")
        with pytest.raises(CompactRefused):
            compact_day(sunday, tmp_path, is_trading_day=_TRADING)
        assert p.exists() and not (tmp_path / "20260719.parquet").exists()

    def test_log_line_literal(self) -> None:
        line = format_compact_line(
            _DAY,
            CompactResult(
                jsonl_rows=8, trades=4, books=2, dups=1, bad_lines=1, secs=0.26, mbytes=0.0123
            ),
        )
        assert (
            line
            == "tick 轉檔 2026-07-21:jsonl 8 列 → 成交 4 列 + 簿 2 列(去重 1、壞行 1),耗時 0.3 秒,0.0 MB"
        )


class TestReviewRound1:
    def test_refuses_when_the_trade_parquet_already_exists(self, tmp_path: Path) -> None:
        """Spec F-01(CLI 側閘):parquet 已在 = 已轉檔;再轉會把它蓋掉(空對空核對會過)。
        要重轉先刪 parquet —— 訊息要講。jsonl 與 parquet 都不動。"""
        jsonl = _write_fixture(tmp_path)
        (tmp_path / "20260721.parquet").write_bytes(b"real")
        with pytest.raises(CompactRefused, match="parquet"):
            compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert jsonl.exists()
        assert (tmp_path / "20260721.parquet").read_bytes() == b"real"
        assert not (tmp_path / "20260721-book.parquet").exists()

    def test_parquet_sorted_by_code_then_msg_seq_only(self, tmp_path: Path) -> None:
        """Spec F-03:排序鍵回到 spec 的 `(code, msg_seq)`(`msg_seq` 同日重啟自檔尾接續,
        不再靠牆鐘 `recv_ns`)。recv_ns 倒序也不影響。"""
        rows = [_trade("2330", 1, 1), _trade("2330", 2, 2, seq=2), _trade("2330", 3, 3, seq=3)]
        rows[0]["recv_ns"], rows[2]["recv_ns"] = rows[2]["recv_ns"], rows[0]["recv_ns"]  # 校時回撥
        tmp_path.mkdir(exist_ok=True)
        jsonl_path(tmp_path, "2026-07-21").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        table = pq.read_table(tmp_path / "20260721.parquet")
        assert table.column("msg_seq").to_pylist() == [1, 2, 3]
        assert [r.msg_seq for r in load_day(_DAY, tmp_path)] == [1, 2, 3]


class TestReviewRound2:
    """pr-263 review 收修(F-02 / F-03 / F-07 / F-12 / F-13)。"""

    def test_book_parquet_is_written_before_trade_parquet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F-02:「成交 parquet 存在」= 已轉檔的判準(CLI / 排程 / loader 三處),所以它必須最後落地;
        被 kill 在兩檔之間才不會卡成「已轉檔但簿列永遠讀不到」。"""
        from copycat import ticks_compact

        _write_fixture(tmp_path)
        order: list[str] = []
        real = ticks_compact._write_parquet

        def _spy(path: Path, rows: list, fields: tuple) -> None:
            order.append(path.name)
            real(path, rows, fields)

        monkeypatch.setattr(ticks_compact, "_write_parquet", _spy)
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert order == ["20260721-book.parquet", "20260721.parquet"]

    @pytest.fixture
    def jsonl_unlink_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """故障注入(不是 mock 真依賴讓測試過):只對 `.jsonl` 的 unlink 拋 Windows 那顆 PermissionError,
        其餘路徑照常;範圍縮到副檔名,比整顆 `Path.unlink` 換掉窄(收修 round-1 Standards F-08)。"""
        real_unlink = Path.unlink

        def _deny(self: Path, missing_ok: bool = False) -> None:
            if self.suffix == ".jsonl":
                raise PermissionError(32, "being used by another process")
            real_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", _deny)

    def test_unlink_failure_rolls_back_both_parquet_and_is_a_compact_failed(
        self, tmp_path: Path, jsonl_unlink_denied: None
    ) -> None:
        """F-03:Windows 上 jsonl 被別的 process 開著時 unlink 拋 PermissionError;parquet 已落地會讓
        之後每次重跑都撞「parquet 已在」exit 2 —— 要回滾成可重入狀態並以 CompactFailed 收場。"""
        from copycat import ticks_compact

        jsonl = _write_fixture(tmp_path)
        with pytest.raises(ticks_compact.CompactFailed, match="jsonl"):
            compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert jsonl.exists()
        assert not (tmp_path / "20260721.parquet").exists()
        assert not (tmp_path / "20260721-book.parquet").exists()
        assert not list(tmp_path.glob("*.tmp"))

    def test_cli_maps_unlink_failure_to_exit_1_with_a_message(
        self, tmp_path: Path, jsonl_unlink_denied: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_fixture(tmp_path)
        assert cli.main(["ticks-compact", "--date", "20260721", "--dir", str(tmp_path)]) == 1
        assert "失敗" in capsys.readouterr().err

    def test_load_day_counts_bad_utf8_as_a_bad_line_instead_of_replacing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """收修 round-1 Spec F-01:`errors="replace"` 會把壞 byte 換成 U+FFFD 後「解析成功」—— 一列髒資料
        悄悄混進去、不計壞行;要與 `compact_day` 同一個讀行器(strict、壞 byte = 壞行)。"""
        import logging

        tmp_path.mkdir(exist_ok=True)
        good = json.dumps(_trade("2330", 1, 1)).encode("utf-8")
        dirty = (
            json.dumps(_trade("2330", 2, 2) | {"flag": "x"})
            .encode("utf-8")
            .replace(b'"x"', b'"\xe4\xb8"')
        )
        jsonl_path(tmp_path, "2026-07-21").write_bytes(good + b"\n" + dirty + b"\n")
        with caplog.at_level(logging.WARNING, logger="copycat.ticks"):
            rows = load_day(_DAY, tmp_path)
        assert [r.msg_seq for r in rows] == [1]
        assert any("壞行 1" in r.getMessage() for r in caplog.records)
        # compact_day 同口徑:同一份檔 → 成交 1 列、壞行 1
        result = compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        assert (result.trades, result.bad_lines) == (1, 1)

    def test_load_day_treats_a_row_missing_identity_fields_as_bad(self, tmp_path: Path) -> None:
        """合法 JSON 但缺身分 / 排序鍵(半行被截在鍵中間又剛好合法)→ 壞行,不是 `TickRow(...)` TypeError。"""
        tmp_path.mkdir(exist_ok=True)
        jsonl_path(tmp_path, "2026-07-21").write_text(
            json.dumps(_trade("2330", 1, 1)) + "\n" + '{"kind": "book", "code": "2330"}\n',
            encoding="utf-8",
        )
        rows = load_day(_DAY, tmp_path)
        assert [r.msg_seq for r in rows] == [1]

    def test_load_day_skips_bad_jsonl_lines_like_compact_day(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """F-07:同一份檔兩個讀者要同口徑 —— 壞行跳過(WARNING 帶計數),不是整天讀不回。"""
        import logging

        _write_fixture(tmp_path)  # 含一行壞 JSON
        with caplog.at_level(logging.WARNING, logger="copycat.ticks"):
            rows = load_day(_DAY, tmp_path)
        assert len(rows) == 7  # 8 行 − 1 壞行(jsonl 分支不去重)
        assert any("壞行 1" in r.getMessage() for r in caplog.records)

    def test_full_chain_parity_from_writer_to_parquet(self, tmp_path: Path) -> None:
        """F-12:列數閘擋不住「整欄靜默 null」。寫入端 → jsonl → load_day 基準 → compact_day →
        load_day parquet,`TickRow` 逐列相等(欄名一漂這條就紅,而不是 unlink 掉唯一原始資料)。"""
        import asyncio
        import datetime as _dt

        from copycat.live.stock_models import parse_stock_realtime
        from copycat.live.tick_persist import TickPersist
        from copycat.ticks_config import TicksConfig
        from tests.server.test_stock_engine import _quote

        persist = TickPersist(
            TicksConfig(dir=str(tmp_path), flush_secs=3600.0),
            now_fn=lambda: _dt.datetime(2026, 7, 21, 10, 0, 0),
        )
        loop = asyncio.new_event_loop()
        try:
            persist.start(loop, "2026-07-21")
            msgs = [
                _quote(cum=1) | {"FlagOfBuySell": "2", "Bid1": "2370", "BidVolume1": "20"},
                _quote(cum=1, bid="2376") | {"Bid1": "2370", "BidVolume1": "20"},  # 簿列
                _quote(cum=3, price="2385", qty="2") | {"FlagOfBuySell": "1", "TradeStatus": "1"},
                _quote("2317", cum=5, bid="100", ask="101"),
            ]
            for i, msg in enumerate(msgs):
                tick, book, _meta = parse_stock_realtime(msg)
                ingested = i != 1  # 第二則 cum 未前進 = engine ingest False = 簿列候選
                persist.observe(
                    code=msg["Security"],
                    quote=msg,
                    book=book,
                    tick=tick if ingested else None,
                    engine_seq=i + 1,
                    trade_date="2026-07-21",
                    recv_ns=1_800_000_000_000_000_000 + i,
                )
        finally:
            persist.close()
            loop.close()
        before = load_day(_DAY, tmp_path)
        assert len(before) == 4 and {r.kind for r in before} == {"trade", "book"}
        assert before[0].flag == "2" and before[2].trade_status == "1"
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        after = load_day(_DAY, tmp_path)
        assert after == before

    def test_server_process_never_imports_pyarrow(self) -> None:
        """F-13:字面掃描掃不到 `copycat/ticks.py`(server 與 live 都 import 它);真斷言 = 起一個
        乾淨子程序載 `copycat.server.app`,`sys.modules` 不得出現 pyarrow。"""
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[1]
        code = (
            "import sys; import copycat.server.app; import copycat.server.ticks_compactor; "
            "import copycat.live.tick_persist; "
            "raise SystemExit(1 if any(m == 'pyarrow' or m.startswith('pyarrow.') for m in sys.modules) else 0)"
        )
        # 裸子程序不經 conftest 的憑證中和:顯式拿掉 CAPITAL_* / DISCORD_* / FINMIND(backend-conventions
        # 記錄過真憑證流入的最壞情況 = 載真 SKCOM DLL segfault;收修 round-1 Standards F-07)
        from copycat.server.verify import CAPITAL_ENV_KEYS, DISCORD_ENV_KEYS

        env = {
            k: v
            for k, v in os.environ.items()
            if k not in CAPITAL_ENV_KEYS and k not in DISCORD_ENV_KEYS and k != "FINMIND_TOKEN"
        }
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,  # 實測 < 3 s
        )
        assert proc.returncode == 0, proc.stderr[-800:]


class TestLoadDayParquet:
    def test_parquet_wins_over_a_stray_jsonl(self, tmp_path: Path) -> None:
        _write_fixture(tmp_path)
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        # 轉檔後又冒出一份 jsonl(例:server 沒重啟續寫)→ loader 仍以 parquet 為準
        jsonl_path(tmp_path, "2026-07-21").write_text(
            json.dumps(_trade("2330", 99, 99)) + "\n", encoding="utf-8"
        )
        rows = load_day(_DAY, tmp_path)
        assert 99 not in {r.msg_seq for r in rows}
        assert len(rows) == 6

    def test_missing_pyarrow_gives_an_install_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_fixture(tmp_path)
        compact_day(_DAY, tmp_path, is_trading_day=_TRADING)
        monkeypatch.setitem(sys.modules, "pyarrow", None)
        monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
        with pytest.raises(ImportError, match=r"\[ticks\]"):
            load_day(_DAY, tmp_path)


class TestCli:
    def test_cli_exit_2_on_non_trading_day(self, tmp_path: Path) -> None:
        rc = cli.main(["ticks-compact", "--date", "20260719", "--dir", str(tmp_path)])
        assert rc == 2
        assert not list(tmp_path.iterdir())

    def test_cli_exit_2_on_missing_jsonl(self, tmp_path: Path) -> None:
        assert cli.main(["ticks-compact", "--date", "20260721", "--dir", str(tmp_path)]) == 2

    def test_cli_success_prints_the_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_fixture(tmp_path)
        assert cli.main(["ticks-compact", "--date", "20260721", "--dir", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert out.startswith(
            "tick 轉檔 2026-07-21:jsonl 8 列 → 成交 4 列 + 簿 2 列(去重 1、壞行 1),耗時 "
        )


def test_pyarrow_never_imported_by_server_or_live() -> None:
    """spec #257:server 進程不 import pyarrow(轉檔走子程序)。loader 與 CLI 之外零命中。"""
    root = Path(__file__).resolve().parents[1] / "copycat"
    hits = [
        p
        for sub in ("server", "live")
        for p in (root / sub).rglob("*.py")
        if "import pyarrow" in p.read_text(encoding="utf-8")
    ]
    assert hits == []
