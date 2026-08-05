# 台股綜合 R1 — design.md

版本:v2(2026-08-05)
Changelog:
- v2:design review round 1 修入 —— R1 pane 錨點 + 既有測試歸屬表;R2 CorrSection
  測試防 lazy vacuity(vi.mock stub + 真身案例分離);R3 fmt 各留一份 /
  FuturesProductState 遷 MarketPane 並 re-export;R5 移除不存在的 readStorage、
  fallback 文字改可辨識;R6 mode initializer 雙 fallback 同源;R7 重疊鈕收斂僅左
  pane(省 MARKET2_OVERLAY_STORE);R8 SC-5 白名單判讀規則明文化;R4 記 Known Risks。
- v1:初版。

對應 brainstorm:`.claude/feat/market-overview-r1-tab/brainstorm.md`(SC-1~SC-5)。
總 spec:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 1。

**Goal**:index tab 改造為「台股綜合」— 雙指數並排圖(MarketPane 抽取)+ basis 保留
+ corr 收合併入、corr tab 移除。純前端,零後端改動。

**架構一句話**:把 IndexPage 的單圖邏輯抽成參數化 storage keys 的 `MarketPane`,
IndexPage 變薄容器(basis 列 + 兩個 pane + CorrSection 收合殼),App.tsx 縮 Tab union。

---

## §0 檔案清單(全貌)

| 檔案 | 動作 | 對應 SC |
|------|------|---------|
| `frontend/src/App.tsx` | 改:Tab union 刪 `"corr"`、initialTab 合法清單刪 `"corr"`、label「大盤」→「台股綜合」、刪 CorrPage lazy import / visited.corr / corr panel 區塊 | SC-1 |
| `frontend/src/components/index/MarketPane.tsx` | 新:單圖 pane(自 IndexPage 抽出) | SC-2 |
| `frontend/src/components/index/IndexPage.tsx` | 改:薄容器化(basis 列 + 雙 pane + CorrSection) | SC-2/3/4 |
| `frontend/src/components/corr/CorrSection.tsx` | 新:收合殼,展開才 lazy mount CorrPage | SC-4 |
| `frontend/src/components/corr/CorrPage.tsx` | 僅檔頭註解更新(gate 敘述過時,R8;單獨 🔵 commit) | SC-4/5 |
| `frontend/src/lib/constants.ts` | 改:新增右 pane 3 key + corr 展開 key(無 overlay key,R7),註解更新 | SC-2/4 |
| `frontend/src/App.test.tsx` | 改:tab 列 / 遷移案例 | SC-1 |
| `frontend/src/components/index/IndexPage.test.tsx` | 改:雙 pane 結構 + 獨立性 + basis | SC-2/3 |
| `frontend/src/components/index/MarketPane.test.tsx` | 新 | SC-2 |
| `frontend/src/components/corr/CorrSection.test.tsx` | 新 | SC-4 |

不動:`CorrPanel` / `RiverPanel` / `useCorrelation` / `useRiver` / `MarketChart` /
`timeframe.ts` / `stock/` / `futures/` / `capital/` / `rail/` / TXO 系 / 後端全部。

---

## §1 App.tsx tab 整併(SC-1)

- `type Tab = "txo" | "stock" | "futures" | "index"`(刪 `"corr"`)。
- `initialTab()`:合法清單刪 `"corr"` → 舊 localStorage 值 `"corr"` 自然 fallback
  `"index"`(不寫遷移碼;值域縮減 = 刻意行為,SC-1 驗證)。
- nav 陣列:`["index", "台股綜合"]`,刪 `["corr", "相關係數"]` 條目。
- 刪:`const CorrPage = lazy(...)`、`visited` 的 `corr` 欄、corr panel `<div hidden=...>`。
  `visited` type 隨 Tab union 縮小自動對齊。
- IndexPage 的 props 與呼叫點**不變**(twse/otc/txf/futures 照傳)。

## §2 MarketPane 抽取與雙掛(SC-2)

### MarketPane.tsx(新檔;邏輯 = 現 IndexPage 206-346 行參數化)

