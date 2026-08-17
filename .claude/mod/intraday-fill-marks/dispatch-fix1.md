# Dispatch fix 波 1 — code review round 1 accepted findings

你是 implementer(fresh context)。repo `C:\side-project\copycat`,分支 `mod/intraday-fill-marks`(已切好;主 tree 直接工作,不開 worktree、不 switch)。前端在 `frontend/`。

先讀:`C:\side-project\copycat\.claude\mod\intraday-fill-marks\code-review-round-1.json`(findings 與 disposition)、`change-spec.md`(SC-1/SC-3/SC-4/SC-9)、相關源檔 `frontend/src/lib/fill-marks.ts`、`frontend/src/components/stock/StockIntradayChart.tsx`、`GroupGridView.tsx`、`StockChart.tsx` 與其測試。

## 要做的(全部 accepted;每條先讓測試紅(能紅的)再改綠)

1. **B-1(P1)** `StockIntradayChart.test.tsx` 補 stkfut 態成交點案:`<StockIntradayChart accum={ACCUM} stkfut fills={[{minute: 8*60+50, priceMilli: 2_380_000, side:"B", qty:1}, {minute:541, priceMilli:2_380_000, side:"B", qty:1}]} />` → `polygon[data-testid="fill-B-530"]` 存在(現貨窗會丟掉它)且 541 那顆 x ≈ `clampFillX(minuteToX(541, w, STKFUT_WINDOW), w)`(≠ SPOT_WINDOW 值)。此案對現有實作應直接綠 → 屬 lock test:**mutation 抽驗**(Edit 把 `projectFills(fills, g, w, xw)` 的 `xw` 暫改 `SPOT_WINDOW` → 測試紅 → Edit 還原 → 綠;**用 Edit 成對操作,禁 git checkout/restore**),commit tag `[lock]` + body `mutation-verified`。
2. **A-1** `fill-marks.ts::projectFills` 窗過濾改 `if (!(f.minute >= xw.start && f.minute <= xw.end)) continue;`(沿 `stock-accum.ts::foldVp` review A3 寫法,註解引它);`fill-marks.test.ts` 補 `minute: NaN` → 不畫案(先紅後綠:NaN 案在舊寫法下會產生一個 mark)。
3. **A-2** readout「成交」欄改吃 **`fillMarks`**(已過窗 / 域 / toggle 的集合;`FillMark extends FillPoint`,`fillsAtMinute(fillMarks, shownMin)` 直接可用),`!card` gate 保留;`StockIntradayChart.test.tsx` 補案:fills 一點 `priceMilli` 落在 `g.yDomain` 外(例如 9_999_000)→ 0 polygon 且 hover 該分鐘 readout 無「成交」(先紅後綠)。同步在 `change-spec.md` SC-4 尾端加 `[amendment 2026-08-17 cr1: A-2 — readout 與三角同一把尺,域外/窗外/toggle 關皆不追加]`。
4. **A-3** 註解修正:`fill-marks.ts` 與 `ladder-lots.ts` 內凡稱 `date` 為「委託建立日」處改為「**最新事件日**(`CapitalStore.apply_reply` 每筆回報有值即覆寫)」,並在 fill-marks 檔頭「已知失真」補一條「昨日部分成交、今日刪單的單 → date 變今日,會以(今日刪單分鐘 × 昨日均價)畫上今日圖;唯一乾淨解 = 精確版逐筆 D 事件」。`change-spec.md` AD-2 與 edge 10 尾端各加 `[amendment 2026-08-17 cr1: A-3 — date 為最新事件日,非建立日;殘餘風險改述]`。
5. **A-4** `clampFillX` 註解改為「正常寬度下 `minuteToX` 值域 `[Y_AXIS_W, w-R_AXIS_W]` 已離 viewBox 邊 ≥ 36px,夾制實際只在退化寬度(plotWidth 被壓到 1)生效;是 spec AD-6 字面公式的守衛,不是常態路徑」。
6. **B-p2-2** `StockIntradayChart.test.tsx` 賣單單側 readout tone:hover 542(S 點)→ 成交欄 class 含 `text-bear`(可併入既有 SC-4 案)。
7. **B-p2-4** `fills-layer` 群組 `pointerEvents="none"` 屬性斷言一行(沿 `PriceLadder.test.tsx:844` 屬性鎖先例)。
8. **B-p2-5** `GroupGridView.memo.test.tsx` 加案:fetch stub 對 `/api/capital/orders` 回一筆 2330 當日成交(`date` 用 `ymdOf(new Date())`)→ 等 2330 卡出現 polygon 後,`quotes` 換 identity 兩輪 rerender → 2330 卡的 render 計數增量與「無成交卡」相同(fills identity 穩定,memo 不因有成交而被打穿)。先紅驗證:Edit 把 `GroupGridView.tsx` 的 `fillsMap` useMemo 暫拿掉 → 該案紅 → Edit 還原 → 綠;`[lock]` + `mutation-verified`。
9. **A-doc** `GroupGridView.tsx` 與 `GroupGridView.test.tsx` 內「四鈕」註解改「五鈕」。

## commit 規則
- 行為修(A-1、A-2)各自:`🟢 test(frontend): add failing test for cr1 A-1 [red]` → `🟢 fix(frontend): cr1 A-1 … [green]`(body `red→green for <sha>`)。可 A-1+A-2 合成一對(同為 review fix 波)。
- lock tests(B-1、B-p2-5、B-p2-2、B-p2-4 可合一 commit):`🟢 test(frontend): lock stkfut fill window / memo with fills [lock]`,body `mutation-verified: <哪些 mutation 紅過>`。
- 註解 / spec 文件修(A-3、A-4、A-doc):`🔵 chore(frontend): cr1 comment fixes (A-3/A-4/A-doc) [refactor]`(純註解無行為;spec 檔改動同 commit 可)。
- 三類不混;禁 `.skip` / 砍測試 / 改非事前標記 assertion。
- Gate(`frontend/`):`npx vitest run src/components/stock src/lib` + `npx tsc -b` + `npx eslint src/components/stock src/lib` 全綠。

## 回報(純文字)
1. 逐條 finding 處置結果(1 行/條)
2. `git log --format="%h %s" 22d9420c..HEAD`
3. gate exit code / 數字
4. 偏離(無則寫無)
