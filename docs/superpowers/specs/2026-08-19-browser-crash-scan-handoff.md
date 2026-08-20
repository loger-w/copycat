# Handoff:2026-08-19 瀏覽器崩潰掃描 → 後續處理

> 給新 session 的交接。來源:Opus workflow 六維度掃描(35 agents)+ 對抗式驗證;
> 完整結果與量測見 `docs/research/2026-08-19-browser-crash-scan.md`;
> workflow 原始 JSON 在該 session 的 `tasks/wuumatu3a.output`(session 專屬暫存,可能已清)。

## 現況一句話(2026-08-19 19:20 更新)

**根因已確認(19:07 第二次崩潰 + 19:09 重載即重現 + clearMeasures 實證)**:React 19.2.7 dev build 的
Component Performance Track 對每個「props identity 變了」的 re-render 打一筆 `performance.measure`(~1.8 KB,
含 props diff detail),Chrome 的 User Timing buffer 無上限、不在 V8 heap → 632 筆/秒 ≈ 1.1 MB/s 線性累積,
4.5 小時 15 GB → renderer Aw Snap。**只影響 `npm run dev`**。證據與量測全在
`docs/research/2026-08-19-browser-crash-scan.md` 的「根因(已確認)」節。

### R0 ✅ 已出貨(2026-08-19 PR #70)`/bug dev 看盤數小時後 renderer Aw Snap:React dev Component Performance Track measure 無上限累積`
- 出貨:`frontend/src/lib/dev-perf-guard.ts`(PerformanceObserver 閾值 5,000 清除,單例 / 降級 no-op)+ main.tsx dev-only 安裝;
  真環境 renderer 記憶體走平。**未拍板**:看盤日常是否改跑 production build(仍建議)。
- 紅測試難寫(瀏覽器 buffer 行為);以「dev-only 在 main.tsx 每 10 s `performance.clearMeasures()+clearMarks()`」
  為最小修法,verify = 同 MCP 分頁實測 renderer Private 記憶體 30 分鐘走平(原 session loop 已裝同款 in-page
  緩解並持續量測,結果會寫回報告「觀察紀錄」)。
- 同步拍板:看盤日常是否改跑 production build(`npm run build` + preview / 靜態 serve → 8721)。
- 放大因子(每則 WS 全樹 re-render、無 memo)歸 R2 / R6,不混進 R0。

下面 R1–R6 是掃描抓出的 P2(驗證者當時判「非崩潰根因」;其中 FE-1/FE-3/FE-4 類 memo 缺口現在升格為
**放大因子**,仍走 R6 效能輪)。

## 拍板待問(開工前先問 user 一次)

- D1 TXO 快照推播:改「內容比對後才推」還是「外來 tick 不標 changed」?(建議兩者皆做:route 早退時
  不 `_mark_changed`,snapshots() 加 version 比對已在,再加 payload hash 短路)
- D2 futures 廣播節流:改 1s 週期 flush(與其他引擎一致)還是保留 event-driven 但 coalesce 同商品?
  (五檔盤中要即時,建議 coalesce:每商品保留最新 payload,以 ≥100ms 週期 flush)
- D3 WS 心跳:應用層 ping/pong 訊息型別要不要進 8 條 WS 契約?(涉前後端契約,§4 規則同改兩邊)
  → **已拍板(08-19,user 選「server 定時報平安」)**:應用層 ping 進 8 條 WS 契約;前端靜默 watchdog 以 ping 為準,不靠資料頻率。

## 建議分輪(各自 /mod,三類分離)

### R1(後端,最高價值)`/mod TXO /ws/txo-pnl 每秒推 22.6KB 相同快照 → 外來 tick 不標 changed + 內容不變不推`

