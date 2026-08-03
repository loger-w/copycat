# Change Spec:夜盤時段支援(mod/night-session)

日期:2026-07-21(凌晨,夜盤中)。現況盤點:`current-state.md`(同目錄)。
User 拍板:**夜盤獨立累積**(15:00 起從零,符合期交所 T+1 定義)— 2026-07-21 AskUserQuestion。

## 1. 成功條件(可驗收)

- **SC-1 夜盤即時**:夜盤時段啟動 server,status=live 後 `totals.ticks` 持續成長(量法:`/api/txo/snapshot` 間隔 ≥20 秒兩次取樣,delta > 0;夜盤 TX4 實測每分鐘全鏈百餘筆成交,20 秒窗口期望 >0,若遇罕見零成交窗口延長至 60 秒),`accumulated_from` 顯示 `15:00:xx`(單位:台北時間字串)。
- **SC-2 啟動時間**:啟動(或切換序列)到 status=live ≤ 90 秒(量法:server log `TC4 connected` 到 `handover done` 時間戳差;現況日盤實測 ~180 秒)。
- **SC-3 跨盤自動切換**:server 常駐跨過時段邊界(台北 05:00 收夜盤 → 08:45 開日盤 → 13:45 收 → 15:00 開夜盤)時自動重跑交接、新時段從零累積,無需重啟(量法:單元測試模擬時段 key 變化觸發重跑;真實環境今日 08:45 開盤觀察 ticks 從零重新成長)。
- **SC-4 日盤不變**:日盤時段窗與現行完全相同(`{ymd}00–06`),日盤行為零差異(量法:既有測試除 §5.5 標記「該紅」者外全綠)。**刻意例外(review R3)**:空回補後 `accumulated_from` 由「殘留上一次起點」改為 `"-"` — 這是行為修正,標 🔴 隨 commit 3 出貨。

## 2. 不能破壞的既有行為白名單

1. `TXO_BACKFILL_DATE=<date>` 休市日回補:指定日期 = 該日**日盤**窗(語意不變)。
2. SUBQUOTE REALTIME 必帶合法 StartTime/EndTime(TC4 硬要求)。
3. 先全鏈 SubHistory 再收割的既有優化(280 檔 10 分 → 2 分)。
4. stale-drop 防重複推播 / 重連重放 / 回補重疊(`aggregate._ingest` 不動)。
5. spot(TC.F.*)分流:不走 stale-drop、獨立於序列、reset 不清(DR-9/DR-13)。
6. 重連自癒(`_check_stale` / `on_reconnect` → force heal)與交接溢出重跑協定。
7. queue 滿載 self-heal(DR-10)。
8. 交接期 buffer 隔離(DR-11)、`ConnectionError` 收斂與 route 層 502 合約。
9. 下單端(tc4_trade / trade routes)完全不碰。
10. 前端契約:snapshot JSON shape 不變(不加欄位、不改語意;`accumulated_from` 本來就是字串時刻)。

## 3. Backward compat / migration

- `build_rt_request` signature 變更:內部 API,caller 只有 `tc4._rt_request` 與 `tests/live/test_tc4.py`(Phase 1 全庫 grep 確認)。無對外相容問題,無資料 migration。
- 無持久化狀態(tick 流 in-memory),重啟即套用,無可逆性議題。

## 4. Out of scope

- `spikes/*`、`data/backfill_tc4.py`、`replay/`、`backtest/`(離線工具,日盤語意正確)。
- 前端顯示「夜盤」標籤 / 時段切換 UI(snapshot 已有 accumulated_from 可辨識;要做另開 feat)。
- 夜盤接續日盤的合併視圖(user 已否決)。
- 下單端夜盤行為(TC4 下單通道與時段無關,已可用)。

---

## 5. Diff 級變更(逐檔)

### 5.1 🟢 新檔 `copycat/live/session.py`(零 IO、不碰 ZMQ)

台股期權時段窗純函數。時區事實:日盤 台北 08:45–13:45 = UTC 00:45–05:45;夜盤 台北 15:00–次日 05:00 = UTC **同日** 07:00–21:00(兩時段各自完整落在單一 UTC 日)。

```python
SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night")

def session_key(now: time.struct_time | None = None) -> SessionKey:
    # now=None → time.gmtime();UTC hour < 7 → ("ymd","day");≥ 7 → ("ymd","night")
def session_window(key: SessionKey) -> tuple[str, str]:
    # day → ("{ymd}00", "{ymd}06");night → ("{ymd}06", "{ymd}22")
```

夜盤窗帶裕度 `06–22`(review R4):UTC 06–07 = 台北 14–15、21–22 = 台北 05–06 皆無成交,零誤收;避免依賴 TC4 窗邊界含斥語意(未實測)。窗歸屬由 session_key 決定,兩窗在 h=6 的重疊無歧義。

