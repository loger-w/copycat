# 現況(mod/signals-today-offload)

> 來源:2026-08-19 瀏覽器崩潰掃描 handoff R5(P2)。分流判定:已成形(handoff 指名
> 行號 + 修法 asyncio.to_thread)→ S 級 0 輪 review。

## 問題

`copycat/server/app.py:1299` `stock_signals_today`(async route)直接呼叫
`hub.today_signals()` — 同步讀整份當日 jsonl(`signal_hub.py:942` `path.read_text`,
兩日不同時讀兩份)。訊號檔大時(08-17 曾 192 則/日,長期只會更多)整個 event loop
被卡住,8 條 WS 的推播 / 心跳一起頓。前端每次 WS 重連自癒都打這條(baseline),
恰好在「連線抖動」時雪上加霜。

對照:hub 自身的 jsonl **寫入**早已走 `asyncio.to_thread`(`signal_hub.py:885`
flush worker),只有讀取路徑漏了。

## Caller map(grep today_signals|read_signals,含動態用法)

| 符號 | caller | 影響 |
|---|---|---|
| `hub.today_signals()` | `app.py:1299`(唯一 production caller)| 本輪唯一改點 |
| 〃 | `tests/server/test_signal_hub.py:653/706/738/2428/2454`(同步直呼)| hub API 不動 → 零影響 |
| `hub.read_signals()` | `today_signals` 內部 + `test_signal_hub.py:737/2447-2453`(**動態替換** `h.hub.read_signals = _counted`)| 不動 read_signals;to_thread 呼叫 bound method,實例屬性替換照樣生效 |
| route 消費端 | `frontend useSignalFeed.ts:24`(WS 重連自癒 baseline)、`_wait_signal` 測試 helper | payload 形狀不變 → 零影響 |

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| jsonl 讀取執行緒 | event loop 執行緒(阻塞) | `await asyncio.to_thread(...)`(worker thread) |
| hub API / 回傳形狀 | 同步 `today_signals() -> list[dict]` / `{"signals":[...]}` | **完全不動** |
| hub 缺席 503 | `_signals(request)` 同步 raise NOT_READY | 不動(在 to_thread 之前) |
| Backward compat | — | 對外 API / payload 零變更;無 migration |

## 併發語意

`today_signals` 全唯讀(檔案 + `_trade_date_fn`/`_now_fn`),無共享可變狀態;與 flush
worker 的 append 併發 = 既有風險(半寫入尾行),`read_signals` 的壞行跳過 +
`errors="replace"` 本來就是為此設計(signal_hub.py:929-936 docstring)→ to_thread 安全。
