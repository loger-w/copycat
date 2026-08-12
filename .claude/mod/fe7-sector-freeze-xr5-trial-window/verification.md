# 驗證記錄 — mod/fe7-sector-freeze-xr5-trial-window(2026-08-12)

grilling 拍板兩項 UX 決策後的小輪實作:FE-7 類股強弱排序凍結、XR-5 試撮窗排除。

## 自動化驗證(review 修復後最終輪)

| Gate | 指令 | 結果 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **2612 passed**(改動前 2608;+4 = 試撮 gate×2 / 開盤界×1 / 窗界×1,minute-domain param 08:59→13:35 淨 0) |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS |
| 前端測試 | `npm test` | **1738 passed**(改動前 1736;凍結 describe 5→7 條,含 C-1 紅先行) |
| 前端型別 | `npx tsc -b` | exit 0 |
| 前端 lint | `npx eslint src` | exit 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |

## TDD 紅綠證據

- XR-5 config:`test_default_values` / `test_load_override` 先改 09:00 斷言 → 2 failed
  (`08:55 != 09:00`)→ 改預設 → 綠。
- C-2 gate:`test_trial_window_snapshot_fully_rejected[08:30:00|08:59:59]` 先行 →
  2 failed(counts 收進去了)→ `_apply` 加 gate → 141 passed(整檔)。
- FE-7:凍結三測試先行 → 3 failed(`sector-frozen` 不存在 / 順序跟著跳)→ 實作 → 綠。
- C-1:「鑽取子產業後收合父列」先行 → 1 failed(chip 殘留)→ engaged 改畫面同構 → 綠。

## 真實環境驗證

本輪為純邏輯改動(config 預設值 + 引擎資料時刻 gate + 前端排序凍結),真實環境行為
依賴盤中時窗(08:55–09:01 的試撮→開盤過渡、盤中 10s 輪詢重排),本日 13:00+ 已過
可觀測窗。盤中驗證項留待 prod 重啟後下一個交易日:

- [ ] 09:00 前開頁:家數帶/類股顯示昨日資料(非試撮值),09:00:1x 起換當日。
- [ ] 盤中展開類股 → 「排序已凍結」標籤出現、列不位移、數字照跳;全收合恢復重排。

(與 memory 慣例一致:盤中層驗證統一掛在 prod 重啟後 user 過目清單。)