邊界語意(顯示「最近一場」):台北 14:00–15:00(h=6)→ 當日日盤;台北 05:00–07:59(h=21–23)→ 剛收的夜盤;台北 08:00–08:45(h=0)→ 當日日盤(空窗等開盤)。

### 5.2 🔴 `copycat/live/tc4.py` 窗改時段窗

- `build_rt_request(request, session, symbol, window: tuple[str, str])`:`ymd` 參數改 `window`,`StartTime/EndTime` 直接取 `window`。
- `_rt_request`:`build_rt_request(..., session_window(session_key()))`。
- `fetch_backfill`:`window = (f"{d}00", f"{d}06") if self._backfill_date else session_window(session_key())`(白名單 1:backfill_date 固定日盤窗)。
- `_today_ymd` 移除(被 session_key 取代)。

### 5.3 🔴 `copycat/live/tc4.py` 回補收割改有界輪詢(等待策略改變,時序上可觀測 — review R2 誠實改標)

現況:`_fetch_symbol_ticks` 每個空 symbol 6 次查詢 + 5 × `poll_wait*0.3` sleep → 空 symbol 越多越慢(夜盤更糟)。改:

- `_fetch_symbol_ticks` 退化為單發(1 次首頁查詢 + 分頁),不再自帶 retry。
- `fetch_backfill` 收割改 round 制:每輪掃 pending symbols,有資料收割並移出;輪間 sleep `poll_wait * 0.5`;停止條件 = pending 清空,或連續 3 輪零進展(dry;2 輪實作時發現會切掉「第 3 查才備妥」的 symbol),上限 8 輪。空 symbol 成本 = 至多 8 次快查(GETHISDATA 實測 ~1ms)+ 共享輪間 sleep,不再逐檔空等。
- 每輪 log 一行(round / pending 數 / 累積 ticks;長跑進度 log 慣例)。
- **非嚴格等價聲明**:舊制中排序靠後的 symbol 隱含享有前面收割耗時當備妥時間,新制總等待較短 — 理論上「備妥極慢」的 symbol 舊制收得到、新制收不到。緩解:(a) 全鏈 SubHistory 仍在收割前先發(備妥時間從訂閱起算,非查詢起算);(b) dry-round 規則保證只要還有進展就續輪;(c) Phase 7 等價證據:同一窗以新制收割,tick 總數對照舊制實測基線(107,787 @ 20260720 日盤窗)偏差 = 0 才過。

### 5.4 🟢 `copycat/server/engine.py` 時段切換偵測

- `EngineRuntime.__init__` 增 `session_rollover: bool = True`;`server/app.py` 組裝時傳 `not backfill_date`(review R5:`TXO_BACKFILL_DATE` 固定日模式下停用偵測,休市日常駐不會被真實時鐘觸發多餘全鏈重回補)。
- `_run_handover` 開頭記 `self._session_key = session_key()`(import 自 `copycat.live.session`,零 ZMQ 依賴,engine 潔癖不破)。
- `_maybe_self_heal` 增條件:`session_rollover 啟用 and self._session_key is not None and session_key() != self._session_key` → reset + `_run_handover(series, subscribe=True)`(review R1:**rollover 必須重訂閱** — `subscribe()` 本就逐 symbol UNSUB→SUB 冪等,重訂即以新時段窗重掛 REALTIME;不可沿用 self-heal 的 `subscribe=False`,否則舊窗訂閱跨 UTC 日後 TC4 是否續推未驗證,凍結 bug 可能以新形態重現)。時段邊界必無 tick → `_consume` timeout 分支天然輪詢到。
- (隨 commit 3 🔴)`_run_handover` 中 `backfill` 為空時 `self._accumulated_from = "-"`(現況:空回補殘留上一時段起點,rollover 後顯示錯誤;SC-4 刻意例外,review R3)。

### 5.5 測試

**該紅(🔴,隨 5.2 改 assertion)**:
- `tests/live/test_tc4.py::TestBuildRtRequest::test_subquote_carries_time_window`:改為傳 window tuple、assert 對應 StartTime/EndTime。

**不該紅**:其餘全部(`test_aggregate` / `test_handover` / `test_engine` 既有項 / `test_tc4` 分頁與 lock timeout 項 — 均用 `poll_wait_secs=0.0` 或 fake source,不受窗與輪詢策略影響)。

**新增(🟢/隨各 commit)**:
- `tests/live/test_session.py`:session_key 邊界(UTC h=0 / 6 / 7 / 20 / 21 / 23,含台北對照註解)+ session_window 兩窗字串。
- `tests/live/test_tc4.py`:(a) 夜盤時刻 `fetch_backfill` / `_rt_request` 用夜盤窗(monkeypatch `tc4.session_key`);(b) `TXO_BACKFILL_DATE` 模式固定日盤窗(白名單 1 迴歸);(c) round 制:首輪空、次輪有資料的 symbol 最終被收割;(d) 全程空 symbol 情境 sleep 次數 ≤ 輪數上限(monkeypatch `time.sleep` 計數,review R7-1,不能只算 call 數)。
- `tests/server/test_engine.py`:(a) 時段 key 變化 → 自動 reset + 重跑交接**且重訂閱發生**(monkeypatch `engine.session_key` 序列 + fake source 記 subscribe 呼叫,review R1);(b) key 未變不重跑;(c) 空回補後 `accumulated_from == "-"`;(d) `session_rollover=False` 時 key 變化不觸發(review R5);(e) rollover 當下 source 拋 `ConnectionError` → degraded 且 `_consume` 存活,後續 `request_self_heal` 恢復 live(review R7-2)。

