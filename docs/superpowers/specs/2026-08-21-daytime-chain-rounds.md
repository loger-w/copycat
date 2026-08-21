# 2026-08-21 日間+夜間無人值守鏈:M0 + R1–R10

> user 外出,各 round 各自 session 跑;「處理 RN」= 讀本檔 §RN,照尾端起跑 prompt 跑流程。
> 本檔**唯讀**(sessions 不回寫本檔;進度記 memory + next-time 勾銷),避免多 session 互改衝突。
> 證據來源一律 `docs/next-time.md`(2026-08-20 驗證輪已把多數條目升級成實測數字)。

## §0 總表與排程

| 棒 | 案 | 分支 | 類型 | 時段限制 | 前置訊號(grep origin/master) |
|---|---|---|---|---|---|
| M0 | 盤中量測觀察(不改 code) | 無(master) | 觀察 | **立即,13:45 前** | 無 |
| R1 | B2 CDP 右緣標籤避讓 | `mod/cdp-edge-label-avoid` | 前端 | 隨時 | 無(可與 M0 平行,見規則) |
| R2 | D a11y 批 | `mod/a11y-radiogroup-tablist-contrast` | 前端 | 隨時 | R1 merge:`grep cdp-edge` |
| R3 | B4 訊號提示合併 | `mod/signal-alert-grouping` | 前端 | 隨時 | R2 merge:`grep a11y` |
| R4 | B10+B11 前端小批 | `mod/drag-void-and-edge-snap` | 前端 | 隨時 | R3 merge:`grep alert-grouping` |
| R5 | B7+B8+B9 | `mod/corr-readout-clamp-healgate` | 前+後端 | **13:45 後**才可重啟 prod | R4 merge:`grep drag-void` |
| R6 | B12 日曆小批 | `mod/calendar-visibility-batch` | 前+後端 | 13:45 後 | R5 merge:`grep healgate` |
| R7 | A4 BalanceCollector 輪次 | `bug/balance-collector-round-token` | 後端 | 13:45 後 | R6 merge:`grep calendar-visibility` |
| R8 | A2 timeout 旗標家族 | `bug/history-timeout-propagation` | 後端 | 13:45 後 | R7 merge:`grep balance-collector` |
| R9 | B14+B15 | `mod/txo-backfill-progress-tape0` | 前+後端 | 13:45 後 | R8 merge:`grep timeout-propagation` |
| R10 | C 重構批 | `refactor/housekeeping-batch-2026-08-21` | 前+後端 | 13:45 後 | R9 merge:`grep tape0` |

**通用規則(每個 session 都要遵守)**

1. **串行、不開 worktree**:同一工作樹,開工前 `git checkout master && git pull`,`git status` 必須乾淨
   (只允許 `node_modules/` untracked)。輪詢前置訊號用 `/loop` 每 15 分鐘
   `git fetch && git log origin/master --oneline | grep <關鍵字>`。
2. **逾時保底 90 分鐘**:上一棒 90 分鐘未 merge(多半卡在鐵則 F 停下等 user)→ 從當下 master 直接開工;
   各 round 檔案已盡量設計零重疊,衝突風險低;`docs/next-time.md` 收尾勾銷若衝突以 rebase 解。
3. **prod backend(8721)**:M0 於 13:45 前起最新 master 並**不得重啟**(盤中不重啟紀律,ops-discipline);
   13:45 後(週五夜盤 15:00 起,in-memory 可棄)含後端改動的 round merge 後**可**重啟一次
   (port → PID taskkill,`.venv\Scripts\python -m copycat.server` 背景),重啟後驗 `/api/health` 的 `git_sha`。
   純前端 round 不碰 8721。
4. **前端 preview(4173)**:M0 起 `npm run build && npm run preview`;前端 round merge 後
   `cd frontend && npm run build` 重建 dist 即可(preview 吃磁碟 dist,重整頁面生效),不必重啟 preview。
5. **前端驗證**:`npm run dev`(5173)+ claude-in-chrome;viewport 控制用同源 iframe host
   (`frontend/public/__viewport_host.html?w=&h=`,臨時檔收尾刪);收 vite 用 port → PID,
   **不要 `taskkill //IM node.exe`**(會殺 MCP)。hidden tab 的 ResizeObserver 不投遞 → 先 screenshot 逼一幀再量 DOM
   (ops-discipline)。
