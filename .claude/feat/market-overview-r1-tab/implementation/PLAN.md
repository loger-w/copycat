# 台股綜合 R1 — implementation PLAN(condensed,v2)

依 design.md v2;impl-spec review round 1(R1-R11)全數修入。
TDD 紅先行,commit tag 依 feat.md Phase 3。
Task 順序 = 依賴順序(review R1 修正):T1(constants)→ T2(MarketPane)→
T3(CorrSection)→ T4(IndexPage 薄容器化)→ T5(App tab 整併)→ T6(CorrPage 註解 🔵)。
寫 frontend 前先讀 `frontend-conventions` + `frontend-testing` skill。

## T1 `frontend/src/lib/constants.ts`

- 新增 4 export:`MARKET2_KEY_STORE = "copycat-market2-key"` /
  `MARKET2_MODE_STORE = "copycat-market2-tf"` / `MARKET2_FUT_STORE = "copycat-market2-fut"`
  (右 pane **3 key**,無 overlay key — design R7)+
  `CORR_OPEN_KEY = "copycat-corr-open"`。
- 既有 `MARKET_*` 4 key 註解補「左圖」;`TAB_KEY` 註解值域刪 corr。
- 無測試(純常數);併入 T2 的 [red] 前置或綠 commit。

## T2 `frontend/src/components/index/MarketPane.tsx`(新)+ `MarketPane.test.tsx`(新)

- 抽取範圍(review R7 修正):IndexPage helper 群(27-196 行:`SIZE`/`FUT_LABELS`/
  `NAMES`/`fmt`/`toX`/`Btn`/`OverlayCard`/`Quote`)整批遷入 + IndexPage 元件本體
  (206-346)中**除 basis span(279-293,留給 T4 BasisRow)以外**的狀態邏輯與版面。
  `fmt` 為複製(IndexPage 留一份給 BasisRow,MarketChart/CandleChart 既有慣例)。
- `export interface PaneStores { key: string; mode: string; fut: string; overlay?: string }`。
- 期貨型別(review R10 修正):**不沿用 `FuturesProductState` 名**(@/types 有同名
  13 欄型別,避免第二個 export point)——
  `export interface PaneFutState { p: number | null; ref: number | null }`;
  IndexPage 的舊 `export interface FuturesProductState` 刪除(Phase 3 先 grep 確認
  全 repo 無 import 自 IndexPage 的使用點,有則回 PLAN 補相容節)。
- Props:`paneId: "left"|"right"`(根節點 `<section data-testid={"market-pane-"+paneId}>`)、
  `twse`/`otc`/`futures?: Record<string, PaneFutState> | null`/`stores`/`defaultKey`/
  `toggles`/`onToggle`。
- 狀態邏輯照抄,**兩處 fallback 同源 `props.defaultKey`**(design R6:key initializer
  + mode initializer 餵 `coerceMode` 的 savedKey fallback);localStorage 讀寫走
  `props.stores.*`;`stores.overlay === undefined` → 不渲染重疊鈕、不建 overlay state。
- figure 不 `flex-1`,`w-full` 由 viewBox 比例驅動。
- 失敗測試(SC-2):design §7 表 (a)-(g) 七案 + 自 IndexPage.test.tsx 搬遷的既有
  單 pane 案例(標的列/週期列/櫃買降級/重疊左形態/market-meta)。

## T3 `frontend/src/components/corr/CorrSection.tsx`(新)+ `CorrSection.test.tsx`(新)

(review R1 修正:提前到 IndexPage 之前 —— T4 要 import 它。)

- 依 design §4 v2 草案:lazy CorrPage、open state(getItem try/catch,預設收合)、
  toggle 寫 `CORR_OPEN_KEY`(persist try/catch 慣例)、`aria-expanded`、
  fallback 文字「相關係數載入中…」。
- 失敗測試(SC-4,防 vacuity — design R2 + review R3/R8):
  - (a)(c)(d) 以 `vi.mock("@/components/corr/CorrPage")` stub;factory **回
    `{ default: Stub }`**(CorrPage 是 default export,漏了 lazy 解析直接炸);
    Stub render `<div data-testid="corr-stub" />` 並在 mount/unmount 記數。
    lazy 即使被 mock 仍非同步 —— (c)(d) 展開後**先 `await findByTestId("corr-stub")`
    確認已 mount** 再斷言;(d) 斷言 unmount 計數 +1,不只 query null。
    (a) 預設收合:`await act(async () => {})` flush 後 stub mount 計數 0 +
    `WebSocket` 建構 0。
  - (b) lazy 真身案例(不 mock CorrPage):stub `fetch`(`/api/corr/state`、
    `/api/river/state` 回 404/空)+ mock `WebSocket`(防 jsdom 真連線);展開後
    `await findByText("等待六腿資料…")`(review R3:「六腿走勢」需 river 資料才渲染,
    無資料真身必渲染等待文案,與 fallback「相關係數載入中…」可區分)。

