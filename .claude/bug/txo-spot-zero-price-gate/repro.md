# repro:TXO spot 0 價閘

## 重現(loop)
`.venv\Scripts\python -m pytest -q tests/live/test_aggregate.py -k SpotZeroPriceGate`
修前:4 failed(index 1 diff: True != False —— 0 價被記價且算 changed)。
真環境(鎖停)不可等,以單元測試為 loop;handoff 已備齊證據。

## Root cause
`ChainAggregator.route` spot 分支(aggregate.py)只有同價短路,無 `> 0` 閘;對照 `_ingest` 同檔已有閘與理由
(鎖停時 TC4 於簿第一檔推市價佇列 0 價)。一次一變數:只加 `if tick.price_millipts <= 0: return False`。

## 驗證
- 紅測試 4 → 綠;tests/live/test_aggregate.py 35 passed
- gate:pytest 2804 passed / ruff clean / pyright 0 / `copycat validate` 42/42 PASS
- blast radius:route caller = engine.py:327(bool 標 changed)、handover.py:63(回補重放,0 價 spot 同樣該丟);
  spot_millipts 讀者 = engine.py:116 → app.py:740 txf_getter(OI 撐壓,受益)
- 反向驗證:`git revert --no-commit 198ad1f7`(保留測試)→ 4 failed;`revert --abort` → 35 passed
