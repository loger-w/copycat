# 群組圖牆逐筆(`mod/group-grid-ticks`,C9)— change spec

來源:`docs/next-time.md` 08-28 節「`/mod` 群組圖牆逐筆」(C9);本 session `grilling` 拍板(2026-09-02)。
動機(user 原話):「我在用群組看時,發現分時圖變動很慢,其實很影響下單體驗」。

## 0. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 群組卡片資料 | 60 s 拉 `group-state`(分鐘 K + VWAP/高低/VP 聚合,**刻意不送 ticks**)+ 每秒 `watchlist_quote` 只覆寫當前分鐘收盤點;卡片 accum 是唯讀渲染輸入,`seq=0`、不吃 `applyTick` | 卡片 accum 由 group-state 播種(含 `seq` / `vwap_vol`),之後**逐筆** `applyTick`(與主圖同款);60 s 輪詢保留為週期性重播種 |
| 後端逐筆推播 | `tick` 訊息**一筆一則**,只推 `code == _main` | 新訊息型別 `ticks`:每 0.1 s 一則,含該窗內「瀏覽器看得到的檔」(主圖 ∪ 各連線登記的檢視集合)全部成交,**逐筆不合併**;舊 `tick` 型別退役 |
| 瀏覽器看哪些檔 | 後端不知道;只知 `_main` | 前端經同一條 `/ws/stock` 送 `{"type":"view","codes":[…]}`;per-connection 登記,斷線自動清;union 進 `_tick_targets`。**不動訂閱池**(群組成員本來就在自選池全天訂著) |
| 不丟保險 | 主圖:seq 跳號 → 全量 refetch;佇列滿丟最舊**靜默**(零 log、零計數) | 每檔 seq 跳號 → 該檔單獨重拉 `group-state?codes=X`;`WsBroadcaster` 丟包計數 + 節流 WARNING;50 檔壓測釘「訊息數 ≪ tick 數、丟包 0、逐檔 seq 連續」 |
| 重繪 | `quotes` 每秒換 identity → 父層每秒 render,memo 擋掉沒變的卡 | 一則打包 = 一次 commit(React 自動批次);只有收到 tick 的卡 accum 換 identity。**不另做 rAF**(見 §2.6) |
| 群組選單 | 列全部群組(含「盤前篩選」~60 檔);未分組不可選 | 隱藏「盤前篩選」;新增虛擬「未分組」(即時算,不落檔) |
| 點訊號 | 只換右欄標的,群組不切 | 群組檢視下:現群組已含 → 不切;否則切到含該檔的第一個群組(含未分組);不在自選 → 只換右欄 |

## 1. Caller map(grep 2026-09-02,worktree HEAD = master a344da9f)

後端:
- `tick` 訊息唯一產生點 `stock_engine.py::_handle_quote`(ingest 為真 & `code == self._main`);消費端:`tests/server/test_stock_engine.py` 5 處(L475/504/2261/2343/2541)。
- `WsBroadcaster.publish` 六路 WS 共用(capital / futures / corr / river / stock / index);丟包政策改動只加計數與 log,政策不變。
- `relay` 八個 accept 點(app.py 6 + capital_api.py 2)共用;`_recv` 現況忽略所有 client 訊息 → 新增 `on_message` 選配參數,預設 None = 逐字舊行為。
- `light_snapshot` 唯一 caller `StockEngine.group_snapshot` → `/api/stock/group-state`;前端讀者 `useGroupSnapshots.fetchGroupState`。
- `SCREEN_GROUP = "盤前篩選"`:`server/screen_engine.py` 產生點;前端目前**零**字面引用(只有註解)→ 新增前端鏡像常數 + parity 測試。

前端:
- `useStockStream` 的 `tick` case:唯一消費 WS tick 的地方;`applyTick` 另有 `stock-accum.test.ts`。
- `accumFromGroupSnapshot` callers:`CardIntradayChart`(唯一)。
- `GroupGridView` props 持有者:`StockPage`(唯一);`selectedGroup` 真相源 `useStockGroup`(localStorage `STOCK_GROUP_KEY`)。
- `SignalRail.onSelect` → `StockPage` 直接轉 `onSelect`(App 的 setStockCode)。
- `WatchlistSidebar.onSelect(next, group)`:群組列帶名、未分組列帶 `null`(F2:群組檢視下 null 不切)。
- `WsHandle` 無 `send` → 新增(additive)。

## 2. 設計決策

