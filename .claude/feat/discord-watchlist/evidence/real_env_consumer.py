"""Phase 6 真實環境 consumer:真 WatchlistService + 真檔案落地,驅動全部 /watch handler。

worktree 直跑腳本必釘 sys.path(否則 editable install 會 import 主 tree 的 copycat)。
fake 只有兩個:engine(不碰 ZMQ — 夜盤紀律)與 interaction(Discord 網路層)。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist")

import asyncio
import json
import tempfile
from pathlib import Path

from copycat.server import discord_bot as db
from copycat.server.watchlist_service import WatchlistService

assert db.__file__.startswith(r"C:\side-project\copycat\.claude\worktrees"), db.__file__


class Engine:
    def __init__(self) -> None:
        self.set_calls: list[list[str]] = []
        self.published: list[dict] = []

    async def set_watchlist(self, codes: list[str]) -> None:
        self.set_calls.append(list(codes))

    def _publish(self, msg: dict) -> None:
        self.published.append(msg)


class Ix:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.response = self
        self.followup = self

    async def defer(self, *, thinking: bool = False) -> None: ...

    async def send(self, content: str) -> None:
        self.sent.append(content)


async def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "watchlist.json"
    engine = Engine()
    svc = WatchlistService(path, engine)
    ix = Ix()
    out: list[str] = []

    async def run(tag: str, coro) -> None:
        text = await coro
        out.append(f"[{tag}] {text!r}")

    # --- happy path(SC-2/1/3/7 全鏈)---
    await run("add+autogroup", db.handle_add(svc, ix, "2330", "電子"))
    await run("add-2317", db.handle_add(svc, ix, "2317", "電子"))
    await run("group-add", db.handle_group_add(svc, ix, "觀察"))
    await run("groups(SC-1 空群組可見)", db.handle_groups(svc, ix))
    await run("ungroup(SC-3)", db.handle_ungroup(svc, ix, "2317", "電子"))
    await run("groups(未分組衍生標注)", db.handle_groups(svc, ix))
    await run("rename", db.handle_group_rename(svc, ix, "電子", "半導體"))
    await run("autocomplete", asyncio.sleep(0) or db.group_choices(svc, ""))
    out[-1] = f"[autocomplete] {await db.group_choices(svc, '')!r}"
    await run("remove", db.handle_remove(svc, ix, "2330"))
    await run("list(既有功能 regression)", db.handle_list(svc, ix))

    # --- edge 1:保留名 ---
    await run("edge 保留名 group-add(SC-6)", db.handle_group_add(svc, ix, "未分組"))
    await run("edge 保留名 ungroup 攔截", db.handle_ungroup(svc, ix, "2317", "未分組"))
    # --- edge 2:查無 / no-op 文案(SC-5/7)---
    await run("edge 查無名稱警告(SC-5)", db.handle_add(svc, ix, "9999", None))
    await run("edge add no-op(SC-7)", db.handle_add(svc, ix, "9999", None))
    await run("edge GROUP_NOT_FOUND", db.handle_group_remove(svc, ix, "不存在的群組"))
    # --- edge 3:壞檔零寫(review A1/B1)---
    before = path.read_text(encoding="utf-8")
    path.write_text(json.dumps({"codes": ["2317", "bad code"]}), encoding="utf-8")
    broken = path.read_text(encoding="utf-8")
    calls_before = len(engine.set_calls)
    await run("edge 壞檔 create_group 零寫", db.handle_group_add(svc, ix, "觀察2"))
    assert path.read_text(encoding="utf-8") == broken, "壞檔被覆寫!"
    assert len(engine.set_calls) == calls_before, "壞檔仍觸發 set_watchlist!"
    out.append("[edge 壞檔] 檔逐字未變 + set_watchlist 零呼叫 ✓")
    path.write_text(before, encoding="utf-8")

    # --- regression 2:apply 同內容零寫早退(前端 PUT 語意未動)---
    calls_before = len(engine.set_calls)
    current = await svc.current()
    await svc.apply(current)
    assert len(engine.set_calls) == calls_before, "同內容 apply 竟落檔!"
    out.append("[regression apply 零寫早退] set_watchlist 零呼叫 ✓")

    out.append(f"[最終檔] {path.read_text(encoding='utf-8')}")
    out.append(f"[engine.set_calls] {engine.set_calls!r}")
    print("\n".join(out))


asyncio.run(main())
