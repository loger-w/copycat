# 現況盤點:夜盤時段支援(mod/night-session)

日期:2026-07-20(夜盤中實測取證)。Baseline:`pytest -q` 644 passed 全綠(master 384499d)。

## 問題(2026-07-20 夜盤實測,server + probe 雙重驗證)

夜盤(台北 15:00–次日 05:00)開 server:連線 / 訂閱 / 交接全通、status=live,但畫面凍結在日盤終值。兩個根因,都是「日盤假設」:

1. **回補窗寫死日盤 UTC 窗**:`tc4.py` `fetch_backfill` 與 `build_rt_request` 都用 `{ymd}00`–`{ymd}06`(= 台北 08:00–14:00)。夜盤已成交段(UTC 07:00 起)不在窗內。
2. **cum stale-drop 基準錯位**:`aggregate.py` `_ingest` 以 `cum_volume <= last` 丟 stale;交接後 `_last_cum` = 日盤回補 Σqty,而**夜盤 REALTIME 的 `TradeVolume` 從 15:00 重新起算**(實測:TXF 夜盤歷史窗 Σqty 16,479 = REALTIME cum 16,479;C.44000 日盤 Σqty 7,436 vs 夜盤 cum ~1,3xx)→ 夜盤推播幾乎全被誤丟(實測交接 buffer 33,695 筆只淨入 21 筆;穩態 20 秒 0 新 tick)。

**關鍵事實:cum 基準與回補窗是同一件事** — 回補窗 = REALTIME 當前時段窗,則 `ingest_backfill` 重建 Σqty 自然等於該時段累積,stale-drop 不需要改。`aggregate.py` 可不動。

### 時區幸運:兩個時段各自完整落在單一 UTC 日

- 日盤 台北 08:45–13:45 = UTC 00:45–05:45 → 窗 `{ymd}00`–`{ymd}06`(現行)
- 夜盤 台北 15:00–次日 05:00 = UTC 07:00–21:00(**同一 UTC 日**)→ 窗 `{ymd}07`–`{ymd}21`
- 判定規則(UTC hour h):h < 7 → 日盤窗;h ≥ 7 → 夜盤窗。皆用 `gmtime` 當日 ymd。
  - 邊界:台北 14:00–15:00(h=6)→ 日盤窗(顯示剛收的日盤);台北 05:00–08:00(h=21–23)→ 夜盤窗(顯示剛收的夜盤);台北 08:00–08:45(h=0)→ 日盤窗(空,等開盤)。

## 附帶問題:回補等待時間

`_fetch_symbol_ticks` 對「無資料 symbol」跑 6 次 GETHISDATA + 5 次 `poll_wait*0.3` sleep(區分「TC4 未備妥」vs「真沒資料」的唯一手段)。日盤 356 檔實測 ~3 分鐘,慢段集中在無成交 symbol(log:後 156 檔耗 ~2 分鐘,前 180 檔含資料收割只 ~40 秒)。夜盤無成交合約比例更高(probe:10 檔抽樣 2 檔 0 成交,深價外更多)→ 不處理會比日盤更慢,直接打臉本次目標。user 明確抱怨 2–3 分鐘等待。

## 相關 caller map(grep 全庫 *.py)

| 標的 | 使用處 | 本次影響 |
|---|---|---|
| `build_rt_request(request, session, symbol, ymd)` | `tc4.py:238`(`_rt_request`)、`tests/live/test_tc4.py:53` | 改:窗參數化。測試 assertion 該紅(🔴) |
| `fetch_backfill` 窗(`tc4.py:261-262`) | engine `_run_handover` 經 QuoteSource Protocol | 改:窗跟時段走 |
| `_today_ymd` | `tc4.py` 內部 ×2 | 併入時段窗函數 |
| `TXO_BACKFILL_DATE` → `backfill_date` | `server/app.py:65` → `TC4QuoteSource.__init__` | **語意保留**:指定日期 = 該日日盤窗(休市日回補用) |
| `aggregate.ingest_backfill` / `_ingest` stale-drop | `handover.run_handover`、engine | **不動**(見上) |
| `engine._run_handover` / `_maybe_self_heal` | `server/app.py` lifespan、routes | 加:時段切換偵測 → 自動重跑交接(復用 self-heal 路徑) |
| spikes/*、`data/backfill_tc4.py`、`replay/`、`backtest/` | 離線一次性 / 歷史研究工具,窗語意 = 日盤(股票) | **out of scope 不動** |

## 為什麼要動 engine(時段切換偵測)

server 常駐跨過 14:00→15:00 或 05:00→08:45 邊界時,`_last_cum` 還是上一時段基準,新時段 cum 從 0 起算 → 同一凍結 bug 鏡像重現(明早日盤開盤一樣會凍)。偵測手段:交接時記住「時段 key」(ymd+day/night),`_consume` 的 timeout 分支(兩盤之間必無 tick,天然會走到)比對當前時段 key,變了 → 走既有 self-heal 路徑(reset + 重跑交接,新窗自然生效)。

## 既有測試地形

- `tests/live/test_tc4.py`:`build_rt_request` 窗 assertion(該紅)、fetch_backfill 分頁 / lock timeout(用 `poll_wait_secs=0.0`,不受等待策略影響)
- `tests/server/test_engine.py`:交接 / 自癒 / 溢出重跑,用 fake QuoteSource(窗邏輯在 tc4 層,不受影響;新增時段切換測試落這)
- REALTIME 推播解析 / spot 分流 / stale-drop:`test_aggregate.py`、`test_handover.py`(不該紅)

## 現有實作意圖(不可破壞)

- 窗必帶:TC4 SUBQUOTE REALTIME 不帶 StartTime/EndTime 會 fail(docs/research/2026-07-18-txo-chain-probe.md)
- 先全鏈 SubHistory 再逐檔收割(10 分鐘 → 2 分鐘的既有優化,保留)
- `TXO_BACKFILL_DATE` 休市日回補模式(CLAUDE.md §1 啟動表)
- stale-drop 防重複推播 / 重連重放 / 回補重疊(design.md §2.3 混合去重制)
- spot(TC.F.*)分流不走 stale-drop、獨立於序列(DR-9/DR-13)
