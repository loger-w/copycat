# repro:個股搜尋提示列/名稱慢現 + 期貨面板間歇不出現

日期:2026-08-04(/auto → /bug)。User 通報三症狀,皆真實使用中遇到,無保存 log。

## 症狀與根因對映

| # | 症狀 | 根因 | 修復層 |
|---|------|------|--------|
| 1 | 個股搜尋提示列一開始不顯示,用一陣子後才出現 | 前端 `useStockNames` 在 server 啟動窗內失敗後落入 error 終態 | frontend |
| 2 | 個股名稱很慢才出現 | 同上(側欄名稱同一個 query) | frontend |
| 3 | 期貨與期貨價差有時不出現 | `futures_engine._subscribe_all` 訂閱失敗後零重試路徑 | backend |

## 症狀 1/2 蒐證(2026-08-04)

**機制鏈(每一環都有 code 佐證):**

1. FastAPI lifespan 在 `yield`(app.py:418)前依序啟動 TXO runtime → stock → index →
   capital → futures → corr。uvicorn 在 lifespan startup 完成後才 bind socket →
   **啟動期間所有 HTTP 連線被拒**。
2. TXO `EngineRuntime.start()`(engine.py:133)`await activate()` → `_run_handover` →
   `await asyncio.to_thread(fetch_backfill)`(engine.py:190)= **同步等完全鏈回補**。
   歷史實測:全鏈收割 ~2 分鐘(CLAUDE.md §8);trial6 回補 48k ticks。
   stock `set_watchlist` 再逐檔 30 檔 REQ。→ 啟動阻塞窗常態達數十秒~分鐘級。
3. 前端 `useStockNames`(useStockNames.ts:28)`retry: 1` → 兩次嘗試在 ~1-2 秒內用完
   (連線被拒是即時失敗)→ query 進 **error 終態**,`data` 為 undefined →
   `WatchlistSidebar.tsx:76` fallback `[]` → `searchStocks` 恆回空 → 提示列不出現、
   側欄名稱缺。
4. 復原路徑 = TanStack Query `refetchOnWindowFocus`(error 態必 stale)→
   「使用一陣子後」(切窗/回焦)才重抓成功 → 與通報「後面使用了一陣子後才有提示列」
   逐字吻合。

**判定:** root cause = 「啟動窗內的暫時失敗被前端當成終態」。名稱表是版控靜態檔
(58 KB),對它 retry 到成功是正確語意(`staleTime: Infinity` 成功後零重抓,成本只在
失敗期)。

**[auto-default: 修前端 retry 策略,不改後端 lifespan 提前 yield | reason: 提前 yield
是架構級改動(engines 的 app.state 時序假設全要重審),retry 修在失敗處理層即根治
使用者可見症狀;lifespan 阻塞本身已是文件化特性]**

## 症狀 3 蒐證

- 既有偵查:`docs/next-time.md` 2026-07-30 條 + `.claude/bug/futures-engine-silent/repro.md`。
  真環境 7 次重現嘗試全健康(涵蓋兩個 TC4 實例、夜盤冷啟、hard kill、快速重啟、跨盤別);
  **本輪 2026-08-04 00:06 再查一次:三品全有值(第 8 次未重現)**。
- **機制缺陷已證實**(上輪 mechanism_probe.py,真 engine + 假 source):
  - `futures_engine.py:131-135`:`except ConnectionError` 只 `logger.warning`,失敗品**無任何後續重試**。
  - `tc4.py:408`:`_resub` 只在成功時 `_subscribed.add` → 失敗品不在 `_subscribed`。
  - `tc4.py:531`:`_check_stale` 重連只重掛 `list(self._subscribed)` → 接不了手;
    且部分失敗時(其他品有推播)`_last_msg` 持續更新,stale 根本不觸發。
  - `_leaf_fallback` 需先由**推播**解析 ym 才啟動 → 全品訂閱失敗時永不啟動。
  - 探針結果:三品訂閱失敗 → `seq=0`、`p=null`、每品 subscribe 只被呼叫一次 —— 與通報症狀逐項相同。
