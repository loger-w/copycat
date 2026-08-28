# /mod 可觀測性小批(2026-08-28 next-time triage B1 拍板)

分支 `mod/observability-batch-0828`(worktree `copycat-wt-obs`,自 master `e74b40c3`)。
決定來源:`docs/superpowers/specs/2026-08-28-next-time-triage.md` B 組;user 拍板「做」,scope 已議定,零畫面改動。

## 現況 vs 目標

| # | 條 | 現況 | 目標 | 檔 |
|---|---|---|---|---|
| 1 | L106 + L171 | 重掛(UNSUB+SUB)後 TC4 回的 snapshot 走 `_realtime_msg` → `_note_push` 清 attempts / `_heal_next`;冷門檔(6949)每 60 s 一發 attempt 1(今日 92 發),`_HEAL_BACKOFF_CAP=300` 永遠到不了,`HEAL_VARIANT_AFTER=3` 換窗逃逸路對凍結 stub 也到不了 | 推播指紋 `(PreciseTime, TradeDate, TradeVolume, TradingPrice)` 與上一則**相同**且到達在該 symbol 上次重掛後 `_SNAPSHOT_GRACE_SECS`(10 s)內 → 視為 SUB 回的 snapshot:`_last_push` 照記(key 活著)、**不清** attempts / `_heal_next`,DEBUG 一行「重掛後 %.1fs 收到同指紋 snapshot,attempts 不清(attempt n)」。退避自然爬 60→120→240→300,第 3 發起換窗 | `copycat/live/tc4.py` |
| 2 | L3 | 有日曆的休市日 index 自癒整天不打(PR #139);日曆誤標交易日為休市時零 log | `_handle_quote`:`_has_calendar` 且 `not _is_trading_day(today)` 且牆鐘 ≥ 09:00,**同一日曆日內收到 ≥ 5 個相異現價** → WARNING 一次「日曆說 %s 休市但 IX0001 09:00 後仍有推播(%d 個相異現價)—— configs/trading_holidays.json 可能誤標」。門檻 5 個相異價擋掉「休市日 server 啟動時 SUBQUOTE 回一則前日收盤 snapshot」的假警報 | `copycat/server/index_engine.py` |
| 3 | L262 | 期貨 1K 落後 / 中段缺格只在前端 gate 5 判,後端零 log,H1(暫時落後)/ H3(memo 釘住)事後不可分 | `bars_range` tf="1" 且 ok 且 bars 非空:(a) 尾根 → 該商品 `_ProductState.t`(最後成交,同 `date`)之間的**可交易分鐘**(domain 依 session,段界之間零分鐘 —— review Spec c1 回校:牆鐘分會在 15:01 / 08:46 每個開盤固定假警報)> `_LAG_WARN_MINUTES`(3)→ WARNING `期貨 1K 落後 %s:尾根 %s 最後成交 %s 落後 %d 分(可交易分鐘)`;(b) 連續 bar 之間可交易分鐘 ≥ `_GAP_WARN_MINUTES`(3;冷門商品開盤頭一兩分沒成交不算 —— review Spec c2 回校)→ WARNING `期貨 1K 中段缺格 %s:%d 段,最大 %d 分(%s→%s;可交易分鐘)`(印**最大**那段,比首段有用)。固定前綴供 grep;同商品同尾根只印一次(避免每分鐘輪詢洗版);檢查跟 fetch 一起跑在 executor thread(review Standards J2) | `copycat/server/futures_engine.py` |
| 4 | 損益列 | `_on_profit_complete` 配對成功就地寫 avg / pnl / cost,零 log;今日 8358 無券空的群益均價值查不回來 | 配對成功且 `avg_price` 與**上次印過的值**不同(per (股號, 種類);review Spec c3 回校:pending 每 60 s 重建、`Position.avg_price` 恆 None,「與部位現值不同」會每輪都印)→ INFO `損益列回填 %s kind=%s avg=%s cost=%s pnl=%s price=%s(原 avg=%s,標籤原文=%r)`(標籤原文供融券 [25] 校準,review Spec b1)。同值不印(每 60 s 一輪不洗版) | `copycat/capital/client.py` |
| 5 | VX sparse | `configs/correlation.json` / `DEFAULT_CONFIG` 只有 SXF 標 sparse;VX 美盤夜間段今日 7 發 R2 假警報 | 兩處 VX 加 `sparse: true`;`test_only_sxf_is_sparse…` 改名 + 集合 `{"SXF","VX"}`(事前標該變);tc4-market-facts 稀疏腿段補一句 VX;CLAUDE.md §4 sparse 契約句的測試名同步(review Spec a2 補列) | `configs/correlation.json`、`copycat/corr_config.py`、`tests/test_corr_config.py`、skill |

## Caller map

- `_note_push`:唯一 caller `_realtime_msg`(四個子類 handle_raw 共用)。`_heal_attempts` / `_heal_next` 讀者:`_heal_tick`、`_heal`、`_unsub`(清)、測試 `TestHealSymbolSilence` / `TestHealWindowVariantEscalation` / `test_unsub_clears_every_heal_book`。
- `index_engine._handle_quote`:source `set_on_message` → `_on_quote_threadsafe` → `_handle_quote`;`_is_trading_day` / `_has_calendar` 既有(PR #139)。
- `futures_engine.bars_range`:`server/bars.py::build_minute` 經 `app._market_payload`;fake `_WithBars` 在 `test_futures_engine.py:1088`。
- `client._on_profit_complete`:collector `on_complete`;測試 `test_balance_chain_marks_avg_source_broker` 等四條。
- `Leg.sparse` 讀者:`app._default_corr_source` → `heal_sparse_symbols`;測試 `test_only_sxf_is_sparse_and_the_repo_file_agrees`、fixture at :95–105 帶 `sparse`。

## 既有行為白名單(不得破壞)

1. 真推播(指紋變動,或非重掛後 10 s 內)照舊清 attempts + `_heal_next`(`test_push_resets_attempts` 逐字不改)。
2. `_unsub` 清所有 heal 記帳(含新增的指紋表)。
3. R1 / R2 判準、`_HEAL_BACKOFF_CAP`、`HEAL_VARIANT_AFTER`、sparse 豁免語意全部不動。
4. index:交易日 / 無日曆路徑零新 log;休市日 server 啟動那一則 snapshot 不觸發。
5. `bars_range` 回傳值與三態 status 不變;WARNING 只在 tf="1" + ok + 非空;timeout / disconnected 路徑零新 log。
6. `_on_profit_complete` 的配對規則、寫入欄位不變;同值輪不印。
7. corr:SXF 仍 sparse;其他腿不變;`sparse` 非 bool WARNING 規則不變。
8. 畫面零改動;wire payload 零改動。

## Seams(測試只寫在這裡)

`tests/live/test_tc4.py`(heal 類)、`tests/server/test_index_engine.py`、`tests/server/test_futures_engine.py`、
`tests/capital/test_client.py`、`tests/test_corr_config.py` + `tests/server/test_main_wiring.py`(既有契約鎖 `test_corr_sparse_legs_come_from_the_config_file` 的期望集合隨 VX 該變;review Spec b3 補列)—— 全是既有 seam,不新開。

## Commit 切法(三類不混)

1. 🔴 test+fix:tc4 snapshot 指紋不清 attempts(紅先行)
2. 🔴 test+chore:VX sparse(先改測試集合紅 → 兩處設定綠)
3. 🟢 index 日曆誤標 WARNING
4. 🟢 futures 1K 落後 / 缺格 WARNING
5. 🟢 capital 損益列回填 INFO
6. chore(docs):skill 一句 + next-time 勾銷
