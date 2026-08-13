# Change spec:個股「試撮/暫緩撮合」(緩)標示 — 時間窗版(第一段)

分流判定:**已成形**(需求指名做法:engine 層萃取 / WS+snapshot 傳遞 / badge 落點 /
降級路線;源自 user-feedback backlog 第 3 條,已調研拍板)→ grilling 姿態,
決策點逐題 `[auto-default]`。規模:**L**(跨前後端 ≥5 檔 + wire 契約 additive 擴充)。

## 0. 降級路線判定(任務內建)

開工時刻 2026-08-13 17:40 = 收盤後,無法盤中取證「延緩撮合」的 TradeStatus 行為
(需暴漲暴跌觸發樣本)。→ 本輪 = **時間窗版標示 + TradeStatus 觀測 log**;
蒐證完成後開第二段(TradeStatus-based per-code 偵測),第二段登記 `docs/next-time.md`。

[amendment 2026-08-13: review R6] 本輪**不覆蓋原始症狀時段**(09:00–13:25 盤中暴漲暴跌
觸發的暫緩撮合本輪永遠不亮)→ **backlog 第 3 條維持未勾銷**,直到第二段落地;
收尾回報必須明講這一點。

## 1. 拍板(全部 [auto-default])

- **D1 trial 推導 = 每次組 payload 當下以本機時鐘現算**,不落 StockDayState。
  `[auto-default: 現算 | reason: 試撮期 TC4 不推成交 tick(實測),tick 路徑萃取不到
  「進窗」事件;時間函數無 stale/清除 bug;StockDayState 維持零 IO 純 tick 狀態機]`
  推導式:`is_trial_window(now_taipei_hhmmssfff, trial_windows_for(code))` —
  兩個既有函式,期貨鍵空窗恆 False → 需求 (d) 天然滿足,前端無需 per-instrument 判斷。
- **D2 wire 契約 = `watchlist_quote` + REST snapshot 各加 additive `trial: bool`**。
  `[auto-default: 兩通道皆加 | reason: 側欄吃 watchlist_quote、單檔頁基底吃 snapshot;
  只加一邊會有一個消費端拿不到。group_snapshot 不加(群組卡片不標,out of scope)]`
  snapshot 的附加點在 **engine.snapshot()**(同 `no_data` 慣例),`StockDayState.snapshot()`
  不動 — trial 是引擎時鐘推導,不是日內狀態機資料。
- **D3 窗轉態推播 = `_flush_watchlist_loop`(既有 1s loop)偵測現貨窗 bool 翻轉**,
  翻轉時對「自選全碼 + 現貨主圖碼」直接 publish `_quote_payload(code)`(繞過
  `state.last is None` skip — 盤前無成交正是要標的時刻)。
  `[auto-default: 掛既有 1s loop | reason: 不加新 task;一天僅 4 次邊界事件,直接
  publish 不打穿 1s 節流;主圖非自選(預覽)也要收到 → 沿 _handle_no_data 對任意 code
  發 watchlist_quote 的既有先例(useStockStream.ts:314 靠它)]`
  期貨主圖鍵(`F:` 前綴)不推(trial 恆 False,推了也是 no-op)。
  [amendment 2026-08-13: review R3] (1) `self._trial_on` 在 `start()` 內以現貨窗現算
  **播種**(窗內啟動不產生假翻轉);(2) `_now_taipei_time()` 定為**模組級函式**
  (同 `_now_taipei_hhmm` :58 慣例),測試一律 monkeypatch 模組屬性注入假時鐘;
  (3) 既有計數型 WS 斷言已核對:test_stock_routes.py:625-627 與 test_signal_routes.py:850
  吃「前 N 則訊息」,但翻轉補推只在**窗 bool 實際變化**時發生 — 播種後測試 process 內
  時鐘幾乎不可能跨越窗邊界(僅真實台北 08:30/09:00/13:25/13:30 邊界分鐘跑測試才有交集);
  新測試以 monkeypatch 假時鐘鎖定,假時鐘固定後窗 bool 恆定、不翻轉不補推。
  [amendment 2026-08-13: review R7] 08:30 翻轉補推可落在 `_pending_date` 已武裝、
  stage2 未跑期間 → payload 值欄位為**昨日殘值**;與既有連線 seed 同語意(builder 原樣
  輸出),**刻意不特判**。
