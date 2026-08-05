# progress ledger — intraday-volume-profile

plan: .claude/feat/intraday-volume-profile/implementation/PLAN.md(v2)
branch: feat/intraday-volume-profile(start 24a8f64)

| task | 狀態 | commits | review |
|---|---|---|---|
| T1+T2 lib 層(stock-accum + volume-profile) | done | 580b0ff [red] → b9292d3 [green](main 補 tag amend) | main gate PASS(34 lib tests + 全前端 1148 綠、tsc/eslint 0;偏離 4 條合理;交接:fixture 紅要等 T3 接線才現形) |
| T3 toggles + 元件 + 既有測試遷移 | done | 6928589 [red] → 6a6e70a 對齊 → 662a8a6 [green] | main gate PASS(全前端 1154 綠、tsc/eslint 0;偏離 2 條合理;SC-5 drawnRects 未打穿) |
| T4 Phase4 fix(A1/A2/B2 置中帶 + A3/B4/B1/A4/B3/B5) | done | 8161250 [red] → 3826ffa [green] | 1157 綠、tsc/eslint 0;偏離 1 條(y=top + 精確偏移斷言)合理,design 已同步 |
