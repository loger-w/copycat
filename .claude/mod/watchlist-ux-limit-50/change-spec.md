# Change spec — 自選清單 UX + 上限 50(mod/watchlist-ux-limit-50)

現況表:同目錄 `current-state.md`。規模:L(≥5 檔、跨前後端,但全為機械性小改)。

**分流判定**:已成形方案(user 指名落點檔案 / 行號 / UI 方向 / 上限值已拍板)→ grilling
姿態;無方向性抉擇,設計細節逐項 `[auto-default]`(見 §D)。

## A. 成功條件

- **SC-1 上限 50 生效**:PUT `/api/stock/watchlist` 50 檔 → 200;51 檔 → 400
  `WATCHLIST_FULL`。`/api/stock/group-state` 50 相異碼 → 200;51 碼 → 400 `BAD_CODES`。
  驗證:`pytest tests/server/test_stock_routes.py -q`(`test_put_at_limit_ok` /
  `test_put_over_limit_400` / `test_group_state_at_limit_ok` / `test_too_many_codes_400`)。
- **SC-2 上限文案全通道一致**:前端 `errText` 與 Discord bot `_ERROR_TEXT` 均為
  「自選已達 50 檔上限」,且數字由常數推導(不再硬編)。
  驗證:`pytest tests/server/test_discord_bot.py -q` + `npm test`(StockPage /
  WatchlistSidebar 文案測試)+ `grep -rn "30 檔|上限 30" copycat frontend/src tests`
  剩餘命中**皆為明列的無關 30**(signal 節流 30/分、`MAX_RULES=30`、candle
  `days=30`、TC4 重連 30 次)[amendment 2026-08-13: R5 grep 改寬;R11 — tests/ 內
  「相關 30」敘述性註解**一併同步**(純註解零行為),gate 不留人工判讀模糊帶]。
