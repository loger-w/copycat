"""Discord bot:`/watch` slash 指令 + 訊號推送出口(design §5 — SC-8)。

**模組層刻意不 import discord**(impl-review R4):extras `[discord]` 是選配,dev venv 沒
裝它;若在模組層 import,`tests/server/test_discord_bot.py` 整檔會 skip = 這條路的合約
其實沒被守住(vacuous gate)。所以:

- 三個指令的邏輯是**純 async 函式**(`handle_add` / `handle_remove` / `handle_list`),
  只吃 duck-typed interaction —— 需要的介面就兩個:`await interaction.response.defer(
  thinking=True)` 與 `await interaction.followup.send(text)`。
- `Bot` 吃 duck-typed client / tree / channel,構造子不碰 discord 型別。
- 只有 `create_bot` **函式內** lazy import(經 `_import_discord` 一層,測試才能決定性地
  模擬 ImportError,不必依賴「這台機器剛好沒裝」)。

降級三態一律回 `None` 讓 server 照常起(SC-8):extras 未裝 / `DISCORD_BOT_TOKEN` 未設 /
token 空字串。env 讀取採 capital/factory 的新語意 —— `name in os.environ` 即用(含空字
串,`set KEY=` 要能壓制 .env),否則讀 repo root `.env`(`utf-8-sig`,never-raise)。

**每個 handler 一進來先 defer**(design R17):`/watch add` 會走到 `WatchlistService` →
`engine.set_watchlist` → ZMQ 往返,可能超過 Discord 的 3 秒回應窗;沒 defer 就會被判逾時
而使用者只看到「應用程式未回應」,即使自選其實已經改成功。
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import os
from pathlib import Path
from typing import Any, Protocol

from copycat.stock_names import load_names
from copycat.stock_watchlist import Watchlist, WatchlistError

logger = logging.getLogger(__name__)

__all__ = [
    "Bot",
    "WatchlistServiceLike",
    "create_bot",
    "handle_add",
    "handle_list",
    "handle_remove",
]

TOKEN_ENV = "DISCORD_BOT_TOKEN"
CHANNEL_ENV = "SIGNALS_DISCORD_CHANNEL_ID"

#: WatchlistError 的 error code → 繁中文案(與前端 `useStockWatchlist.errText` 同一組)
_ERROR_TEXT = {
    "WATCHLIST_FULL": "自選已達 30 檔上限",
    "BAD_CODE": "股號格式不正確",
    "BAD_GROUP": "群組名稱不合法",
}
_NOT_READY = "服務未就緒"
_FALLBACK_ERROR = "儲存失敗"
_UNEXPECTED = "操作失敗,請看伺服器 log"


# ---- env(capital/factory 同語意)----


def _dotenv_values() -> dict[str, str]:
    """repo root .env 逐 key 解析。utf-8-sig:BOM 會讓首 key 靜默失效(真踩過)。
    never-raise:壞檔/權限問題視同無檔 —— Discord 是選配功能,不該擋住 server 起來。"""
    env_file = Path(".env")
    try:
        if not env_file.exists():
            return {}
        text = env_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(".env 讀取失敗,dotenv fallback 視同無檔:%s", e)
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            out[key.strip()] = value.strip()
    return out


_dotenv_cache: dict[str, str] | None = None


def _getenv(name: str) -> str | None:
    """os.environ 有此 key(含空字串)即回傳,不 fallback;僅未設才讀 repo root .env。"""
    if name in os.environ:
        return os.environ[name]
    global _dotenv_cache
    if _dotenv_cache is None:
        _dotenv_cache = _dotenv_values()
    return _dotenv_cache.get(name)


# ---- 純 handler(不碰 discord)----


class WatchlistServiceLike(Protocol):
    """`WatchlistService` 的結構子集(測試注入 fake)。"""

    async def add(self, code: str, group: str | None = None) -> Watchlist: ...

    async def remove(self, code: str) -> Watchlist: ...

    async def current(self) -> Watchlist: ...


class _Response(Protocol):
    async def defer(self, *, thinking: bool = False) -> Any: ...


class _Followup(Protocol):
    async def send(self, content: str) -> Any: ...


class Interaction(Protocol):
    """duck-typed slash interaction:handler 只用得到這兩條路。"""

    @property
    def response(self) -> _Response: ...

    @property
    def followup(self) -> _Followup: ...


_names_cache: dict[str, str] | None = None


def _stock_name(code: str) -> str:
    """版控靜態名稱表(`copycat/stock_names.json`),process 內讀一次;查無回 ""。"""
    global _names_cache
    if _names_cache is None:
        _names_cache = load_names()
    return _names_cache.get(code, "")


def _label(code: str) -> str:
    name = _stock_name(code)
    return f"{code} {name}" if name else code


async def _run(interaction: Interaction, action: Any) -> str:
    """defer → 執行 → followup 的共同骨架;回傳實際送出的文字(測試與 log 都用得到)。

    `except Exception` 是刻意的**指令邊界**:handler 拋出去只會被 discord.py 記在它自己的
    log,使用者停在「思考中」永遠等不到回覆。這裡轉成明確文案 + `logger.exception`。
    """
    await interaction.response.defer(thinking=True)
    try:
        text = await action()
    except WatchlistError as e:
        text = _ERROR_TEXT.get(str(e), _FALLBACK_ERROR)
    except Exception:
        logger.exception("Discord 指令執行失敗")
        text = _UNEXPECTED
    await interaction.followup.send(text)
    return text


async def handle_add(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    code: str,
    group: str | None = None,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        await service.add(code, group)
        suffix = f"(群組:{group})" if group else ""
        return f"已加入自選:{_label(code)}{suffix}"

    return await _run(interaction, action)


async def handle_remove(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    code: str,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        await service.remove(code)
        return f"已從自選移除:{_label(code)}"

    return await _run(interaction, action)


async def handle_list(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        return _format_watchlist(await service.current())

    return await _run(interaction, action)


def _format_watchlist(wl: Watchlist) -> str:
    """依群組列出、未分組殿後;空群組不列(列的是股票,不是群組名冊)。"""
    codes = list(wl["codes"])
    if not codes:
        return "自選清單目前是空的"
    lines = [f"自選 {len(codes)} 檔"]
    grouped: set[str] = set()
    for group in wl["groups"]:
        members = [c for c in group["codes"] if c in codes]
        if not members:
            continue
        grouped.update(members)
        lines.append(f"【{group['name']}】" + "、".join(_label(c) for c in members))
    rest = [c for c in codes if c not in grouped]
    if rest:
        lines.append("【未分組】" + "、".join(_label(c) for c in rest))
    return "\n".join(lines)


# ---- Bot ----


def _log_login_failure(task: asyncio.Task[None]) -> None:
    """背景登入 task 的結束回呼(CC-6):非取消例外 = 登入失敗,當下就要留下真因。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Discord bot 登入失敗,訊號改走 webhook: %s", exc)


