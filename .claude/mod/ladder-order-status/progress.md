# progress — mod/ladder-order-status

對應 spec:`.claude/mod/ladder-order-status/change-spec.md`(含 amendment 2026-08-13 / 13b)
現況表:`.claude/mod/ladder-order-status/current-state.md`

## Phase 記錄

- §0-1:branch `mod/ladder-order-status`;baseline backend 2622 / frontend 1741 全綠。
- §2-3:change-spec + review round-1(P0×1/P1×4/P2×6 全 accepted)+ 限縮加輪
  (P1×3/P2×5 全 accepted,無 P0)→ review 退出。兩輪 findings 吸收於 spec 兩個
  amendment 節。
- §4 計畫:兩包序列 dispatch(opus)—
  - 包 B(後端):🟢[red] SC-5/SC-7 測試 → 🔴[green] client.py debounce 0.5 +
    in-flight 守門;+ A7 unit lock(tests/capital)。
  - 包 F(前端):🔵 抽 lib/ladder-lots → 🟢[red] 三座梯 + lib 測試 → 🔴[green]
    LadderView/FuturesLadder/futures-ladder.ts/兩 container。

## Task ledger

- [done 2026-08-13] 包 B(後端):6da49d25 🟢[red] / e32fb85f 🟢[lock merge] /
  0f648d8a 🟢[lock unit] / 2e907e55 🔴[green]。gate:pytest tests/capital 314 passed、
  ruff/pyright PASS、全套 2629 passed(implementer 自跑)+ main 親跑 pyright 0 errors。
  review gate:diff 逐行對照 amendment R1/A1/A5 吻合;偏離 3 條全數合理(SC-7(d) 天生
  無紅可先行 / A7 獨立 lock commit / degraded 不清旗標為 A5 正解)。
- [done 2026-08-13] 包 F(前端):08982a8d 🔵[refactor] / 3f031436 🟢[red] /
  67587ae5 🔴[green]。gate:vitest 觸及 133 passed、tsc/eslint 0、react-doctor 零新增;
  紅 commit 當下 26 failed 全在預告範圍。偏離 5 條合理(2 案天生綠轉 lock 性質 /
  同步錨補強 / 拆案 / text-[10px] 沿紅方格幾何 / CLAUDE.md §4 留收尾)。
- [done 2026-08-13] §6 波尾全套 gate(main 親跑):backend pytest 2629 / ruff / pyright 0 /
  validate 42/42;frontend 1768 / tsc 0 / eslint 0。
- [done 2026-08-13] §5 自評 review round-1:3 lens(白名單/正確性/覆蓋)→
  `code-review-round-1.json`。白名單 10 條全 PRESERVED;P0×0 / P1×4(C1 rc≠0 吃 due +
  T1/T2/T3 渲染分界無鎖)/ P2×14(accepted 大宗;C2/W2 collector 輪次化 rejected →
  docs/next-time.md 2026-08-13 節)。
- [done 2026-08-13] fix 波:255f7552 🟢[red] / 9886013e 🔴[green] / 1e7552ed 🟢[lock] /
  9f997844 🟢[red] / 11e0e11e 🔴[green] / 5ae047e5 🟢[lock]。gate:pytest 2631 / vitest
  1778 / ruff / pyright / tsc / eslint 全 0;mutation 證據 5 件(a-e,見 dispatch 回報與
  commit body);LadderView.test.tsx 新檔(prop 介面級守門案)。W4 留收尾已補
  (CLAUDE.md §4)。self_review_head = 5ae047e5。
- [done 2026-08-13] §8:check_feat_tags PASS(13 commits);artifact commit 5956f2d9。
