# progress ledger — mod/watchlist-ux-limit-50

對應 spec:`.claude/mod/watchlist-ux-limit-50/change-spec.md`(round 2 定稿)

| # | 包 | 內容 | 狀態 |
|---|---|---|---|
| 1 | 後端 | 🔴 wave 1 後端:上限 50([red]→[green])+ 註解/docs 同步 | **done**(bfbfd222 [red] → d36900d0 [green];紅=預期 3 支;gate ruff/pyright/pytest 觸及範圍綠) |
| 2 | 前端 | 🔵 wave 0 helper 抽取 → 🔴 wave 1 前端文案 → 🔴 wave 2 header 視覺 → 🟢 wave 3 全收/全展 | **done**(2523326d → 2af09d5e 共 8 commits;efeb8d23 補 2 處「30 張」註解,reword 去掉誤掛的 [green] → 2af09d5e)|
| 3 | 自評 review | 雙 lens(A 白名單 / B 測試效力)round 1 | **done**(P0×0 P1×1 P2×5,全 accepted;JSON 落檔)|
| 4 | fix 波 | B-1 lock test + B-2/B-3/A-1/A-2 | **done**(085ef998 + e4e3082a;mutation ×3 verified)|
| 5 | 真實環境 | SC-1 API 邊界 / SC-3/SC-4 截圖 | **done**(evidence 三張圖 + api-boundary.txt;SC 全 PASS,user 過目待)|
| 6 | 收尾 | 最終全套 gate + tag 機驗 + phase7 checklist | **done**(pytest 2662 / vitest 1809 / validate 42-42 / tag PASS)|

- `self_review_head` = e4e3082a;其後增量僅 docs(next-time 追記)+ artifacts,無 code
  → 依 review-protocol C 節意圖沿用自評,不補跑。

- 包 1 附帶發現(既有,非本輪引入,master 重現):`test_signal_routes.py::TestConftestWatchlistIsolation::test_hub_data_dir_isolated_without_explicit_path` 在 8 檔組合跑時 flake(conftest 隔離 fixture 順序相依),單跑綠;收尾時記 docs/next-time.md。

- baseline:backend 2659 passed / frontend 1797 passed(2026-08-13,master=5a1a97aa)
- spec review:round 1(P0×1 P1×3 P2×6,全 accepted)→ round 2 限縮(P1×2 P2×3,全 accepted)→ 退出
