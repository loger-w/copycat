# R6 群益下單批 — change-spec

分支 `mod/capital-order-batch`。需求原文 = `docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R6
的 12 條(N011 / N014 / N017 / N018 / N075 / N080 / N081 / N082 / N098 / N099 / N065 / N073),
user 全勾「做」、無附註。

---

## §0 既有行為白名單(caller map + 不得因本輪變鬆的行為)

### 0.1 真錢三道閘(CLAUDE.md §7;本輪一條都不動)

| # | 閘 | 產生點 | 本輪處置 |
|---|---|---|---|
| W1 | 下單總開關 `CAPITAL_ORDER_ENABLED` | `capital/safety.py::_master`(所有 `check_*` 的第一道) | 不動;所有新增閘一律**在它之後**或在 route 層,絕不繞過 |
| W2 | 單筆量 / 名目金額上限 `CAPITAL_MAX_QTY` / `CAPITAL_MAX_AMOUNT` | `safety.py::_check_qty_amount`(`None`=不限,user 拍板) | 不動 |
| W3 | 價格哨符 `_bad_price`(NaN / ≤0) | `safety.py::_bad_price` | 不動 |
| W4 | 個股期送單檔位閘 `_require_legal_tick` | `server/capital_api.py::_stkfut_gates`(送單)/ `_correct_price_tick_gate`(改價) | **只新增第三個 caller(close route,N098),既有兩處逐字不動** |
| W5 | 個股期產品閘 `PRODUCT_NOT_ALLOWED`(ETF / 非標準單位) | `_stkfut_gates` → `_is_tickable_stkfut` | 不動 |
| W6 | 二次確認窗 | `components/capital/CapitalConfirmDialog.tsx`(4 caller 條件掛載) | 元件本身**零改動**(N080 改的是 `useFlashArm` 的監聽相位) |
| W7 | 武裝 = 唯一繞過確認窗的路徑,清除路徑寬於進入路徑 | `lib/flash-arm.ts::reduceArm` | 不動;N081 只**加寬 `armDisabled`(進入方向)**,`ArmRow` 的 `armDisabled && !armed` 讓解除鈕恆可按 |
| W8 | append-only 審計每筆 req/res | `capital/client.py::_record` / `_audit_blocked` / `_audit_after` / `_on_late_result`(`append_audit(..., prefix="capital")`) | 不動;N082 只是讓 `req.source` 這個**既有欄位**多一個值 |
| W9 | 雙環境隔離 banner / `env` 欄 | `capital/factory.py` + `status_view()` | 不動 |
| W10 | 平倉去重鎖 `_close_dup_reason` / `_submit_close_locked` | `client.py::close_position` | 不動;N098 的閘在 route 層(更早) |
| W11 | 平倉「估不出價 → 鍵鎖住」 | `lib/futures-ladder.ts::futCloseEstimate`(≤0 → null)+ `RightRail` 的 `futKey=null` | 不動;N099 只**多一個回 null 的理由** |
| W12 | 市價鈕三態 `marketButtonState`(blocked > estimateMissing > buyLocked) | `lib/flash-send.ts` | 不動 |
| W13 | 送單前置閘 `isOrderBlocked`(前端,ETF / 非標準單位) | `lib/stkfut.ts` | 不動;N099 讓**平倉估價**多讀它一次 |

### 0.2 其餘被本輪碰到的既有行為

| # | 行為 | 產生點 | 本輪處置 |
|---|---|---|---|
| W14 | 欠帳窗語意:每個 `##` 消耗一筆欠帳;零列窗內吞、帶列照 flush;rows 不動欠帳;`_awaiting` 守門;窗外全數作廢 | `capital/balance.py::BalanceCollector` | **語意全數保留**,只把「單一 `_stale_until` + `_owed` 計數」換成 per-debt deadline deque(N017) |
| W15 | `_stale_until` / `_owed` 兩個私有欄位是 5 支既有測試的觀測窗 | `tests/capital/test_balance.py` / `test_client.py` | 保留為**唯讀 property**(deque 導出),既有斷言零改動 |
| W16 | `reset(keep_abandoned=True)` 把欠帳窗帶進下一輪 | `client.py` 三段查詢 | 不動 |
| W17 | 價格別標籤 fail-safe 方向 = 「只會缺標籤,不會誤標」 | `capital/store.py::note_price_type` / `_price_type_of` | **不得變鬆**(見 §1 N075 的判定) |
| W18 | `OrderRecord.unit` 字面值(張/口/股)是前端過濾鍵(CLAUDE.md §4) | `store.py::_to_record` | 不動 |
| W19 | `GET /api/capital/positions` 每列附衍生欄 `code`(反查不到 = `null`,不 500) | `capital_api.py::capital_positions` + `mapping.py::stock_code_of` | 不動;N065 由**前端**就地數 `code === null`,不加新 wire 欄 |
| W20 | `positionsByCode` 跳過 `code` null 的 fut 列(猜股號比不顯示糟) | `lib/position-summary.ts` | 不動;N065 只在側欄底加一行提示 |
| W21 | 拖曳落點作廢 → 高亮回來源組(三種 null 落點同一條) | `WatchlistSidebar.tsx::onHandleDown` 的 `move` | 保留;N014 只加「作廢」的**視覺可辨性** + `to` 未變回同 reference |
| W22 | `EMPTY_MARKS` / `EMPTY_FILLS` / `EMPTY_PEGS` 模組層常數 identity 穩定 | `lib/fill-marks.ts` 等 | 不動;N073 只補**測試**(零 production 改動) |
| W23 | `CapitalConfirmDialog` 的 `stopPropagation`(窗開著時 Esc 只作用於窗) | `CapitalConfirmDialog.tsx` | **不動**(見 N080 判定:改的是 window 監聽的相位,不是窗) |

