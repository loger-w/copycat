# 個股五題整體 review findings(2026-08-06 獨立 session)

> Review 對象:PR #21 / #22 / #25 / #27 / #28(全部已 merge master,基準 e0abcd20)。
> 交接文件:`docs/handoff-2026-08-06-quintet-review.md`。
> 方法:5 個對抗式 reviewer(跨 PR 交互 / stock_engine 精讀 / 真錢面 / 前端三題 /
> watchlist+規則引擎)並行,每條 finding 要求 file:line trace + 自我反駁;
> P0/P1 由主 session 逐條親自讀 code 覆核後才收錄。
> handoff §4 的已知風險(next-time 各節 / design.md Known Risks)已排除,不在此列。
> ⚠ 本檔位於 worktree,`git worktree remove` 前必須先複製到主 tree(§8 教訓)。

## 總結

- **P0 ×1、P1 ×2、P2 ×15**。
- handoff 最擔心的三個交互切角全部成立(好消息):`F:` instrument 不進 `_watch`
  的不變式三輪疊加後仍守住、規則熱重載無半重建窗、期貨回補走對 session。
  「壞檔清空自選」(EMPTY_WL 同類)確認不存在 clobber 路徑。
- ⚠ **P0 未修前不得做 prod 安全首單**(題3 待辦):首單會直接撞上 C-1。

## P0(主 session 已覆核確認)

### C-1 個股期送單被路由到 SendOptionOrder(選擇權通道)

- `copycat/capital/client.py:94` — `_FUTURE_PRODUCTS = {"TXF","MXF","TMF"}` 白名單
  未隨個股期擴充。
- 鏈路:`capital_api.py:207-215` 個股期單過 `_stkfut_gates`、`multiplier_of("CDF")`
  由 stkfut_map 查到 unit → 放行 → `client.py:678`
  `is_option = exchange_product_of("CDFI6") not in _FUTURE_PRODUCTS`;
  `exchange_product_of`(`mapping.py:85-102`)的 `_KNOWN_PRODUCTS` 只含指數乘數表
  ∪ 週選(`mapping.py:41-43`,不含個股期)→ 啟發式回 `"CDF"` → 不在白名單 →
  `is_option=True` → `com.py:164` 呼叫 **SendOptionOrder**。
- **送單與平倉(close_position)兩條路都中**。金額閘為個股期接了 stkfut_map,
  分流白名單沒同步 —— 兩處「什麼是期貨」定義不一致。
- 最好情況:群益/期交所退單 → 個股期下單+平倉整條功能不可用;最壞情況:
  選擇權通道解讀 FUTUREORDER struct 造成非預期委託。
- 測試缺口:`tests/capital/test_client.py:251-287` 只斷言 TXF→False、TXO/TX4→True;
  `tests/server/test_capital_api.py:409` 個股期案例不看 is_option。
  `test_client.py:287` 註解把「非 {TXF,MXF,TMF} 一律 option」寫成不變量,已過時。
- 修法方向:分流判準改為「個股期對映表可查到 → future」或白名單納入
  stkfut prod 集合;補 is_option 斷言測試。

## P1(主 session 已覆核確認)

### C-2 改價(correct-price)路徑沒有 BAD_TICK 閘

- `capital_api.py:226-232` correct-price route 直接組 `CorrectPriceRequest`,
  無 `_stkfut_gates`(該閘只掛在送單 route :207);client 側
  `correct_price` 只過總開關+price>0+名目金額。
- 前端可達:個股期合約態 `RightRail.tsx:94` market="fut" →
  `CapitalOrdersList.tsx:168` inline 改價輸入。
- 後果 fail-closed(期交所退單),但失效樣態正是 BAD_TICK 閘要消滅的
  「畫面只剩一句委託失敗」;改價(手動輸入)比點階梯更容易打錯檔位。

### E-1 期貨合約回補的累積量欄假設未實證,若 TradeVolume=0 重疊窗成交雙記

- `stock_models.py:265` `parse_hist_tick` 直接讀 `row["TradeVolume"]`(缺值歸 0);
  `stock_state.py:107-108` `apply_backfill` 的 survivor 判準
  (`cum_vol > backfill_max`)完全壓在這個欄位上。
- CLAUDE.md §8(2026-07-18 TXO probe)記載同段(`TC.F.TWF.*`)歷史 TICKS 的
  TradeVolume **全為 0**;#28 design D4 只實證了列數(2381 rows),probe 的
  TradeVolume 輸出未留存。現貨不受影響(測試真樣本有累積量)。
