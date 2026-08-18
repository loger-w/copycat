# change-spec — TC4 REALTIME 零推播自癒(root cause 見 repro.md)

## 目標
被 TC4「任一 key 歸零 → 退訂整個 symbol 上游;count>0 的 SUB 不重掛」打死的 REALTIME 訂閱,
server 自己在 ≤ 約 60s 內偵測並復活,**不靠重啟**。所有 5 條 TC4 session(TXO / stock / index / futures / corr)一體適用。

## 修改點(最小)
### 1. `copycat/live/tc4.py::TC4QuoteSource`(基底,generic)
新 kwargs(預設全部**關閉** → 既有測試/行為零變):
- `heal_silence_secs: float | None = None`:R1「整條 session 靜默」門檻;None = 自癒整體關閉。
- `heal_symbol_silence_secs: float | None = None`:R2「單 symbol 曾有推播後靜默」門檻;None = R2 關。
- `heal_active: Callable[[], bool] = lambda: True`:僅回 True 時做自癒(盤外不 churn)。
- `heal_poll_secs: float = 5.0`。

狀態:`_last_push: dict[str, float]`(symbol → monotonic;在 `_realtime_msg` 內以 `msg["Quote"]["Symbol"]` 記錄 —
四個子類的 `handle_raw` 都經過它,單點)、`_sub_at: dict[str, float]`(成功 SUBQUOTE 時記:`_resub`、TXO `subscribe`、
`_check_stale` 重訂)、`_heal_attempts: dict[str, int]`、`_heal_next: dict[str, float]`、`_window_variant: dict[str, int]`。

Watchdog thread `_heal_loop`(daemon;`_start_listener` 內、heal 開啟時才起;`_stop` 為止),每 `heal_poll_secs`:
- `heal_active()` False → 略過。
- **R1**:subs 非空 且 `max(_last_push[s] for s in subs, default=0) < now-T` 且 `max(_sub_at[s]) < now-T`
  → 對**所有** subs 逐一 heal(session 級 backoff:T, 2T, 4T … cap 300s)。
- **R2**(T2 非 None):對每個 sub:`s in _last_push and _last_push[s] < now-T2 and _heal_next.get(s,0) <= now` → heal(s)。
- `heal(s)`:`_heal_attempts[s]+=1`;**attempts ≥ 3 → `_window_variant[s] = (_window_variant.get(s,0) % 3) + 1`**
  (同 key 兩次沒救回 = 這把 key 有別的持有者(TXF.HOT 由 TXO+futures 雙持、外部 probe),
  只有換一把 count 0 的新 key 才會觸發 TC4 `ReqSubQuote`);呼叫 `_resub(s)`(持 `self._lock`,和 `_check_stale` 互斥);
  `_sub_at[s]=now`;`_heal_next[s] = now + min(T·2^(attempts-1), 300)`。
  例外 `(ConnectionError, zmq.ZMQError, OSError, json.JSONDecodeError)` → `logger.warning` + backoff,不得殺 thread。
  log(grep 判準):`TC4 REALTIME 零推播自癒:%s 靜默 %.0fs → 重掛(attempt %d, window_variant=%d)`。
- 收到 symbol 推播時(`_realtime_msg`):`_heal_attempts.pop(s, None)`(variant **保留**,那把 key 是活的)。

**Window variant 套用**:基底 `_rt_request` 改為 `window = self._rt_window(symbol)` + `_apply_variant(symbol, window)`;
新增 `_rt_window(symbol) -> (start,end)`(預設 `session_window(session_key())`)。`stock_source.StockQuoteSource` 與
`corr_source.CorrQuoteSource` **從覆寫 `_rt_request` 改為覆寫 `_rt_window`**(行為等價;純搬家)。
`_apply_variant`:variant k>0 → EndTime 小時 +k(cap 23;若已 23 則改 StartTime 小時 −k,cap 00)。
`_sub_history` / `_get_history`(歷史)**不吃 variant**(回補窗維持原樣;歷史 key 與 REALTIME key 不同型別無關)。

### 2. `copycat/live/stock_source.py::StockQuoteSource`(R3,個股專屬)
`_health_check(code)`:not seen 且 `_in_trading_hours()` 且仍在 `_subscribed` → 除既有 `_on_no_data(code)`(**只在第一次**發,
維持既有 engine 語意)外,**`_resub(symbol)` 並以 backoff 重掛 timer**(10 → 20 → 40 → 60s cap,持續到 seen 或退訂;
`_resub` 失敗 warning 不 raise)。第 3 次起同樣走 window variant(共用基底 `_window_variant` / `_heal_attempts` 記帳)。
建構子把 `heal_silence_secs=30, heal_symbol_silence_secs=60, heal_active=in_trading_hours` 傳給基底。

