# /mod 個股內外盤改讀達錢旗標 — 前置盤點(2026-09-15)

## 1. Caller map(`side` 的產生點與讀者)

產生點(唯一算式)`copycat/live/stock_models.py`:
- `derive_side(price, bid, ask)`:price ≥ ask → outer;price ≤ bid → inner;否則 neutral。
- `parse_stock_realtime(msg)`:REALTIME → `StockTick(side=derive_side(price, bid0, ask0))`,bid0/ask0 = `_best_limit_price`(五檔第一個 >0 限價檔)。
  **不讀 `FlagOfBuySell`**(08-28 欄位普查有記、無理由)。別名 `futures_models.parse_futures_realtime`(期貨引擎不讀 side)。
  另一 caller `server/corr_engine._handle_quote`(只用 price / book)。
- `parse_hist_tick(code, row)`:歷史 TICKS row → `side=derive_side(price, row.Bid or None, row.Ask or None)`(單一 Bid/Ask 欄;0 歸 None)。
  唯一 caller `live/stock_source.backfill()`(per-code、QryIndex 序 = 時序)。
- `relabel_locked_side(tick, upper, lower)`:只補 neutral 且雙側 None 且價 = 漲停(→ inner)/ 跌停(→ outer)。
  唯一 caller `live/stock_state.apply_backfill`(meta 有值才套;survivors 不套)。

讀者(`tick.side` 三值字面 `outer | inner | neutral`):
- 後端 `stock_state._apply`(MinuteAgg o/i/u)、`_fold_vp`(VP cell [總, 外, 內])、`snapshot()` ticks[].side、`stock_engine._flush_ticks` 打包 item.side。
- 前端 `lib/stock-accum.ts`(applyTick o/i/u、foldVp)、`components/stock/TickTape.tsx::volTone`、`lib/stock-intraday-svg.ts::sideSummary`(外盤比 = 外/(外+內);判定率 `LOW_DECIDED_PCT=75` 標可疑)。
- **不讀 side**:`live/signal_state._eval_sweep`(首筆外盤自比 `price >= tick.ask_milli`)、期貨引擎、corr。
- 回測 `data/models.Bar1K` 用 1K UpVolume/DownVolume,獨立鏈路(skill 07-31 條)。

## 2. 現況 vs 目標

| 面 | 現況 | 目標 |
|---|---|---|
| 即時 side | 同則訊息簿 `derive_side` | `FlagOfBuySell` 1→inner / 2→outer;0 → 退回 derive_side |
| 回補 side | 同列(成交後簿)`derive_side` → 鎖停 relabel | 兩條推論補 neutral:前一筆報價 → 前一筆成交價 tick rule;仍不出留 neutral;與鎖停 relabel 的先後要定 |
| 掃單首筆外盤 | `price >= tick.ask_milli` | 不動 |
| wire / 前端 | side 三值 | 不動 |

## 3. 既有行為白名單(不能破壞)

- `side` wire 值域三值字面不變;`ticks[].b/a` 仍帶成交當下簿(TickTape 顯示)。
- VP / 外盤比 / 能量副圖算式不變(side 是輸入);`tests/fixtures/vp_parity.json` 前後端 parity 不動。
- `relabel_locked_side` 鎖停補判語意保留(鎖漲停 → inner / 鎖跌停 → outer;五道閘)。
- `apply_backfill` reset + 重放、survivors 不套補判、seq 跳增、試撮跳過、meta 未到 WARNING + 漲跌停值變化重排回補(stock_engine)。
- 掃單簇 `_eval_sweep` 首筆外盤判準與 `tick.ask_milli` 語意不動。
- `StockTick` 既有欄位與 keyword 建構點(tests 16 處)相容 —— 新欄位必須有 default。
- 期貨 / corr 經 `parse_stock_realtime` 的行為不變(它們不讀 side;期貨訊息缺旗標 → 退回 derive_side = 現況)。
- `trial_windows` 兩把尺同源;歷史 row 0 價歸 None 不當價位。

## 4. 事實(本次自查)

- 官方 PDF p.9(pypdf 抽取):`FlagOfBuySell BSTR 內外盤(1: 買盤成交(內盤) 2: 賣盤成交(外盤) 0: 無法判斷)`。字串型。
- 09-14 09:04 起 60 s raw 抓檔(38ca session scratchpad `flag-capture/raw_20260914_090423.jsonl`,49,610 則、82 檔訂閱):
  flag 分佈 2: 29,789 / 1: 19,807 / 0: 14(未去重)。去重 (code, TradeVolume) 首次出現 6,320 筆成交。
