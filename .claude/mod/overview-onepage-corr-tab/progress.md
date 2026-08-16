# progress ledger — mod/overview-onepage-corr-tab

plan/spec:`.claude/mod/overview-onepage-corr-tab/change-spec.md`(現況 `current-state.md`)
branch:`mod/overview-onepage-corr-tab`(自 master `e18f61c5`)
baseline:`npm test` 112 files / 1830 tests 全綠(2026-08-16 18:28)

| # | 包 | 內容 | commit 範圍 | review |
|---|---|---|---|---|
| A | 🔵 註解 + 🔴 5.2a subtab 退役/CorrSection 刪 + 🔴 5.2c 家數帶 | f22fee4f..96207282(5 commits) | 完成 | gate 綠 46 files/794;tag 配對 OK;偏離兩項接受((l2) 超集鎖 getItem;CorrPage 檔頭留 C 包) |
| B | 🔴 5.2b 佈局 / 圖高 / 騰落線 / LimitList 容器 | 551ac58f..f6d690a3(10 commits,5 組 red→green) | 完成 | gate 綠 9 files/174(+17);全前端 1834 綠;偏離 7 項皆接受(w-full 不加 h-full / labelBounds 收斂 / BasisRow shrink-0 / overlayPair / :479 註解 / ADL 空態置中 / (k2) 恆 render 鎖);paneSvgHeight(430,300)=405/381/700 |
| C | 🟢 5.3 corr 頂層 tab + App.corr-tab.test | 31763eb9..2cb1fc37(2 commits) | 完成 | gate 綠 13 files/201;tag OK;偏離無(mutation 自檢用 git checkout 還原 — 已 commit 後無害,紀律上應用 Edit,記 feedback) |

spec review:round1 15 accepted(P0 1)/ round2 限縮 12 accepted(P0 0)→ 定案。

自評 round 1:lens whitelist-layout(跑中)+ tests-deadcode(9 P2 回收);全套 gate:tsc/vitest 1837/eslint/build 綠;doctor 新增 2 finding(MarketPane only-export-components:PANE_FRAMES/paneSvgHeight → 搬 lib);pytest 1 flake(既有 test_ws_streams_index_payload,單測 3/3 綠,後端零 diff);ruff/pyright 綠。截圖 subagent 跑中。

fix 波 1(code-review-round-1.json 15 條 + amendment r3):27410a52..29efabc2 14 commits(🔵2 / 🔴4 組 / 🟢4 lock),gate 74 files/1066 綠、doctor 無 issue;TD-3/KR-2 skill 引用由主 session 修(未 commit)。偏離 1(MarketPane root `@[1050px]:min-h-0` 量到左欄寬)判定為錯目標 → 追加 mini fix(SendMessage 同 agent)。
rollback 記錄:SC-4「縮 200 仍不捲」與地板互斥 → 失敗四分流 (4) 改寫 SC(amendment r3),SC-7 1280「整頁可捲」實作缺陷 → (2) 回實作(WL-1)。
mini fix ×2:fd07b571/7adda9c6(pane root min-h-0 無條件)、75a3caa0/5a111c68(連板/名稱 nowrap)。截圖補驗 SC-3/4/7 全 PASS。最終 gate:vitest 1852 / tsc / eslint / build / doctor 綠;tag 機驗 PASS(35 commits,14 red↔14 green)。self_review_head=5a111c68。