- 佐證:失敗夜 log 的 TC4 connect 間隔 = 3 × REQ_TIMEOUT(REQ 通道確實在逾時)。
- **本輪拍板:修「訂閱失敗零重試」這個已證實的 code 缺陷**。上輪依鐵則 A 暫緩是因
  「真環境觸發條件未定位」;但 (a) 缺陷本身與症狀的因果已由探針證實,(b) user 持續
  真實遇到,(c) 紅測試(假 source 先失敗後成功)= 該機制的穩定重現。真環境觸發源
  (為何 REQ 逾時)另留 next-time 判準:下次發生 grep `futures <p> subscribe ... failed`。

## 修法(實際採用)

1. **frontend**:`useStockNames` **保留 `retry: 1`**(error 態要能浮現 — 404/舊 build
   錯誤碼契約與既有 2 條 isError 測試依賴它),加
   `refetchInterval: (query) => (query.state.data === undefined ? 3000 : false)`:
   無資料(含 error 態)每 3s 自動重抓,一旦成功即永久停止(staleTime Infinity 穩態零成本)。
   〔推翻本檔上方原草案「retry: true 無限重試」— 無限重試會讓 error 終態永不浮現〕
   已從 query-core 5.101.2 原始碼確認 interval 觸發的 fetch 不受 error 態阻擋。
2. **backend**:`FuturesEngine.__init__` 加 `resub_interval_secs=10.0`;`_subscribe_all`
   失敗品進 `_pending_subs`(warning 字串 `futures subscribe %s failed` 原封不動 —
   next-time.md 的一次定案 grep 判準保留);`start()` 有 pending 才起 `_resub_loop`
   背景 task 重試至成功;`close()` 在 source close 前 cancel/await 收掉。成功品路徑零改變。

## 實驗記錄(Phase 2-4)

- **backend 紅→綠**:紅測試 4 條(`TestPendingResubscribe`)— 現行 code 每品 subscribe
  只呼叫一次 → 紅;修復後重試至成功、推播照常驅動狀態、全成功時零 retry task、close 收掉
  loop → 綠。commits `99ef888`(紅)→ `30c05d1`(修)。pytest 1497 passed / ruff / pyright 全綠。
- **frontend 紅→綠**:紅測試 1 條 — fetch 前 2 次 500 後成功;紅時進 error 態後 data 恆
  undefined(10s waitFor 逾時);修復後 4.07s 內自動拿到 names,無任何 focus/remount。
  commits `0047531`(紅)→ `2d14476`(修)。vitest 914 passed / tsc / eslint 全綠。
- 2026-08-04 00:06 順手檢查跑著的 server(23:56 起,夜盤):TXF/MXF/TMF 三品全有值
  (第 8 次觀測未重現症狀 3;修復後下次真發生時 10s 內自癒並留
  `futures %s subscribe retry ok` log)。

## 反向驗證(Phase 8)

- revert 30c05d1(backend 修復)→ `TestPendingResubscribe` **4 條全紅**(25 綠)→ abort 還原。
- revert 2d14476(frontend 修復)→ 自動復原測試 **紅**(4 綠)→ abort 還原。
- 兩邊紅測試都確實抓得住 bug;全 gate 與真實環境證據見同目錄 `verification.md`。

[amendment 2026-08-12: 30c05d1 commit message「補上唯一缺的復原路徑」措辭不成立
(回溯審 P1-3)— pending-resub 只接了「首輪訂閱失敗」;原症狀的第二條發生路徑
(`_check_stale` 重連時 SUBQUOTE 失敗 / 迴圈中途拋錯尾段蒸發)當時零復原零覆蓋,
且迴圈本身只接 ConnectionError、close 不等 in-flight worker(P1-1/P1-2)。
三洞已由 fix/futures-resub-recovery 補齊,見 `.claude/bug/futures-resub-recovery/`。]
