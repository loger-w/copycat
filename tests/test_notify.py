"""Discord webhook 發送層(copycat.notify)測試 — SC-1..SC-4."""

from __future__ import annotations

import email.message
import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from copycat import notify

URL = "https://discord.test/api/webhooks/1/abc"


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notify, "_WEBHOOK_URL", None)
    monkeypatch.setattr(notify, "_URL_RESOLVED", False)


class FakeResp:
    def __init__(self, status: int = 204) -> None:
        self.status = status

    def __enter__(self) -> FakeResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b""


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(URL, code, "err", hdrs, io.BytesIO(b"body"))


# ---------- SC-1:no-op ----------


def test_no_url_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # 無 .env
    calls: list[Any] = []
    monkeypatch.setattr(notify, "urlopen", lambda *a, **kw: calls.append(a))
    assert notify.notify_discord("hi") is False
    assert calls == []


def test_env_empty_value_is_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DISCORD_WEBHOOK_URL=   \n", encoding="utf-8")
    assert notify.resolve_webhook_url() is None


# ---------- SC-2:payload 形狀 ----------


def _capture_urlopen(monkeypatch: pytest.MonkeyPatch, reqs: list[Any], status: int = 204) -> None:
    def fake(req: Any, timeout: float = 0.0) -> FakeResp:
        reqs.append(req)
        return FakeResp(status)

    monkeypatch.setattr(notify, "urlopen", fake)


def test_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    reqs: list[Any] = []
    _capture_urlopen(monkeypatch, reqs)
    ok = notify.notify_discord("訊息內容", title="標題", fields={"股號": "2330", "價": "1000"})
    assert ok is True
    assert len(reqs) == 1
    req = reqs[0]
    assert req.full_url == URL
    assert req.get_header("Content-type") == "application/json"
    body = json.loads(req.data.decode("utf-8"))
    embed = body["embeds"][0]
    assert embed["title"] == "標題"
    assert embed["description"] == "訊息內容"
    assert embed["fields"] == [
        {"name": "股號", "value": "2330"},
        {"name": "價", "value": "1000"},
    ]


def test_default_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    reqs: list[Any] = []
    _capture_urlopen(monkeypatch, reqs)
    assert notify.notify_discord("msg") is True
    embed = json.loads(reqs[0].data.decode("utf-8"))["embeds"][0]
    assert embed["title"] == "copycat"
    assert "fields" not in embed


def test_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    reqs: list[Any] = []
    _capture_urlopen(monkeypatch, reqs)
    fields = {f"k{i:03d}" + "n" * 300: "v" * 2000 for i in range(30)}
    assert notify.notify_discord("d" * 5000, fields=fields) is True
    embed = json.loads(reqs[0].data.decode("utf-8"))["embeds"][0]
    assert len(embed["description"]) == 4096
    assert len(embed["fields"]) == 25
    assert all(len(f["name"]) <= 256 and len(f["value"]) <= 1024 for f in embed["fields"])


# ---------- SC-3:失敗語意 ----------


def test_429_retry_once_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    sleeps: list[float] = []
    monkeypatch.setattr(notify, "sleep", sleeps.append)
    attempts: list[int] = []

    def fake(req: Any, timeout: float = 0.0) -> FakeResp:
        attempts.append(1)
        if len(attempts) == 1:
            raise _http_error(429, retry_after="2")
        return FakeResp(204)

    monkeypatch.setattr(notify, "urlopen", fake)
    assert notify.notify_discord("m") is True
    assert sleeps == [2.0]
    assert len(attempts) == 2


def test_429_retry_after_capped_and_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    sleeps: list[float] = []
    monkeypatch.setattr(notify, "sleep", sleeps.append)
    monkeypatch.setattr(
        notify, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(_http_error(429, "99"))
    )
    assert notify.notify_discord("m") is False
    assert sleeps == [5.0]


def test_429_retry_after_garbage_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    sleeps: list[float] = []
    monkeypatch.setattr(notify, "sleep", sleeps.append)
    monkeypatch.setattr(
        notify, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(_http_error(429, "soon"))
    )
    assert notify.notify_discord("m") is False
    assert sleeps == [1.0]


def test_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    attempts: list[int] = []

    def fake(req: Any, timeout: float = 0.0) -> FakeResp:
        attempts.append(1)
        raise _http_error(404)

    monkeypatch.setattr(notify, "urlopen", fake)
    assert notify.notify_discord("m") is False
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "exc", [TimeoutError("ssl read timeout"), urllib.error.URLError("dns"), OSError(0, "conn")]
)
def test_network_errors_swallowed(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    monkeypatch.setattr(notify, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(exc))
    assert notify.notify_discord("m") is False


# ---------- SC-1/SC-4:URL 解析 ----------


def test_env_file_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "FINMIND_TOKEN=x\nDISCORD_WEBHOOK_URL=" + URL + "\n", encoding="utf-8"
    )
    assert notify.resolve_webhook_url() == URL


def test_env_var_wins_and_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", URL)
    assert notify.resolve_webhook_url() == URL
    monkeypatch.delenv("DISCORD_WEBHOOK_URL")
    assert notify.resolve_webhook_url() == URL  # lazy cache


# ---------- SC-4:CLI ----------


def test_cli_notify_test_no_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from copycat.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["notify-test"]) == 1


def test_cli_notify_test_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from copycat.cli import main

    monkeypatch.setattr(notify, "resolve_webhook_url", lambda: URL)
    sent: list[tuple[str, str | None]] = []

    def fake_notify(message: str, *, title: str | None = None, fields: Any = None) -> bool:
        sent.append((message, title))
        return True

    monkeypatch.setattr(notify, "notify_discord", fake_notify)
    assert main(["notify-test", "--message", "hello", "--title", "t"]) == 0
    assert sent == [("hello", "t")]


def test_cli_notify_test_send_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from copycat.cli import main

    monkeypatch.setattr(notify, "resolve_webhook_url", lambda: URL)
    monkeypatch.setattr(notify, "notify_discord", lambda message, **kw: False)
    assert main(["notify-test"]) == 1
