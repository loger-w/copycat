# Change Spec — next-time [behavior] 批次修復(2026-08-03)

來源:refactor 輪(stock-page-dedupe-deadcode)記帳於 docs/next-time.md 2026-08-03 節的
[behavior] 清單;**user 拍板「畫面 OK 直接修 next-time」= 全批預核准**。
個股頁 UI 過目已 PASS。findings 依據:`.claude/refactor/stock-page-dedupe-deadcode/findings-deadcode.md`。
Review 輪 1(change-spec-reviewer):S-1~S-11(4 P1 / 7 P2)全 accepted,已反映;變更標【S-n】。

## 行為白名單(必須保留,任何 item 不得波及)

- 個股頁其餘一切可觀察行為:五檔/明細/江波圖/K 線/自選/閃電梯的畫面與互動
- WS 訊息五型別(tick/book/status/stkfut/watchlist_quote)shape 不變(M3 只動 REST snapshot)
- 錯誤碼字串與優先序(engine None → 503 NOT_READY 先於 400 BAD_CODE)
- 內外盤 derive_side / relabel_locked_side 判定邏輯(M3 只刪聚合輸出欄位,不碰判定)
- per-minute `minutes.{i,o,u,h,l}` 欄位(能量副圖依賴)照舊
- 回測鏈路(backtest/ 用 1K UpVolume/DownVolume,與 live 無呼叫關係)零觸碰

## Items(每項:紅測試先行 → 🔴 fix;連帶死碼另立 🔵 commit)

### M1|後端|/api/stock/bars tf=D 忽略 days(對齊 docstring)
- 現況:docstring 寫「tf=D 忽略 days」,但 `?tf=D&days=abc` 回 400 BAD_DAYS。
- 新行為:tf=D 時完全不驗 days(壞值/缺值皆忽略,回 200 日 K)。tf=分鐘級行為不變。
- 紅測試:`/api/stock/bars/2330?tf=D&days=abc` → 200。
- 檔:copycat/server/app.py bars route;tests/server/test_stock_routes.py。

### M2|後端|`_resub_task` 關機取消
- 現況:stock_engine `_resub_task` 持有參考防 GC 但不進 `_tasks`,close() 不取消;且
  rollover 連跑兩次時 `self._resub_task = ...` 覆寫會讓前一個 task 失去參照(同類洩漏)。
- 新行為:resub task **append 進 `_tasks`**(不再單獨欄位覆寫)【S-2】,close() 既有的
  cancel+await 鏈自然涵蓋;更新 L-13 註解。
- 紅測試【S-2】:pending 的製造 = 先 `await engine._pool_lock.acquire()`(task 停在
  `async with self._pool_lock`,尚未進 to_thread,取消才乾淨)→ `await engine.close()` →
  task cancelled。**不可**用 subscribe_gate 未 set 製造(to_thread 已開跑取消不掉 → 死鎖)。
- 既有測試不該紅:test_rollover_stage1_does_not_block_event_loop(:489,不呼叫 close)。
- 檔:copycat/server/stock_engine.py;tests/server/test_stock_engine.py。

### M3|後端|REST snapshot 死欄位清除(wire 契約改動,前端讀取端已於 refactor 輪移除)
- 移除【S-7 位置更正】:`stock_state.snapshot()` 的 `cum_inner`/`cum_outer`/`meta.y_close`
  三者;`stock_engine.snapshot()`(:186-189)的 `tc4`/`backfilling`/`stkfut_prod` 三者
  (含每 snapshot 的 stkfut_prod 計算)。**WS status 訊息的 tc4/backfilling 是活碼,不動**。
- 保留:`minutes.{i,o,u}`、`last.cum_vol`、`names.count`/`bars.code,tf`;
  【S-9】**`StockMeta.y_close_milli` 與其 parse 鏈保留**(TC4 YClosedPrice 唯一落點、
  除權息判別唯一來源)— dataclass 補註解「刻意保留:目前無消費者」。
