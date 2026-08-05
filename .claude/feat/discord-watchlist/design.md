# design — Discord 自選補齊(題 4)v1

changelog:
- v1(2026-08-05):初版。
- v2(2026-08-05):design review round 1 九條全修 —— R1 autocomplete 加 1s 逾時降級;
  R2 保留名改讀時遷移;R3 巢狀 Group 補 description + 接線測試改擴充既有 wiring 測試;
  R4 create_group strip 比對;R5 _format_groups 未分組標注 + 保留名操作專屬文案;
  R6 apply 解包 + lock 契約句;R7 Choice 100 字元上限 + allowed_mentions;
  R8 子字串過濾偏離記檔;R9 set_watchlist 差集行為改已驗證結論。
- v3(2026-08-05):自評 code review round 1 —— [amendment: A1/B1] 四個新群組方法的
  現況基準改「`_current_canonical()` 為 None(壞檔/超限檔)→ 拋
  `WATCHLIST_UNAVAILABLE` 零寫」(原 `_snapshot()` 空 fallback 會讓 create_group
  以空為底覆蓋 = 靜默清空自選;GROUP_NOT_FOUND 誤導文案同修);[A2] `_run` 回覆
  >1900 截斷 + `followup.send` 包 try(超長回覆不再永久卡「思考中」);[A3] `add()`
  群組比對 strip + handler 入口統一 strip 群組名參數(判定與回覆同基準)。

**Goal**:`/watch` 補齊群組管理 + autocomplete + 軟白名單 + 保留名 gate + 回覆差異化
(brainstorm SC-1..8)。

**架構**:沿既有三層 — 純 handler(discord_bot)→ WatchlistService(單鎖複合操作)→
stock_watchlist(normalize 單一定義)。零新檔、零前端、零 API route 改動。
discord 仍 lazy import;新 handler 全部 duck-typed 可測。

## 檔案組織

| 檔 | 變更 |
|---|---|
| `copycat/stock_watchlist.py` | `UNGROUPED_NAME = "未分組"` 常數 + normalize 拒絕保留名(SC-6) |
| `copycat/server/watchlist_service.py` | `_commit` 回傳 changed flag;新方法 create_group / delete_group / rename_group / ungroup;add/remove 回傳型改 tuple(SC-2/3/7) |
| `copycat/server/discord_bot.py` | 新 handler ×5 + `_format_groups` + `group_choices` autocomplete 純函式 + create_bot 接線(subgroup)+ `_ERROR_TEXT` 補 `GROUP_NOT_FOUND`(SC-1/2/3/4/5/7) |
| `tests/test_stock_watchlist.py` | SC-6 |
| `tests/server/test_stock_engine.py` | R9 守門(group-only 變更零 SUB/UNSUB,用 FakeStockSource) |
| `tests/server/test_watchlist_service.py` | SC-2/3/7 service 層 |
| `tests/server/test_discord_bot.py` | SC-1/2/3/4/5/7 handler 層 |

## 資料流與介面(SC 對應)

### SC-6 保留名 gate — `stock_watchlist.py`

```python
UNGROUPED_NAME = "未分組"  # 前端 WatchlistManagerDialog UNGROUPED_LABEL 同值(跨檔契約)
# normalize() 群組名迴圈內:
if not name or name in names or name == UNGROUPED_NAME:
    raise WatchlistError("BAD_GROUP")
```
- 單一定義點 → bot 與前端 PUT 同時被擋。
- **讀時遷移(R2)**:`load_watchlist` 在 codes 推導**之後**丟棄 strip 後名 ==
  `UNGROUPED_NAME` 的群組 + `logger.warning`(檔路徑 + 群組名)。不就地寫檔
  (v1/v2 遷移同慣例);成員因 codes 已含而落回未分組衍生桶,語意即使用者本意。
  理由:此狀態**現行 bot 今天就造得出來**(`/watch add 2330 未分組` 走自動建群),
  若只在寫路拒,毒檔會讓所有 bot 指令與前端 PUT 永久 `BAD_GROUP`、零寫早退失效
  (`_current_canonical` 恆 None)。v2 遷移的 union 先算(含保留名組)再丟組,
  codes 不流失。
- 沿用 `BAD_GROUP`(前端 errText 已有文案),不新增前端可見碼。
- 注意:`load_watchlist` 現無 logger,需補 `logging.getLogger(__name__)`。

### SC-2/3/7 service 層 — `watchlist_service.py`

