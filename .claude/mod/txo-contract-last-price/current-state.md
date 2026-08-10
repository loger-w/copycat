# current-state:TXO snapshot per-contract last_price(2026-08-05)

Baseline:master(5341f37)全 gate 綠(本 session 稍早親跑:pytest 1672 passed / ruff /
pyright 0 / validate 42/42)。分支 mod/txo-contract-last-price。

## 現況

- `copycat/live/aggregate.py::_PosState`(:34-40):5 欄(net_qty / net_cost_millipts /
  volume / outer_qty / inner_qty)— **沒有累積最近成交價**。
- `_ingest`(:78-97):逐 tick 分類內外盤;stale-drop(cum 序)在最前早退;未分類 tick
  仍計 totals。每筆 tick 都有 `price_millipts`。
- `_contract_rows`(:117-134):7 欄(symbol/cp/strike/net_qty/volume/outer_qty/inner_qty),
  無 last_price;strike 升冪 C 前排序。
- `snapshot`(:136-202):`"contracts": self._contract_rows()`;價格慣例 = 毫點 int 內部、
  對外 `/1000` float(見 `spot.price`)。

## Caller map(grep 完整)

- `ChainAggregator` 建構/使用:`server/engine.py`(EngineRuntime,:59/:109/:161)、
  `live/handover.py:55`(run_handover)、測試。`_contract_rows` 僅 snapshot 內部。
- snapshot 消費端:REST `/api/txo/snapshot`(app.py:550-556)+ WS `/ws/txo/pnl`
  (app.py:558-566),**裸 dict 無 response_model** — 新欄不會被 FastAPI 過濾
  [amendment 2026-08-05: review P2-3 行號/route 名更正]→ 前端
  `types.ts::ContractRow`(**`last_price?: number | null` 已預留**,註解「點;snapshot
  契約只加不改」)→ `OrderPanel.tsx:57-58`(市價估價 = 該合約 last_price,缺值鎖市價選項,
  已有測試 OrderPanel.test.tsx:214/:231 鎖缺值行為)。
- 動態用法:grep `last_price` 全 repo — 只有前端預留 + next-time 條目,後端零讀者。
- [amendment 2026-08-05: review P2-3 補]`frontend/src/lib/tquote.ts` 亦 import ContractRow
  (T 字報價列)— additive 加欄不受影響。`run_handover`(live/handover.py:55-63)先
  ingest_backfill 再 flush buffer、self-heal 前 reset() → 無「回補舊價蓋掉 live 新價」
  時序風險(SC-4 成立依據)。`_PosState` 實際行號 :33-39。

## 既有測試盤點(加欄的爆點)

- `tests/live/test_aggregate.py::test_snapshot_contracts_detail`(:221-249):
  **contracts rows 精確 dict 相等** → 加欄必紅(該紅 🔴,契約已預告「只加不改」=
  additive 加欄是預告過的變化,assertion 屬事前標為該變)。
- `tests/live/test_replay_golden.py::test_replay_golden_snapshot_locked`:snapshot 與
  `tests/fixtures/txo_golden/expected_snapshot.json` **全等** → 加欄必紅(該紅 🔴)。
  fixture 再生:`tests/fixtures/txo_golden/regen.py`(比對非 contracts 部分,diff 非零
  不覆寫 exit 1)。
- `test_contracts_invariants` / `test_contracts_reset_cleared` / `test_app.py:136,144`:
  按鍵取值,不受加欄影響(不該紅)。
- 前端 `OrderPanel.test.tsx`:fixture 已含 last_price,行為不變(不動)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| _PosState | 無最近成交價 | 加 `last_price_millipts: int \| None = None`,`_ingest` 逐 tick 記(過 stale-drop 後;含未分類 tick — 成交價與內外盤分類無關) |
| _contract_rows | 7 欄 | 加 `"last_price": millipts/1000 float 或 None`(對齊 spot.price 慣例與前端「點」註解) |
| wire 契約 | contracts row 7 欄 | additive 加欄(前端 optional 已預留,舊 client 不讀新欄零影響) |
| backfill 路徑 | ingest_backfill → _ingest | 天然涵蓋(排序後最後一筆 = 時序最後成交價) |
| reset | 清 _pos | last_price 隨 _PosState 一起清(序列切換不留舊價)— 天然行為 |
| migration | — | 無(無持久化;golden fixture 用 regen.py 重生) |
