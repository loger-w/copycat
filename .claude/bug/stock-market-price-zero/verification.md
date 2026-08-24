# stock-market-price-zero 驗證(2026-08-24)

- 紅測試先行:修前 `1 failed, 85 passed`(bstrPrice "590.00" ≠ "0")
- 修後:`pytest tests/capital/` **354 passed**;全套 `pytest -q` **2912 passed**
- 反向驗證:stash mapping.py → 紅回(1 failed)→ pop → 綠
- `ruff check copycat tests` PASS;`pyright` 0 errors
- diff:
 copycat/capital/mapping.py    |  6 +++++-
 tests/capital/test_mapping.py | 15 +++++++++++++++
 2 files changed, 20 insertions(+), 1 deletion(-)

- 真環境:待 prod 重啟 + user 安全首單(repro §真環境驗收)

## review round-1 後補(1 P1 / 5 P2 → 4 accepted 全收)
- C1(P1):字面 "0" 標註為推定未實測 + fallback "0.00" 寫進 mapping 註解與 repro(「必須為 0」本身已實證)。
- C4:既有 FOK 市價測試補 `bstrPrice == "0"`(防組合條件誤寫)。
- C2:blast radius 補「一鍵平倉同走 market、從未成功過」;驗收擴為兩筆。
- C3:repro 筆數更正 7 筆;改價場景理由更正。
- 複驗:tests/capital 354 passed / ruff / pyright PASS。
