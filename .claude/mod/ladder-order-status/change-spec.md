# change-spec — 閃電梯掛單顯示 + 庫存刷新提速

/mod L 級。分流判定:**已成形**(user 指名做法 + 資料源 + 落點檔案;調研已做)→ grilling
姿態,無方向性抉擇 → 全部細部決策以 `[auto-default]` 落檔,不停等。

## 決策記錄(auto-defaults)

- [auto-default: 已成交量 = 同契約+同委託價+同側**所有**單的 `filled_qty` 聚合(不看
  actionable)| reason: user 點名「actionable=false 的全部成交單也要計入」;泛化到所有單
  可一併正確涵蓋「部分成交後刪單」(已刪單帶 filled_qty>0,成交是事實不該消失);失敗/
  退單 filled_qty 恆 0 自然不進來,不需要另查狀態表(前端不抄狀態表是 OrderRecord 契約)]
- [auto-default: 未成交=0 且已成交>0 → 顯示 `(N)` 為**不可點徽章**(span,非 button)|
  reason: 無 seq 可刪,保留 button 形同「可刪」的假訊號;樣式沿紅方格幾何但降為 muted
  邊框色,與可刪紅方格視覺區分]
- [auto-default: 期貨梯(FuturesLadder)**不走 LadderView**,在自己的渲染路徑 + splitMyLots
  同步實作 | reason: user 前提「三座梯共用 LadderView」與實況不符(現況表);讓「三座梯
  一體受益」的意圖成立,需在期貨梯自有路徑補同款顯示,不做合併重構(版面鐵律:武裝中
  點擊目標不位移,重構期貨梯渲染超出本次 scope)]
- [auto-default: 期貨梯紅方格維持**不分買賣側**(既有單一格)| reason: 既有語意;同價
  同時掛買+掛賣會自成交,實務罕見;分側需改 FutLadderRow shape 與版面,風險大於收益。
  格式同款 `未成交(已成交)`,聚合含兩側]
- [auto-default: 先 🔵 抽共用 `aggregateLots` 到 `lib/ladder-lots.ts` | reason: PriceLadder
  / StkfutLadder 兩份逐字相同(現況表),本次要同改兩處 — 先合一再改,行為擴充只寫一次]
- [auto-default: 改價單的已成交量跟著最新委託價顯示 | reason: `OrderRecord.price` 是最新
  委託價(P/B 更新),殘量既有語意亦如此;逐 fill 價位化需後端逐筆成交明細,非本次資料源]

## SC(成功條件)

- **SC-1 現股梯格式**:買側同價掛 2 張、成交 1 張 → 該價位列左緣紅方格顯示 `1(1)`;
  點擊仍逐 seq 直刪(僅活單 seq)。賣側對稱。
  驗證:`npm test -- PriceLadder`(既有 SC-7 案 assertion 更新 + 新案)。
- **SC-2 全成交徽章**:同價全部成交(殘 0、成交 N)→ 顯示 `(N)`,**非 button 不可點**
  (`data-testid="ladder-filled-lot"`);失敗/退單(filled 0)無任何徽章。
  驗證:`npm test -- PriceLadder`(新案:查無「刪 {價}」button、徽章 textContent `(2)`)。
- **SC-3 個股期梯同款**:比對鍵仍是期交所契約碼;格式與徽章同 SC-1/SC-2。
  驗證:`npm test -- StkfutLadder`。
- **SC-4 期貨梯同款**:splitMyLots 輸出加 filled;自畫列紅方格 `未成交(已成交)`、全成交
  轉徽章。驗證:`npm test -- futures-ladder`(lib 案)+ `npm test -- FuturesLadder`。
- **SC-5 balance debounce 0.5s**:成交回報後 `_balance_due − monotonic() ≤ 0.5`(容差
  +0.05);連續成交仍只查尾端一次(merge 語意 = due 重設,既有)。
  驗證:`.venv\Scripts\python -m pytest tests/capital/test_client.py -q`(新 assert 釘上界)。
- **SC-6 即時更新(既有鏈,零改動)**:成交 → `/ws/capital` `capital_order` → 200ms
  debounce invalidate → 紅方格數字變化。
  驗證:自動化 = 既有 useCapital 測試不紅;真實環境 = 盤中掛單成交目視(驗證窗口:交易日
  08:45-13:45;窗口外降級:testid/格式以測試 + 截圖 mock 資料佐證)。