- **D4 前端狀態源**:側欄 = `quotes[code].trial`;單檔頁 header = `accum.trial`
  (snapshot 種子 + `watchlist_quote` 針對 current instrument 的補寫,與 noData 同款)。
  `[auto-default: accum 補寫 | reason: 預覽股不在自選,開頁後的轉態只有 D3 的主圖
  推播帶得進來;noData 已走同一條路,語意成對]`
  [amendment 2026-08-13: review R2] 既有 noData 補寫分支(useStockStream.ts:318-325)
  是**單向黏性**(只 false→true,清除靠 refetch)且無測試鎖 —— **一字不動**;
  trial 走**獨立新分支**(`msg.code === current && Boolean(msg.trial) !== acc.trial` →
  `{...acc, trial}`,雙向,時間窗語意天然要雙向)。不合併兩者。
- **D5 badge 表述**:全形括號「(緩)」,琥珀色(amber)小字 — 中性狀態,不能與漲跌
  (bull/bear)或 accent 混用。側欄:第一行 code 右側;單檔頁:h2 內 code 右側。
  `[auto-default: (緩)+amber | reason: 需求原文用「(緩)」;試撮非漲跌方向性狀態]`
  [amendment 2026-08-13: review R6] 本輪「(緩)」只承載試撮窗語意;第二段(盤中暫緩
  撮合)落地時是否共用同一表述或分化(如「(暫停)」)**留待第二段拍板**,不在本輪預設。
- **D6 TradeStatus 觀測 log = engine 層 per-code 轉態記錄**(從 raw quote dict 讀,
  **不動 parse 層簽名**)。[amendment 2026-08-13: review R1+R10 重寫] 規則:
  - **只對現貨鍵觀測**:[amendment S5 更正] 落點在 `_handle_quote` **:815 期貨夜盤
    整則早退之後**(此時 code 已解出、parse 已完成),且先 `if is_futures_key(code):
    跳過觀測` —— 期貨鍵空窗會讓 `is_trial_window` 恆 False,任何轉態都誤落「窗外」分支。
  - **首見值只播種不記錄**:`code not in self._trade_status` → 寫入前值即返回
    (`None→"0"` 不是轉態;否則每交易日 255 檔各噴一則假 WARNING)。
  - [amendment S4] state = `self._trade_status: dict[str, tuple[str, bool]]`
    (前值, episode 已記 WARNING);`_rollover_stage2` **一併清空** —— 跨日殘留前值
    會把隔日首則推播誤判成「恢復」帶昨日值記 WARNING,污染蒐證樣本。
  - 轉態且**新值非 "0" 且當下在試撮窗外** → `WARNING`(盤中延緩撮合蒐證訊號),
    episode 旗標置 True。
  - 轉態恢復為 "0" 且 **episode 旗標為 True** → `WARNING`(起訖成對),旗標歸 False。
  - [amendment S6] **其餘所有轉態一律 `DEBUG`**(含窗內 0↔1 常態、窗內出現值域外值
    —— 值域面由 parse 層 :215 的 warning 負責,engine 側只管轉態時序)。
  - [amendment 2026-08-13: code review D6-1] **觀測分級用的窗判準 = TRIAL_WINDOWS 兩端
    各放寬 2s**(觀測專用常數;payload `trial` 不動)—— 本機時鐘與 TC4 時戳的秒級偏移
    會把 13:25 進窗的 0→1 判成「窗外非 0」,產出每檔每日最多一對假 WARNING 淹沒蒐證。
  - [amendment 2026-08-13: code review IC-1,**改寫 SC-5(f) 與其測試 assertion(該變,
    鐵則 E 顯式宣告)**] 首見值三分:首見 "0" → 播種零記錄;首見非 "0" **且觀測窗外**
    → WARNING(訊息帶 `first_seen=1`)+ episode=True(訂閱前已進延緩撮合的股票是最
    可能取樣路徑,不可靜默);首見非 "0" 窗內 → 播種 episode=False 零記錄(冷啟動在
    試撮窗內 255 檔齊帶 "1" 不可齊噴)。
  - [amendment 2026-08-13: code review IC-5] `_trade_status` 清空**掛 rollover stage1**
    (episode 是日內語意;只掛 stage2 會讓 08:00–09:00 整段沿用昨日 episode → 假
    「恢復」WARNING 且時戳今日);stage2 的清空保留(快路徑雙保險)。
  - [amendment 2026-08-13: code review IC-6] qty 缺欄記 `-`(與 `qty=0` 可辨);
    真退訂(`set_watchlist` removed / `set_main` 換檔且無其他 owner)時 `_trade_status`
    一併 pop(對齊 `_backfilled` 清帳紀律)。
  - [amendment 2026-08-13: code review D6-2,記錄] 窗內起 / 窗外訖的 episode(如收盤
    試撮窗跨越的延緩撮合)在本段規則下全程只有 DEBUG —— 蒐證時 13:25–13:30 前後需
    併看 DEBUG 級;第一段不改(改了動 SC-5(c)),註記 docstring + next-time。
  - **訊息帶固定可 grep 前綴** `trade-status-observe`(格式:
    `trade-status-observe code=%s %s->%s t=%s trial_window=%s qty=%s`)——
    與 parse 層 :215 的值域外 warning 是**同事件兩則**(parse 管值域、engine 管轉態
    時序),蒐證對帳以本前綴為準,parse 那則不動(r2-F5 契約)。
  `[auto-default: WARNING/DEBUG 分層 | reason: 窗內轉態是已知常態,全 INFO 會淹沒
  蒐證訊號;窗外事件即是要抓的 evidence]`