### 5.6 Commit 計畫(三類分離;無 🔵,依依賴序)

1. 🔴 `perf(dq4): 回補收割改有界輪詢,空合約不逐檔空等`(5.3 + 測試 c/d;等待策略行為改,見 5.3 聲明)
2. 🟢 `feat(dq4): live/session 時段窗純函數`(5.1 + test_session;未接線,無行為變化)
3. 🔴 `fix(dq4): 回補/訂閱窗改時段窗,夜盤 tick 不再被日盤基準誤丟`(5.2 + 該紅 assertion + 窗測試 a/b + accumulated_from 清空與 engine 測試 c)
4. 🟢 `feat(dq4): engine 時段切換自動重跑交接`(5.4 其餘 + engine 測試 a/b/d/e)

## 6. Known Risks / 註記

- 夜盤 REALTIME 用夜盤窗訂閱未經 TC4 實測。**Fallback(review R8)**:若 SUBQUOTE 回 invalid Date Time Format,REALTIME 窗退回固定 `{ymd}00–06` 格式(僅歷史 TICKS 窗必須分時段;昨夜已實證日盤格式窗收得到夜盤推播)。
- UNSUBQUOTE 窗與原 SUBQUOTE 窗跨時段錯配(review R6):TC4 退訂認 symbol 還是認 (symbol, 窗) 未知;Phase 7 驗證項 — 跨界後切序列,觀察 `dropped_foreign_ticks` 是否異常增長。
- `session_key` 在交接進行中跨界的競態:key 記錄與窗計算相差毫秒級,錯位最多觸發一次多餘重跑(冪等,自癒路徑本就容忍)。
- rollover 交接失敗時 `_session_key` 已更新,時段條件不再重觸發,恢復依賴 on_reconnect 鏈(測試 e 釘住,review R7-2)。

## 7. Review 記錄

- Round 1(change-spec-reviewer,2026-07-21):P1 ×3(R1 rollover 重訂閱 / R2 輪詢制誠實改標 + 等價證據 / R3 accumulated_from 拆 🔴)、P2 ×5(R4 窗裕度 / R5 backfill_date 停用偵測 / R6 UNSUB 窗 / R7 測試強化 / R8 fallback)— 全數採納,已反映於上文。
- Phase 5 自評(general-purpose reviewer,2026-07-21):P1 ×2(F1 交接並發 double-ingest,repro 實證 → `_handover_running` 序列化;F2 spot 不隨 rollover 重訂閱 → 每次重掛)、P2 ×2(F3 等價證據 = Phase 7 必附;F4 風格/測試釘緊)— 全數修畢(62bd37d、0f53586)。

self_review_head: 0f53586

## 8. Phase 6/7 驗證證據(2026-07-21)

- 自動化:pytest 660 passed(exit 0)/ ruff 0 / pyright 0 / `copycat validate` 42/42 PASS。
- **SC-2 啟動時間**:server log `TC4 connected 10:24:50` → `handover done 10:24:57` = **7 秒**(基線 ~180 秒,目標 ≤90 秒)。
- **SC-4 日盤 regression**:盤中 snapshot 兩採樣 15 秒 +126 ticks、spot 43941→43932 在動、`accumulated_from=08:45:00`、`dropped_foreign_ticks=0`(R6 觀察項無異常)。
- **R2/F3 等價證據**:`backfill_date=2026-07-20`(昨日日盤窗)新 round 制收割 = **107,787 ticks,基線 107,787,diff=0**,耗時 5 秒(舊制 3 分鐘)。
- **夜盤窗實測**:GETHISDATA `2026072006–2026072022` 回完整夜盤 TXF 31,501 rows / Σqty 42,135(昨晚 20:29 時點量 16,479 的整晚延伸,合理);SUBQUOTE/UNSUBQUOTE REALTIME 夜盤格式窗回 `Success=OK`(R8 格式風險排除;實際推播待今晚 15:00 開盤觀察)。
- **SC-1 / SC-3 真實觀察待今晚**:單元測試已釘(rollover 重訂閱/序列化/degraded 恢復);server 常駐跨 13:45 收盤 → 15:00 夜盤開的實地 rollover 今天下午即可觀察。
- 收割 cap 8→16(f4934c4):冷啟動實測第 8 輪仍在進展,dry 早停才是設計收斂條件。