```tsx
export interface PaneStores {
  key: string;      // MarketKey 持久化 key
  mode: string;     // MarketMode 持久化 key
  fut: string;      // 期指商品(TXF/MXF/TMF)持久化 key
  overlay?: string; // overlay 開關持久化 key;undefined = 不顯示重疊鈕(右 pane)
}

/** 期貨三檔即時狀態 —— 自 IndexPage.tsx:44 遷入本檔並 export;
 *  IndexPage `export type { FuturesProductState } from "./MarketPane"` 保外部相容
 *  (`import type` 匯入,無執行期循環)。 */
export interface FuturesProductState { p: number | null; ref: number | null; }

interface MarketPaneProps {
  paneId: "left" | "right";        // data-testid={`market-pane-${paneId}`}(R1 錨點)
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  futures?: Record<string, FuturesProductState> | null;
  stores: PaneStores;
  defaultKey: MarketKey;           // 左 "TWSE" / 右 "OTC"
  toggles: ChartToggles;           // useChartToggles 上提 IndexPage(單一實例,
  onToggle: (k, v) => void;        //  兩 pane 共享 bb 開關 — 現行為即全域單開關)
}
```

- 根節點 `<section data-testid={"market-pane-" + paneId}>`(R1:測試以
  `within(getByTestId(...))` 選取,消除雙 pane 重名 ambiguity)。
- 內部 state(key/mode/futKey/overlay)與 `selectKey` / `selectMode` / `selectFut` /
  `toggleOverlay` / `coerceMode` 防非法組合:**照抄現邏輯**,僅 localStorage key 改讀
  `props.stores.*`;**兩處 fallback 同源改 `props.defaultKey`**(R6):key initializer
  的 fallback **與** mode initializer 內餵給 `coerceMode` 的
  `isMarketKey(savedKey) ? savedKey : "TWSE"` 的 `"TWSE"` —— 各判各的會複製既有
  review P1-5 的「落在 disabled 模式」bug 到右 pane。
- **重疊鈕僅左 pane 顯示**(R7):`stores.overlay === undefined` 時不渲染該鈕、
  不建 overlay state —— OverlayCard 畫的固定是加權vs櫃買,右 pane 開重疊會出現
  兩張相同圖 + `aria-label` 重複。`MARKET2_OVERLAY_STORE` 因此**不新增**。
- `Btn` / `Quote` / `OverlayCard` / `NAMES` / `FUT_LABELS` / `toX` / `SIZE`
  隨遷入 MarketPane.tsx(IndexPage 中刪除)。`fmt` **兩檔各留一份**(R3):
  BasisRow(留 IndexPage)也用 `fmt` —— MarketChart / CandleChart 本就各有一份
  fmt,依既有慣例複製,不動 `@/lib/format`。
- figure 佈局改:**不再 `flex-1` 撐滿頁高**(雙 pane 並排 + 下方 corr 區塊,
  高度由 SVG viewBox 比例驅動,`w-full`)。
- basis 列**不在** MarketPane 內(見 §3)。

### IndexPage.tsx(薄容器化)

```tsx
export function IndexPage({ twse, otc, txf, futures }: Props) {  // Props 不變
  const { toggles, set } = useChartToggles();
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <BasisRow txf={txf} twse={twse} />                       {/* §3 */}
      <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(480px,1fr))]">
        <MarketPane stores={LEFT_STORES}  defaultKey="TWSE" ... />
        <MarketPane stores={RIGHT_STORES} defaultKey="OTC"  ... />
      </div>
      <CorrSection />                                           {/* §4 */}
    </div>
  );
}
```

- `LEFT_STORES` = 既有 4 key(`MARKET_KEY_STORE` / `MARKET_MODE_STORE` /
  `MARKET_FUT_STORE` / `INDEX_OVERLAY_STORE`)→ 舊使用者左圖狀態零丟失。
- `RIGHT_STORES` = 新 4 key(§5)。
- 響應式:`repeat(auto-fit, minmax(480px, 1fr))` — 寬 ≥ ~1000px 並排、
  窄視窗自動上下疊,無橫向溢出(edge case 5)。

## §3 basis 列(SC-3)

- 現 IndexPage 標的列尾端的 basis span(`data-testid="basis-row"`,含台指期價 /
  價差色標 / 「至 HH:MM」)抽成 `BasisRow` 小元件,**置於雙圖上方**獨立一列。
- 計算式與呈現**零改動**:`basis = (txf.p - twse.p) / 1000`、正 `text-bull` /
  負 `text-bear` / 缺值「價差 -」。