class Bot:
    """discord client 的薄殼:起停 + guild 限定指令同步 + 訊號頻道推送。

    型別全 `Any`:discord 是 lazy import,模組層拿不到它的型別(也不該拿)。
    """

    def __init__(
        self,
        *,
        client: Any,
        tree: Any,
        command: Any,
        token: str,
        channel_id: int | None,
        service: WatchlistServiceLike | None,
        hub: Any,
    ) -> None:
        self.client = client
        self.tree = tree
        self.command = command
        self.channel_id = channel_id
        self._token = token
        self._service = service
        self._hub = hub  # 目前只存著:指令不讀 hub,但 lifespan 以它成對建立/收攤
        self._channel: Any = None
        self._task: asyncio.Task[None] | None = None

    def start_bg(self) -> None:
        """背景登入;登入本身可能失敗(token 錯 / 斷網),失敗只影響 Discord 這條路。

        `add_done_callback` 是唯一**當下**說得出真因的地方(CC-6):沒有它,線索只剩第一則
        訊號走 fallback 時的「bot 未送出,改走 webhook」,而那行看不出是 token 錯還是斷網;
        asyncio 的「Task exception was never retrieved」則要等 GC 才印。
        """
        if self._task is None:
            self._task = asyncio.create_task(self.client.start(self._token))
            self._task.add_done_callback(_log_login_failure)

    async def close(self) -> None:
        await self.client.close()
        task, self._task = self._task, None
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                try:
                    await task
                except Exception:
                    # 登入失敗的例外在這裡才被 await 到;往外拋會讓關機序列的後半
                    # (hub.close → worker 收攤 + 盡力落檔)整段跳過(CC-1)
                    logger.exception("Discord bot 背景 task 以例外結束(關機續行)")

    async def on_ready(self) -> None:
        """取訊號頻道 → 對它的 guild 註冊並 sync 指令(guild 限定 = 即時生效且僅該 guild)。

        頻道未設或取不到時只降級(不 raise):訊號推送與指令都停用,server 照常跑。
        """
        if self.channel_id is None:
            logger.warning("%s 未設,Discord 指令不註冊、訊號不推送", CHANNEL_ENV)
            return
        try:
            channel = await self.client.fetch_channel(self.channel_id)
        except Exception:
            logger.exception("Discord 訊號頻道取得失敗:%s", self.channel_id)
            return
        guild = getattr(channel, "guild", None)
        if guild is None:
            logger.warning("Discord 頻道 %s 不屬於任何 guild,指令不註冊", self.channel_id)
            return
        self._channel = channel
        try:
            self.tree.add_command(self.command, guild=guild, override=True)
            await self.tree.sync(guild=guild)
        except Exception:
            # 指令同步失敗不該連帶關掉訊號推送(頻道已取到)
            logger.exception("Discord 指令同步失敗")
            return
        logger.info("Discord bot 就緒:channel=%s", self.channel_id)

    async def send_signal(self, text: str) -> bool:
        """訊號推送出口(hub 的 discord sender);未 ready / 送失敗回 False 讓 hub 走 fallback。"""
        channel = self._channel
        if channel is None:
            return False
        try:
            await channel.send(text)
        except Exception:
            # discord 型別在此拿不到(lazy import),只能寬捕;回 False 由 hub 決定 fallback
            logger.warning("Discord 訊號推送失敗", exc_info=True)
            return False
        return True


