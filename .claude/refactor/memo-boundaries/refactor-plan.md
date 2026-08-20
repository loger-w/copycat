# Refactor plan:memo 邊界(refactor/memo-boundaries,handoff R6)

> round-1 review(refactor-plan-reviewer)P0×3 / P1×5 / P2×5,除 R12(REFUTED:baseline
> 2323 為本 session 於分支 HEAD=294f604a 實跑)外全數 accepted 併入本版;
> 全文重寫,changelog 見文末。

## Why(gate)

崩潰掃描(2026-08-19)定位的放大因子:App 層掛五條流(指數 ~1s / 廣度 / 個股報價批 1s /
期貨 coalesce 0.1s / 訊號),每則推播重繪整棵樹(App.tsx:146-150 註解自承)。dev 洩漏已由
R0 堵住,但 prod 的**跨流串擾**仍在:右欄閃電梯 subtree 在停留 index/txo/corr tab 或
看個股時,以 10Hz 陪跑期貨 tick;江波圖 hover 一動七腿幾何全重算。為什麼是現在:
handoff 六輪最後一段,行為面(R0–R5)已全數出貨;整天掛機是本專案核心使用型態。

## 量測(先量再改)— 三拍順序(R8)

每步固定三拍,每個 commit 都全綠:
1. 本機先寫計次 harness、在改動前跑出 baseline 數字 N 落
   `evidence/baseline-render-counts-S<N>.txt`(**不 commit 紅斷言**);
2. 🔵 memo commit(行為不變,既有測試全綠);
3. 🟢 commit 計次測試(斷言 0/僅相關者),mutation 抽驗 = 拔 memo/useMemo → 紅。

真環境層:日盤已收(14:27),真 tick trace 驗證窗口 = 夜盤 15:00+(期貨腿)或次一
交易日盤中;降級策略 = 計次測試 + user 過目畫面無異狀。**殘留預期(R13)**:期貨 tab 的
rail 仍隨 `futProd` 10Hz、個股 tab 的 rail 仍隨 `accum` 每 tick —— 可量到 0 的是
index/txo/corr tab 的 rail 與「期貨 tick 不再動 stock ctx」的跨流串擾;真 trace 對照
要以此為預期,期貨頁 scripting 沒降不代表 memo 失效。

## 範圍決策(對照 handoff R6 原文)

- **做**:S1 App→RightRail 邊界、S3 江波圖 corr、S2 MarketPane OverlayCard 幾何
  (順序 S1 → S3 → S2;S2 收益條件性,見該節)。
- **不做(記載理由)**:
  - `PriceLadder` render body 重算:原碼明文標註「純算術每 tick 重算不值得 memo」
    (L234/L237),且其 props(book/last)本來就每 tick 變 — memo 無收益,動它是 churn。
    `LadderView` 同理:其 props 由 PriceLadder 每 render 以 inline JSX/arrow 建構,單獨
    memo 比不過;正確邊界在上游 App→RightRail(S1 覆蓋整條 subtree)。
  - `useChartToggles.set` 包 useCallback(R9 刪):全 repo memo 節點(GroupCard /
    ChartStatic / EnergySub)無一收 `onToggle`,GroupGridView.tsx:142-143 註解更明寫刻意
    不把 `set` 傳進卡片 —— 零受益的 identity churn,記 next-time 待有受益節點再做。
  - `GroupGridView` 2.5 萬 SVG 節點縮減:per-card memo 已存在且有計次測試;節點數縮減
    是視覺/結構設計變更 → 記 next-time。

## 守門事實(R4)

**本 repo 沒有 eslint-plugin-react-hooks**(eslint.config.js 僅 js/tseslint/
react-you-might-not-need-an-effect;GroupGridView.tsx:289-290 註解自承)。useMemo deps
完整性的守門 = 各步的 **App 層 / 元件層計次+內容測試**(見各步),不是 lint。

## 步驟(每步獨立綠、單獨 commit)

### S1 App→RightRail 邊界(預估 diff < 60 行)

- `App.tsx`:`railCtx` 拆兩個 `useMemo` + module 常數 `NONE_CTX`:
  - `stockCtx` deps = [stockCode, stkfutContract, accum](ctx 欄位 name/book/last/meta 全
    derive 自 accum,以 accum 整體為 dep 即完整;實作時對照 L187-200 逐欄核)
  - `futuresCtx` deps = [product, futProd, futContract]
  - `railCtx = tab === "stock" ? stockCtx : tab === "futures" ? futuresCtx : NONE_CTX`