- 若個股期 leaf 同樣為 0:`backfill_max=0` → live tick 全算 survivor →
  訂閱~回補完成重疊窗的成交雙記(分鐘量/VWAP/內外盤灌水);且合約主圖因
  meta 漲跌停值變化(`stock_engine.py:777-782`)幾乎必補第二次,每補一層疊一層。
  零錯誤訊號。
- **定案方式:一次 TC4 probe**(對合約 leaf 印歷史 TICKS 首列 TradeVolume;
  用既有 `.claude/feat/stkfut-contracts/evidence/ticks_probe.py`)。依「不起第二條
  TC4 連線」紀律,probe 留給修復輪在 prod server 停機窗做。
  若實證有累積量 → 本條降級為「補 probe 證據留存」即可;若為 0 →
  回補側要以 TradeQuantity 逐檔重建 cum(probe 報告 §37 的原建議)。

## P2(15 條,依主題分組;未逐條主 session 覆核,repro 見各輪 reviewer 敘述)

### 真錢面(#28)

- **C-3** 前端 `isOrderBlocked`(`stkfut.ts:95`)在 unit=null(對映表過期)時放行,
  後端靠 `multiplier_of` ValueError 兜底 → 淨效果 fail-closed,但錯誤碼是
  INVALID_ORDER(指向使用者參數),真因是伺服器端對映檔過期。建議分開錯誤碼。
- **C-4** 當沖 checkbox(`StkfutLadder.tsx:115`)不隨合約切換重置;同元件的武裝鍵
  (:222 `[instrumentKey]` effect)與口數(RightRail per-instrument 分槽)都重置了,
  獨漏 dayTrade。
- **C-5** `_stkfut_gates` 的 `round(req.price*1000)`(`capital_api.py:147`)對 ±inf 拋
  OverflowError,`:212` 只 catch ValueError → 502 TC4_DOWN 而非 400(NaN 反而正確)。

### stock_engine(#27/#28)

- **E-2** `_backfilled`/`_backfill_failed` 日別記帳不隨退訂作廢(`stock_engine.py:312`
  removed 分支只清 `_no_data`):移出自選再加回後,退訂期間的分鐘缺口整天補不回來,
  畫面無訊號。
- **E-3** rollover pending 期間(08:00–09:00)合約 tick 不觸發 stage2(D14a 刻意),
  但昨日 `_last_cum` 讓 08:45–09:00 合約成交被靜默丟棄,09:00 現貨首筆後才靠回補
  補回;極端(自選空 + 主圖合約)整天不換日。stage2 需要對 pending 期間丟棄的
  期貨 tick 有補償點。
- **E-4** `set_watchlist` removed 分支無條件清 `_no_data`(:312-314),與
  `set_main_contract` 的 A7d 守則(仍有 owner 不清,:351-361)相反;main 兼自選、
  自自選移除時旗標被誤清。
- **E-5** `_rollover_stage2`(:650)在 event loop 迭代 `_states.values()`,
  `_acquire` 在 worker thread setdefault 插鍵 → 撞上 RuntimeError 會讓換日跑一半
  中斷且不再有第二次 stage2(`_pending_date` 已清)。`quotes()` 同 hazard 已防
  (:385),此處獨漏。修法:`list(self._states.values())`。

### 跨 PR / 資源共用

- **X-1** 訊號熱路徑真實成本 N×|window| 非 design 記載的 N:每顆 detector 無條件
  維護自己的 tick 窗(`signal_state.py:204`),`_eval_volume` 全窗 sum(:391);
  `window_secs` 可寫到 3600s、30 規則 × 30 檔上界下 event loop 可飽和,無任何訊號。
- **X-2** 三輪疊加後同一條 TC4 stock session 的 `api.lock` 有三個 REQ 生產者
  (群組回補 / basis sweep / Fut2 目錄查詢),而 lock timeout 5s < RCVTIMEO 10s
  (`tc4.py:227/70`):單一慢 REQ ⇒ 等鎖者 `_dispose` 整條連線;基準路失敗
  當日不重試(cdp=None 整天無訊號)、回補路誤報 tc4_status=down。
  boot 時序上 basis sweep 與 prewarm 必然重疊(`app.py:489` vs :699)。
- **X-3** WatchlistService 單鎖橫跨 `set_watchlist` 整段 ZMQ 訂閱迴圈
  (`watchlist_service.py:180`),`/watch` 寫入路徑無 timeout guard(autocomplete
  有 1s guard,寫入沒有):TC4 故障時最壞單指令持鎖 ~15 分鐘,後續所有寫入堆積。

### 前端(#22/#27/#28)