def _import_discord() -> tuple[Any, Any]:
    """單獨一層讓測試能決定性模擬 ImportError(不依賴「這台機器剛好沒裝」)。

    走 `importlib.import_module` 而非 `import discord`(capital/com.py 同慣例):選配
    依賴在沒裝它的環境用靜態 import 會讓 pyright 整檔紅,而唯一的消音手段是 ignore 註解。
    """
    return importlib.import_module("discord"), importlib.import_module("discord.app_commands")


def _channel_id() -> int | None:
    raw = (_getenv(CHANNEL_ENV) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r 不是整數 → 視為未設", CHANNEL_ENV, raw)
        return None


def create_bot(service: WatchlistServiceLike | None, hub: Any) -> Bot | None:
    """組裝 bot;token 未設或 extras 未裝 → None(功能停用,server 照常)。"""
    token = (_getenv(TOKEN_ENV) or "").strip()
    if not token:
        logger.info("%s 未設,Discord bot 不啟用", TOKEN_ENV)
        return None
    try:
        discord, app_commands = _import_discord()
    except ImportError:
        logger.info("discord.py 未安裝(extras [discord]),Discord bot 不啟用")
        return None

    client = discord.Client(intents=discord.Intents.default())
    tree = app_commands.CommandTree(client)
    group = app_commands.Group(name="watch", description="自選股管理")

    @group.command(name="add", description="加入自選")
    @app_commands.describe(code="股號(例:2330)", group="群組名稱(選填)")
    async def _add(interaction: Any, code: str, group: str | None = None) -> None:
        await handle_add(service, interaction, code, group)

    @group.command(name="remove", description="移出自選")
    @app_commands.describe(code="股號(例:2330)")
    async def _remove(interaction: Any, code: str) -> None:
        await handle_remove(service, interaction, code)

    @group.command(name="list", description="列出自選")
    async def _list(interaction: Any) -> None:
        await handle_list(service, interaction)

    bot = Bot(
        client=client,
        tree=tree,
        command=group,
        token=token,
        channel_id=_channel_id(),
        service=service,
        hub=hub,
    )

    @client.event
    async def on_ready() -> None:
        await bot.on_ready()

    return bot
