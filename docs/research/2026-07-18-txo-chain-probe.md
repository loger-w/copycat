# TXO 期權鏈探測報告(SC-1 spike)

日期:2026-07-18(週六,休市日執行)
腳本:`spikes/txo_chain_probe.py`(`.venv\Scripts\python spikes\txo_chain_probe.py --port 50774 --date 2026-07-17`)
結果:**三斷言全過,exit 0**(`contracts_count_ge_30` / `ticks_fetched_gt_0` / `subscribe_all_ok`)
產物:`spikes/out/txo_instruments.json`(合約清單 dump)、`spikes/out/txo_ticks_20260717.jsonl`(6,000 筆真實 tick 錄檔,SC-5 golden 素材)

## 1. 合約清單(SC-1a ✓)

- `QUERYALLINSTRUMENT` 的 `Type` 參數:**`"Opt"` 有效**(wrapper 註解寫 `Options`,實測 `Opt` 才回 OK)。
- TWF 期權 symbol 共 2,826 檔,格式 `TC.O.TWF.<prod>.<expiry>.<C|P>.<strike>`。
- 序列(2026-07-18 時點):`TXO.202608/09/10/12、202703`(月選)+ `TX4.202607`(280 檔)/`TX5.202607`(274 檔)(週三別週選)+ `TXY.202607`(274)/`TXZ.202607`(240)(另一組週別,待確認週五別對應)。
- 07 月選(TXO.202607)已到期消失 → **序列清單必須動態查詢,不可 hardcode**(印證 design edge 4)。
- 最近序列 = `TX4.202607`(2026-07-22 到期,REALTIME `EndDate` 欄位可證),280 檔 ≥ 30 ✓。

## 2. 歷史 TICKS 回補(SC-1c/d ✓)

- 窗口格式同 backfill_tc4 慣例:`YYYYMMDD00`~`YYYYMMDD06`(UTC 小時)。
- ATM ± 15 檔(60 symbols)拉 2026-07-17 全日:**6,000 筆**;分頁 QryIndex 迴圈正常(最活絡檔 944 筆跨多頁)。
- 欄位覆蓋率:`TradingPrice`/`TradeQuantity`/`Date`/`FilledTime`/`PreciseTime` 100%、`Bid` 100%、`Ask` 99.68%、`OI` 0%(空字串)。
- **關鍵限制:歷史 TICKS 的 `TradeVolume` 全為 0(無累積量)**;排序/去重靠 `PreciseTime`(微秒級,如 `35114861000` = 03:51:14.861)+ `QryIndex`(該檔序號)。
- **內外盤判定可行**:每筆 tick 帶成交當下 Bid/Ask 一檔。

## 3. 即時訂閱(SC-1b,休市日降級驗證 ✓)

- **現版 TC4 的 `SUBQUOTE`(SubDataType=REALTIME)必須帶 `StartTime`/`EndTime`**,否則 `{"Success":"Fail","ErrMsg":"invalid Date Time Format"}`。官方 wrapper `SubQuote()` 沒帶時間欄位 → 與現版 API drift(`UNSUBQUOTE` 同)。帶當日 UTC 窗(`YYYYMMDD00`~`YYYYMMDD06`)即 `Success: OK`。
- 61 檔(60 選擇權 + TXF HOT)訂閱全 OK;休市日訂閱即回推每檔一則 REALTIME snapshot。
- REALTIME Quote 欄位(比設計假設富裕):
  - 去重/累積核心:`TradingPrice`、`TradeQuantity`(單筆口數)、**`TradeVolume`(當日累積量,有值!)**、`FilledTime`/`PreciseTime`
  - 內外盤:`Bid`/`Ask`(最佳一檔)+ **五檔深度**(`Bid1..Bid4` 有值、`BidVolume1..5`;注意 `Bid`=最佳、`Bid1`=第二檔的位移命名)
  - 合約中繼:`StrikePrice`、`CallPut`、`EndDate`(到期日)、`Underlying: TC.F.TWF.TXF`、`Security: TX4`
  - 籌碼:`OpenInterest`(19)、`TotalBidCount/Volume`、`TotalAskCount/Volume`
  - Greeks 欄位存在但空(另有 `SubGreeks` 通道,MVP 不用)

## 4. 對 design 的回饋(已反映至 design.md v3)

1. **交接去重主鍵混合制**:live 段用 `TradeVolume`(累積量)單調遞增;回補段無累積量 → 以回補段 `TradeQuantity` 逐檔累加**重建** cum,交接 flush 以「live `TradeVolume` > 重建值」放行。重建值與 TC4 內部計數的一致性 2026-07-20 盤中驗證(Known Risk)。
2. `parse_realtime` 對映表可直接照本報告 §3 欄位寫;`parse_history_tick` 照 §2。
3. 訂閱層必須自帶 `SubQuoteRT`(帶時間窗),不能用 wrapper 原 `SubQuote`。
4. TC4 週選產品代碼(TX4/TX5/TXY/TXZ)與「週五別」對應關係待盤中對照 UI 確認;序列選單顯示名先用 `Security + expiry + EndDate` 組合。

## 5. 遺留驗證(2026-07-20 週一盤中)

- live REALTIME push 頻率/語意(每筆成交推播?或 throttle?)
- `TradeVolume`(live)與回補段 `TradeQuantity` 累加的一致性
- heartbeat / 斷線重連行為
