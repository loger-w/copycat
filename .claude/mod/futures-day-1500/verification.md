# verification:期貨 tab 改 15:00 夜盤起算(mod/futures-day-1500)

> 2026-08-28 凌晨。worktree `C:\side-project\copycat-wt-fd1500`,fixed point origin/master c80dbde5。

## 1. 自動化(worktree)

| 指令 | 結果 |
|---|---|
| `npx vitest run`(frontend,review 收修前 d6f93a12) | 152 檔 / 2871 tests:2870 passed + 1 紅 = `App.memo.test.tsx`「換主檔」(1.1 s;App 級 lazy 負載 flake,單獨重跑 8/8 綠;與本案零關聯 —— next-time 08-27 已記同型) |
| `npx vitest run`(review 收修後 5316f857) | 150 檔綠 + 2 檔紅 = `App.test.tsx`「capital WS 唯一掛載」(1.58 s)/ `App.memo.test.tsx`「換主檔」(1.27 s):同一型負載 flake(跑時與後端關機 / preview 收掉重疊);兩檔單獨重跑 **61/61 綠** |
| `npx vitest run` 本案七檔(allday / adapter / FuturesChart / txf-overlay / trading-calendar / fill-marks / SIC.futures) | 收修後全綠 233(allday 36、adapter 22、FuturesChart 54、txf 13、trading-calendar 16、fill-marks 53、SIC.futures 39;pr-133 F-04 回校 —— 原分項四檔數字是事後補寫,以 `grep -cE '^\s*it\('` 逐檔實數為準,總和 233 不變) |
| `npx tsc -b` | exit 0(收修前後各一次) |
| `npx eslint src` | 0(收修前後各一次) |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |
| `ruff check copycat tests` / `pyright` / `pytest -q` | 0 / 0 / **3132 passed, 3 skipped**(後端零 diff,跑 gate 只證沒被連帶) |
| `copycat validate` | 未跑:後端 / replay 零 diff,worktree 無 out/ 產物;主 tree 上次 PASS 狀態不受本案影響 |

紅先行證據:`allday.test.ts` 重寫後 23/36 紅 → 新 `allday.ts` 後 36/36 綠;adapter 12 紅 → 橋實作後綠;
FuturesChart 測試先改 3 紅(gate 5 空檔 / 日曆 deps)→ 元件改後 53/53 綠。

## 2. SC 對照

| SC | 證據 |
|---|---|
| SC-1 四段 / 1365 | `allday.test.ts`「段長 539 / 301 / 225 / 300」 |
| SC-2 索引 / 空檔 null | `allday.test.ts` alldayIndexOf 三條 |
| SC-3 alldayHhmmOf 含空檔 | `allday.test.ts`「段界反查(含空檔兩端)」+ 全軸互逆 |
| SC-4 九顆刻度 | `allday.test.ts` ALLDAY_TICKS 字面;`FuturesChart.test.tsx` SC-2 標籤順序;真環境截圖 §3 |
| SC-5 anchorDateOf + nextTradingDayIso | `allday.test.ts` anchorDateOf 八條(含假日 / 顯式集合);`trading-calendar.test.ts` 五條 |
| SC-6 slice | `allday.test.ts` sliceCurrentAllday 八條(13:45–15:00 / 翻頁 / 週末 (a)(b) / 假日) |
| SC-7 水平橋 | `futures-accum-adapter.test.ts` 橋節四條(兩側 / 只夜 / 只日 / live 佔位算日盤側);`FuturesChart.test.tsx` SC-1 首條斷言橋 y = 05:00 y |
| SC-8 gate 5 可交易距離 | `FuturesChart.test.tsx`「gate 5 跨空檔以可交易根數計」(2 根放行 / 4 根擋且文案印 4);gate 1–4 既有條全綠 |
| SC-9 日曆 deps | `FuturesChart.test.tsx`「假日前夜盤與假日後日盤同一天:日曆載入後 slice 重算」 |
| SC-10 CDP 基準 | `FuturesChart.test.tsx` N042 節(fixture 改週四夜 + 週五日盤,基準仍 08-20);真環境截圖「疊線基準 2026-08-27」= 剛收那天 |
| SC-11 疊線解耦 | `txf-overlay-series.test.ts` 14 條全綠,`txf-overlay-series.ts` 不再 import anchorDateOf |
| SC-12 CONTEXT.md | 「錨定日」條(chore 5316f857) |
| SC-13 真環境 | §3 |