- 位置:IndexPage 直下第一列(雙 pane 之上),與 pane 無關(pane 切什麼標的都顯示)。
- `BasisRow` 定義於 IndexPage.tsx 內(私有小元件,不另開檔)。

## §4 CorrSection 收合殼(SC-4)

### CorrSection.tsx(新檔,components/corr/)

```tsx
const CorrPage = lazy(() => import("@/components/corr/CorrPage"));

export function CorrSection() {
  // 直接 getItem(R5:codebase 無 readStorage helper);初始化在 useState initializer
  // 內,Safari 私密視窗拋錯時外層不炸 —— 包 try/catch 回 false
  const [open, setOpen] = useState<boolean>(() => {
    try { return window.localStorage.getItem(CORR_OPEN_KEY) === "1"; }
    catch { return false; }
  });
  ...
  return (
    <section className="rounded-md border border-line bg-surface">
      <button type="button" aria-expanded={open} onClick={toggle}
              className="flex w-full items-center gap-2 px-4 py-2 text-left">
        <span className="text-sm font-bold text-ink">相關係數</span>
        <span className="text-xs text-ink-dim">{open ? "收合" : "展開"}</span>
      </button>
      {open ? (
        <div className="px-4 pb-4">
          {/* fallback 文字刻意與 CorrPanel 空狀態(「載入中…」)區隔(R5),
              測試錨點才能區分「仍 suspend」與「CorrPage 已 mount」 */}
          <Suspense fallback={<p className="py-6 text-center text-sm text-ink-muted">相關係數載入中…</p>}>
            <CorrPage />
          </Suspense>
        </div>
      ) : null}
    </section>
  );
}
```

- **WS gate 機制**:`useCorrelation` / `useRiver` 活在 CorrPage 內(現況);
  `open === false` 時 CorrPage 不 render → hook 不 mount → **零 WS**。
  展開 → mount 建線;收合 → unmount,hook 既有 cleanup 斷線(edge case 4)。
- lazy chunk 邊界不變(原 App 層 lazy 移到這裡,corr bundle 仍按需載入)。
- 展開狀態寫 `CORR_OPEN_KEY`("1"/"0"),寫入包 try/catch(useChartToggles
  `persist()` 慣例)。
