# verification — mod/ladder-pills-avgpct(R6,2026-08-17)

## 自動化(worktree,HEAD 9 commits on master 0242c9c1)
| 指令 | 結果 | exit |
|---|---|---|
| `npx tsc -b` | PASS | 0 |
| `npx eslint src` | PASS | 0 |
| `npx vitest run` | **119 files / 1971 passed**(baseline 1961 → +10;第一輪曾 1 flake 重跑全綠) | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | 1 warning = PriceLadder:39 TRADE_KINDS export(master 同在);中途新增的 no-giant-component(PriceLadder)/ prefer-module-scope-pure-function(avgBadge)已以 🔵 抽出歸零 | 0 |
| `pytest -q` / `ruff check` / `pyright` | 2635 passed 3 skipped / All checks passed / 0 errors(後端零改動) | 0 |
| `check_feat_tags.py` | PASS(flow=mod) | 0 |

## 真實環境(fake server 8721(R5 evidence 樣板:FakeCapital WS open + PushingFuturesSource)+ vite dev 5180 自 worktree;claude-in-chrome)
| SC | 結果 | 證據 |
|---|---|---|
| SC-1 | 武裝列 `[武裝][鎖定][現股 融資 融券 無券]` 同列(aside 288px,row 257px,pill 各 34→30px);現股選中 accent;選融券 → 融券 warn 琥珀、其餘灰框;armed+locked 態(解除+鎖定中)仍同列且武裝鈕無溢出(69px,scrollWidth==clientWidth) | `evidence/SC-1_pills_288.png`(修前 px-1)、`SC-1_pills_288_armed_locked_before_fix.png`(貼齊零餘裕)、`SC-1_pills_288_armed_locked_margin.png`(px-0.5 + warn) |
| SC-2 | 點「無券」→ 買側全 disabled、賣側可點;點回「現股」買側恢復 | JS 讀值 |
| SC-3 | 選無券 → 切委託 → 回閃電 → 仍無券 pressed | JS 讀值 |
| SC-4 | 群組列「四檔 +0.88% 4」「六檔 +1.12% 6」…(紅字),未分組列無 %;title「平均漲幅 +x%(4/4 檔有成交)」 | `evidence/SC-4_group_avg.png`、`full_page.jpg` |
| 未改功能抽樣 | 個股分時圖 / 五檔 / R5 鎖定鈕照常 | 截圖 |
限制:fake 資料流(夜間無 TC4 / 群益);試撮 title 分支僅 vitest 覆蓋。
