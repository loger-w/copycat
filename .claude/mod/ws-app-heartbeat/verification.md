# verification — mod/ws-app-heartbeat(2026-08-20)

## 自動化(worktree `.claude/worktrees/ws-app-heartbeat`,HEAD 298e201f)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| backend 全套 | `.venv\Scripts\python -m pytest -q` | 2789 passed / 1 skipped(baseline 2780;首跑 2784+5 紅 = 跨午夜 23:59→00:02 日期切換,重跑全綠;test_bars 單跑 51 綠) | 0 |
| backend 觸及 | `pytest -q tests/server/test_ws_disconnect.py tests/server/test_app.py`(fix 波後) | 32 passed;test_ws_disconnect 3× 無 flake(實作包 20×3、fix 波 21×3) | 0 |
| ruff | `ruff check copycat tests` | All checks passed | 0 |
| pyright | `pyright` | 0 errors / 0 warnings | 0 |
| frontend 全套 | `npx vitest run` | 2309 passed / 1 failed(`App.test.tsx` capital WS 唯一掛載 — **baseline 同一條**全套負載 flake,單跑 36/36 綠) | 0 |
| frontend 觸及 | `npx vitest run src/hooks src/lib/ws-reconnect.test.ts`(fix 波後) | 288 passed(baseline 267) | 0 |
| tsc / eslint | `npx tsc -b` / `npx eslint src` | PASS / PASS | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 12 files,No issues found | 0 |
| validate | 不動 replay / engine,免跑(無 copycat/replay、engine 改動) | — | — |

TDD tag 實查(`git log --format=%s e55f6082..HEAD`):5 對 `[red]`→`[green]` 配對、body `red→green for <sha>` 皆指向本分支實存 red commit;`[lock]` 兩筆 body 註 mutation-verified;🔵/🔴/🟢 未混。

## 真實環境(側車 8899 = worktree code、零 ZMQ;vite 5199 proxy;Chrome MCP 分頁)

| SC | 結果 | 證據 |
|---|---|---|
| SC-1(c) ping 間隔 | PASS:首幀 snapshot,ping 10.01 / 20.01 / 30.01 s,gap 10.00 s | `evidence/SC-1_ping_interval.txt` |
| SC-2(c) 半死 → 重連 | PASS ×2 輪:stall 後最後一則 ping 起 30–35 s 觸發(console `txo-pnl: 30 s 無訊息,重連`,其餘 WS 34–35 s)→ 卸舊 socket 立即排重連 → stall 結束即 open | `evidence/SC-2_SC-7_watchdog_realenv.md` |
| SC-4(ii) 短命 cap | PASS:`/ws/capital`、`/ws/breadth`(engine 缺席 accept-then-close)重連間隔 5.0–6.0 s(cap 5 s + 背景分頁 timer 對齊),不再 1 Hz | `evidence/SC-4_backoff_realenv.txt` |
| SC-7 badge 序列 | PASS:「即時連線中」→「連線中斷,重試中」(~2 s)→「連線中」→ 恢復「即時連線中」;復原截圖 | `evidence/SC-7_badge_recovered_after_stall.jpg` + badge log |
| 抽 2 未改功能 | 個股頁 2330 分時 / 五檔 / 成交列仍由 /ws/stock 即時更新;選擇權頁 onOpen refetch 正常(footer「更新」時戳在重連後刷新) | 同上截圖 / badge log |
| SC-3 / SC-5 / SC-6 | 自動化測試(txo ping 不覆蓋 / 兩代 onerror / `grep "WS 心跳" CLAUDE.md` 命中 :151) | vitest / CLAUDE.md |

備註:Chrome MCP 分頁數次 `Page.captureScreenshot` 逾時(renderer 暫時無回應)— dev build 既有現象,非本輪改動;「連線中斷,重試中」僅持續 ~2 s 未截到靜態圖,以 badge log + console 時戳為主證(spec SC-7 已允許)。