### 2.1 wire:`ticks` 打包訊息(🔴 後端 + 前端)
`{"type":"ticks","items":[{code,t,p,q,side,b,a,h,l,seq},…]}`,item 欄位與舊 `tick` 逐字相同(少 `type`)。
產生點:`_handle_quote` ingest 為真且 `code == _main or code in _tick_targets` → append 進 `_pending_ticks`;
新 task `_flush_ticks_loop`(`tick_flush_secs`,預設 0.1;測試 0.01)每週期非空才 publish 一則。
同一檔在同一則內 seq 遞增;跨檔順序 = 到貨順序。主圖不再另發單筆 `tick`(主圖最多晚 0.1 s,user 拍板接受)。
`book` 照舊逐則即發(五檔是「最新有意義」,不需累積)。

### 2.2 檢視集合登記(🟢 後端)
`StockEngine.set_view(token, codes)` / `clear_view(token)`;`_views: dict[object, frozenset[str]]`,
`_tick_targets = ∪ views`(改動時重算)。`ws_stock` 每條連線一個 token;`relay(on_message=…)` 收到
`{"type":"view","codes":[…]}` 即 `set_view`,`finally` `clear_view`。非法 JSON / 非 dict / 非 view → WARNING 一則後忽略
(client 輸入驗證,不是不懂的錯)。**不碰 `_refs` / TC4 SUB**;未訂閱的 code 登記了也不會有 tick(無害)。
主圖恆在收件人集合(`_main`),前端不必把主圖塞進 view。

### 2.3 丟包可觀測(🟢 後端)
`WsBroadcaster.dropped`(累計)+ 首次丟包後每 60 s 最多一則 WARNING(`ws 佇列滿:丟最舊 n 則(累計 N,maxsize M)`)。
政策(丟最舊保最新)逐字不變。盤後判準:`grep "佇列滿" logs/server-*.log` 為 0 = 沒丟。

### 2.4 group-state 加鍵(🟢 後端,additive)
`light_snapshot` 加 `seq`(tick 套用錨點)與 `vwap_vol`(增量 VWAP 分母;語意同 `snapshot()`)。舊鍵一個不動。

### 2.5 前端:群組 live accum
- `lib/tick-stream.ts`(模組層 store,沿 `signal-bus` / `useChartToggles` 慣例):`setTickView(codes)` / `subscribeTickView` /
  `emitTicks(items)` / `subscribeTicks`。
- `useStockStream`:`ticks` case → 主圖項走既有 tick 邏輯(pending / 跳號 refetch),整則套完一次 `setAccum`;
  非主圖項 `emitTicks`。訂閱 `tick-stream` 的 view 變化 → `handle.send({"type":"view","codes"})`;**onOpen 重送**(重連後新 token)。
- `hooks/useGroupLiveAccums(codes, snapshots)`:以 `accumFromGroupSnapshot`(改吃 `seq` / `vwap_vol` 播種 `amountMilli` / `volume`)
  播種;訂閱 `subscribeTicks`;per-code `seq === acc.seq + 1` 才 `applyTick`,否則該檔 refetch `group-state?codes=X`
  (單飛 + pending 重放 `seq > snap.seq`,沿 useStockStream 樣板);60 s 輪詢新 `snapshots` 到 → 全體重播種。
- `GroupGridView`:掛載 / codes 變 → `setTickView(codes)`;卸載 → `setTickView([])`。卡片圖改吃 `accum`(`CardIntradayChart` props
  `snap+liveP` → `accum`);`snap` 仍供三態旗標。`quote` 只餵卡片頭的價格區,不再每秒延伸分鐘線。

### 2.6 為什麼不做 rAF 合批
打包已把 commit 頻率釘在 ≤ 10 次/s(每則一次 setState,React 18+ 自動批次同一 handler 內的多個 setState);
一畫格 16 ms ≫ 一次 commit。rAF 只在「訊息積壓時多則合一 commit」有價值,而積壓本身就是丟包前兆,由 §2.3 觀測。
驗收仍量:開盤 5 分鐘 DevTools trace 無 > 50 ms long task(§4)。量到才加,不預先加抽象(鐵則 B)。

### 2.7 三件 UI(各自獨立 commit)
- (a) 群組 pill 隱藏 `SCREEN_GROUP_NAME`(前端鏡像常數 `lib/constants.ts`,後端 parity 測試直讀前端檔;側欄照舊顯示)。
  localStorage 記住的是「盤前篩選」→ 走既有 fallback 第一個可見群組。
