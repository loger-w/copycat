"""_Tee 與 _setup_prod_log 的直接單元測試(review T-3:核心交付「prod stdout 落檔」
先前只有 wiring 層的 patch 計數,落檔本身壞掉不會有任何測試紅 —— 而那個失效樣態
正是這個 feature 要消滅的:server 照常跑、只是沒有檔案證據)。"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any, cast

import pytest

import copycat.server.__main__ as main_mod


class _RecordingSink(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


class _FailingSink(io.StringIO):
    """write 一律拋 OSError(磁碟滿 / 檔案被鎖的形狀)。"""

    def __init__(self) -> None:
        super().__init__()
        self.write_attempts = 0

    def write(self, s: str) -> int:
        self.write_attempts += 1
        raise OSError("disk full")


def _tee(sink: io.StringIO) -> tuple[Any, io.StringIO]:
    console = io.StringIO()
    return main_mod._Tee(cast(Any, console), cast(Any, sink)), console


def test_write_lands_in_both_and_sink_flushed_per_write() -> None:
    sink = _RecordingSink()
    tee, console = _tee(sink)
    tee.write("line-1\n")
    assert console.getvalue() == "line-1\n"
    assert sink.getvalue() == "line-1\n"
    assert sink.flush_count >= 1  # 每筆 write 即 flush:crash 當下已落盤是本 feature 的點


def test_writelines_lands_in_sink() -> None:
    """writelines 若走 __getattr__ 委派會整個繞過 sink(review R-1 的 mutation 形狀)。"""
    sink = _RecordingSink()
    tee, console = _tee(sink)
    tee.writelines(["a\n", "b\n"])
    assert console.getvalue() == "a\nb\n"
    assert sink.getvalue() == "a\nb\n"


def test_flush_flushes_sink_independently_of_write() -> None:
    """flush() 必須自己 flush sink,不得依賴「write 每筆已 flush」(review R-4)。"""
    sink = _RecordingSink()
    tee, _console = _tee(sink)
    before = sink.flush_count
    tee.flush()
    assert sink.flush_count == before + 1


def test_isatty_false() -> None:
    tee, _console = _tee(_RecordingSink())
    assert tee.isatty() is False


def test_degrades_once_on_oserror_console_survives() -> None:
    sink = _FailingSink()
    tee, console = _tee(sink)
    tee.write("first\n")
    tee.write("second\n")
    out = console.getvalue()
    # console 那份不能丟、警告只印一次、降級後不再打 sink
    assert "first\n" in out and "second\n" in out
    assert out.count("[server-log]") == 1
    assert sink.write_attempts == 1


def test_degrades_on_valueerror_closed_sink() -> None:
    """sink 被 close 後的寫入是 ValueError 不是 OSError(review R-3)—— 也要走降級,
    不得從每筆 write 往外拋。"""
    sink = io.StringIO()
    sink.close()
    tee, console = _tee(sink)
    tee.write("after-close\n")
    assert "after-close\n" in console.getvalue()
    assert "[server-log]" in console.getvalue()


def test_getattr_delegates_and_uninitialized_raises_attributeerror() -> None:
    tee, console = _tee(_RecordingSink())
    assert tee.encoding == console.encoding  # 委派原 stream
    # 未初始化實例(copy/deepcopy 的 __new__ 空殼)要是 AttributeError,不是
    # RecursionError(review R-2)
    shell = main_mod._Tee.__new__(main_mod._Tee)
    with pytest.raises(AttributeError):
        _ = shell.anything


def test_setup_prod_log_writes_file_and_replaces_stdio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(main_mod, "LOG_DIR", tmp_path / "logs")
    # 登記還原點:_setup_prod_log 直接賦值 sys.stdout/stderr,teardown 由 monkeypatch 還原
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)

    path = main_mod._setup_prod_log()

    assert path is not None and path.exists()
    try:
        print("stdout-evidence")
        sys.stderr.write("stderr-evidence\n")
        # main() 的 basicConfig 依賴「StreamHandler 建構當下快取 sys.stderr」——
        # 此刻建的 handler 必須綁到 _Tee,鎖住 tee-before-basicConfig 的機制
        handler = logging.StreamHandler()
        assert isinstance(handler.stream, main_mod._Tee)
        text = path.read_text(encoding="utf-8")
        assert "stdout-evidence" in text
        assert "stderr-evidence" in text
    finally:
        # 收掉 sink 檔 handle(Windows 上留著會卡 tmp_path 清理)
        cast(Any, sys.stdout)._sink.close()
