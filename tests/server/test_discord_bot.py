"""Discord bot 的 handler 行為與降級(design §5 — SC-8)。

**本檔必須在沒裝 extras `[discord]` 的 venv 全跑不 skip**(impl-review R4):handler 是純
async 函式,吃 duck-typed interaction(只要有 `response.defer` / `followup.send`),`Bot`
吃 duck-typed client/channel/tree,所以 discord.py 缺席時這些合約照樣測得到。只有最後
一小節「真 discord 型別接線」才 `skipif` —— 那節驗的是 discord.py 的 API 名稱沒漂移。
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from typing import Any

import pytest

from copycat.server import discord_bot
from copycat.server.discord_bot import (
    Bot,
    create_bot,
    handle_add,
    handle_list,
    handle_remove,
)
from copycat.stock_watchlist import Watchlist, WatchlistError

_HAS_DISCORD = importlib.util.find_spec("discord") is not None


class _FakeResponse:
    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self._log = log

    async def defer(self, *, thinking: bool = False) -> None:
        self._log.append(("defer", thinking))


class _FakeFollowup:
    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self._log = log

    async def send(self, content: str) -> None:
        self._log.append(("send", content))


class FakeInteraction:
    """duck-typed interaction:記錄 defer / send 的**順序**(R17 要求 defer 先行)。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.response = _FakeResponse(self.calls)
        self.followup = _FakeFollowup(self.calls)

    @property
    def sent(self) -> str:
        return next(payload for name, payload in self.calls if name == "send")

    @property
    def order(self) -> list[str]:
        return [name for name, _ in self.calls]


class FakeService:
    def __init__(self, wl: Watchlist | None = None, error: Exception | None = None) -> None:
        self.wl: Watchlist = wl if wl is not None else {"codes": [], "groups": []}
        self.error = error
        self.added: list[tuple[str, str | None]] = []
        self.removed: list[str] = []

    async def add(self, code: str, group: str | None = None) -> Watchlist:
        if self.error is not None:
            raise self.error
        self.added.append((code, group))
        return self.wl

    async def remove(self, code: str) -> Watchlist:
        if self.error is not None:
            raise self.error
        self.removed.append(code)
        return self.wl

    async def current(self) -> Watchlist:
        if self.error is not None:
            raise self.error
        return self.wl