畫面可指認表述(UI 驗收):價位列左緣(買)/右緣(賣)的紅底方格,文字由單一數字變
`1(0)` 型;全成交後同位置變無紅底的灰邊 `(1)` 徽章,滑鼠點擊無反應。

## 不能破壞的既有行為白名單

1. 點紅方格逐 seq 直刪:cancel bodies 逐筆 `{seq_no, market: "sec"|"fut"}`,順序與筆數不變;
   **徽章(殘 0)不得觸發 cancel**。
2. 他契約 / 他檔 / 現股單過濾不變(比對鍵:現股=股號、期貨/個股期=期交所契約碼)。
3. 市價單(price null)不上階梯(含其已成交量 — 既有語意)。
4. 武裝/點價/500ms 防抖/idle 解除/Esc 全不動;點價鈕 flex-1 佈局不動(紅方格寬度隨字數
   增長屬既有行為)。
5. 部位條、打平/均價標記、市價買賣列、跟隨置中全不動。
6. 後端:連續成交只查一次 balance(due 重設語意)、60s stale 輪詢、degraded 也查、
   查詢串行鏈(balance→profit→OI)全不動;**只縮預設 delay 值**。
7. 前端 `INVALIDATE_DEBOUNCE_MS = 200` 不動;**送單路徑(submit/cancel/close)零觸碰**。
8. `/api/capital/orders` 契約與 OrderRecord 欄位零改動(純前端消費)。

## Backward compat / migration

無對外 API、無持久化格式、無 migration。純 UI 顯示 + 內部 debounce 預設值。可逆 = revert。

## Edge cases

1. 部分成交後刪單(已刪單 filled_qty>0):filled 計入、殘量不計、seq 不進刪單清單。
2. 全成交後同價再掛新單:徽章回升為 button,顯示 `新殘量(累計成交)`。
3. 失敗/退單/逾時(filled 0):不產生 entry,無徽章(與現況同 = 零痕跡)。
4. 同價多筆混合(活單×2 + 全成交×1):qty=Σ活單殘、filled=Σ全部、seqs=活單 only。
5. 改價單:含已成交量整筆跟最新委託價列顯示(auto-default 第 6 條)。
6. 期貨梯漲跌停截斷外的價位:lot 不在 rows 內就不顯示(既有語意,零改動)。

## Out of scope

- 期貨梯買賣分側(auto-default 第 4 條)。
- 逐 fill 價位明細(需成交明細資料源)。
- FuturesLadder 合併進 LadderView(重構另案)。
- OrdersList / 委託列表任何顯示(已有完整狀態欄)。
- 前端 200ms debounce、TQ 輪詢間隔調整。

## Diff 級計畫(三類分開)

### 🔵 refactor(行為零變更,先行)
- **新 `frontend/src/lib/ladder-lots.ts`**:`aggregateLots(orders, key: string | null)`
  自 PriceLadder/StkfutLadder 逐字搬移(null 早退合併);`LadderLot` 型別自 LadderView
  re-export 或移入此檔(LadderView import 回來,避免循環)。
- **`PriceLadder.tsx` / `StkfutLadder.tsx`**:刪檔內副本改 import。
- 既有測試:全不該紅。

### 🟢 test [red](該紅的 assertion 改動 + 新案)
- `PriceLadder.test.tsx`:SC-7 案 `"4"` → `"4(1)"`、`"1"` → `"1(0)"`;新案 SC-2(全成交
  徽章 + 失敗單零痕跡 + 徽章不可點不觸發 cancel)。
- `StkfutLadder.test.tsx`:`"4"` → `"4(1)"`、`"1"` → `"1(0)"`;新案同上(可精簡)。
- `FuturesLadder.test.tsx`:`"4"` → `"4(1)"`;新徽章案。
- `frontend/src/lib/ladder-lots.test.ts`(新):聚合口徑 4 edge 案。
- `futures-ladder.test.ts`:splitMyLots 加 filled 欄案。
- `tests/capital/test_client.py`:新 assert `_balance_due − monotonic() ≤ 0.55`。

