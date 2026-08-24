# mod/tc4-session-hardening — change-spec

R8「TC4 連線/訂閱深水區」13 條(N259 / N260 / N261 / N049 / N050 / N052 / N092 / N093 /
N094 / N111 / N112 / N051 / N033)。需求原文 =
`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R8。

---

## §0 白名單(每條先 grep 過 caller,含動態用法)

### 0.1 `tc4.py` 共用層(N259 / N050 / N051 / N092)

`TC4QuoteSource` 的四個消費者(blast radius):

| source | 檔 | 用到的共用面 |
|---|---|---|
| TXO(基底直用) | `app._default_source` → `TC4QuoteSource` | `_ensure_connected` / `subscribe` / `_rt_window` |
| 個股 + 指數 | `live/stock_source.py::StockQuoteSource` | 覆寫 `_rt_window`、`_resub` / `_unsub` / `_heal_resub` |
| 期貨 | `live/futures_source.py::FuturesQuoteSource` | **不**覆寫 `_rt_window`(沿用盤別窗) |
| 相關係數 | `live/corr_source.py::CorrQuoteSource` | 覆寫 `_rt_window` = 全天窗 |

- `_ensure_connected` caller(grep `_ensure_connected`):`tc4.list_series` /
  `list_stock_futures` / `fetch_backfill` / `subscribe`;`stock_source.subscribe_symbol` /
  `backfill` / `fetch_day_minutes` / `fetch_daily_bars` / `fetch_bars_range_tagged`;
  `futures_source.subscribe_symbol` / `subscribe_leaf` / `fetch_day_1k` /
  `fetch_bars_range`;`corr_source.subscribe_raw` / `fetch_day_1k`。全部只吃
  「成功即已連線 / 失敗拋 `ConnectionError`」這個契約 → 契約不變。
- `_apply_variant` caller:`_rt_request`(唯一)+ 三個測試。
- `_heal_tick` caller:`_heal_loop`(唯一)+ 測試直呼。
- `_fetch_symbol_ticks` caller:`fetch_backfill`(唯一)。
- **既有測試白名單**(不得紅):`tests/live/test_tc4.py` 全檔(含
  `TestApplyVariant` 四條窗變體互異、`TestHealSessionSilence` / `TestHealSymbolSilence`、
  `TestReconnectResubWarning`)、`tests/live/test_stock_source.py`、
  `tests/live/test_futures_source.py`、`tests/live/test_corr_source.py`、
  `tests/live/test_futures_bars.py`、`tests/live/test_stock_bars.py`。

### 0.2 `stock_source.set_trade_date`(N052)

caller:`stock_engine.start()`(啟動同步日窗)、`stock_engine.rollover_stage1`、
`index_engine.start()`(**在連線之前**呼叫)、`index_engine._rollover_loop`(換日)。
白名單:`tests/live/test_stock_source.py::TestRolloverClearsHealBooks`、
`tests/server/test_stock_engine.py` 的 rollover 兩段式整組、
`tests/server/test_index_engine.py` 的換日 pending buffer 整組。

### 0.3 `index_engine._subscribe_and_backfill`(N094)

caller:`start()`、`_retry_loop`(唯一兩處)。
白名單:`tests/server/test_index_engine.py` 全檔,特別是
「pending 期間 retry 抓的是新日窗」「`_swap_day` 三層疊法(早輪回補 < 最終回補 <
live pending)」「分時自癒無進展 → 換窗口階梯」三組 —— **合併序不得變**。

### 0.4 `futures_engine._handle_reconnect`(N260)

caller:`_on_reconnect_threadsafe`(唯一)+ 測試直呼。
白名單:`tests/server/test_futures_engine.py::TestReconnect*` 全部,尤其
`test_reconnect_does_not_clear_leaf_fed`(`_leaf_fed` 本身不得清)、
`test_reconcile_survives_inflight_retry_success`(epoch)、
`test_month_rollover_rearms_leaf_fed_products`。

### 0.5 `corr_engine._on_reconnect_threadsafe`(N261)

caller:`start()` 掛給 source 的 `on_reconnect`(唯一)。
白名單:`tests/server/test_corr_engine.py::TestPendingResubscribe` 整組、
`tests/server/test_corr_engine_river.py` 全檔(single-flight 互吃與逾時重補階梯)。

### 0.6 `stock_engine.set_watchlist`(N111 / N112)

caller:`app.py` boot 還原(`_start_stock`)、`watchlist_service._settle`(前端 PUT +
Discord `/watch` 共用)、`tests/**` 102 處直呼(不帶 `seq`)。
`WatchlistEngine` Protocol 在 `watchlist_service.py`;實作面另有各 fake。
白名單:`tests/server/test_stock_engine.py` 的 `TestRefcountPool` / seq 定序 /
「名單先指派再訂閱」/ hub membership 全組、`tests/server/test_watchlist_service.py` 全檔、
`tests/server/test_stock_routes.py` 的 restore-on-startup 三條、
`tests/server/test_discord_bot.py`。

### 0.7 lifespan 關機序(N049)

唯一定義點 `app.py` lifespan `finally`。白名單:`tests/server/test_boot_window.py` 全檔
(關機中斷 boot / 反序 close 不洩漏)、`tests/server/test_verify.py`。
`run.ps1` 無自動化測試(PowerShell;見 verification.md「需 user 過目」)。

### 0.8 `trading_calendar.warn_if_year_missing`(N033 安全半)

caller:`resolve_trade_date`(唯一)→ `app._resolve_trade_date` / breadth / index。
白名單:`tests/test_trading_calendar.py` 全檔。

---

## §1 逐條處置

### N259 `_ensure_connected` 原子化 🔴

**改動**:`tc4.py::_ensure_connected` 整段(check → `QuoteAPI(...)` → `Connect` →
指標發布)移進 `self._api_lock`,並在鎖內加 `_stop` 早退。

**判定與理由**:
- 條文寫「check+建立+發布以 `_api_lock` 原子化」→ 逐字照做(持鎖跨越 `Connect()`),
  不做「建立在鎖外、發布時比對、落敗者 dispose」的樂觀版本 —— 後者仍會真的建出兩條
  TC4 登入(TC4 端 log 會看到兩次 login/logout),而 KeepAlive 執行緒在 `Disconnect()`
  之前就已經起來了。
- 代價:`_connection()` / `_req` 的讀側在重連期間最壞等 `_REQ_TIMEOUT_MS`(10 s)。
  那條路本來就只能拿到 `None` → `ConnectionError`;等完拿到**新連線**嚴格優於當場失敗。
- 鎖序不變(`self._lock` → `_api_lock`),`Connect()` 內不取 `_api_lock` → 無死鎖。
- `_stop` 早退:`close()` 之後在途的 executor 工作項(`futures._retry_subscribe`、
  個股健檢 timer)不得把連線建回來;`futures_engine._retry_subscribe` 的註解本來就
  指向「殘餘 race 的根治 = tc4 `_ensure_connected` 原子化,獨立 /mod」= 本條。

**四 source 各一條 race lock**:`tests/live/test_tc4.py::TestEnsureConnectedAtomic`
以 `sys.modules["tcoreapi_mq"]` 注入延遲 `QuoteAPI` 替身,parametrize 四個 source 類別。

### N260 reconnect 對帳含 leaf 🔴

**改動**:`futures_engine._handle_reconnect` 在回填 `_pending_subs` 之前,對
`_leaf_fed` 的品清掉它們在 `_leaf_done` 的鍵、並把 `st.p` 歸 `None`。

**判定與理由**:條文寫「清 `_leaf_done` 當日鍵重走 fallback」。**只清 `_leaf_done`
不夠** —— `_leaf_fallback` 的另一道判準是 `st.p is not None` 就跳過,而 leaf-fed 品的
`p` 正是 leaf 推上來的舊值。兩道一起解除才會重走,手法與既有「換月重武裝」逐字同款
(`_handle_quote` 跨日分支也是把 leaf-fed 品的 `p` 清 `None`)。
健康品(HOT 自己在推、不在 `_leaf_fed`)**不動** —— 無條件清 `p` 會讓每次重連右上角
期貨價空一格,那是新的失效。`_leaf_fed` 本身不清(白名單
`test_reconnect_does_not_clear_leaf_fed` 鎖住的語意)。

### N261 corr 重連對帳 🔴

**改動**:`corr_engine` 新增 `_handle_reconnect`(取代 `_on_reconnect_threadsafe` 直接
排 `_schedule_backfill`):bump `_resub_epoch` → 把**全部 tc4 腿**回填 `_pending_subs`
→ 沒有活著的 `_resub_task` 就建一個 → 最後才 `_schedule_backfill()`(舊行為保留)。
`_resub_round` 加 epoch 比對(await 期間重連 = 該筆掛在舊連線上,留在 pending)。

**判定與理由**:條文說「下次動 corr 時比照 futures 接對帳」= 本輪。形狀逐字照
`futures_engine._handle_reconnect`(含 `_loop is None` 早退與 epoch)。
**迭代 `tc4_legs()`**:base 腿(futures_engine 來源)結構上不可能進 pending —— 重複訂
`TXF.HOT` 會讓其中一邊永久零推播。

### N049 shutdown 保證 LOGOUT 🔴

**兩個候選都做**(條文列 A 或 B,兩者互補):
1. **B(app lifespan)**:`capital.close()`(同步 COM join,prod ≤5 s)從
   `futures → capital → index → stock → runtime` 移到 **runtime 之後**(最後一步)。
   它與 index / stock / runtime 之間沒有依賴(有依賴的只有 corr→futures、
   signals→stock),把關機預算最前面那 5 秒讓給真正有時間壓力的 TC4 收尾。
   這是**唯一**違反「一律照建立的反序收」的一段,理由寫在該段註解。
2. **A(run.ps1)**:`finally` 先 `Wait-GracefulExit -Proc $backend`(`WaitForExit`,
   上限 10 s)再 `Stop-Tree`。**只有 B 不夠** —— Ctrl+C 之後 PowerShell 的 finally 在
   幾十毫秒內就 `taskkill /T /F`,lifespan 根本跑不到任何 `close()`;A 給窗、B 讓窗
   夠用。

**判定型決定**:條文的候選 A 原文是「輪詢 :8721 消失」;改用 `Process.WaitForExit`
—— 同一件事的更直接判準(port 釋放晚於 process 結束,且 `Get-NetTCPConnection`
在某些環境不存在,腳本裡已有 `$null =「無法判定」`的分支)。

### N050 TXF.HOT 雙 session 同 key 🔴

**判定型決定 —— 選候選一(TXO 側改窗)**,實作為 `TC4QuoteSource` 新增
`_window_offset: dict[str, int]` 常駐窗位移,`subscribe()`(TXO 專用入口)登記
`SPOT_SYMBOL → SPOT_WINDOW_OFFSET(=1)`;`_apply_variant` 的總位移 k =
`variant + offset`。

**理由**:
- 候選二(futures_engine 單持、TXO 讀 `futures.state`)會改掉 **TXO 面現貨點位的資料源
  語意**(從自己的推播改成跨引擎讀取),牽動 `runtime.spot` / `index_engine.txf_getter` /
  TXO 綜合損益三處,且 futures 引擎缺席時 TXO 面直接沒有現貨 —— 那是要 user 拍板的
  範圍(列為判定型決定,本輪不做)。
- 候選一對既有訂閱面的改動最小(只多一個 dict 與一次登記)、可回退(offset 設 0 即
  逐字回到現況),且與既有的 window-variant 機制同一條階梯,不引進第二套窗計算。
- **只位移 TXO 這一邊**:兩邊一起位移還是同一把 key,而期貨面的盤別窗是它自己的既有
  行為。測試 `test_futures_session_keeps_the_base_window_for_the_same_symbol` 釘住。
- 不變式:登記 offset 後 variant 0/1/2/3 仍兩兩互異(`test_spot_offset_survives_the_heal_variant_ladder`)。
- `_unsub` **不**清 `_window_offset`:offset 是「這條 session 對這個 symbol 用哪一把
  key」的身分,不是自癒的節奏(variant / attempts 才是)。

### N052 rollover 舊窗 key 洩漏 🔴

**改動**:`StockQuoteSource.set_trade_date` 在換日**之前**呼叫新的
`_unsub_stale_window()` —— 對當下的窗(含 variant)逐 symbol 發 `UNSUBQUOTE`,
`_subscribed` 不動(stage 2 靠它當重掛名單)。日期沒變則整段不發。

**理由**:舊窗 key 歸零會讓上游退訂該 symbol —— 這正是要的:stage 2 的新窗 SUB 走
0→1 觸發 `ReqSubQuote` 把 feed 重新掛上,形狀與已在跑的
`_heal_resub(bump_variant=True)`(先退舊窗再換窗)完全相同。
**不得拋**:`index_engine.start()` 在**連線之前**就呼叫 `set_trade_date`;第一發失敗
即停(失敗多半是連線已死,其餘也會失敗,同 `close()` 的收斂)。

### N092 姊妹 ready-check 三態化 🔴 + 🔵

三處「首頁非空即 break」逐處處置不同:

| 處 | 處置 | 理由 |
|---|---|---|
| `river_backfill.collect_1k_minutes` | 🔴 stub 簽名(rows 非空 / `skipped == 0` / minutes 全空)由「warning + 回空」改成 **`raise HistoryTimeoutError`** | 唯一有**無誤報風險**簽名的一處:`parse_1k_minutes` 已把「欄位壞掉」分流到 `skipped`。凍結 stub 的語意 = 「現在取不到,不是沒有」= 該例外的語意;它是 `ConnectionError` 子類,corr 的逾時重補階梯(3 輪 × 30 s)因此接得到手 |
| `stock_source.backfill` | 🔵 只補 stub 簽名 log,控制流不變 | `parse_hist_tick` 的**試撮窗過濾**會製造同形狀的**合法**空(08:30–09:00 盤前回補、13:25–13:30),升成例外會讓那條路被 worker 無限重排。要真三態化得先把「試撮濾掉」與「解析不出」分流 → 留尾 |
| `tc4._fetch_symbol_ticks` | 🔵 只補 stub 簽名 log,控制流不變 | `fetch_backfill` 的 round 制本來就把「0 tick」當 still-pending 再試一輪 → 復原路徑已在;缺的只是這條路上唯一的 grep 判準 |

**該變清單**:`tests/live/test_river_backfill.py::test_all_rows_dropped_warns_frozen_stub`
→ 改名 `test_all_rows_dropped_raises_history_timeout`,斷言由 `== []` 改為
`pytest.raises(HistoryTimeoutError)`(舊契約「回空」正是 N092 要消滅的那半)。
`test_unparsable_rows_do_not_claim_frozen_stub` 維持回空(不是 stub)。

### N093 heal variant 的 history 訂閱無釋放路徑 — **未做**

見 verification.md「未做 / 留尾」。安全半 = 記帳:階梯**已有上限**
(`WINDOW_VARIANT_END_BASE=6` → `CAP=23`,單日單 symbol ≤18 把,`_swap_day` 歸零),
不會無限增長。要收的那半(對舊 1K 窗發 `UNSUBQUOTE` 釋放)**需要真 TC4 才敢動** ——
tc4-market-facts 記的是「**任一把 key** SumSubCount 歸 0 → 上游退訂整個 symbol」,
若那條規則對 history key 也成立,退訂 1K 窗就會把 `IX0001` 的 REALTIME feed 一起殺掉,
而失效樣態是「加權分時線與右上角一起靜默死掉」。本 session 零 TC4 → 不硬做。

### N094 `_twse.minutes` 跨執行緒無鎖 🔴

**改動**:`_subscribe_and_backfill(variant) -> dict[str, int]`(worker thread,只做 IO
與回傳);新增 `_merge_backfill(minutes) -> bool`(event loop thread,合併 + 進展判定)。
兩個 caller(`start()` / `_retry_loop`)在 `await` 之後才合併。

**合併序不變式(白名單,逐字保留)**:`_merge_backfill` 的 pending 分支仍寫
`_pending_backfill`、非 pending 分支仍寫 `_twse.minutes`,三顆 dict 仍是 in-place
`.update()`;`_swap_day` 的三層疊法(`_pending_backfill` < `backfill` <
`_pending_minutes`)一行未動。
**為什麼不需要世代旗標**:cancel 之後 `await` 不再返回 → 合併那一步天然不發生。

### N111 ZMQ 訂閱迴圈的 `_pool_lock` 粒度 🔴(部分)

**改動**:`set_watchlist` 從「整段一鎖」改成 **逐項取鎖**(照同檔 `_retry_round` 的
既有形狀):
- 第一段短鎖(**無 await**):seq 判定 + 算 added/removed + `self._watchlist = list(codes)`。
- added / removed 各自逐項 `async with self._pool_lock`,項內重驗
  (`_superseded(seq)` / `code in self._watchlist`)。
- 尾段(種子廣播 + hub membership)另取一次鎖。

**不變式對齊**:
- 「名單先指派再訂閱」(round4 項 4):名單在第一段短鎖就指派 → 比改動前**更早**,
  不變式加強不是放寬(`test_watchlist_is_assigned_before_any_subscribe`)。
- seq 定序:逐項取鎖打開一條舊碼結構上不可能發生的窗(較舊那一發在較新名單套用之後
  才跑完剩下的檔)→ `_superseded(seq)` 每項重驗,過期即整段放棄
  (`test_stale_call_abandons_the_rest_of_its_loop`)。

**做到哪裡(誠實記帳)**:第二個寫入者的等待上界從「整段迴圈」(50 檔 × 10 s)降到
「當下這一檔」(≤10 s)。ZMQ IO **仍在鎖內** —— 要完全移出得引進 per-code in-flight
狀態(`owners.add` 佔位 + 等待/回滾),那是新的不變式,列留尾。

### N112 `set_watchlist(seq=None)` 豁免顯式化 🔴

**改動**:
- `stock_engine` 新增 `WATCHLIST_BOOT_SEQ = 0`(boot 哨兵,恆為最舊)與
  `WATCHLIST_UNORDERED = -1`(非生產直呼);簽名改 `seq: int = WATCHLIST_UNORDERED`,
  `int | None` 與 `if seq is not None` 分支刪除。
- `_wl_seq_applied` 初值改 `WATCHLIST_BOOT_SEQ - 1`。
- `app.py` boot 還原顯式 `seq=WATCHLIST_BOOT_SEQ`。
- `watchlist_service.WatchlistEngine` Protocol 的 `seq` **沒有預設值** → 未來的生產
  caller 漏帶 keyword 在 pyright 期就紅。
- `_settle` 的 `if not changed` 改 `if not changed or seq is None`(型別收窄,行為等價:
  `_commit` 的不變式是 changed=True 必帶號)。

**判定與理由**:條文的「刪 None 分支」逐字照做。**沒有**把 `seq` 改成必填 —— 那要動
102 處測試呼叫點(每處還得配遞增號),churn 與風險遠大於收益;改成「Protocol 無預設
+ 生產 caller 全部帶號 + 非生產的 UNORDERED 明確標名」,同樣消滅了條文點名的
「未來 caller 漏帶 keyword 零訊號」。條文說「這條不變式沒在任何地方斷言」→ 新增
`TestWatchlistBootSentinel` 兩條把它斷言起來。

### N051 corr 每腿各自時段閘 🔴

**改動**:
- `tc4.py` 新增 `heal_symbol_active: Callable[[str], bool]`(預設 `always_symbol_active`)
  與 `_heal_tick` 的母體過濾(**在母體形成處**扣除,R1 的全場靜默判定也一起扣)。
- `corr_source.py` 新增 `TAIFEX_PREFIX` 與 `taifex_leg_gate(clock_gate)`:台期交段的腿
  吃 `clock_gate`,其餘段恆 True。
- `app._default_corr_source(calendar)` 接日曆,gate =
  `taifex_leg_gate(_heal_gate(calendar, in_futures_session_now))`;`create_app` 傳日曆。

**判定與理由**:
- 台期交段的國外指數期貨(SXF/UDF/SPF/UNF)與台指**同時段同結算**(tc4-market-facts
  「海外商品」節實證)→ 直接沿用期貨盤別閘,不是猜。M0 log 點名的 churn 大戶
  SXF(3 小時 8 發)正是這一段。
- **不猜海外時段**:CME / SGX / OSE 的時段本專案沒有實測事實,猜錯的失效樣態是
  「該救的腿整場不救」,比多幾發 churn 嚴重得多 → 恆 True。收那半邊的前提寫進留尾。
- 日曆也只 AND 在台期交那半邊 —— session 級 `heal_active` 維持不接日曆
  (`test_corr_source_keeps_the_always_on_session_gate` 逐字保留)。
- M0 log 另兩個 churn 來源(收盤段 IX0001 18 發、個股冷門檔 153 發)**本輪不收**,
  理由見留尾。

### N033 executor 同池耦合 — **部分(安全半)**

- **做**:`trading_calendar._warned_years` 的 check-then-add 加 `_warn_lock`
  (條文的「屆時一併看」那半;零風險、可測)。
- **未做**:「純本機檔案 IO 獨立有界 executor」—— 條文自帶條件「**若 prod 觀察到**
  today / daily_bars 變慢」。沒有量測就分池 = 憑感覺加抽象(鐵則 B),且分池本身會改
  關機時 `shutdown_default_executor` 的 join 範圍。觀察腳本與判準見 verification.md。

---

## §2 backward compat

| 面 | 影響 |
|---|---|
| HTTP / WS 契約 | **零改動**(payload、error shape、欄名全同) |
| frontend | **零改動**(本輪不動 `frontend/`) |
| `set_watchlist` 呼叫端 | Protocol 的 `seq` 變必填 —— 生產只有兩個 caller,均已顯式帶號;concrete 方法留 `WATCHLIST_UNORDERED` 預設,102 處測試直呼行為逐字不變 |
| `fetch_day_1k`(corr / futures source) | 凍結 stub 從「回空」變 `HistoryTimeoutError`(`ConnectionError` 子類)—— 只寫 `except ConnectionError` 的呼叫端行為不變;corr 專門接 `HistoryTimeoutError` 的那條改為重補 |
| `IndexEngine._subscribe_and_backfill` | 回傳型別 `bool → dict[str, int]`,私有方法,caller 只有同檔兩處 |
| TC4 訂閱面 | TXO 的 `TXF.HOT` 換一把窗(N050);換日多一輪舊窗 UNSUBQUOTE(N052)。兩者都是「多送 / 換送 REQ」,不改任何 symbol 的訂閱集合 |
| 關機順序 | capital 移到最後(N049)—— 無依賴,對外行為只有「TC4 更常來得及 LOGOUT」 |

## §3 seams(測試落點)

| seam | 測什麼 |
|---|---|
| `TC4QuoteSource._ensure_connected`(注入 `sys.modules["tcoreapi_mq"]`) | 四 source 的重連 race 各一條 |
| `TC4QuoteSource._heal_tick(now)`(純判定,注入時鐘) | 逐 symbol 閘的 R1 / R2 母體 |
| `TC4QuoteSource._rt_request` 送出的 `(Request, Symbol, StartTime, EndTime)` | 窗 = TC4 refcount 鍵,N050 / N052 都在這一層斷言 |
| `IndexEngine._subscribe_and_backfill` / `_merge_backfill` | worker / loop 兩側分離(N094) |
| `FuturesEngine._handle_reconnect` / `CorrelationEngine._handle_reconnect` | 直呼(threadsafe 入口另有既有測試) |
| `StockEngine.set_watchlist` + per-code gate source | 鎖粒度(N111)與哨兵(N112) |
| `create_app` + fake source 的 `close()` 順序戳 | 關機序(N049) |