- **F-1** `refetch()` 副作用寫在 `setStatus` updater 內(`useStockStream.ts:219`),
  StrictMode 下 double-invoke + `pendingRefetchRef` 合併語意 → 每次回補完成
  串行多打一次 MB 級全量 snapshot。
- **F-2** `book` WS 訊息無 stale guard 也不進 pending buffer(:177):refetch 期間
  的新簿被較舊 snapshot 回捲,鎖板/盤後推播稀疏時回捲窗可達數十秒
  (鎖板正是 §0a 核心場景)。
- **F-3** `refetch` 非 2xx / throw 靜默失敗無重試(:113/:124),`accum===null` 時
  tick 早退讓 seq-gap 自癒死路 → 頁面釘「載入中…」;#28 的 `?contract=` 讓
  502/503 從正常操作可達,放大既有問題。
- **F-4** `<TickTape key={code}>`(`StockPage.tsx:381`)沒跟上 instrumentKey,
  換月/切合約時展開筆數跨 instrument 存活(純顯示)。
- **F-5** VP 價位帶 `half = tickOf(p)/2`(`volume-profile.ts:64`)在 tick 級距邊界
  (50/100/500/1000 元)跨過鄰檔,兩根長條 y 重疊視覺失真(純視覺)。

### watchlist / 規則(#21/#25)

- **W-1** `add`/`remove` 同為 read-modify-write 卻繞過 `_require_current`
  (`watchlist_service.py:70/95` vs :184):壞檔時回「股號格式不正確」等誤導錯誤
  而非 WATCHLIST_UNAVAILABLE(零寫,不清空,僅語意錯)。
- **W-2** `_current_canonical` catch 集合漏 AttributeError(:217):JSON 根非物件時
  自癒路徑(前端 PUT)變 502 TC4_DOWN,唯一出路是手動刪檔。
- **W-3** `handle_add` 的 group 參數不擋保留名「未分組」(`discord_bot.py:218`),
  與其餘三個群組 handler 不一致;且群組名不合法讓整筆 add 連坐失敗
  (股票也沒加進去),而「未分組」是 bot 自己印在 /watch list 畫面上的名字。

## 確認過沒問題的重點(正面證據,de-risk 清單)

- `F:` instrument 鍵永不進 `_watch` / 訊號層 / 同群摘要 / 換日(`_CODE_RE` 拒冒號
  + membership gate + `rolls_the_day` + quotes 只迭代 `_watchlist`)。
- 規則熱重載:save 後 swap `_slots` + seed 在同一無 await 同步區塊,無半重建窗;
  壞規則檔 fail-loud(503)不會靜默空規則。
- 期貨回補走持有 REALTIME 訂閱的同一條 stock session(§8 通則);回補窗/試撮窗
  live 與回補同一把尺。
- watchlist:無 clobber 路徑(壞檔都在 load/normalize 拋,save 到不了);
  PUT/bot 同一條 event loop 同一把 asyncio.Lock,`save_watchlist` 全 repo 單一
  呼叫點且在鎖內;取鎖順序單向無死鎖。
- 乘數/金額閘:stkfut_map 320 prod 與指數表零碰撞,標準/小型各自帶 unit,
  「取大者」只影響顯示腿選擇不影響金額閘。
- 元/毫元轉換點逐一核對無雙重換算;前端階梯只出合法檔位、市價 0 檔位歸一。
- FUTUREORDER 其餘欄位(帳號/契約碼/BuySell/口數/新平倉/TIF/市價升 IOC)對映正確;
  審計涵蓋個股期;timeout 走 shield +「結果未知勿重送」+ late 審計行。
- 前端五個 refetch 觸發點全走單一 `stateUrl`,恆帶 contract;overlay 同類
  過渡漏洞在 bars/VP/五檔/訊號欄四處均未重現;mini 圖牆 memo 邊界成立、
  群組檢視不改訂閱池不搶主圖。
- 舊 enabled API 退役完整(零殘留 caller);Discord fallback webhook 可達。

## 建議處置(依 handoff §7)

1. **C-1(P0)+ C-2(P1)**:一輪 `/bug`(同檔真錢面,引用本檔 + stkfut design SC-6)。
   修完才能做 prod 安全首單。
2. **E-1(P1)**:`/bug` 或 `/mod`,第一步是 probe 定案(prod 停機窗跑
   ticks_probe 對合約 leaf),依結果決定是否重建 cum。
3. **15 條 P2**:記 `docs/next-time.md`(X-2/X-3/E-5 與 F-2/F-3 建議優先,
   前者是共用資源結構性問題、後者影響鎖板場景與可用性)。