## T4 `frontend/src/components/index/IndexPage.tsx` + `IndexPage.test.tsx`

- 薄容器化:Props 介面不變(twse/otc/txf/futures;futures 型別改
  `Record<string, PaneFutState> | null`,review R10);**不做型別 re-export**。
- `BasisRow` 私有元件(basis span 279-293 原樣搬入,`data-testid="basis-row"` 不變,
  含 fmt 本地一份)置頂;雙 pane grid
  `grid gap-3 grid-cols-[repeat(auto-fit,minmax(480px,1fr))]`:
  left = 既有 4 key(`MARKET_KEY_STORE`/`MARKET_MODE_STORE`/`MARKET_FUT_STORE`/
  `INDEX_OVERLAY_STORE`)+ defaultKey TWSE、right = `MARKET2_*` 3 key(無 overlay)
  + defaultKey OTC;`useChartToggles` 上提、toggles/set 下傳兩 pane;
  尾接 `<CorrSection />`(T3 已存在)。
- 失敗測試(SC-2/3/4;選取一律 `within(getByTestId("market-pane-*"))`):
  - (a) 兩 pane 同屏:left 內 figcaption「加權指數」、right 內「櫃買指數」。
  - (b) 獨立性:`within(left)` 點「日K」→ left 日K active、right 分時仍 active。
  - (c) basis-row 存在 + 缺值「價差 -」+ 色標(既有案例留此)。
  - (d) **stores 接線持久化**(review R4):`within(right)` 點「加權」與「日K」→
    `copycat-market2-key`/`copycat-market2-tf` 被寫入且
    `copycat-market-key`/`copycat-market-tf` **不變**;反向 `within(left)` 操作寫舊
    key、market2 不變。
  - (e) **CorrSection 整合**(review R5):`getByRole("button", { name: /相關係數/ })`
    存在、`aria-expanded="false"`,且位於 basis-row 之後
    (`compareDocumentPosition`)。
  - 搬往 MarketPane.test.tsx 的既有案例自本檔刪除。
- **既有 App.test.tsx:108-116 在本 task 轉紅**(review R2:裸 `getByRole` 取
  櫃買/台指期/日K 在雙 pane 下 ambiguous)→ 本 task 一併改為
  `within(screen.getByTestId("market-pane-left"))`,不留到 T5。

## T5 `frontend/src/App.tsx` + `App.test.tsx`

- Tab union 刪 `"corr"`;`initialTab` 合法清單刪 `"corr"`;nav 陣列
  `["index","台股綜合"]`、刪 corr 條目;刪 CorrPage lazy import / visited.corr /
  corr panel div。IndexPage 呼叫點不動。
- `initialTab` 檔頭註解更新(review R9):「值域不變(五個舊值)」改為
  「值域縮減一項:corr 移出合法清單 → 舊值 fallback index(SC-1 刻意遷移)」。
- 失敗測試(SC-1)+ 既有改動明細(review R6,實際落點):
  - 新增:tab 列四顆(無「相關係數」、首顆「台股綜合」);`TAB_KEY="corr"` → 初始 index。
  - 既有:5 處 `name: "大盤"`(:80/:91/:104/:110/:192)改「台股綜合」;
    :142 labels 陣列改 4 項(刪「相關係數」);:206 顆數 5→4;
    :78/:89/:108/:134 it 標題與 :138/:204 註解同步改。

## T6 `frontend/src/components/corr/CorrPage.tsx`(僅註解)

- 檔頭「沒開過這個 tab 就不會有流量」改為 gate 在 CorrSection 展開的敘述。
- 單獨 🔵 commit(純註解無行為,不掛 TDD tag)。

## 驗證(每 task 綠後跑,T5 後全套)

`npm test` / `npx tsc -b` / `npx eslint src`(frontend/);後端 gate 不受影響
(零後端 diff),Phase 5 仍照 auto-verify 全跑。SC-5 白名單判讀規則見 design §7。