- 紅測試:snapshot/state payload 斷言六個 key 不存在。
- 既有測試該紅對照表【S-3】(紅 → 替代斷言,regression lock 不得無聲拆掉):
  - test_stock_state.py:65-66(cum_outer/cum_inner)→ 改斷言 minutes 的 o/i 聚合
  - test_stock_state.py:77(snap["cum_outer"])→ 改斷言 key 不存在 + minutes 聚合
  - test_stock_engine.py:207(snap["cum_outer"]==1,「reset 後首筆 ingest 且判到側」唯一證明)
    → 改斷言 `snap["minutes"][...]["o"] == 1`(保留同一行為鎖)
  - test_stock_engine.py:463-473(CR4 lock:`snapshot("5483")["backfilling"] is None`)
    → 改斷言 WS status 訊息或 engine 內部 backfilling 態(保留 worker-survives lock)
  - test_stock_state.py:222-223 / test_stock_models.py:91(y_close_milli 建構/解析)→
    **不該紅**(parse 鏈保留)
- 連帶死碼(🔵 另 commit)【S-8 判準更正】:**prod 端**零讀者即可刪,測試讀者隨之改寫
  (列入該紅表)—— `StockDayState.cum_inner/cum_outer` 欄位與 `_apply` 累加(prod 唯一
  讀者是 snapshot 輸出,移除後即零)可刪;y_close 鏈依【S-9】保留。
- 檔:copycat/live/stock_state.py、stock_models.py、server/stock_engine.py;對應測試。

### M4|後端+前端|VWAP 分母錯位修復
- 現況:前端 `fromSnapshot` 以 `vwap × last.cum_vol` 還原分子(stock-accum.ts:103,116),
  但後端 vwap 分母是 `_volume` = 去重剔試撮 Σqty(stock_state.py:143-145)≠ `cum_vol`
  (TC4 TradeVolume)→ 兩者不等時前端增量 VWAP 靜默偏移至下次 refetch。
- 新行為:後端 snapshot 增 additive 欄位 `"vol": self._volume`;前端 volume 種子改
  `snap.vol ?? snap.last?.cum_vol ?? 0`(舊後端 fallback 保留)。applyTick 增量鏈不變。
- 紅測試:後端 — snapshot 含 vol 且 = Σqty(去重後);前端 — snapshot vol ≠ cum_vol 時
  fromSnapshot 後 vwap 增量與後端口徑一致(建 fixture:vwap=100_000、cum_vol=60、vol=50,
  apply 一筆 (p=200_000,q=10) → vwap = round((100_000×50+200_000×10)/60),分母 =
  50+10=60 —— 注意此處分母是 vol 種子 50 加本筆 10,非 cum_vol 的 60;數字巧合相同,
  fixture 改用 cum_vol=80 避免巧合:錯誤實作分母 90、正確實作分母 60)。
- Blast radius【S-11】:applyTick 的 `last.cum_vol` fallback(`acc.last?.cum_vol ?? acc.volume`)
  已評估 —— snapshot 無 last 時後端 `_volume` 必為 0,兩口徑等價,保留現狀不動。
- 既有測試不該紅:stock-accum.test.ts:130 VWAP 增量測試(fixture 無 vol 欄位 → fallback
  cum_vol,行為同舊)。
- 檔:copycat/live/stock_state.py;frontend/src/lib/stock-accum.ts;兩側測試。

### M5|前端|ref/upper/lower <=0 一律視為「不可得」(一族收斂)
- 現況【S-4 更正】:後端 `to_milli_units("0")` 對 ref/upper/lower 三欄一視同仁回 0 非 None。
  真實觸發(TC4 送 "0")極可能三欄同時為 0:y 域走 `upper!==null && lower!==null` 分支 →
  `[0,0]` → flat 常數 toY(不是原描述的「autofit 壓上半」);ref=0 另打壞 yTicks(:303
  `ref > 0` 分支退化成 3 格 + 假價位 0)與 lastTone / hover 時間標籤價色(恆 bull)。
- 新行為:**幾何入口統一歸一**【S-4a】—— buildIntradayGeometry 入口把 ref/upper/lower
  的 <=0 歸一為 null(此後既有分支自然走 autofit);StockIntradayChart **:528 一次歸一**
  【S-5】`ref = (accum.meta?.ref ?? 0) > 0 ? ... : null`,讓 lastTone / hover 時間標籤 /
  shownChg 三處自動一致;lastTone 改呼叫既有 `markTone`。
- 紅測試:meta={ref:0, upper:0, lower:0} → y 域 = autofit(prices) 不含 0;last-dot =
  fill-ink-dim;hover 時間標籤價色 = fill-ink【S-5】。