### 0.3 caller grep 結果(動態用法一併查過)

- `abandon(` → `client.py:391`(balance 逾期解卡)、`client.py:514-515`(pending watchdog 對 profit/oi);
  測試 `test_balance.py` ×9、`test_client.py` ×2(其中 1 處以 `_spy` **動態替換** `client._balance.abandon`,
  簽名 `(now_monotonic=None)` 必須保留)。
- `_stale_until` / `_owed` → 只在 `balance.py` 內部 + 上述測試;無 production 讀者。
- `note_price_type` → `client.py:754`(唯一 production caller,經 `_note_price_type`),測試 ×8。
- `_require_legal_tick` → `_stkfut_gates`、`_correct_price_tick_gate`(本輪 +close route)。
- `source:` (前端送單 payload) → `PriceLadder` ×2、`StkfutLadder` ×2、`FuturesLadder` ×2(`"flash"`)、
  `OrderPanel` ×1(`"panel"`);後端 `source: str = "panel"` 三個 body、`PositionCloseRequest.source`。
- `armDisabled` / `lockDisabled` → `ArmRow.tsx` 定義,`PriceLadder`(經 `LadderView`)/ `StkfutLadder`
  (經 `LadderView`)/ `FuturesLadder` 三處;`LadderView` 是 pass-through。
- `isOrderBlocked` → `StkfutLadder.tsx:121`(唯一 production caller,本輪 +`RightRail`)。
- `EMPTY_MARKS` → `StockIntradayChart.tsx:1005`(唯一 production 讀者)。

---

## §1 逐條處置

### N011 OrderPanel kind 單向靜默收斂 — 🔴

**判定**:移除 render 期間的 `setKind("limit")` 收斂,改「`disabled` 只擋**進入**方向 + 送出鈕
已 disabled 再補一句可見理由」。

理由:原實作把使用者選的「市價」在估價空窗(WS 快照未到)時**單向**翻成限價且不還原 ——
估價回來後畫面停在限價,使用者以為還在市價。`formInvalid` 本來就含
`kind === "market" && marketEstimate == null`,送出鈕早已 disabled,所以「不翻」不會放行任何單。
市價 pill 的 `disabled` 改成 `marketEstimate == null && kind !== "market"`,與 `ArmRow` 的
「disabled 只擋進入方向」同一條慣例 —— checked 的那顆不再 disabled,原註解擔心的
「整組從鍵盤消失」也一併不成立。估價回來 → `formInvalid` 自然轉 false = 條文的「估價回來時還原」。