```python
async def _commit(self, wl: Watchlist) -> tuple[Watchlist, bool]:
    # 早退分支回 (canonical, False);落檔分支回 (saved, True)

async def apply(self, wl: Watchlist) -> Watchlist:
    # 簽名不變(REST route 零改)但 body 必改:wl, _ = await self._commit(wl); return wl(R6)
async def add(self, code, group=None) -> tuple[Watchlist, bool]
async def remove(self, code) -> tuple[Watchlist, bool]
async def create_group(self, name: str) -> tuple[Watchlist, bool]
async def delete_group(self, name: str) -> tuple[Watchlist, bool]
async def rename_group(self, old: str, new: str) -> tuple[Watchlist, bool]
async def ungroup(self, code: str, group: str) -> tuple[Watchlist, bool]
```

語意:
- **鎖契約(R6)**:五個新方法一律 `async with self._lock:` 內完成
  load → 存在性檢查 → 改 → `_commit`,與既有 add/remove 同形 —— 存在性判定與
  commit 同一輪持鎖,無 TOCTOU。
- `create_group`:以 `name.strip()` 對現況(canonical)群組名比對(R4),
  相同 → `(current, False)`(no-op,不報錯);否則 append 空群組。
  保留名 / 空名由 `_commit` 內 normalize 拒(`BAD_GROUP`)。
- `delete_group` / `rename_group` / `ungroup`:目標群組不存在(以 strip 後名比對)→
  `raise WatchlistError("GROUP_NOT_FOUND")`(先於 _commit,零寫)。
- `delete_group`:自 groups 移除該組;codes 不動(成員落回未分組衍生桶)。
- `rename_group`:只改 name;新名撞既有名 / 保留名 → normalize 拒 `BAD_GROUP`;
  strip 後同名 → `(current, False)`。
- `ungroup`:code 不在該群組 → `(current, False)`;在 → 自該組 codes 移除,
  wl codes 不動(仍在自選)。
- changed flag 來源 = `_commit` 早退判斷(單一事實點,無 TOCTOU)。
- **已驗證(R9)**:group-only 變更以相同 codes 呼叫 `engine.set_watchlist` 是安全的 —
  `set_watchlist` 的 added 以 `_refs` 實況、removed 以 `_watchlist` 差集算
  (stock_engine.py:225-226),同集合零 SUB/UNSUB;`SignalHub.on_watchlist` 亦差集
  (signal_hub.py:235-243),不 drop_code 不重抓基準。**不加**「codes 未變跳過
  set_watchlist」備案(會連跳重試路徑的名單重指派)。以測試鎖:group-only 變更時
  fake engine 的 subscribe/unsubscribe 呼叫數 = 0。

### SC-1/2/3/5/7 handler 層 — `discord_bot.py`

```python
_ERROR_TEXT += {"GROUP_NOT_FOUND": "找不到該群組"}

async def handle_groups(service, interaction) -> str          # SC-1
async def handle_group_add(service, interaction, name) -> str  # SC-2
async def handle_group_remove(service, interaction, name) -> str
async def handle_group_rename(service, interaction, old, new) -> str
async def handle_ungroup(service, interaction, code, group) -> str  # SC-3

def _format_groups(wl: Watchlist) -> str:
    # 「群組 N 個」/ 每組一行「【名】M 檔」含 0 檔
    # 末行「未分組 K 檔(衍生,非群組)」(K>0 才列;R5 標注非真群組)
    # 零群組:codes 空 → 「尚無群組」;codes 非空 → 「尚無群組;未分組 K 檔」(R5)
```
- **保留名操作攔截(R5)**:handle_ungroup / handle_group_remove / handle_group_rename
  在呼叫 service 前判 `name.strip() == UNGROUPED_NAME` → 回
  `「未分組」不是群組,無法操作`(不打 service;GROUP_NOT_FOUND 留給真缺席)。

回覆文案(測試逐字鎖):
| 情境 | 文案 |
|---|---|
| add 新增 | `已加入自選:{label}`(+`(群組:{g})`) |
| add no-op | `已在自選:{label}(無變更)` |
| add 查無名稱(SC-5) | 上列文案 + `(查無此檔名稱,請確認代碼)`(仍加入) |
| remove 移除 | `已從自選移除:{label}` |
| remove no-op | `不在自選:{label}` |
| group add 建立 | `已建立群組:{name}` |
| group add 已存在 | `群組已存在:{name}` |
| group remove | `已刪除群組:{name}(成員移至未分組)` |
| group rename | `已改名:{old} → {new}` |
| rename no-op | `名稱未變:{name}` |
| ungroup 移出 | `已自群組 {g} 移出:{label}(仍在自選)` |
| ungroup no-op | `{label} 不在群組 {g}` |
| 保留名操作(ungroup/group remove/rename) | `「未分組」不是群組,無法操作` |
| 現況不可用(四個群組方法,v3) | `WATCHLIST_UNAVAILABLE` → `自選檔目前不可用,請自前端存檔修復` |