### 3. 各 source 預設(prod 建構點 `app.py::_default_*`;source 建構子預設值即可,不改 app.py):
| source | R1 T | R2 T2 | heal_active |
|---|---|---|---|
| StockQuoteSource(stock + index 共用類) | 30 | 60 | `in_trading_hours`(既有參數) |
| FuturesQuoteSource | 30 | 60 | always(盤外 churn 上限 = 3 symbol / 300s,可接受) |
| CorrQuoteSource | 120 | 240 | always(海外腿稀疏,門檻放寬) |
| TC4QuoteSource(TXO,`app._default_source`) | 60 | None(277 契約深 OTM 本就靜默,R2 會 churn) | `session.py` 判「日盤 08:45–13:45 / 夜盤 15:00–05:00」(台北牆鐘;新增小 helper) |

## 紅測試(tests/live/test_tc4.py + test_stock_source.py;fake api 記錄 REQ 序列、可注入 monotonic/時間)
- T1 R1:訂閱後無任何 REALTIME 超過 T → watchdog 對每個 sub 發 UNSUBQUOTE+SUBQUOTE;`heal_active` False → 不發;有推播 → 不發。
- T2 R2:symbol A 有推播後靜默 ≥ T2、B 持續推播 → 只 A 被重掛;A 恢復推播 → attempts 歸零。
- T3 escalation:同 symbol 連續 3 次 heal 仍靜默 → 第 3 次 SUBQUOTE 的 EndTime = 原 +1h;第 4 次(=攻擊後 variant 保留)。
- T4 heal 期間 `_rt_request` 拋 ConnectionError → thread 存活、下輪繼續(backoff)。
- T5 stock R3:訂閱 +10s 無推播 → 發 no_data 回呼**一次** + UNSUB→SUB;+20s 仍無 → 再重掛;seen 後不再重掛。
- T6 純搬家:stock/corr 覆寫 `_rt_window` 後 SUBQUOTE 的窗與改前完全相同(既有測試應直接覆蓋)。
- 現有全部測試綠;`ruff` / `pyright` 綠。

## 實作 deviation(round-1 收尾補記)

規格寫的與實際實作不同、或規格沒寫而實作有的行為,逐條列出(review round-1 T-5 / T-8 要求):

- **R1 命中即 return**:同一輪 tick 內 R1 整批重掛後**不再走 R2**。兩條規則各記一次
  `_heal_attempts` 會讓退避與換窗階梯整條錯位(spec §1 只寫「R1 → 對所有 subs 逐一 heal」,
  沒寫短路)。鎖在 `TestHealRuleInteraction`。
- **`_note_push` 同時 pop `_heal_next`**:spec 只寫「清 attempts、variant 保留」。只清
  attempts 的話,恢復後又靜默的 symbol 要等上一輪算出的退避到期(最壞 300s)才救得回。
- **R2 母體(round-1 C-6)**:改為「曾有推播」**或**「`_sub_at` 已超過 T2 卻從未推播」。
  spec 原文只收前者,漏掉「從未推播的部分死亡腿」—— 那正是 08-18 個股面的形狀。
- **窗變體規則(round-1 C-1)**:spec 的「EndTime +k,滿 23 改 StartTime −k」對 corr 全天窗
  是 no-op、對 TXO 夜盤窗 k=1/2/3 塌成同一把 key。改為「總位移 k 先加 EndTime,餘量推
  StartTime;StartTime 已頂到 00 則改往後推」,四把 base 窗的 variant 1..3 互異且 != base。
- **換窗那一發先 UNSUB 舊窗(round-1 C-7)**:序列 = `[UNSUB 舊窗, UNSUB 新窗, SUB 新窗]`。
- **R3 獨立記帳(round-1 C-9)**:個股健檢的 attempts/退避改記在 `_no_data_attempts` /
  `_no_data_next`,與 watchdog 只共用 `_window_variant`(spec §2 原寫「共用基底記帳」)。
- **`heal_active` AND 交易日曆(round-1 C-5)**:prod 的 TXO / stock / index / futures 四條
  session 的閘再 AND `trading_calendar.is_trading_day(today)`;corr 維持 always。
  已知邊界:週六凌晨 00:00–05:00 屬週五夜盤那一場,`is_trading_day(週六)` 為 False → 該段
  不自癒(取「寧可少救不可空 churn」)。

## 不做(留 next-time)
- shutdown 保證 LOGOUT(run.ps1 taskkill /F 之下做不到;有自癒後不再是必要條件)。
- TXO/futures 對 TXF.HOT 的雙持去重(variant escalation 已涵蓋)。
- skill `tc4-market-facts` 錯誤事實「同 symbol 跨 session 只推一邊」改寫 → 本輪 docs commit 一起改(main session 做)。
