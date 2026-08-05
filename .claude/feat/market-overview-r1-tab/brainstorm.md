# 台股綜合 R1 — tab 整併 + 雙圖 + basis + corr 併入(brainstorm)

日期:2026-08-05
來源:總 spec `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 1
(D-1~D-7 已拍板不重議;user 指示「照 §5 Round 1 做」)。

## 分流判定記錄

已成形方案:條件 1 中(總 spec 指名 UI 形式 + 檔案落點 + 資料流)、條件 2 中
(仍有可拷問決策點:期指入口 / overlay 去留 / corr 掛載時機)→ grilling 姿態,
決策逐題 auto-default(無方向性抉擇,SC 集合不因選項互換而改寫)。

## 環境事實(自查,非假設)

- **basis 價差列已存在**:`IndexPage.tsx` `data-testid="basis-row"` —— 台指期價 +
  價差(TXF spot − 加權,/1000)+ bull/bear 色標 + 缺值「價差 -」。R1 的 basis 工作
  = 雙圖改版時**保留**,非新做。
- **OverlayCard 已存在**:加權 vs 櫃買相對昨收 % 疊線,`overlay` 開關
  (`INDEX_OVERLAY_STORE`)只在 mode=intraday 且非期指時可用。
- IndexPage 單圖狀態 = 3 個 localStorage key(`MARKET_KEY_STORE` / `MARKET_MODE_STORE`
  / `MARKET_FUT_STORE`)+ overlay;`coerceMode` 防非法組合(櫃買+日K)。
- CorrPage = 薄容器:`useCorrelation` + `useRiver` 兩條 WS **都在頁內建立**,
  `visited.corr` gate —— 沒開過 corr tab 就零流量。
- App.tsx:Tab union 五值;`initialTab` 合法清單判定,無值 fallback "index";
  tab label「大盤」。TAB_KEY 舊值全數保留還原(值域不變慣例)。

## 共識方案

一句話:index tab 改名「台股綜合」,單圖抽成可雙掛的 MarketPane(左承舊狀態、
右新增預設櫃買),basis 列與 overlay 能力原樣保留,corr tab 移除、內容以
「展開才 mount」的收合區塊併入,corr WS 建立時機隨之改為「展開才建」。

### [auto-default] 決策清單

1. **Tab id 維持 `"index"`、label 改「台股綜合」** | reason: 值域不變慣例,零遷移;
   `"corr"` 自 union 與 `initialTab` 合法清單移除 → 舊值自動 fallback index。
2. **抽 `MarketPane` 元件**(現單圖邏輯參數化 storage keys + 預設標的);左 pane
   繼承既有 3 key + overlay key(舊使用者狀態不失),右 pane 用新 key、預設 OTC
   | reason: 復用既有邏輯,狀態零丟失。
3. **overlay 疊線保留、僅左 pane 有開關**
   [amendment 2026-08-05: design review R7 — OverlayCard 固定畫加權vs櫃買,右 pane
   開重疊會出現兩張相同圖 + aria-label 重複;原「per-pane 各自開關」收斂為僅左 pane]
   | reason: 不刪既有能力,但避免無意義的重複畫面。
4. **corr 區塊預設收合、展開才 mount(WS 才建立)、展開狀態持久化** | reason:
   index 是預設頁,無條件常駐 corr/river 兩條每秒 WS 違反「沒開就零流量」既有特性;
   持久化讓常看的人只多點一次。
5. **期指入口 = 每 pane 標的列保留「台指期」鈕**(既有形式,總 spec open question 1)
   | reason: 零新 UI,兩 pane 任一張都可切期指。
6. **CorrPage.tsx 保留原樣作為收合區塊的 lazy body**,新增薄的 `CorrSection.tsx`
   收合殼;`CorrPanel` / `RiverPanel` / 兩支 hook 零改動
   [amendment 2026-08-05: 原「CorrPage 退役、內容搬 index/」改為保留 — 零內容 diff
   更小、lazy chunk 邊界不變] | reason: 只加殼不動內容。

## SC(成功條件)

- **SC-1 tab 整併**:tab 列由左至右為「台股綜合 / 個股(期) / 選擇權 / 期貨」,
  不再出現「相關係數」;首顆 label 文字 =「台股綜合」。localStorage `copycat-tab`
  為 `"corr"` 或無值時,開頁落在台股綜合 tab。
  驗證:vitest(App.test.tsx tab 列 + initialTab 遷移案例)+ 截圖。窗口:anytime。
- **SC-2 雙圖並排**:台股綜合 tab 主區同屏可見兩張市場圖:左圖 figcaption 預設
  「加權指數」、右圖預設「櫃買指數」;各圖上方有**自己的**標的列(加權/櫃買/台指期)
  與週期列(分時…月K)。點左圖「日K」→ 僅左圖切日K,右圖模式不變;右圖切「櫃買」時
  日/週/月鈕 disabled(既有 `isModeAvailable`)。重整頁面後兩圖各自的標的/模式保留。
  驗證:vitest(新 MarketPane 測試 + IndexPage 雙 pane 獨立性案例)+ 截圖。窗口:anytime。
- **SC-3 basis 保留**:雙圖版面內仍可見 `basis-row` 一列:「台指期 <價> 價差 <±x.xx>」,
  正價差紅(text-bull)/ 逆價差綠(text-bear)/ 期貨無資料顯示「價差 -」。
  驗證:既有 basis 測試沿用 + 截圖;數值正確性盤中對照(窗口外 fixture 斷言算式)。
- **SC-4 corr 併入**:雙圖下方有標題「相關係數」的收合區塊,預設收合;點擊展開後
  可見六腿江波圖(RiverPanel)與相關係數表(CorrPanel),展開狀態重整後保留;
  **收合時不建立 corr/river WS**(mock WebSocket 計數 = 0),展開才建立。
  驗證:vitest(WS 建立計數 + 展開持久化)+ 截圖。窗口:anytime。
- **SC-5 regression**:`npm test` 全綠;`git diff --stat` 不含 stock/ txo(QuoteTable
  等)/ futures/ capital/ rail/ 元件(corr/ 目錄僅允許**新增** CorrSection.tsx,
  既有檔零改動)[amendment 2026-08-05: 隨 decision 6 amendment 同步]。
  驗證:npm test + tsc + eslint + diff 檢查。窗口:anytime。

## Edge cases

1. 兩 pane 選同一標的(都加權)→ 允許,合理用法(左分時右日K)。
2. 右 pane 預設 OTC + 舊 `MARKET_MODE_STORE` 殘值是日K → 右 pane 有自己的 key,
   初始 `coerceMode` 防非法組合(左 pane 繼承舊值時同樣過 coerce,既有邏輯)。
3. futures engine 間歇零推播(§8 已知)→ basis 列顯示「價差 -」,既有行為保留。
4. corr 區塊展開→收合 → unmount,hook cleanup 斷 WS(既有 cleanup 邏輯,測試驗證)。
5. 窄視窗:雙圖 wrap 成上下疊(flex-wrap / grid),不橫向溢出(frontend-conventions
   響應式慣例,Phase 1 定具體斷點)。
6. 盤後 / 休市:兩圖與 basis 顯示最後值或「-」,無新增行為。

## Out of scope

- 家數帶 / 騰落線(R2)、漲跌停列表(R3)、類股強弱 / 訊號事件流(R4)。
- 期貨 tab / 個股 tab / TXO tab 任何改動(SC-5 白名單)。
- 第三張圖、pane 數可設定化。
- CorrPanel / RiverPanel / useCorrelation / useRiver 內部任何改動。
- 後端任何改動(本輪零後端)。

## 執行約束(跨輪掃描)

- 總 spec §6:UI SC = AI 截圖(claude-in-chrome)+ user 過目雙層;驗前端只起 vite dev
  (盤中不起第二台連 TC4 的後端)。
- 前輪 index-board 白名單精神延續:個股頁零改動;TAB_KEY 值域不變(本輪唯一例外:
  `"corr"` 移出合法清單 = 刻意遷移,SC-1 涵蓋)。
- 寫 frontend 前先讀 `frontend-conventions` / `frontend-testing` skill(Phase 3)。

## 規模分流

L(預計動檔 ≥5:App.tsx / IndexPage.tsx / 新 MarketPane.tsx / 新 corr 收合區塊 /
constants.ts / CorrPage.tsx 刪 + 測試檔群;純前端、無鑑權/金流/hot path 高風險面
→ 輪數同 M)。