- `RightRail.tsx`:`const RightRail = memo(function RightRail(...))`(專案具名 memo 慣例)。
- 🟢 測試(R5:必須有 **App 層**,harness 層只是補充;量法依 R14–R16):
  - `App.memo.test.tsx`:**mock RightRail 內部葉子、保留真 RightRail 與真 memo**(R14:
    mock RightRail 本體會把要測的 memo 一起換掉 — stub 不包 memo 恆紅、包了 memo 守門
    是空的)。`vi.mock("@/components/stock/PriceLadder")`(必要時加 FuturesLadder /
    StkfutLadder,import 於 RightRail.tsx:5-8),stub push `{book, last, meta}` 記錄。
    拔 `memo(RightRail)` 或漏 railCtx deps 都會紅。
  - **測試前置 tab 必須落在 stock 分支**(R15):`localStorage.setItem("copycat-tab",
    "stock")` + main code(App.test.tsx:728 樣板);否則 railCtx 走 NONE_CTX 恆定,
    斷言零訊號綠。另補一條 index tab 案專測 NONE_CTX。
  - **案例拆分依實際訊息型別**(R16:單一則更新不可能同時動 book/last/meta):
    futures-only 更新 → 葉子計次不變;**book 訊息 → ctx.book 為新值**(右欄舊五檔
    = 真錢風險主案);tick 訊息 → ctx.last 為新值;meta 走換股案。tick 的 seq 必須
    接續 snapshot 的 seq(seq-gap 會觸發自癒 refetch 多一次 setAccum,汙染計次)。
- 風險:deps 漏項 → 右欄顯示舊 book/last/meta。守門 = 上述 App 層測試 +
  RightRail.test.tsx 60 條既有行為測試全綠。

### S3 江波圖 corr(預估 diff < 60 行;R1/R2/R3 硬性要求)

- **前置 characterization(🟢,先行 commit)**:RiverPanel/RiverOverlay 目前無 hover 覆蓋
  (RiverPanel.test.tsx 14 條無 mouseMove 案例)→ 先拍:mouseMove 進圖 → 讀值列出現
  各腿 %(cursor readout);勾掉某腿 → 線消失(已有,確認仍綠)。
  **jsdom 坑(R17)**:handleMouseMove 先取 `getBoundingClientRect()`,jsdom 恆回 0 →
  rect.width===0 早退 → readout 永遠 null。必須
  `vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({...})`
  (先例:MarketChart.test.tsx:416-419 / StockIntradayChart.test.tsx:54-55 /
  FuturesChart.test.tsx:244-245),座標換算假設 svg 等比渲染。
- `RiverPanel.tsx`:`order` useMemo(deps=[state?.legs])、`entries` useMemo
  (deps=**[state?.legs, off]** — `state.base` 不參與計算,不入 deps(R2));
  **兩個 useMemo 必須上提到 `state === null` 早退之前**(R3:否則條件式 hook,
  corr tab 開站即崩),null 分支回 `[]`,entries 內部對 `state?.legs[key]` null 守。
  驗收含 RiverPanel.test.tsx:148 null 案例 + null→有資料連續 render。
- `RiverCards.tsx` `RiverCard`:具名 memo + L28 `buildLegGeometry` 包 useMemo([leg, win])。
- `RiverOverlay.tsx`(R1 切界):useMemo(deps=[entries, win])**只包** `g` 與純 derive 自
  g 的 `labelYs` / `firstOffsets` / `earliest` / `lateStarts`;**`readout` 留在外面**
  (依賴 cursor;或另一個 deps=[g, cursor] 的 useMemo)。hover(cursor setState)不再
  重算七腿幾何,但讀值列照常更新(前置 characterization 守住)。
- 🟢 計次測試:hover 不重算幾何 / 某腿更新只有該卡重繪。**量法(R11)**:優先 mock
  子元件邊界計次 + 樣板的「同輪對照組相對比較」;若必須 mock lib 函式,一律
  `importOriginal` partial mock 並保留其餘 export(`river-chart-svg` 的 `offsetAtX` /
  `spreadLabelYs` / `timeTicks` 是 hover 與時間軸的依賴,漏了座標變 NaN)。

