"""industry chain 落檔 / 回讀(market-overview R4 Task 2,design §4.2)。

`breadth_engine._save`/`_restore` 同款:tmp + `os.replace` 原子寫、版本與形狀
不符一律 None(never-raise)。fetched_at 是 epoch(掛鐘)—— TTL 跨重啟才算得準。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.server.chain_store import load_chain, save_chain

_ROWS: list[dict] = [
    {"stock_id": "2330", "industry": "半導體", "sub_industry": "晶圓代工"},
    {"stock_id": "2317", "industry": "電子零組件", "sub_industry": "組裝"},
]


class TestRoundtrip:
    def test_save_then_load_returns_rows_and_fetched_at(self, tmp_path: Path) -> None:
        path = tmp_path / "industry_chain.json"

        save_chain(path, _ROWS, 1754400000.5)
        loaded = load_chain(path)

        assert loaded is not None
        rows, fetched_at = loaded
        assert rows == _ROWS
        assert fetched_at == pytest.approx(1754400000.5)

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "industry_chain.json"

        save_chain(path, _ROWS, 1754400000.0)

        assert path.exists()
        loaded = load_chain(path)
        assert loaded is not None
        assert loaded[0] == _ROWS

    def test_payload_shape_is_versioned(self, tmp_path: Path) -> None:
        path = tmp_path / "industry_chain.json"

        save_chain(path, _ROWS, 1754400000.0)

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_version"] == 1
        assert payload["fetched_at"] == pytest.approx(1754400000.0)
        assert payload["rows"] == _ROWS

    def test_save_leaves_no_tmp_behind(self, tmp_path: Path) -> None:
        """原子寫:落檔後目錄只剩正式檔,tmp 不殘留。"""
        path = tmp_path / "industry_chain.json"

        save_chain(path, _ROWS, 1754400000.0)

        names = sorted(p.name for p in tmp_path.iterdir())
        assert names == ["industry_chain.json"]


class TestLoadDegradation:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert load_chain(tmp_path / "industry_chain.json") is None

    def test_bad_json_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "industry_chain.json"
        path.write_text("{not json", encoding="utf-8")

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records

    def test_version_mismatch_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "industry_chain.json"
        path.write_text(
            json.dumps({"_version": 2, "fetched_at": 1.0, "rows": _ROWS}),
            encoding="utf-8",
        )

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records

    def test_rows_not_list_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "industry_chain.json"
        path.write_text(
            json.dumps({"_version": 1, "fetched_at": 1.0, "rows": {"2330": "半導體"}}),
            encoding="utf-8",
        )

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records

    def test_fetched_at_not_number_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "industry_chain.json"
        path.write_text(
            json.dumps({"_version": 1, "fetched_at": "2026-08-06", "rows": _ROWS}),
            encoding="utf-8",
        )

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records

    def test_row_element_not_dict_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """rows 是 list 但元素不是 dict → 視為無快取(review S-3/C-4)。

        只驗 `isinstance(rows, list)` 的話,壞元素會一路交給 `rows_to_chain_map`,
        而那支在 boot 路徑上被呼叫 —— 一份壞快取檔就能讓整台 server 起不來。
        """
        path = tmp_path / "industry_chain.json"
        path.write_text(
            json.dumps({"_version": 1, "fetched_at": 1.0, "rows": [_ROWS[0], "2330", None]}),
            encoding="utf-8",
        )

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records

    def test_payload_not_dict_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "industry_chain.json"
        path.write_text(json.dumps(_ROWS), encoding="utf-8")

        with caplog.at_level("WARNING"):
            assert load_chain(path) is None

        assert caplog.records
