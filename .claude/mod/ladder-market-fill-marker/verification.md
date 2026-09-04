# verification — mod/ladder-market-fill-marker(2026-09-05,週六;prod 8721 關著、TC4 未開)

## 自動化(worktree `.claude/worktrees/mod-ladder-market-fill-marker`,review 收修後 HEAD 42c061da)

| gate | 指令(在 worktree `frontend/`) | 結果 | exit |
|---|---|---|---|
| 觸及 + 白名單檔 | `npx vitest run src/lib/ladder-lots.test.ts src/components/stock/PriceLadder.test.tsx src/components/stock/StkfutLadder.test.tsx src/components/stock/LadderView.test.tsx src/lib/fill-marks.test.ts src/lib/futures-ladder.test.ts src/components/futures/FuturesLadder.test.tsx` | 7 files / 288 passed(ladder-lots 31:既有 12 + 市價 6 + 限價 7 + ymdWindow 4 + ymdOf 2;PriceLadder 83 含新案 1) | 0 |
| 前端全套 | `npx vitest run` | 154 files / 2980 passed(本輪新增 14 條:lib 13 + 元件 1;收修前 2978) | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint --fix src/lib/ladder-lots.ts src/lib/ladder-lots.test.ts src/lib/futures-ladder.ts src/lib/fill-marks.ts`(+ 第一輪對 PriceLadder 兩檔) | 無輸出、無改動 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found(第一版接線 7 行曾讓 `PriceLadder.tsx:201` 新報 `no-giant-component` —— 主 tree master 全掃 8 條、worktree 9 條 = 新增 finding;收成兩行後消失,存量 8 條不動) | 0 |
| build | `npm run build` | ✓ built in 1.24s | 0 |
| 後端 pytest / ruff / pyright / validate | 未跑 —— 本輪零 `.py` 改動(`git diff --stat` 只有 frontend/ 與 .claude/mod/) | — | — |

紅先行實查:`5bf556ad`(市價 6 紅:含既有案改述後多的 price=0 幽靈 entry 斷言)→ `60603ec0` 綠;
`d1aa60a8`(限價 2 紅)→ `d01b19e2` 綠;review 收修兩案(總量不等 / 異常列)先紅(vitest 2 failed 實查)→ `52d23ad0` 綠。
三類分開:test / fix / chore(docstring)× 兩輪。react-doctor 收修後重跑 No issues found;build 收修前跑過(收修只動 lib 純函式與 docstring)。

## 真實環境

| SC | 結果 | 證據 |
|---|---|---|
| SC-4 市價單兩價成交 → 兩列各 `(1)` | 元件層 PASS(RTL:`findAllByTestId("ladder-filled-lot")` 兩顆,`closest("[data-price]")` 落在 100.5 / 100 列,無「刪 … 買單」aria) | `PriceLadder.test.tsx`「市價買全成交(fills 兩價)」 |
| SC-1 限價 98.5 買成交 98.3 → 98.3 列 | 純函式 PASS | `ladder-lots.test.ts` 限價節 7 案(含 SC-2 總量不等雙向 / 異常列三種退回委託價) |
| SC-5 真環境 UI 過目 | **未驗**:週六無盤、prod 關著,09-04 的兩張 2426 市價賣(seq 2313223176699 / 2313223222486)只剩 audit 的送單列,回報 raw 沒落檔,無法回放。判準留給下一個交易日(見下) | — |
| 抽 2 未改功能 | 市價買賣鈕送單 / 防抖 / hint(W6)、限價點價武裝直送(SC-7 既有案)—— 全套內全綠 | `PriceLadder.test.tsx` 既有 82 案 |

### 下一個交易日 user 過目判準(prod 重啟 + 主 tree `npm run build` 後)

1. 閃電梯按市價買 / 賣 1 張 → 成交後 **成交價那列**右 / 左緣出現 muted 邊框 `(1)` 徽章(與限價全成交徽章同款);委託列表「市價」標籤照舊。
2. 掛限價高於外盤(如買 98.5、外盤 98.3)→ 成交後徽章在 **98.3 列**,與成本線同列;98.5 列不再有徽章。
3. 部分成交:掛 2 張成交 1 張於較優價 → 委託價列紅方格 `1(0)`(可刪)+ 成交價列 `(1)` 徽章。
4. 反向確認沒壞:限價成交在委託價(常態)→ 畫面與過去完全相同 `殘(成)`。

## Review

見 `code-review-round-1.json`(two-axis,Standards / Spec 各一 sub-agent,opus):Standards 9(P2 4 / P3 5)、
Spec 5(P2 2 / P3 3)。全修 12、rejected 1(std F-08 commit 分類)、知情接受 1(spec F-03 `0(0)` 畫面態)。
收修 commit `52d23ad0`(fix)/ `42c061da`(chore)已在上表 gate 內(觸及 7 檔 + 全套 2980 皆收修後數字)。
