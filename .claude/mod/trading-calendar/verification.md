# verification — mod/trading-calendar(2026-08-16 週日)

## 1. 自動化 gate(auto-verify;波尾主 session 親跑 + fix 波後 implementer 復跑)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q`(波尾,fix 前)| 2620 passed / 1 failed(`test_ws_disconnect::test_no_write_to_dead_transport` recv timeout;單跑 3 次 2 過 1 失;與本輪無關的已知 timing flake,memory「ws_disconnect flake 待排查」)| 1(flake) |
| `.venv\Scripts\python -m pytest -q`(fix 波後,implementer)| **2627 passed** | 0 |
| `ruff check copycat tests` | All checks passed | 0 |
| `pyright` | 0 errors / 0 warnings | 0 |
| `copycat replay four_tigers` / `five_tigers` | 完成(11048 events)| 0 |
| `copycat validate` | **42/42 PASS** | 0 |
| frontend `npm test -- --run` | **113 files / 1872 tests passed** | 0 |
| frontend `npx tsc -b` / `npx eslint src` | clean | 0 |
| frontend `npx react-doctor@latest --scope changed --no-telemetry` | 10 files scanned, No issues(0 新增)| 0 |

## 2. 真實環境(SC-11;窗口 = 週日即窗內)

起法:`TXO_SERVER_PORT=8721`、**無** `TXO_BACKFILL_DATE`,`python -m copycat.server`(真 TC4 50774 在線、真 FinMind、
群益登入)+ `npm run dev`;驗完即收(prod 原本未在跑)。log:`logs/server-20260816-2307.log`。

| 檢查 | 結果 |
|---|---|
| `GET /api/health` | `{"git_sha":"5147f864","git_dirty":true(.claude 未追蹤),"started_at":"2026-08-16T23:07:31"}` |
| `GET /api/calendar` | `today=2026-08-16, trade_date=2026-08-14, calendar_trade_date=2026-08-14, backfill_env=null, holidays=18 筆, years_loaded=[2026], calendar_loaded=true` |
| `GET /api/ready` | `ready:true, error:null` |
| `GET /api/index/state` | `trade_date=2026-08-14`,`twse.minutes=270`(週五 1K 回補非空),`stale=False`;`otc.minutes=1`(MIS 只有最後快照 — 櫃買無歷史來源,重啟即歸零,**既有限制非本輪**)|
| `GET /api/market/breadth` | `trade_date=2026-08-14, as_of=15:00:00, stale=False, series=106`(log:`breadth restore 2026-08-14:106 分鐘`),counts 非 null |
| `GET /api/market/breadth/rows` | `trade_date=2026-08-14, rows=1943, streaks_ready=True`(log:`streak restore 2026-08-14:43 檔 / 10 交易日`)|
| `GET /api/stock/state/2330` | `ticks=6284`(週五全日)|
| `GET /api/stock/group-state?codes=3481` | `minutes=267` |
| `GET /api/stock/overlay/2330` | `date=2026-08-13`(基準 = 08-14 前最後一根,SC-13)|
| server log WARNING | 無任何交易日曆 WARNING(無過期 / 無臨時休市 / 無缺年);其餘 WARNING 皆既有(discord voice / capital 預約單)|
| 假日 poll 下降(W5)| 週日 23:07 起 server,breadth 只跑首圈(log 僅一次 restore + 無週期 fetch)|

截圖(`evidence/`,user 過目):
- `SC-11-overview-sunday.jpg`:台股綜合 — 加權分時整日曲線 + 均價/CDP、家數帶「2026-08-14 15:00:00」、騰落線、
  漲跌停列表左上 **「08-14 收盤」膠囊**(SC-10a);櫃買分時空(MIS 單點,既有限制)。
- `SC-11-stock-single-3481-sunday.jpg`:個股單檔 3481 週五分時 + CDP 線 + 「疊線基準 2026-08-13」。
- `SC-11-stock-group-sunday.jpg`:群組「玻璃」三張卡片週五分時。
- 左欄「今日訊號」列的是週五訊號(review S6 → next-time)。

## 3. 白名單對照(§7 回頭核 goal)

- W1 交易日盤中不變:兩 lens review 逐字核對 + engine 預設值 lock 測(stock weekday / index True / breadth 純時間窗)+ 交易日盤前失敗仍等窗開的 W1 lock 測。
- W2 env 最高優先:test_calendar_wiring env 情境(stock/index/hub/overlay/`/api/calendar.trade_date`)綠。
- W3 K 線不動:兩 route 仍 `_date.today()`(docstring 明列例外)。
- W4 streak 演算法不動:diff 零觸及演算法;R5 回歸測鎖數值。
- W5 FinMind 配額不增:非交易日只首圈(真實 log 印證)+ 交易日語意不變測。
- W6 39 個 create_app 呼叫點零改動:全套 pytest 綠。W7 health 不變:test_health_payload_unchanged。
- W8 前端週末不變:trading-hours 既有測全綠。W9 engine 直接建構不變:三個 default lock 測。
- migration:無(無資料格式變更);可逆 = revert 即回牆鐘。

## 4. 未在本輪(見 change-spec §3 / KR + docs/next-time.md 08-16 節)
TXO 面仍需 env;交易日盤前冷啟動空圖(KR-4,待 user 決定 R3b);臨時休市只有 14:00 後重啟才 WARNING(KR-3);
SignalRail「今日訊號」標題;錯標日可見訊號;試撮(緩)badge;櫃買假日分時無歷史來源(既有)。