- flag vs 同則訊息簿 `derive_side`:一致 78.5%、neutral 18.6%、矛盾 2.9%、flag=0 僅 1 筆。
- **flag vs 前一則訊息簿 `derive_side`(n=6,239,扣每檔首筆):一致 100%、零 neutral、零矛盾。**
  → 帶成交的 REALTIME 那則五檔是**成交後簿**;19% neutral 與 3% 矛盾全由此來。
  引申:`StockDayState.book`(上一則訊息)在處理成交那則當下正是成交前簿。
- flag vs tick rule(前一筆去重成交價;價相等沿上一方向):對 80.5%、錯 16.1%、判不出 3.4%。
- 歷史 1,337 萬筆(memory arch-scan):outer 44.6 / inner 33.9 / 價差內 11.1(列上 Bid/Ask 是成交後簿;61% 可用前一筆報價、37% 要 tick rule)/ 雙側缺 10.1(98.7% 在日高 = 鎖漲停市價佇列)/ 集合競價 0.2。
- 歷史 TICKS row 無旗標;prod server 此刻跑著(e05a964f,12:32 起),TC4 在線,可開側車拉 09-14 TICKS 對 6,320 筆旗標做回補規則準確率實測。

## 5. 09-15 側車實測:歷史回補規則 vs 旗標(ground truth = 09-14 6,320 筆)

側車:獨立 TC4 session SubHistory TICKS 09-14 窗 82 檔(380,854 列,9.3 s;歷史訂閱不殺 REALTIME = refcount bug repro F),
LOGOUT 收工。腳本 scratchpad `fetch_ticks_0914.py` / `rules_xcheck.py`,原始列 `ticks_0914.jsonl`。
配對鍵 (股號, UTC 秒, 價, 量) 順序消耗,6,320 / 6,320 全對上。

**事實 A:歷史 TICKS row 的 `TradeVolume` 全為 "0"**(380,854 列無例外;07-06 報告樣本亦然)。既有 `apply_backfill`
的 survivors 判準 `cum > 回補最大 cum(=0)` → 回補期間已 ingest 的 live tick 全數倖存重放 → 重疊窗(通常 1–3 s)
重複計量。**不在本案動**,記 next-time / 交 user。

**事實 B:單規則(判得出 / 判得出裡對)**:同列簿比 r0 80.7% / 96.5%;前一列簿比 r1 85.2% / 99.3%;
tick rule 嚴格 37.3% / 93.1%;tick rule 相等沿方向 99.4% / 83.1%;前一列中價 88.8% / 98.3%;同列中價 85.1% / 95.3%。

**事實 C:組合(對 / 錯 / 留白,全體 6,320)**:
- r0→r1→tick 沿方向(user 原案):93.1 / 6.3 / 0.6
- r1→r0→tick 沿方向:94.9 / 4.4 / 0.6
- r1→r0:91.3 / 1.4 / 7.3
- r1→r0→前一列中價→同列中價:92.4 / 2.2 / 5.5
- 同上→tick 嚴格:93.5 / 2.9 / 3.6;→tick 沿方向:95.0 / 4.4 / 0.6

**事實 D:殘餘段(r1、r0 都判不出,464 筆,flag inner 274 / outer 190)**:tick 嚴格 55.3%、tick 沿方向 54.2%、
前一列中價 59.4%、同列中價 56.1% —— 全部接近擲銅板。歷史列上沒有訊號能判這一段。

**事實 E:雙側缺列**:對上真值 37 筆全在 5314(鎖跌停,旗標全 outer = 恆等式);全日 5,108 列集中 6 檔(5314 / 6226 / 6706 / 2305 / 2351 / 3374)。
全日 380k 列留白率:r0 13.3% → r1→r0 5.6% → 加兩條中價 4.6% → 加 tick 沿方向 1.35%(其中雙側缺 5,108 列 = 1.35% 幾乎全部,靠鎖停補判)。

**事實 F:旗標 = 0**:去重後 6,320 筆只 1 筆(6706 09:03:22 成交價 144 低於當時買一 144.5,疑盤中零股 / 簿外);試撮與 09:00 集合競價的旗標值未抓到(抓檔自 09:04 起)。