**事前標「該變」的既有測試**:`OrderPanel.test.tsx` 的
`A11Y-2:市價態換到無估價合約 → 收斂回限價,radiogroup 仍有可聚焦項` —— 它鎖的正是本條要
推翻的「單向收斂」。改寫成新語意(市價維持 checked 且**不** disabled、送出鈕 disabled 且帶
可見理由、換回有估價合約即恢復)。同檔
`市價估價:snapshot 估價入 payload;無估價合約鎖市價選項` 的**尾段三行**同理(它在選了市價
之後換到 PUT 再 `expectMarketLocked()`)—— 換成同一組新斷言。`expectMarketLocked()` 本身
與另兩個呼叫點(`kind` 停在限價、只是「不能進入市價」)語意不變、不改。

### N014 註解改口 + drag reference + 邊價等值 lock + 作廢視覺 — 🔴 + 🔵

四個子項:

1. **(🔵)** `RightRail.tsx:285` / `futures-ladder.ts:156` 的「後端會 400 BAD_TICK」改口。
   本輪 N098 之後平倉路由**確實**會對 tickable 個股期驗檔位,所以不是刪掉而是**寫準**:
   點名 close route 的閘(N098)、並保留「前端 edgeOf 是第一道守門」的事實。
2. **(🔴)** `WatchlistSidebar.tsx` 的 `move`:`to` 未變時回**同一個** `drag` reference
   (`setDrag` 的 updater 回 `p` 本身)。原實作每個 `pointermove` 都造新物件 → 整個側欄
   每幀重繪;症狀只是拖曳掉幀,零錯誤訊號。
3. **(🟢 測試)** 兩處邊價顯式等值 lock:`stkfutMarketEdgeMilli` × `futCloseEstimate(…, stkfutMarketEdgeMilli)`
   與 `futMarketEdgeMilli` × `futCloseEstimate(…)` 各一條 —— 「市價鈕送的價」與「平倉鍵估的價」
   必須同值,靠註解維持的相等關係本輪起有機械閘。
4. **(🔴)** 作廢態視覺回饋:`drag` 加 `voided` 旗標,作廢時被拖的列 `opacity-30`、
   高亮的來源組框改 `border-dashed border-ink-dim`(不是實線 accent)—— 現況「作廢」與
   「停在來源組上」畫面完全同形。

   **事前標「該變」的既有測試**(N014-4 的直接後果,兩條的**語意**「高亮回到來源組」
   不變,只有框的 class 從 `border-accent` 換成 `border-dashed`):
   `WatchlistSidebar.test.tsx` 的 `拖曳中移入作廢帶 → 落點高亮回到來源組(不是最上面那組)`
   與 `拖曳中移到側欄外 → 落點高亮同樣回到來源組(null 落點一致)`。
   兩條裡「主力/未分組**不**帶 `border-accent`」的負向斷言逐字不動。

### N017 欠帳窗逐筆化 — 🔴

**判定**:`_stale_until`(單一 deadline)+ `_owed`(計數)→ `_debts: deque[float]`(每筆欠帳
各自 deadline);`_settle_debt` 先 popleft 掉所有已過期的欠帳,再走既有的消耗路徑。

理由:`abandon()` 把**同一個** `_stale_until` 推到 `now + 20`,等於替所有未清欠帳續命 ——
profit / OI 兩段的 abandon 相距可達 60s,第 1 筆早該過期卻跟著第 2 筆的窗活著,於是多吞
一次合法的空回應(= 真空帳戶多掛一輪幽靈部位)。deque 的 deadline 單調遞增(monotonic clock),
popleft-while 即正確。

