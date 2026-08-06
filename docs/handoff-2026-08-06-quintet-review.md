# Handoff — 個股五題(quintet)review session 交接

> 給新 session:對 2026-08-05/06 出貨的五個 feature 做整體 review。
> 本檔 = 唯一交接物;寫給零上下文的讀者,對話歷史不需要。

## 0. 一句話背景

user 拍板五個個股功能(討論輪共識:主 tree `.claude/feat/stock-quintet-discussion/brainstorm.md`,
未入版控;各輪 brainstorm 已複製其拍板內容),由 /auto 依 4→2→1→5→3 順序各跑一輪
完整 /feat,五個 PR 全部 merge master。**修改量大(合計 ~90 commits),user 要求
獨立 session 復審。**

## 1. Review 對象(五個 PR,建議逐 PR 審)

| PR | slug | 內容一句話 | 風險重心 |
|---|---|---|---|
| [#21](https://github.com/loger-w/copycat/pull/21) | discord-watchlist | /watch 群組管理 + autocomplete + 保留名 gate | watchlist_service 壞檔語意 |
| [#22](https://github.com/loger-w/copycat/pull/22) | intraday-volume-profile | 分時圖價位量條(前端 only) | stock-accum fold 與幾何 |
| [#25](https://github.com/loger-w/copycat/pull/25) | signal-rules | 訊號規則化(per-rule detector 組合式)+ 舊 enabled API 退役 | signal_hub 重構(slots/basis cache)、🔴 API 移除 |
| [#27](https://github.com/loger-w/copycat/pull/27) | group-grid | 群組 mini 分時圖牆 + Discord 同群摘要 + **backfill 鏈去 main 綁定(🔴)** | stock_engine 回補 guard 語意變更 |
| [#28](https://github.com/loger-w/copycat/pull/28) | stkfut-contracts | 個股期選月 → 分時/五檔切換 + 群益下單 | **真錢面**:下單三閘/乘數/檔位;engine instrument 推廣 |

可用 `/code-review ultra <PR#>` 逐個跑 GitHub PR 的多 agent 雲端 review(user 觸發)。

## 2. 每輪 artifact 位置(全部已入版控)

`.claude/feat/<slug>/` 各含:`brainstorm.md`(SC 定義)、`design.md`(含 review
changelog — **改動的「為什麼」都在這**)、`implementation/PLAN.md`、
`design-review-round-*.json` / `impl-spec-review-round-1.json` /
`code-review-round-1.json`(已審過什麼 + 處置)、`progress.md`(commit 對照)、
`phase7-verification.md`(SC ↔ 測試 ↔ 證據對照表)、`evidence/`(截圖/consumer
腳本/probe)。

## 3. 已做過的 review(別重掃,聚焦缺口)

每輪都走過:design review 1-2 輪 + impl-spec review 1 輪 + 自評雙 lens code review
(finder 各附實跑 repro / mutation 反證)+ fix 輪。累計攔下 P0 ×10+(各輪
code-review JSON 有完整處置記錄)。**新 review 的高價值切角**:

- 跨 PR 交互(單輪 review 看不到):#25 規則引擎 × #27 同群摘要 × #28 期貨主圖
  同時掛在 signal_hub / stock_engine 上 — 三輪各自的不變式合在一起還成立嗎?
  (例:#28 的 `F:` instrument 不進 `_watch`、#27 的 quotes_fn 快照、#25 的
  per-rule detector 熱路徑成本疊加)
- `stock_engine.py` 被三輪連續重構(backfill guard → 雙 set → instrument 路由),
  是全案 blast radius 最大的檔,值得單檔精讀
- 真錢面終審:`capital_api` 的三閘(BAD_TICK/PRODUCT_NOT_ALLOWED/金額閘乘數)、
  `StkfutLadder` 送單欄位、武裝解除鍵 — `.claude/feat/stkfut-contracts/design.md`
  的 SC-6 節是拍板語意
- 前端 `useStockStream` 的 instrumentKey 貫穿(五個 refetch 觸發點)

## 4. 已知風險 / 刻意取捨(不要當新發現報)

各輪 design.md 的 Known Risks 節 + `docs/next-time.md` 的五個 2026-08-05/06 節
(全部已記帳)。重點:ws_disconnect flake(既有,重現率升高待排查,memory 有記);
duplicate-key console error(嫌疑已定位:priceMilli 當 key 四處,next-time 有行號);
ETF/調整契約禁下單;期貨態僅分時;20k tick deque 上界。

## 5. 驗證環境(重要紀律)

- 六 gate:`.venv\Scripts\python -m pytest -q` / `ruff check copycat tests` / `pyright`
  (repo root)+ `npx vitest run` / `npx tsc -b` / `npx eslint src`(frontend/)。
  最終態:pytest 2319 / vitest 1556 / 其餘 0 / validate 42/42。
- **盤中/夜盤不得起第二台連 TC4 的後端**(CLAUDE.md §8);要看畫面用各輪
  `evidence/fake_server.py`(零 ZMQ,起 8899 + 暫改 vite proxy)— stkfut 輪的版本
  最全(含個股期 instrument 種資料)。
- worktree `.claude/worktrees/feat-discord-watchlist` 是上一輪工作區(全部已 merge,
  可刪);在 worktree 直跑腳本要 `sys.path.insert(0, <worktree root>)`(§8)。

## 6. 待 user 的驗證(review session 不必做,但可核對清單合理性)

1. 題 3 真送單安全首單(遠價 1 口 → 群益 APP 核對 → 刪單,§7)
2. 各題畫面過目(截圖已在各 evidence/)+ Discord 實發(/watch autocomplete、
   規則觸發帶規則名、同群摘要)
3. prod 重啟後首個交易日:期貨分時 08:45–09:00 有資料(夜盤訂閱窗假設觀察項)

## 7. Review 產出建議落點

發現的問題:P0/P1 開 `/bug` 或 `/mod` 逐條處理(引用本檔 + 對應輪的 design.md);
P2 記 `docs/next-time.md`。不要直接在 master 上大改 — 五輪的測試網(pytest 2319 /
vitest 1556)是行為合約。