- **D7 蒐證後續**:第二段(依蒐證結果做 per-code 偵測 + 事實記回 tc4-market-facts)
  登記 `docs/next-time.md`;本輪 log 即蒐證工具。

## 2. 成功條件(SC gate)

- **SC-1 側欄標示**:試撮窗內(08:30–09:00 / 13:25–13:30 台北),自選側欄每檔現貨列
  第一行代號右側出現琥珀色小字「(緩)」;窗外該字消失;`no_data` 列不標。
  驗證:vitest `WatchlistSidebar`(餵 `trial: true/false` quote 斷言「(緩)」存在/不存在);
  真實環境 = 盤中截圖。**驗證窗口:僅台北 08:30–09:00 / 13:25–13:30 交易日**。
  [amendment 2026-08-13: review R11] 窗外降級結案:**pytest(SC-3 假時鐘)+ vitest
  雙證據即可結案**;真實環境截圖登記 memory 待辦,次一交易日 08:30–09:00 窗過目補件。
  (刪 `python -c` 一項 — 與 SC-3 pytest 假時鐘重複且較易寫錯。)
- **SC-2 單檔頁 header 標示**:同窗內,單檔頁 `<h2>` 的股號右側出現「(緩)」;
  期貨合約態(下拉選了月份)不出現;窗外消失。
  [amendment 2026-08-13: code review IC-4] `no_data` 檔不標(`&& !accum.noData`,
  與 SC-1 側欄同口徑 — 對沒有報價的檔講撮合狀態是錯誤表述)。
  [amendment 2026-08-13: code review IC-3] trial 補寫沿 pendingBook(F-2)樣板加
  in-flight 守門:refetch 期間收到的翻轉先記 `{key, trial}`,snapshot 套用後 key 相符
  覆寫 —— 否則出窗訊息被舊 snapshot 蓋掉,header 掛假「(緩)」至下次 refetch。
  驗證:vitest `StockPage`(accum.trial true/false × contract null/非 null 四格 +
  noData case)+ useStockStream refetch 交錯 case;真實環境窗口同 SC-1。
