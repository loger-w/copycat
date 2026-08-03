# Phase 7 真實環境驗證(2026-07-20,達錢 4 實連 port 50774)

Probe(read-only,scratchpad/probe_tc4common.py)輸出原文:

```
INFO copycat.live.tc4: TC4 connected, session=df115849
[regression] list_series: 9 series, head=['TX4.202607', 'TX5.202607', 'TXY.202607', 'TXZ.202607']
[happy] _fetch_symbol_ticks TC.F.TWF.TXF.HOT 20260720: 62863 ticks
        first seq=1 last seq=62863 last price=42641000
[edge] 遠古空窗 ticks: 0(預期 0)
[happy] _fetch_1k 2330 2026-07-20: 270 bars
        first m=0 last m=269 last close=2320.0
probe done, disconnected
```

對照(行為不變):

- `_fetch_symbol_ticks`(iter_qry_pages 改接後)實連分頁 62,863 ticks,seq 1..62863 連續無缺 —
  多頁游標推進正確;空窗 edge 正常終止回 []。
- `_fetch_1k`(backfill 路徑改接後)2330 當日 270 根 = 09:00–13:30 全根數,首末 index 0/269
  與台北分鐘索引一致。
- `list_series` 9 序列(regression 抽樣,未改動路徑)正常。
- `close()` 後 process 正常退出(§0a KeepAlive 生命週期)。

未能真實驗證:`tc4_trade._restore`(需 TradeAPI 綁券商帳號登入,期貨商 API 權限尚未申請)—
由 tests/live/test_tc4_trade.py 停滯/空首頁/空 QryIndex 三測覆蓋。

自動化 gate(harness.json verify,exit code 逐一檢查無管線):pytest exit=0(607 passed)、
ruff exit=0、pyright exit=0。`copycat validate` 紅為 pre-existing(master 同紅 12/42,
逐字相同)— 已記 docs/next-time.md,與本 refactor 無關。
