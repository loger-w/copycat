# feat/live-last-bar — verification(spec #214;tickets #215 / #216 / #217)

寫於 2026-09-08 晚(收盤後,worktree `.claude/worktrees/feat-live-last-bar`,merge-base `410c0f1c`)。

## 1. 紅 → 綠(TDD 逐票)

| Ticket | 紅 commit | 綠 commit | 紅的證據 |
|---|---|---|---|
| T1 #215 分 K 純函式 | `bea84973`(規則表案 1/2/3/4/5/8/9) | `4be0273a` | `Failed to resolve import "@/lib/live-last-bar"`(模組不存在,1 file failed) |
| T1 #215 StockChart 接線 | `dea48d26`(4 案) | `97a04ee4` | 2 failed / 2 passed(兩條守門案本來就綠:換股 race、08:59) |
| T2 #216 日 K 純函式 | `2874bc77`(案 6a/6b/7/8) | `dbb82d2a` | 4 failed(`mergeLiveDailyBar` 未 export) |
| T2 #216 日 K 接線 | `8a282cb8`(5 案) | `812407d7` | 3 failed / 6 passed(守門案:08:59、定稿閘 本來就綠) |
| two-axis Spec-01 交易日閘 | `c6880803`(週六 09:06 不補) | `ce531c02` | 1 failed / 9 passed(readout 出現 `2026-09-12 09:07` 假 K) |

tsc 一次紅:`live-last-bar.ts` TS2698(`let cur: Bar | null = null` 被窄成 `null`,迴圈內 spread 成 never)→ `null as Bar | null` 修,tsc 0 errors。

## 2. 突變體(seam 兩層合跑:`live-last-bar.test.ts` + `StockChart.livebar.test.tsx`,基線 20 passed)

| # | 突變 | 結果 |
|---|---|---|
| M1 | `barMinuteOf`:`accumMinute + 1` → `accumMinute`(整條左移一格) | KILLED(9 failed) |
| M2 | 拿掉 13:30 上限(`Math.min(…, LAST_BAR_MIN)` → `accumMinute + 1`) | KILLED(1 failed:案 2) |
| M3 | StockChart 定稿閘拿掉(`dataUpdatedAt < finalAt` 條件刪) | KILLED(1 failed:「定稿閘」案) |
| M4 | 09:00 閘拿掉(`nowMinute >= 9 * 60` 刪) | KILLED(1 failed:「08:59 不補」案) |
| M5 | 換股 code 閘拿掉(`accum.code === code` 刪) | KILLED(1 failed:「換股 race」案) |
| M6 | 交易日閘拿掉(`&& isTradingDay(now)` 刪;two-axis Spec-01 收修後加跑,基線 21 passed) | KILLED(1 failed:「週六 09:06 不補」案) |

腳本:scratchpad python(每隻套用 → `npx vitest run` → 還原;判讀先去 ANSI 再比 `N failed`,第一版沒去 ANSI 全誤報 SURVIVED,已修)。跑完 `git status` 乾淨。

## 3. 自動化 gate(CLAUDE.md §1)

| Gate | 指令(工作目錄) | 結果 |
|---|---|---|
| vitest 全套 | `npx vitest run`(frontend/) | review 前 **156 files / 3066 passed**;two-axis 收修後重跑 **156 files / 3067 passed**(+ 週六案),exit 0 |
| tsc | `npx tsc -b`(frontend/) | 0 errors,exit 0(收修後重跑同) |
| eslint | `npx eslint src`(frontend/) | 0 issues,exit 0(收修後重跑同) |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | 1 warning `no-high-complexity-react-function` StockChart.tsx:59 —— **存量**(主樹 master 全量掃 StockChart.tsx:48 已有同條),非新增,不擋(收修後重跑同) |
| pytest | `.venv\Scripts\python -m pytest -q`(worktree root,借主樹 venv) | 3558 passed / 3 skipped(231 s),exit 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed!,exit 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors / 0 warnings,exit 0 |
| copycat validate | 後端零改動(本批只碰 frontend/ + 文件),golden gate 不受影響;沿 W2 前例不重跑 replay | 略 |

## 4. 重畫成本量測(T3 #217;spec「> 16 ms 才做退路」)

方法:臨時 bench host(`frontend/src/__bench__/live-bar-bench.tsx` + `bench.html` + `vite.bench.config.ts`,**已刪不進 PR**),
`vite build --config vite.bench.config.ts` **prod build** → `vite preview` 5198,chrome-devtools 開頁讀 `#bench`。
每 100 ms 換一次末根(同一分鐘內只換 c/h/l/v,每 5 拍推進一分鐘),600 拍;量「setState 前 → 該次 commit 的 `useLayoutEffect([bars])`」
= React render(App + CandleChart,bars 走 useMemo 同 StockChart 形狀)+ DOM commit。第一版 dev build + StrictMode + 取樣進 state
量到 p95 98 ms —— 那是 bench 自己每拍多兩次 re-render + dev React,作廢。

| 場景 | bars 總數 | 可視 | render p50 | p95 | max | merge+aggregate p50 / p95 |
|---|---|---|---|---|---|---|
| 3 分 K(30 日 1 分 K 8,100 根聚合) | 2,680 | 700 | 3.10 ms | **6.60 ms** | 11.10 ms | 1.10 / 1.80 ms |
| 1 分 K | 8,039 | 700 | 2.70 ms | **7.80 ms** | 12.90 ms | 0.40 / 0.60 ms |
| 日 K(只換末根) | 401 | 120 | 1.50 ms | **2.10 ms** | 3.20 ms | 0.00 / 0.10 ms |

