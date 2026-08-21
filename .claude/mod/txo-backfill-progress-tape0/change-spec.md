# change-spec — TXO 回補重試進度可觀測 + 群組檢視 `?tape=0`(mod/txo-backfill-progress-tape0,R9 / B14+B15)

分流判定:已成形方案(rounds.md §R9 指名;預核准)。Scope:**M**(後端 2 源檔 + 前端 4 檔 + 測試)。

## 現況
- **B14** `server/engine.py::_run_handover_locked`(L240-300):`for attempt in 1.._HANDOVER_RETRIES(3)`:`_set_status("backfilling")` → subscribe → `fetch_backfill` → overflow 則重試。
  `self._handover` 只在 buffer 非 None 時寫 `{backfill_secs, buffer_used, buffer_cap, buffer_warned, overflows}`;**attempt 未寫入**。08-19 R1 起快照只在內容有變才推 → 重試期間 WS 零訊息(心跳已解保活),前端 `ConnectionBadge` 固定「回補中」不知第幾次。
  前端 `types.ts::Snapshot` 無 `handover` 欄型別;`App.tsx:424` 只傳 `status` / `wsStatus`。next-time 08-19 txo-snapshot 節 C4。
- **B15** `/api/stock/state/{code}`(app.py:1436-1456)恆回 `stock.snapshot(key)` 含整份 `ticks`(deque 上限 20000;M0 盤中實測 5608 = 555 KB、2609 = 1.46 MB,50 檔群組輪點 ≈ 20–70 MB);
  群組檢視點卡片 → `onSelect` → App `setStockCode` → `useStockStream` refetch 全量,而群組檢視**無主圖 / tape 讀者**(`CardIntradayChart` 吃 group-state)。
  `useStockStream(code, contract)`(App.tsx:175 唯一 caller)`stateUrl()` 唯一 URL 產生點(R2-7);`fromSnapshot` 以 `snap.ticks ?? []` 折 VP + tape。
  view 狀態在 `StockPage`(`initialView` / `selectView` + localStorage `STOCK_VIEW_KEY`),App 不知道。W-4:onSelect 仍須換訂閱(route 內 `set_main_contract`)。

## 拍板(auto-default)
- **D1 B14 後端**:每個 attempt 開頭(`_set_status("backfilling")` 後)寫 `self._handover = {**(self._handover or {}), "attempt": attempt, "attempts_max": _HANDOVER_RETRIES, "phase": "backfilling"}`;
  成功 / 降級結束時既有欄位照寫並保留 `attempt`,`phase` 改 `"live"` / `"degraded"`。`[auto-default | reason: 內容真變 → 快照推送;欄位 additive,舊讀者不受影響]`
- **D2 B14 前端**:`types.ts::Snapshot` 加 `handover?: { attempt?: number; attempts_max?: number; phase?: string; backfill_secs?: number; … } | null`;
  `ConnectionBadge` 加 optional prop `handover`;`status === "backfilling" && handover?.attempt !== undefined && handover.attempt > 1` → label `回補中(第 ${attempt} 次)`;attempt 1 / 缺 → 「回補中」逐字不變。App 傳 `snapshot?.handover`。
- **D3 B15 後端**:route 加 `tape: int = 1`(Query);`tape == 0` → `snap["ticks"] = []`、`snap["tape_omitted"] = True`(額外旗標讓前端 / 測試可辨;additive)。其他值照舊(不驗 0/1 以外,非 0 皆全量)。`set_main_contract` 仍呼叫(W-4)。
- **D4 B15 前端**:view 狀態**上提到 App**(`useStockView()` hook 封裝 initialView / persist,App 持有 `stockView` 傳 `view` / `onView` 給 StockPage;StockPage 既有 `selectView` 改呼叫 prop);
  `useStockStream(code, contract, { tape })`,`stateUrl` 加 `tape=0` query(`&` / `?` 組合正確);`tape` 進 refetch 觸發:group→single 切換時若當前 accum 由 `tape=0` 取得(`tapeOmittedRef`)→ refetch 全量;single→group 不 refetch(多出的 ticks 無害)。
  `[auto-default: 上提 view 而非 StockPage 內建第二條 stream | reason: stream 在 App 層是 D2 右欄跟隨的前提;上提 view 是最小改動]`

## 成功條件
- SC-1 B14 後端:FakeSource 第 1 次 overflow、第 2 次成功 → 快照序列中出現 `handover.attempt == 1` 與 `== 2`,最終 `phase == "live"`、`attempt == 2`;全部 overflow → `phase == "degraded"`、`attempt == 3`。驗證 tests/server/test_engine*.py。
- SC-2 B14 前端:`ConnectionBadge status="backfilling" handover={{attempt: 2}}` → 文字「回補中(第 2 次)」;attempt 1 / undefined → 「回補中」;非 backfilling 不帶次數。App.test:snapshot 含 handover.attempt 3 → header 顯示「回補中(第 3 次)」。
- SC-3 B15 後端:`GET /api/stock/state/2330?tape=0` → `ticks == []`、`tape_omitted is True`、其餘鍵與全量相同、`set_main` 仍被呼叫(engine fake 記錄);無參數 → 全量、無 `tape_omitted`。
- SC-4 B15 前端:群組檢視點卡片 → fetch URL 含 `tape=0`;切回單檔 → 再 fetch 一次全量(URL 不含 tape=0);單檔模式下換檔 → 全量。驗證 App.test / useStockStream.test(fetch spy URL)。
- SC-5 UI:TXO 重試態需真環境(不可刻意觸發)→ 以 App.test 為證;群組檢視點卡後 DevTools/headless 量 `/api/stock/state` 回應 bytes 明顯小於全量(盤後 tape 近空,留 **user 盤中過目**)。

