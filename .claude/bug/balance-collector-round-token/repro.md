# repro — BalanceCollector 無輪次識別:遲到 `##` 清空部位顯示(bug/balance-collector-round-token,R7 / A4)

來源:rounds.md §R7(預核准);next-time 08-13 ladder-order-status 節(review C2/W2)。

## 症狀
零事件死查詢(GetRealBalanceReport 發出後 10s 內 COM 零事件)→ `_maybe_query_balance` 逾期解卡 → `_balance.reset()` + 第二次查詢 →
**第一輪遲到的 `##`** 抵達時 staging 為空 → `_flush()` → `_on_balance_complete([])` → pending=[] → 鏈收尾 `set_positions([])` → 有庫存顯示無部位、
平倉鍵鎖住(08-20 當沖空單修法後代價變大);且 `_closed=True` 後第二輪的 rows + `##` 全數被「本輪已 flush」丟棄 → 最壞 60s(下一次 stale 重查)才自癒。

## 最小重現(loop,紅測試)
`tests/capital/test_client.py`(FakeCom 可注入亂序事件):
1. `_mark_ready`,store 先有部位(餵一輪 rows + `##` 走完鏈)。
2. `_balance_due` 過期 → `_maybe_query_balance()` → 查詢 #1;**不餵任何事件**,把 `_balance_inflight_until` 設為過去 → 再 `_maybe_query_balance()` → 查詢 #2(`_balance_queries(com) == 2`)。
3. `_handle_balance("##")`(第一輪遲到終止符)→ **現況**:`_pending_sec == []`,走完鏈後 `store.positions()` 為空 = 紅。
4. 接著餵第二輪 rows + `##` → 現況被丟棄(`_closed`)→ 部位仍空。
期望:步驟 3 後 store 部位**不變**(不得以空集合覆蓋);步驟 4 後部位 = 第二輪 rows。

## Root cause
COM 回呼(OnRealBalanceReport / OnProfitLossGWReport / OnOpenInterest)**不帶任何查詢識別**,`##` 無法與發出的查詢配對;
collector 的 `reset()` 只清 staging 與 `_closed`,不知道「上一輪還欠一個 `##`」。逾期解卡本質上放棄了一輪,但 collector 沒有被告知。

## 修法(輪次 = 「被放棄的輪欠一個終止符」;`[auto-default]`)
- 真正的 per-event token 不可得(COM 無關聯欄)。rounds.md 候選「帶輪次序號驗 token」退化為:client 在**逾期解卡**路徑呼叫
  `collector.abandon()`(或 `reset(abandoned=True)`):collector 記 `_stale_terminators += 1`。
- `feed("##")`:若 `_stale_terminators > 0` **且本輪尚無任何 row 被餵**(`_fed_rows == 0`)→ 視為舊輪遲到終止符,`_stale_terminators -= 1`、**不 flush、不關閉**;
  否則照舊 flush。有 rows 抵達 → `_stale_terminators = 0`(有資料就是活的回應,不論屬哪輪,flush 它都是最新快照)。
- 正常 `reset()`(非逾期路徑)清 `_stale_terminators`(上一輪已正常完成)。
- poll timeout 路徑不變;`_closed` 語意不變(只針對「本輪已 flush」)。三個 collector 共用(profit / OI 的逾期解卡走 `_poll_pending` → `_finalize_positions`,
  下一輪 `reset()` 前也可能收到遲到 `##`:同一機制,profit/OI 的 reset 由鏈呼叫 → 在 `_poll_pending` 逾時路徑對 `_profit` / `_oi` 呼叫 `abandon()`)。
- 代價(明示):真空帳戶在死查詢後的第一輪空 `##` 會被當舊終止符忽略 → 最多 60s 後下一輪清空(vs 現況:有庫存被誤清空 + 平倉鎖)。
  `[auto-default: 寧可晚 60s 顯示「無部位」,不可誤顯示無部位 | reason: 平倉鍵依部位鎖解,誤清空 = 真錢面不可操作]`

## Blast radius
`BalanceCollector` 唯一 caller = `capital/client.py`(三實例);`reset()` 呼叫點 L381 / L399 / L442;逾期路徑 L373-377(balance)、`_poll_pending`(profit/OI)。
tests/capital/test_balance.py(collector 單元)、test_client.py(鏈)。

## 反向驗證
修復 commit `git revert --no-commit` → 紅測試該紅回來 → 還原 → 綠(追記於本檔末)。

## 反向驗證結果(2026-08-21)

紅測試(commit `846d7233`,4 支):
- `tests/capital/test_balance.py::test_collector_abandoned_round_ignores_late_end_marker`
- `tests/capital/test_balance.py::test_collector_reset_after_abandon_clears_stale_debt`
- `tests/capital/test_balance.py::test_collector_rows_clear_stale_debt`
- `tests/capital/test_client.py::test_late_end_marker_from_abandoned_round_keeps_positions`

修復前(fix 未進):三支 collector 單元 `AttributeError: 'BalanceCollector' object has no
attribute 'abandon'`;client 鏈測 `assert [] is None ... _pending_sec`(遲到 `##` flush 空集合
啟動了鏈)。

修復(commit `66ace43f`)後:`pytest -q tests/capital` → **338 passed**。