`_stale_until` / `_owed` 保留為**唯讀 property**(`_debts[-1]` / `len(_debts)`)——
5 支既有測試以它們當觀測窗,語意(「窗開著嗎」/「還欠幾筆」)在 deque 下不變,零 assertion 改動。

### N018 R7 P2 三條 — 🔴

1. 吞終止符 WARNING 帶 collector 名:`BalanceCollector` 加 `name` 建構參數(預設 `"balance"`),
   client 三個 collector 各自具名(`balance` / `profit` / `oi`);WARNING / DEBUG 逐行帶名。
   現況三段共用同一句文案,prod log 裡分不出是哪一段被抑制。
2. `_set_status("ok")` 改專用 `clear()` 不走 `reset()`:`reset()` 會把 `_awaiting` 設成 **True**
   (= 「已發查詢、等回應中」),但重連落地時根本沒有在途查詢 —— 下一次 watchdog 的
   `abandon()` 於是對它記帳成功,白吞一輪合法空回應。`clear()` = 清 staging / deadline / 欠帳
   且 `_awaiting = False`。
3. `_query_open_interest` 無期貨帳號提前 return 時清 `_oi_abandoned`(並 `clear()` 掉 OI collector
   的欠帳):該路徑永遠不會再發 OI 查詢,旗標與欠帳留著只是 write-only 的殘留狀態,
   一旦日後拿到期貨帳號,第一次 `reset(keep_abandoned=True)` 會白吞一輪。

### N075 委託列表「市價」標籤的日界語意 — 🔴

**判定:採交易日口徑(`trading_calendar`),且以「本機日 + 交易日兩個候選,任一相符即帶出」
的加法形式落地。不採 ±1 日窗。**

理由(user 要求寫進 change-spec):

- 條文的兩個候選是「交易日口徑(`trading_calendar`)」與「±1 日窗(與前端 `ymdWindow` 同口徑)」。
  交易日口徑產生的日期**恆落在** `ymdWindow(now, [-1,0,1])` 之內(夜盤最多推進一個交易日),
  所以選它與前端 ladder 的 ±1 窗口徑**不衝突** —— 它是那個窗的一個子集。
- ±1 窗會**額外接受「昨日」**。而 `note_price_type` 的 docstring 已寫明日期界的存在理由正是
  「server 長跑、券商 seq 若重用,沒有日期界就會把今日的限價單標成昨日那張的『市價』」——
  往回放一天等於把那條誤標路徑重新打開。真錢面板上既有的 fail-safe 方向(§0 W17:
  只會缺標籤、不會誤標)不得因本輪變鬆,所以 ±1 出局。
- 純粹改記「交易日」而丟掉「本機日」也不行:群益回報的 `_Agg.date` 到底是本機日還是交易日
  **未實證**(原 docstring 自承)。若它是本機日,單記交易日會讓**今天還會標的夜盤單反而失標** ——
  用未實證的假設換掉一個現在可能有效的比對,是拿功能去賭。故記兩個候選:
  比對集合是舊行為的**超集**,永不失標;新增的那一天是**唯一**一個有語意根據的日子(該筆
  委託所屬的交易日),不是任意的 ±1。
- prune 規則同步改成「候選集合與新項不相交才刪」——否則夜盤那筆會被同交易日的日盤單順手清掉。

實作:`TradingCalendar` 加 `next_trading_day(d)`(`last_trading_day` 的鏡像,同一條保險絲);
`client.py` 加 `_trade_ymd()`(≥15:00 → 次日起算的下一個交易日;<05:00 → 含今日的下一個交易日;
其餘 → `last_trading_day`),日曆載入失敗降級 `WEEKEND_ONLY` + WARNING(標籤路徑不得炸掉
COM 執行緒的送單結果處理)。`store.note_price_type(seq, price_type, date, *, trade_date=None)`。

**事前標「該變」的既有測試:無。** 上述設計是加法,`test_price_type_not_applied_across_days`
與 `test_note_price_type_prunes_other_days`(兩者都不帶 `trade_date`)語意逐字不變、照樣綠。

