# current-state — 個股訊號降噪(mod/signal-denoise)

分流判定:**已成形方案**(需求指名落點 signal_state / SignalHub / 規則 params、四條做法明確;
決策點可逐分支追問)→ grilling 姿態,逐題 `[auto-default]`。

## 0. 動機證據(2026-08-17 盤中)

`data/signals/20260817.jsonl` 192 則 / 33 檔:CDP 穿越 120(62%)、爆拉 24 / 爆跌 27、
鎖停 9 / 打開 4、爆量 8。09 點檔 131 則。噪音四型:
1. CDP 同線來回:`touch_count>=2` 61 則、`>=3` 32 則(2484 cdp ×7、3105 ah ×7、2492 nl ×6)。
   每次都有真離線 ≥5 tick 再回來,間隔 15–25 分 > 冷卻 600s → 現行 rearm(5 tick)+ 冷卻擋不住。
2. 同一 tick 多則:13 個時點多出 14 則(cdp+crash 同秒 ×7、4979 一秒三則、6182 vol+lock)。
3. 爆拉/爆跌乒乓:51 則中 15 則是 30 分內反向第二則(冷卻 per (code, kind) 分開)。
4. 2492 六則全在 price == nl 線價(292000):`prev > v >= price` 把「碰到線」算穿越。

回放(1 分 K 重建 tick;基準版 136 vs 實際 120,近似誤差 ~13%):
駐留 5 分 → 97(−29%)、駐留 10 分 → 83、±3 tick(user 原提)→ 174(更鬆,否決)。(此為獨立 sim;餵真 detector 的基準版 = 134,見 replay_cdp.py。)
單穿一兩次的股票(2408/3006/3037/8064)在駐留版本下則數不變。

## 1. 現況表(逐檔)

| 檔 | 現況 | 目標 | caller 影響 |
|---|---|---|---|
| `copycat/signals_config.py` `SignalsConfig` | `cdp_rearm_ticks=5`、`cdp_cooldown_secs=600`、`surge_cooldown_secs=1800`… | 加 `cdp_rearm_dwell_secs: float = 300.0` | `configs/signals.json`(repo 未附)逐鍵覆寫;`load_dataclass_json` 未知鍵 raise — 新鍵加在 dataclass 即可 |
| `copycat/live/signal_state.py` `SignalDetector` | `_suppressed: set[(code, level)]`;rearm = 任一 tick `abs(price-value) >= rearm_ticks*tick` 立刻解除(:280-283);穿越判定 `prev < v <= price` / `prev > v >= price`(:291-296);surge/crash 冷卻鍵 `(code, kind, "")`(:350-353) | (1) `_suppressed` → `dict[(code, level), float|None]`(線外起算 mono;None=線內);解除 = 連續線外 ≥ dwell;(2) 穿越改「線上點透明」的側別追蹤(見 spec D2);(3) surge/crash 共用冷卻鍵 `(code, "surge_crash", "")`,touch 鍵不變 | 唯一實例化點 `signal_hub._make_slot`(rule_config → per-rule cfg);`reset_day` / `drop_code` 清 `_suppressed`(:166 / :176)要跟著改型別;`evaluate_book` 不碰 CDP |
| `copycat/signal_rules.py` | `PARAM_SPECS["cdp_cross"] = {"rearm_ticks": (0, 50)}`(**精確鍵集合**,多缺鍵皆 INVALID_RULE);`_seed_params`;`rule_config` 映射;`_CACHE_VERSION = 1`;`load_rules` 版本不符 raise | 加 `rearm_dwell_secs: (0, 3600)`(float);seed 帶 `cfg.cdp_rearm_dwell_secs`;`rule_config` 映射到 `cdp_rearm_dwell_secs`;**migration**:既有 `data/signal_rules.json`(v1,cdp 規則只有 rearm_ticks)在精確鍵集合下會整檔 INVALID → hub raise → 503。需 v1→v2 轉換(cdp_cross 規則缺 `rearm_dwell_secs` 補預設 300)+ `_CACHE_VERSION=2` | REST `PUT/POST /api/stock/signals/rules`(`test_signal_routes.py`)走 `normalize_rule`;前端送 params 必帶新鍵 |
| `copycat/server/signal_hub.py` | `_emit` 每事件一 row → `_publish`(WS)+ jsonl 佇列 + Discord 佇列;`_discord_worker` 逐 row `_send_discord`;`format_signal_text(row)`(bot 與 webhook 共用);`_event_id` 含 rule_id + levels + time_key | Discord worker 把**佇列中連續同 (code, time) 的 row** 合成一則(one-slot lookahead);新 `format_signal_group_text(rows)`;jsonl / WS / id **不動** | `discord_bot` 只吃 hub 給的字串(`attach_discord(sender)`);`notify.py` webhook fallback 同 |
| `frontend/src/lib/signal-model.ts` | `SignalMsg` / `kindLabel` / `mergeSignals`(id 去重 + time 降冪) | 加 `groupSignals(signals)`:相鄰同 (code, time) 併成一組(純函式) | 消費者 `SignalRail`(列表)、`useSignalAlerts`(toast,**不改**) |
| `frontend/src/components/stock/SignalRail.tsx` | `signals.map` 每則一 `<li key=id>` | 改吃 `groupSignals` 輸出:一組一列,kind 文案以「・」串接、規則名去重串接 | `StockPage` 傳 `signals`(不變);`SignalRail.test.tsx` 既有列數斷言要看 |
| `frontend/src/components/stock/SignalRulesDialog.tsx` | `PARAM_FIELDS.cdp_cross = [rearm_ticks]`、`DEFAULT_PARAMS.cdp_cross = {rearm_ticks:"2"}`、`ruleSummary` 印 rearm tick | 加 `rearm_dwell_secs` 欄(label「線外駐留秒數」)、預設 "300"、摘要加「駐留 N 秒」 | `useSignalRules` 型別 `params: Record<string, number>` 不用改 |
| `data/signal_rules.json`(runtime,gitignored) | v1、cdp 規則 `params={"rearm_ticks":5.0}` | 載入時轉 v2 記憶體形;下次 upsert 才落 v2 | 回退路徑:見 spec migration 節 |