- (b) 虛擬「未分組」pill:`selectedGroup` 值域加 sentinel `UNGROUPED_PICK`;`StockPage` 以 `ungroupedCodes(wl)` 傳
  `ungrouped` prop;側欄未分組列在群組檢視下**改為切到未分組**(原 F2「未分組列不切」明文推翻:未分組現在是可選的一組)。
- (c) 訊號 → 群組:純函式 `groupForCode(groups, ungrouped, current, code)`:current 含 → current;否則第一個含它的
  群組(群組序,未分組最後;排除盤前篩選);皆無 → null(只換右欄)。`StockPage` 包 `SignalRail.onSelect`。

## 3. 既有行為白名單(不可破壞;優先於新行為)

| # | 既有行為 | 守住的方式 |
|---|---|---|
| W1 | `book` / `watchlist_quote` / `status` / `stkfut` / `signal` / `watchlist_changed` 六型訊息的形狀、產生點、節流(1 s)、試撮翻轉補推逐字不變 | 既有 engine 測試不改 |
| W2 | 訂閱池(`_refs` / owner / TC4 SUB-UNSUB)不因檢視集合而變;`set_view` 零副作用於池 | 新測試斷言 `src.subscribed` 不變 |
| W3 | `/api/stock/group-state`:不 `set_main`、去重保序、150 上限、`no_data` 語意、既有鍵全在;新鍵 additive | `TestGroupSnapshot` / `test_app` 既有案不改 |
| W4 | 主圖:seq 跳號(含回退)→ 全量 refetch、refetch 期間 pending 重放 `seq > snap.seq`、六個 refetch 觸發、`stateUrl` 逐字 | `useStockStream.test.ts` 既有案只改訊息型別(tick → ticks 打包),斷言語意不動 |
| W5 | `WsBroadcaster` 丟最舊保最新;`relay` 心跳 / 斷線 / 例外分流;`on_message` 未傳時 client 訊息一律忽略 | `TestRelay` 既有案不改 |
| W6 | 六路其他 WS(capital / futures / corr / river / index)零改動 | 不碰 |
| W7 | `GroupGridView`:空態三分、受控 pill + fallback、`gridShape`、fills / positions identity、只有變的卡重畫 | 既有 GroupGridView 四檔測試不改(memo 案改以 tick 為變因) |
| W8 | 60 s `group-state` 輪詢 + 盤外 `msUntilTradingOpen` 不變 | `useGroupSnapshots.test` 不改 |
| W9 | 單檔檢視下點訊號 / 點側欄列行為不變;群組檢視點卡片只換右欄 | `StockPage.test` 既有案不改 |
| W10 | 訊號層 `signal_hub.on_tick` 對全自選逐筆評估,與檢視集合無關 | 不碰 |
| W11 | rollover(seq 歸零)/ `apply_backfill`(seq +1000)語意不變 = 前端跳號訊號 | 不碰 |
| W12 | CLAUDE.md §4 既有契約(心跳 / `tape=0` / seq 兩口徑)不變;新增三條(ticks 打包 / view 入站 / 盤前篩選群組名 parity) | 文件 |
| W13 | 側欄 F2:群組列在群組檢視下切到該組 | 既有案不改;未分組列那半明文改(§2.7b) |

事前標記「該變」的既有測試:`test_stock_engine.py` 5 處 `type == "tick"`(改讀 `ticks` 打包 items);
`useStockStream.test.ts` 的 tick 案(訊息形改打包);`StockPage.test.tsx`「未分組列不切」半句;
`GroupGridView.memo.test.tsx` 變因由 quote 改為 tick(quote 每秒仍只重畫變的卡,語意不變)。

## 4. 驗收

- 自動化:pytest / ruff / pyright / validate / vitest / tsc / eslint / react-doctor 全綠。
- 壓測(單元):FakeSource 50 檔 × 20 tick 同窗灌入 → 打包則數 ≤ 3、items 1000、逐檔 seq 1..20 連續、`dropped == 0`;
  maxsize=5 對照組 → `dropped > 0` 且 WARNING 恰一則。
- 真環境(盤中):群組檢視卡片線與量隨成交動,與右欄主圖同步(動機判準);`grep "佇列滿"` 為 0;
  開盤 5 分鐘 DevTools performance trace 無 > 50 ms long task,截圖入 `evidence/`;三件 UI user 過目。