### 🔴 行為改動 [green]
- **`lib/ladder-lots.ts`**:`LadderLot` 加 `filled: number`;聚合納入全部單的 filled_qty;
  entry 條件 qty>0 或 filled>0。
- **`LadderView.tsx`** 234-346 價位列:lot.qty>0 → button 文字 `${qty}(${filled})`;
  qty=0 且 filled>0 → span 徽章 `(${filled})`(muted 樣式、`data-testid="ladder-filled-lot"`)。
- **`lib/futures-ladder.ts`**:`MyFutLot`/`FutLadderRow` 加 filled 欄;splitMyLots 同口徑。
- **`FuturesLadder.tsx`** 410-419:同款 button 文字 / 徽章分支。
- **`copycat/capital/client.py:323`**:`delay_s: float = 2.0` → `0.5`。

### 既有測試紅/不紅預告
該紅:三座梯紅方格 textContent 案(上列)。不該紅:其餘全部(含 test_client 1146-1161、
點刪 seq bodies、他契約過濾、部位條、武裝、useCapital)。

---

## [amendment 2026-08-13: spec review round-1(P0×1/P1×4/P2×6 全 accepted)]

### R1(P0)balance 鏈 in-flight 守門 — 白名單 6 原陳述不成立,🔴 後端條目改寫

`_maybe_query_balance` 無 in-flight 守門:縮到 0.5s 後,鏈(balance→profit→OI,
`_PENDING_TIMEOUT_S=8.0`)進行中第二筆成交可再發 GetRealBalance → 群益 1019 +
`_pending_sec` 被覆寫 → 第一輪 OI 完成 finalize 後,第二輪 profit rows 走「遲到丟棄」
分支 → 該輪部位均價/pnl 整批遺失。**delay 值本身就是串行化的安全邊際**,不能只縮值。

🔴 後端條目改寫(取代原「只改 323 行預設值」):
- `client.py` 加 `_balance_inflight_until: float | None`(monotonic deadline;新常數
  `_BALANCE_CHAIN_TIMEOUT_S = 10.0` — 覆蓋 pending 8s + balance 段 1s flush 保險)。
- `_maybe_query_balance`:inflight 未逾期 → **return 不清 `_balance_due`**(鏈結束後
  下一輪幫浦補查,成交不漏);逾期 → 清旗標放行(**零事件死查詢** collector `poll()`
  在 `_last_feed is None` 時早退、永不 flush — deadline 是唯一解卡通道,已讀
  balance.py:228-231 證實)。發查詢時設旗標;rc != 0 即清(鏈未啟動)。
- `_finalize_positions` 發布時清旗標(`_poll_pending` 逾時與 OI 失敗路徑都會走到)。
- `_mark_balance_dirty` 預設 2.0 → 0.5(原條目保留)。
- 白名單 6 改寫:「串行鏈非重疊語意由 in-flight 守門維持,非由 delay 值維持;
  連續成交合併(due 重設)/60s stale/degraded 也查全不變」。

新 SC-7:鏈進行中再成交不重發 GetRealBalance,鏈結束後補查一次;守門逾期自動解卡。
驗證:pytest 新案(FakeCom 計 get_real_balance 次數;紅先行 — 現況無守門會發第二次)。

### R2(P1)actionable 殘 0 活單不得失去刪單入口

「D 先到 N 未到」(store.py:86 註)與改量亂序期存在 actionable 且 `order_qty-filled_qty=0`
的活單,現況渲染可點紅方格 `"0"`。徽章條件收緊:`qty === 0 && seqs.length === 0 &&
filled > 0` 才轉徽章;**seqs 非空一律維持 button**(顯示 `0(N)`)。白名單補:
「actionable 但殘量 0 的單仍必須是可點紅方格」。ladder-lots.test.ts 加案。

### R3(P1)該紅預告補列 + SC-4 驗證補 tsc

- `futures-ladder.test.ts` splitMyLots 3 案(139-142/155/160)`toEqual` 精確比對 →
  **該紅**;其中 **155 案語意該變**(`order_qty=2, filled_qty=2` 從「全排除」變
  「產出 filled 條目」— 鐵則 E 事前標記:此 assertion 該變)。