- 既有測試不該紅:hasRef/tickTone 相關(語意本已把 0 當無)。
- 檔:frontend/src/lib/stock-intraday-svg.ts、components/stock/StockIntradayChart.tsx;測試。

### M6|前端|DepthBar 市價 0 價檔位全套處理(badge + 聚合 + 顯示)
- 現況:`b[0]?.[0] === upper` — 鎖停時 TC4 第一檔推市價佇列(價 0),badge 永不亮;
  【S-6】同一份簿的 maxVol 歸一(:67)與 bidTotal/askTotal(:68-69)混市價量、
  `fmt(0)` 印成 0 元 — CLAUDE.md §8「第四處」同型,OrderBook 已全套修過。
- 新行為(對齊 OrderBook 既有慣例):(a) 鎖停判定取「第一個 price>0 檔位」比對
  upper/lower(雙側對稱);(b) maxVol / 總量只算限價檔(limit-only,與 OrderBook
  limitOnly 同源邏輯);(c) 0 價檔位價格顯示「市價」,其量照列(bar 夾制比照 OrderBook)。
- 紅測試:bids=[[0,N],[upper,m],…] → badge 亮;總量 = 限價和;0 價列顯示「市價」;
  無 0 價檔位時三者行為全不變(既有測試不該紅)。
- 檔:frontend/src/components/quote/DepthBar.tsx;DepthBar.test.tsx(參照 OrderBook.tsx
  的 limitOnly / 市價列實作,可抽共用 helper 進 lib/stock-tick.ts 或就地小函式)。

### M7|前端|CandleChart 滾輪 effect deps 補齊【S-1 降級 🔵】
- 更正:`dimW = DIMS.width`(:32 模組常數 1400,永不變)、dimH 不參與錨點計算 →
  **不存在可觀察 bug**(plan review R-4 的 useContainerSize 來源判斷有誤;deadcode 輪
  L-16 的 [safe] 判定才是對的)。
- 新行為:無 — 純 🔵 hygiene:deps 補 dimW/dimH(當前值恆定,行為不變),消未來
  「height prop 影響 x」的潛在 stale closure。
- 測試:不加行為紅測試(寫不出可紅可綠的差);既有 bars/viewport 測試為回歸保護。
- 檔:frontend/src/components/stock/CandleChart.tsx。🔵 commit。

### M8|前端|TickTape 切股歸零(+ 附帶 🔵 reverse memo)
- 現況:`limit`(載入更多)是元件 state,StockPage 未帶 key → 切股後展開筆數殘留
  (與 pickerOpen 的換股歸零不一致);另每 render `[...ticks].reverse()` 200 列。
- 新行為:切股 → limit 回初始值(實作任選:StockPage `key={code}` 或 TickTape 內
  effect-on-code;傾向 key,零新 state 邏輯)。
- 紅測試:展開後切股 → 顯示筆數回初始。
- 附帶(🔵 獨立 commit,行為不變):reverse 移入 useMemo([ticks])。
- 檔:frontend/src/components/stock/{StockPage,TickTape}.tsx;測試。

### M9|前端|useStockNames 錯誤路徑併入 parseError
- 現況:行內 `res.json().catch(() => ({}))` 後直接 `body.detail?.error` — body 為合法 JSON
  `null` 時 TypeError 逸出 queryFn(錯誤訊息變 TypeError 文字)。
- 新行為:改用 `lib/api-error.ts` parseError(never-raise,回 HTTP_<status>)。
- 紅測試:mock fetch 回 `"null"` body(status 500)→ query error message = "HTTP_500"。
- 檔:frontend/src/hooks/useStockNames.ts;useStockNames.test.tsx。

## 不在本批(維持記帳)

L-5(QryIndex 游標需先驗)、範圍外 parseError×3 / fmtPct×5(純重複非行為)、
D-8/D-10/D-13/D-14 JSX、B-D6;【S-10】L-8(apply_backfill 去重不對稱 — 已由
docs/next-time.md 2026-07-21 節既有條目與 stock_state.py 註解承接,對齊即改張數,
需獨立驗證輪)。

## 收尾

- docs/next-time.md 2026-08-03 節逐條打勾 [x] 附 commit。
- 全 gate + validate;真環境:fake-source smoke + M3 後 `/api/stock/state` shape 確認。