## 白名單
- W1 `_handover` 既有五欄語意與值不變;overflow 重試邏輯 / 狀態機不變;`snapshot()` 其餘鍵不變。
- W2 ConnectionBadge 其餘 status 文案與 tone 不變;`wsStatus` broken 分支優先不變。
- W3 `/api/stock/state/{code}` 無 `tape` 參數時回應位元不變;`?contract=` 驗證與 400/502 語意不變;`set_main_contract` 恆呼叫(W-4)。
- W4 `useStockStream` 五個 refetch 觸發與 in-flight 合併(CR1)不變;`stateUrl` 仍唯一 URL 產生點;單檔模式 URL 不變。
- W5 StockPage view 切換行為與 localStorage 鍵值不變(只搬家);group-state batch 端點不動。

## Out of scope
TXO delta 化(B13)、group-state 端點、tape 200 筆上限、前端顯示 backfill_secs。

## Edge cases
1. attempt 1 即成功 → handover.attempt = 1,badge 不帶次數。2. degraded 後 `_maybe_self_heal` 再啟動 → attempt 從 1 重計(每次 `_run_handover_locked` 呼叫新序)。
3. `tape=abc` → FastAPI 422(型別),可接受。4. group 檢視下 WS tick 照進(`applyTick` 追加 ticks 從空開始)—— 切回單檔的 refetch 全量覆蓋。5. 切回單檔時 code 同時變更 → 單一 refetch(合併)。

## 該紅 / 不該紅
- 後端:`test_engine` 既有快照等值斷言若含 `handover` 整 dict 全等 → 該紅(additive 欄);route 測試無 tape → 不該紅。
- 前端:`ConnectionBadge.test` 既有 → 不該紅;`StockPage.test` 的 view 切換測試 → 若直接 render StockPage 無 App,需改傳 `view/onView`(該紅:prop 接線);`useStockStream.test` URL 斷言 → 不該紅(無 tape 選項時 URL 不變)。

## Diff 級
- 🟢 後端 engine.py attempt 欄(測試先紅)。🟢 route `tape` 參數(測試先紅)。
- 🔴 前端 ConnectionBadge(新 prop,測試先紅)、App 接線;🔴 `useStockView` 上提 + StockPage prop + `useStockStream` tape 選項(測試先紅)。

---
## Spec review round 1 amendments(`change-spec-review-round-1.json`,11 條全 accepted;以本節為準)
- **D4' tape ref 化(R1)**:`const tapeRef = useRef(tape); tapeRef.current = tape;`,`stateUrl(code, contractRef.current, tapeRef.current)`;W4 補「新參數比照 code/contract 走 ref,不得由 `[]` deps 閉包捕獲」。預設 `tape=true` 時 URL **不附加任何 query**(`useStockStream.test.ts` 全等斷言不紅)。
- **D4'' 無條件 transition refetch(R2)**:刪 `tapeOmittedRef` 最佳化;effect deps `[tape]`:`false → true` 無條件 `void refetch()`(走 CR1 合併),`true → false` 不打。`tape_omitted` 旗標仍由後端回(測試 / 診斷用),前端不依賴。
- **D4''' view 上提改 optional(R3)**:StockPage 新 optional prop `onViewChange?: (v: StockView) => void`(**view 仍留 StockPage**,localStorage 與 `selectView` 不動,呼叫時多通知);`StockView` 型別 export;
  App 持 `stockView` state(初值與 StockPage 同源 `initialView()` → 抽 `lib/stock-view.ts::readStockView()` 兩邊共用)→ `tape = stockView !== "group"`。既有 50+ 呼叫點零改動。
- **SC-1 機制(R4)**:fake `fetch_backfill` 內直接 `rt._buffer.overflowed = True`(第 1 次)→ 第 2 次正常;斷言改用 `latest_snapshot()` 於每 attempt 的交握點(fake 內 `asyncio.Event`)而非 yield 序列;degraded 案三次皆 overflow。
- **D1' `_mark_changed`(R5)**:每次寫 `self._handover` 後緊接 `self._mark_changed()`(冪等),不依賴零 await 排程;註解釘住。
- **D1'' 不 merge 舊欄(R6)**:attempt 開頭 `self._handover = {"attempt", "attempts_max", "phase": "backfilling"}`(五欄不帶);attempt 結束時寫完整五欄 + attempt + phase。W1 改寫「五欄只在 attempt 結束時出現」。
- **D3' `tape: str = "1"`(R7)**:非 `"0"` 皆全量,不產生 422;D3'' 旗標下傳 `state.snapshot(tape=False)`(R8)跳過 ticks list comprehension(不只省 payload);`light_snapshot` 不動。
- **SC-5'(R9)**:重啟後 `curl -s -o /dev/null -w '%{size_download}' /api/stock/state/<活躍檔>` vs `?tape=0` 同日下午對照(set_main 觸發當日全量回補,ticks 仍兩萬筆);該紅清單補 `App.memo.test.tsx`(view 上提改 optional 後應不紅,仍列觀察)、`useStockStream.test.ts`(非 .tsx)。
- **R10 Out of scope 依據**:`/api/stock/group-state` 走 `light_snapshot()` 本就不含 ticks(test_stock_engine:1548 全等 lock)→ 無 tape 可省。
- **R11**:engine attempt 欄 🟢 commit subject 註明「重試期間每 attempt 多一則快照推播(內容真變,非回退 R1)」。