- `futures-ladder.test.ts:67` buildFuturesLadder 的 `myLots` literal 在 `filled` 必填後
  **tsc 紅(vitest 可能仍綠)** → SC-4 驗證指令補 `npx tsc -b`。

### R4(P1)seqs 收集規則釘死 + 全撤白名單

- 🔴 兩個 lib 條目本文釘死:**filled 貢獻不得產生 seq/seqNos**(僅 actionable 單的 seq
  進 seqs;filled-only entry 的 seqs 恆空)。
- 白名單補:「FuturesLadder 全撤:`allSeqNos` 只含活單 seq;本契約僅剩全成交徽章時
  全撤鈕維持 disabled + title『無本契約活單』」。FuturesLadder.test 加 assert。

### R5(P1)filled 聚合加日期界(store 跨日不清)

`CapitalStore.clear()` 全 repo 無 caller、`orders()` 含昨日預約單、prod server 跨日長跑
→「所有單」無日期界會長出昨日幽靈徽章。規則細化:
**filled 計入條件 = `o.actionable || o.date === todayYmd`**(活單的成交恆計 — 覆蓋昨日
建立、今日成交中的預約單;終態單只計今日建立)。已知縮限:昨日建立、今日全成交的
預約單其 filled 不顯示(date=委託建立日)— 記 Known Risks,量級罕見且 fail-safe。
`todayYmd` 由 container 每 render 以 `new Date()` 算(YYYYMMDD,與 OrderRecord.date
同格式;FuturesLadder todayOf 同型邊界慣例)。Edge cases 補「跨日殘留單」案。

### R6(P2)現股梯聚合加單位閘

零股(TL/TC,unit="股")同股號單現況即漏進張梯(既有洩漏,僅活單可見);聚合所有單後
擴大到終態徽章(量級錯千倍)。修法:共用 `aggregateLots` 加 `unit` 參數(現股梯傳
`"張"`、個股期傳 `"口"`),過濾 `o.unit !== unit`。**顯式行為修正**(白名單 2 改寫:
現股梯不再顯示零股單紅方格;其刪單入口仍在委託列表)。測試補零股案。

### R7(P2)期貨鏈三段逐行點名

splitMyLots 的 `!o.actionable` 早退(:50)與 `remaining <= 0` skip(:52)改寫為
filled/seqs 分流;`buildFuturesLadder` rows 對映補 `myFilled: lotMap.get(...)?.filled ?? 0`;
`FuturesLadder.tsx:410` 渲染分支 `r.myQty > 0` → `r.myQty > 0 || r.mySeqNos.length > 0`
(button)/ else `r.myFilled > 0`(徽章)。SC-4 lib 案加「rows 帶得到 myFilled」assert。

### R8(P2)徽章佔位 = 承認的版面偏差

全成交後徽章常駐(現況紅方格消失、點價鈕回全寬)→ 點價鈕變窄屬**本次明文承認的
偏差**(與多位數殘量增寬同級);徽章 span 加 `pointer-events-none`(不吃點擊)。
UI 驗收補:徽章存在時同列點價鈕仍可點。

### R9(P2)SC-5 補下界 + merge lock

SC-5 assert 改 `0.45 ≤ _balance_due − monotonic() ≤ 0.55`(防 debounce 被整個拿掉);
加 merge lock 案:連兩筆 D 回報,第二次 due > 第一次 due(既有行為,無紅可先行 →
`[lock]` + mutation-verified)。

### R10(P2)🔴 拆兩包獨立可逆

🔴 前端(三座梯顯示)與 🔴 後端(debounce+守門)分開 commit;Backward compat 段註明
可獨立 revert。

### R11(P2)SC-6 真實環境降級

真實環境成交驗證涉真錢下單(§7 三道閘)→ **降級為 user 盤中過目,實作者不代下單**;
AI 層以測試 + mock 資料截圖佐證(SC 原文「窗口外降級」路徑轉正)。

---

## [amendment 2026-08-13b: 限縮加輪(P1×3/P2×5 全 accepted;無 P0 → review 退出)]

### A1(P1)守門條件改雙判,deadline 只管 balance 段

`_balance_inflight_until` 從發查詢起算,`_pending_deadline` 從 `_on_balance_complete`
起算 +8s — 10s 單一 deadline 蓋不住「balance 段 >2s + pending 8s」。改:
- 守門條件 = **`_pending_sec is not None`(pending 段,有 `_poll_pending` 8s 保底)
  `or`(`_balance_inflight_until` 未逾期)**(balance 段)。