- **SC-3 wire 契約**:`watchlist_quote` 與 `/api/stock/state/{code}` 皆帶 `trial: bool`;
  現貨碼窗內 True / 窗外 False;期貨鍵(`F:CDF:202609`)恆 False。
  驗證:pytest `tests/server/test_stock_engine.py`(fake clock monkeypatch)+
  `tests/server/test_stock_routes.py`(snapshot 鍵存在)。
- **SC-4 窗轉態推播**:窗邊界翻轉後 ≤ 2 個 flush 週期(throttle 2 tick)內,自選各碼
  與現貨主圖碼各收到一則帶新 `trial` 值的 `watchlist_quote`(**含盤前無成交、
  `state.last is None` 的檔**)。驗證:pytest flush loop 測試(假時鐘翻轉 + fake ws 收集)。
- **SC-5 TradeStatus 觀測 log**:(a) 窗外收到 TradeStatus 由 "0"→"2"(模擬值)→
  caplog 出現 WARNING 含前綴 `trade-status-observe` + code 與兩值;(b) 恢復 "2"→"0"
  → 再一則 WARNING;(c) 窗內 "0"→"1" → 無 WARNING(DEBUG 級);(d) 同值連續推播
  不重複記;[amendment 2026-08-13: review R1] (e) 期貨鍵任何 TradeStatus 轉態 →
  零 `trade-status-observe` WARNING;(f) [amendment IC-1 改寫,原「首見一律零記錄」
  assertion 標**該變**,鐵則 E 顯式宣告] 首見 "0" 與首見非 "0" 窗內 → 零記錄僅播種;
  首見非 "0" 窗外 → 一則 WARNING 帶 `first_seen=1` + episode 武裝(後續恢復 "0" 再一則
  WARNING);(g) [amendment IC-5] stage1 之後、stage2 之前收到帶 "0" 的推播 → 零
  WARNING;(h) [amendment IC-2] `_now_taipei_time()` 真實實作格式 fullmatch
  `HH:MM:SS.fff` + 凍結時鐘走真實路徑的窗邊界斷言。
  驗證:pytest caplog(斷言比對固定前綴,R10)。
- **SC-6 丟棄行為不變**:`test_stock_state.py` / `test_stock_models.py` 既有試撮丟棄
  測試零改動全綠。驗證:pytest -q 全量。

## 3. 不能破壞的既有行為白名單

1. `StockDayState.ingest` / `apply_backfill` 試撮 tick 丟棄 + `_last_cum` 不觸碰
   (stock_state.py:72-81, 115)— 零改動。
2. `watchlist_quote` 既有欄位語意:`no_data=True` 時值欄位全 None、`p`/`ref` 互斥、
   `upper`/`lower` 亮燈(`trial` 是旗標類,同 `no_data` 不受「值欄位 None」約束,
   但 no_data 列前端不標 — SC-1)。
3. 1s 節流不被打穿:D3 只在窗邊界(每日 4 次)直接 publish;dirty 路徑不變。
4. `trial_windows_for` 期貨空窗語意(D2 契約)與期貨夜盤整則早退(:801)不動。
5. parse 層 TradeStatus 值域外 warning 觀測不丟棄(r2-F5)— 保留原行號原文案。
6. REST snapshot 既有鍵形 additive-only;`group_snapshot` 形狀零改動。
7. 主圖 tick/book/status/stkfut 訊息形狀零改動。
8. 側欄既有渲染:漲跌停亮燈、無資料、參考價三態、兩行式版面、拖曳幾何(ROW_H)不動。
9. 期現對照 corr_engine 與 futures_models 對 parse 的呼叫(不看 is_trial/trial)不動。

## 4. Backward compat / migration

全 additive:舊前端忽略未知 key(既成慣例);新前端缺 key → `Boolean(undefined)=false` /
`?? false` 降級 = 不標,不炸。無資料格式落盤、無 migration → 可逆性 N/A(revert 即回)。

## 5. Edge cases

1. **窗邊界秒級**:flush loop 1s 粒度 + 本機時鐘,邊界 ±1–2s 誤差 — 接受(標示用途)。
2. **休市日 / 週末 08:30**:純時間推導會照標「(緩)」— 已知限制(server 無交易日
   日曆;TC4 不推播、頁面通常沒人看)。記 Known Risks,不在本輪加日曆。
