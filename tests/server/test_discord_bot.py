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
    group_choices,
    handle_add,
    handle_group_add,
    handle_group_remove,
    handle_group_rename,
    handle_groups,
    handle_list,
    handle_remove,
    handle_ungroup,
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
    """`changed` 由建構參數控制 —— no-op 文案(「已在自選」/「名稱未變」)測的就是
    service 回 False 那條路,fake 不自己推導「有沒有變」才不會把待測邏輯搬進 fake。"""

    def __init__(
        self,
        wl: Watchlist | None = None,
        error: Exception | None = None,
        changed: bool = True,
    ) -> None:
        self.wl: Watchlist = wl if wl is not None else {"codes": [], "groups": []}
        self.error = error
        self.changed = changed
        self.added: list[tuple[str, str | None]] = []
        self.removed: list[str] = []
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.renamed: list[tuple[str, str]] = []
        self.ungrouped: list[tuple[str, str]] = []

    async def add(self, code: str, group: str | None = None) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.added.append((code, group))
        return self.wl, self.changed

    async def remove(self, code: str) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.removed.append(code)
        return self.wl, self.changed

    async def current(self) -> Watchlist:
        if self.error is not None:
            raise self.error
        return self.wl

    async def create_group(self, name: str) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.created.append(name)
        return self.wl, self.changed

    async def delete_group(self, name: str) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.deleted.append(name)
        return self.wl, self.changed

    async def rename_group(self, old: str, new: str) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.renamed.append((old, new))
        return self.wl, self.changed

    async def ungroup(self, code: str, group: str) -> tuple[Watchlist, bool]:
        if self.error is not None:
            raise self.error
        self.ungrouped.append((code, group))
        return self.wl, self.changed


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
            ("WATCHLIST_FULL", "自選已達 150 檔上限"),
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

    async def test_noop_text_when_service_reports_unchanged(self) -> None:
        """SC-7:文案的唯一事實點是 service 的落檔比對,不是 handler 自己猜。"""
        it = FakeInteraction()

        await handle_add(FakeService(changed=False), it, "2330")

        assert it.sent == "已在自選:2330 台積電(無變更)"

    async def test_changed_with_group_text(self) -> None:
        it = FakeInteraction()

        await handle_add(FakeService(), it, "2330", "主力")

        assert it.sent == "已加入自選:2330 台積電(群組:主力)"

    async def test_unknown_code_appends_warning_suffix(self) -> None:
        """SC-5:軟白名單 —— 仍照加,但提醒可能打錯代碼。"""
        it = FakeInteraction()

        await handle_add(FakeService(), it, "9999")

        assert it.sent == "已加入自選:9999(查無此檔名稱,請確認代碼)"

    async def test_noop_unknown_code_keeps_both_clauses(self) -> None:
        """no-op 與「查無名稱」是兩件獨立的事,同時成立時兩句都要在(逐字鎖)。"""
        it = FakeInteraction()

        await handle_add(FakeService(changed=False), it, "9999")

        assert it.sent == "已在自選:9999(無變更)(查無此檔名稱,請確認代碼)"

    async def test_noop_with_group_omits_group_suffix(self) -> None:
        """no-op 代表「群組關係也沒動」—— 印出「(群組:X)」會讓人以為剛剛入了群。"""
        it = FakeInteraction()

        await handle_add(FakeService(changed=False), it, "2330", "主力")

        assert it.sent == "已在自選:2330 台積電(無變更)"

    async def test_group_name_is_stripped_before_service_and_reply(self) -> None:
        """v3 A3:判定 / service 呼叫 / 回覆三者同基準 —— 否則回覆印的是使用者手滑打的
        「主力 」,而實際入的是「主力」,兩邊對不上。"""
        service = FakeService()
        it = FakeInteraction()

        await handle_add(service, it, "2330", " 主力 ")

        assert service.added == [("2330", "主力")]
        assert it.sent == "已加入自選:2330 台積電(群組:主力)"

    async def test_watchlist_unavailable_text(self) -> None:
        service = FakeService(error=WatchlistError("WATCHLIST_UNAVAILABLE"))
        it = FakeInteraction()

        await handle_add(service, it, "2330")

        assert it.sent == "自選檔目前不可用,請自前端存檔修復"


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

    async def test_noop_text_when_service_reports_unchanged(self) -> None:
        it = FakeInteraction()

        await handle_remove(FakeService(changed=False), it, "2330")

        assert it.sent == "不在自選:2330 台積電"


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