### S2 MarketPane OverlayCard 幾何(預估 diff < 30 行;收益條件性,R10)

- **收益前提**:OverlayCard 只在「重疊」toggle 開啟時 render(預設關)。baseline 量測
  時記錄 toggle 狀態;若 user 日常不開重疊,本步預期收益 = 0(仍做:成本極低、
  開重疊時擋掉 10Hz futures 經 IndexPage 的串擾,收尾對照以此解讀)。
- `MarketPane.tsx` `OverlayCard`:L136 `buildOverlayGeometry(...)` 包 useMemo,
  deps = **[twse.minutes, twse.ref, otc.minutes, otc.ref, height]**(R7:欄位叫 `ref`
  不是 prev_close;`size` 物件是 render 內現建的不可當 dep — MarketPane.tsx:363-366
  既有註解同款警告;`unitScale`/`font` 非幾何輸入不入 deps — 實作時對照
  buildOverlayGeometry 實際簽名逐項核)。
- 🟢 計次測試:同 R11 量法(partial mock `@/lib/index-chart-svg` 必保留
  `X_START_MIN`/`X_END_MIN` 等其餘 export,或改量子元件邊界)。
- 不做 `memo(MarketPane)`:twse/otc 每秒新 identity,skip 命中率低。

### 實作模式

L 級(6 檔)→ 逐步 dispatch(opus),每步三拍(量測 → 🔵 → 🟢);ledger `progress.md`。
dispatch prompt 必附:本 plan 對應節全文 + 守門事實節 + 專案 memo 慣例
(具名 `memo(function X(...))`、穩定 identity 註解、`.memo.test.tsx` 計次樣板)。

## Blast radius

- `railCtx` 唯一消費者 = RightRail(App.tsx:315)。
- `useChartToggles` 呼叫端五處(R6):IndexPage.tsx:108、StockChart.tsx:64、
  StockIntradayChart.tsx:1436、FuturesChart.tsx:94、GroupGridView.tsx:263 —— 本版已
  刪掉動 `set` 的半步,五處均不受影響(記載供後續參照);MarketPane 不呼叫該 hook
  (吃 `onToggle` prop)。
- `order`/`entries` 唯一消費者 = RiverCards/RiverOverlay(RiverPanel.tsx:125/127)。
- 每步跑完整 suite(vitest 全套 + tsc + eslint + react-doctor)。

## 可量化改進(收尾核對)

- 計次:index/txo/corr tab 停留時無關更新下 RightRail subtree 重繪 N→0;期貨 tick 不再
  動 stock ctx(跨流);River hover 幾何重算 每 mousemove→0;OverlayCard 幾何(重疊開啟
  時)10Hz futures 串擾→僅指數分鐘/ref 變更。
- **殘留(R13)**:期貨 tab rail 仍 10Hz(futProd 本來就該動它)、個股 tab rail 仍每
  tick(accum)— 這是正確行為不是 memo 失效。
- 真 tick 層(驗證窗口內):DevTools trace 主執行緒 scripting 對照,以上述殘留為預期。

## Changelog

- [amendment 2026-08-20 round-1 review] R1:RiverOverlay readout(cursor 依賴)切出
  useMemo;S3 前置 hover characterization。R2:entries deps=[state?.legs, off]。
  R3:useMemo 上提早退前 + null 守。R4:守門改 App 層測試(repo 無 react-hooks lint)。
  R5:S1 必有 App 層計次+內容測試。R6:useChartToggles 五呼叫端入 blast radius。
  R7:OverlayCard deps 修正為 [minutes, ref, height]。R8:三拍順序。R9:刪 set
  useCallback 半步(零受益)。R10:S2 收益條件性 + 降序。R11:計次測試量法(子元件
  邊界 / importOriginal partial mock)。R13:殘留預期入量測與收尾。R12 REFUTED
  (baseline sha 正確)。
- [amendment 2026-08-20 round-2 限縮] R14(P1):App 層測試 mock 葉子保留真 memo。
  R15:前置 tab=stock 否則 NONE_CTX 零訊號綠。R16:案例依訊息型別拆分(book/tick/meta)
  + seq 接續。R17:hover characterization 需 getBoundingClientRect spy(jsdom 恆 0 早退)。
  無 P0 → 退出 review,進實作。