### N080 CapitalConfirmDialog 開著時 Esc 不解除鎖定 — 🔴

**判定**:`useFlashArm` 的 Esc 監聽改 **capture 相位**(`addEventListener("keydown", onKey, true)`);
`CapitalConfirmDialog` 一個字不改。

理由:窗內 `stopPropagation()` 擋的是**冒泡**;window 的 capture 監聽在事件下行時先跑,
兩邊各自拿到一次 Esc —— 窗照關(它的處理沒被剝奪)、武裝/鎖定照解除。反過來若去動窗的
`stopPropagation`,會連帶影響那 4 個 caller 的所有 Esc 語意(含非武裝態),blast radius 大得多。
`flash-arm.ts::LOCK_TITLE` 的承諾(「斷線 / 連 3 敗 / Esc / 解除仍會解除」)本輪起才是真的。
條文自承「改 capture 監聽屬 🔴」,user 已勾做 → 以 🔴 commit。

### N081 未鎖定時 WS closed 期間仍可武裝 — 🔴

**判定**:三座梯的 `armDisabled` 一併吃 `arm.wsStatus !== "open"`;新增 `ARM_WS_TITLE` 常數。

理由:鎖定鈕早已在非 open 時 disabled(SC-13),武裝鈕沒跟進 = 同一個「連線未就緒」在同一列
上有兩個答案。`ArmRow` 的 `disabled={armDisabled && !armed}` 保證只擋**進入**方向,
已武裝時解除鈕恆可按(W7 不變)。文案優先序:個股期 `blocked` > 連線;期貨「合約未解析」> 連線
(前者是更根本的「送不出去」)。

**事前標「該變」的既有測試 1 條**:`ArmRow.characterization.test.tsx` 的 `FUTURES_ARM_ROW`
逐字 DOM(該檔 `beforeEach` 是 connecting)—— 武裝鈕多了 `disabled` / `title` / `opacity-40`,
正是本條要加的東西。其餘五條 characterization(直接 render `LadderView`,`armDisabled` 走預設)
逐字不動。

**setup 變更(非 assertion)**:`PriceLadder` / `StkfutLadder` / `FuturesLadder` / `RightRail`
四個測試檔的 `beforeEach` 預設 wsStatus 由 `"connecting"` 改 `"open"` —— 既有的「武裝後…」案
在新閘下會被擋在門外(前提改變,不是期望改變),所有斷言逐字不動。要驗連線閘的案
(`PriceLadder` SC-13 與本輪新增的 N081 案)自己顯式設 `"connecting"`。

### N082 後端 `source="flash-locked"` 稽核 — 🔴(前端產生點)

**判定**:前端六個送單點的 `source` 改 `flashSource(arm.state.locked)`(新 helper 在 `lib/flash-send.ts`);
後端**零改動**(`source: str` 本來就可擴,`_record` 已 `dataclasses.asdict(req)` 把它寫進
`capital-YYYYMMDD.jsonl`)。舊值 `"flash"` / `"panel"` 語意不變。
後端補一條 route→審計檔的端到端 lock(送 `source="flash-locked"` → 審計行的 `req.source` 相同)。

### N098 後端個股期平倉路徑補 tick 閘 — 🔴

**判定**:`capital_position_close` route 在 `market == "fut"` 時由 `body.key`(期交所契約碼)
反查 product → `lookup_product` → `_is_tickable_stkfut` 為真才 `_require_legal_tick(body.price)`。
判準與送單面 / 改價面**共用同兩支函式**,不新寫規則。

不變的邊界(白名單):`market == "sec"` 整條不碰;契約碼推不出產品(`ValueError`)/ 非個股期
(指數期權)/ ETF 期貨與除權息調整腿 → **放行**(現股 tick 表不適用,與 `_correct_price_tick_gate`
同一條逃生口)。

### N099 ETF / 除權息調整腿的平倉估價回 null — 🔴

**判定**:`RightRail` 的個股期 `closePriceOf` 在 `isOrderBlocked(code, contract.unit)` 為真時直接回
`null`(= 平倉鍵鎖住),比照送單面。

