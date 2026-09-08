# fix/pr-218-review-followups — verification(pr-review #218 收修;報告 `docs/superpowers/specs/pr-218-review.md`)

寫於 2026-09-09 凌晨(worktree `.claude/worktrees/fix-pr-218-review-followups`,merge-base `16605b70`)。
user 拍板(09-09):F-01 修 / F-02 + F-03 併同批 / F-04 遇到再說(next-time)/ F-05 參考用(只補 doc)。

## 1. 紅 → 綠(receiving-code-review:逐條技術核實後才動)

| Finding | 紅 commit | 綠 commit | 紅的證據 |
|---|---|---|---|
| F-01 定稿閘只看 `dataUpdatedAt`(達錢關著 14:01 回 200 + 墊背 + status 非 ok → 閘關、退回早上半成品) | `1869df7a` RTL「達錢關著:14:05 抓回 200 + 墊背(status disconnected、非空)→ 仍以 accum 蓋」 | `8dfe3dba` `dailyFinal = dataUpdatedAt >= finalAt && data?.status === "ok"` | readout 印「收 100.5」(正式半成品)而非「收 103」(accum),1 failed |
| F-02 日 K h/l 直接取代、回補未到 / 放棄時窄化 | `1869df7a` lib 案 6c「正式 h 110 / l 97 比 accum 108 / 98 寬 → 取聯集」+ 反向「accum 寬照贏」 | `8dfe3dba` 取代分支 `h: Math.max(last.h, live.high)` / `l: Math.min(last.l, live.low)` | 期望 110 / 97 實得 108 / 98,1 failed |
| F-03 verification §6 判準 1「無跳動」分不出已知近似 | —(文件) | `8505deca` 判準改「時戳不位移;o 與顏色可能變一格(已知近似)」;判準 2 加「且 status = ok」 | — |
| F-04 交易日閘只擋日曆知道的休市日 | —(user 拍板留尾) | `8505deca` next-time 一條(修法 = `/api/calendar` 的 `trade_date === liveToday`) | — |
| F-05 13:30 夾端點 | —(參考用) | `8dfe3dba` `barMinuteOf` doc 標明夾端點範圍 / 曝險窗 / 期貨批勿照抄;next-time 一條 | — |

## 2. 反向驗證(/bug 自家 gate;python 暫時還原修法 → 跑 seam 兩檔 → 還原)

| 還原 | 結果 |
|---|---|
| 修法在(基線) | GREEN(23 passed) |
| F-01 拿掉 `&& data?.status === "ok"` | **RED(1 failed)**:「達錢關著 14:05…」案 |
| F-02 拿掉 `h: Math.max / l: Math.min` 兩行 | **RED(1 failed)**:案 6c |
| 還原 | GREEN(23 passed) |

Blast radius:`dailyFinal` 只有 `StockChart.tsx` 一個讀者(新變數);`mergeLiveDailyBar` 唯一 caller = `StockChart.tsx`(grep `mergeLiveDailyBar` 全 src 只有 lib 定義、StockChart import 與測試);`data?.status` 的值域由 `useStockBars.fetchBars` 正規化(缺欄 / 未知值 → "ok",舊後端不會讓閘永遠開著);append 分支(DK 尚無今日列)無正式 h/l 可比、刻意不動。既有 RTL「定稿閘:14:05 + status ok → 不蓋」與「13:50 半成品 → 14:05 仍蓋」照舊綠 = 兩半各自語意未變。

## 3. 自動化 gate

| Gate | 結果 |
|---|---|
| vitest 全套(frontend/) | **156 files / 3069 passed**(+2 新案),exit 0 |
| tsc -b | 0 errors |
| eslint src | 0 issues |
| react-doctor --scope changed | 1 warning StockChart 複雜度 —— 存量(master :48 / 本批 :59 同一條),非新增 |
| pytest -q(借主樹 venv;本批零 .py 改動) | 3558 passed / 3 skipped(236 s),exit 0 |
| ruff / pyright | All checks passed! / 0 errors 0 warnings |

two-axis 收修後(S-03 🔵 明列欄位 / S-05 stub 參數化 / docs ×4)seam 兩檔 23 passed、tsc 0、eslint 0;全量 vitest 重跑數字見下方補記。

## 4. 兩軸 review

見 `code-review-round-1.json`(fixed point `16605b70`)。

## 5. 真環境判準(併入 `.claude/feat/live-last-bar/verification.md` §6 已改口那兩條)

- 達錢關著的交易日 14:0x:個股頁日 K 今天那根**維持** accum 值不退回(Network 那發 `tf=D` 200 + 舊 bars + status disconnected);達錢開著:14:01 換定稿。
- 盤中 server 重啟後開日 K:今天那根上下影線 ≥ 正式半成品(不會比早上窄)。
- 3 分 K 補的根換成正式版:時戳不位移;顏色可能翻一格屬預期。
- 知情(S-01):達錢開著但 DK 慢到逾時(非空 + status timeout)的 14:01 那發不封閘,今天那根留 accum 值到午夜 —— 與定稿差最多一格量;要分辨只能看 Network 回應 status。

## 6. 三類 commit

🟢 test ×1(紅先行兩案)/ 🔴 fix ×1(F-01 + F-02 行為修正 + F-05 doc)/ chore(docs) ×1(spec / verification / CLAUDE.md / next-time / 報告雙檔入 docs)+ artifacts。
