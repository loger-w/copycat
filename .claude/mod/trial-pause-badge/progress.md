# Progress ledger — mod/trial-pause-badge

對應 spec:`.claude/mod/trial-pause-badge/change-spec.md`(+ current-state.md)

Baseline:pytest 2631 passed / vitest 1778 passed(2026-08-13,master 5dbe2bbc)。
Spec review:round 1(P0×1+P1×4+P2×6 全 accepted 修畢)、round 2 限縮(P1×2+P2×6 全修)→ 收斂。

## 包規劃(序列)

- 包 1(後端):stock_engine trial 推導 + payload/snapshot additive + flush 窗翻轉補推 +
  TradeStatus 觀測 log + pytest(SC-3/4/5/6)
- 包 2(前端):useStockStream / stock-accum / WatchlistSidebar / StockPage + fixture 補欄 +
  vitest(SC-1/2)

## Task log

- 包 1(後端)done:commits 6e1293f5 [red] → e1cabfc5 [green];動 stock_engine.py +
  test_stock_engine.py + test_stock_routes.py;觸及 gate 614 passed / ruff 0 / pyright 0。
  偏離 4 條(見 dispatch 回報):(1) 新增模組級 `_spot_trial_now()`(等價);(2) stage2
  清空語意 = 觸發那一則仍用昨日前值、之後重播種(spec 兩指令合成的實際語意,測試 docstring
  已載);(3) 測試 helper `_tap`;(4) 加 3 則同 SC 範圍測試。待包後 review gate 裁決。
  波尾 pyright 全案親跑 exit 0(IDE 診斷注入為殘影,已依 gate 為準裁決)。
- 包 2(前端)done:commits 4f2a46d2 [red] → ca01fdaf [green];實作 4 檔 + 測試 6 檔;
  觸及紅態 11 failed/186 passed → 綠態 197/197;全量 vitest 1794 passed;tsc/eslint/
  react-doctor(changed)全 0。零功能偏離;色用 text-amber-400(既有 badge 先例同款)。
- 波尾全量 pytest 2645 passed(baseline 2631+14)。
- Code review round 1(雙 lens):10 findings → SPEC-1 REFUTED(時序誤報)、9 accepted。
- Fix 波後端:6e219782 [red] → 31a67ac7 [green](D6-1 觀測窗 ±2s / IC-1 首見三分含
  SC-5(f) assertion 該變 / IC-5 stage1 清 / IC-2 真時鐘格式鎖 / IC-6 三小項 / D6-2
  docstring);觸及 200 passed + ruff/pyright 0。
- Fix 波前端:2815d20f [red] → 94382944 [green](IC-3 pendingTrial in-flight 守門 /
  IC-4 header noData gate / P2-AGG(1) min-w-0);觸及 149/149、全量 1797、tsc/eslint 0。
- next-time 兩筆 chore:7e2bfa0f / 83ed9e06。
- self_review_head = 94382944(記 change-spec.md 末尾)。