3. **期貨合約主圖 + 現貨窗內**:合約 accum.trial 恆 False(空窗);同畫面側欄現貨列
   照標 — 兩者並存正確。
4. **盤前無成交檔(state.last is None)**:D3 直接 publish 繞過 flush skip;payload
   的 p/vol 本來就 None(既有 None 路徑),只有 trial 有值。
   [amendment S7] 此條適用於 **rollover stage2 已跑、state 已 reset 後**(或當日
   本來就零成交)的檔;stage2 未跑時見 edge 8。
5. **WS 重連 / 開頁在窗內**:連線種子走 `_quote_payload` → trial 自帶;主圖 snapshot
   同理 — 無需額外自癒。
6. **no_data 檔窗內**:payload trial 照算 True,前端 SC-1 規則不標(顯示「無資料」)。
7. **TradeStatus 缺欄 / 空字串**:視同 "0"(parse 既有 `or "0"` 語意),觀測 log 同基準。
8. [amendment 2026-08-13: review R7] **窗翻轉補推撞 rollover 武裝期**:[amendment S7]
   限 **stage2 未跑、`_states` 仍持昨日 last/meta** 時 → payload 值欄位是昨日殘值
   (與 edge 4 互斥:那條是 reset 後的 None 路徑)。與既有連線 seed 同語意(builder
   原樣輸出),刻意不特判;盤前側欄本來就顯示昨日狀態。

## 6. Out of scope

- 盤中延緩撮合的 **TradeStatus-based per-code 偵測**(第二段,待蒐證)。
- 群組檢視卡片(GroupGridView)/ TickTape / 閃電梯的緩撮標示。
- 交易日日曆(edge 2)。
- 大盤廣度鏈(XR-5 拍板不動)。
- Discord 訊號 / signal_hub(試撮 tick 本來就進不了訊號層)。

## 7. Diff 級章節(逐檔;三類標記)

全部改動屬 🟢(additive 新功能),無 🔴(不改任何既有行為/assertion)、無 🔵。

| 檔 | 動什麼 | 類 |
|---|---|---|
| `copycat/server/stock_engine.py` | (1) `_now_taipei_time()` 新**模組級**函式(`HH:MM:SS.fff` 對齊 `is_trial_window` 尺)+ `_trial_now(code)`;(2) `_quote_payload` 加 `"trial"`;(3) `snapshot()` 加 `snap["trial"]`;(4) `_flush_watchlist_loop` 窗翻轉偵測 + 補推([amendment S8] `__init__` 宣告 `self._trial_on: bool = False`,`start()` 以現貨窗現算覆寫);(5) [amendment S1/S4/S5] TradeStatus 轉態觀測插在 `_handle_quote` **:815 期貨夜盤早退之後**(此時 code 已解出、parse 已完成),`is_futures_key(code)` 先跳過;state = `self._trade_status: dict[str, tuple[str, bool]]`(前值, episode 已記 WARNING),`_rollover_stage2` 一併清空(跨日殘留前值會把隔日首則誤判成「恢復」);規則詳見 D6 | 🟢 |
| `frontend/src/hooks/useStockStream.ts` | `WatchlistQuote.trial: boolean`;handler 解析 `Boolean(msg.trial)`;[amendment S2] **新增獨立 trial 補寫分支**(`msg.code === current && Boolean(msg.trial) !== acc.trial` → `{...acc, trial}`),既有 no_data 補寫塊(:318-325)**零改動** | 🟢 |
| `frontend/src/lib/stock-accum.ts` | `StockAccum.trial: boolean` + `SnapshotShape.trial?: boolean` + `fromSnapshot` 帶入(`?? false`);`applyTick` spread 保留 | 🟢 |
| `frontend/src/components/stock/WatchlistSidebar.tsx` | `stockRow` 第一行 code 右側 `q?.trial && !q?.no_data` → `<span>(緩)</span>`(amber 小字,`data-testid="wl-trial-<code>"`)。[amendment R9] 落點:第一行現為 flex-col 內單一 `<span>{code}</span>`,直接後綴會換行 — 改為 `<span className="flex items-baseline gap-1"><span className="font-mono text-base text-ink">{code}</span>{badge}</span>`,badge 帶 `shrink-0 whitespace-nowrap`;列高 ROW_H 與名稱 truncate 不受影響(vitest 斷言 badge 與 code 同列) | 🟢 |
| `frontend/src/components/stock/StockPage.tsx` | header h2 code 右側 `accum?.trial && contract === null` → `(緩)`(`data-testid="page-trial"`) | 🟢 |
| [amendment R4] `frontend/src/components/stock/WatchlistSidebar.test.tsx` | 既有 WatchlistQuote fixture(:87/:96/:99/:828/:852 一帶)補 `trial: false` 欄(型別遷移,不動 assertion) | 🟢 |
| [amendment R4] `frontend/src/components/stock/GroupGridView.test.tsx` + `GroupGridView.memo.test.tsx` | `quote()` builder(:16 / :30)補 `trial: false` 欄(同上) | 🟢 |
| `docs/next-time.md` | 登記第二段(TradeStatus 偵測 + tc4-market-facts 記實)候選 + `_quote_payload` docstring「四個產出點」漂移(實為 7,review R5) | 🟢 |