_RESERVED_BLOCKED = "「未分組」不是群組,無法操作"


class TestGroupsCommand:
    """SC-1:`/watch groups` 列的是**群組名冊**(含 0 檔群組),不是股票清單。"""

    async def test_lists_groups_with_counts_and_ungrouped(self) -> None:
        service = FakeService(
            {
                "codes": ["2330", "5483", "2317"],
                "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
            }
        )
        it = FakeInteraction()

        await handle_groups(service, it)

        assert it.order == ["defer", "send"]
        assert it.sent.splitlines() == [
            "群組 1 個",
            "【主力】2 檔",
            "未分組 1 檔(衍生,非群組)",
        ]

    async def test_no_ungrouped_line_when_all_grouped(self) -> None:
        service = FakeService(
            {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        )
        it = FakeInteraction()

        await handle_groups(service, it)

        assert "未分組" not in it.sent

    async def test_empty_group_is_still_listed(self) -> None:
        """SC-1 的核心:空群組是使用者建的東西,不能因為沒成員就消失。"""
        service = FakeService(
            {
                "codes": ["2330"],
                "groups": [{"name": "主力", "codes": ["2330"]}, {"name": "觀察", "codes": []}],
            }
        )
        it = FakeInteraction()

        await handle_groups(service, it)

        assert it.sent.splitlines() == ["群組 2 個", "【主力】1 檔", "【觀察】0 檔"]

    async def test_zero_groups_with_empty_watchlist(self) -> None:
        it = FakeInteraction()

        await handle_groups(FakeService(), it)

        assert it.sent == "尚無群組"

    async def test_zero_groups_with_codes(self) -> None:
        service = FakeService({"codes": ["2330", "2317"], "groups": []})
        it = FakeInteraction()

        await handle_groups(service, it)

        assert it.sent == "尚無群組;未分組 2 檔"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_groups(None, it)

        assert it.sent == "服務未就緒"


class TestGroupAddCommand:
    async def test_creates(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_add(service, it, "主力")

        assert service.created == ["主力"]
        assert it.order == ["defer", "send"]
        assert it.sent == "已建立群組:主力"

    async def test_duplicate_is_noop_text(self) -> None:
        it = FakeInteraction()

        await handle_group_add(FakeService(changed=False), it, "主力")

        assert it.sent == "群組已存在:主力"

    async def test_reserved_name_maps_to_bad_group(self) -> None:
        """建立保留名**不在 handler 攔** —— 合法性只有 normalize 一份定義(SC-6)。"""
        service = FakeService(error=WatchlistError("BAD_GROUP"))
        it = FakeInteraction()

        await handle_group_add(service, it, "未分組")

        assert it.sent == "群組名稱不合法"

    async def test_name_is_stripped_before_service_and_reply(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_add(service, it, " 主力 ")

        assert service.created == ["主力"]
        assert it.sent == "已建立群組:主力"

    async def test_watchlist_unavailable_text(self) -> None:
        """v3 A1:壞檔下 create_group 零寫並拋 —— 文案要指出自癒路徑(前端存檔)。"""
        service = FakeService(error=WatchlistError("WATCHLIST_UNAVAILABLE"))
        it = FakeInteraction()

        await handle_group_add(service, it, "主力")

        assert it.sent == "自選檔目前不可用,請自前端存檔修復"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_group_add(None, it, "主力")

        assert it.sent == "服務未就緒"


class TestGroupRemoveCommand:
    async def test_ok(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_remove(service, it, "主力")

        assert service.deleted == ["主力"]
        assert it.sent == "已刪除群組:主力(成員移至未分組)"

    async def test_missing_group_text(self) -> None:
        service = FakeService(error=WatchlistError("GROUP_NOT_FOUND"))
        it = FakeInteraction()

        await handle_group_remove(service, it, "不存在")

        assert it.sent == "找不到該群組"

    async def test_reserved_name_blocked_without_calling_service(self) -> None:
        """「未分組」是衍生桶不是群組:攔在 handler,GROUP_NOT_FOUND 留給真缺席。"""
        service = FakeService()
        it = FakeInteraction()

        await handle_group_remove(service, it, " 未分組 ")

        assert it.sent == _RESERVED_BLOCKED
        assert service.deleted == []

    async def test_name_is_stripped_before_service_and_reply(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_remove(service, it, " 主力 ")

        assert service.deleted == ["主力"]
        assert it.sent == "已刪除群組:主力(成員移至未分組)"

    async def test_watchlist_unavailable_text(self) -> None:
        service = FakeService(error=WatchlistError("WATCHLIST_UNAVAILABLE"))
        it = FakeInteraction()

        await handle_group_remove(service, it, "主力")

        assert it.sent == "自選檔目前不可用,請自前端存檔修復"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_group_remove(None, it, "主力")

        assert it.sent == "服務未就緒"


class TestGroupRenameCommand:
    async def test_ok(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_rename(service, it, "主力", "核心")

        assert service.renamed == [("主力", "核心")]
        assert it.sent == "已改名:主力 → 核心"

    async def test_same_name_is_noop_text(self) -> None:
        it = FakeInteraction()

        await handle_group_rename(FakeService(changed=False), it, "主力", "主力")

        assert it.sent == "名稱未變:主力"

    async def test_missing_group_text(self) -> None:
        service = FakeService(error=WatchlistError("GROUP_NOT_FOUND"))
        it = FakeInteraction()

        await handle_group_rename(service, it, "不存在", "核心")

        assert it.sent == "找不到該群組"

    async def test_reserved_old_blocked_without_calling_service(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_rename(service, it, "未分組", "核心")

        assert it.sent == _RESERVED_BLOCKED
        assert service.renamed == []

    async def test_reserved_new_falls_through_to_bad_group(self) -> None:
        """取新名為保留名是「名稱不合法」不是「不是群組」—— 語意不同,不共用文案(R2)。"""
        service = FakeService(error=WatchlistError("BAD_GROUP"))
        it = FakeInteraction()

        await handle_group_rename(service, it, "主力", "未分組")

        assert it.sent == "群組名稱不合法"

    async def test_names_are_stripped_before_service_and_reply(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_group_rename(service, it, " 主力 ", " 核心 ")

        assert service.renamed == [("主力", "核心")]
        assert it.sent == "已改名:主力 → 核心"

    async def test_noop_text_uses_stripped_new_name(self) -> None:
        """padding-only 改名是 no-op:文案印 strip 後的新名(印原字串會出現詭異空白)。"""
        service = FakeService(changed=False)
        it = FakeInteraction()

        await handle_group_rename(service, it, " 主力 ", "主力")

        assert service.renamed == [("主力", "主力")]
        assert it.sent == "名稱未變:主力"

    async def test_watchlist_unavailable_text(self) -> None:
        service = FakeService(error=WatchlistError("WATCHLIST_UNAVAILABLE"))
        it = FakeInteraction()

        await handle_group_rename(service, it, "主力", "核心")

        assert it.sent == "自選檔目前不可用,請自前端存檔修復"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_group_rename(None, it, "主力", "核心")

        assert it.sent == "服務未就緒"


class TestUngroupCommand:
    async def test_ok(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_ungroup(service, it, "2330", "主力")

        assert service.ungrouped == [("2330", "主力")]
        assert it.order == ["defer", "send"]
        assert it.sent == "已自群組 主力 移出:2330 台積電(仍在自選)"

    async def test_noop_when_not_member(self) -> None:
        it = FakeInteraction()

        await handle_ungroup(FakeService(changed=False), it, "2330", "主力")

        assert it.sent == "2330 台積電 不在群組 主力"

    async def test_missing_group_text(self) -> None:
        service = FakeService(error=WatchlistError("GROUP_NOT_FOUND"))
        it = FakeInteraction()

        await handle_ungroup(service, it, "2330", "不存在")

        assert it.sent == "找不到該群組"

    async def test_reserved_group_blocked_without_calling_service(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_ungroup(service, it, "2330", "未分組")

        assert it.sent == _RESERVED_BLOCKED
        assert service.ungrouped == []

    async def test_group_is_stripped_before_service_and_reply(self) -> None:
        service = FakeService()
        it = FakeInteraction()

        await handle_ungroup(service, it, "2330", " 主力 ")

        assert service.ungrouped == [("2330", "主力")]
        assert it.sent == "已自群組 主力 移出:2330 台積電(仍在自選)"

    async def test_noop_text_uses_stripped_group(self) -> None:
        it = FakeInteraction()

        await handle_ungroup(FakeService(changed=False), it, "2330", " 主力 ")

        assert it.sent == "2330 台積電 不在群組 主力"

    async def test_watchlist_unavailable_text(self) -> None:
        service = FakeService(error=WatchlistError("WATCHLIST_UNAVAILABLE"))
        it = FakeInteraction()

        await handle_ungroup(service, it, "2330", "主力")

        assert it.sent == "自選檔目前不可用,請自前端存檔修復"

    async def test_service_none(self) -> None:
        it = FakeInteraction()

        await handle_ungroup(None, it, "2330", "主力")

        assert it.sent == "服務未就緒"


class _RaisingFollowup:
    """`followup.send` 拋 —— Discord 側 5xx / 訊息被拒(超長、權限)都是這個形。"""

    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self._log = log

    async def send(self, content: str) -> None:
        self._log.append(("send", content))
        raise RuntimeError("discord 503")


class RaisingInteraction(FakeInteraction):
    def __init__(self) -> None:
        super().__init__()
        self.followup = _RaisingFollowup(self.calls)  # type: ignore[assignment]


class TestReplyGuards:
    """v3 A2:`_run` 是所有指令的唯一出口,它拋出去 = 使用者永遠停在「思考中」。"""

    async def test_over_long_reply_is_truncated(self) -> None:
        """Discord 訊息上限 2000 字;群組名是自由文字,`/watch groups` 可以輕易超過。
        超長訊息會被 Discord 直接拒收 → 已 defer 的互動永遠等不到回覆。"""
        service = FakeService({"codes": [], "groups": [{"name": "長" * 3000, "codes": []}]})
        it = FakeInteraction()

        text = await handle_groups(service, it)

        assert text.endswith("…(截斷)")
        assert len(text) == 1900 + len("…(截斷)")
        assert it.sent == text  # 回傳值 = 實際送出的那份

    async def test_normal_reply_is_untouched(self) -> None:
        it = FakeInteraction()

        text = await handle_groups(FakeService(), it)

        assert text == "尚無群組"

    async def test_send_failure_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """送出失敗往外拋只會被 discord.py 記在它自己的 log(且指令 callback 沒有其他
        接手處);轉成 `logger.exception` 才留得下真因。"""
        it = RaisingInteraction()

        with caplog.at_level(logging.ERROR, logger="copycat.server.discord_bot"):
            text = await handle_add(FakeService(), it, "2330")

        assert text == "已加入自選:2330 台積電"
        assert any("回覆送出失敗" in r.getMessage() for r in caplog.records)


class _HangingService(FakeService):
    """`current()` 永不返回 —— 模擬寫入持鎖(TC4 往返)期間的 autocomplete。"""

    async def current(self) -> Watchlist:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class TestGroupChoices:
    def _service(self, names: list[str]) -> FakeService:
        return FakeService(
            {"codes": [], "groups": [{"name": n, "codes": []} for n in names]}
        )

    async def test_returns_group_names(self) -> None:
        assert await group_choices(self._service(["主力", "觀察"]), "") == ["主力", "觀察"]

    async def test_substring_filter(self) -> None:
        """子字串(非前綴):中文群組名沒有前綴語意(design R8 amendment)。"""
        service = self._service(["主力股", "觀察名單", "波段主力"])

        assert await group_choices(service, "主力") == ["主力股", "波段主力"]

    async def test_none_service_returns_empty(self) -> None:
        assert await group_choices(None, "") == []

    async def test_timeout_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """3 秒硬窗 + 與寫入共用單鎖:等不到就放手回空,不可堆積等鎖 task。"""
        monkeypatch.setattr(discord_bot, "_AUTOCOMPLETE_TIMEOUT", 0.01)

        assert await group_choices(_HangingService(), "") == []

    async def test_error_returns_empty(self) -> None:
        assert await group_choices(FakeService(error=RuntimeError("boom")), "") == []

    async def test_long_name_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Choice name 上限 100:單一超長項會讓整份回應被 Discord 拒收(R7)。"""
        service = self._service(["x" * 101, "主力"])

        with caplog.at_level(logging.WARNING, logger="copycat.server.discord_bot"):
            result = await group_choices(service, "")

        assert result == ["主力"]
        assert any("100" in r.getMessage() for r in caplog.records)

    async def test_filtered_out_long_name_is_not_warned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """warning 要在 needle 過濾**之後** —— autocomplete 每一鍵都呼叫一次,擺在
        過濾前會讓一個超長群組名把 log 洗成每按一鍵一行。"""
        service = self._service(["x" * 101, "主力"])

        with caplog.at_level(logging.WARNING, logger="copycat.server.discord_bot"):
            result = await group_choices(service, "主力")

        assert result == ["主力"]
        assert caplog.records == []

    async def test_capped_at_25(self) -> None:
        service = self._service([f"g{i}" for i in range(30)])

        assert len(await group_choices(service, "")) == 25


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
    def _bot(self, monkeypatch: pytest.MonkeyPatch) -> Bot:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
        monkeypatch.setenv("SIGNALS_DISCORD_CHANNEL_ID", "42")
        bot = create_bot(FakeService(), None)
        assert bot is not None
        return bot

    def _leaves(self, bot: Bot) -> dict[str, Any]:
        app_commands = importlib.import_module("discord.app_commands")
        return {
            c.qualified_name: c
            for c in bot.command.walk_commands()
            if isinstance(c, app_commands.Command)
        }

    def test_create_bot_builds_client_and_tree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        discord = importlib.import_module("discord")

        bot = self._bot(monkeypatch)

        assert isinstance(bot.client, discord.Client)
        assert bot.channel_id == 42

    def test_command_tree_leaf_qualified_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R7:子群組變數名若叫 `group`,既有 `@group.command` 會靜默改掛到子群組 ——
        數量對不上不夠,要鎖**完整路徑**才抓得到掛錯層。"""
        bot = self._bot(monkeypatch)

        assert set(self._leaves(bot)) == {
            "watch add",
            "watch remove",
            "watch list",
            "watch groups",
            "watch ungroup",
            "watch group add",
            "watch group remove",
            "watch group rename",
        }

    @pytest.mark.parametrize(
        ("qualified", "param"),
        [
            ("watch add", "group"),
            ("watch ungroup", "group"),
            ("watch group remove", "name"),
            ("watch group rename", "old"),
        ],
    )
    def test_autocomplete_wired(
        self, monkeypatch: pytest.MonkeyPatch, qualified: str, param: str
    ) -> None:
        leaf = self._leaves(self._bot(monkeypatch))[qualified]

        parameter = leaf.get_parameter(param)

        assert parameter is not None
        assert parameter.autocomplete is True

    def test_client_suppresses_mentions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """群組名是自由文字且會原樣回填訊息:`/watch group add @everyone` 不得真 ping(R7)。

        逐欄比對而非比物件:`AllowedMentions` 沒有 `__eq__`,直接 `==` 恆為 False。
        """
        allowed = self._bot(monkeypatch).client.allowed_mentions

        assert (allowed.everyone, allowed.users, allowed.roles) == (False, False, False)
