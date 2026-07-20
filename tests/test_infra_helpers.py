"""fileio / configio 共用 helper 直接單元測試(refactor/shared-infra-helpers 步驟 6)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from copycat.configio import load_dataclass_json
from copycat.fileio import atomic_open_text, atomic_write_text

# ---------- fileio ----------


def test_atomic_write_text_roundtrip_and_no_tmp(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    atomic_write_text(path, '{"a": 1}')
    assert path.read_text(encoding="utf-8") == '{"a": 1}'
    assert not path.with_suffix(".tmp").exists()


def test_atomic_write_text_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "out.md"
    path.write_text("old", encoding="utf-8")
    atomic_write_text(path, "new")
    assert path.read_text(encoding="utf-8") == "new"


def test_atomic_open_text_csv(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    with atomic_open_text(path) as fh:
        w = csv.DictWriter(fh, fieldnames=["a", "b"])
        w.writeheader()
        w.writerow({"a": "1", "b": "2"})
    with path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [{"a": "1", "b": "2"}]
    assert not path.with_suffix(".tmp").exists()


def test_atomic_open_text_failure_leaves_target_untouched(tmp_path: Path) -> None:
    # 沿既有語意:寫 tmp 中途失敗 → 目標檔不動(tmp 殘留可接受)
    path = tmp_path / "rows.csv"
    path.write_text("intact", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with atomic_open_text(path) as fh:
            fh.write("partial")
            raise RuntimeError("boom")
    assert path.read_text(encoding="utf-8") == "intact"


# ---------- configio ----------


@dataclass(frozen=True, slots=True)
class _Cfg:
    x: int = 1
    ys: tuple[int, ...] = (1, 2)


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_load_dataclass_json_defaults_and_override(tmp_path: Path) -> None:
    cfg = load_dataclass_json(
        _write(tmp_path, {"x": 5}), _Cfg, tuple_keys=("ys",), unknown_label="未知參數"
    )
    assert cfg == _Cfg(x=5, ys=(1, 2))


def test_load_dataclass_json_tuple_coercion(tmp_path: Path) -> None:
    cfg = load_dataclass_json(
        _write(tmp_path, {"ys": [3, 4]}), _Cfg, tuple_keys=("ys",), unknown_label="未知參數"
    )
    assert cfg.ys == (3, 4)


def test_load_dataclass_json_unknown_key_uses_label(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        load_dataclass_json(
            _write(tmp_path, {"nope": 1}), _Cfg, tuple_keys=(), unknown_label="自訂標籤"
        )
    assert str(exc.value) == "自訂標籤: ['nope']"
