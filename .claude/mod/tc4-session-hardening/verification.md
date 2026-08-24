# mod/tc4-session-hardening — verification

分支 `mod/tc4-session-hardening`(自 master 切)。**零 TC4 / 零 ZMQ / 零群益**:全程
fake source,未起任何連 TC4 的程序、未碰 prod 8721。

---

## 1. commits

| # | 類 | 主旨 | 涵蓋 |
|---|---|---|---|
| 1 | 🔴 | `fix(dq4): TC4 共用層連線與訂閱鍵硬化(重連 race / 雙持 key / 舊窗洩漏 / stub 簽名)` | N259 / N050 / N052 / N092 / N051(機制) |
| 2 | 🔴 | `fix(backend): 三引擎的重連對帳與跨執行緒回補合併` | N260 / N261 / N094 |
| 3 | 🔴 | `fix(backend): 關機保證 LOGOUT、自選定序哨兵與鎖粒度、缺年提醒原子化` | N049 / N111 / N112 / N033(安全半) / N051(接線) |
| 4 | chore | `chore(docs): R8 change-spec 與 verification` | artifacts |

SHA(依序):`334c9578` / `445bb849` / `247e1fad` / `ac258c21`(本 session **只 commit,不 push、不建 PR**)。

## 2. 紅態證據(TDD)

| 條 | 紅態 | 指令 / 輸出 |
|---|---|---|
| N259 | `TypeError: ... unexpected keyword argument 'heal_symbol_active'` × 2、race 測 4 條 `assert len(created) == 1` 失敗、`_stop` 早退 `DID NOT RAISE` | `pytest tests/live/test_tc4.py -k "EnsureConnectedAtomic or SpotWindowOffset or HealSymbolGate or FetchSymbolTicksStub"` → **9 failed, 3 passed** |
| N050 | `test_txo_spot_window_differs_from_the_session_window` 失敗(兩把窗相同) | 同上 |
| N051 | `heal_symbol_active` 不存在 → 建構即 TypeError | 同上 |
| N092(tc4) | `assert "疑似凍結 stub" in caplog.text` → caplog 為空 | 同上 |
| N052 | `_rt_keys(reqs) == [("UNSUBQUOTE", …)]` 失敗(換日零 REQ) | `pytest tests/live/test_stock_source.py -k "RolloverUnsubscribesStaleWindow or BackfillStubSignature"` → **3 failed, 3 passed** |
| N092(river) | 反向 mutation(把 `raise` 換成 `pass  # MUTANT`)→ `test_all_rows_dropped_raises_history_timeout` **1 failed**;還原 + `sleep 1`(避同秒 pycache)→ 10 passed | 腳本 `scratchpad/`,已還原,`grep -c MUTANT` = 0 |
| N260 / N261 / N094 | `pytest tests/server/test_futures_engine.py::TestReconnectLeafReconcile tests/server/test_corr_engine.py::TestReconnectResubscribes tests/server/test_index_engine.py::TestBackfillMergesOnEventLoop` → **5 failed, 1 passed**(index 的 `assert eng._twse.minutes == {}` 實得 `{'0901': 43000000}` = orphan retry 真的寫進去了) |
| N111 | mutation(逐項取鎖改回「整段一鎖」)→ `test_second_writer_gets_in_between_codes` **TimeoutError, 1 failed**;還原 → 3 passed | `scratchpad/mutate_n111.py`,已還原,`grep -c MUTANT` = 0 |
| N112 | `AttributeError: module 'copycat.server.stock_engine' has no attribute 'WATCHLIST_BOOT_SEQ'` × 3 | `pytest tests/server/test_stock_engine.py -k "WatchlistPoolLockGranularity or WatchlistBootSentinel"` → **4 failed, 2 passed** |
| N049 | `order` 實得 `['capital', 'stock', 'txo']` → `assert order.index("capital") > order.index("stock")` 失敗 | `pytest tests/server/test_boot_window.py -k capital_com` → **1 failed** |
| N033 | 4 條執行緒各印一行 → `assert len(caplog.records) == 1` 實得 4 | `pytest tests/test_trading_calendar.py -k atomic` → **1 failed** |

**治具自陷各一次(記帳)**:
- N033 首版把 `time.sleep` 放在 `super().__contains__` **之前** → 答案延到別人 add 完才取,
  治具自己把競賽消掉、測試假綠。改成「先算答案再睡」才紅。
