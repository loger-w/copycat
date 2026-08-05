# progress ledger — signal-rules

plan: .claude/feat/signal-rules/implementation/PLAN.md(v2)
branch: feat/signal-rules(start a3d567c)

| task | 狀態 | commits | review |
|---|---|---|---|
| T1 signal_rules 模型 | done | bb005f2 [red] → 48300c2 [green] | main gate PASS(104+全案 1926 綠、pyright 0 親驗;偏離 6 條合理 — clamp 限遷移、OSError 不轉碼、int-valued float 收、id 非空、params float 化、load 重複 id 拒) |
| T2 hub 規則引擎(純加法) | done | 6bf0212 [red] → 46f2223 [green] | main gate PASS(62+全案 1959 綠、pyright 0 親驗;偏離 7 條合理 — :461 提前改寫有據、_cfg 沿用、epoch 走 now_fn、worker 例外餵 None 界定、ctx 外層 try、detector staged 家族閒置留 T3b 後清點) |
| T3 rules routes | done | a9e68cc [red] → a4d45ae [green] | main gate PASS(親驗綠;RuleBody object 欄防 pydantic 寬鬆轉型是好解) |
| T3b enabled 家族退役(🔴) | done | e8ae823 [red] → 970875e 🔴[green] | main gate PASS(全案 1970 綠、pyright 0 親驗;偏離 5 條合理 — 行號改名稱定位、helper 修正入 green body) |
| T4 前端 | done | e955e82 chore → 2bc15b0 [red] → bb91f9c [green](含 🔴 filterKinds 註記) | main gate PASS(1182/79 檔綠、tsc 0 親驗;偏離 7 條 — 偏離 3(feed 取代制)待 Phase 4 fix 改並列) |