> **已出貨 2026-08-19(PR #68)**;artifact `.claude/mod/txo-snapshot-no-redundant-push/`;SC-4 prod 量測 + SC-5 待 prod 重啟。D1 拍板 = 兩者皆做 + Event 換代。
- 位置:`copycat/server/engine.py:295-297`(`_consume` 在 `self._agg.route(tick)` 後無條件 `_mark_changed()`;
  route 對非本鏈 symbol 早退只加 `dropped_foreign_ticks`)、`engine.py:127-137`(`snapshots()` 1s 節流無內容比對)。
- 證據:14:22 實測 `/ws/txo-pnl` 1 msg/s、23.2 KB/s(佔全部 WS 96%),連續 6 則去掉 generated_at 逐字相同;
  `/api/txo/snapshot` totals `dropped_foreign_ticks=3,089,555` vs `ticks=2300`。
- 附帶:`WS-TXO-SHARED-EVENT`(engine.py:131 多 client 共用單一 asyncio.Event,一 client clear 可能讓另一
  client 漏一次版本)可同輪處理。
- 前端消費點 `useTxoSnapshot.ts:29-33`;`<TxoPage />` 在 `App.tsx:242` 無條件掛載(只 hidden)。

### R2(後端)`/mod futures_engine 每則 quote 無節流廣播 + leaf fallback 永不退訂`

> **已出貨 2026-08-19(PR #69)**:per-product coalesce 0.1 s + 自癒閘看盤別;**leaf 備胎不退(user 拍板,理由見 `.claude/mod/futures-broadcast-coalesce-leaf-unsub/change-spec.md` 檔頭 + docs/next-time.md 08-19 節)**;D2 拍板 = coalesce。SC-8 prod 量測待重啟。
- `futures_engine.py:426-435` `_handle_quote` 尾端無條件 `_seq += 1` + broadcast 完整 payload(含五檔),
  全檔 grep `throttle` 零命中;對照 `index_engine.py:498-500`、`stock_engine.py:1297-1300`、`corr_engine.py:187-190` 皆有 1s 閘。
- `futures_engine.py:312-345` `_leaf_fallback` → `subscribe_leaf` 只訂不退;`_leaf_fed.discard`(:406)只是記帳;
  `futures_models.py:44-47` HOT 形與 YYYYMM 形解析成同 product → HOT 自癒回魂後同商品雙流各推一次(整流 +33%)。
  `tc4.py:915-921` 重連照 `_subscribed` 全量重訂,leaf 會被復原,雙訂閱可掛整天。
- 附帶:`app.py:359` 期貨自癒閘只看交易日不看盤別 → 13:45–15:00 / 05:00–08:45 持續 UNSUB/SUB churn(log 那行的來源)。
  `futures_source.py:29,34-38` 有 `FUTURES_MINUTE_DOMAIN`。

### R3(前後端契約)`/mod 8 條 WS 加應用層心跳 / 靜默 watchdog` — **已出貨(08-19,PR #TBD,branch mod/ws-app-heartbeat)**
- 出貨內容:relay 每 10 s `{type:"ping"}`(8 條 WS,不經 queue);前端 `lib/ws-reconnect.ts` 共用 helper(首則 ping 武裝 + sticky per-URL 的 30 s 靜默 watchdog、backoff 三分支 1/2/4/5/5 短命 cap、onerror 關自身、ping 過濾);後端 accept-then-close 不動(前端 short-lived cap 已解 1 Hz)。
- **注意:後端重啟後請重整瀏覽器分頁**(舊 bundle 的 txo hook 會把 ping 當 snapshot → TXO 頁例外;dev HMR 不受影響)。spec / 證據:`.claude/mod/ws-app-heartbeat/`。
- 原記載:
- 前端 8 hook 重連唯一入口是 `ws.onclose`,無 heartbeat / lastMsg watchdog(grep 零命中);後端 `ws.py:96` relay
  無心跳,只靠 uvicorn 預設 ws_ping 20s。專案 CLAUDE.md §7 明文要求 heartbeat。
- 同輪順手:引擎缺席時 accept-then-close(`app.py:1629/1663/1686/1700`、`capital_api.py:325/347`)+ 前端 onopen
  歸零 backoff → 1 Hz 重連;改成 accept 前判斷 / 用 close code 讓前端不歸零。
- 同輪順手:`useStockStream.ts:460` 等 `ws.onerror = () => ws?.close()` 關的是共用變數當下的 socket
  (`FE-WS-ONERROR-ALIAS`),改成關自身 socket。

### R4(前端)`/mod 訊號提示副作用:AudioContext suspended 節點洩漏 + Notification 洪水` — **已出貨(08-20,branch mod/signal-alert-side-effects)**
- 出貨:playBeep 在 `state !== "running"` 不建節點(suspended → resume in-flight 守門一發;
  closed → 回收單例下一則重建);Notification tag 固定 `copycat-signal` + 5 s leading-edge 節流
  (permission 擋掉不消耗窗口)。artifact `.claude/mod/signal-alert-side-effects/`。
- 原記載:
- `useSignalAlerts.ts:30-44` `playBeep` 在 AudioContext suspended 時 `osc.stop` 排在凍結的 currentTime → 節點永不結束;
  `useSignalAlerts.ts:97` 背景分頁每則訊號 `new Notification`,tag 用唯一 sig.id 不合併。
- 這一輪與「跑一段時間後掛」的時間相依性最像(節點只增不減),但 14:11 無訊號,故驗證者仍判 P2;
  修法簡單(suspended 時 skip / resume 後才排;Notification tag 固定 + 節流)。

### R5(後端小修)`/mod /api/stock/signals/today 同步讀 jsonl 阻塞 event loop` — **已出貨(08-20,branch mod/signals-today-offload)**
- 出貨:route 層 `await asyncio.to_thread(...)`(hub API 不動;503 判定留 loop 內;
  例外傳播 502 有 lock 測試)。artifact `.claude/mod/signals-today-offload/`。
- 原記載:`app.py:1285` async route 內同步讀整份當日 jsonl → 8 條 WS 一起卡;改 `asyncio.to_thread` 或 aiofiles。

### R6(前端效能清理,可選)`/refactor 閃電梯 / 江波圖 / MarketPane memo 邊界` — **已出貨(08-20,branch refactor/memo-boundaries)**
- 出貨:App railCtx 雙 useMemo + memo(RightRail)(跨流串擾歸零:停個股/綜合 tab 時期貨
  10Hz 不再重繪 rail subtree);江波圖 order/entries/幾何 useMemo + memo(RiverCard)
  (hover 幾何重算歸零、單腿 tick 只重繪該卡);OverlayCard 疊圖幾何 useMemo(重疊開啟時
  擋 futures 串擾)。PriceLadder/LadderView 本層維持原註解決策(邊界在上游);
  GroupGridView 節點縮減記 next-time。artifact `.claude/refactor/memo-boundaries/`。
- 原記載:
- `LadderView` / `PriceLadder` / `RightRail` 無 memo(App.tsx:146-150 註解自承);`RiverCards.tsx:28` /
  `RiverOverlay.tsx:39` / `MarketPane.tsx:136` 幾何未 useMemo;`GroupGridView` 50 卡 ×(分時+271 量柱)≈ 2.5 萬 SVG 節點。
- 純效能,行為不變 → /refactor;先量再改(React Profiler)。

### 其餘 P2 備忘(不排輪)
TRADEDATE-REFETCH-LOOP(useIndexStream.ts:151)、RIVER-DELTA-ALLOC(useRiver.ts:55/63)、CAPITAL-TIMERS-GLOBAL
(useCapital.ts:267 module 級 timer 被 cleanup 互抹)、HEAL-SET-ITERATION(tc4.py:487)、WS-FIVE-WILDCARD-SUBS
(tc4.py:886)、DEV-VITE-GIT-SYNC(sha-plugin.ts:64-76 execSync 阻塞 vite 主行程)、CAP-QUERY-OBSERVER-FANOUT
(useCapital.ts:157)、TXO-ROLLOVER-FULL-HANDOVER(engine.py:318 15:00 全鏈重訂 + 277 檔回補)。

## 崩潰根因取證(平行進行中,不在本 handoff 範圍)

原 session cron `83d47649` 每 30 分鐘讀 MCP 分頁 sampler;掛掉時走 DevTools MCP 蒐證並寫回
`docs/research/2026-08-19-browser-crash-scan.md` 觀察紀錄節。若取證得出 OOM 曲線或特定長任務,再開 /bug。
另一條可自行嘗試的排除法:`npm run build` + `npm run preview` 直連(不經 vite dev / StrictMode)看是否仍掛。
