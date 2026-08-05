"""WatchlistService 行為合約(design §6 — SC-8 後端半 / SC-11)。

三個入口(前端 PUT / Discord `/watch add` / `/watch remove`)共用同一把 lock 與
同一條「落檔 → set_watchlist → 廣播」序列;engine 用 fake 記錄呼叫。
"""

from __future__ import annotations

import asyncio
import json
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
        self.published: list[dict] = []
        self._delay = delay

    async def set_watchlist(self, codes: list[str]) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
        self.set_calls.append(list(codes))

    def _publish(self, msg: dict) -> None:
        self.published.append(msg)


def _service(tmp_path: Path, delay: float = 0.0) -> tuple[WatchlistService, _FakeEngine, Path]:
    path = tmp_path / "watchlist.json"
    engine = _FakeEngine(delay)
    return WatchlistService(path, engine), engine, path


class TestAdd:
    async def test_add_with_group_persists_subscribes_and_broadcasts(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        result = await service.add("2330", group="主力")

        assert result == {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}
        assert load_watchlist(path) == result
        assert engine.set_calls == [["2330"]]
        assert engine.published == [{"type": "watchlist_changed"}]

    async def test_add_without_group_lands_ungrouped(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)

        result = await service.add("2330")

        assert result == {"codes": ["2330"], "groups": []}
        assert load_watchlist(path)["codes"] == ["2330"]
        assert engine.set_calls == [["2330"]]

    async def test_add_creates_missing_group_and_keeps_existing(self, tmp_path: Path) -> None:
        service, engine, _ = _service(tmp_path)
        await service.add("2330", group="主力")

        result = await service.add("5483", group="觀察")

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

        result = await service.add("2330", group="主力")

        assert result["codes"] == ["2330"]
        assert result["groups"] == [{"name": "主力", "codes": ["2330"]}]
        assert len(engine.published) == 2

    async def test_add_duplicate_is_noop(self, tmp_path: Path) -> None:
        service, engine, path = _service(tmp_path)
        first = await service.add("2330", group="主力")
        mtime = path.stat().st_mtime_ns

        again = await service.add("2330", group="主力")

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

        result = await service.remove("2330")

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

        result = await service.remove("5483")

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
