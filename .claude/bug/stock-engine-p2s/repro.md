# repro — stock-engine-p2s(quintet review E-2/E-3/E-4/E-5,四條 P2 批次修)

來源:`.claude/bug/stkfut-order-channel/review-findings.md`(2026-08-06 五題整體 review,
stock_engine 精讀 reviewer,每條含 file:line trace + 自我反駁,主 session 覆核掛點)。
branch:`fix/stock-engine-p2s`(基準 29004dc8 = origin/master)。
四條皆為時序 / 狀態機缺陷,穩定重現 = 紅測試(deterministic 構造時序);
review trace 為蒐證,紅測試為執行證據。

## E-5:`_rollover_stage2` 迭代 `_states.values()` 撞 executor thread 的 setdefault

- trace:`stock_engine.py:650` 在 event loop 迭代;`_acquire`(:269/:280,經 to_thread
  在 executor thread)對 `_states` setdefault 插新鍵。`quotes()` 同 hazard 已防
  (:385 docstring 顯式辨識,test_quotes_survives_states_mutation_during_iteration 鎖住),
  :650 獨漏。
- 失效:RuntimeError 讓 stage2 跑一半中斷,`_pending_date` 已清 → 不再有第二次
  stage2;沒 reset 到的 state 整天 ingest=False;hub 沒收到 on_rollover。
- 修法:`for state in list(self._states.values())`(快照後迭代,零行為改動)。

## E-4:`set_watchlist` removed 分支無條件清 `_no_data`,與 A7d 守則相反

- trace:`stock_engine.py:312-314` 無 `not in self._refs` 判斷;鏡像路徑
  `set_main_contract`(:353-361)已依 code review A7d 做對(仍有 owner 不清,
  註解完整論證)。
- 失效:code 同時是 main + 自選,自自選移除 → 旗標被清,TC4 no-data 回呼一次性
  已發過 → 之後 snapshot 恆 no_data=False,「查無此檔」與「還沒推」合併成同一畫面。
- 修法:removed 迴圈改 `if code not in self._refs: self._no_data.discard(code)`。

## E-2:`_backfilled` / `_backfill_failed` 日別記帳不隨退訂作廢

- trace:清空點只有 `_rollover_stage2`(:657-658)與 `_handle_reconnect`(:716);
  removed 分支(:312-314)不動它們。移除再加回(`_acquire` setdefault 用回舊 state)
  後 `code not in self._backfilled` 恆假(:441)→ 群組回補永不重新入列,退訂期間
  的分鐘缺口整天補不回,`backfilling`/`no_data` 都是 False,畫面零訊號。
- 修法:**loop 側**清(`_release` 在 executor thread,記帳集合是 loop-only 不變式,
  不可在 `_release` 內動):
  - `set_watchlist` removed 迴圈:`if code not in self._refs:` 時一併
    `_backfilled.discard(code)`、`_backfill_failed.discard(code)`;
  - `set_main_contract` 的 A7d 區塊(:353)同步加(主圖槽位真退訂同理)。
  語意:真退訂 = 該檔的「今日已回補 / 失敗冷卻」判斷作廢,重新訂閱後回補
  機會重新開始(失敗冷卻歸零是接受的:re-acquire 是使用者驅動,非重試風暴)。

## E-3:rollover pending 期間(08:00–09:00)合約 tick 不觸發 stage2 → 08:45–09:00 成交被丟

- trace:`stock_engine.py:796-802` stage2 觸發要求 `rolls_the_day`(= 非期貨鍵);
  期貨日盤 08:45 開盤,pending 期間合約 tick 落到 :803 `state.ingest`,昨日
  `_last_cum` 使其恆 False(不 apply 不推播);現貨首筆 09:00 才觸發 stage2。
  極端:自選空 + 主圖合約 → 平日靠 checkpoint 武裝了 pending 但永遠等不到現貨
  首筆 → 整天不換日。
- 修法(主 session 拍板):**允許期貨鍵 tick 完成(complete)pending stage2**,
  stage1 武裝(:787-795 快路徑)仍限現貨 —— D14a 的雙保險不動:
  - 夜盤 tick 根本到不了這段(:738 `_in_futures_session` 整則早退),能到的期貨
    tick 必屬日盤 08:45–13:45,其 `trade_date` 即當日,無跨午夜歧義;
  - 00:00–05:00 夜盤時段 `_pending_date` 恆 None(checkpoint 08:00 才武裝、
    週六 weekday>=5 不武裝)→ 夜盤不可能誤觸;
  - 既有測試 `test_contract_tick_does_not_complete_a_pending_rollover` 鎖的是
    D14a 舊解讀,**事前標為該變**:改為「日盤合約 tick 完成 pending stage2」+
    新 regression「pending=None 時合約 tick 不武裝 stage1」。
  - 殘留已知限制:補市日(週六)+ 自選空 + 主圖合約時 checkpoint 不武裝、現貨
    快路徑也沒有現貨 tick → 仍整天不換日;極罕見,註解記載,不在本輪展開。

## 實驗記錄

- 掛點與執行緒歸屬由主 session 逐行覆核(:282-292 `_release` 在 executor thread、
  :650 迭代在 loop、:312-314 vs :353-361 不對稱、:738 夜盤整則早退保證)。
- 各條的執行證據 = 紅測試(見 Phase 8 反向驗證)。