- N111 首版讓第二個寫入者在第一發**已進入第二檔的 to_thread 之後**才排隊 → 逐項取鎖
  也救不了(它就是卡在當下那一檔),測試逾時。改成「在第一檔在途時就排隊」才對齊
  「檔與檔之間進得來」這個真正的斷言。

## 3. 完成前 gate(repo root,`.venv\Scripts\python`)

| gate | 結果 |
|---|---|
| `-m pytest -q` | **3010 passed, 1 warning in 174.49s**(master 基準 2976 → +34) |
| `-m ruff check copycat tests` | **All checks passed!** |
| `-m pyright` | **0 errors, 0 warnings, 0 informations** |
| `-m copycat validate` | **42/42 PASS** |
| frontend | **未動 `frontend/`** → 不適用 |

`run.ps1` 另過 PowerShell 語法檢查:
`[System.Management.Automation.Language.Parser]::ParseFile(...)` → `parse OK, no errors`。

## 4. 白名單逐條核對(change-spec §0)

| 白名單 | 結果 |
|---|---|
| `tests/live/test_tc4.py` 全檔(含 `TestApplyVariant` 四把 base 窗變體互異) | 68 passed(含新增 12) |
| `tests/live/test_stock_source.py` / `test_futures_source.py` / `test_corr_source.py` / `test_river_backfill.py` | 全綠 |
| `tests/server/test_futures_engine.py`(`test_reconnect_does_not_clear_leaf_fed` / `test_reconcile_survives_inflight_retry_success` / `test_month_rollover_rearms_leaf_fed_products`) | 全綠 —— `_leaf_fed` 本身未清,只清 `_leaf_done` + `p` |
| `tests/server/test_corr_engine.py` + `test_corr_engine_river.py`(single-flight 互吃 / 逾時重補階梯) | 全綠 |
| `tests/server/test_index_engine.py`(pending 期間 retry 抓新日窗 / `_swap_day` 三層疊法 / 換窗口階梯) | 全綠 —— **合併序一行未動**,只把合併點從 worker 移到 loop |
| `tests/server/test_stock_engine.py`(refcount 池 / seq 定序 / 名單先指派再訂閱 / hub membership / rollover 兩段式) | 全綠(含新增 6) |
| `tests/server/test_watchlist_service.py` / `test_stock_routes.py`(restore-on-startup 三條)/ `test_discord_bot.py` | 全綠 |
| `tests/server/test_boot_window.py` / `test_verify.py` / `test_main_wiring.py` | 全綠 |
| `tests/test_trading_calendar.py` | 39 passed |
| 102 處不帶 `seq` 的 `set_watchlist` 直呼 | 全綠(concrete 方法保留 `WATCHLIST_UNORDERED` 預設) |

**該變清單(事前標,change-spec §1 N092)**:
`tests/live/test_river_backfill.py::test_all_rows_dropped_warns_frozen_stub` →
`test_all_rows_dropped_raises_history_timeout`,`== []` → `pytest.raises(HistoryTimeoutError)`。
另 `tests/server/test_main_wiring.py::test_corr_source_keeps_the_always_on_gate` 只改名為
`..._always_on_session_gate`(斷言 `"heal_active" not in kwargs` 逐字不變,新增的是
`heal_symbol_active` 那一條)。

## 5. 未做 / 留尾

### 5.1 N093 heal variant 的 history 訂閱無釋放路徑 — **整條未做**

- **理由**:條文自帶條件「TC4 per-session history 訂閱上限未實測 …… 若有上限」。要收的
  動作(對舊 1K 窗發 `UNSUBQUOTE` 釋放)**需要真 TC4 才敢動**:tc4-market-facts 記的是
  「**任一把 key** SumSubCount 歸 0 → 上游退訂整個 symbol」,若這條對 history key 也
  成立,退訂 1K 窗就會把 `IX0001` 的 REALTIME feed 一起殺掉 —— 失效樣態是「加權分時線
  與右上角台指一起靜默死掉」。本 session 零 TC4,不硬做也不裝做。
