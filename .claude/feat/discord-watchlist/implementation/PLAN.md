# PLAN — Discord 自選補齊(condensed;design v2 對應;v2 = impl-spec review R1-R8 修入)

> For agentic workers:依 feat.md Phase 3 執行(TDD 紅→綠,tag 見該節);
> 每節 = 一檔;「失敗測試」欄為紅測試清單,先紅後綠。

任務順序:T1(stock_watchlist)→ T2(watchlist_service)→ T3(discord_bot)。
下游依賴上游介面;各任務自帶紅→綠 commit 對。

## T1 `copycat/stock_watchlist.py` + `tests/test_stock_watchlist.py`(共用 util,高風險面 → 全簽名)

新增 / 變更:
```python
UNGROUPED_NAME = "未分組"          # module-level;前端 UNGROUPED_LABEL 同值(跨檔契約)
logger = logging.getLogger(__name__)  # 檔內現無 logging,補 import + logger

def normalize(wl: Watchlist) -> Watchlist:
    # 群組名迴圈:if not name or name in names or name == UNGROUPED_NAME:
    #     raise WatchlistError("BAD_GROUP")     ← 僅加第三條件

def load_watchlist(path: Path = DEFAULT_PATH) -> Watchlist:
    # codes 推導(v3/v1 原樣、v2 union)之後:
    # dropped = [g for g in groups if g["name"].strip() == UNGROUPED_NAME]
    # 有 dropped →(R4)dropped 各組 codes 依序 union 進 codes(三路徑一致,orphan
    #   不流失;手改 v3 檔的保留名組可能含 codes 外股號)
    #   + logger.warning("watchlist 含保留名群組,讀時丟棄:%s(%s)", path, names)
    # groups = 其餘
```
輸入輸出例:`load({"codes":["2330"],"groups":[{"name":"未分組","codes":["2330"]}]})`
→ `{"codes":["2330"],"groups":[]}`;v2 檔 `{"groups":[{"name":"未分組","codes":["2330"]}]}`
→ `{"codes":["2330"],"groups":[]}`;手改 v3 檔
`{"codes":["2330"],"groups":[{"name":"未分組","codes":["2317"]}]}`
→ `{"codes":["2330","2317"],"groups":[]}`(R4 orphan 保留)。

失敗測試(SC-6):
- `test_normalize_rejects_reserved_group_name`(strip 後同名亦拒)
- `test_load_drops_reserved_group_and_keeps_codes`(v3 + v2 兩形)
- `test_load_drops_reserved_group_keeps_orphan_code`(R4)
- `test_normalize_keeps_empty_groups`(SC-1 依賴的既有行為補鎖)

## T2 `copycat/server/watchlist_service.py` + `tests/server/test_watchlist_service.py`

- `_commit` → `tuple[Watchlist, bool]`(早退 `(canonical, False)` / 落檔 `(saved, True)`);
  `apply` body 解包回 `Watchlist`(REST 契約不變)。
- 新方法(全部 `async with self._lock:` 內 load → 存在性檢查 → 改 → `_commit`;
  比對一律 strip 後名對 canonical 現況):
  `create_group(name) / delete_group(name) / rename_group(old, new) /
  ungroup(code, group) -> tuple[Watchlist, bool]`
- `delete_group/rename_group/ungroup` 目標缺席 → `raise WatchlistError("GROUP_NOT_FOUND")`
  (零寫);`create_group` 同名存在 → `(current, False)`;`rename` strip 後同名 →
  `(current, False)`;`ungroup` code 不在組 → `(current, False)`。
- `add/remove` 改回 tuple(呼叫端僅 bot + 測試)。

既有測試遷移(R3,**獨立 commit、不掛 TDD tag**,與新紅測試分開):
- `FakeService`(test_discord_bot.py:64-86)補四個新方法、add/remove 改回
  `(wl, changed)`(changed 由建構參數控制,no-op 文案測試共用)
- `test_watchlist_service.py` 既有 8 處 `await service.add/remove(...)` 直接比 dict
  的斷言改 `wl, changed = ...` 解包 + 順手鎖 changed 值

失敗測試(SC-2/3/7 + R9):
- `test_create_group_empty_and_duplicate_noop`(含帶尾空白重複 → no-op 非 BAD_GROUP)
- `test_delete_group_keeps_codes` / `test_delete_group_missing_raises`
- `test_rename_group_{basic,collision_bad_group,same_after_strip_noop,missing_raises}`
- `test_ungroup_{removes_membership_keeps_code,noop_when_absent,missing_group_raises}`
- `test_add_remove_return_changed_flag`(no-op 假 / 真變更真)
- `test_add_with_reserved_group_raises_bad_group_and_writes_nothing`(R5:斷言
  BAD_GROUP + `engine.set_calls == []` + 檔未落/未變 — 保留名 gate 唯一端到端證明)