三場景 p95 皆 < 16 ms → **「只重畫末根」退路不做**(spec 條件工作,只記數字)。逐筆 0.1 s 打包節奏下 CPU 佔比約 3–8%。
真環境(prod preview 4173、盤中熱門股)的數字下一交易日補在 §6。

## 5. 兩軸 review

見 `code-review-round-1.json`(fixed point `410c0f1c`);處置摘要與收修 commit 在該檔 `disposition`。

## 6. 真環境判準(下一交易日,誰在盤中就順手看;prod 需重 build + 重啟前端 preview)

1. 個股頁 3 分 K:最後一根與成交明細同步跳(目測 < 1 s);每整 3 分鐘新根自己長出;60 s 後 Network 一發 `tf=1` 回來,補的根換成正式版時
   **時戳不位移**(右移一格 = 分鐘鍵契約漂了,見 CLAUDE.md §4);**o 與顏色可能變一格**(已知近似:補的根 o = 前一根 c,見 next-time「即時末根已知近似」;pr-218 review F-03 回校,不是 bug);**補的根的量與 60 s 後換上的正式 1 分 K 量同量級**
   (差幾張可以,差 ×1000 = 單位漂了;two-axis Spec-06)。
1a. 休市日(週末或國定假日)09:00 後開著個股頁:分 K / 日 K 末根仍是前一交易日,不長出「今天」的根(Spec-01 交易日閘)。
2. 日 K:今天那根高 / 低 / 收與側欄高 / 低 / 現價逐字同值、量 = 側欄總量(`last.cum_vol`);13:30 後值停住;14:01 Network 一發 `tf=D` **且回應 status = ok** 後今天那根
   = 達錢定稿(可能微調一格),之後不再跟成交明細;達錢關著時那發回 200 + 墊背(status disconnected / timeout),今天那根**維持** accum 值不退回(pr-218 review F-01 判準)。
3. 08:5x 開著的頁:日 K 末根仍是昨天(不補);09:00 首筆成交後才長出今天那根。
4. 換股:切到別檔那一瞬間 K 線末根不會先出現前一檔的值(accum gate 卸載重掛 + code 閘)。
5. 抽兩個未改功能:江波圖 / 個股期合約態(K 線鈕反灰、只有分時)照舊。
6. 效能:Performance 面板錄 60 s,主執行緒 long task(> 50 ms)= 0;與 §4 bench 對照。

## 7. 三類 commit 分離

🟢 test ×5(紅先行,含 Spec-01 週六案)/ 🟢 feat ×5(含 Spec-01 交易日閘)/ 🔵 refactor ×1(two-axis Standards 收修:key factory / memo / codec import /
測試字面量,`86aabdcf`,行為不變、既有測試零改動)/ chore(docs) ×3(CONTEXT.md 術語、CLAUDE.md §4 + next-time、review 回校)+ artifacts。零 🔴 行為改動。

## 8. 回頭核 goal(verification-before-completion;對 spec #214 User Stories 逐條)

| Story | 實作 | 測試 / 證據 |
|---|---|---|
| 1 分 K 末根跟成交跳(含進行中) | `mergeLiveMinuteBars` + StockChart 分 K 接線 | lib 案 1/4/9;RTL「3 分 K 進行中桶」「再一筆成交」;§6-1 |
| 2 日 K 今天那根高低收量即時 | `mergeLiveDailyBar`(h/l/c = accum、v = `last.cum_vol`) | lib 案 6a/6b;RTL「今天那根 = accum」;§6-2 |
| 3 正式 1 分 K 到了換掉補的根 | merge 只補正式末根之後,每 render 重算 | lib 案 1(正式 09:05 已有 → 跳過);§6-1 |
| 4 13:30–14:01 留前端值、14:01 換定稿 | 定稿閘 = `dataUpdatedAt ≥ 14:00` | RTL「定稿閘」「13:50 抓的半成品」;§6-2 |
| 5 14:01 失敗不退回 | 閘看 `dataUpdatedAt` 不看牆鐘 | RTL「13:50 … 牆鐘過 14:00 仍蓋」;M3 |
| 6 09:00 前不出假 K | `nowMinute >= 540` + `isTradingDay`(review 補) | RTL「08:59」「週六」;M4 / M6;§6-3 / 1a |
| 7 換股不誤貼 | `accum.code === code` | RTL「換股 race」;M5;§6-4 |
| 8 期貨態不動 | `!isFut` 既有 | `StockChart.futconverge.test.tsx` 既有綠;§6-5 |
| 9 逐筆不卡 | bench p95 6.6 / 7.8 / 2.1 ms | §4;§6-6 |
| 10 純函式零 React、下一批可接 | `lib/live-last-bar.ts`(結構型參數) | lib 規則表 11 案 |
| 11 分鐘鍵對齊由測試釘住 | `+1` / 13:30 上限 | lib 案 1/2/9;M1 / M2;CLAUDE.md §4 契約 |

Out of Scope 逐條未動:期貨 / 加權頁、個股期合約態、每分鐘首筆價、後端、群組圖牆、視覺標示。白名單:`useStockBars` 只多 export key factory
+ 回 `dataUpdatedAt`(既有欄)、`candle.ts` 只 export 兩支既有私有函式、`aggregateBars` / CandleChart / StockIntradayChart / `stock-accum.ts` 零改動
(`git diff 410c0f1c...HEAD --stat` 核過)。
