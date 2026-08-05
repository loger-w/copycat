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
from copycat.stock_watchlist import UNGROUPED_NAME, Watchlist, WatchlistError

logger = logging.getLogger(__name__)

__all__ = [
    "Bot",
    "WatchlistServiceLike",
    "create_bot",
    "group_choices",
    "handle_add",
    "handle_group_add",
    "handle_group_remove",
    "handle_group_rename",
    "handle_groups",
    "handle_list",
    "handle_remove",
    "handle_ungroup",
]

TOKEN_ENV = "DISCORD_BOT_TOKEN"
CHANNEL_ENV = "SIGNALS_DISCORD_CHANNEL_ID"

#: WatchlistError 的 error code → 繁中文案(與前端 `useStockWatchlist.errText` 同一組)
_ERROR_TEXT = {
    "WATCHLIST_FULL": "自選已達 30 檔上限",
    "BAD_CODE": "股號格式不正確",
    "BAD_GROUP": "群組名稱不合法",
    "GROUP_NOT_FOUND": "找不到該群組",
}
_NOT_READY = "服務未就緒"
_FALLBACK_ERROR = "儲存失敗"
_UNEXPECTED = "操作失敗,請看伺服器 log"
#: 「未分組」是 `_format_groups` 的**衍生桶**不是群組:對它做群組操作沒有對象。
#: 攔在 handler 而不是讓 service 回 `GROUP_NOT_FOUND` —— 後者要留給「真的打錯名字」。
_RESERVED_BLOCKED = f"「{UNGROUPED_NAME}」不是群組,無法操作"
_UNKNOWN_CODE_HINT = "(查無此檔名稱,請確認代碼)"

#: autocomplete 的取值上限。Discord 的 autocomplete 沒有 defer,3 秒不回就整份丟掉;
#: 而 `service.current()` 與寫入共用同一把鎖,鎖被 `_commit` 的 ZMQ 往返佔住時只能放手。
_AUTOCOMPLETE_TIMEOUT = 1.0
#: Discord `Choice` 的 name / value 各 100 字上限;單一超長項會讓**整份**回應被拒收。
_CHOICE_NAME_LIMIT = 100
_CHOICE_LIMIT = 25


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
    """`WatchlistService` 的結構子集(測試注入 fake)。

    寫入類方法一律回 `(watchlist, changed)`:handler 要靠 `changed` 分「已加入」與
    「已在自選(無變更)」兩種文案,而那個判斷的唯一事實點在 service 的落檔比對。
    """

    async def add(self, code: str, group: str | None = None) -> tuple[Watchlist, bool]: ...

    async def remove(self, code: str) -> tuple[Watchlist, bool]: ...

    async def current(self) -> Watchlist: ...

    async def create_group(self, name: str) -> tuple[Watchlist, bool]: ...

    async def delete_group(self, name: str) -> tuple[Watchlist, bool]: ...

    async def rename_group(self, old: str, new: str) -> tuple[Watchlist, bool]: ...

    async def ungroup(self, code: str, group: str) -> tuple[Watchlist, bool]: ...


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
    """SC-5:名稱查不到只**提醒**不擋 —— 靜態名稱表落後於新上市/改名是常態,
    擋下去會讓合法股號加不進來,而使用者最需要的正是「剛上市那檔」。"""

    async def action() -> str:
        if service is None:
            return _NOT_READY
        _, changed = await service.add(code, group)
        hint = "" if _stock_name(code) else _UNKNOWN_CODE_HINT
        if not changed:
            return f"已在自選:{_label(code)}(無變更){hint}"
        suffix = f"(群組:{group})" if group else ""
        return f"已加入自選:{_label(code)}{suffix}{hint}"

    return await _run(interaction, action)