## 3. 真環境(TC4 真資料,2026-08-28 00:21,08-27 夜盤進行中)

prod 8721 當時未跑(user 08-27 收工後未重起);從 worktree 起一台後端(`serve_wt.py`,同 port 8721、
唯一一台連 TC4、零後端 diff,health `git_sha d6f93a12`)+ `vite preview --port 4174`,Chrome 截圖
`evidence/SC-13_night_session_2026-08-28_0021.jpg`:

- x 軸標籤 `15:00 18:00 21:00 00:00 03:00 05:00 09:00 11:00 13:00`(SC-4);左緣 15:00 起有線,
  右半(05:00 → 13:45)留白(日盤未開、不補橋,Q9 拍板 (a))。
- 主線 15:00 → 00:21 連續,現價圈落在 00:21(live 點四道 gate 在夜盤路徑正常)、readout 首欄印 `00:21`。
- 昨收基準 46064 = 08-27 結算價(tc4-market-facts 期指節),15:00 起算的一天單一基準(W7)。
- 「疊線基準 2026-08-27」:夜盤時段 CDP / MA 基準 = 剛收那天的 DK(SC-10 連帶正確,現況會印 08-26)。
- VWAP 46246 / 高 46405 低 46036 標記 / VP 左緣直方圖 / 量副圖:全部只含 15:00 起的資料。

**待 user 過目 / 待窗口**(SC-13 b–e):15:01 翻頁那一刻、次一交易日 08:46 的水平橋 + 跳價、CDP 值對 APP、
個股頁台指期線夜盤時段仍在(本輪 00:2x 個股頁未截:index engine trade_date 深夜語意另案)。

**09-01 回填**:(b) 資料面 PASS(09-01 盤中補驗,見 next-time f3326c4e);(d) 機器半邊 PASS
(22:06 夜盤:TXF CDP 46857\* = 09-01 完整 D bar 算的 46856.5 經 fmtIndexPts round、TMF 46859\* 同構
各對各家 bar,疊線基準 2026-09-01)—— **對達錢 4 APP 的數字仍待 user 眼**;(e) **PASS**(22:06
夜盤 2455 單檔開台指期 toggle,橙線 + 標籤正常)。剩 (c) 次一交易日 08:46 水平橋 + 跳價(server
需 08:45 前起)與 (d) 的 APP 對照。

## 4. 白名單核對(W1–W13)

- W2 後端零 diff:`git diff origin/master...HEAD -- copycat/ tests/` 空。
- W3 `trading-hours.ts` 零 diff;W6 `candle.ts` 零 diff;W12 `alldayFillPoints` 簽名加**選配**第 4 參 `holidays`(P5 收修;既有三參呼叫相容),函式體改 `anchorDateOf(stamp, holidays)`;唯一 prod caller `FuturesChart.tsx` 已同步傳 `holidaySet`(pr-133 F-01 回校 —— 原句「函式體未動、只改註解」被 `git diff c80dbde5...HEAD -- fill-marks.ts` 推翻)。
- W4 gate 1–4:`FuturesChart.test.tsx` live 節既有條(錨定日 gate 獨立 / gate 4 單獨 / 同錨定日追加 / 邊界 4 擋 3 放行 / 無成交空檔 / 常態落後 / 一天之外)全綠。
- W5 個股頁疊線:`txf-overlay-series.test.ts` 既有 14 條期望值零改(只改 3 條標題),含「bars 空 → 不追加」「日期不同 → 不疊」。
- W7 ref 來源不動;W9 常數 identity(IIFE)不動;W13 `FUT_LIVE_LAG_MAX`/文案不動。

## 5. two-axis review

見 `code-review-round-1.json`:Standards 7(6 fixed / 1 rejected → next-time)、Spec 6(5 fixed / SC-13 partial)。
收修後 mutation:`liveSlotOf(new Date(), holidaySet)` 改回模組集合 → 新測試「假日前夜盤:live 點與成交點跟 slice
吃同一份日曆」紅(1 failed),還原後綠。收修 commit 以 `reset --soft` 重打成 feat 608b1cfc / fix 1dbb7775 / chore 5316f857
(S2:commit type)。

## 6. 收尾

後端 `serve_wt.py` 以 CTRL_BREAK 優雅收工(log:關機收尾 0.17 s、Application shutdown complete);preview 4174 killed;
worktree `.env` / `spikes/TCPY` 複本於 worktree remove 前刪除。