理由:現況那些腿的 `closePriceOf` 拿**現股 tick 表**去 snap(0.01 倍數),對 ETF 期貨的 0.05 檔位
是「嚴格改善」但仍是猜的;送單面對同一組腿一律 `PRODUCT_NOT_ALLOWED`,平倉鍵卻放行 =
同一個標的兩個答案。N098 之後後端也會擋(其實不會 —— 那些腿走 `_is_tickable_stkfut` 為 false
的放行分支),所以前端這道是**唯一**的守門,更該與送單面同口徑。

### N065 `code` null 的個股期倉位三處靜默不顯示 — 🔴

**判定**:`lib/position-summary.ts` 加純函式 `unmappedFutCount(positions)`(fut + `qty !== 0` +
`code` 為 null/空),`WatchlistSidebar` 底部渲染一行「n 筆個股期倉位無法對映」(n=0 不渲染)。

理由:條文候選是「positions 回傳 `code_missing` 計數」,但 `code: string | null` **已經在 wire 上**
(§0 W19),再加一個聚合欄等於同一事實兩個來源、多一條會漂的跨檔契約。前端就地數是同一份
真相的投影。三處顯示(chip / header / 群組卡)的既有「跳過」行為不動。

### N073 toggle 關態 `EMPTY_MARKS` identity 無機械閘 — 🟢(補測試,零 production 改動)

**判定:做得出來,做。**(條文寫「若日後改 ChartStatic memo 契約,順手補 render-count 閘」;
cr1 當時 rejected 的理由是「關態沒有可計次函式」—— 那是**在 `fill-marks` 這支 lib 裡**找不到,
關態確實不呼叫 `projectFills` / `fillTrianglePoints`。)

可計次的探針在別處:`ChartStatic` 的 **render body**(不在任何 `useMemo` 內)無條件呼叫
`stock-intraday-svg::buildVwapLabel`。以 `importOriginal` partial mock 把它換成 delegate 計次版,
`toggles.fills = false` 下 render → `fireEvent.mouseMove`(hover 使父層 re-render 但 ChartStatic
的 props 全部 identity 穩定)→ 斷言計次不增。把 `EMPTY_MARKS` 換成行內 `[]` 的 mutant 會讓
`fillMarks` 每輪新 identity → memo 被打穿 → 計次 +1 → 紅。

---

### 收尾:react-doctor 驅動的兩支抽取 — 🔵

N081 / N099 的實作把 `RightRail.tsx` 與 `StkfutLadder.tsx` 推過 `no-giant-component` 門檻
(全量掃描交叉驗證:換回 master 版本後那兩個 finding 消失 → **本輪新增**,依 gate 屬 FAIL)。
修法不是調 config 也不是 suppress,而是把本來就該在 module 層的兩段搬出去:

- `RightRail::stkfutClosePriceOf(code, contract, meta)` — 個股期平倉估價的四條規則
  (契約碼算不出來鎖住 / 邊價走股票 tick 表 / N099 blocked 腿回 null / `code` 缺時的
  fallback 方向)本來就是純函式。
- `flash-arm::armGate(wsOpen, blockedTitle?)` — 武裝鈕的 `disabled` + `title`,含
  「商品面理由優先於連線理由」的優先序。三梯各寫一次三元式的失效樣態是「兩個理由同時成立時
  其中一梯印出另一句」—— 畫面照常,使用者被指向錯的原因。

行為不變(前端全綠,含 `ArmRow.characterization` 的逐字 DOM 鎖)。

---

## §2 backward compat

- **審計檔**(`capital-YYYYMMDD.jsonl`):欄位形狀不變。`req.source` 多一個值 `"flash-locked"`;
  舊行落檔的 `"flash"` / `"panel"` 照舊,無讀者需要改(檔案是 append-only 人看的)。