6. **收尾三件事**:PR auto-merge(branch-lifecycle)→ `docs/next-time.md` 勾銷對應條目(標日期與 PR 號)→
   寫 memory(`<slug>-shipped.md` + MEMORY.md 一行,含「待 user 過目」點)。
7. **模型路由**:S 級主 session 直做;M 級實作 dispatch(顯式帶 model);review 一律 dispatch。

---

## §M0 盤中量測觀察 session(不改 code,13:45 前)

**目的**:把 next-time 裡「留次一盤中實測」的幾條一次收掉,並順手做健康觀察;產出 = 數字回寫
next-time + 截圖入 `docs/specs/next-time-mcp-verification-2026-08-21/screenshots/`。

**步驟**

1. 起 prod:`git checkout master && git pull`;確認達錢 4 在(port 50774 listener);
   `.venv\Scripts\python -m copycat.server` 背景起 → `/api/health` sha = origin/master HEAD。
   `cd frontend && npm run build && npm run preview`(4173)。**之後整天不重啟 8721。**
2. **82 群組檢視拉全量 tape(實測大小)**:盤中對自選活躍檔 `curl /api/stock/state/{code}` 量 bytes 與 `ticks` 長度
   (08-20 盤後只量到 579B,早盤 log 顯示 3450 回填 4266 ticks);回寫 08-17 group-grid R4 節該條。
3. **80 群組圖牆盤中量測**:preview 分頁開群組檢視(最大群組 6 檔)—— DevTools network 看冷 cache
   `/api/stock/overlay` 耗時、`group-state` payload、`liveP` 每秒 paint(PerformanceObserver longtask);
   回寫同節。
4. **1 真 tick trace(R6 memo 邊界驗證)**:preview 分頁(prod build)期貨 tab 與個股 tab 各錄 30s
   DevTools performance trace,看 scripting 佔比;預期見 `.claude/refactor/memo-boundaries/verification.md`
   (期貨 tab rail 10Hz 是正確行為);回寫 08-20 R6 節。
5. **17 TXO 日盤推播率**:`scratchpad` 寫 websockets client 連 `/ws/txo-pnl` 60s,記每則 bytes 與則/秒
   (08-20 夜盤 = 17.1KB、0.4/s);回寫 08-19 txo-snapshot 節。
6. **log 對帳**:最新 `logs/server-*.log` grep (a) `trade-status-observe`(106 緩撮蒐證,有樣本就依
   next-time 08-13 trial-pause 節判讀);(b) `負股數` / `種類標籤未知`(若 user 今天沒交易應為零);
   (c) `零推播自癒` 各 symbol 計數(33 海外腿 churn 頻率,08-21 凌晨 SXF.HOT 每 4–5 分一發)。
7. **A3 殭屍勾銷**:查 `docs/next-time.md` 「futures_engine 會間歇性整段零推播」P1 條(2026-07-30
   realtime-correlation 節附近)是否已被 08-18 refcount 根治吸收(`git log --grep refcount`、memory
   `tc4-realtime-refcount-kill-shipped`),是則打 `[x]` 標「2026-08-21 查證:已由 PR #66 吸收」。
8. 13:45 後:把 2–7 的數字回寫 next-time(只在 `git branch --show-current` 是 master 且樹乾淨時 commit,
   否則把 diff 存 scratchpad 留給 R10 收尾一併提交)。**不要**動 8721。

**與 R1 平行的注意**:M0 只讀 + 最後 docs commit;R1 在同一工作樹切分支時,8721 仍跑已載入的 master
code(Python 模組已 import),preview 吃 dist,皆不受影響。M0 的 docs commit 時機照第 8 點。

**起跑 prompt**
```
處理 M0:讀 docs/superpowers/specs/2026-08-21-daytime-chain-rounds.md §M0,13:45 前完成盤中量測(82/80/1/17)與 log 對帳,數字回寫 next-time,不改 code、不重啟 8721。
```

---

## §R1 B2 CDP 右緣標籤避讓(/mod,M)