## 2. Caller map(grep 結果)

- `SignalDetector(`:`signal_hub._make_slot`(唯一)+ tests。
- `_suppressed`:signal_state 內部(`__init__` / `reset_day` / `drop_code` / `_eval_cdp`)+
  `tests/live/test_signal_state.py`(白盒?grep 確認:無直接引用 `_suppressed`)。
- `cdp_rearm_ticks`:signals_config / signal_state:280 / signal_rules(seed、rule_config)/ tests。
- `PARAM_SPECS` / `rearm_ticks`:signal_rules、tests/test_signal_rules.py、tests/server/test_signal_routes.py、
  frontend SignalRulesDialog(+test)、useSignalRules.test。
- `format_signal_text`:signal_hub `_send_discord`、tests/server/test_signal_hub.py;discord_bot 不直接呼叫。
- `_discord_worker` / `_send_discord`:hub 內部;`attach_discord` 由 app 接 bot。
- 前端 `mergeSignals` / `kindLabel`:SignalRail、useSignalFeed、useSignalAlerts、tests。
- 動態用法:規則 params 以 dict 鍵存取(`params["rearm_ticks"]`)— 前端 `p.rearm_ticks`。

## 3. Backward compat / migration

- 規則檔 v1 → v2:載入時對 `kind == cdp_cross` 且缺 `rearm_dwell_secs` 者補模組常數 `_DEFAULT_REARM_DWELL_SECS = 300.0`(非 cfg;`load_rules` 簽名不動 — R10)
  預設;其餘 kind 不動;version 1 → 2 後走 `normalize_rule`。**不在載入時回寫檔案**(回退窗:
  尚未 upsert 前舊碼仍讀得到 v1 檔)。upsert 後檔案為 v2 — 舊碼讀 v2 會 raise(既有「版本不符
  raise」語意)。回退手順:刪 cdp 規則的 `rearm_dwell_secs` 鍵 + `_cache_version` 改 1。
- REST:前端舊版送不帶 `rearm_dwell_secs` 的 cdp 規則 → INVALID_RULE(精確集合語意保留;
  前後端同版部署,無 rolling deploy)。
- jsonl / WS / id / `/api/stock/signals/today` 形狀零改動。
- `configs/signals.json` 若存在且無新鍵 → 套預設 300(dataclass 預設,不是錯)。

## 4. 既有測試盤點(該紅 / 不該紅)

- `tests/live/test_signal_state.py::TestCdpCross::test_rearm_released_at_five_ticks`:**該紅**
  (+700s 一筆 79.50 即解除;新規則需線外連續 300s)。改法:離線後推進 300s 再一筆線外 tick → 解除。
- `::test_cooldown_blocks_second_cross`:斷言第一筆 79_500 為 `[]`(rearm 解除但冷卻擋)— 新規則
  下同為 `[]`(未 dwell),**不該紅**但語意變(註解要改)。
- `::test_rearm_not_released_within_five_ticks`:不該紅。
- surge/crash:`test_surge_emits` / `test_crash_emits` / `test_cooldown_blocks_second_surge`:不該紅;
  新增 surge→crash 共用冷卻測試(紅先行)。
- `tests/test_signal_rules.py`:所有以 `{"rearm_ticks": ...}` 精確集合的 fixture **該紅**(缺新鍵 →
  INVALID);load v1 檔測試該紅(需 v2 或轉換)。
- `tests/server/test_signal_routes.py` / `test_signal_hub.py`:帶 cdp params 的 payload 該紅(同上);
  Discord 送出次數斷言若有同 tick 多事件 → 看情況。
- frontend `SignalRulesDialog.test.tsx` / `useSignalRules.test.tsx`:`params: { rearm_ticks: 2 }` fixture
  該紅(型別不擋,但摘要文案 / 欄位數斷言可能紅)。`SignalRail.test.tsx` 列數斷言若含同 (code,time)
  多則 → 該紅。