- **`GET /api/capital/positions`**:回應形狀零改動(N065 不加欄)。
- **`POST /api/capital/position/close`**:body 形狀不變;**新增**一個 400 `BAD_TICK` 回應
  (僅 tickable 個股期 + 非法檔位)。前端平倉鍵的估價一律走 `stkfutMarketEdgeMilli`(已 snap),
  正常路徑打不到;打得到的情境本來就是券商退單。
- **`BalanceCollector`**:公開方法簽名不變(`abandon(now_monotonic=None)` 保留 —— 測試以動態
  替換用它);新增 keyword-only `name`。`_stale_until` / `_owed` 由欄位變唯讀 property,
  只有測試在讀。
- **`CapitalStore.note_price_type`**:新增 keyword-only `trade_date`(預設 None = 舊行為)。
- **`TradingCalendar`**:新增 `next_trading_day`,既有方法不動。
- **前端**:`flash-arm.ts` 新增 `ARM_WS_TITLE`;`flash-send.ts` 新增 `flashSource`;
  `position-summary.ts` 新增 `unmappedFutCount`。皆為 additive。

---

## §3 seams(測試只寫在這些 seam)

| seam | 覆蓋條 |
|---|---|
| `BalanceCollector`(純狀態機,注入 clock) | N017 / N018-1 |
| `CapitalClient` + `FakeCom`(COM 執行緒真跑,零真登入) | N018-2 / N018-3 |
| `CapitalStore`(純記憶體) | N075 |
| `TradingCalendar`(純函式) | N075 |
| FastAPI `TestClient` + `FakeCom`(route → client → 審計檔) | N082 / N098 |
| `lib/*.ts` 純函式(`futures-ladder` / `stkfut` / `position-summary` / `flash-send`) | N014-3 / N099 / N065 / N082 |
| RTL 元件(`OrderPanel` / `ArmRow` 三梯 / `WatchlistSidebar` / `IntradayChartCore`) | N011 / N014-2,4 / N080 / N081 / N073 |

真錢紀律:全部走 `tests/conftest.py` 的憑證中和 + `FakeCom`,無任何腳本會碰群益正式環境,
`.env` 不動。

## 4. two-axis review round 1 修正(主 session)

- **W17 措辭改精確(review ST1/SP1)**:N075 的候選日多開「所屬交易日」一天,是 seq 重用的誤標窗(群益 seq 是日曆日還是
  交易日重置**未實證**)。收修:`note_price_type` 綁 `stock_no` + `buy_sell`(回報口徑 "B"/"S"),帶出時同名欄位必須等值;
  期貨單只綁方向(`tc4_symbol` 與回報契約碼不同域)、平倉經送單函式一併綁;`_on_late_result` 同款。
  W17 自此成立的形式 = 「同 seq + 同標的 + 同方向 + 候選日相符才帶出;任一不符只缺標籤」。
- **SP3**:鎖定態的梯上平倉(`FuturesLadder.confirmClose`)`closeBodyOf(pos, est, "flash-locked")`;未鎖 / 面板路徑不帶
  `source`(後端預設 panel,舊契約零改)。
- **ST5**:OrderPanel 兩句同義文案收 `MARKET_ESTIMATE_MISSING`(pill title 與提示同句;本輪新測試的 title 期望跟改)。
- **SP2**:`useFlashArm.test` 補真 `CapitalConfirmDialog` 端到端案(窗 onCancel 恰一次 + 鎖定同時解除)。
- **ST3**:`test_client.py` 未用 import 與 noqa 清掉、stdlib import 順序。
- 反駁:**ST2**(四檔 `beforeEach` wsStatus `connecting→open` 是前提變更非改斷言,SC-13 自身保留 `connecting` 覆蓋;
  只在 `armUp()` 內設 open 會讓「非武裝路徑在 connecting 下」的既有案語意跟著漂,受影響面反而更難說清);
  **ST4**(route 層 tick 閘早於 client 的 `CAPITAL_ORDER_ENABLED`,與既有 `order/future` / `correct-price` 兩個 caller
  同一順序 —— 三處一致優先;總開關關閉時仍是 client 層擋,安全語意不變)。