**證據**:2026-08-20 MCP 量測,2330 平靜日右緣 11 顆標籤(5 顆 CDP`*` + MA5/MA20/VWAP/昨收/現價)擠 36px 縱距,
**9 對兩兩相疊**;截圖 `docs/specs/next-time-mcp-verification-2026-08-20/screenshots/102-cdp-label-cluster-2330.jpg`。
next-time:08-14 fix/index-line-vanish 節「CDP 五個右緣帶標籤自身互疊」+ 08-14 index-overlay 節「修法可借 index 側 rightEdgeLabels」。

**檔案**:`frontend/src/lib/stock-intraday-svg.ts`(個股圖 `edgePriceLabels` 1D 避讓,現只套現價/VWAP 級標籤)、
`frontend/src/components/stock/StockIntradayChart.tsx`、對照 `frontend/src/lib/index-chart-svg.ts::rightEdgeLabels`
(fixed 錨 + 三段式 + 殘餘丟棄,index 側演算法)。

**修法候選(spec 拍板)**:(a) 把 `edgePriceLabels` 的 1D 避讓推廣到 CDP 帶標籤(同一支函式換 bounds);
(b) 近價合併顯示(`2365*/2360*` 併一顆);(c) 先比對兩份演算法可否合一(next-time 明示「不要各長一套」)。
**行為契約**:標籤文字與價位不變、只動 y;avg/VWAP 標籤既有避讓不得退化(`stock-intraday-svg.pegs.test.ts`)。

**驗證**:以 2330 08-20 的 CDP 五值 + MA/VWAP/昨收/現價為 fixture 做幾何測試 → 相疊對數 0(或拍板的最小間距);
MCP 截圖 2330 對照(盤後資料亦可)。gate:npm test / tsc / eslint / react-doctor。

```
處理 R1:讀 docs/superpowers/specs/2026-08-21-daytime-chain-rounds.md §R1,跑 /mod「個股分時圖 CDP 右緣標籤避讓(2330 實測 11 顆 9 對相疊)」,分支 mod/cdp-edge-label-avoid。純前端,不碰 8721。
```

---

## §R2 D a11y 批(/mod,S–M)

**證據**:next-time 08-17 ladder-pills-avgpct R6 節(review A3/A6)+ 08-14 overview-subtabs 節(review A-4)+
08-11 react-doctor 快修批留尾(側欄列無鍵盤路徑)。

**三件事**
1. **aria-pressed pill 群 → radiogroup**(sr-only radio + label,單選/方向鍵/roving tabindex 免費):
   PriceLadder 交易別 pill、StockPage 檢視切換、GroupGridView 檔數、OrderPanel;含 FuturesPage/FuturesLadder/
   MarketPane 同構處(`grep -rl aria-pressed frontend/src/components`)。**同時**把 tablist 半套補全:
   IndexPage + RightRail 的 `role=tablist/tab` 補 `aria-controls` / `role=tabpanel` + `aria-labelledby` / roving tabindex。
2. **零態對比**:`text-ink-dim` 對 `bg-surface` 2.92:1 → 改 `text-ink-muted`(6.06:1),三處一起
   (群組平均漲幅 0.00% / stockRow / GroupGridView QuoteCell 零態)。
3. **側欄自選列鍵盤路徑**(WatchlistSidebar row div 無鍵盤、組內排序無鍵盤):至少 row 可 focus + Enter 選取。

**契約**:視覺零變(只改語意與鍵盤);react-doctor 既有誤報 triage 不翻案(`prefer-tag-over-role` GroupGridView 卡片)。
**驗證**:RTL 測試用 role 查詢(`getByRole("radio")` / `tab` + `aria-selected`);鍵盤事件測試;對比用既有 token 即可。

```
處理 R2:讀 …rounds.md §R2,跑 /mod「a11y 批:pill 群改 radiogroup + tablist 補全 + 零態對比 + 側欄鍵盤路徑」,分支 mod/a11y-radiogroup-tablist-contrast。純前端。
```

---

## §R3 B4 訊號提示合併(/mod,S–M)

**證據**:next-time 08-20 signal-alert-side-effects 節兩條 + 08-18 denoise 節「toast/桌面通知不合併」。
現況:同 tick 三則仍跳三張 toast;桌面通知 5s 窗固定 tag **leading-edge**(看到窗內最舊那則)。

**檔案**:`frontend/src/hooks/useSignalAlerts.ts`(+ test)、`frontend/src/lib/signal-model.ts::groupSignals`
(SignalRail 合併口徑,**沿用不另長一套**)、`frontend/src/components/ToastStack.tsx`、`useSignalSound.ts`
(音效每 tick 一聲即可,別跟著合併變多聲)。

