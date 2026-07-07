from __future__ import annotations

import json
from pathlib import Path

from copycat.watchlist import Watchlist, load_watchlist


def test_load_watchlist(tmp_path: Path) -> None:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({
        "name": "test",
        "members": [
            {"broker_id": "9227", "name": "凱基城中", "role": "leader"},
            {"broker_id": "779Z", "name": "國票安和", "role": "follower"},
        ],
    }), encoding="utf-8")
    wl = load_watchlist(p)
    assert wl == Watchlist(name="test", broker_ids=frozenset({"9227", "779Z"}))


def test_broker_id_case_sensitive(tmp_path: Path) -> None:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"name": "t", "members": [{"broker_id": "779Z", "name": "安和"}]}),
                 encoding="utf-8")
    wl = load_watchlist(p)
    assert "779Z" in wl.broker_ids and "779z" not in wl.broker_ids
