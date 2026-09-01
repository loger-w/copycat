"""WatchlistService 行為合約(design §6 — SC-8 後端半 / SC-11)。

三個入口(前端 PUT / Discord `/watch add` / `/watch remove`)共用同一把 lock 與
同一條「落檔 → set_watchlist → 廣播」序列;engine 用 fake 記錄呼叫。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from copycat.server.watchlist_service import WatchlistService
from copycat.stock_watchlist import (
    UNGROUPED_NAME,
    WATCHLIST_LIMIT,
    Watchlist,
    WatchlistError,
    load_watchlist,
)


class _FakeEngine:
    """記錄 set_watchlist / _publish;delay 用來製造並發窗。"""

    def __init__(self, delay: float = 0.0) -> None:
        self.set_calls: list[list[str]] = []
        self.seqs: list[int | None] = []
        self.published: list[dict] = []
        self._delay = delay
        #: 第一次進到 set_watchlist(= 慢訂閱窗的起點;X-3 的並發測試靠它定錨)
        self.entered = asyncio.Event()

    async def set_watchlist(self, codes: list[str], *, seq: int | None = None) -> None:
        self.entered.set()
        if self._delay:
            await asyncio.sleep(self._delay)
        self.set_calls.append(list(codes))
        self.seqs.append(seq)

    def _publish(self, msg: dict) -> None:
        self.published.append(msg)


def _service(tmp_path: Path, delay: float = 0.0) -> tuple[WatchlistService, _FakeEngine, Path]:
    path = tmp_path / "watchlist.json"
    engine = _FakeEngine(delay)
    return WatchlistService(path, engine), engine, path


async def _wait_codes(path: Path, codes: list[str], timeout: float = 0.25) -> None:
    """等落檔變成 `codes`(不看 engine —— 這裡驗的正是「落檔不必等訂閱」)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if path.exists() and load_watchlist(path)["codes"] == codes:
            return
        await asyncio.sleep(0.01)
    got = load_watchlist(path)["codes"] if path.exists() else None
    raise AssertionError(f"{timeout}s 內落檔仍是 {got},沒變成 {codes}(第二個 commit 被鎖擋住)")