- **已確認的安全事實(本輪記帳)**:階梯本來就有上限 ——
  `WINDOW_VARIANT_END_BASE(6)` → `WINDOW_VARIANT_END_CAP(23)`,單日單 symbol 至多 18 把
  history 訂閱,`_swap_day` 換交易日歸零。不會無限增長。
- **盤中量測腳本 / 判準**:見 §6.2。

### 5.2 N033 「純本機檔案 IO 獨立有界 executor」 — **未做**(只做 `_warned_years` 安全半)

- **理由**:條文自帶條件「**若 prod 觀察到** today / daily_bars 變慢」。沒有量測就分池
  = 憑感覺加抽象(鐵則 B);分池另會改關機時 `shutdown_default_executor` 的 join 範圍
  (`test_boot_window` 已有一條註解點名 3.13 上限 300s 的那條路)。
- **判準**:見 §6.3。

### 5.3 N111 深修剩下的一半

逐項取鎖把第二個寫入者的等待上界從「整段迴圈」降到「當下這一檔」,**ZMQ IO 仍在鎖內**。
要完全移出需要 per-code in-flight 狀態:`owners.add(owner)` 先佔位 → IO 在鎖外 →
失敗回滾,同時要處理「第二個 acquirer 看到 owners 非空就跳過訂閱,而第一個還在途中或
已失敗」這個新的不一致窗(需要 per-code 的 in-flight event + 等待)。那是新的不變式,
獨立輪。`set_main_contract` / `_release_stkfut` 同款迴圈本輪未動(它們是單檔,不是迴圈)。

### 5.4 N092 `stock_source.backfill` 的真三態化

本輪只補 stub 簽名 log。要升成例外必須先把 `parse_hist_tick` 的「試撮窗濾掉」與
「解析不出」分流(現在兩者都回 `None`)—— 否則 08:30–09:00 盤前回補會被判成 stub 而
無限重排。分流 = 改 `parse_hist_tick` 的回傳契約,獨立輪。

### 5.5 N051 另外兩個 churn 來源(M0 log 點名,本輪不收)

- **收盤段 `IX0001` 13:25:37–13:34 每 30 s 一發共 18 發**:index source 的閘是
  `in_trading_hours_now`(08:30–13:35),而加權指數在收盤集合競價段本就停推。收法 =
  給 index source 一把自己的閘(上界 13:25)。**不在本輪**:那會連帶關掉 13:25–13:35
  之間真正零推播時的自癒,而 13:30 收盤後還有最後一筆指數 —— 該不該放棄它要 user 拍板。
- **個股冷門檔(6921 全日 6 ticks → 153 發、6949 → 59 發)**:R3 健檢對「當日本來就
  沒成交」的檔一樣狂重掛。收法要一個「今天這檔本來就沒成交」的判準,而它與「這檔真的
  被 TC4 殺了」在協定上不可分(SUBQUOTE 恆回 OK)—— 誤判的代價是自選裡那一檔整天空白。
  可行方向:對「從未推播」的檔把退避上限從 60 s 拉到 300 s(降 5 倍 churn,不放棄自癒)。

### 5.6 其他

- `corr_source.taifex_leg_gate` 對 SGX / CME / CBOT / OSE 段恆 True。要收那半邊的前提 =
  先拿 `QUERYINSTRUMENTINFO` 的 `OpenCloseTime` 把各段時段落成事實(skill 目前只有
  OSE 一組:`OpenTime=160000 / CloseTime=144500` 台北)。
- `tests/live/test_river_state.py` 的 UTF-8 BOM(N059)**未順手處理** —— 不在本輪 scope。

## 6. 需 user 過目 / 盤中量測

### 6.1 N049 兩半的真環境驗證(下次收工時,**非盤中**)

1. 正常 `.\run.ps1` 起站 → Ctrl+C。
2. 期望看到腳本印:
   `[run] 等 backend 自行收尾(TC4 退訂 + Disconnect,最多 10s) ...`
   後接 `[run] backend 已自行結束(TC4 session 已 LOGOUT)`。
   若印的是黃字 `10s 內未結束,改為強制收掉` → 表示 lifespan 仍跑不完,回報。
3. TC4 端對帳(判準):
   `grep "RemoveLoginInfo" "C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-YYYYMMDD-0.log" | tail`
   —— 時戳應**貼著** Ctrl+C 那一刻(±2 s),而不是 60 s 之後;同時
   `grep "ExecuteCheckPingTime"` 在該時段**不應**出現 reap 這幾條 session。