### 既有測試:該紅的 / 不該紅的

- **不該紅**:`test_stock_state.py`(丟棄)、`test_stock_models.py`(窗/值域)、
  `test_stock_engine.py` / `test_stock_routes.py` 既有 payload 測試(斷言逐鍵取值非全
  dict 相等 — 加鍵不紅;落地遇全形比對測試視為「該紅的 🟢 附帶」逐一確認)、
  前端 runtime 行為測試全部。
- [amendment 2026-08-13: review R4] **該紅的(TS 型別遷移,🟢 附帶,不動任何 assertion)**:
  `trial` 定為 WatchlistQuote **必填**(選填會讓漏帶靜默成 false)→ tsc 紅的建構點逐檔:
  `WatchlistSidebar.test.tsx`(:87/:96/:99/:828/:852 一帶物件字面值)、
  `GroupGridView.test.tsx:16` 與 `GroupGridView.memo.test.tsx:30`(`quote()` builder
  逐欄列全)→ 各補 `trial: false`。`StockAccum` 側既有測試走 `as unknown as StockAccum`
  硬轉(StockPage.test.tsx:37、StockChart.test.tsx:26)不會紅;`StockAccum.trial` 同樣
  必填,`fromSnapshot` 以 `?? false` 降級舊後端。
- **新測試**:
  - pytest:`test_quote_payload_trial_in_window` / `..._futures_key_false` /
    `test_snapshot_has_trial` / `test_flush_loop_pushes_on_window_flip`(含 last=None 檔)/
    [amendment S3] `test_trade_status_transition_logging` **六態(SC-5 a-f)**,
    (e)(f) 各自獨立 case(`..._skips_futures_key` / `..._first_seen_seeds_only`)。
  - vitest:sidebar badge 有/無/no_data 三態;StockPage badge × contract 四格;
    useStockStream watchlist_quote trial 解析 + accum 補寫;stock-accum fromSnapshot trial。

## 8. Known Risks

- 休市日純時間標示(edge 2)— 接受,第二段 TradeStatus 版天然消除(靠實際推播)。
- 本機時鐘偏移 → 窗邊界誤差;部署綁本機=台北為既有前提(`_now_taipei_hhmm` 同款)。
- [amendment 2026-08-13: review R8] 多 client + 單 `_main` 槽:兩 tab 各看不同檔時
  只有最後 set_main 的那檔是 `_main`,另一 tab 的**非自選預覽檔**窗翻轉時漏更新
  (badge 遲到至下次 refetch)。與既有 noData 缺口同源,不在本輪展開。

---

self_review_head: 94382944059ec99c26e3eb01d6379368f5a79c59
(code review round 1:lens A+B 共 10 條 — SPEC-1 REFUTED、9 條 accepted 已修/已記錄;
fix 波 commits 6e219782/31a67ac7(後端)+ 2815d20f/94382944(前端))