- service 層 group-only 斷言:`engine.set_calls` 多一筆且 codes 相同(R1 改語意真實版)

R9 守門測試(R1 改層):`tests/server/test_stock_engine.py` 用
`tests/helpers/fake_sources.FakeStockSource`(有 subscribed/unsubscribed 記錄)—
`set_watchlist(["2330","2317"])` 後以**相同 codes** 再呼叫,斷言兩份記錄長度不變。

## T3 `copycat/server/discord_bot.py` + `tests/server/test_discord_bot.py`

- `_ERROR_TEXT["GROUP_NOT_FOUND"] = "找不到該群組"`。
- 新 handler(全走 `_run` 骨架):`handle_groups / handle_group_add / handle_group_remove /
  handle_group_rename / handle_ungroup`;`handle_add/handle_remove` 改吃 tuple 分文案
  + add 掛軟白名單尾綴(`_stock_name(code) == ""` → `(查無此檔名稱,請確認代碼)`)。
- 保留名攔截(R2 明確化):ungroup 的 `group`、group_remove 的 `name`、
  group_rename 的 **`old`(操作對象)** strip 後 == UNGROUPED_NAME →
  `「未分組」不是群組,無法操作`(不打 service)。rename 的 `new` **不攔** —
  交 service → normalize → `BAD_GROUP` → 「群組名稱不合法」(取新名非法語意)。
- `_format_groups(wl)`:設計 v2 規格(空群組列出、未分組標注衍生、零群組雙分支)。
- `group_choices(service, current) -> list[str]`:None → [];`asyncio.wait_for(
  service.current(), 1.0)` 逾時/例外 → [];子字串過濾;略過 len>100 + warning;≤25。
- `create_bot`:外層變數改名 `watch`;子群組變數名 **`group_cmd`**(R7,不得叫
  `group` — 會遮蔽參數且讓既有 `@group.command` 靜默改掛子群組)=
  `app_commands.Group(name="group", description="群組管理", parent=watch)` 掛
  add/remove/rename;頂層加 groups / ungroup;四處 `@cmd.autocomplete(...)` 接
  `group_choices`;
  `discord.Client(intents=..., allowed_mentions=discord.AllowedMentions.none())`。
- `WatchlistServiceLike` Protocol 同步全部新簽名。

失敗測試(SC-1/2/3/4/5/7;文案逐字鎖 design v2 表):
- `test_handle_groups_*` 四態(R6):有群組且未分組 K>0(逐字鎖含「(衍生,非群組)」)/
  有群組且 K=0(斷言無「未分組」字樣)/ 含 0 檔群組仍列出 / 零群組×{codes 空, 非空}
- `test_handle_group_add_{creates,duplicate_noop,reserved_bad_group}` /
  `test_handle_group_remove_{ok,missing,reserved_blocked}` /
  `test_handle_group_rename_{ok,missing,reserved_old_blocked,reserved_new_bad_group}`(R2)
- `test_handle_ungroup_{ok,noop,missing_group,reserved_blocked}`
- `test_handle_add_{noop_text,unknown_code_warning,changed_with_group}` /
  `test_handle_remove_noop_text`
- `test_group_choices_{normal,substring_filter,none_service,timeout,long_name_skipped,cap_25}`
- `TestRealDiscordWiring` 擴充(R7):leaf 的 **qualified name 集合** ==
  {watch add, watch remove, watch list, watch groups, watch ungroup,
  watch group add, watch group remove, watch group rename} + autocomplete 已掛
  (discord 已裝才跑)

## 驗證 gate(Phase 5)

`.venv\Scripts\python -m pytest -q` + `ruff check copycat tests` + `pyright` 全綠
(worktree 內用主 tree venv 絕對路徑;pytest cwd 優先無 editable 陷阱)。
前端零改 → npm gate 不觸發。`copycat validate` 照 CLAUDE.md gate 跑。

非自動化交付項(R8):
- **prod 檔中毒檢查**(design Known Risks):主 tree
  `python -c "import json;d=json.load(open(r'C:\side-project\copycat\data\stock_watchlist.json',encoding='utf-8'));print([g['name'] for g in d.get('groups',[])])"`
  → 預期輸出不含「未分組」;含 → 讀時遷移會處理,記入交付說明。
- **SC-4 Discord 實發 = user 過目**(prod 重啟後);窗口外以 group_choices 單元測試
  降級,交付說明明列此項待 user。