- `_on_balance_complete` 設 pending 時**清 `_balance_inflight_until`**(交棒給 pending 判)。
- SC-7 補案:pending 已設且 inflight deadline 已過 → 仍不放行第二次查詢。

### A2(P1)entry 生成條件同步收編 seqs

原 🔴 條目 entry 條件 `qty>0 || filled>0` 漏了「P/U 先到、N 未到」的 actionable 單
(order_qty=0、filled=0)→ entry 消失連刪單入口都沒有。改:
**entry 條件 = `qty > 0 || filled > 0 || seqs.length > 0`**(seqs 非空必上梯,顯示
`0(0)` 可點)。ladder-lots.test.ts 加案。

### A3(P1)日期界分梯:現股嚴格、期貨 ±1 日窗

`date` = idx23 委託建立日(reply.py:55,C/D 事件實測仍為原單日期);**夜盤跨午夜語意
未實證**(交易日 vs 日曆日兩種假設下嚴格比對都有反例),而夜盤是期貨/個股期梯真場景。
拍板:
- **現股梯(無夜盤):filled 計入 = `actionable || date === today`**(嚴格;幽靈全滅)。
- **期貨/個股期梯:filled 計入 = `actionable || date ∈ {昨日, 今日, 明日}`**(±1 日窗;
  兩種夜盤語意假設下皆涵蓋)。
- 實作:`aggregateLots` / `splitMyLots` 收 `filledDates: ReadonlySet<string>`(YYYYMMDD),
  container 以 `new Date()` 邊界算(lib 加純函式 `ymdWindow(now, offsets)` 可測)。
- Known Risks 補:(a) 期貨梯昨日終態單的徽章今日仍顯示(bounded 1 日,server 跨日
  長跑時);(b) 現股昨日建立、今日成交的預約單 filled 不顯示(原 R5 條保留)。
- Edge cases 補「夜盤跨午夜」案(lib 層以固定 now 測 ymdWindow + filledDates 過濾)。

### A4(P2)unit 閘縮為「現股梯排除零股」單向

整筆 `unit !== "口"` 過濾會誤殺 market 缺值(→ unit fallback "張")的期貨單,砍掉
個股期梯刪單入口。改:**只有現股梯傳 `excludeUnit: "股"`**(整筆排除零股 — 活單側
消失為顯式承認,刪單入口在委託列表);期貨/個股期梯**不設 unit 閘**(契約碼含英文
字母、與股號零碰撞,既有比對鍵已足)。R6 原「個股期傳 口」條刪除。

### A5(P2)清旗標落點釘死

`_finalize_positions` 清 `_balance_inflight_until` 與 `_pending_sec/_pending_deadline`
同組、在 `set_positions`/`_emit` **之前**(emit 例外不得滯留旗標);狀態轉回 ok
(重登/重連)時一併清。early-return(遲到丟棄)分支不清(該輪已 finalize 過)。

### A6(P2)徽章測試 fixture 日期交叉

三座梯測試 fixture 的 `date` 是寫死過去日(20260728/20260806)— 終態徽章案照抄必
取不到 filled。SC-2/SC-3 明訂:徽章案 fixture `date` 動態取今日(helper);另加
「終態單 date=昨日(現股)→ 無徽章」把日期界釘住。

### A7(P2)unit 字面值升格跨檔契約

CLAUDE.md §4 級契約補一行(spec 內登記):**`OrderRecord.unit` 字面值(張/口/股)
自本次起為前端過濾鍵,改字面值 = 改契約要同時改兩邊**。tests/capital 補 TL 零股 →
`unit == "股"` lock(mutation-verified)。

### A8(P2)SC-7 測試構造釘死

不得 sleep;時間一律直接設欄位:(1)「鏈進行中」= 發第一次查詢後**不餵 `##`** /
或餵完 balance `##` 讓 pending 掛起;(2) due 到期 = 直接設 `_balance_due` 為過去;
(3) 守門逾期 = 直接設 `_balance_inflight_until` 為過去。FakeCom 計
`get_real_balance` 呼叫次數斷言。
