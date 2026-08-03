"""`/api/health` = 執行中 server 的建置身分(docs/next-time.md 2026-07-29 紅標)。

守的失效樣態:跑著的 server 是舊版 build,而前端與人都無從辨識 —— 該紅標的起因是
:8721 少了 `/api/stock/bars` 這條 route,卻花了一輪才發現「不是 code 沒寫,是 server 沒重啟」。
"""

from __future__ import annotations

import datetime as _dt

from fastapi.testclient import TestClient

from copycat.server import build_info
from copycat.server.app import create_app
from tests.helpers.fake_txo import FakeTxoSource


def _client() -> TestClient:
    return TestClient(create_app(FakeTxoSource()))


class TestHealthRoute:
    def test_returns_build_identity(self) -> None:
        with _client() as client:
            body = client.get("/api/health").json()
        assert set(body) == {"git_sha", "git_dirty", "started_at"}

    def test_sha_is_real_repo_head(self) -> None:
        """在本 repo 跑 = 真的問到 git,不是恆回 None 的空殼。"""
        with _client() as client:
            body = client.get("/api/health").json()
        sha = body["git_sha"]
        assert sha is not None, "本 repo 內 git sha 不該是 None"
        assert len(sha) >= 7 and all(c in "0123456789abcdef" for c in sha)
        assert isinstance(body["git_dirty"], bool)

    def test_captured_once_at_startup_not_per_request(self, monkeypatch) -> None:
        """build 身分必須在啟動時定格。

        不比對兩次請求的 `started_at` 字串 —— 它是秒解析度,同一秒內的兩次請求就算
        每次重算也會相等(假綠)。直接數 `capture` 的呼叫次數才守得住。
        """
        calls: list[int] = []
        real = build_info.capture

        def counting_capture(**kwargs) -> build_info.BuildInfo:
            calls.append(1)
            return real(**kwargs)

        monkeypatch.setattr(build_info, "capture", counting_capture)
        with _client() as client:
            first = client.get("/api/health").json()["started_at"]
            client.get("/api/health")
            client.get("/api/health")
        assert len(calls) == 1, f"capture 被呼叫 {len(calls)} 次,應只在啟動時一次"
        _dt.datetime.fromisoformat(first)  # 可解析的 ISO-8601

    def test_git_unavailable_degrades_to_none(self, monkeypatch) -> None:
        """git 未裝 / 非 repo / 打包部署 → 降級,不得讓 server 起不來。"""
        monkeypatch.setattr(build_info, "_git", lambda *args: None)
        with _client() as client:
            resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["git_sha"] is None
        assert resp.json()["git_dirty"] is None

    def test_startup_logs_banner_with_sha(self, caplog) -> None:
        """啟動 banner:不開瀏覽器也看得到版本(next-time 列的候選修法之一)。"""
        with caplog.at_level("INFO", logger="copycat.server.app"):
            with _client() as client:
                sha = client.get("/api/health").json()["git_sha"]
        banner = [r.getMessage() for r in caplog.records if "build" in r.getMessage()]
        assert banner, f"啟動未印 build banner;records={[r.getMessage() for r in caplog.records]}"
        assert sha is not None and sha in banner[0]


class TestCapture:
    def test_dirty_reflects_porcelain_output(self, monkeypatch) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_git(*args: str) -> str | None:
            calls.append(args)
            return "abc1234" if args[0] == "rev-parse" else " M copycat/x.py"

        monkeypatch.setattr(build_info, "_git", fake_git)
        info = build_info.capture()
        assert info.git_sha == "abc1234"
        assert info.git_dirty is True

    def test_clean_tree_is_not_dirty(self, monkeypatch) -> None:
        monkeypatch.setattr(
            build_info, "_git", lambda *args: "abc1234" if args[0] == "rev-parse" else ""
        )
        assert build_info.capture().git_dirty is False

    def test_dirty_is_none_when_status_fails_but_sha_works(self, monkeypatch) -> None:
        """半殘狀態要誠實回 None,不可預設 False —— 假的『乾淨』比沒有更糟。"""
        monkeypatch.setattr(
            build_info, "_git", lambda *args: "abc1234" if args[0] == "rev-parse" else None
        )
        info = build_info.capture()
        assert info.git_sha == "abc1234"
        assert info.git_dirty is None