class TestAdd:
    async def test_add_with_group_persists_subscribes_and_broadcasts(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        result, changed = await service.add("2330", group="主力")

        assert changed is True
        assert result == {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        assert load_watchlist(path) == result
        assert engine.set_calls == [["2330"]]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_add_without_group_lands_ungrouped(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        result, changed = await service.add("2330")

        assert changed is True
        assert result == {"codes": ["2330"], "groups": []}
        assert load_watchlist(path)["codes"] == ["2330"]
        assert engine.set_calls == [["2330"]]

    async def test_add_creates_missing_group_and_keeps_existing(self, tmp_path: Path) -> None:
        service, engine, _ = _service(tmp_path)
        await service.add("2330", group="主力")

        result, changed = await service.add("5483", group="觀察")

        assert changed is True
        assert result["codes"] == ["2330", "5483"]
        assert result["groups"] == [
            {"name": "主力", "codes": ["2330"]},
            {"name": "觀察", "codes": ["5483"]},
        ]
        assert engine.set_calls[-1] == ["2330", "5483"]

    async def test_add_existing_code_into_new_group_is_a_change(self, tmp_path: Path) -> None:
        """已在自選但不在該群組 → 仍是變更(入群組),照樣落檔廣播."""
        service, engine, _ = _service(tmp_path)
        await service.add("2330")

        result, changed = await service.add("2330", group="主力")

        assert changed is True
        assert result["codes"] == ["2330"]
        assert result["groups"] == [{"name": "主力", "codes": ["2330"]}]
        assert len(engine.published) == 2

    async def test_add_duplicate_is_noop(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        first, _ = await service.add("2330", group="主力")
        mtime = path.stat().st_mtime_ns

        again, changed = await service.add("2330", group="主力")

        assert changed is False
        assert again == first
        assert path.stat().st_mtime_ns == mtime  # 沒落檔
        assert engine.set_calls == [["2330"]]
        assert len(engine.published) == 1


class TestRemove:
    async def test_remove_drops_from_codes_and_all_groups(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.apply(
            {
                "codes": ["2330", "5483"],
                "groups": [
                    {"name": "主力", "codes": ["2330", "5483"]},
                    {"name": "觀察", "codes": ["2330"]},
                ],
            }
        )
        engine.published.clear()

        result, changed = await service.remove("2330")

        assert changed is True
        assert result == {
            "codes": ["5483"],
            "groups": [{"name": "主力", "codes": ["5483"]}, {"name": "觀察", "codes": []}],
        }
        assert load_watchlist(path) == result
        assert engine.set_calls[-1] == ["5483"]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_remove_absent_code_is_noop(self, tmp_path: Path) -> None:
        service, engine, _ = _service(tmp_path)
        await service.add("2330")
        engine.set_calls.clear()
        engine.published.clear()

        result, changed = await service.remove("5483")

        assert changed is False
        assert result["codes"] == ["2330"]
        assert engine.set_calls == []
        assert engine.published == []


class TestApply:
    async def test_apply_persists_and_notifies(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        wl: Watchlist = {"codes": ["2330"], "groups": [{"name": "a", "codes": ["5483"]}]}

        result = await service.apply(wl)

        assert result == {"codes": ["2330", "5483"], "groups": [{"name": "a", "codes": ["5483"]}]}
        assert load_watchlist(path) == result
        assert engine.set_calls == [["2330", "5483"]]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_same_content_apply_twice_second_is_noop_with_same_body(
        self, tmp_path: Path
    ) -> None:
        """canonical 零寫早退(design §6 R18/R2-10):第二次不落檔不訂閱不廣播,回傳同形."""
        service, engine, path = _service(tmp_path)
        wl: Watchlist = {"codes": ["2330", "5483"], "groups": [{"name": "a", "codes": ["2330"]}]}
        first = await service.apply(wl)
        mtime = path.stat().st_mtime_ns

        second = await service.apply(wl)

        assert second == first
        assert path.stat().st_mtime_ns == mtime
        assert engine.set_calls == [["2330", "5483"]]
        assert len(engine.published) == 1

    async def test_noncanonical_request_matching_current_is_noop(self, tmp_path: Path) -> None:
        """比較基準是正規化後的形:重複碼 / 群組成員未列入 codes 都算同內容."""
        service, engine, _ = _service(tmp_path)
        first = await service.apply(
            {"codes": ["2330", "5483"], "groups": [{"name": "a", "codes": ["5483"]}]}
        )

        second = await service.apply(
            {"codes": ["2330", "2330"], "groups": [{"name": " a ", "codes": ["5483", "5483"]}]}
        )

        assert second == first
        assert len(engine.set_calls) == 1
        assert len(engine.published) == 1


class TestCurrent:
    """Discord `/watch list` 的讀取入口(T5):唯讀,不落檔不廣播。"""

    async def test_returns_canonical_snapshot(self, tmp_path: Path) -> None:
        service, engine, _ = _service(tmp_path)
        await service.add("2330", group="主力")
        engine.published.clear()

        assert await service.current() == {
            "codes": ["2330"],
            "groups": [{"name": "主力", "codes": ["2330"]}],
        }
        assert engine.published == []
        assert engine.set_calls == [["2330"]]

    async def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        service, _, path = _service(tmp_path)

        assert await service.current() == {"codes": [], "groups": []}
        assert not path.exists()

    async def test_broken_file_degrades_to_empty(self, tmp_path: Path) -> None:
        service, _, path = _service(tmp_path)
        path.write_text(json.dumps({"codes": ["bad code"], "groups": []}), encoding="utf-8")

        assert await service.current() == {"codes": [], "groups": []}

    async def test_unparseable_json_degrades_to_empty(self, tmp_path: Path) -> None:
        """MFS-3:壞的不只是「內容不合規則」,還有「根本不是 JSON」(半寫入 / 手改壞)。"""
        service, _, path = _service(tmp_path)
        path.write_text("{壞掉的 json", encoding="utf-8")

        assert await service.current() == {"codes": [], "groups": []}


class TestSelfHealing:
    """MFS-3:壞檔不得讓「用一份合法名單覆蓋掉它」這條自癒路徑失效。"""

    async def test_unparseable_json_is_overwritten_by_valid_apply(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        path.write_text("{壞掉的 json", encoding="utf-8")

        result = await service.apply({"codes": ["2330"], "groups": []})

        assert result == {"codes": ["2330"], "groups": []}
        assert load_watchlist(path) == result
        assert engine.set_calls == [["2330"]]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_wrong_shaped_json_is_overwritten_by_valid_apply(self, tmp_path: Path) -> None:
        """群組缺 name / codes 不是 list → KeyError / TypeError,同樣不得穿出去。"""
        service, _, path = _service(tmp_path)
        path.write_text(json.dumps({"groups": [{"codes": "2330"}]}), encoding="utf-8")

        assert await service.apply({"codes": ["2330"], "groups": []}) == {
            "codes": ["2330"],
            "groups": [],
        }
        assert load_watchlist(path)["codes"] == ["2330"]


class TestRejection:
    async def test_bad_code_raises_and_writes_nothing(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        with pytest.raises(WatchlistError, match="BAD_CODE"):
            await service.apply({"codes": ["bad code"], "groups": []})

        assert not path.exists()
        assert engine.set_calls == []
        assert engine.published == []

    async def test_over_limit_raises_and_leaves_previous_file(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("2330")
        before = path.read_text(encoding="utf-8")

        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            await service.apply(
                {"codes": [f"{1000 + i}" for i in range(WATCHLIST_LIMIT + 1)], "groups": []}
            )

        assert path.read_text(encoding="utf-8") == before
        assert engine.set_calls == [["2330"]]
        assert len(engine.published) == 1

    async def test_add_bad_code_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        with pytest.raises(WatchlistError, match="BAD_CODE"):
            await service.add("23")

        assert not path.exists()
        assert engine.published == []


class TestConcurrency:
    async def test_concurrent_adds_serialize(self, tmp_path: Path) -> None:
        """單一 lock:兩個 add 同時進來,後者要看見前者的落檔結果(不覆寫)."""
        service, engine, path = _service(tmp_path, delay=0.02)

        await asyncio.gather(service.add("2330", group="a"), service.add("5483", group="b"))

        saved = load_watchlist(path)
        assert sorted(saved["codes"]) == ["2330", "5483"]
        assert len(engine.set_calls) == 2
        assert sorted(engine.set_calls[-1]) == ["2330", "5483"]  # 最後一次是累積結果
        assert len(engine.published) == 2

    async def test_second_commit_persists_while_first_subscribe_in_flight(
        self, tmp_path: Path
    ) -> None:
        """X-3:訂閱副作用移到鎖外 —— 落檔 + 定序留鎖內,ZMQ 往返不再擋住下一個寫入。

        TC4 故障時單次 `set_watchlist` 最壞是 50 檔 × 數十秒;鎖在裡面的話,期間所有
        `/watch` 與前端 PUT 全部堆積,而 Discord 的 interaction token 只有 15 分鐘。
        """
        service, engine, path = _service(tmp_path, delay=0.5)

        first = asyncio.create_task(service.apply({"codes": ["2330"], "groups": []}))
        await asyncio.wait_for(engine.entered.wait(), 1)
        second = asyncio.create_task(service.apply({"codes": ["2317"], "groups": []}))

        await _wait_codes(path, ["2317"])
        assert not first.done(), "前提失效:第一次的訂閱已跑完,這條測不到鎖凸出"
        await asyncio.gather(first, second)

    async def test_commit_hands_engine_a_monotonic_seq(self, tmp_path: Path) -> None:
        """定序在鎖內取號:鎖外的訂閱不論以什麼順序抵達 engine,都認得出誰比較新。"""
        service, engine, _ = _service(tmp_path)

        await service.add("2330")
        await service.add("5483")

        assert engine.seqs == [1, 2]

    async def test_subscribe_done_when_call_returns(self, tmp_path: Path) -> None:
        """語意不變(回歸):呼叫端 await 返回時 engine 那一趟已跑完、廣播已發。

        收斂的是**鎖凸出**,不是自己這一次的等待 —— 改成 fire-and-forget 的話
        route 回應時訂閱可能還沒掛上,前端拿到的第一份 snapshot 會缺。
        """
        service, engine, _ = _service(tmp_path, delay=0.05)

        await service.add("2330")

        assert engine.set_calls == [["2330"]]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_concurrent_same_add_only_writes_once(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path, delay=0.02)

        await asyncio.gather(service.add("2330"), service.add("2330"))

        assert json.loads(path.read_text(encoding="utf-8"))["codes"] == ["2330"]
        assert len(engine.set_calls) == 1
        assert len(engine.published) == 1


class TestCreateGroup:
    """SC-2:建空群組;同名(strip 後)= no-op 不是錯誤;保留名 / 空名照 normalize 拒。"""

    async def test_create_group_empty_and_duplicate_noop(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        wl, changed = await service.create_group("主力")

        assert changed is True
        assert wl == {"codes": [], "groups": [{"name": "主力", "codes": []}]}
        assert load_watchlist(path) == wl
        mtime = path.stat().st_mtime_ns

        again, changed_again = await service.create_group("主力 ")  # strip 後同名

        assert changed_again is False
        assert again == wl
        assert path.stat().st_mtime_ns == mtime  # 沒落檔
        assert len(engine.set_calls) == 1

    async def test_create_group_blank_name_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            await service.create_group("   ")

        assert not path.exists()
        assert engine.set_calls == []

    async def test_create_group_reserved_name_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            await service.create_group(UNGROUPED_NAME)

        assert not path.exists()
        assert engine.set_calls == []

    async def test_group_only_change_reissues_same_codes(self, tmp_path: Path) -> None:
        """R9:group-only 變更照樣 set_watchlist,codes 相同(引擎端零 SUB/UNSUB,
        守門測試在 tests/server/test_stock_engine.py)。"""
        service, engine, _ = _service(tmp_path)
        await service.apply({"codes": ["2330", "5483"], "groups": []})

        _, changed = await service.create_group("觀察")

        assert changed is True
        assert len(engine.set_calls) == 2
        assert engine.set_calls[-1] == ["2330", "5483"]  # codes 未變,仍重送一次


class TestDeleteGroup:
    async def test_delete_group_keeps_codes(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.apply(
            {"codes": ["2330", "5483"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        )

        wl, changed = await service.delete_group(" 主力 ")  # strip 後比對

        assert changed is True
        assert wl == {"codes": ["2330", "5483"], "groups": []}  # 成員落回未分組衍生桶
        assert load_watchlist(path) == wl
        assert engine.set_calls[-1] == ["2330", "5483"]

    async def test_delete_group_missing_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("2330")
        before = path.read_text(encoding="utf-8")
        engine.set_calls.clear()

        with pytest.raises(WatchlistError, match="GROUP_NOT_FOUND"):
            await service.delete_group("不存在")

        assert path.read_text(encoding="utf-8") == before
        assert engine.set_calls == []


class TestRenameGroup:
    async def test_rename_group_basic(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.apply({"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]})

        wl, changed = await service.rename_group("主力", " 觀察 ")

        assert changed is True
        assert wl == {"codes": ["2330"], "groups": [{"name": "觀察", "codes": ["2330"]}]}
        assert load_watchlist(path) == wl
        assert engine.set_calls[-1] == ["2330"]

    async def test_rename_group_collision_bad_group(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.apply(
            {
                "codes": ["2330", "5483"],
                "groups": [{"name": "主力", "codes": ["2330"]}, {"name": "觀察", "codes": []}],
            }
        )
        before = path.read_text(encoding="utf-8")
        engine.set_calls.clear()

        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            await service.rename_group("主力", "觀察")

        assert path.read_text(encoding="utf-8") == before
        assert engine.set_calls == []

    async def test_rename_group_same_after_strip_noop(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        first = await service.apply(
            {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        )
        mtime = path.stat().st_mtime_ns

        wl, changed = await service.rename_group("主力", " 主力 ")

        assert changed is False
        assert wl == first
        assert path.stat().st_mtime_ns == mtime
        assert len(engine.set_calls) == 1

    async def test_rename_group_missing_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("2330")
        before = path.read_text(encoding="utf-8")
        engine.set_calls.clear()

        with pytest.raises(WatchlistError, match="GROUP_NOT_FOUND"):
            await service.rename_group("不存在", "新名")

        assert path.read_text(encoding="utf-8") == before
        assert engine.set_calls == []


class TestUngroup:
    async def test_ungroup_removes_membership_keeps_code(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.apply(
            {"codes": ["2330", "5483"], "groups": [{"name": "主力", "codes": ["2330", "5483"]}]}
        )

        wl, changed = await service.ungroup("2330", " 主力 ")

        assert changed is True
        assert wl == {
            "codes": ["2330", "5483"],
            "groups": [{"name": "主力", "codes": ["5483"]}],
        }  # 仍在自選
        assert load_watchlist(path) == wl
        assert engine.set_calls[-1] == ["2330", "5483"]

    async def test_ungroup_noop_when_absent(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        first = await service.apply(
            {"codes": ["2330", "5483"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        )
        mtime = path.stat().st_mtime_ns

        wl, changed = await service.ungroup("5483", "主力")

        assert changed is False
        assert wl == first
        assert path.stat().st_mtime_ns == mtime
        assert len(engine.set_calls) == 1

    async def test_ungroup_missing_group_raises(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("2330")
        before = path.read_text(encoding="utf-8")
        engine.set_calls.clear()

        with pytest.raises(WatchlistError, match="GROUP_NOT_FOUND"):
            await service.ungroup("2330", "不存在")

        assert path.read_text(encoding="utf-8") == before
        assert engine.set_calls == []


class TestChangedFlag:
    async def test_add_remove_return_changed_flag(self, tmp_path: Path) -> None:
        service, _, _ = _service(tmp_path)

        wl, changed = await service.add("2330")
        assert changed is True
        assert wl["codes"] == ["2330"]

        _, changed_again = await service.add("2330")
        assert changed_again is False

        _, removed = await service.remove("2330")
        assert removed is True

        _, removed_again = await service.remove("2330")
        assert removed_again is False


#: 「現況不可用」的兩種真實形態:內容不合規則(壞碼)與超上限(讀得到但 normalize 拒)。
#: 兩者都讓 `_current_canonical()` 回 None,而四個群組方法的存在性判定就架在它上面。
_BROKEN_FILE = json.dumps(
    {"codes": ["2330", "bad code"], "groups": [{"name": "主力", "codes": ["2330"]}]},
    ensure_ascii=False,
)
_OVER_LIMIT_FILE = json.dumps(
    {
        "codes": [f"{1000 + i}" for i in range(WATCHLIST_LIMIT + 1)],
        "groups": [{"name": "主力", "codes": ["1000"]}],
    },
    ensure_ascii=False,
)

#: 四個群組方法的代表性呼叫(目標群組「主力」在壞檔裡確實存在 —— 若基準改讀空快照,
#: delete/rename/ungroup 會回誤導的 GROUP_NOT_FOUND,create_group 更會以空為底覆蓋)。
_GROUP_OPS: dict[str, Callable[[WatchlistService], Awaitable[tuple[Watchlist, bool]]]] = {
    "create_group": lambda s: s.create_group("新組"),
    "delete_group": lambda s: s.delete_group("主力"),
    "rename_group": lambda s: s.rename_group("主力", "核心"),
    "ungroup": lambda s: s.ungroup("2330", "主力"),
}


class TestGroupOpsOnUnusableFile:
    """v3 A1/B1:現況不可用 → 四個群組方法一律 `WATCHLIST_UNAVAILABLE` 且零寫。

    舊碼以 `_snapshot()`(壞檔視同空)當基準,於是 `/watch group add` 會拿一份**空**
    名單當底覆蓋回去 = 靜默清空整份自選(使用者只看到「已建立群組」);
    delete/rename/ungroup 則回「找不到該群組」,把「檔壞了」講成「你打錯名字」。
    """

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(_BROKEN_FILE, id="broken"),
            pytest.param(_OVER_LIMIT_FILE, id="over_limit"),
        ],
    )
    @pytest.mark.parametrize("op", sorted(_GROUP_OPS))
    async def test_raises_unavailable_and_writes_nothing(
        self, tmp_path: Path, op: str, payload: str
    ) -> None:
        service, engine, path = _service(tmp_path)
        path.write_text(payload, encoding="utf-8")

        with pytest.raises(WatchlistError, match="WATCHLIST_UNAVAILABLE"):
            await _GROUP_OPS[op](service)

        assert path.read_text(encoding="utf-8") == payload  # 逐字不變
        assert engine.set_calls == []
        assert engine.published == []

    async def test_apply_still_heals_an_unusable_file(self, tmp_path: Path) -> None:
        """零寫早退不得擋住自癒:整份 apply(前端存檔)仍要能覆蓋壞檔。"""
        service, engine, path = _service(tmp_path)
        path.write_text(_BROKEN_FILE, encoding="utf-8")

        result = await service.apply({"codes": ["2330"], "groups": []})

        assert result == {"codes": ["2330"], "groups": []}
        assert load_watchlist(path) == result
        assert engine.set_calls == [["2330"]]


class TestGroupNameStrip:
    """v3 A3:群組名的比對基準統一為 strip 後值(add 的自動建群曾漏掉)。"""

    async def test_add_with_padded_group_joins_existing_group(self, tmp_path: Path) -> None:
        """舊碼以未 strip 的名比對 → 「主力 」建出第二個群組,而 normalize strip 後
        兩組同名 → `BAD_GROUP`;使用者看到的是「群組名稱不合法」而名字明明合法。"""
        service, engine, _ = _service(tmp_path)
        await service.add("2330", group="主力")
        engine.published.clear()

        result, changed = await service.add("5483", group="主力 ")

        assert changed is True
        assert result["groups"] == [{"name": "主力", "codes": ["2330", "5483"]}]

    async def test_add_padded_group_membership_is_a_noop(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        first, _ = await service.add("2330", group="主力")
        mtime = path.stat().st_mtime_ns

        again, changed = await service.add("2330", group=" 主力 ")

        assert changed is False
        assert again == first
        assert path.stat().st_mtime_ns == mtime
        assert engine.set_calls == [["2330"]]


class TestReservedGroupGate:
    """SC-6 R5:保留名 gate 的唯一端到端證明(bot 自動建群那條路打得到)。"""

    async def test_add_with_reserved_group_raises_bad_group_and_writes_nothing(
        self, tmp_path: Path
    ) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("5483")
        before = path.read_text(encoding="utf-8")
        engine.set_calls.clear()
        engine.published.clear()

        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            await service.add("2330", group=UNGROUPED_NAME)

        assert path.read_text(encoding="utf-8") == before  # 檔未變
        assert engine.set_calls == []
        assert engine.published == []
class TestSettleMissingSeq:
    """review ST3:`_settle` 的 `or seq is None` 是**型別收窄**,但它同時把
    「落檔了(changed=True)卻沒帶號」變成靜默丟棄使用者的變更 —— 檔已經改了、
    訂閱池與畫面沒跟上,而且一行 log 都沒有。這條不該發生,發生就要有訊號。
    """

    async def test_changed_without_seq_is_logged_as_error(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        svc, engine, _path = _service(tmp_path)
        wl = {"codes": ["2330"], "groups": []}
        with caplog.at_level(logging.ERROR, logger="copycat.server.watchlist_service"):
            saved, changed = await svc._settle((wl, True, None))  # type: ignore[arg-type]
        assert (saved, changed) == (wl, False)
        assert engine.set_calls == []  # 不訂閱不廣播(既有語意逐字不變)
        assert engine.published == []
        assert len(caplog.records) == 1
        assert "定序號" in caplog.text


class TestReplaceGroup:
    """盤前篩選 nightly 覆寫(#173):整組取代 + 淘汰檔不堆積未分組桶。"""

    async def test_creates_group_when_missing(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        await service.add("2330")

        result, changed = await service.replace_group("盤前篩選", ["1111", "2222"])

        assert changed is True
        assert result["groups"] == [{"name": "盤前篩選", "codes": ["1111", "2222"]}]
        # 既有未分組檔保留,新成員由 normalize 併入 codes
        assert result["codes"] == ["2330", "1111", "2222"]
        assert load_watchlist(path) == result
        assert engine.set_calls[-1] == ["2330", "1111", "2222"]
        # 廣播斷言(review F-17):replace_group 是唯一由後台 task 觸發的寫入路徑,
        # 漏廣播的症狀是側欄整晚不知道群組換過 —— 不只靠 _settle 共用段間接護。
        # 前面的 add 已廣播一次,故驗「多了一則且尾筆是 watchlist_changed」
        assert len(engine.published) == 2
        assert engine.published[-1] == {"type": "watchlist_changed"}

    async def test_replaced_out_codes_leave_watchlist_unless_grouped_elsewhere(
        self, tmp_path: Path
    ) -> None:
        service, _engine, _path = _service(tmp_path)
        await service.replace_group("盤前篩選", ["1111", "2222"])
        # 2222 同時屬於使用者自己的群組 → 淘汰後仍留在自選;1111 只在篩選組 → 一併離開
        await service.add("2222", group="主力")

        result, changed = await service.replace_group("盤前篩選", ["3333"])

        assert changed is True
        assert result["groups"] == [
            {"name": "盤前篩選", "codes": ["3333"]},
            {"name": "主力", "codes": ["2222"]},
        ]
        assert result["codes"] == ["2222", "3333"]  # 1111 已離開

    async def test_same_codes_is_noop(self, tmp_path: Path) -> None:
        service, engine, _path = _service(tmp_path)
        await service.replace_group("盤前篩選", ["1111"])
        calls = len(engine.set_calls)
        published = len(engine.published)

        result, changed = await service.replace_group("盤前篩選", ["1111"])

        assert changed is False
        assert result["codes"] == ["1111"]
        assert len(engine.set_calls) == calls  # 零寫早退:不訂閱
        assert len(engine.published) == published  # 也不廣播(review F-17)