- 收合時 CorrPage unmount 即丟當下 corr 表格狀態 — 可接受:corr 資料是 WS
  推播的即時狀態,重展開重建(與原「切離 corr tab 再回來」... 原本 App 用
  `hidden` 保 DOM,tab 切走不 unmount。**行為差異**:收合=unmount。記入
  Known Risks R2。

## §5 constants.ts 新增 key(SC-2/4)

```ts
/** 台股綜合右圖標的 — components/index/IndexPage.tsx(左圖沿用 MARKET_KEY_STORE) */
export const MARKET2_KEY_STORE = "copycat-market2-key";
export const MARKET2_MODE_STORE = "copycat-market2-tf";
export const MARKET2_FUT_STORE = "copycat-market2-fut";
/** 相關係數收合區塊展開狀態("1" 展開)— components/corr/CorrSection.tsx */
export const CORR_OPEN_KEY = "copycat-corr-open";
```

(v2:`MARKET2_OVERLAY_STORE` 隨 R7「重疊鈕僅左 pane」取消,不新增。)
既有 `MARKET_*` 4 key 註解補「左圖」字樣。`TAB_KEY` 註解值域更新(刪 corr)。
無孤兒鍵產生(舊 4 key 由左 pane 續用)。

## §6 資料流(不變部分明示)

- App 層 `useIndexStream` / `useFuturesStream` 建立時機與傳遞**零改動**;
  IndexPage props 介面不變 → App.tsx 對 IndexPage 的呼叫點只受 tab 整併影響。
- corr / river WS:唯一改動 = gate 從 `visited.corr`(tab 級)變成
  `CorrSection.open`(區塊級)。連線位址、hook 內容不動。
- 後端零改動;無新 API。

## §7 測試計畫(對應 SC)

| 測試檔 | 案例 | SC |
|--------|------|-----|
| App.test.tsx | tab 列 = 台股綜合/個股(期)/選擇權/期貨(無「相關係數」);`TAB_KEY="corr"` 時初始 tab = index;**既有改動明細(R1)**:`getByRole("tab",{name:"大盤"})` 7 處改「台股綜合」、「5 顆 tab」計數斷言改 4 | SC-1 |
| MarketPane.test.tsx | (a) defaultKey 尊重(無 storage 時右 pane 顯示櫃買);(b) storage keys 注入生效(寫入到指定 key);(c) OTC 時日/週/月 disabled;(d) 殘值日K+OTC 經 coerce 回 intraday;(e) 期指子鈕切換;(f) **只寫 mode=day 不寫 key** → defaultKey=OTC 落分時、無 disabled 模式被選中(R6);(g) `stores.overlay` undefined 時無「重疊」鈕(R7);**+ 自 IndexPage.test.tsx 搬遷的既有案例**(單 pane 渲染免 ambiguity):標的列切換 / 週期列 / 櫃買降級 / 重疊(左 pane 形態)/ market-meta 群 | SC-2 |
| IndexPage.test.tsx | (a) 兩個 pane 同屏:`getByTestId("market-pane-left")` 內 figcaption「加權指數」、right 內「櫃買指數」;(b) 獨立性:`within(left)` 點「日K」→ left 內日K active、`within(right)` 分時仍 active;(c) basis-row 存在 + 缺值「價差 -」+ 色標(既有案例留此);**選取慣例(R1):一律 `within(screen.getByTestId("market-pane-*"))`,不裸用 getByRole** | SC-2/3 |
| CorrSection.test.tsx | **防 lazy vacuity(R2),閘門與 lazy 分開測**:(a)(c)(d) 以 `vi.mock("@/components/corr/CorrPage")` 換同步 stub(mount 時計數/開 mock WS)—— (a) 預設收合 stub 零 mount + `WebSocket` 建構 0;(c) 展開寫 localStorage、重 mount 保持展開;(d) 展開後收合 → stub unmount(cleanup 斷線由既有 hook 測試把關);(b) **lazy 真身案例**(不 mock):展開後 `await findByText("六腿走勢")`(RiverPanel 專屬文字,與 fallback「相關係數載入中…」可區分) | SC-4 |
| (跑全套) | `npm test` 全綠 + `git diff --stat` 白名單檢查 | SC-5 |

**SC-5 白名單判讀規則(R8)**[amendment 2026-08-06: code review F2 — 實際新增
**三檔**:`CorrSection.tsx` + `CorrSection.test.tsx` + `CorrSection.lazy.test.tsx`,
lazy 真身案例因 vi.mock 檔案級 hoist 無法與 stub 案例同檔,拆檔為 PLAN T3 預授權
路徑];既有檔中**僅允許 `CorrPage.tsx` 檔頭註解更新**
(「沒開過這個 tab 就不會有流量」在 tab 移除後成錯敘述 — 單獨一個 🔵 註解 commit,
不碰任何執行碼);stock/ futures/ capital/ rail/ TXO 系與後端零 diff。

frontend-testing skill 的 mock 慣例(vi.spyOn / 無 jest-dom 替代寫法)Phase 3 開工先讀。

## Known Risks

- KR-1(P2):`repeat(auto-fit, minmax(480px, 1fr))` 在極窄視窗(<480px)單欄仍可能
  溢出 — 桌面看盤工具,非目標視窗;jsdom 不驗 layout,截圖層把關。
- KR-2(P1):corr 區塊「收合 = unmount」與原 corr tab「切走保 DOM」行為不同 —
  重展開有 lazy 載入 + WS 重連的短暫空窗。判定可接受:corr 是即時推播資料,
  重建狀態秒級恢復;換得「不看零流量」特性在預設頁成立。
- KR-3(P2):兩 pane 共享 `useChartToggles`(bb 開關)單實例上提 — 與現行全域
  單開關行為一致,非新差異。
- KR-4(P2,review R4):`CORR_OPEN_KEY="1"` 持久化後,因 `visited.index` 恆 true
  (IndexPage 常駐掛載),**下次開頁即使停在其他 tab,corr/river WS 也在 App 啟動
  即建立**。判定可接受:user 展開過 = opt-in(原設計 session 內開過 corr tab 後
  切走也持續推播,差異僅在跨 session 持久化);不加 `active` prop —— 加了會讓
  「切離 index tab」變成斷線/重連,對常看 corr 的人更差。
