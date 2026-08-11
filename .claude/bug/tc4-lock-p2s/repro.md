# repro — tc4-lock-p2s(quintet review X-2/X-3,TC4 session/鎖結構兩條 P2)

來源:`.claude/bug/stkfut-order-channel/review-findings.md`(跨 PR 交互 reviewer)。
branch:`fix/tc4-lock-p2s`(基準 e1930f8c = origin/master)。
穩定重現 = 紅測試(受控時序);兩條都是三輪疊加後的資源共用結構問題。

## X-2a:lock timeout(5s)< REQ socket timeout(10s)→ 慢 REQ 使等鎖者棄連線

- trace:`tc4.py:70` `_REQ_TIMEOUT_MS = 10_000`(RCVTIMEO/SNDTIMEO);`:227`
  `lock_timeout_secs: float = 5.0`;`:328-331` 等鎖逾時 → `_dispose(api)` + raise。
  持鎖上界(健康慢路徑 ≈ RCVTIMEO 10s)> 等鎖上界(5s)恆真 → 三個 REQ 生產者
  (群組回補 / basis sweep / Fut2 目錄)任一慢,其餘等鎖者**必**棄整條連線。
  boot 時序上 basis sweep(app.py:489)與 stkfut prewarm(:699)必然重疊。
- 修法(拍板):`lock_timeout_secs` 預設 5.0 → **12.0**(> RCVTIMEO 10s + 餘裕)。
  dispose-on-timeout 的毒鎖防護**保留**(KeepAlive Pong 無 try/finally 死鎖仍要能
  棄連線重建,偵測延遲 5s→12s 是可接受代價)。紅測試:鎖住不等式契約 ——
  `StockQuoteSource()._lock_timeout * 1000 > _REQ_TIMEOUT_MS`(以常數關係斷言,
  不寫死 12);既有 dispose-on-timeout 行為測試保持綠。

## X-2b:CDP 基準取得失敗當日永久 None(不重試)→ 一次連線抖動毒掉十幾檔一整天

- trace:`signal_hub.py:590-595` `_daily_bars` 例外 → `bars=[]` → cdp=None 落
  cache,「不重試(design §4.2)」;basis sweep 間隔僅 0.2s,X-2a 的 dispose
  級聯可在數秒內連續毒掉多檔,該些檔整天無 CDP 訊號,畫面只是「規則沒發」。
- 修法(拍板,收窄 §4.2 而非推翻):**分流兩種失敗** ——
  - `_daily_bars` **例外**(連線/傳輸層,暫時性):有限重試 —— per (code, basis_date)
    重試計數 ≤ 2,經 delay(30s,config 可覆寫則沿 signals_config 慣例,否則常數)
    重新入列;超限才落 None。重試 job 走同一佇列(帶原 basis_date/staged,
    `_stale` 尺自然擋跨日殘留)。
  - `done` 為空(**資料面**:新上市無歷史日 K):維持現狀不重試(重試不會改變答案),
    照落 None + warning。
  - `_basis_failed`(worker 級未預期例外)同例外路徑分流。
- 紅測試:daily_bars 第一次 raise 第二次回真值 → 最終 cdp 有值(現行實作永久 None,
  紅);重試上限(連 raise 3 次 → None 定格,恰 3 次呼叫);空 bars → 不重試
  (恰 1 次呼叫);跨日後殘留重試 job 被 `_stale` 丟棄。

## X-3:WatchlistService 單鎖橫跨整段 ZMQ 訂閱迴圈

- trace:`watchlist_service.py:180` `_commit` 在 `self._lock` 內
  `await engine.set_watchlist(codes)`;engine 逐檔 `to_thread(_acquire)`,單檔
  上界 ≈ 等鎖 + RCVTIMEO;TC4 故障 + `added` 以 `_refs` 實況計算(回滾後全量)
  → 單一指令最壞持鎖 30×~30s,期間所有 `/watch` 寫入與前端 PUT 堆積,
  Discord interaction 15 分鐘 token 過期。autocomplete 有 1s guard,寫入沒有。
- 修法(拍板):**落檔+定序留鎖內,訂閱副作用移鎖外,last-writer-wins**:
  - service:`_commit` 鎖內做 normalize → canonical 比對 → save → `_apply_seq += 1`
    取 `seq`;**鎖外** `await engine.set_watchlist(codes, seq=seq)`(呼叫端仍
    await —— 收斂的是鎖凸出,不是自己那次的等待;回傳 saved 語意不變)。
  - engine:`set_watchlist` 加 keyword-only `seq: int | None = None`;
    `_pool_lock` 內先比 `seq <= self._wl_seq_applied` → 過期整段跳過(不訂不退
    不廣播不通知 hub),否則記下 seq 續走原邏輯。None(既有 caller / boot)=
    不參與定序,照舊。過期跳過即 last-writer-wins:兩個並發 commit 都到 engine
    時,舊 seq 者無論先後到都不會用舊名單蓋掉新名單的訂閱池 / hub membership /
    `watchlist_changed` 廣播。
  - 死鎖面不變:取鎖順序仍是 service._lock(短)→(釋放後)engine._pool_lock。
- 紅測試:(a) 慢 subscribe fake(sleep)下,第一個 commit 的訂閱進行中,第二個
  commit 的**落檔**不被阻塞(量測第二個 apply() 返回檔案內容的時間 / 或以事件序
  斷言 save 先於第一個訂閱完成);(b) 亂序:seq=2 先套、seq=1 後到 → 訂閱池 /
  hub membership / 廣播都是 seq=2 的名單(現行無 seq,舊名單會蓋,紅);
  (c) 既有行為回歸:單一 commit await 返回後 engine 訂閱已完成(語意不變)。

## 實驗記錄

- 三段關鍵碼(tc4.py 鎖區、signal_hub 基準鏈、watchlist_service._commit)由主
  session 逐行讀過拍板;X-2a 的不等式與 X-3 的鎖凸出為結構事實,執行證據 = 紅測試。