async def handle_remove(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    code: str,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        _, changed = await service.remove(code)
        if not changed:
            return f"不在自選:{_label(code)}"
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
        lines.append(f"【{UNGROUPED_NAME}】" + "、".join(_label(c) for c in rest))
    return "\n".join(lines)


async def handle_groups(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        return _format_groups(await service.current())

    return await _run(interaction, action)


def _format_groups(wl: Watchlist) -> str:
    """群組**名冊**(SC-1)—— 與 `_format_watchlist` 的差別是這裡列的是群組本身,
    所以 0 檔群組必須出現:剛建好還沒放東西的群組不能看起來像建立失敗。

    「未分組」標注「衍生,非群組」是為了讓它跟真群組在視覺上可分 —— 它只是
    「不在任何群組的股票」的計數,對它下 `/watch group remove` 沒有對象可刪。
    """
    codes = list(wl["codes"])
    groups = wl["groups"]
    grouped = {c for g in groups for c in g["codes"] if c in codes}
    rest = len([c for c in codes if c not in grouped])
    if not groups:
        return "尚無群組" if not codes else f"尚無群組;{UNGROUPED_NAME} {rest} 檔"
    lines = [f"群組 {len(groups)} 個"]
    for group in groups:
        members = [c for c in group["codes"] if c in codes]
        lines.append(f"【{group['name']}】{len(members)} 檔")
    if rest:
        lines.append(f"{UNGROUPED_NAME} {rest} 檔(衍生,非群組)")
    return "\n".join(lines)


async def handle_group_add(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    name: str,
) -> str:
    """保留名**不在此攔** —— 群組名的合法性只有 `stock_watchlist.normalize` 一份定義,
    handler 再判一次就成了第二份會漂移的規則(建立保留名的正確答案是「名稱不合法」)。"""

    async def action() -> str:
        if service is None:
            return _NOT_READY
        _, changed = await service.create_group(name)
        if not changed:
            return f"群組已存在:{name}"
        return f"已建立群組:{name}"

    return await _run(interaction, action)


async def handle_group_remove(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    name: str,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        if name.strip() == UNGROUPED_NAME:
            return _RESERVED_BLOCKED
        await service.delete_group(name)
        return f"已刪除群組:{name}(成員移至{UNGROUPED_NAME})"

    return await _run(interaction, action)


async def handle_group_rename(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    old: str,
    new: str,
) -> str:
    """只攔 `old`(操作對象):`new` 是保留名時語意是「取的新名不合法」,交 service →
    normalize → `BAD_GROUP`,兩種錯誤各自說得清楚(design R2)。"""

    async def action() -> str:
        if service is None:
            return _NOT_READY
        if old.strip() == UNGROUPED_NAME:
            return _RESERVED_BLOCKED
        _, changed = await service.rename_group(old, new)
        if not changed:
            return f"名稱未變:{new}"
        return f"已改名:{old} → {new}"

    return await _run(interaction, action)


async def handle_ungroup(
    service: WatchlistServiceLike | None,
    interaction: Interaction,
    code: str,
    group: str,
) -> str:
    async def action() -> str:
        if service is None:
            return _NOT_READY
        if group.strip() == UNGROUPED_NAME:
            return _RESERVED_BLOCKED
        _, changed = await service.ungroup(code, group)
        if not changed:
            return f"{_label(code)} 不在群組 {group}"
        return f"已自群組 {group} 移出:{_label(code)}(仍在自選)"

    return await _run(interaction, action)


async def group_choices(service: WatchlistServiceLike | None, current: str) -> list[str]:
    """`group` / `name` / `old` 參數的 autocomplete 選項(SC-4)。

    **三態一律回空清單**(service 未就緒 / 逾時 / 例外):autocomplete 不能 defer,
    Discord 只給 3 秒;而這條路與寫入共用 `WatchlistService` 的單鎖,寫入正卡在 ZMQ
    往返時堆積等鎖 task 只會讓後面每一次輸入都更慢。回空 = 使用者仍可手打群組名。

    子字串(非前綴)過濾:中文群組名沒有前綴語意,打「主力」要找得到「波段主力」。
    """
    if service is None:
        return []
    try:
        wl = await asyncio.wait_for(service.current(), _AUTOCOMPLETE_TIMEOUT)
    except TimeoutError:
        logger.warning("群組 autocomplete 逾時(%.1fs),回空選單", _AUTOCOMPLETE_TIMEOUT)
        return []
    except Exception:
        # 指令邊界同理:這裡拋出去只會讓使用者看到選單卡住,且真因埋在 discord.py 的 log
        logger.exception("群組 autocomplete 取得自選失敗")
        return []
    needle = current.strip()
    out: list[str] = []
    for group in wl["groups"]:
        name = group["name"]
        if len(name) > _CHOICE_NAME_LIMIT:
            logger.warning(
                "群組名稱超過 Discord Choice 的 %d 字上限,autocomplete 略過:%.20s…",
                _CHOICE_NAME_LIMIT,
                name,
            )
            continue
        if needle and needle not in name:
            continue
        out.append(name)
        if len(out) >= _CHOICE_LIMIT:
            break
    return out


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

    client = discord.Client(
        # 群組名是自由文字且會原樣回填訊息(`已建立群組:@everyone`)—— 沒有這個
        # 設定,任何人都能透過 `/watch group add` 把 bot 變成 mention 擴音器。
        intents=discord.Intents.default(),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    tree = app_commands.CommandTree(client)
    # 變數名 `watch` / `group_cmd` 是刻意的:叫 `group` 會遮蔽 `_add(..., group=...)` 參數,
    # 且子群組一旦叫 `group`,既有的 `@group.command` 會**靜默**改掛到子群組底下。
    watch = app_commands.Group(name="watch", description="自選股管理")
    group_cmd = app_commands.Group(name="group", description="群組管理", parent=watch)

    async def _group_ac(interaction: Any, current: str) -> list[Any]:
        return [
            app_commands.Choice(name=n, value=n) for n in await group_choices(service, current)
        ]

    @watch.command(name="add", description="加入自選")
    @app_commands.describe(code="股號(例:2330)", group="群組名稱(選填)")
    @app_commands.autocomplete(group=_group_ac)
    async def _add(interaction: Any, code: str, group: str | None = None) -> None:
        await handle_add(service, interaction, code, group)

    @watch.command(name="remove", description="移出自選")
    @app_commands.describe(code="股號(例:2330)")
    async def _remove(interaction: Any, code: str) -> None:
        await handle_remove(service, interaction, code)

    @watch.command(name="list", description="列出自選")
    async def _list(interaction: Any) -> None:
        await handle_list(service, interaction)

    @watch.command(name="groups", description="列出群組")
    async def _groups(interaction: Any) -> None:
        await handle_groups(service, interaction)

    @watch.command(name="ungroup", description="自群組移出(仍留在自選)")
    @app_commands.describe(code="股號(例:2330)", group="群組名稱")
    @app_commands.autocomplete(group=_group_ac)
    async def _ungroup(interaction: Any, code: str, group: str) -> None:
        await handle_ungroup(service, interaction, code, group)

    @group_cmd.command(name="add", description="建立群組")
    @app_commands.describe(name="群組名稱")
    async def _group_add(interaction: Any, name: str) -> None:
        await handle_group_add(service, interaction, name)

    @group_cmd.command(name="remove", description="刪除群組(成員移至未分組)")
    @app_commands.describe(name="群組名稱")
    @app_commands.autocomplete(name=_group_ac)
    async def _group_remove(interaction: Any, name: str) -> None:
        await handle_group_remove(service, interaction, name)

    @group_cmd.command(name="rename", description="群組改名")
    @app_commands.describe(old="原群組名稱", new="新群組名稱")
    @app_commands.autocomplete(old=_group_ac)
    async def _group_rename(interaction: Any, old: str, new: str) -> None:
        await handle_group_rename(service, interaction, old, new)

    bot = Bot(
        client=client,
        tree=tree,
        command=watch,
        token=token,
        channel_id=_channel_id(),
        service=service,
        hub=hub,
    )

    @client.event
    async def on_ready() -> None:
        await bot.on_ready()

    return bot