反向驗證:`git revert --no-commit 66ace43f` → 上述 4 支全部 **FAILED**(失敗訊息與修復前一致:
三支 AttributeError + `assert [] is None`,`4 failed in 0.70s`)→ `git revert --quit` +
`git checkout HEAD -- copycat/capital/balance.py copycat/capital/client.py` 還原
(工作區僅這兩檔被 revert 動到,還原後 `git status --short` 只剩本目錄與 node_modules 未追蹤)
→ 重跑 `pytest -q tests/capital` → **338 passed**。

Gate:`pytest -q` **2844 passed**(166s)/ `ruff check copycat tests` All checks passed /
`pyright` 0 errors, 0 warnings。

## Code review round 1 → 設計修正(`code-review-round-1.json`,14 條全 accepted)
- **P0 F1/T1**:修復誤把 `self._balance_inflight_until = None` 換成 `abandon()` → 旗標不清,每 50ms 重入再 abandon;必須補回。
- **P0 F2**:計數式欠帳對真空帳戶自我延續(每輪 abandon → 每輪零列 `##` 被吞)→ 幽靈部位永不清。改為**時間窗**:`abandon()` 記
  `_stale_until = monotonic + STALE_WINDOW_S(20s)`,零列 `##` 只在窗內被吞(遲到終止符不可能晚過 20s);窗外 `##` 照 flush。
  `[auto-default: 20s | reason: 鏈 timeout 10s 後 COM 遲到回應落在數秒內;真空帳戶最晚下一輪(≤60s)清空]`
- `_awaiting` 旗標(reset 設、flush / 吞終止符清);`abandon()` 非 awaiting → no-op(F4 double-count)。刪 `_fed_rows`(T6,與欠帳冗餘):任何 row → `_stale_until = None`。
- client:`*_abandoned` 旗標在 `rc == 0` 後才清(F3,三處);`_set_status("ok")` 清三旗標 + 三 collector `reset()`(F5)。
- log:吞 → WARNING(部位更新被抑制);abandon → DEBUG。
- 殘餘風險(F7,無 token 不可解):新輪已收 rows 時舊 `##` 會 flush 截斷快照並關閉本輪(機率 = 兩回應交錯在同一 ms 級窗),記 next-time。

## 反向驗證結果(round 2)

紅測試(commit `b4151b37`,3 支,全在 `tests/capital/test_client.py`):
- `test_dead_query_unlock_clears_inflight_and_abandons_once`(F1/T1)
- `test_empty_account_clears_positions_after_stale_window`(F2)
- `test_requery_rc_failure_keeps_abandon_debt`(F3)

修復前(fix 未進)訊息:
`TypeError: BalanceCollector.abandon() takes 1 positional argument but 2 were given`(F1,
spy 帶 `now_monotonic`)/ `TypeError: BalanceCollector.__init__() got an unexpected keyword
argument 'clock'`(F2)/ `assert False is True ... _balance_abandoned`(F3)。

修復 `21931840`(時間窗 + `_awaiting` 守門 + client 三處旗標)後 → `pytest -q tests/capital`
**341 passed**;再加 lock commit `d59267bf`(T2–T8 / F4 / F5)→ **347 passed**。

反向驗證:`git revert --no-commit 21931840` → 上述 3 支全部 **FAILED**(失敗訊息與修復前
一致,`3 failed in 0.20s`);同時 `tests/capital` 整包 collection error
(`ImportError: cannot import name 'STALE_WINDOW_S'` — lock 測試已依賴新常數,預期內)。
還原:`git revert --quit` + `git checkout HEAD -- copycat/capital/balance.py
copycat/capital/client.py tests/capital/test_balance.py`(revert 連同 fix commit 內的
既有測試改接一起退,故三檔一起還原)→ `git status --short` 只剩 node_modules 未追蹤 →
重跑 `pytest -q tests/capital` → **347 passed**。

Mutation 驗證(13 個變異體,逐一改壞 source → 跑 `tests/capital` → 還原;腳本在 scratchpad):
abandon 不清 staging / 不清 `_last_feed` / 無 `_awaiting` 守門、吞終止符不看時間窗、
`_flush` 不關 `_awaiting`、收到 row 不關窗、`reset` 不理 `keep_abandoned`、
client 解卡不清 inflight、balance 旗標在 rc 判定前清、profit/OI `reset` 丟掉
`keep_abandoned`、重連不清欠帳、`STALE_WINDOW_S` 20→0 —— **13/13 KILLED**。

Gate:`pytest -q` **2853 passed**(165s)/ `ruff check copycat tests` All checks passed /
`pyright` 0 errors, 0 warnings。

既有測試的適配(允許範圍內,明列):`test_collector_abandoned_round_ignores_late_end_marker`
/ `test_collector_reset_after_abandon_clears_stale_debt` / `test_collector_rows_clear_stale_debt`
三支在 `abandon()` 前補一行 `c.reset()` —— 新語意下 `abandon()` 只對「已發查詢、還在等
回應」(`_awaiting`)的 collector 記帳,處女態 collector 記帳等於 F4 要擋的那個 bug;
`reset()` = 發查詢,是最貼近真實 client 路徑的寫法。斷言本身未改動。
`test_late_end_marker_from_abandoned_round_keeps_positions` 的部位改由「真餵一輪」做出來
(取代 `store.set_positions`,review T2),斷言不變。
