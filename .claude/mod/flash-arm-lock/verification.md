# verification — mod/flash-arm-lock(2026-08-17)

## 自動化(worktree `.claude/worktrees/flash-arm-lock`,HEAD = fe2c8e33 之後 8 commits,rebase onto master 59f62b42)
| 指令 | 結果 | exit |
|---|---|---|
| `npx tsc -b`(frontend/) | PASS | 0 |
| `npx eslint src` | PASS(0 warning) | 0 |
| `npx vitest run` | **118 files / 1961 tests passed**(baseline 1872 → +89 案;實作 +40、review 補強 +49) | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | 4 warnings 全存量(only-export-components ×3 / no-giant-component LadderView ×1,master 同在),新增 0 → PASS | 0 |
| `.venv\Scripts\python -m pytest -q` | 2635 passed, 3 skipped(後端零改動) | 0 |
| `ruff check copycat tests` / `pyright` | All checks passed / 0 errors 0 warnings | 0 |

## 真實環境(fake server 8721:R4 樣板 + `_FakeCapital`(/ws/capital 維持 open)+ `PushingFuturesSource`(EndDate → resolved_contract);vite dev 5180 自 worktree;claude-in-chrome;不真送單 — fake capital 無 submit 方法 → 5xx)
| SC | 操作 | 結果 | 證據 |
|---|---|---|---|
| SC-1 | 個股頁 2330 → 右欄武裝列 | 三控制項同列(武裝 153px / 鎖定 42px / 交易別 select),aside 288px,武裝列 29px 無換行;按「鎖定」→「解除」青底 + 「鎖定中」桃紅底 aria-pressed=true | `evidence/SC-1_stock_288_unlocked.png` / `SC-1_stock_288_locked.png` / `SC-1_full_page_locked_final_bundle.jpg` |
| SC-2 | 鎖定 → 點自選 2317 | 梯換 2317,仍「解除 / 鎖定中」 | `SC-2_switch_stock_2317_still_locked.jpg` |
| SC-3 | 鎖定 → 主 tab 期貨(TMF,合約已解析) | 期貨梯掛載即「解除 / 鎖定中」;切回個股仍鎖定 | `SC-3_futures_ladder_still_locked.jpg` |
| SC-4 | 鎖定 → 右欄 委託 → 閃電 | 仍「解除 / 鎖定中」 | JS 讀值(onOrdersTab=[] / backFlash=[解除,鎖定中]) |
| SC-6 | 鎖定 → 殺 fake server(WS closed) | 1.5s 後「武裝 / 鎖定(disabled)」= 解除 + 清鎖定 + SC-13 非 open 鎖定鈕 disabled | JS 讀值 |
| SC-7 | 鎖定 → 選擇權頁(無梯)→ window Esc → 回個股 | 「武裝 / 鎖定」 | JS 讀值 |
| SC-8 | 鎖定 → 點 賣 218 / 217.5 / 217(fake capital 5xx) | 第 3 次失敗後「武裝 / 鎖定」 | JS 讀值 |
| SC-9 | 鎖定中 點「鎖定中」→ 「解除 / 鎖定」(仍武裝);再點「鎖定」→ 鎖定中 | PASS | JS 讀值 |
| SC-10 | 鎖定 → F5 | 「武裝 / 鎖定」;localStorage 無 arm/lock 鍵 | JS 讀值 |
| S2(review) | 未鎖定 張數 5 → 換股 → 仍 5;鎖定 張數 10 → 換股 2308 → 回 1,仍鎖定 | PASS(fix 波 bundle,vite `--force` 重啟後) | JS 讀值 |
| SC-5 / SC-11 / SC-12 / SC-13 / S1 / S3 | vitest 覆蓋(閒置 6 分 fake timers / 白名單既有測試 / blocked-disabled 兩態 / connecting 不 disabled 已鎖定 / 遲到 ok 不歸零) | 全綠 | vitest |
| 未改功能抽樣 | 個股分時圖 + 群組圖牆(R4)照常;期貨頁五檔 / 分時照常 | PASS | 截圖 |

**限制**:真 TC4 / 真群益未在線(夜間),真實環境為 fake 資料流;S4 註明:真環境切期貨頁若 `resolved_contract` 尚未到齊會 E-3 自動解鎖需重按。
**教訓**:vite dev 對 rebase 改寫的檔案曾服舊 bundle(RightRail 無 S2 段),`--force` 重啟後才正確 — 真實環境驗證前先 curl 源檔確認含本輪標記。