- **SC-3 群組標題列可指認差異**(畫面可指認):群組與「未分組」標題列整條有
  `bg-surface`(#10161f)底色帶、組名字重 `font-medium`,個股列維持透明底;
  拖曳落點高亮(section 外框 `border-accent`)不變。
  驗證:vitest class 斷言(header 含 `bg-surface`、stock row 不含)+ AI 截圖對照 +
  user 過目。驗證窗口:無(盤外可驗)。
- **SC-4 全部展開/收合**(畫面可指認):sticky 搜尋區塊內、搜尋列與建議清單**之間**
  新增一列右對齊文字鈕 [amendment 2026-08-13: R8 — 原「區塊下緣」會被行內建議清單推動,
  位置跳動];「未分組 + 全部群組」皆折疊時顯示「全部展開」,否則顯示「全部收合」。
  點「全部收合」→ 未分組與所有群組清單全部隱藏、`WL_COLLAPSED_KEY` 寫入現行全組名、
  `WL_UNGROUPED_KEY` = "1";點「全部展開」→ 全開、set 清空、"0"。重整後狀態保留
  (沿用既有兩把 key,無新 key)。**鈕與「管理」鈕同受 `data === undefined` gate:
  自選尚未載入 / 載入失敗時不渲染**(EMPTY_WL 危險窗內 `groups=[]`,全收會把既有
  折疊持久化覆寫成空)[amendment 2026-08-13: R1 P0]。
  驗證:vitest(localStorage + DOM 斷言)+ AI 截圖對照 + user 過目。
- **SC-5 效能假設盤點**:`current-state.md` §B 表逐項評估完成;結論 = 50 檔下
  `_CLIENT_QUEUE_MAX`(1000)與 60s group_snapshot 節奏**均無需調參**,僅同步來源檔
  註解數字與 `docs/next-time.md` 已知缺口數字。驗證:本檔 §C diff 清單 + review。

## B. 不能破壞的既有行為白名單

1. `applyCollapsed` 三步不變式(ref 同步 → persist → setState 成對;review TC-4)與
   `dropCollapsed` 刪組清折疊(W-20)。全收/全展**必須走同一寫入點**。
2. 逐群組 ▸/▾ 折疊與未分組折疊的單獨 toggle 行為、localStorage key 名與值格式
   (`WL_COLLAPSED_KEY` = JSON string[]、`WL_UNGROUPED_KEY` = "1"/"0")不變。
3. 拖曳:`ROW_H` 幾何、`zonesNow` 對折疊區塊的處理、落點高亮 `border-accent`、
   拖曳中 header `onClick` 守衛與 hover 關閉語意不變。
4. `sectionHeader` a11y:原生 `<button>`、`aria-expanded` / `aria-controls`、▸/▾
   `aria-hidden`、focus-visible 底線不變。
5. API error 契約:`{"detail": {"error": code}}` shape 與 `WATCHLIST_FULL` / `BAD_CODE`
   / `BAD_GROUP` / `BAD_CODES` code 值不變(變的只有前端/bot 的中文文案數字)。
6. W-22 零 PUT(`isSameWatchlist` 早退)與 watchlist_service canonical 零寫早退不變。
7. `/api/stock/group-state` 先去重(保序)再驗數量的順序不變。
8. Discord 訊號節流 30/分(signal hub `_MAX_PER_MIN`)是**無關常數,不動**
   (`tests/server/test_signal_hub.py:727` 那組不得變紅)。
9. `stock_watchlist.py` v1/v2/v3 讀時遷移、保留名群組丟棄邏輯不動。
10. `errText` 其餘三句文案(BAD_CODE / BAD_GROUP / fallback)與 bot 其餘文案不變。
11. `/watch list` 的 `_REPLY_LIMIT`(1900)截斷語意不變 [amendment 2026-08-13: R10]:
    輸出長度量級 = **Σ(各組成員數)× ~10 字 + 組名**(逐群組列出、同檔可屬多組、
    群組數無上限),不是檔數 × 10 —— 多群組滿載時**現況即可能截斷**,截斷是既有
    安全降級;30→50 只是同比例 ×1.67 放大,非新機制,不改 [amendment 2026-08-13:
    R14 — 原「遠低於 1900」估算把每檔當只出現一次,刪除該過度保證]。

## C. Diff 級章節(逐檔;三類標記)

### 🔵 wave 0(重構,行為不變)

- `frontend/src/components/stock/WatchlistSidebar.tsx`:抽
  `applyUngroupedCollapsed(next: boolean)`(寫 `WL_UNGROUPED_KEY` + setState),
  `toggleUngroupedCollapsed` 改呼叫之。行為逐字等價(既有測試
  `WatchlistSidebar.test.tsx:387` StrictMode 持久化不得紅)。

### 🔴 wave 1(行為:上限 30→50 + 文案)

先改既有測試紅(`[red]`):
- `tests/server/test_stock_routes.py`:
  - `test_put_over_limit_400`:`range(31)` → **字面 `range(51)`** 並註明「與 at-limit
    成對釘死邊界 50/51」[amendment 2026-08-13: R12 — 參數化會讓 50 這個值失去任何
    測試錨點;字面對(50→200, 51→400)唯一釘死上限=50]。本身不紅(51 檔在上限 30
    下也是 400)。
  - **新增** `test_put_at_limit_ok`:PUT **字面 50 檔** → 200【現況紅:30 上限擋下】
    [amendment 2026-08-13: R12 — 原 `range(WATCHLIST_LIMIT)` 在常數=30 時即綠,
    [red] 落空]。
  - `test_too_many_codes_400`:31 → **字面 51**(同邊界對理由)。
  - `test_duplicate_codes_are_deduped_before_the_count_check`:`["2330"] * 31` →
    `* (WATCHLIST_LIMIT + 1)` 並註明「重複數必須 > 上限,否則失去鑑別力」(考點是
    去重先於驗數的**順序**,跟隨常數即可)[amendment 2026-08-13: R3]。
  - `test_dedup_does_not_defeat_the_limit`:31 → `WATCHLIST_LIMIT + 1`(考點是去重
    不放行,跟隨常數)。
  - **新增** `test_group_state_at_limit_ok`:字面 50 相異碼 → 200【現況紅】。
- `tests/server/test_discord_bot.py:173`:期望文案 → 「自選已達 50 檔上限」【紅】。
- `frontend/src/components/stock/WatchlistSidebar.test.tsx:574`、
  `frontend/src/components/stock/StockPage.test.tsx:489`:期望文案 → 50【紅】。

再改實作綠(`[green]`):
- `copycat/stock_watchlist.py:37`:`WATCHLIST_LIMIT = 30` → `50`。
- `copycat/server/discord_bot.py:58`:`"自選已達 30 檔上限"` →
  f-string 由 `WATCHLIST_LIMIT` 推導(import 自 `copycat.stock_watchlist`,檔內已有
  同源 import)。
- `frontend/src/lib/constants.ts`:新增 `export const WATCHLIST_LIMIT = 50`,註明
  跨檔契約(與後端 `stock_watchlist.WATCHLIST_LIMIT` 同值,改一邊要同步另一邊);
  **同步登錄專案 `CLAUDE.md` §4 跨檔契約**(沿 `OrderRecord.unit` 先例:產生點 =
  `stock_watchlist.py`,讀者 = 前端常數 + bot 文案)[amendment 2026-08-13: R7]。
- `frontend/src/hooks/useStockWatchlist.ts:27`:文案改模板字串
  `` `自選已達 ${WATCHLIST_LIMIT} 檔上限` ``。
- 註解數字同步(與行為同 commit;它們陳述的就是本次改的假設):
  `stock_engine.py:562,566,1260`、`stock_state.py:202`、`bars.py:243`、
  `app.py:337,527,1208,1212`、`docs/next-time.md:408`(30 檔 × 10s → 50 檔 × 10s,
  500s;**同條補退出準則**:TC4 離線啟動實測 index/breadth 就緒 >10 分鐘 → 做
  per-code timeout 縮短 / 並行訂閱 [amendment 2026-08-13: R9])、
  `docs/next-time.md:1033`(HR-6「佇列 1000 按 30 檔推的」→ 50 檔重述,穩態評估
  見 current-state B-1)[amendment 2026-08-13: R6]、
  `docs/next-time.md:62,676`(30 檔 30 行 warning → 50;不佔 30 檔上限 → 50)
  [amendment 2026-08-13: R15]、
  `frontend/src/hooks/useGroupSnapshots.ts:10,13,52`、
  `frontend/src/components/stock/GroupGridView.tsx:80,187`、
  `tests/server/test_stock_routes.py:508` 行尾註解 [amendment 2026-08-13: R5]、
  以及 `tests/` 內**相關 30**敘述性註解一併同步(純註解零行為;R11 明列):
  `tests/live/test_stock_state.py:308,337`、`tests/server/test_stock_routes.py:464,481`、
  `tests/server/test_stock_engine.py:1205,1215,1327`、
  `tests/server/test_watchlist_service.py:325`、`tests/server/test_signal_routes.py:763`
  [amendment 2026-08-13: R11]。**不動**無關 30:signal hub 30/分、`MAX_RULES=30`、
  candle `days=30`、TC4 重連 30 次。

### 🔴 wave 2(行為:群組標題列視覺)

先紅:`WatchlistSidebar.test.tsx` 新增 **classList token 級**斷言
[amendment 2026-08-13: R2 — `toContain("bg-surface")` 會被既有 `hover:bg-surface`
子字串誤命中,假紅 + vacuous lock]:
- `header.classList.contains("bg-surface") === true`【現況紅:classList token 只有
  `hover:bg-surface`,無裸 `bg-surface`】;
- `header.className` **不含** `hover:bg-surface`(鎖 D-2 hover 換手)【現況紅】;
- 組名 span `classList.contains("font-medium")`【現況紅】;
- 個股列容器 `classList.contains("bg-surface") === false`【**lock,現況即綠**,
  mutation 抽驗依 core-flow §4】。
再綠:`WatchlistSidebar.tsx` `sectionHeader`:
- className 加 `rounded-t bg-surface`(section 是 `rounded border`,補 rounded-t 讓
  底色帶與外框圓角對齊);組名 span `text-ink` → `font-medium text-ink`。
- hover:`drag === null && "hover:bg-surface"` 因底色帶變 no-op → 改
  `drag === null && "hover:bg-line/50"`(仍為 token;拖曳中關 hover 的守衛原樣保留)。

### 🟢 wave 3(新功能:全部展開/收合)

先紅(`[red]`,新測試):
- 部分展開時鈕文字「全部收合」;點擊 → 未分組與全部群組清單 DOM 隱藏、
  `WL_COLLAPSED_KEY` = 現行全組名、`WL_UNGROUPED_KEY` = "1"、鈕文字變「全部展開」。
- 全折疊時點「全部展開」→ 全開、set 空、"0"。
- 零群組:鈕仍作用於未分組。
- 殘留淨化:`WL_COLLAPSED_KEY` 預置已不存在的組名,點「全部收合」後值 = 現行組名
  集合(殘留被替換,與 W-20 防呆同向)。
- **自選未載入(fetch pending / 失敗)時鈕不渲染**,`WL_COLLAPSED_KEY` 既有值不變
  [amendment 2026-08-13: R1 P0]。
再綠(`[green]`):`WatchlistSidebar.tsx`
- `allCollapsed = ungroupedCollapsed && groups.every(g => collapsed.has(g.name))`。
- `toggleAll()`:全收 → `applyCollapsed(new Set(groups.map(g => g.name)))` +
  `applyUngroupedCollapsed(true)`;全展 → `applyCollapsed(new Set())` +
  `applyUngroupedCollapsed(false)`。**走既有單一寫入點**(白名單 1)。
- 落點:sticky 區塊內、搜尋列與建議清單之間加一列(位置不隨建議清單出現跳動,R8):
  `<button>`(`text-xs text-ink-dim hover:text-ink`,右對齊),
  文字 = `allCollapsed ? "全部展開" : "全部收合"`。
- **渲染受 `data === undefined` gate**(與「管理」鈕同一不變式:拿得到 EMPTY_WL 的
  寫入口不存在)[amendment 2026-08-13: R1 P0]。sticky 區塊與底部管理鈕是**不同子樹**
  → 抽單一 `wlReady = data !== undefined`(或等價單一判斷)供兩處引用,599 行既有
  長註解補一行指向新守門點,不複製第二份裸條件 [amendment 2026-08-13: R13]。

### 既有測試「該紅 / 不該紅」總表

| 測試 | 判定 |
|---|---|
| `test_stock_routes.py` over-limit 兩支 + dedup 兩支(含 R3 的重複碼支) | 參數化改寫,不紅 |
| 新增 at-limit 兩支 + 前端/bot 文案三處 | **該紅**(wave 1 [red]) |
| `test_stock_watchlist.py` / `test_watchlist_service.py`(參數化) | 不該紅 |
| `test_signal_hub.py` 節流 30/分 | 不該紅(無關常數) |
| `WatchlistSidebar.test.tsx` 既有 a11y / 折疊 / 拖曳 / StrictMode | 不該紅 |
| `WatchlistSidebar.dropcollapsed.test.tsx` | 不該紅 |
| 新增 header classList 斷言三支(R2 修訂形) | **該紅**(wave 2 [red]) |
| 新增「個股列不含 bg-surface」 | **lock**(現況即綠,mutation 抽驗) |
| 新增全收/全展五支(含 R1 的未載入 gate) | **該紅**(wave 3 [red]) |

## D. `[auto-default]` 決策記錄

1. 視覺差異手法 `[auto-default: bg-surface 底色帶 + font-medium 字重 + rounded-t |
   reason: user 指定「底色帶/字重」方向;surface 是全站既有「浮起一層」token,不需要
   新色票]`。
2. header hover `[auto-default: hover:bg-line/50 | reason: 底色帶令既有 hover:bg-surface
   no-op;line 是次一階亮度的既有 token,50% 透明疊在 surface 上為 subtle lighten;
   拖曳守衛原樣]`。
3. toggle 落點 `[auto-default: sticky 搜尋區塊下緣、右對齊文字鈕 | reason: 高頻操作要
   恆在可視範圍(sticky);放底部「管理」旁常在捲動範圍外]`。
4. 鈕語意 `[auto-default: 單顆切換、全折疊才顯示「全部展開」 | reason: 兩顆鈕佔寬;
   「有任何展開 → 提供全收」符合掃視工作流(收起來再逐組打開)]`。
5. 全收寫入 `[auto-default: 以現行組名集合**替換**(非 union 併入殘留) | reason: 順帶
   淨化改名/刪組殘留,與 W-20 同向;殘留組名沒有對應 UI,保留無意義]`。
6. 測試文案斷言 `[auto-default: 測試端保留字面值「自選已達 50 檔上限」不引常數 |
   reason: 文案是 UX 契約,引常數會讓斷言與實作同源(恆真),失去鎖定力]`。
7. 前端常數落點 `[auto-default: lib/constants.ts | reason: 既有跨元件常數(WL_* keys)
   聚集地;errText 是唯一讀者但契約註解需要一個可 grep 的錨點]`。

## E. Backward compat / migration

- 30→50 為純放寬:既存自選檔(≤30)天然合法,**零 migration**。
- 可逆性:回退 50→30 時,>30 檔的存檔進入既有「可讀但不可 normalize」態
  (discord-watchlist design 已文件化),讀路徑不炸;非新風險。
- localStorage 結構不變(全收/全展只是批次寫既有形),零 migration。
- API shape / error code 不變 → 無對外契約破壞;`OrderRecord.unit` 等其他契約不觸及。

## F. Edge cases

1. 零群組時點「全部收合」:只收未分組;`groups.every` 對空陣列為 true,故此後鈕文字
   由 `ungroupedCollapsed` 單獨決定 — 全收後正確顯示「全部展開」。
   **注意與「未載入」區分**:零群組(data 已載入、groups=[])鈕照常渲染;未載入
   (data === undefined)鈕不渲染 [amendment 2026-08-13: R1 P0]。
2. `WL_COLLAPSED_KEY` 含已刪/已改名組殘留:全收以現行組名替換(§D-5),全展清空。
3. 恰 50 檔 + 群組成員 union 補進 codes 後第 51 檔:`normalize` 照 raise
   `WATCHLIST_FULL`(既有語意,測試參數化涵蓋)。
4. group-state 51 個重複碼:先去重(≤50)→ 200(白名單 7,既有測試涵蓋)。
5. 拖曳中游標經過全收/全展鈕:鈕在 sticky 區,pointer 事件被拖曳 window listener
   接管,click 不會派發;即使派發(邊角),折疊變更後 `zonesNow` 每次 pointermove
   重算幾何,不會用到 stale rect(既有設計)。

## G. Out of scope

- boot 還原 `set_watchlist` 在 TC4 離線時 50×10s 拖慢背景 boot 的**結構性**修法
  (per-code timeout 縮短 / 並行訂閱 / breadth 提前)— 既有已知缺口,本輪只更新
  `docs/next-time.md` 數字(300s→500s)。
- 組內排序鍵盤路徑(既有 next-time 缺口)。
- 側欄其他 UX(排序、搜尋行為)與 WatchlistManagerDialog 視覺。
- TC4 訂閱檔數官方上限查證(無已知文件;真實環境驗證時觀察即可)。

---

self_review_head: e4e3082a9a305cdd568bd0f791ae923c23899902
(自評 round 1 雙 lens + fix 波收斂後之 HEAD;收尾增量 review 依據)
