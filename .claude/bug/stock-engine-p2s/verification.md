# verification — stock-engine-p2s(E-2/E-3/E-4/E-5 批次)

分支:`fix/stock-engine-p2s`(8 commits on 29004dc8)

## Phase 6|自動化 gate(主 session 親跑)

| gate | 結果 | exit |
|---|---|---|
| pytest -q | 2546 passed, 1 skipped | 0 |
| ruff check copycat tests | All checks passed! | 0 |
| pyright | 0 errors | 0 |
| replay ×2(--data-dir 主 tree)+ validate | 42/42 PASS | 0 |

## Phase 7|真實環境驗證

本批四條皆為 rollover / 訂閱池狀態機時序缺陷,deterministic 重現只存在於
受控時序(紅測試以 fake source 構造),真實環境層 = **prod 重啟後首個交易日
的觀察項**(與既有待重啟清單同批):
- 08:45–09:00 合約主圖分時有成交(E-3;先前為空到 09:00)
- 自選移除再加回後群組卡片分鐘序列完整(E-2)
偵測性 sanity:`grep "rollover stage2" prod log` 應在 08:45(合約 main 時)
或 09:00(現貨)出現一次。

## Phase 8|反向驗證(主 session 親跑)

`git revert --no-commit 4d084100 38e56012 f91aa6f6 7aa007f9` → 跑
test_stock_engine.py:**5 failed, 100 passed** —— 恰為五條新紅測試
(E-5 stage2 迭代 / E-3 合約 tick 完成 stage2 / E-4 no_data 存活 /
E-2 記帳重啟 ×2),各自失敗訊息 = 原 bug 樣態。
`git reset --hard HEAD` + sleep 1 → 還原後全綠(pytest 2546)。

## Phase 9|留尾巴

- 補市日(週六)+ 自選空 + 主圖合約:checkpoint 不武裝(weekday>=5)且無現貨
  快路徑 → 仍整天不換日。極罕見組合,已在 E-3 修法註解記載;記 next-time。
