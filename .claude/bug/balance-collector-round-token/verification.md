# verification — bug/balance-collector-round-token(R7)
## 自動化(2026-08-21 20:4x):pytest 2853 passed(baseline 2840 → +13)| ruff All checks passed | pyright 0 | 前端未動
## 紅測試 → 綠:初版 4 支(遲到 ## 清空部位)+ review round 1 三支(F1 inflight 未清 / F2 真空帳戶時間窗 / F3 rc≠0 保欠帳)皆先紅後綠。
## 反向驗證:round 1 `git revert --no-commit 66ace43f` → 4 紅;round 2 `git revert --no-commit 21931840` → 3 紅;還原後 347 passed(repro.md 兩節追記)。
## Mutation:13/13 killed(abandon 清本輪 / awaiting 守門 / 時間窗 / 收 row 關窗 / keep_abandoned 三接線 / inflight / rc 順序 / reconnect 清欠帳 / STALE_WINDOW_S)。
## Blast radius:BalanceCollector 唯一 caller client.py 三實例;tests/capital 347 綠;regression 抽樣 tests/server/test_capital_api 綠(全套內)。
## 真實環境:merge 後重啟 8721(health sha);死查詢 + 遲到 ## 無法刻意觸發 → 以 FakeCom 亂序事件測試為證;**user 盤中觀察部位面板不再瞬間清空**。
## 殘餘(F7,記 next-time):新輪已收 rows 時舊 `##` 會 flush 截斷快照(無 token 不可解);真空帳戶在死查詢後最晚下一輪(≤60s)才顯示無部位。
