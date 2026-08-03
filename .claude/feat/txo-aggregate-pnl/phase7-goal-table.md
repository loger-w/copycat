# Phase 7 結構化證據表(2026-07-18,HEAD 5e4efdc,全 gate 當日新鮮重跑)

| SC | 實作檔案:行號 | 自動化測試 + pass count | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 spike | spikes/txo_chain_probe.py(全檔);copycat/live/tc4.py:1-320 | tests/live/test_tc4.py 6 tests(分組/request 組裝/分頁) | spike exit 0 三斷言全過(docs/research/2026-07-18-txo-chain-probe.md);server 對真 TC4 全鏈跑通(281 檔訂閱/22,935 ticks 回補,real-env-round-1.json SC-1) | `infra_fail: 週六休市 — live 流/TXF spot 推播/heartbeat 遞延 2026-07-20`(= state.phase_6_blocked_reason) |
| SC-2 引擎 | copycat/live/models.py:1-135、payoff.py:1-100、aggregate.py:1-170、handover.py:1-55 | tests/live 51 tests(models 16/payoff 13/aggregate 15/handover 5 + tc4 6 計入 SC-1;pytest 總 505 passed) | 引擎輸出即 SC-3 snapshot 證據(BEP 42,632.9/curve 138 點,evidence/SC-3_snapshot.json) | 既有回測套件 454 tests 同跑全綠(505−51);copycat validate 42/42 |
| SC-3 server | copycat/server/engine.py:1-230、app.py:1-115、__main__.py | tests/server 15 tests(engine 9 + app 6) | curl happy(snapshot/series)+ edge(400 UNKNOWN_SERIES/404)輸出入 real-env-round-1.json;WS 瀏覽器實連推播(截圖之連線徽章「即時連線中」) | 同上 505 全綠 |
| SC-4 frontend | frontend/src/lib/pnl-svg.tsx、format.ts、hooks/useTxoSnapshot.ts、useSeries.ts、components/*.tsx、App.tsx | vitest 19 passed(6 檔);tsc -b 0 errors;eslint 0 | docs/specs/txo-aggregate-pnl/screenshots/SC-4_main-view.png(曲線分區著色/BEP 金點/指標卡/繁中/console 0 errors) | build 成功(dist gzip js 86KB) |
| SC-5 replay golden | tests/live/test_replay_golden.py + tests/fixtures/txo_golden/(1,679 筆真實 tick + golden JSON) | test_replay_golden 1 passed(snapshot 全等,人工核對數字量級:net short 263 口 call 曲線形狀合理) | golden 素材 = spike 真實錄檔(07-17 TX4 ATM±5) | 含在 pytest 505 |
| SC-6 gate | — | pytest 505 passed / ruff 0 / pyright 0 / validate 42/42 / tsc 0 / vitest 19 / eslint 0 / build 0(本 phase 全數新鮮重跑,exit code 逐一檢查無管線) | — | validate 42/42 = 既有 replay golden 未退化 |

判定:全列綠(SC-1 real-env 欄為契約允許的 `infra_fail` 註記,對應 phase_6_blocked_reason;design Known Risk 1 + parse_realtime 隔離層已控改動半徑)。
