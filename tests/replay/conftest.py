from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.data.import_neigui import run_import
from tests.data.test_import_neigui import _write_events_csv, _write_src


@pytest.fixture()
def imported_data(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    _write_src(src)
    ev_csv = tmp_path / "tigers.csv"
    _write_events_csv(ev_csv)
    data = tmp_path / "data"
    run_import(src, ev_csv, data)
    return data


@pytest.fixture()
def watchlist_four(tmp_path: Path) -> Path:
    p = tmp_path / "wl.json"
    p.write_text(
        json.dumps(
            {
                "name": "four_tigers",
                "members": [
                    {"broker_id": "779c", "name": "國票敦北"},
                    {"broker_id": "779Z", "name": "國票安和"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return p