**做法**:useSignalAlerts 走 `groupSignals` 口徑把同 tick 多則合成一張 toast(文案沿 SignalRail 合併列語意);
通知改 latest-wins(窗內記最後一則、窗尾補發一次)或維持 leading 但文案吃 grouping —— spec 拍板。
**契約**:08-20 R4 的 suspended 不建節點 / closed 重建 / 固定 tag 節流三條 lock 不得破。

```
處理 R3:讀 …rounds.md §R3,跑 /mod「訊號 toast 與桌面通知走 groupSignals 合併 + 通知 latest-wins」,分支 mod/signal-alert-grouping。純前端。
```

---

## §R4 B10 + B11 前端小批(/mod,S)

**B10 拖曳到 sticky 搜尋區改作廢**:next-time 08-13 watchlist-ux 節(review A-3);2026-08-20 vitest 探針證實
y 在所有 zone 上方 → 回最上 zone index 0。檔案 `frontend/src/lib/list-drag.ts::dropTargetFromPointer` +
`WatchlistSidebar.tsx` 的 `zonesNow`。做法:把 sticky 高度傳進 zones,y 落帶內回 null;不動 ROW_H / bounds。

**B11 貼漲跌停 snap 口徑統一 + fut ≤0 守門**:next-time 08-17 ladder-market-buttons R1 節兩條;探針證實
`futMarketEdgeMilli` 對 0 回 0、負值放行(stkfut 版回 null)。檔案 `frontend/src/lib/futures-ladder.ts`、
`frontend/src/components/rail/RightRail.tsx:256`(個股期平倉用未 snap 的 `meta.upper/lower`)、`lib/stkfut.ts`。
做法:平倉也吃 snap 版 + fut 加 `≤0 → null`;**`FuturesPage.test.tsx:150-168` 值斷言事前標為該變**(🔴)。

**契約**:兩者都是「同一標的兩處邊價必須同值」與「不合法落點不送」,不改下單路由。

```
處理 R4:讀 …rounds.md §R4,跑 /mod「拖曳 sticky 落點作廢 + 貼漲跌停 snap 口徑統一與 ≤0 守門」,分支 mod/drag-void-and-edge-snap。純前端。
```

---

## §R5 B7 + B8 + B9(/mod,S×3;**13:45 後**)

三條 2026-08-20 機械探針全證實,修法明確、互不重疊:

- **B7 重疊圖空腿 readout 印「—」**(前端):`frontend/src/lib/river-chart-svg.ts::buildOverlayGeometry` 濾掉
  `minutes={}` 的腿 → `RiverOverlay.tsx` readout 跟著消失。做法:readout 改由未過濾 entries 產生,空腿印「—」;
  圖上仍不畫(保留「不是 0% 直線」語意)。next-time 08-17 corr R5 節 review R-2。