class TestAddCommand:
    async def test_success_text_has_code_name_and_group(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_add(service, it, "2330", "主力")

        assert service.added == [("2330", "主力")]
        assert "2330" in it.sent
        assert "台積電" in it.sent
        assert "主力" in it.sent

    async def test_defers_before_replying(self) -> None:
        it = FakeInteraction()

        await handle_add(FakeService(), it, "2330", None)

        assert it.order == ["defer", "send"]
        assert it.calls[0] == ("defer", True)

    async def test_success_without_group_omits_group_text(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_add(service, it, "2330")

        assert service.added == [("2330", None)]
        assert "群組" not in it.sent

    async def test_unknown_code_still_replies_with_code(self) -> None:
        it = FakeInteraction()

        await handle_add(FakeService(), it, "9999")

        assert "9999" in it.sent

    @pytest.mark.parametrize(
        ("code_error", "expected"),
        [
            ("BAD_CODE", "股號格式不正確"),
            ("BAD_GROUP", "群組名稱不合法"),
            ("WATCHLIST_FULL", "自選已達 30 檔上限"),
        ],
    )
    async def test_watchlist_error_maps_to_chinese_text(
        self, code_error: str, expected: str
    ) -> None:
        service = FakeService(error=WatchlistError(code_error))
        it = FakeInteraction()

        await handle_add(service, it, "2330")

        assert it.sent == expected
        assert service.added == []

    async def test_service_none_replies_not_ready(self) -> None:
        it = FakeInteraction()

        await handle_add(None, it, "2330")

        assert it.order == ["defer", "send"]
        assert it.sent == "服務未就緒"

    async def test_unexpected_error_is_reported_not_raised(self) -> None:
        service = FakeService(error=RuntimeError("boom"))
        it = FakeInteraction()

        await handle_add(service, it, "2330")

        assert "失敗" in it.sent


class TestRemoveCommand:
    async def test_success(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_remove(service, it, "2330")

        assert service.removed == ["2330"]
        assert it.order == ["defer", "send"]
        assert "2330" in it.sent
        assert "台積電" in it.sent

    async def test_watchlist_error_text(self) -> None:
        service = FakeService(error=WatchlistError("BAD_CODE"))
        it = FakeInteraction()

        await handle_remove(service, it, "23")

        assert it.sent == "股號格式不正確"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_remove(None, it, "2330")

        assert it.sent == "服務未就緒"


class TestListCommand:
    async def test_groups_listed_with_ungrouped_last(self) -> None:
        service = FakeService(
            {
                "codes": ["2330", "5483", "2317"],
                "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
            }
        )
        it = FakeInteraction()

        await handle_list(service, it)

        lines = it.sent.splitlines()
        assert it.order == ["defer", "send"]
        assert "3" in lines[0]
        assert lines[1] == "【主力】2330 台積電、5483 中美晶"
        assert lines[2] == "【未分組】2317 鴻海"

    async def test_no_ungrouped_line_when_all_grouped(self) -> None:
        service = FakeService(
            {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        )
        it = FakeInteraction()

        await handle_list(service, it)

        assert "未分組" not in it.sent

    async def test_empty_watchlist(self) -> None:
        it = FakeInteraction()

        await handle_list(FakeService(), it)

        assert "空" in it.sent

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_list(None, it)

        assert it.sent == "服務未就緒"


class TestCreateBotDegradation:
    def test_token_unset_returns_none(self) -> None:
        assert create_bot(FakeService(), object()) is None

    def test_import_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """裝了 token 但沒裝 extras → 降級回 None,server 照常起(SC-8)。"""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")

        def boom() -> tuple[Any, Any]:
            raise ImportError("no discord")

        monkeypatch.setattr(discord_bot, "_import_discord", boom)

        assert create_bot(FakeService(), object()) is None

    def test_blank_token_is_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "   ")

        assert create_bot(FakeService(), object()) is None

    def test_token_falls_back_to_dotenv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(discord_bot, "_dotenv_values", lambda: {"DISCORD_BOT_TOKEN": "tok"})
        monkeypatch.setattr(discord_bot, "_dotenv_cache", None)

        assert discord_bot._getenv("DISCORD_BOT_TOKEN") == "tok"

    def test_env_wins_over_dotenv_even_when_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """安全 key 慣例(capital/factory):`set KEY=` 清空要能壓制 .env。"""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
        monkeypatch.setattr(discord_bot, "_dotenv_values", lambda: {"DISCORD_BOT_TOKEN": "tok"})
        monkeypatch.setattr(discord_bot, "_dotenv_cache", None)

        assert discord_bot._getenv("DISCORD_BOT_TOKEN") == ""


class _FakeChannel:
    def __init__(self, guild: object | None = None, fail: bool = False) -> None:
        self.guild = guild
        self.sent: list[str] = []
        self._fail = fail

    async def send(self, content: str) -> None:
        if self._fail:
            raise RuntimeError("discord down")
        self.sent.append(content)


class _FakeClient:
    def __init__(
        self, channel: _FakeChannel | None = None, *, start_error: Exception | None = None
    ) -> None:
        self.channel = channel
        self.started: list[str] = []
        self.closed = False
        self._start_error = start_error
        self._stop = asyncio.Event()

    async def start(self, token: str) -> None:
        self.started.append(token)
        if self._start_error is not None:  # token 失效 → discord.py 在登入時拋
            raise self._start_error
        await self._stop.wait()

    async def close(self) -> None:
        self.closed = True
        self._stop.set()

    async def fetch_channel(self, channel_id: int) -> _FakeChannel:
        if self.channel is None:
            raise RuntimeError(f"channel {channel_id} not found")
        return self.channel


class _FakeTree:
    def __init__(self) -> None:
        self.added: list[tuple[Any, Any]] = []
        self.synced: list[Any] = []

    def add_command(self, command: Any, *, guild: Any = None, override: bool = False) -> None:
        self.added.append((command, guild))

    async def sync(self, *, guild: Any = None) -> list[Any]:
        self.synced.append(guild)
        return []


def _bot(client: _FakeClient, tree: _FakeTree | None = None, channel_id: int | None = 42) -> Bot:
    return Bot(
        client=client,
        tree=tree if tree is not None else _FakeTree(),
        command=object(),
        token="tok",
        channel_id=channel_id,
        service=FakeService(),
        hub=None,
    )


class TestBotLifecycle:
    async def test_start_bg_then_close(self) -> None:
        client = _FakeClient()
        bot = _bot(client)

        bot.start_bg()
        await asyncio.sleep(0)
        await bot.close()

        assert client.started == ["tok"]
        assert client.closed is True

    async def test_start_bg_logs_login_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """CC-6:登入失敗全程無聲。

        沒有 done callback 時,唯一的線索是第一則訊號走 fallback 留下的
        「bot 未送出,改走 webhook」—— 那行看不出是 token 錯還是斷網,而 asyncio 的
        「Task exception was never retrieved」要等 GC 才印。
        """
        client = _FakeClient(start_error=RuntimeError("Improper token"))
        bot = _bot(client)

        with caplog.at_level(logging.ERROR, logger="copycat.server.discord_bot"):
            bot.start_bg()
            await asyncio.sleep(0.01)

        assert any("登入失敗" in r.getMessage() for r in caplog.records)
        assert any("Improper token" in r.getMessage() for r in caplog.records)
        await bot.close()

    async def test_close_swallows_login_failure(self) -> None:
        """CC-1:登入失敗(token 錯)讓背景 task 帶著例外結束 —— `close()` 不得把它往外拋。

        `close()` 是關機序列的一環,拋出去會讓 `_close_signals` 的後半(hub.close)整段跳過。
        """
        client = _FakeClient(start_error=RuntimeError("LoginFailure"))
        bot = _bot(client)

        bot.start_bg()
        await asyncio.sleep(0)
        await bot.close()

        assert client.closed is True

    async def test_close_without_start_is_safe(self) -> None:
        client = _FakeClient()

        await _bot(client).close()

        assert client.closed is True

    async def test_send_signal_before_ready_is_false(self) -> None:
        assert await _bot(_FakeClient()).send_signal("hi") is False

    async def test_ready_syncs_guild_commands_and_enables_send(self) -> None:
        guild = object()
        channel = _FakeChannel(guild=guild)
        tree = _FakeTree()
        bot = _bot(_FakeClient(channel), tree)

        await bot.on_ready()

        assert tree.synced == [guild]
        assert [g for _, g in tree.added] == [guild]
        assert await bot.send_signal("訊號") is True
        assert channel.sent == ["訊號"]

    async def test_ready_without_channel_id_does_not_sync(self) -> None:
        tree = _FakeTree()
        bot = _bot(_FakeClient(_FakeChannel(guild=object())), tree, channel_id=None)

        await bot.on_ready()

        assert tree.synced == []
        assert await bot.send_signal("x") is False

    async def test_ready_with_missing_channel_degrades(self) -> None:
        tree = _FakeTree()
        bot = _bot(_FakeClient(None), tree)

        await bot.on_ready()

        assert tree.synced == []
        assert await bot.send_signal("x") is False

    async def test_send_signal_failure_returns_false(self) -> None:
        channel = _FakeChannel(guild=object(), fail=True)
        bot = _bot(_FakeClient(channel))
        await bot.on_ready()

        assert await bot.send_signal("x") is False


@pytest.mark.skipif(not _HAS_DISCORD, reason="extras [discord] 未安裝(降級路徑另有測試)")
class TestRealDiscordWiring:
    def test_create_bot_builds_client_and_tree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        discord = importlib.import_module("discord")

        monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
        monkeypatch.setenv("SIGNALS_DISCORD_CHANNEL_ID", "42")

        bot = create_bot(FakeService(), None)

        assert bot is not None
        assert isinstance(bot.client, discord.Client)
        assert bot.channel_id == 42
