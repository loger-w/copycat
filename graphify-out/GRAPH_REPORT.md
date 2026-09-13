# Graph Report - copycat  (2026-09-13)

## Corpus Check
- Large corpus: 2368 files · ~3,369,923 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 4687 nodes · 9039 edges · 296 communities (248 shown, 40 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 608 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Lock Quality Engine
- Fade Backtest Config
- Capital Contract Mapping
- TC4 ZMQ Quote Source
- Harness Hooks (non-system)
- Bars Cache & Fetch
- Capital Order Store
- Capital Balance Parsing
- Signal Hub Internals
- Fade Anatomy Analysis
- Live Signal State
- Capital COM Client
- Stock Engine Internals
- Fade Cell Evaluation
- Stock Source & Backfill
- Premarket Screening
- Frontend Stock Components
- Server App Routes
- Fade Market Features
- Trading Calendar
- Live Stock State
- Market Breadth Compute
- Server App Corr Routes
- Harness Hooks (non-system)
- Stock Watchlist
- Capital COM Bridge
- Signal Hub Emit
- Live Stock/Signal Bridge
- TXO OI Levels
- Frontend Types
- Data Backfill Scripts
- Signal Rules
- Frontend Lib
- Frontend Hooks & Query
- Backtest Fade
- Live Corr
- Live Session
- Server Engine
- Server Verify
- Server Corr
- Server Watchlist
- Server Breadth
- Backtest Pipeline
- Capital Client
- Server Stock
- Backtest Fade
- Backtest Fade
- Live Stock
- Fe Hooks
- Fe Lib
- Data Daily
- Server Ws
- Fe Components
- Fe Lib
- Live Payoff
- Live River
- Server Bars
- Backtest Search
- Capital Safety
- Live Trade
- Live River
- Fe Components
- Server Breadth
- Server Signal
- Fe Components
- Fe Components
- Fe Lib
- Server Signal
- Fe App
- Fe Lib
- Fe Lib
- Frontend Tsconfig App
- Backtest Fade
- Capital Balance
- Capital Com
- Server Futures
- Fe Components
- Backtest Fade
- Live Handover
- Live Corr
- Docs Harness Hooks
- Fe Lib
- Corr Config
- Stkfut Map
- Fe Lib
- Fe Lib
- Server Index
- Ref Types React
- Fe Lib
- Fe Lib
- Server Engine
- Server Stock
- Server Stock
- Frontend Package Devdependencies
- Backtest Features
- Server Breadth
- Stock Names
- Docs Harness Hooks
- Fe Components
- Fe Lib
- Data Backfill
- Live Futures
- Server Breadth
- Server Discord
- Server Discord
- Docs Harness Hooks
- Fe Components
- Fe Lib
- Spikes Txo Chain
- Server Index
- Server Stkfut
- Fe Lib
- Frontend Tsconfig Node
- Spikes Capital Login
- Data Import
- Live Models
- Server Overlay
- Server Index
- Fe Hooks
- Fe Lib
- Fe Lib
- Spikes Backfill Phaseb
- Capital Client
- Data Backfill
- Notify Rationale
- Server Corr
- Server Discord
- Server Discord
- Server Futures
- Server Main
- Fe Components
- Fe Hooks
- Fe Lib
- Fe Lib
- Server Audit
- Server Build
- Server Discord
- Server Futures
- Fe Components
- Fe Hooks
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Backtest Simulate
- Server Index
- Server Ws
- Fe Components
- Fe Components
- Fe Components
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Spikes Nk225 Leg
- Server Index
- Server Mis
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Hooks
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Server Shutdown
- Server Breadth
- Server Stock
- Frontend Sha Plugin
- Fe Components
- Fe Components
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Live Futures
- Live Stock
- Server Breadth
- Server Signal
- Server Stock
- Server Watchlist
- Docs Harness Hooks
- Frontend Package Scripts
- Fe Components
- Fe Components
- Fe Components
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Backtest Universe
- Server Capital
- Frontend Doctor Config
- Frontend Package Dependencies
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Spikes River 1K
- Data Models
- Server Discord
- Server Discord
- Server Futures
- Docs Harness Hooks
- Fe Components
- Fe Components
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Capital Client
- Live Signal
- Server Discord
- Server Discord
- Server Futures
- Fe Components
- Fe Components
- Fe Components
- Fe Components
- Fe Hooks
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Test
- Spikes Capital Typelib
- Spikes Index Tree
- Data Store
- Server Breadth
- Server Engine
- Server Futures
- Server Stock
- Fe Components
- Fe Components
- Fe Components
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Fe Lib
- Frontend Tsconfig
- Backtest Init
- Capital Init
- Engine Init
- Init
- Live Init
- Replay Init
- Server Futures
- Server Futures
- Server Init
- Fe Lib
- Pkg Copycat

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 115 edges
2. `Bar1K` - 105 edges
3. `CapitalClient` - 79 edges
4. `FadeBacktestConfig` - 71 edges
5. `StockEngine` - 71 edges
6. `SignalHub` - 70 edges
7. `react` - 60 edges
8. `DailyIndex` - 51 edges
9. `TC4QuoteSource` - 51 edges
10. `Bar` - 49 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `DailyIndex`  [INFERRED]
  spikes/backfill_phaseb_1k.py → copycat/data/daily.py
- `scan_band()` --uses--> `DailyIndex`  [INFERRED]
  spikes/backfill_phaseb_1k.py → copycat/data/daily.py
- `_harvest()` --uses--> `Bar1K`  [INFERRED]
  spikes/backfill_phaseb_1k.py → copycat/data/models.py
- `scan_band()` --calls--> `_needs_refetch()`  [EXTRACTED]
  spikes/backfill_phaseb_1k.py → copycat/data/backfill_tc4.py
- `scan_ctrl_t1()` --calls--> `_needs_refetch()`  [EXTRACTED]
  spikes/backfill_phaseb_1k.py → copycat/data/backfill_tc4.py

## Import Cycles
- None detected.

## Communities (296 total, 40 thin omitted)

### Community 0 - "Lock Quality Engine"
Cohesion: 0.06
Nodes (56): fmt_min(), _lock_bucket(), LockQualitySignals, LockTracker, _queue_bucket(), Phase 2 鎖板品質:LockTracker(鎖死定義與 neigui extract_features.py 對齊)., 逐 bar 餵入;first_touch / n_reopens 盤中可查且不回改;finalize 收盤定稿., _tier() (+48 more)

### Community 1 - "Fade Backtest Config"
Cohesion: 0.07
Nodes (69): Condition, _combo_from_base(), enumerate_baseline_combos(), enumerate_fade_stop_combos(), enumerate_tp_combos(), fade_sim_config_hash(), FadeBacktestConfig, FadeStopCombo (+61 more)

### Community 2 - "Capital Contract Mapping"
Cohesion: 0.07
Nodes (62): contract_from_fill(), exchange_product_of(), _month_year_codes(), multiplier_of(), product_of(), 群益送單欄位映射 + TC4 → 期交所契約碼轉換(純函式;唯一的 IO = 個股期對映表查詢)。 `multiplier_of`(乘數 fallback)與…, 部位列的 `stock_no` → 台股股號;對映不出來回 None(**不 raise**)。 `Position.stock_no` 在 sec…, YYYYMM → 月碼 + 年末碼(期貨/Call A..L、Put M..X)。 (+54 more)

### Community 3 - "TC4 ZMQ Quote Source"
Cohesion: 0.06
Nodes (27): ConnectionError, Any, UNSUB→SUB 冪等重掛(逐 symbol 訂閱路徑共用;stock/futures/corr 三 source)。…, 已訂閱才退訂(未訂閱 = no-op),並清掉這個 symbol 的自癒帳。 帳留著的話,下一輪訂閱會**帶著上一輪的 variant 與…, 退訂後、Disconnect 前對 TC4 送 LOGOUT(fix/tc4-logout)。 wrapper 的 `Disconnect()` 只關…, 原始電文 → REALTIME 訊息 dict;無 topic 分隔 / 非 JSON / 非 REALTIME → None。 **回整則 msg 而非…, SUB socket 一則原始電文 → TXO Tick 分派(listener 與測試共用)。 子類覆寫這一支即可共用整個…, PING 都收不到超過閾值 → 判斷線,重連 + 重訂閱 + 通知 on_reconnect(補回遺失段)。 (+19 more)

### Community 4 - "Harness Hooks (non-system)"
Cohesion: 0.07
Nodes (42): check_standard(), check_wave(), Commit, main(), Path, wave 模式:[waveN] 存在 + 輸出 wave→SC 對映(全 SC 歸屬由呼叫方核)。, /feat Phase 8 的 TDD commit tag 機械驗證(feat.md Phase 8 步驟 2 的 script 化)。 規則單一…, start_sha..HEAD 依時序(舊 → 新)。 (+34 more)

### Community 5 - "Bars Cache & Fetch"
Cohesion: 0.07
Nodes (40): BarsFetcher, Bar, K 線 bar(毫元整數;`t` 日 K = YYYY-MM-DD、分 K = "YYYY-MM-DD HH:MM" 台北)。 與 DailyBar…, stock_bars(), BarsCache, BarsResult, build_daily(), build_minute() (+32 more)

### Community 6 - "Capital Order Store"
Cohesion: 0.06
Nodes (34): is_option_contract(), 期交所契約碼 → 是否為選擇權(送單分流 SendOptionOrder vs SendFutureOrder)。 「什麼是期貨」只能有一份定義:原本…, FillRecord, OrderRecord, 逐筆成交(D 事件)一列(成交點精確版,L76)。與 OrderRecord 同尺:qty 已換算…, 委託清單一列 = 一張單的聚合狀態(key=13碼委託序號)。qty 已換算顯示單位。, ReplyRecord, _Agg (+26 more)

### Community 7 - "Capital Balance Parsing"
Cohesion: 0.07
Nodes (46): merge_fut_positions(), _opt_float(), parse_balance_line(), parse_open_interest_line(), parse_profit_line(), ProfitRow, NamedTuple, OnRealBalanceReport(即時庫存)/ 損益試算 / OnOpenInterest(期貨部位)解析與收集。 邏輯照搬 treading-king… (+38 more)

### Community 8 - "Signal Hub Internals"
Cohesion: 0.05
Nodes (24): Path, 同 (code, time) 且**相鄰**的多 row 合成一則送出(SC-4)。 單槽…, 關機盡力落檔:jsonl 是歷史真相源,Discord 這時不再送。, 每日 `policy_outcome_time`(牆鐘 `now_fn`)跑一次;起動時**只在已過當日時點才立即跑** (就算當日那一次;13:50…, 把 T+1 / T+2 開盤價(連日期)原地補進過去日檔的政策列。 範圍 = 最近 `policy_outcome_days` 個日檔中,日期**同時小於**…, 一檔的日 K;例外 → None、逾時 / 斷線 → 空 list + WARNING(兩者該檔本趟都留 null); 逐檔間隔沿 CDP 基準 worker…, 讀取日集合 = {engine 日別, 牆鐘日}(R2-3);通常同一天 = **單檔讀**。 寫檔的日別有兩個來源(XR-3):engine 在場時走…, 當日 jsonl → row 清單;壞行跳過(半寫入的最後一行不該讓整條端點掛掉)。 `errors="replace"`… (+16 more)

### Community 9 - "Fade Anatomy Analysis"
Cohesion: 0.06
Nodes (48): _cell_param(), flush_anatomy(), _gap_bucket(), hl_anatomy(), _inner_bucket(), inner_gate_anatomy(), mfe_anatomy(), _nested_float() (+40 more)

### Community 10 - "Live Signal State"
Cohesion: 0.09
Nodes (28): _change_pct(), _clock_key(), _mono(), datetime, 個股即時訊號偵測狀態機(零 IO;design §3 — SC-1/2/3/4/6;spec #192 掃單簇)。 六類訊號:CDP 五線穿越 / 爆拉跌 /…, 當前同毫秒群的前綴狀態(一檔一群;時刻換了就整個換掉)。, 由 SignalHub 從 `StockDayState` 組出的簿面快照(消費端已過濾市價 0 檔位)。, 牆鐘 → 秒數純量。差值才有意義,固定 epoch 相減避開 naive datetime 的時區假設。 (+20 more)

### Community 11 - "Capital COM Client"
Cohesion: 0.07
Nodes (23): BuySell, _ComCall, CapitalClient, _do(), AbstractEventLoop, Market, 期貨/選擇權送單。contract = 已解析期交所碼(HOT 由 route 先 resolve), multiplier = 金額閘乘數(route 由…, market → 帳號選擇 + store 市場別交叉驗證。回 (gate, account)。 store 查無(None)信 request 的… (+15 more)

### Community 12 - "Stock Engine Internals"
Cohesion: 0.05
Nodes (21): executor thread:關機中早退,縮小「close 後 source 再被呼叫」的窗。 cancel 一個正 await `to_thread` 的…, executor thread:owner 已在池內,只需重掛 SUB(UNSUB→SUB 冪等)。, 階段二:首筆新日 tick 確認 → reset 全部狀態,觸發 tick 重新 ingest。, TC4 重連:status 推播 + 主圖自癒重回補(design §2.4)。, 入列回補 job 的**唯一**接點(六個產出點共用:set_main / rollover stage2 / reconnect / 漲跌停值變 /…, timer 到期 → 出帳後入列。 **先出帳**:handle 已經用掉了,留在 dict 裡會讓 `close()` / rollover 去取消一支 死…, 退訂 / 主圖槽位真退訂時呼叫:取消該 code 在途的逾時重排 timer + 清逾時記帳。 兩份記帳同以**訂閱期**為界(與 `_backfilled`…, 取消並清空全部在途重排 timer(`close()` 與 rollover stage2 共用的唯一取消點)。 (+13 more)

### Community 13 - "Fade Cell Evaluation"
Cohesion: 0.09
Nodes (48): _entry_idx_for(), _actuarial_block(), _baseline_entry_idx(), _broker_hits(), _calendar_segment(), _CellSpec, _cluster_z_block(), _d5_criteria() (+40 more)

### Community 14 - "Stock Source & Backfill"
Cohesion: 0.08
Nodes (29): Any, instrument key → TC4 symbol(**唯一定義**;engine 經 `symbol_of` 取用)。 - 股號 →…, 台北交易日 YYYY-MM-DD → 日盤 UTC 窗。 窗以**小時**為粒度(`YYYYMMDDHH`),實際回 UTC 00–06 = 台北…, instrument key → TC4 symbol(`StockSource` Protocol;engine 路由表的鍵來源)。, rollover 階段一:換日窗(重掛訂閱由呼叫端執行)。 自癒的 variant / attempts / 退避一併清掉:那些是「**昨天**那把 key…, 對**當下**的窗(含 variant)逐 symbol 發 UNSUBQUOTE;`_subscribed` 不動。 `_subscribed` 是…, UNSUB→SUB 冪等重掛;失敗 raise(engine refcount 回滾依賴,design §2.4)。, 排下一發健檢,並**換掉**這個 code 上待觸發的那一把(疊鏈是 C-4 的根因)。 (+21 more)

### Community 15 - "Premarket Screening"
Cohesion: 0.09
Nodes (23): apply_eligibility(), 當沖資格 + 處置股過濾,保序。 `daytrade_ok` = 逐檔查 `TaiwanStockDayTrading` 最近交易日**有列**的代號集合…, ScreenCandidate, BreadthFetchError, RuntimeError, 取數失敗;`quota=True` 代表 FinMind 配額用盡(HTTP 402),呼叫端改走長退避。, date, datetime (+15 more)

### Community 16 - "Frontend Stock Components"
Cohesion: 0.05
Nodes (19): Props, SOURCE_TEXT, OrderPanel(), STATUS_BLOCKED, useTxoContracts(), BOX, PnlChart(), Props (+11 more)

### Community 17 - "Server App Routes"
Cohesion: 0.08
Nodes (38): BreadthFetchers, create_app(), _breadth(), _breadth_booted(), corr_state(), _index(), index_state(), list_series() (+30 more)

### Community 18 - "Fade Market Features"
Cohesion: 0.10
Nodes (39): FadeTakeProfitCombo, _auction_mismatch(), _bid_exhaustion(), fade_trigger_features(), _intraday_basic(), _open_eq_high_count(), _price_vol_divergence(), T+1 Fade 竭盡特徵(design.md v2 §6e/6f/6g)— 觸發 bar 時點計算,零 IO. ~224 欄:盤中基礎 7 + 微結構… (+31 more)

### Community 19 - "Trading Calendar"
Cohesion: 0.08
Nodes (38): calendar(), _calendar_crosscheck(), _breadth_today(), _start_index(), _resolve_trade_date(), _now(), _date, _datetime (+30 more)

### Community 20 - "Live Stock State"
Cohesion: 0.08
Nodes (40): 期指 K 線 bar(`tf` = "D" 日 K / "1" 分 K;start/end = YYYY-MM-DD 含端點)。 **必須從這條…, _aggregate_1k_rows(), aggregate_1k_to_daily(), _daily_fallback_window_days(), DailyBar, _delta_vol(), _fold(), in_index_heal_window_now() (+32 more)

### Community 21 - "Market Breadth Compute"
Cohesion: 0.08
Nodes (38): compute_day_limitups(), 連板數純函式(零 IO)—— SC-2。 輸入 = FinMind `TaiwanStockPrice` 的單日全市場 rows(無 data_id);輸出…, 數值欄 → float;缺值 / 非數值 → None(`backfill_finmind._map_row` 同語意)。 `bool` 明確排除:True…, 單日 TaiwanStockPrice 全市場 rows → 該日收盤漲停的 4 位普通股代號集合。 -…, _to_float(), assemble_universe(), classify_stock_id(), compute_breadth() (+30 more)

### Community 22 - "Server App Corr Routes"
Cohesion: 0.08
Nodes (36): _BootT, 逐腿自癒閘(N051 + F4):依 symbol **前綴**分派時段閘,未列的段恆 True。 corr 是唯一一條 session…, segment_leg_gate(), _boot(), _Booted, lifespan(), _boot_all(), _boot_engines() (+28 more)

### Community 23 - "Harness Hooks (non-system)"
Cohesion: 0.11
Nodes (21): CompletedProcess, run_hook(), test_active_feature_injects_slug_phase_gate(), test_no_active_feature_silent(), git(), make_repo(), make_state(), Path (+13 more)

### Community 24 - "Stock Watchlist"
Cohesion: 0.09
Nodes (35): load_backtest_config(), Path, load_fade_config(), Path, main(), CLI 入口:import-neigui / replay / validate / compare 逐 task 接上., 讀取順序:env → repo root .env → 明確錯誤(design round 1 R12)., _resolve_finmind_token() (+27 more)

### Community 25 - "Capital COM Bridge"
Cohesion: 0.05
Nodes (11): _OrderEvents, _parse_account_row(), GetUserAccount → pump 迴圈收 OnAccount 事件到 timeout(review R6)。 OnAccount…, SKReplyLib 事件 sink;回呼例外不可炸掉 COM 事件迴圈。, SKOrderLib 事件 sink(帳號清單+即時庫存+損益+期貨部位);回呼例外不可炸 COM 迴圈。, 決定 SKCOM.dll 載入方式 → (要加進 DLL 搜尋路徑的資料夾 or None, 給 GetModule 的引數)。 有設 dll_dir →…, OnAccount 的 bstrAccountData 一列 → (market_prefix, full_account);畸形列回 None 略過。…, 真實群益 SKCOM 實作(comtypes)。 (+3 more)

### Community 26 - "Signal Hub Emit"
Cohesion: 0.08
Nodes (34): atomic_write_bytes(), Path, 位元組版(零換行翻譯):原地改寫既有檔、其餘位元組要逐字保留時用(signal_hub 回填)。, _dedup(), format_policy_group_text(), format_signal_group_text(), format_signal_text(), _is_policy() (+26 more)

### Community 27 - "Live Stock/Signal Bridge"
Cohesion: 0.09
Nodes (34): 期貨 REALTIME 對映(capital-order SC-8;design §10)。 期貨 REALTIME…, _best_limit_price(), derive_side(), _hhmmss(), is_trial_window(), parse_hist_tick(), _parse_levels(), parse_stock_realtime() (+26 more)

### Community 28 - "TXO OI Levels"
Cohesion: 0.08
Nodes (34): _dotenv_values(), FinMind token 解析(server 不載 dotenv:env → repo root .env 逐 key fallback)。 自…, repo root .env 逐 key 解析。utf-8-sig:Windows BOM 會讓首 key 靜默失效; never-…, `FINMIND_TOKEN in os.environ` 即用(含空字串 = 未設,可壓制 .env)→ 否則 .env。 空字串當未設而**不**往下…, resolve_token(), _empty(), fetch_oi_levels(), _fetch_rows() (+26 more)

### Community 29 - "Frontend Types"
Cohesion: 0.05
Nodes (39): AVG_SOURCES, AvgSource, BreadthBuckets, BreadthCounts, BreadthPoint, BreadthRow, BreadthRowsState, BreadthState (+31 more)

### Community 30 - "Data Backfill Scripts"
Cohesion: 0.08
Nodes (32): _dates(), DayTradeIndex, _fetch_dataset(), _fetch_retry(), FetchFn, Path, FinMind 當沖資格資料回補:TaiwanStockDayTrading(按日)+ DispositionSecuritiesPeriod. 「可當沖」=…, 當沖資格判定:在當日名單且不在處置期間;該日無任何 rows → None(未覆蓋,R18). (+24 more)

### Community 31 - "Signal Rules"
Cohesion: 0.11
Nodes (36): _append_seed(), _as_int(), _bad(), _clamp(), default_rules(), load_rules(), _migrate_v1(), _migrate_v2() (+28 more)

### Community 32 - "Frontend Lib"
Cohesion: 0.05
Nodes (32): BASELINE_TO_CENTER, EDGE_LABEL_H, EdgePriceLabel, EnergyBar, ExtremeMark, GeometryOpts, Input, IntradayGeometry (+24 more)

### Community 33 - "Frontend Hooks & Query"
Cohesion: 0.07
Nodes (23): EMPTY_TEXT, FuturesChart(), hhmmOf(), liveSlotOf(), pad2(), Props, tradeSlotOf(), initialMode() (+15 more)

### Community 34 - "Backtest Fade"
Cohesion: 0.09
Nodes (27): _actuarial_rows(), build_universes(), _with_bars(), _fwd_note(), Path, round 3 報告:b 變體表 + Q2(候選)+ 底倉格 + 精算表 + forward 段(SC-2/4/7)。, round 4 報告:主判定變體表(含賺賠比)+ Q2′ + 消融 + 敏感度 + 雙精算表., round 5 報告:樣本預算 + 主判定臂(Q3)+ 敏感度 + 消融 + 精算對比 + 底倉觀察. (+19 more)

### Community 35 - "Live Corr"
Cohesion: 0.07
Nodes (22): all_day_window(), CorrQuoteSource, Any, 相關係數引擎的行情源:泛化任意 TC4 symbol 訂閱(SC-5;design §5.5)。 與…, 當日 1K → [(台北 minute_end, close 毫點)]。 **首頁在預算內未備妥 →…, 當日 UTC 全天窗;不隨台指盤別變動(design §5.5)。, collect_1k_minutes(), Any (+14 more)

### Community 36 - "Live Session"
Cohesion: 0.08
Nodes (32): in_futures_session_now(), time, FuturesQuoteSource:TXF/MXF/TMF HOT REALTIME 資料源(capital-order design §10)。 繼承…, 期貨盤別閘 = TXO 時段各寬 5 分(期貨與 TXO 同時段,共用 `in_txo_session`)。 prod 自癒閘 = 交易日曆 AND…, backfill_window(), in_txo_session(), SessionKey, struct_time (+24 more)

### Community 37 - "Server Engine"
Cohesion: 0.08
Nodes (16): _content(), EngineRuntime, _fmt_precise_time(), 可下單商品全集:active 序列合約(SeriesInfo 全集,非 snapshot 已成交子集)∪ TXF。 trade 白名單資料驅動(design…, 現貨(台指期)最新價;index-board txf_getter 用(IR1)。單值讀取免鎖(GIL 原子)。, 節流 snapshot 流:版本有變**且內容有變**才 yield,間隔 ≥ throttle_secs。 `seed` = 呼叫端已經送出去的首則…, rollover 比對用的回補窗 identity(預設 = session_key)。, §4 select 流程:unsub 舊 → reset → 交接協定(訂閱 buffer → 回補 → flush)→ live。 互斥涵蓋**整個… (+8 more)

### Community 38 - "Server Verify"
Cohesion: 0.09
Nodes (31): BreadthConfig, load_breadth_config(), Path, 家數帶 / 騰落線的輪詢與退避門檻(market-overview R2 design §5)。 慣例沿用…, 讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 → ValueError。, load_dataclass_json(), Path, Dataclass config JSON 載入樣板 — 唯一實作,取代三份 loader 手刻. 樣板 = unknown-key 檢查(raise… (+23 more)

### Community 39 - "Server Corr"
Cohesion: 0.09
Nodes (14): CorrelationEngine, Any, 只訂 source == tc4 的腿;單腿失敗降級續行,失敗品進 `_pending_subs` 由重試迴圈接手。 (寫入安全:start() 正…, pending 腿每 `resub_interval_secs` 重訂一次,成功即出列;全清空即結束。 迭代 `tc4_legs()` 而非…, 一次取樣 + 計算 + 廣播(tick task 每 tick_secs 呼叫;測試直接呼叫)。, 台指腿的分鐘點 + 每秒 delta 廣播。 台指腿走 pull 不走推播,分鐘桶用本機時鐘 —— `futures_engine` 的 `st.t` 在既有…, 逐腿 1K 回補(single-flight);單腿失敗只降級該腿(SC-3)。 `legs` = 只補這些腿(逾時重試輪用)。`None` =…, single-flight 互吃:把被擋下那一發的腿併回進行中那一輪的 pending。 舊碼兩處都是靜默… (+6 more)

### Community 40 - "Server Watchlist"
Cohesion: 0.13
Nodes (21): _copy_groups(), Group, 自自選與**所有**群組移除(留在任一群組就會被 normalize 補回 codes)。, 建立空群組;strip 後同名已存在 → no-op(不報錯 —— 使用者的意圖已經成立)。 保留名 / 空名不在此判,交 `_commit` 內的…, 刪群組;codes 不動 —— 成員落回未分組衍生桶(刪群組不等於刪股票)。, 改名;新名撞既有名 / 保留名 / 空名 → `normalize` 拒(`BAD_GROUP`)。, 整組覆蓋(盤前篩選 nightly 寫入,#173):該群組成員 = `codes`(不存在自動建); 原成員若不再屬於**任何**群組,同時自 wl…, 自該群組移出;wl codes 不動 —— 移出群組不等於移出自選。 (+13 more)

### Community 41 - "Server Breadth"
Cohesion: 0.10
Nodes (15): BreadthEngine, FinMind 全市場家數輪詢引擎;取數三元組由呼叫端注入(測試 fake / prod 真取數)。, REST 全量(`GET /api/market/breadth`)。`counts` 為 None = 首輪未成 = 載入中。, REST 全量逐檔(`GET /api/market/breadth/rows`)—— **連板算術只在這裡**。 `streak`…, WS scalar 訊息;`last_minute` 只在本輪真的 append 了一格時帶值。, 非交易日首圈失敗要沿既有退避重試,到成功一次為止(C1)。 `_in_window` 吃了交易日 gate 之後,假日的取數機會只剩「首圈無條件」那一次;…, 首圈無條件跑一輪(盤後開站也要有數字),之後只在台北窗內取數。 `except Exception` 是**任務存活邊界**(index…, 一輪:快照 → 對照表 → 統計 → append/落檔 → 廣播(成敗皆廣播一則)。 (+7 more)

### Community 42 - "Backtest Pipeline"
Cohesion: 0.12
Nodes (32): avg20_t1(), find_trigger(), 靜態 6 欄(neigui daily_ctx 同源;dtr_t1 Phase A 無資料源 → None)., 第一根 high ≥ prev_close×(1+θ) − eps 的 bar index;無 → None., 20 日均量(張),基準 = T-1(neigui prevs[-20:] 同源,不含 T 日)., 觸發窗 w = bars[:trig_idx+1] 上的 13 盤中特徵 + 靜態 6 欄(bool → 1.0/0.0)., static_features(), trigger_features() (+24 more)

### Community 43 - "Capital Client"
Cohesion: 0.08
Nodes (20): 價格別記憶的日界 = 本機日曆日(與回報 idx23 同時區;idx23 跨日語意未實證,見 `store.note_price_type`)。 抽成…, broadcast 失敗不可炸 COM 執行緒/寫入鏈:推播是輔助面,log 留痕即可。, OnNewData 主動回報 → store + 推 WS;成交(D)排程庫存重查。, 幫浦圈呼叫:due 到了或距上次查詢逾 60s → 發查詢。 degraded(回報斷線)也要查 — 此時 60s 輪詢是部位唯一的更新來源。…, 證券庫存收齊 → 暫存(不落 store)→ 串行接損益查詢(避開 1019 查詢處理中)。 同檔多種庫存列(集保+融資並存)全數保留 — store 以…, 損益回填進 pending 證券部位(均價+含費稅息基底)→ 串行接期貨部位查詢。 同檔多種類報告每種類一列:只回填同 kind 的列 —…, 期貨部位查詢(串行末段);無期貨帳號 → fut 恆空;查詢失敗 → 沿用上一輪 fut 部位收尾(review A7:閃斷不可把面板期貨部位清空)。, OI 查詢失敗/逾時:沿用 store 既有 fut 部位(review A7)。 僅 OI 成功回報(_on_oi_complete)才全量覆蓋 fut 段。 (+12 more)

### Community 44 - "Server Stock"
Cohesion: 0.09
Nodes (20): is_futures_key(), instrument key 是否為個股期(兩段形對照腿或三段形合約)。, instrument key → 試撮窗(個股期空窗,D2)。 **單一定義**:engine(REALTIME)與 source(回補)必須同一把尺 ——…, trial_windows_for(), _in_futures_session(), _now_taipei_hhmm(), _now_taipei_time(), _observe_window_now() (+12 more)

### Community 45 - "Backtest Fade"
Cohesion: 0.11
Nodes (30): assign_pool(), _bucket_stats(), _classify_approach(), cluster_se(), _comparison_and_verdict(), diagnose_limit_approach(), diagnose_pool_fade(), load_turnover_map() (+22 more)

### Community 46 - "Backtest Fade"
Cohesion: 0.12
Nodes (29): _build_day_recs(), cdp_levels(), _DayRec, _first_flip(), flow_flip_anatomy(), _scan(), flow_flip_go(), _fmt_rate() (+21 more)

### Community 47 - "Live Stock"
Cohesion: 0.09
Nodes (12): MinuteAgg, 把一筆成交折進 VP。**規則逐條對齊前端 `stock-accum.ts::foldVp`** (parity 由…, 分鐘序列的 wire 形。**鍵名的單一定義** —— 全量 snapshot 與群組 batch 共用。 兩邊各寫一份的漂移樣態是其中一邊的 `h`/`l`…, 靜態盤別資料的 wire 形(同上,單一定義)。 缺 meta 回 `None` **不是漏鍵**:前端 `raw.meta ?? null`…, 群組 batch 專用的輕量 payload(code review A1)。 `group_snapshot` 對最多 150 檔(上限)、每 60s…, REST 全量(design §4:snapshot 為前端累算基底)。 `tape=False` =…, True = 收下(通過試撮/去重);False = 丟棄。, 原子重建 + merge:回補列為基底,回補期間已 ingest 的 live tick (cum > 回補上限)為倖存者接續重放 —… (+4 more)

### Community 48 - "Fe Hooks"
Cohesion: 0.11
Nodes (29): CapitalEvent, CapitalListener, clearInvalidateTimers(), emitCapitalEvent(), EVENT_QUERY_KEY, fetchJson(), fillsQueryOptions(), invalidateTimers (+21 more)

### Community 49 - "Fe Lib"
Cohesion: 0.07
Nodes (28): CHART_MODE_KEY, CHART_TOGGLES_KEY, FEE_DISCOUNT_KEY, FUT_CHART_MODE_KEY, INDEX_OVERLAY_STORE, LEGACY_MAIN_CODE_KEY, LIMIT_LIST_FILTER_KEY, MAIN_CODE_KEY (+20 more)

### Community 50 - "Data Daily"
Cohesion: 0.12
Nodes (9): DailyIndex, _DayRow, 日線索引:adv20 / 一價到底 / 下一交易日 / 漲停集合 / 連板數., n 個交易日前的 date;不足 → None., 參考前收 = close − spread(neigui 同源,除權息安全);≤0 → None。 該 row 無 spread 資訊(None)→…, 含當日往前 n 個 close;不足 → None., 布林帶寬 = 2kσ/MA(母體 σ);MA ≤ 0 或資料不足 → None., 當日帶寬在近 window 日帶寬中的百分位 rank(嚴格小於比例);資料不足 → None. (+1 more)

### Community 51 - "Server Ws"
Cohesion: 0.11
Nodes (21): ws_corr(), ws_index(), ws_river(), ws_stock(), ws_txo_pnl(), _consume_ws_task(), _is_close_sent_error(), _is_disconnect() (+13 more)

### Community 52 - "Fe Components"
Cohesion: 0.11
Nodes (24): amountRank(), amountText(), buildEntries(), changeText(), changeTone(), decimalText(), DEFAULT_FILTER, Entry (+16 more)

### Community 53 - "Fe Lib"
Cohesion: 0.13
Nodes (24): arrivalOrder(), displayLabel(), firstness(), formatGroupToastText(), groupKindLabels(), groupPolicies(), groupPolicyTags(), groupRuleNames() (+16 more)

### Community 54 - "Live Payoff"
Cohesion: 0.15
Nodes (20): ChainAggregator, ChainAggregator:零 IO 聚合狀態機(內外盤累積 → 損益曲線 snapshot)。design.md §2。, SC-1 per-contract 明細:strike 升冪、同 strike C 在前(deterministic)。, 單一 active 序列的逐檔累積;台指期(`SPOT_PREFIX`)只更新 spot(DR-9 分流)。 其餘期貨(個股期 / 海外腿 / 費半 /…, DR-3:清空全部 per-symbol 狀態並替換合約集合(select 切換時呼叫)。, Totals, OptionContract, build_grid() (+12 more)

### Community 55 - "Live River"
Cohesion: 0.13
Nodes (17): close_clamp_rank(), _expand(), offset_of(), 盤別 → (start_min, end_min);未知盤別回日盤窗(never-raise:引擎不因盤別字串倒)。, 跨午夜展開後的 `(m, start, end)` —— `offset_of` 與 `close_clamp_rank` 的同一把尺。…, 台北 minute-of-day(終點標記)→ 窗內 offset(1..N);窗外 None。 跨午夜:小於窗首的分鐘先 +1440 展開(夜盤 00:30…, 收盤補正的「第幾分鐘」:非 clamp 0、`end+1` → 1、…、`end+5` → 5;超出 clamp 窗 None。 `offset_of` 把…, window_bounds() (+9 more)

### Community 56 - "Server Bars"
Cohesion: 0.09
Nodes (27): index_overlay(), tagged(), market_bars(), plain_with_status(), tagged_source(), _market_payload(), BarsStatus, 大盤 K 線回應(index-board N-5)。 `meta` 不是裝飾:前端固定把它渲染成一行「來源 · 涵蓋期間」,讓「壞了 vs 沒資料」… (+19 more)

### Community 57 - "Backtest Search"
Cohesion: 0.14
Nodes (24): _ga_candidates(), GA 候選規則:predicates → exhaustive + GA seeds → 排序 → jaccard 去重 top-30(wf/單切分共用)., build_predicates(), _entry(), _evaluate(), exhaustive_scan(), _try(), ga_search() (+16 more)

### Community 58 - "Capital Safety"
Cohesion: 0.18
Nodes (24): _dotenv_values(), _env_limit(), get_capital(), _getenv(), 從環境變數組裝 CapitalClient 單例(get_capital;結構對照 treading-king capital_factory)。…, repo root .env 的 CAPITAL_*/TXO_AUDIT_DIR 逐 key 解析(每次 get_capital 重讀, 量小;server…, os.environ 有此 key(含空字串)即回傳,完全不 fallback;僅未設才讀 repo root .env。 與 cli/notify(值空白也…, 上限環境變數 → 數值或 None(=不限)。未設/空/0/負值/解析失敗都是 None; 解析失敗要留 warning — user… (+16 more)

### Community 59 - "Live Trade"
Cohesion: 0.12
Nodes (24): AccountInfo, BrokerRejectedError, classify_is_sim(), mask_account(), millipts_from_price_str(), OrderReport, OrderRequest, parse_accounts() (+16 more)

### Community 60 - "Live River"
Cohesion: 0.14
Nodes (22): _hh_mm(), minute_end_from_1k(), minute_end_from_taipei(), minute_end_from_utc_hhmmss(), parse_1k_minutes(), Parsed1k, NamedTuple, 江波圖的純對映層(design v2 §1/§4;零 IO、只依賴 stdlib)。 **分鐘鍵一律「終點標記」**(bar end),與 TC4 1K 的… (+14 more)

### Community 61 - "Fe Components"
Cohesion: 0.13
Nodes (18): RIVER_FILLS, RIVER_STROKES, RIVER_TEXTS, CardProps, fmtPrice(), Props, RiverCard, RiverCards() (+10 more)

### Community 62 - "Server Breadth"
Cohesion: 0.12
Nodes (19): build_name_map(), build_type_map(), dedup_sector_map(), parse_active_disposition(), date, TaiwanStockInfo rows → `stock_id` → `stock_name`(同代號取最新 date 那筆)。 snapshot…, TaiwanStockInfo rows → `stock_id` → `"twse"` / `"tpex"`(取最新 date 那筆)。 `type`…, TaiwanStockInfo rows → `stock_id` → 主產業(決定性去重)。 Tie-break 順序: 1.… (+11 more)

### Community 63 - "Server Signal"
Cohesion: 0.11
Nodes (18): _copy_rule(), _filter_levels(), 規則 / detector / 開關集合是**不可分割**的一組(R2)。 拆成三個平行 dict 時,熱路徑可能讀到「新規則配舊…, 對外回傳的規則一律是副本 —— 呼叫端改到的不能是熱路徑正在讀的那份。, 規則只訂閱部分 CDP 線 → 只餵那幾條(detector 只認得被餵進去的線)。, 三態(`load_rules`):缺檔 → 由既有全域設定 + 舊開關檔生成預設並落檔; 合法(含空陣列)→ 照用(使用者刪光規則不得復活預設);壞檔 →…, 建 detector 的**唯一**入口(R5):初始化 / 遷移 / upsert 三處同式, 漏帶 `now_fn`…, `rule_id` None = 新增(配新 id),否則 = 編輯(缺 → RULE_NOT_FOUND)。 順序(R17):鎖內驗證 → 落檔 →… (+10 more)

### Community 64 - "Fe Components"
Cohesion: 0.14
Nodes (23): applyDrop(), avgBadge(), dropHint(), EMPTY_WL, fmtPrice(), loadCollapsed(), loadUngroupedCollapsed(), persistCollapsed() (+15 more)

### Community 65 - "Fe Components"
Cohesion: 0.11
Nodes (20): barW(), ChartStatic, ChartVariant, CoreProps, EMPTY_ENERGY, EMPTY_IDX_LINES, EMPTY_PEGS, EnergySub (+12 more)

### Community 66 - "Fe Lib"
Cohesion: 0.12
Nodes (19): accumFromGroupSnapshot(), applyTick(), extendMinutes(), foldVp(), fromSnapshot(), GroupLikeSnapshot, MinuteAgg, minuteKey() (+11 more)

### Community 67 - "Server Signal"
Cohesion: 0.10
Nodes (18): 台北 `HH:MM:SS.fff` → 自午夜秒數(float);格式不符 → None(呼叫端退回牆鐘)。 研究 tick 檔的「毫秒(自午夜)」÷…, tick_secs(), _event_id(), _put_drop_oldest(), 一顆掃單簇事件 → 評四條政策,每命中一條各發一列 `kind="policy"`(WS + jsonl)。 不評(raw 列照記、零政策列)的情況:參考價缺…, `notify` 只擋 Discord:jsonl 是歷史真相源,關通知不等於不留紀錄。, 有界佇列滿載策略(design R14):丟最舊再放入,熱路徑零反壓。回傳「是否丟了一筆」。, 決定性鍵(design §4.3 R1):不依賴 process 記憶 → 重啟後同一事件同 id。 `rule_id` 是必要的一段:同 kind… (+10 more)

### Community 68 - "Fe App"
Cohesion: 0.11
Nodes (15): App(), CorrPage, FUT_PRODUCTS, FutProduct, FuturesPage, IndexPage, initialProduct(), initialStockCode() (+7 more)

### Community 69 - "Fe Lib"
Cohesion: 0.13
Nodes (17): aggregate(), alldayFillPoints(), baseFill(), clampFillX(), EMPTY_FILLS, EMPTY_MARKS, FILL_MARK, FillBase (+9 more)

### Community 70 - "Fe Lib"
Cohesion: 0.16
Nodes (18): avgText(), cardText(), chipText(), chipTitle(), EMPTY_POSITIONS, futLotText(), futQtyText(), FutRow (+10 more)

### Community 71 - "Frontend Tsconfig App"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleDetection (+13 more)

### Community 72 - "Backtest Fade"
Cohesion: 0.17
Nodes (20): _evaluate_round5(), _entry_inner15(), _entry_signal(), _entry_vote(), _levels_for(), _vote_params(), round 5 評估:投票制進場(內盤比 × 流向反轉 × 位階)+ 最簡出場。 出場 = 硬線(guard)∧ 災難回落 ∧ 抱到收盤(無結構停損 / TP…, find_inner15_entry() (+12 more)

### Community 73 - "Capital Balance"
Cohesion: 0.12
Nodes (10): BalanceCollector, Any, 收集一輪查詢的多筆事件,結束標記或 timeout 後一次 flush(全量替換語意)。 只在 COM…, 最後一筆欠帳的 deadline(None = 沒有未清欠帳)。唯讀觀測窗,語意 =「窗還開著嗎」。, 發新查詢前清空本輪。預設把欠帳窗關掉(正常路徑 = 上一輪已正常收尾); `keep_abandoned=True` 供 client 在「放棄輪的 `##`…, 重連 / 重登落地的清點(N018)。與 `reset()` 的差別只有一個字但是關鍵: **`_awaiting` 留在 False** ——…, 放棄本輪(client 逾期解卡 / pending watchdog 逾時):清空 + 開遲到終止符窗。 必須在放棄的當下呼叫,不能延到下一次發查詢 ——…, 剔除已過期的欠帳(真空帳戶的逃生路)。deadline 隨 monotonic clock 單調遞增 → 隊首必為最早到期者,popleft-while… (+2 more)

### Community 74 - "Capital Com"
Cohesion: 0.10
Nodes (3): CapitalCom, Protocol, 群益 COM 封裝。CapitalCom 是介面;SkcomCapitalCom 是真實 comtypes 實作。…

### Community 75 - "Server Futures"
Cohesion: 0.11
Nodes (7): FuturesEngine, pending 商品每 `resub_interval_secs` 重訂一次,成功即出列;全清空即結束。 只有失敗品才會起這個 task ——…, 全量快照。**`seq` 是廣播游標,不是內容版本**(coalesce 後兩者不再同步): `products` 每則 quote 就即時更新,`seq`…, HOT → 實際契約月份 YYYYMM;未解析/未知商品 → None(送單層拒單,不猜月份)。, 當日 1K 分鐘序列 passthrough(江波圖台指腿回補;index-river-chart SC-4)。 阻塞呼叫,呼叫端負責丟…, executor thread:訂 leaf 後把結果經 call_soon_threadsafe 回寫集合 (集合只在 loop thread…, TC4 重連對帳:`_check_stale` 重掛失敗品靜默出集合(僅 warning)、迴圈中途 拋錯時尾段 symbol 蒸發 —— 掉訂品不進…

### Community 76 - "Fe Components"
Cohesion: 0.11
Nodes (18): Btn(), fmt(), FUT_LABELS, FutKey, MarketPane(), selectFut(), selectKey(), NAMES (+10 more)

### Community 77 - "Backtest Fade"
Cohesion: 0.22
Nodes (18): ArmParamSet, ArmSpec, _build_delta_flip_arm(), _build_fixed_time_arm(), _build_inner_flip_arm(), _build_pin_bar_arm(), _build_pullback_arm(), _build_vol_exhaust_arm() (+10 more)

### Community 78 - "Live Handover"
Cohesion: 0.15
Nodes (10): _PosState, 回補灌入:按 (symbol, precise_time, seq) 排序;重建 cum(Σqty)寫 _last_cum。 回傳 rebuilt…, 回傳「這筆 tick 有沒有改到 snapshot 內容」——foreign / stale / spot 同價 / spot 0 價皆 False。…, HandoverBuffer, 回補↔live 交接協定(design.md §2.3 DR-1/DR-11):訂閱先行 buffer → 回補灌入 → flush。, 交接期 live tick 暫存;獨立於穩態 queue(DR-11)。append 回 False = 溢出。, 交接步驟 3-4:回補排序灌入(重建 cum)→ flush buffer(只放行 cum 較大者)。 溢出處理(重跑協定)由呼叫端 engine…, run_handover() (+2 more)

### Community 79 - "Live Corr"
Cohesion: 0.13
Nodes (12): log_return(), mid_from_book(), 相關係數引擎的純函數層:中價與對數報酬(design §1.2 / SC-2)。 秒級取樣一律用 **Bid/Ask 中價**,不用成交價 ——…, 最佳買賣中價(毫點整數);任一側無報價 → None。 單邊缺檔不用另一側硬湊 —— 單邊價不是市場對該商品的共識定價,拿來算報酬會製造 假波動。整除的…, 對數報酬 ln(cur/prev);任一端非正 → None(取 log 前的定義域防護)。, CorrState, SessionKey, 滾動相關係數狀態機(零 IO;SC-1/3/4;design §5)。 每秒一筆取樣 → 多窗滾動 Pearson。設計要點: -… (+4 more)

### Community 80 - "Docs Harness Hooks"
Cohesion: 0.19
Nodes (19): CompletedProcess, run_hook(), test_bash_bulk_git_add_blocked(), test_bash_cat_env_blocked(), test_bash_cat_source_allowed(), test_bash_curl_pipe_bash_blocked(), test_bash_rm_rf_home_blocked(), test_bash_rm_rf_node_modules_allowed() (+11 more)

### Community 81 - "Fe Lib"
Cohesion: 0.14
Nodes (12): assignToGroup(), detachFromGroups(), Group, groupForCode(), insertAt(), moveToGroup(), reinsertIntoCodes(), reorderUngrouped() (+4 more)

### Community 82 - "Corr Config"
Cohesion: 0.15
Nodes (16): _BadSparse, CorrConfig, Leg, load_config(), _parse_legs(), _ParsedLegs, NamedTuple, Path (+8 more)

### Community 83 - "Stkfut Map"
Cohesion: 0.18
Nodes (18): _contract_unit(), _fetch_html(), load_map(), _parse_rows(), parse_taifex_html(), _product_index(), Path, 股號 ↔ 個股期產品碼對映(design v4.1 §2.6;v2 = stkfut-contracts SC-2)。 個股期不在 TC4… (+10 more)

### Community 84 - "Fe Lib"
Cohesion: 0.16
Nodes (17): buildLegGeometry(), buildOverlayGeometry(), hhmm(), LegGeometry, LegPoint, offsetAtX(), OverlayEntry, OverlayGeometry (+9 more)

### Community 85 - "Fe Lib"
Cohesion: 0.15
Nodes (12): connectWithRetry(), isPing(), WS_BACKOFF_CAP_MS, WS_BACKOFF_START_MS, WS_MIN_UPTIME_MS, WS_SHORT_LIVED_CAP_MS, WS_SILENCE_TIMEOUT_MS, WS_WATCHDOG_JITTER_MS (+4 more)

### Community 86 - "Server Index"
Cohesion: 0.15
Nodes (5): IndexEngine, **worker thread**:訂閱 + 回補當日 1K,只回傳抓到的分鐘,**不寫**任何共享狀態 (只讀 `_loop` /…, 櫃買當日分 bar + 起始時刻(`HH:MM`;無資料 → `None`)。 `t` 必須是 `"YYYY-MM-DD HH:MM"` —— 前端…, 加權 minutes 最後一鍵是否落後牆鐘超過 `_LAG_HEAL_MIN` 分(僅 heal 窗內呼叫)。 牆鐘封頂…, 盤中台指現價長時間為 None → 節流 warning(index-board review P1-1)。 現價源自 2026-07-30 起收斂為…

### Community 87 - "Ref Types React"
Cohesion: 0.12
Nodes (16): name, private, type, version, eslint, eslint-plugin-react-you-might-not-need-an-effect, globals, jsdom (+8 more)

### Community 88 - "Fe Lib"
Cohesion: 0.17
Nodes (16): ALLDAY_GAP, ALLDAY_HOUR_TICKS, ALLDAY_LEN, ALLDAY_SEGMENTS, ALLDAY_TICKS, ALLDAY_WINDOW, alldayHhmmOf(), alldayIndexOf() (+8 more)

### Community 89 - "Fe Lib"
Cohesion: 0.22
Nodes (16): bestLimit(), buildLadder(), fmtTickPrice(), isMarketLevel(), Ladder, LadderInput, LadderRow, limitOnly() (+8 more)

### Community 90 - "Server Engine"
Cohesion: 0.18
Nodes (6): SeriesInfo, Protocol, QuoteSource, 行情來源抽象;TC4 實作在 copycat.live.tc4,測試注入 fake。, FakeTxoSource, 全部 no-op 的 TXO source:lifespan 需要一個 `QuoteSource`,verify 模式與六組 route 測試(corr /…

### Community 91 - "Server Stock"
Cohesion: 0.12
Nodes (6): AbstractSet, date, datetime, 個股行情來源抽象;TC4 實作在 copycat.live.stock_source,測試注入 fake。 `code` 一律是 **instrument…, 整批預熱:對每檔先送 SubHistory 讓 TC4 平行備資料,之後逐檔 `backfill` 收割 (perf/opening-backfill-…, StockSource

### Community 92 - "Server Stock"
Cohesion: 0.12
Nodes (8): 現貨那把尺的「當下在試撮**時間窗**內」——**純窗**,不看交易日曆。 per-instrument 判定走…, 單工 worker;出隊時把佇列裡**當下全部**的 job 一次取出,整批先交 source `prepare_backfill`(對每檔送…, 窗翻轉要補推的收件人:自選全碼 + **現貨**主圖碼(D3)。 主圖也收 `watchlist_quote` 是既有先例(`_handle_no_data`…, 側欄節流:1s 合併一則(design §2.4)+ 試撮窗翻轉補推(D3)。, 現貨試撮旗標 = 交易日曆 AND 時間窗(D4')——`_flush_watchlist_loop` 的翻轉判準。 日曆來源是 engine 既有的…, 階段一:換日窗(同步、即返)+ 全量重掛(背景 to_thread,CR3);不清狀態; generation bump 作廢 in-flight 回補。…, 全量重掛(UNSUB→SUB 冪等,新日窗);ZMQ REQ 全程 to_thread,不佔 event loop。 `new_date` 非…, _spot_trial_window_now()

### Community 93 - "Frontend Package Devdependencies"
Cohesion: 0.12
Nodes (17): devDependencies, eslint, eslint-plugin-react-you-might-not-need-an-effect, globals, jsdom, react-doctor, tailwindcss, @tailwindcss/vite (+9 more)

### Community 94 - "Backtest Features"
Cohesion: 0.19
Nodes (12): BacktestConfig, 回測全參數(版本化;configs/*.json 覆寫)— 樣式同 strategy_config(spec §8/design D5-D6).…, sim_config_hash(), _ignition_first(), 觸發時點特徵(neigui extract_trigger_features.py 同源移植;characterization 錨點 SC-2)…, 位階特徵族(全部以 T-1 為基準,無 lookahead)., 啟動第一根:近 lookback 日未觸 +θ、近 5 日盤整、近 N 日無漲停(全部 T-1 止)., structural_features() (+4 more)

### Community 95 - "Server Breadth"
Cohesion: 0.12
Nodes (10): compute_prev_streaks(), `day_sets` = 連續交易日的漲停集合,**新 → 舊**排序(day_sets[0] = 最近可得 交易日)。回傳 {stock_id: 截至…, _is_bucket_row(), Path, restore 本地落檔(序列 + streak)+ 起 poll task。**零網路 IO** —— 首輪 fetch 在 task 上跑,FinMind…, 單次嘗試:自 `today − 1` 往回掃 → 逐日收成漲停集合 → 交集遞進 → 落檔。 `today` **進場取樣一次**:掃描起點 / 檔名 /…, tmp + `os.replace` 原子寫;失敗只降級(記憶體成果照在,重啟才會重算)。, 讀 `streaks-<today>.json`;**命中即連 `_streak_armed_day` 一併設為 today**。… (+2 more)

### Community 96 - "Stock Names"
Cohesion: 0.18
Nodes (13): load_names(), parse_isin_html_with_stats(), ParseStats, Path, 全市場股票代號 ↔ 名稱表(個股搜尋提示列用;change-spec stock-ui-round4 🟢-6)。 資料源 = 證交所 ISIN…, 讀名稱表。**任何讀取/格式問題都回 `{}`**(`/api/stock/names` 承諾不 500)。, 抓 ISIN 頁重生名稱表;守門任一條不成立 → 拋 `ValueError` 保留舊檔。, 逐段筆數與剔除計數 —— refresh 要 log 出來,格式漂移才看得見(禁止靜默截斷)。 (+5 more)

### Community 97 - "Docs Harness Hooks"
Cohesion: 0.23
Nodes (15): CompletedProcess, run_hook(), test_hookspath_get_allowed(), test_hookspath_readonly_in_compound_command_allowed(), test_hookspath_readonly_query_allowed(), test_hookspath_set_equals_form_blocked(), test_hookspath_set_value_blocked(), test_hookspath_unset_all_blocked() (+7 more)

### Community 98 - "Fe Components"
Cohesion: 0.17
Nodes (11): blankForm(), FormState, KIND_LABEL, LEVEL_LABEL, num(), Props, ruleSummary(), SignalRulesDialog() (+3 more)

### Community 99 - "Fe Lib"
Cohesion: 0.16
Nodes (13): aggregateBars(), Bar, buildCandleGeometry(), Candle, CandleGeometry, DeltaVolBar, shiftDate(), Size (+5 more)

### Community 100 - "Data Backfill"
Cohesion: 0.22
Nodes (14): aggregate_brokers(), brokers_path(), _event_targets(), _fetch_report(), _fetch_retry(), FetchFn, Path, FinMind 分點日報回補:taiwan_stock_trading_daily_report(per stock-day 專用 endpoint).… (+6 more)

### Community 101 - "Live Futures"
Cohesion: 0.17
Nodes (7): futures_symbol(), FuturesQuoteSource, Any, 補訂實際月份 leaf 契約(TC.F.TWF.<p>.<YYYYMM>)。 HOT 與 TXO runtime 的 spot 訂閱同 symbol…, 當日 1K → [(台北 minute_end, close 毫點)]。 台指的回補**必須從這條 session 發** ——…, SUB socket 一則原始電文 → REALTIME Quote dict 分派(listener 與測試共用)。, 產品碼 → TC4 期貨樹熱門月 symbol(台指期產品碼 = TXF,非 FITX;07-20 實證)。

### Community 102 - "Server Breadth"
Cohesion: 0.20
Nodes (14): fetch_daily_prices(), fetch_day_trading(), fetch_disposition(), fetch_snapshot(), fetch_stock_info(), _get_rows(), _date, FinMind 全市場取數層(market-overview R2 design §4)— 阻塞,呼叫端丟 to_thread。 五個取數點,錯誤分類與… (+6 more)

### Community 103 - "Server Discord"
Cohesion: 0.19
Nodes (13): _channel_id(), create_bot(), _group_ac(), _dotenv_values(), _getenv(), group_choices(), _import_discord(), Discord bot:`/watch` slash 指令 + 訊號推送出口(design §5 — SC-8)。 **模組層刻意不 import… (+5 more)

### Community 104 - "Server Discord"
Cohesion: 0.19
Nodes (14): _group_remove(), _remove(), _ungroup(), action(), handle_group_remove(), handle_remove(), action(), handle_ungroup() (+6 more)

### Community 105 - "Docs Harness Hooks"
Cohesion: 0.27
Nodes (14): find_ancestor(), find_python_tool(), find_repo_root(), format_js_ts(), format_python(), main(), Path, Prefer venv-pinned tool, fall back to PATH. (+6 more)

### Community 106 - "Fe Components"
Cohesion: 0.17
Nodes (14): BODY_CLASS, CandleChart(), ChartStatic, DIMS, EMPTY_LINE, PRICE_TAG, Props, readoutFields() (+6 more)

### Community 107 - "Fe Lib"
Cohesion: 0.16
Nodes (10): FEE_BASE, FEE_DISCOUNT_DEFAULT, feeRate(), isAvgSource(), positionEcon, PositionEconInput, px(), SELL_TAX (+2 more)

### Community 108 - "Spikes Txo Chain"
Cohesion: 0.17
Nodes (9): QuoteAPI, main(), QUERYINSTRUMENTINFO 節點展開:找指數分類節點(一次性)., main(), 指數 symbol 探測(一次性,收工必 Disconnect):加權/櫃買在 TC4 symbol 樹的代碼. 背景:股票類…, main(), poll_history(), SC-1 spike:TXO 期權鏈探測(一次性,收工必 Disconnect)。 驗證:(a) 序列/合約清單可查(最近序列 ≥ 30 檔斷言);(b)… (+1 more)

### Community 109 - "Server Index"
Cohesion: 0.19
Nodes (10): in_futures_session(), in_watch_window_now(), now_time(), date, time, 指數引擎(index-board SC-4;design v4). 三檔:加權(TC4 IX0001 push + 1K 回補)、櫃買(MIS 5s…, 台指期交易時段(跨午夜的夜盤以「或」拆兩段判)。, watchdog 判定窗;end-exclusive(13:25:00 起即試撮窗凍結 — review F4 界義)。 (+2 more)

### Community 110 - "Server Stkfut"
Cohesion: 0.19
Nodes (8): 個股期合約目錄:當日 in-memory cache + 單飛 + 白名單查詢(stkfut-contracts SC-1)。…, 本機日界(= 台北;部署綁本機,同 overlay / bars 的既有慣例)。, `fetch` = 同步的 TC4 查詢(`TC4QuoteSource.list_stock_futures`),丟 to_thread 跑。, boot 尾段預熱(code review A3):把冷查詢移出盤中熱路徑。 冷 cache 的第一次 `QUERYALLINSTRUMENT(Fut2)`…, 股號 → `{name, std, mini}`;無期貨 → None。查詢失敗原樣拋(route 轉 502)。, `?contract=` 白名單:prod 屬該股號(標準或小型)且 ym 在該產品的月份清單內。 沒有這道閘,使用者可以把…, StkfutCatalog, _today()

### Community 111 - "Fe Lib"
Cohesion: 0.15
Nodes (9): edgeMilli(), FUT_TICK_MILLI, FutClosePos, FutCloseQuote, FutDepthLevel, FutLadderRow, futMarketEdgeMilli(), FutOrderSource (+1 more)

### Community 112 - "Frontend Tsconfig Node"
Cohesion: 0.14
Nodes (13): compilerOptions, allowImportingTsExtensions, isolatedModules, lib, module, moduleDetection, moduleResolution, noEmit (+5 more)

### Community 113 - "Spikes Capital Login"
Cohesion: 0.16
Nodes (3): load_env(), main(), mask()

### Community 114 - "Data Import"
Cohesion: 0.31
Nodes (12): _build_events(), _import_daily(), _import_k1(), _import_limitup(), _import_near_miss(), _import_tick_auction(), Path, neigui five-tigers 種子資料 → copycat 標準格式(一次性匯入). 來源唯讀;TC4 原始格式陷阱(UTC… (+4 more)

### Community 115 - "Live Models"
Cohesion: 0.18
Nodes (12): parse_history_tick(), parse_option_symbol(), parse_realtime(), tick / 合約資料模型與 TC4 訊息對映(欄位事實:docs/research/2026-07-18-txo-chain-probe.md)., TC.O.TWF.<prod>.<expiry>.<C|P>.<strike> → (prod, expiry, cp, strike_pts)。, 歷史 TICKS row → Tick;缺 price/qty/PreciseTime → None。cum_volume 恆 None(spike 實測)。, REALTIME Quote dict → Tick(DR-4 隔離層);無成交(qty 空/0)→ None。…, _to_int() (+4 more)

### Community 116 - "Server Overlay"
Cohesion: 0.18
Nodes (9): stock_overlay(), build_overlay(), compute_cdp(), compute_ma(), OverlayCache, 江波圖疊線(CDP / MA)計算與 cache — stock-ui-upgrade SC-4. 「已完成 bar」規則(design R1):輸入先剔除…, 毫元整數 CDP 五值;cdp 為 round-half-up(impl-spec R1:(x+2)//4,無 float)。, bars(升冪)→ overlay response;剔除今日 partial 後空 → 全 null。 (+1 more)

### Community 117 - "Server Index"
Cohesion: 0.19
Nodes (4): **event loop thread**:把回補的分鐘併進狀態;回「本次是否帶來新分鐘鍵」。 判準是鍵集合差而非值(review…, 作廢在飛的 retry:世代 +1 = 上一發(含它排在 executor 裡還沒起跑的工作項)整組 作廢(review SP5);cancel 讓已…, TC4 重連後的重掛 + 重抓(loop 執行緒)—— **沿用當前自癒 variant**(review A6 / §3.4)。 改動前走…, 換日:三份新日分鐘按**可信度由低到高**疊起來(N107 / review SP2(b))。 `_pending_backfill`(pending 期間…

### Community 118 - "Fe Hooks"
Cohesion: 0.17
Nodes (9): CDP_LEVELS, fetchRules(), MAX_RULES, RULE_KINDS, RuleDraft, RuleKind, RULES_KEY, SignalRule (+1 more)

### Community 119 - "Fe Lib"
Cohesion: 0.24
Nodes (11): areaPaths(), buildScales(), curvePath(), CurvePoint, fmt(), invertX(), linePath(), ScaleBox (+3 more)

### Community 120 - "Fe Lib"
Cohesion: 0.17
Nodes (6): isEtfUnderlying(), isOrderBlocked(), StkfutContracts, StkfutLeg, StkfutSelection, STOCK_FUTURE_UNITS

### Community 121 - "Spikes Backfill Phaseb"
Cohesion: 0.26
Nodes (11): _harvest(), main(), Path, Phase B 前置 TC4 1K 批次回補(next-time 2026-07-07:對照組 T+1 + 7-8% 帶宇宙)。 一次性…, 對照組(source==control)缺 T+1 1K 的 (stock_id, t1_date)。, 7-8% 帶宇宙:回傳 (帶內總 stock-day, 缺 T 日 1K 清單)。, 收割單一 stock-day 1K(已先 SubHistory;等待輪詢比舊逐檔模式短)。, run() (+3 more)

### Community 122 - "Capital Client"
Cohesion: 0.20
Nodes (7): BaseException, 在 event loop 上 resolve 寫入 future。逾時側(wait_for)可能已 cancel, done 的 future 再 set…, OnDisconnect:回報主機斷線 → degraded(送單通道獨立可用), 不自動重連、不 clear store(重播 backlog 前必須先…, 登入 + 憑證 + 連回報 + 帳號發現。成功回 True(ok/degraded);失敗 False(error)。, 執行緒結束時佇列殘留的命令沒人消化:future 必須 fail, 否則 status 檢查通過後才入佇列的寫入請求會永久懸掛。, _settle(), Future

### Community 123 - "Data Backfill"
Cohesion: 0.30
Nodes (10): _date_to_utc_window(), _fetch_1k(), _find_missing(), _needs_refetch(), Path, TC4 歷史 1K 回補:讀 events.csv 找缺 T+1 1K 的 stock-day,逐筆向 TC4 拉取., 回傳與種子匯入同格式的 Bar1K list(parse_raw_bar 同源,含零量試撮根)., run_backfill_tc4() (+2 more)

### Community 124 - "Notify Rationale"
Cohesion: 0.20
Nodes (10): _build_embed(), notify_discord(), Discord webhook 發送層(泛用訊息;訊號內容由 caller 決定). 介面形狀沿 treading-king discord_notifier…, 讀取順序:env → repo root .env → None(lazy cache;測試 reset module 屬性)., 送一則 embed 訊息到 Discord webhook;URL 未設 no-op、失敗不拋例外. 回傳 True = Discord…, resolve_webhook_url(), _make_signals(), load_signals_config() (+2 more)

### Community 125 - "Server Corr"
Cohesion: 0.17
Nodes (5): CorrSource, _LegState, Protocol, SessionKey, 行情源抽象;TC4 實作在 copycat.live.corr_source,測試注入 fake。

### Community 126 - "Server Discord"
Cohesion: 0.17
Nodes (8): Bot, _log_login_failure(), Task, 背景登入 task 的結束回呼(CC-6):非取消例外 = 登入失敗,當下就要留下真因。, discord client 的薄殼:起停 + guild 限定指令同步 + 訊號頻道推送。 型別全 `Any`:discord 是 lazy…, 背景登入;登入本身可能失敗(token 錯 / 斷網),失敗只影響 Discord 這條路。 `add_done_callback`…, 取訊號頻道 → 對它的 guild 註冊並 sync 指令(guild 限定 = 即時生效且僅該 guild)。 頻道未設或取不到時只降級(不…, 訊號推送出口(hub 的 discord sender);未 ready / 送失敗回 False 讓 hub 走 fallback。

### Community 127 - "Server Discord"
Cohesion: 0.17
Nodes (5): _add(), handle_add(), `WatchlistService` 的結構子集(測試注入 fake)。 寫入類方法一律回 `(watchlist, changed)`:handler 要靠…, SC-5:名稱查不到只**提醒**不擋 —— 靜態名稱表落後於新上市/改名是常態, 擋下去會讓合法股號加不進來,而使用者最需要的正是「剛上市那檔」。, WatchlistServiceLike

### Community 128 - "Server Futures"
Cohesion: 0.26
Nodes (10): _bar_minute(), _last_trade_at(), datetime, FuturesEngine:TXF/MXF/TMF HOT 五檔/成交狀態機 + HOT→實際契約解析(SC-8;design §10)。 - per-…, 期貨 1K 落後 / 中段缺格 WARNING(L262,2026-08-28)。固定前綴供 grep: `期貨 1K 落後` / `期貨 1K…, 1K bar 的 `t`("YYYY-MM-DD HH:MM" 台北)→ datetime;形狀不對回 None(健康檢查跳過,不炸 route)。, `_ProductState.date`("YYYY-MM-DD")+ `t`("HH:MM:SS.fff")→ 該成交所屬 1K bar 的**終點標記**…, (a, b] 之間落在 domain 段內(終點標記口徑 HHMM ∈ [start, end])的分鐘數;b ≤ a → 0。 逐分走(bar 分鐘級,一天… (+2 more)

### Community 129 - "Server Main"
Cohesion: 0.21
Nodes (5): Any, Exception, TextIO, 把一路 stdout/stderr 同時寫 console 與 log 檔。 檔案每筆 write 即 flush:log 的價值在 crash…, _Tee

### Community 130 - "Fe Components"
Cohesion: 0.23
Nodes (8): markMap(), PositionRow, positionRows(), PriceLadder(), clickPrice(), marketOrder(), showHint(), Props

### Community 131 - "Fe Hooks"
Cohesion: 0.21
Nodes (10): BarsPayload, barsPollInterval(), BarsStatus, ChartMode, fetchBars(), MINUTE_DAYS, MinuteMode, STATUSES (+2 more)

### Community 132 - "Fe Lib"
Cohesion: 0.17
Nodes (6): CANDLE_CHROME_Y, CANDLE_INSET_X, INTRADAY_CHROME_Y, PANE_FRAMES, PaneBox, PaneFrame

### Community 133 - "Fe Lib"
Cohesion: 0.20
Nodes (7): coerceMode(), DAILY_MODES, defaultMode(), isModeAvailable(), MARKET_MODES, MarketKey, MarketMode

### Community 134 - "Server Audit"
Cohesion: 0.25
Nodes (9): append_audit(), audit_path(), AuditWriteError, Any, date, Exception, Path, 下單審計 JSONL(§7 閘三):append-only、跨執行緒序列化、失敗拋 AuditWriteError。 寫者 = 群益… (+1 more)

### Community 135 - "Server Build"
Cohesion: 0.24
Nodes (8): BuildInfo, capture(), _git(), datetime, 執行中 server 的建置身分(git sha + 啟動時刻)。 **存在理由**(docs/next-time.md 2026-07-29…, `git_dirty` 三態:True/False = 問到了;None = 問不到(git 不可得)。, 跑一條 git,任何取不到的情況一律 `None`。 catch 的處理邏輯就是降級本身(鐵則 E:catch 後要有具體處理)—— 呼叫端靠 `None`…, 在 lifespan 啟動時呼叫一次;之後整個行程回同一份。 刻意**不**每次請求重算:sha 是「這個行程跑的是哪一版 code」,啟動後才 commit…

### Community 136 - "Server Discord"
Cohesion: 0.24
Nodes (6): _Followup, Interaction, Any, Protocol, duck-typed slash interaction:handler 只用得到這兩條路。, _Response

### Community 137 - "Server Futures"
Cohesion: 0.18
Nodes (4): FuturesSource, Protocol, 期貨行情來源抽象;TC4 實作在 copycat.live.futures_source,測試注入 fake。, executor thread:關機中早退,縮小「close 後 source 再被呼叫」的窗。 cancel 正 await `to_thread` 的…

### Community 138 - "Fe Components"
Cohesion: 0.24
Nodes (7): EnergyBar(), HeadCells(), netTone(), QUOTE_COLUMNS, SideCellCtx, SideCells(), sideColumns()

### Community 139 - "Fe Hooks"
Cohesion: 0.29
Nodes (9): D1_SNAPSHOT, D_FINAL_SNAPSHOT, D_SNAPSHOT, firstCallsAfterMidnight(), partialLastAt(), pastDailyFinal(), pastMidnight(), snapshotAt() (+1 more)

### Community 140 - "Fe Hooks"
Cohesion: 0.31
Nodes (10): ChartToggles, DEFAULTS, getSnapshot(), listeners, load(), persist(), setToggle(), Stored (+2 more)

### Community 141 - "Fe Lib"
Cohesion: 0.22
Nodes (9): buildOverlayGeometry(), IndexOverlayGeometry, OutOfDomainLevel, OverlayLinePts, Size, sortedEntries(), toX(), X_END_MIN (+1 more)

### Community 142 - "Fe Lib"
Cohesion: 0.24
Nodes (7): bus, sameList(), setTickView(), subscribe(), subscribeTicks(), subscribeTickView(), view

### Community 143 - "Fe Lib"
Cohesion: 0.25
Nodes (7): holidaySet, isoLocalDate(), isTradingDay(), isTradingDayIso(), isWeekendIso(), nextTradingDayIso(), shiftIso()

### Community 144 - "Fe Lib"
Cohesion: 0.25
Nodes (7): inFuturesAllDayHours(), msUntilFuturesAllDayOpen(), msUntilFuturesTradingOpen(), msUntilNextOpen(), msUntilTradingOpen(), OpenAt, prevDay()

### Community 145 - "Backtest Simulate"
Cohesion: 0.29
Nodes (8): enumerate_stop_combos(), T 日進場模擬器(design §3 D6/D7/D9 + §4)— 零 IO,悲觀成交. 時序語意: - 進場 = 觸發 bar close +…, 單族(S1/S2/S3/S4)+ S1×S2 疊加,× t1300 兩臂;固定順序(determinism)., _round_trip_cost(), simulate_sample(), _pnl(), StopCombo, TradeOutcome

### Community 146 - "Server Index"
Cohesion: 0.20
Nodes (6): _is_blank_time(), _millipt(), minute_key(), TC4 quote「沒給時間欄位」的形狀:`''` / `'0'` / `'000000'`(全零或空)。 只認全零 —— 真值 `'000000'`(UTC…, 日曆誤標偵測(L3,2026-08-28):有日曆、日曆說今天休市、牆鐘已過 09:00,卻收到 ≥ `_HOLIDAY_PUSH_WARN_PRICES`…, 時刻 → 分鐘鍵(1K 終點標記 = floor+1;IR3/IR4/F5)。utc=True 先 +8。

### Community 147 - "Server Ws"
Cohesion: 0.24
Nodes (4): 新 client 的訊息流;`seed` 逐則在**呼叫當下同步**入該 client 的佇列。 種子**不可借用 `publish`**(那會打到所有…, per-client 有界 queue fanout;`publish` 必須在 event loop 上呼叫。 丟包**可觀測**(mod/group-…, 節流窗到期 → 結算「上一窗共丟幾筆」(pr-187 review #8 收修 spec F-01)。 掛在 `publish()`…, WsBroadcaster

### Community 148 - "Fe Components"
Cohesion: 0.31
Nodes (9): FuturesLadder(), cancelAll(), cancelLot(), clickPrice(), confirmClose(), marketOrder(), showHint(), Props (+1 more)

### Community 149 - "Fe Components"
Cohesion: 0.29
Nodes (8): initialTab(), panelId(), RailContext, RailTab, RightRail, stkfutClosePriceOf(), tabId(), TABS

### Community 150 - "Fe Components"
Cohesion: 0.33
Nodes (8): chipClass(), hhmm(), Props, railTitle(), ruleTitle(), segmentTitle(), SignalRail(), toneOf()

### Community 151 - "Fe Lib"
Cohesion: 0.33
Nodes (9): clampCount(), clampViewport(), initialViewport(), MAX_VISIBLE, MIN_BARS, onTotalChange(), panBy(), Viewport (+1 more)

### Community 152 - "Fe Lib"
Cohesion: 0.22
Nodes (6): CANDLE_MARK, ExtremeDir, ExtremeMarkStyle, INTRADAY_MARK, markCenterX(), markOuterRadius()

### Community 153 - "Fe Lib"
Cohesion: 0.22
Nodes (8): ARM_IDLE_MS, ARM_WS_TITLE, ArmEvent, ArmState, initialArm(), LOCK_TITLE, LOCK_WS_TITLE, reduceArm()

### Community 154 - "Fe Lib"
Cohesion: 0.22
Nodes (4): fmt(), fmtIndexPts(), nf, nfPts

### Community 155 - "Fe Lib"
Cohesion: 0.22
Nodes (9): buildIndexOverlayLines(), INDEX_OVERLAY_LABEL, IndexOverlayKey, IndexOverlayLine, IndexOverlaySeries, OVERLAY_KEYS, Row, SORTED_ROWS (+1 more)

### Community 156 - "Fe Lib"
Cohesion: 0.20
Nodes (8): AssertEqual, Expect, KIND_TRAITS, _KindDomainsMatch, kindTraits, TRADE_KINDS, TradeKind, UNKNOWN_KIND_TRAITS

### Community 157 - "Spikes Nk225 Leg"
Cohesion: 0.40
Nodes (9): _collect_ids(), main(), rt(), _port_in_use(), probe_1k(), 日經腿前置探測(一次性,收工必 Disconnect):R5「相關係數加小日經第七腿」spec 第一步。 四件事: 1. QUERYALLINSTRUMENT…, 遞迴收 EXGID 節點 → {EXGID: {"CHT":..., "instrument_ids": [...]}}。, req() (+1 more)

### Community 158 - "Server Index"
Cohesion: 0.22
Nodes (3): IndexSource, Protocol, 指數行情來源(StockQuoteSource 相容子集);測試注入 fake。

### Community 159 - "Server Mis"
Cohesion: 0.28
Nodes (8): fetch_otc_snapshot(), _millipt(), OtcSnap, Any, TypedDict, TPEx 櫃買指數 MIS 快照(index-board SC-4). MIS 為非契約公開端點(design Known Risk 1):失敗一律 None…, 價格欄毫點 int;time 為 HHMMSS 字串(台北時刻)。, 單次快照;任何失敗(網路/格式/暫停計算)→ None(caller 保留前值)。

### Community 160 - "Fe Components"
Cohesion: 0.25
Nodes (6): CapitalOrdersList(), FUT_MARKETS, isFutMarket(), OrderRow(), OrderRowProps, PendingAction

### Community 161 - "Fe Components"
Cohesion: 0.25
Nodes (6): EMPTY_CODES, GRID_TOGGLES, gridShape(), GroupCard, GroupGridView(), Props

### Community 162 - "Fe Components"
Cohesion: 0.28
Nodes (5): currentPermission(), Props, StockPage(), requestNotif(), VIEW_LABELS

### Community 163 - "Fe Components"
Cohesion: 0.31
Nodes (6): Props, rejectIfUnchanged(), WatchlistManagerDialog(), groupRow(), submitAddGroup(), submitRename()

### Community 164 - "Fe Hooks"
Cohesion: 0.28
Nodes (8): BuildDrift, DriftMode, getJson(), HEALTH_POLL_MS, HttpError, ServerBuild, useBuildDrift(), useServerBuild()

### Community 165 - "Fe Hooks"
Cohesion: 0.25
Nodes (8): PendingBook, PendingTrial, stateUrl(), StkfutQuote, StockStreamState, useStockStream(), WatchlistQuote, WsMsg

### Community 166 - "Fe Lib"
Cohesion: 0.36
Nodes (8): DiscountState, listeners, loadDiscount(), persistDiscount(), readFeeDiscount(), subscribe(), useFeeDiscount(), useFeeDiscountField()

### Community 167 - "Fe Lib"
Cohesion: 0.25
Nodes (6): FUT_CHART_MODES, FutChartMode, initialFutChartMode(), isFutChartMode(), MINUTE_STEPS, MinuteMode

### Community 168 - "Fe Lib"
Cohesion: 0.33
Nodes (8): readLocal(), readLocalJson(), removeLocal(), warnedParseKeys, warnRead(), warnRemove(), warnWrite(), writeLocal()

### Community 169 - "Server Shutdown"
Cohesion: 0.32
Nodes (7): close_worst_secs(), 單條 session `close()` **可計段**的最壞耗時上界(秒)—— 關機預算的產生點之一(review A1)。 = 等 `_api_lock`…, lifespan_close_worst_secs(), 關機預算 —— 三個讀者同源(review A1,mod/shutdown-budget)。 讀者: - `run.ps1`:`python -c "from…, lifespan `finally` 反序 close 的最壞耗時(秒)。, `run.ps1` 的 graceful 窗:uvicorn 先等 WS 收攤,再跑 lifespan。整數 —— PowerShell 端以 `[int]`…, run_grace_secs()

### Community 170 - "Server Breadth"
Cohesion: 0.25
Nodes (6): date, 該不該重取這張對照表。三個條件的**順序即語意**: 1. 退避中 → 一律不取(失敗剛發生,再打也是同一個壞上游)。 2. 上次成功不是今天(含冷啟動…, DailyPricesFetch, DispositionFetch, SnapshotFetch, StockInfoFetch

### Community 171 - "Server Stock"
Cohesion: 0.25
Nodes (5): 一輪對帳:快照判準(短鎖)→ 三段重試,每項各自重拿鎖重驗。 **不是整輪一鎖**:TC4 斷線時單檔 SUBQUOTE 要等…, 該主圖檔有個股期對映、但期貨鍵上沒掛它的 owner(= 這一腿沒訂上)。, 段內迭代起點逐輪輪轉(C-1)。 段級 break 只解跨段餓死;固定順序 + 首個失敗就 break,排最前的恆失敗檔會永久 餓死同段後面所有檔(head-…, 常駐迴圈:每輪對帳「該訂而沒訂上的」並補訂。 與 futures/corr 的 pending-resub 不同,這裡的重試項目是**動態集合**(使用者…, _round_robin()

### Community 172 - "Frontend Sha Plugin"
Cohesion: 0.36
Nodes (5): buildShaPlugin(), gitSha(), @tailwindcss/vite, vite, @vitejs/plugin-react

### Community 173 - "Fe Components"
Cohesion: 0.39
Nodes (7): AdvanceDeclineChart(), minuteOf(), netOf(), Plot(), signed(), SIZE, toX()

### Community 174 - "Fe Components"
Cohesion: 0.36
Nodes (6): contractPositions(), Props, StkfutLadder(), clickPrice(), marketOrder(), showHint()

### Community 175 - "Fe Hooks"
Cohesion: 0.29
Nodes (7): IndexSeries, IndexStreamState, toSeries(), TxfQuote, useIndexStream(), WireMsg, WireSeries

### Community 176 - "Fe Hooks"
Cohesion: 0.46
Nodes (7): applyDelta(), lastOf(), mergeLeg(), mergeSnapshot(), resetForSession(), RiverStreamState, useRiver()

### Community 177 - "Fe Hooks"
Cohesion: 0.29
Nodes (7): freshQueue(), queue, QueueState, useWatchlistCommit(), WatchlistCommit, WatchlistCommitOptions, WatchlistTransform

### Community 178 - "Fe Lib"
Cohesion: 0.25
Nodes (7): CARD_CHROME, cardSvgBox, CHART_FRAME, MAIN_RATIO_DEN, MAIN_RATIO_NUM, Size, svgBox

### Community 179 - "Fe Lib"
Cohesion: 0.36
Nodes (7): aggregateLots(), groupUsableFillsBySeq(), LadderLot, limitPriceOf(), UsableFill, ymdOf(), ymdWindow()

### Community 180 - "Fe Lib"
Cohesion: 0.25
Nodes (3): ORDER_STATUS_TEXT, SIDE_TEXT, TRADE_ERROR_TEXT

### Community 181 - "Live Futures"
Cohesion: 0.29
Nodes (5): product_from_symbol(), 推播 Symbol → 產品碼;HOT 形與實際月份形都認得,非期貨樹 → None。, HOT 推播 → 實際契約月份 YYYYMM;解析不到 None(不猜月份)。 候選序(design §10:解析源依實測,先信最結構化的欄位): 1.…, resolve_contract_ym(), 寬限期後,對仍零推播的商品補訂 leaf 契約(每 (product, ym) 只補一次)。 月份借同家族已 resolve 的 ym(TXF/MXF/TMF…

### Community 182 - "Live Stock"
Cohesion: 0.33
Nodes (4): BarsStatus, K 線 bar + 空結果的原因(`tf` = "D" 日 K / "1" 分 K;start/end 含端點)。 range 型而非 days…, 同 `fetch_bars_range`,另回**實際走到的資料源標籤**。 大盤頁的 meta 行要誠實說出這一份 bar 從哪來(index-board…, 加權 K 線歷史 —— **必須從本引擎的 session 問**(review P0-1)。 `IX0001` 的 REALTIME 訂閱與當日 1K…

### Community 183 - "Server Breadth"
Cohesion: 0.24
Nodes (6): max_tick_datetime(), datetime, snapshot rows 的 `date` 欄最大值 → **台北 naive** datetime;無有效值回 None。 `Z` 尾(UTC…, _cancel(), Task, 收攤一條背景 task(poll / streak 同款):cancel 後等它真的結束。

### Community 184 - "Server Signal"
Cohesion: 0.43
Nodes (3): log 用的規則識別:名稱可以改、可以重複,id 才追得回是哪一顆 slot(review A4)。, evaluate 與 fanout 分開接(review A4):兩者的失敗語意完全不同 ——…, _rule_tag()

### Community 185 - "Server Stock"
Cohesion: 0.29
Nodes (4): AbstractEventLoop, 在途計數 −1(worker 的每一條離開路徑都要經過)。 歸零就移除鍵而不是留一個 0:`in` 形式的判斷在別處(測試、日後的程式碼)是 自然寫法,留著…, `_BACKFILL_TIMEOUT_RETRY_SECS` 後重新入列;**同 code 的舊 timer 先取消**。 孤兒 timer 的失效樣態(同…, 一筆回補 job 的完整處置(原 `_backfill_worker` 迴圈本體,逐字搬出)。

### Community 186 - "Server Watchlist"
Cohesion: 0.29
Nodes (4): Path, Protocol, StockEngine 結構子集(測試注入 fake)。, WatchlistEngine

### Community 187 - "Docs Harness Hooks"
Cohesion: 0.38
Nodes (6): detect_bypass(), main(), _normalize(), Strip empty quote pairs that split a flag (e.g. --no""-verify → --no-verify)., Return (matched_pattern, reason) if the command contains a bypass; else None., PreToolUse hook: block git/hook bypass flags (hardened). Triggers on Bash tool…

### Community 188 - "Frontend Package Scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, doctor, lint, preview, test

### Community 189 - "Fe Components"
Cohesion: 0.33
Nodes (5): BasisRow(), fmt(), LEFT_STORES, Props, RIGHT_STORES

### Community 190 - "Fe Components"
Cohesion: 0.29
Nodes (4): ASK_SLOTS, BID_SLOTS, CellProps, Props

### Community 191 - "Fe Components"
Cohesion: 0.38
Nodes (5): emitPriceClick(), lots(), OrderBook(), Props, SideProps

### Community 192 - "Fe Hooks"
Cohesion: 0.33
Nodes (6): BARS_FETCH_TIMEOUT_MS, BARS_SLOW_WARN_MS, fetchFuturesBars(), FUTURES_MINUTE_DAYS, FuturesBarsKey, useFuturesBars()

### Community 193 - "Fe Hooks"
Cohesion: 0.43
Nodes (6): fetchGroupState(), groupPollInterval(), GroupSnapshot, RawState, useGroupSnapshots(), vpFromRecord()

### Community 194 - "Fe Hooks"
Cohesion: 0.33
Nodes (6): BarsMeta, BarsStatus, fetchMarketBars(), MARKET_MINUTE_DAYS, MarketBars, useMarketBars()

### Community 195 - "Fe Hooks"
Cohesion: 0.48
Nodes (6): beepFor(), notifyDesktop(), playBeep(), SignalToast, toGroup(), useSignalAlerts()

### Community 196 - "Fe Hooks"
Cohesion: 0.48
Nodes (5): fetchWatchlist(), toWatchlist(), unionCodes(), useSaveWatchlist(), useStockWatchlist()

### Community 197 - "Fe Lib"
Cohesion: 0.29
Nodes (3): BLOCKED_TEXT, FlashSendCtx, MarketBtnState

### Community 198 - "Fe Lib"
Cohesion: 0.38
Nodes (4): bus, onSignal(), onWsOpen(), subscribe()

### Community 199 - "Fe Lib"
Cohesion: 0.29
Nodes (5): COOLDOWN_DEFAULT, COOLDOWN_MAX, COOLDOWN_MIN, PARAM_FIELDS, ParamField

### Community 201 - "Fe Lib"
Cohesion: 0.29
Nodes (5): Geo, VP_FILL_OPACITY, VP_MAX_W_RATIO, VP_POC_FILL_OPACITY, VpBar

### Community 202 - "Backtest Universe"
Cohesion: 0.47
Nodes (4): _classify(), 樣本宇宙(design §2 universe / D7 limit 分軌)— 分組由 watchlist 輸入,不 hardcode 分點., 可替換分點集合 — 只影響事件標記與報表分組,不進評分邏輯(spec §2)., Watchlist

### Community 203 - "Server Capital"
Cohesion: 0.33
Nodes (4): FastAPI, 掛 capital/futures router + 顯式註冊群益例外映射。 AuditWriteError(500 AUDIT_WRITE_FAILED)與…, register_capital(), _make_handler()

### Community 204 - "Frontend Doctor Config"
Cohesion: 0.33
Nodes (5): rules, react-doctor/effect-needs-cleanup, react-doctor/js-set-map-lookups, react-doctor/no-fetch-in-effect, $schema

### Community 205 - "Frontend Package Dependencies"
Cohesion: 0.33
Nodes (6): dependencies, clsx, react, react-dom, tailwind-merge, @tanstack/react-query

### Community 206 - "Fe Components"
Cohesion: 0.40
Nodes (5): CapitalConfirmDialog(), armContractCheck(), requestCancel(), CapitalConfirmDialogProps, ConfirmRow

### Community 207 - "Fe Components"
Cohesion: 0.40
Nodes (5): ChartReadout(), Props, ReadoutField, ReadoutTone, toneClass()

### Community 208 - "Fe Components"
Cohesion: 0.47
Nodes (5): Cell(), CorrPanel(), Props, toneOf(), windowLabel()

### Community 210 - "Fe Components"
Cohesion: 0.33
Nodes (3): Bucket, BUCKETS, MARKETS

### Community 211 - "Fe Components"
Cohesion: 0.53
Nodes (5): chgPct(), fmt(), IndexBar(), IndexCell(), Props

### Community 212 - "Fe Components"
Cohesion: 0.53
Nodes (5): CenterRequest, isCancelable(), LadderView(), lotText(), Props

### Community 213 - "Fe Hooks"
Cohesion: 0.47
Nodes (5): applyFuturesMsg(), FuturesStreamState, FuturesWsMsg, mergePending(), useFuturesStream()

### Community 214 - "Fe Hooks"
Cohesion: 0.40
Nodes (5): fetchToday(), SignalFeed, TODAY_KEY, TodayPayload, useSignalFeed()

### Community 215 - "Fe Hooks"
Cohesion: 0.53
Nodes (5): getSoundOn(), setSoundOn(), subscribe(), subscribers, useSignalSound()

### Community 216 - "Fe Hooks"
Cohesion: 0.47
Nodes (5): fetchStockNames(), NAMES_MAX_ERROR_CYCLES, NAMES_RETRY_INTERVAL_MS, namesRefetchInterval(), useStockNames()

### Community 217 - "Fe Lib"
Cohesion: 0.47
Nodes (3): clamp(), clampTagX(), clampTagY()

### Community 218 - "Fe Lib"
Cohesion: 0.40
Nodes (4): CLOSE_KIND, closeBodyOf(), KIND_TEXT, kindOf()

### Community 219 - "Fe Lib"
Cohesion: 0.47
Nodes (5): DAILY_FINAL_TIME, DayBarsQuery, dayBarsRefetchInterval(), dayBarsStaleTime(), msUntilDayRollover()

### Community 220 - "Fe Lib"
Cohesion: 0.53
Nodes (5): buildFuturesOverlay(), computeCdp(), computeMa(), EMPTY_OVERLAY, usable()

### Community 222 - "Fe Lib"
Cohesion: 0.53
Nodes (6): buildEnergyBars(), buildIntradayGeometry(), energyFrom(), minuteToX(), plotWidth(), windowedEntries()

### Community 223 - "Fe Lib"
Cohesion: 0.53
Nodes (5): dayMinuteOf(), hhmm(), splitStamp(), txfBarsToSeries(), TxfQuoteInput

### Community 224 - "Spikes River 1K"
Cohesion: 0.53
Nodes (5): main(), probe_history(), 六腿江波圖 Phase 0 probe:海外/台期交各段的 **1K 當日回補支援度**。 為什麼不直接 probe…, SubHistory → 輪詢首頁 → 回 row 數與首末列(不做完整分頁收割,只判支援度)。, req()

### Community 225 - "Data Models"
Cohesion: 0.40
Nodes (5): _num(), parse_raw_bar(), UTC HHMMSS(無前導零)→ 台北分鐘索引(09:01=0 … 13:30=269)., neigui 原始 bar dict(全字串)→ Bar1K。欄位缺漏 raise ValueError., taipei_min()

### Community 226 - "Server Discord"
Cohesion: 0.40
Nodes (5): _groups(), _format_groups(), handle_groups(), action(), 群組**名冊**(SC-1)—— 與 `_format_watchlist` 的差別是這裡列的是群組本身, 所以 0…

### Community 227 - "Server Discord"
Cohesion: 0.40
Nodes (5): _list(), _format_watchlist(), handle_list(), action(), 依群組列出、未分組殿後;空群組不列(列的是股票,不是群組名冊)。

### Community 228 - "Server Futures"
Cohesion: 0.40
Nodes (3): BarsStatus, 期指 K 線歷史 —— **必須從本引擎的 session 問**(同 `fetch_day_1k` 的理由)。 借不到就回空、不 fallback…, BarsStatus

### Community 229 - "Docs Harness Hooks"
Cohesion: 0.50
Nodes (4): detect_violation(), main(), Return (matched_pattern, reason) for any violation, else None., PreToolUse hook: block destructive ops + secrets exposure (customized).…

### Community 230 - "Fe Components"
Cohesion: 0.50
Nodes (3): CapitalPositionsList(), CapitalPositionsListProps, rowKeyOf()

### Community 231 - "Fe Components"
Cohesion: 0.60
Nodes (4): barsKeyOf(), FuturesPage(), Props, todayOf()

### Community 232 - "Fe Hooks"
Cohesion: 0.70
Nodes (4): mergeSnapshot(), upsert(), useBreadth(), WireMsg

### Community 233 - "Fe Lib"
Cohesion: 0.50
Nodes (4): drawableIndexOf(), futuresBarsToAccum(), FuturesLive, Input

### Community 234 - "Fe Lib"
Cohesion: 0.50
Nodes (3): barMinuteOf(), LiveDay, mergeLiveMinuteBars()

### Community 235 - "Fe Lib"
Cohesion: 0.60
Nodes (4): hhmm(), HOUR_TICKS, HourTick, hourTicksOf()

### Community 238 - "Capital Client"
Cohesion: 0.50
Nodes (3): _mask_account(), 帳號遮罩:只露末 4 碼(status route/log 共用語意;帳號本體不得外流)。, GET /api/capital/status 欄位(design §6);disabled 情境由 route 處理(client None)。

### Community 240 - "Server Discord"
Cohesion: 0.50
Nodes (3): _group_add(), handle_group_add(), 保留名**不在此攔** —— 群組名的合法性只有 `stock_watchlist.normalize` 一份定義, handler…

### Community 241 - "Server Discord"
Cohesion: 0.50
Nodes (3): _group_rename(), handle_group_rename(), 只攔 `old`(操作對象):`new` 是保留名時語意是「取的新名不合法」,交 service → normalize →…

### Community 246 - "Fe Components"
Cohesion: 0.83
Nodes (3): priceTone(), TickTape(), volTone()

### Community 248 - "Fe Lib"
Cohesion: 0.67
Nodes (3): ErrorDetail, parseError(), parseErrorDetail()

### Community 253 - "Fe Lib"
Cohesion: 0.83
Nodes (3): pad2(), settlementCountdown(), thirdWednesday()

### Community 257 - "Spikes Capital Typelib"
Cohesion: 0.83
Nodes (3): dump_methods(), dump_struct(), main()

### Community 258 - "Spikes Index Tree"
Cohesion: 0.83
Nodes (3): main(), 指數 symbol 樹探測:QUERYALLINSTRUMENT 各 Type 名試打,dump 找櫃買指數(一次性)., walk_strings()

### Community 259 - "Data Store"
Cohesion: 1.00
Nodes (3): bars_path(), Path, write_bars()

### Community 261 - "Server Engine"
Cohesion: 0.67
Nodes (3): HandoverBusyError, RuntimeError, 交接進行中,`activate` 不可重入(route 層轉 503 HANDOVER_BUSY)。 不複用…

### Community 262 - "Server Futures"
Cohesion: 0.67
Nodes (3): _EngineClosing, Exception, close() 已開始(_loop 已斷)— executor worker 以此早退,不得再碰 source。

### Community 263 - "Server Stock"
Cohesion: 0.67
Nodes (3): _EngineClosing, Exception, 關機中的早退訊號(訂閱重試迴圈內部用)。 刻意**不是** `ConnectionError`:那會被重試段的 except 接住,打出與「TC4 訂閱失敗」…

### Community 272 - "Fe Lib"
Cohesion: 0.67
Nodes (3): bandLabels(), edgePriceLabels(), layoutEdgeLabels()

### Community 273 - "Fe Lib"
Cohesion: 0.67
Nodes (3): buildVwapLabel(), labelWidth(), vwapLabelBox()

### Community 274 - "Fe Lib"
Cohesion: 0.67
Nodes (3): labelCenter(), yieldToObstacles(), yieldToObstaclesBaseline()

## Knowledge Gaps
- **563 isolated node(s):** `$schema`, `react-doctor/effect-needs-cleanup`, `react-doctor/no-fetch-in-effect`, `react-doctor/js-set-map-lookups`, `name` (+558 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2067 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **40 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `Server App Routes` to `Bars Cache & Fetch`, `Server Audit`, `Server Engine`, `Signal Hub Internals`, `Server Futures`, `Capital COM Client`, `Stock Engine Internals`, `Stock Source & Backfill`, `Premarket Screening`, `Trading Calendar`, `Live Stock State`, `Server Ws`, `Server App Corr Routes`, `Stock Watchlist`, `TXO OI Levels`, `Server Index`, `Server Mis`, `Live Session`, `Server Engine`, `Server Verify`, `Server Corr`, `Server Watchlist`, `Server Breadth`, `Server Ws`, `Server Bars`, `Live Trade`, `Server Signal`, `Server Signal`, `Server Capital`, `Server Futures`, `Corr Config`, `Server Index`, `Server Engine`, `Server Stock`, `Stock Names`, `Server Discord`, `Server Stkfut`, `Server Overlay`, `Notify Rationale`, `Server Corr`, `Server Discord`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `CapitalClient` connect `Capital COM Client` to `Capital Contract Mapping`, `Capital Safety`, `Server Audit`, `Capital Balance Parsing`, `Capital Order Store`, `Capital Balance`, `Capital Com`, `Capital Client`, `Capital Client`, `Server App Routes`, `Server App Corr Routes`, `Capital Client`, `Live Trade`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `BreadthEngine` connect `Server Breadth` to `Server Breadth`, `Server Verify`, `Server Breadth`, `Premarket Screening`, `Server App Routes`, `Server Ws`, `Server App Corr Routes`, `Server Breadth`, `Server Breadth`, `Server Breadth`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `create_app()` (e.g. with `BreadthConfig` and `CapitalClient`) actually correct?**
  _`create_app()` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 79 inferred relationships involving `Bar1K` (e.g. with `_entry_idx_for()` and `dispatch_trigger()`) actually correct?**
  _`Bar1K` has 79 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `CapitalClient` (e.g. with `BalanceCollector` and `ProfitRow`) actually correct?**
  _`CapitalClient` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `FadeBacktestConfig` (e.g. with `_cell_param()` and `_entry_idx_for()`) actually correct?**
  _`FadeBacktestConfig` has 52 INFERRED edges - model-reasoned connections that need verification._