- **B8 小日經 13:50 蓋 13:45 收盤**(後端):`copycat/live/river_models.py::offset_of` 對 13:46–13:50 全回
  offset 300,`river_state.py::push` 無條件 last-write-wins。做法:clamp 只在 end 格尚無值時套用
  (把 apply_backfill 的 don't-overwrite 語意搬進 push 的 clamp 分支)。同節 review R-3;ES/NQ/YM 同類受益。
- **B9 自癒閘跨午夜**(後端):`copycat/server/app.py::_heal_gate` 週六 01:00 gate=False(該救不救)、
  週一 01:00 gate=True(空 churn)—— 真日曆探針證實。做法:凌晨段(hour < 6,TXO/futures 的 clock_gate
  為真)改查前一日 `is_trading_day`;stock/index 的日盤閘不受影響。next-time 08-19 coalesce 節 + 08-18 refcount 節。
  **本週末就是驗證窗**(週五夜盤跨週六凌晨):merge + 重啟後看 log 週六 00:00–05:00 自癒是否仍活。

**prod**:merge 後重啟 8721(13:45 後),health sha 驗證。

```
處理 R5:讀 …rounds.md §R5,跑 /mod「重疊圖空腿 readout 印 — / 江波圖收盤 clamp 不覆寫 / 自癒閘跨午夜查前一日」,分支 mod/corr-readout-clamp-healgate。13:45 後才可重啟 8721。
```

---

## §R6 B12 日曆小批(/mod,S–M;13:45 後)

**證據**:next-time 08-16 trading-calendar 節三條(review S5/S6 + 試撮 badge)。

1. **錯標日可見訊號**:日曆把真交易日標成假日時全站輪詢靜默停擺、唯一提示是 boot WARNING。做法:前端拿
   `GET /api/calendar` 的 holidays 命中本機今日 → 標頭掛膠囊「日曆判今日休市」。
2. **SignalRail 標題帶日期**:假日開站掛的是上一交易日訊號,標題仍寫「今日訊號」(`SignalRail.tsx:118-122`);
   改「`MM-DD` 訊號」(等於今日時仍「今日訊號」),沿 LimitList 既有口徑。
3. **試撮(緩)badge 接日曆**:休市日/週末窗內純時間照標;同一份 holidays 餵給那條判定(trial 推導在
   `stock_engine` / 前端 `trial` 旗標讀者,grep `trial`)。

**契約**:日曆資料單一來源 `/api/calendar`;交易日盤前冷啟動(R3b)**不在本輪**(待 user 拍板)。

```
處理 R6:讀 …rounds.md §R6,跑 /mod「日曆可見性小批:錯標膠囊 + SignalRail 標題帶日期 + 試撮 badge 接日曆」,分支 mod/calendar-visibility-batch。13:45 後才可重啟 8721。
```

---

## §R7 A4 BalanceCollector 輪次識別(/bug,S–M;13:45 後)

**證據**:next-time 08-13 ladder-order-status 節(review C2/W2 rejected 當輪 scope)。
零事件死查詢 10s 逾期解卡後 `_balance.reset()` 再發第二次查詢,第一輪遲到的 `##` 以空 staging flush →
`set_positions([])` → 有庫存顯示無部位(最壞 60s 自癒)。**2026-08-20 當晚的當沖空單修法讓平倉鍵依部位
存在與否鎖/解鎖,部位被誤清空的代價變大**,升級開工。

**檔案**:`copycat/capital/balance.py::BalanceCollector`(feed/poll/reset)、`copycat/capital/client.py`
(`_on_balance_complete` / 損益 / OI 三段串行 + 10s 逾期解卡)。
**做法候選**:發查詢帶輪次序號給 collector(feed 的 `##` 驗 token,舊輪事件丟棄)或逾期解卡改換新 collector 實例;
三個 collector 共用節奏,一起改。
**驗證**:紅測試重現「舊輪 ## 遲到 → 不得 flush 空集合」;FakeCom 可注入亂序事件。

```
處理 R7:讀 …rounds.md §R7,跑 /bug「BalanceCollector 無輪次識別:遲到 ## 清空部位顯示」,分支 bug/balance-collector-round-token。13:45 後才可重啟 8721。
```

---

## §R8 A2 timeout 旗標家族(/bug,M;13:45 後)

**證據**:next-time 08-13 index-chart-empty-minutes 節首條 + 2026-08-20 caller 盤點:
`HistoryResult.timed_out` 旗標已存在(08-05 bars 三態),**只有** `stock_source.py:691-709`(stock bars)在讀;
`futures_source.py:187/192`、`stock_source.py:643/721/724` 皆 `.rows` 直取丟旗標;`river_backfill.py:52`
另有自己的「首頁非空即 break」迴圈(且 `minute_end_from_1k` 只讀 Time 不讀 Date,凍結 stub 會變今日分鐘)。
真實事故:river 六腿 08:23 三腿同秒 timeout 回空無重試。

**做法**:逐 caller 決定語意 —— futures K 線走與 stock bars 同款三態 status;stock 643/721/724(backfill /
daily)timeout → 拋可重試例外或回 `None` 讓既有 retry 排程接手(**不得**把 timeout 讀成「資料面就是沒有」);
river 改走基底 `_collect_history` 或至少讀 timed_out + Date 判定。動基底 `TC4QuoteSource` 前先盤 blast radius
(`grep -rn "_collect_history" copycat`)。
**契約**:「首頁備妥但 0 rows」仍是空(不重試);只有 timed_out 才重試。

```
處理 R8:讀 …rounds.md §R8,跑 /bug「_collect_history timed_out 旗標六處 caller 無視 → 逐 caller 接三態/重試」,分支 bug/history-timeout-propagation。13:45 後才可重啟 8721。
```

---

## §R9 B14 + B15(/mod,S×2;13:45 後)

- **B14 TXO 回補重試進度可觀測**(後端+前端):next-time 08-19 txo-snapshot 節(code review C4,心跳出貨後只剩 UX 面)。
  把重試進度(attempt / backfill_secs)寫進 `_handover` 讓內容真的變 → 前端 `ConnectionBadge` 的 `backfilling`
  文案帶「第 n 次」。
- **B15 群組檢視 `?tape=0`**(後端+前端):next-time 08-17 group-grid R4 節(review B7)。`/api/stock/state/{code}`
  恆帶整份 ticks,群組檢視點卡片無主圖讀者;加 `?tape=0` 省略 ticks,`useGroupSnapshots` / 群組 onSelect
  路徑帶參數(**W-4:onSelect 仍須換訂閱**,只省 payload)。M0 會量到盤中真實大小供 PR 描述引用。

```
處理 R9:讀 …rounds.md §R9,跑 /mod「TXO 回補重試進度可觀測 + 群組檢視 ?tape=0」,分支 mod/txo-backfill-progress-tape0。13:45 後才可重啟 8721。
```

---

## §R10 C 重構批(/refactor,零行為;13:45 後,鏈尾)

next-time 散落的 🔵 條目一次收,**每條獨立 commit、行為零差異、既有測試一律綠**:

- C1 `localYmd()` 兩份(useStockOverlay / useIndexOverlay)抽 `@/lib` 單一來源(08-14 index-overlay 節)。
- C2 「六腿」字樣批改腿數無關(`grep -rn 六腿 copycat frontend/src`;08-17 corr R5 節)。
- C3 `lib/index-chart-svg.ts` 死碼 cluster(`buildIndexGeometry` / `rightEdgeLabels`(**若 R1 已用它則不刪**)/
  `IndexPt` / `RightEdgeLabel` / `RightEdgeInput`)連 `index-chart-svg.test.ts` 三個 describe 清理;
  `MarketPane.size.test` 改 import `INTRADAY_CHROME_Y`(08-17 index-core R4 節)。
- C4 主副圖比例三份(FuturesChart `MAIN_RATIO_*` / StockChart 行內 / chart-frame `CARD_MAIN_RATIO`)收 chart-frame
  單一 export;`EMPTY_HLINES` 兩份搬 lib(08-18 futures-intraday-core 節)。
- C5 三梯武裝列 JSX 三份(LadderView + FuturesLadder)合一(08-17 flash-arm-lock 節)。
- C6 測試 deadline-poll helper 6 份手抄收斂(08-11 tc4-lock-p2s 節)。
- C7 四處註解舊根因改口(`futures_engine.py:117`、`corr_engine.py:6/149`、`corr_config.py:7`、`app.py:775`;
  真因 = reap 殺 key,非「跨 session 只推一邊」;08-18 refcount 節)。
- C8 四處裸 `localStorage.getItem` 包 try/catch(RightRail `initialTab()` + MarketPane;照 `initialSubTab()` 慣例;08-14 subtabs 節)。

**鏈尾責任**:merge 後重啟 8721、`npm run build`;若 M0 的 docs diff 留在 scratchpad,一併提交。

```
處理 R10:讀 …rounds.md §R10,跑 /refactor「housekeeping 八條(localYmd / 六腿字樣 / 死碼 / 比例常數 / 武裝列 / poll helper / 註解改口 / localStorage try-catch)」,分支 refactor/housekeeping-batch-2026-08-21。鏈尾:重啟 8721 + build。
```

---

## 未排入(需要 user)

- **F1** 當沖先賣實錄 → 空單平倉鍵解鎖(capital-kind-garbled-and-daytrade-short memory)。
- **F2** 現股市價安全首單 / 真市價 "M"。
- **F3** 過目:B1/B3(build 後)、08-20 八張截圖、M0 新截圖、Discord 合併訊息。
- **F4** 拍板:R3b 盤前冷啟動、期貨 CDP 口徑(B6 前置)、鎖定態禁送窗、當沖稅率、POC D6。
- **B5** 成交點精確版(L)、**B6** 期貨分時 CDP/MA(等 F4)、**B13** TXO delta 化(M–L)—— 下一批。
