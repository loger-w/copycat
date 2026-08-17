# progress ledger — mod/intraday-fill-marks
對應 spec:`.claude/mod/intraday-fill-marks/change-spec.md`(現況表 `current-state.md`)

| 時間 | 項 | 狀態 / commit / 備註 |
|---|---|---|
| 2026-08-17 | §0 開工 | branch `mod/intraday-fill-marks` off master 0c0322ad;artifact 目錄建立 |
| 2026-08-17 | §1 baseline | `npm test -- --run` 120 files / 2027 tests 全綠 |
| 2026-08-17 | §2 spec | current-state.md + change-spec.md 落檔;evidence/sidecar_server.py(R1 樣板 + /_fake/fill)已試跑注入成功 |
| 2026-08-17 | §3 spec review | round 1 dispatched(change-spec-reviewer, opus) |
| 2026-08-17 | §3 review round 1 | 13 findings(P0×1 / P1×6 / P2×6)全 accepted → spec amendment(JSON `change-spec-review-round-1.json`) |
| 2026-08-17 | §3 review round 2(限縮) | 8 findings(P1×4 / P2×4)全 accepted → spec amendment r2;無 P0 → 退出(JSON `change-spec-review-round-2.json`) |
| 2026-08-17 | §4 包 A dispatch | opus implementer(`dispatch-pkgA.md`):ymdOf 🔵 / fill-marks.ts / useChartToggles.fills / tsc 該紅四檔 |
| 2026-08-17 | §4 包 A 完成 | commits 02cba5ae(🔵 ymdOf)/ 795d131c→10e007ef(SC-1 red→green)/ 61962c65→88479a43(SC-2 red→green);觸及範圍 gate 238 tests 綠 + tsc + eslint 0;tag 自檢 OK;主 session gate 過 |
| 2026-08-17 | §4 包 B dispatch | opus implementer(`dispatch-pkgB.md`):core 標記 / readout / toggle 鈕 + Card / GroupGridView / StockChart 接線 + SC-3~7/9 測試 |
| 2026-08-17 | §4 包 B 完成 | 6 commits(afcb41b2→7d54998c SC-3/4/5/9;bdfc8525→00b1e62c SC-5 圖牆/SC-6;2f62647a→22d9420c SC-7);SC-9 併 pair 1(偏離已記 body);波尾全套 vitest 121 files / 2094 tests 綠、tsc 0、eslint 0、react-doctor 只有存量 finding |
| 2026-08-17 | §5 code review round 1 | lens A(白名單/行為)P2×4、lens B(mutation)P1×1 + P2×6 → `code-review-round-1.json`;accepted 9 / rejected 2;fix 波 1 dispatched(`dispatch-fix1.md`) |
| 2026-08-17 | §6 real-env(與 fix 波平行) | 側車 8721(fake capital + stkfut catalog)+ vite 5173:page ▲/▼ + hover readout「成交 買 3@1195.33」/ toggle 關 0 開回 / 圖牆 2330×2、2317×1、其餘 0、牆頂 toggle 同步 / 個股期 CDF 202608 `fill-B-570` + readout「成交 買 2@1190」;截圖 evidence/SC-8-*.png |