文案變數一律為 **strip 後**值(v3:handler 入口統一 strip);rename no-op 的
`{name}` 明定 = strip 後的 `new`。

- SC-5 判定:`_stock_name(code) == ""` → 警告尾綴;只掛在 add(remove 的對象必已在檔)。
- 既有 `handle_add/handle_remove` 改吃 tuple 回傳並分文案;`WatchlistServiceLike`
  Protocol 同步(內部契約,消費者僅 bot + 測試 fake)。

### SC-4 autocomplete — `discord_bot.py`

```python
async def group_choices(service: WatchlistServiceLike | None, current: str) -> list[str]:
    """降級三態(R1):service None → [];asyncio.wait_for(service.current(), 1.0)
    逾時 / 例外 → []。autocomplete 不能 defer(3 秒硬窗)且與寫入共用 service 單鎖,
    鎖被 _commit 的 ZMQ 往返佔住時必須放手回空,不可堆積等鎖 task。
    子字串過濾(R8,偏離 brainstorm 的「前綴」— 中文名無前綴語意,已記 amendment);
    略過 len > 100 的名稱並 logger.warning(R7:Choice name/value 各 100 上限,
    單一超長項會讓整份回應被 Discord 拒收);≤25。"""
```
- create_bot 內以 `@cmd.autocomplete("group")` 接線,callback 將字串轉
  `app_commands.Choice`;純函式獨立測(fake service:正常 / None / 永不返回的
  current() 三態)。接線層由既有 `TestRealDiscordWiring`(discord 已裝才跑)涵蓋
  建構,擴充斷言:指令樹 leaf 數 = 8、autocomplete callback 已掛上(R3)。
- 掛點:`/watch add` 的 group、`/watch ungroup` 的 group、`/watch group remove` 的
  name、`/watch group rename` 的 old。
- **訊息注入防護(R7)**:群組名為自由文字且會原樣回填訊息,
  `discord.Client(intents=..., allowed_mentions=discord.AllowedMentions.none())`
  — `/watch group add "@everyone"` 之後的任何 `/watch groups` 不得真 ping。

### 指令樹(create_bot)

```
/watch add <code> [group←AC]     /watch remove <code>      /watch list
/watch groups                     /watch ungroup <code> <group←AC>
/watch group add <name>           /watch group remove <name←AC>
/watch group rename <old←AC> <new>
```
- 子群組(R3):`app_commands.Group(name="group", description="群組管理", parent=watch)`
  — **description 必帶**(缺 → `TypeError('groups must have a description')`,而
  create_bot 在 `_start_signals` 內被呼叫,炸掉會被 boot 傘吞成訊號整段靜默停用)。
  外層變數自 `group` 改名 `watch`(現名與 `_add(..., group=None)` 參數遮蔽,R3)。
  guild 限定 sync 沿 on_ready 既有路徑,零改。

## 邊界

- 空群組在 normalize / save / load 全程保留(SC-1 依賴;現行 code 已如此,測試補鎖)。
- `current()` 壞檔回空清單 → `_format_groups` 出「尚無群組」;autocomplete 回 []。
- defer-first 骨架 `_run` 沿用,所有新 handler 走同一條(3 秒窗 + 錯誤邊界)。

## Known Risks

- **保留名毒檔(R2,已消化)**:現行 bot 的 `/watch add <code> 未分組` 真的會建出
  名為「未分組」的群組;若無讀時遷移,SC-6 gate 上線後該檔會讓全部寫入路徑永久
  `BAD_GROUP`。已以讀時遷移消化;實際 prod 檔(`data/stock_watchlist.json`)是否已
  中毒在 Phase 6 順手檢查。
- **autocomplete 逾時降級(R1)**:TC4 慢 / 斷線時寫入持鎖秒級,autocomplete 於該窗
  一律回空選單(使用者仍可手打群組名)— 接受此 UX,不做鎖外快取(YAGNI)。
- **讀時遷移 × 30 上限交互(B-p2#6,接受)**:保留名組的 orphan union 理論上可把
  codes 推破 `WATCHLIST_LIMIT` → 檔進入「可讀但不可 normalize」態;此態下群組操作
  一律大聲拒絕(`WATCHLIST_UNAVAILABLE`)零寫,自癒路徑 = 前端整份 apply。前置
  條件僅手改檔可達(舊 bot 建的保留名組成員必已在 codes)→ 不加遷移端 cap,記
  next-time。
- **群組名長度 / 群組數上限不加(A2 縮範圍)**:回覆層以 1900 截斷 + send 防護兜底;
  上限本身維持 out of scope(brainstorm 決策),記 next-time。
