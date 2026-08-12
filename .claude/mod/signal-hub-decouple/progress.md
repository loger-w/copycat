# progress ledger — mod/signal-hub-decouple

plan/spec:.claude/mod/signal-hub-decouple/change-spec.md(round-2 review 收斂版)
現況:.claude/mod/signal-hub-decouple/current-state.md
baseline:2595 passed(2026-08-12,master 1adf9ee9)

## 包切分

- 包 1(單 implementer,序列三段):
  1. 🔵 stock_engine.py ws 注入參數(行為不變)
  2. 🔴 [red] 該紅 4 條改寫 + 新測試 T1-T6 + tests/server/conftest.py(test-infra)
  3. 🔴 [green] app.py(stock_ws / _make_signals / _signals gate / /ws/stock)+
     __main__.py(verify 落點)
  依賴:3 依賴 1 的新參數與 2 的紅測試 → 不可平行,單包序列。

## Task log

- 包 1 完成(implementer opus,2026-08-12):
  - 11504521 🔵 refactor(server): stock engine WS broadcaster 可注入 [refactor]
  - 6abd3e22 🔴 test(server): XR-3 hub 獨立存活行為紅測試 [red](紅證據 8 failed/78 passed)
  - 2ccd6619 🔴 fix(server): SignalHub 解耦 [green](red→green for 6abd3e22)
  - 觸及 gate:tests/server 1093 passed / ruff clean / pyright 0 errors
  - 偏離 3 處(narrowing 寫法 / portal assert / T1 併該紅第一條)— 皆非行為面,accepted
  - main session 複核:pyright + ruff CLI 全綠(IDE 注入殘影不採信);全套 pytest 波尾跑中