4. 下一次啟動後開頭 60 s **不應**再出現 `TC4 REALTIME 零推播自癒` 整批重掛
   (`grep "零推播自癒" logs/server-*.log | head`)。

### 6.2 N093 觀察(側車重演 SC-5 時順手,**需真 TC4**)

- 目的:量 TC4 per-session 的 history 訂閱上限,以及「對舊 1K 窗發 UNSUBQUOTE 會不會
  把該 symbol 的 REALTIME feed 一起帶走」。
- 腳本形狀(scratchpad 一次性,**不要用 prod 的窗訂 prod 的 symbol**,收工必
  `UNSUB + Disconnect`):
  1. 對一個 prod 沒訂過的 symbol(如 `TC.S.TWS.2330`)同時掛 `REALTIME` 與 `1K`,
     確認兩者都有回應。
  2. 連續對同一 symbol 用 `end hour` 6→23 建 18 把 1K 訂閱,每把 `GETHISDATA("0")`
     記 rows 數。**判準**:某一把之後開始「靜默回空」= 觸頂;全部都有資料 = 18 把之內
     無上限。
  3. 對第 1 把 1K 窗發 `UNSUBQUOTE`,之後 60 s 觀察該 symbol 的 **REALTIME** 是否仍有
     推播。**判準**:仍有 = history key 與 REALTIME feed 解耦,N093 可以安全收;
     停了 = 「任一把 key 歸零帶走整個 symbol」對 history 也成立,N093 **不能**用退訂收,
     只能靠階梯上限(現況)。
  4. TC4 端交叉對帳:`grep "IX0001|1K|" QuoteZMQService-*.log` 看
     `Add/RemoveSubQuoteCount(... count:N, SumSubCount:M)` 與有無 `ReqSubQuote()`。

### 6.3 N033 executor 判準(盤中,零風險純觀察)

- 盤中(TC4 半死或全站零推播那種時段最有價值)量:
  `curl -s -o NUL -w "%{time_total}\n" localhost:8721/api/signals/today` 與
  `.../api/stock/overlay/2330`,各 10 發取中位。
- **判準**:中位 > 1.0 s 且同期 `py-spy dump --pid <server pid>` 看得到多條
  `_listen_loop` / `subscribe_symbol` 卡在 executor(ThreadPoolExecutor worker 全滿)
  → 分池成立,開 N033 的另一半。否則維持現狀。

### 6.4 N050 的真環境判準(盤中 / 盤後任一,**需真 TC4**)

改動後 TXO 的 `TXF.HOT` 訂閱窗會比 futures session 多一小時。判準:
`grep "TXF.HOT|REALTIME|" QuoteZMQService-YYYYMMDD-0.log | grep AddSubQuoteCount`
應看到**兩把不同的 `StartTime|EndTime`**(各自 `count:1`),而不是同一把 `count:2`。
若仍是同一把 → 位移沒生效,回報。

### 6.5 N052 的真環境判準(次一交易日 08:00 stock stage1 / 08:30 index 換日)

`grep "換日清舊窗" logs/server-*.log` 應**沒有**輸出(那是失敗時才印的 warning);
TC4 端 `grep "<symbol>|REALTIME|" QuoteZMQService-*.log` 在換日前後應看到
舊窗 `RemoveSubQuoteCount(... SumSubCount:0)` → 新窗 `AddSubQuoteCount(... count:0→1)`
→ `ReqSubQuote()` 這一串,而不是舊窗 key 停在 `count:1` 一整天。

### 6.6 畫面過目(prod 重啟後)

- **期貨面**:重連之後(可等自然發生,或看 `grep "TC4 reconnected" logs/server-*.log`)
  leaf-fed 商品的價格會**短暫空一格**再被新推播填回 —— 這是 N260 刻意的重武裝,不是 bug。
  若觀察到價格空著超過一個 `leaf_grace_secs + 一輪 resub interval`(prod ≈ 13 s)沒回來,
  回報。
- **自選**:PUT / Discord `/watch` 的回應在 TC4 半死時應比以前快(N111);連續快速改
  兩次自選,最終畫面必須是**後改的那一份**(N111 的 `_superseded` 守的就是這條)。
