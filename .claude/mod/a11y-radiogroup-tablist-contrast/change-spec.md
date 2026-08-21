# change-spec — a11y 批:radiogroup + tablist 補全 + 零態對比 + 側欄鍵盤(mod/a11y-radiogroup-tablist-contrast,R2 / D)

分流判定:**已成形方案**(§R2 指名做法:sr-only radio + label / tablist 補 aria-controls / 換 token / row focus+Enter)。
Scope:**L**(≥ 5 檔,但無對外 API、無 migration;全為語意與鍵盤層)。現況見 `current-state.md`。

## 拍板(auto-default)

- **D1 樣板 = 共用元件 `RadioPills`**(`frontend/src/components/ui/RadioPills.tsx`):
  `<fieldset role="radiogroup" aria-label>` 內每項 `<input type="radio" class="peer sr-only" name={useId()} checked onChange>` +
  `<label htmlFor>`(class 由呼叫端 `pillClass(item, checked)` 回傳,**逐字沿用原 button 的 class**);
  `disabled` 項 input disabled(label 加 `aria-disabled` 保留樣式鉤)。
  `[auto-default: 一支共用元件而非八處各寫 | reason: next-time 明寫「樣板級決定,四處一併」;原生 radio 免費給單選 / 方向鍵 / roving tabindex,不自寫 key handler]`
- **D2 涵蓋範圍 = current-state §1 表列的 8 檔單選 pill(含同構 FuturesPage / StockChart / FuturesChart / MarketPane)**;
  toggle 類保留 `aria-pressed`;GroupGridView 卡片 `role=button` 不動。
  `[auto-default | reason: §R2 明列「含 FuturesPage/FuturesLadder/MarketPane 同構處(grep)」;FuturesLadder 三顆是開關非單選,grep 結果歸 toggle]`
- **D3 tablist 只有 RightRail 一處**(IndexPage subtab 2026-08-16 退役)。補:每 tab `id` + `aria-controls={panelId}`、
  `tabIndex={selected ? 0 : -1}`、`onKeyDown` ←/→/Home/End 切換並 focus;panel 外層 `<div role="tabpanel" id aria-labelledby>`
  包住既有條件 render(**不改成 hidden**,D-13)。`[auto-default | reason: WAI-ARIA APG tabs 樣板;條件 render 紀律不破]`
- **D4 零態色三處 `text-ink-dim` → `text-ink-muted`**(WatchlistSidebar 94 / 498、GroupGridView 91);不動其他 dim 用法。
- **D5 側欄 row**:`div` 加 `role="button" tabIndex={0}` + Enter/Space(preventDefault)→ `onSelect`;
  `aria-pressed={active === code}`(選取態);拖曳握把照舊 `aria-hidden`。排序鍵盤路徑 **不在本輪**(next-time 保留)。
  `[auto-default: 不換成 <button> | reason: row 內含握把 / 群組鈕 / 移除鈕等互動子元素,button 內巢狀 button 是無效 HTML;照 GroupGridView 卡片既有 role=button 樣板]`
- **D6 視覺零變**:label 沿用原 button 全部 class;focus ring 改 `peer-focus-visible:ring-1 peer-focus-visible:ring-accent`
  (原 button 的 focus-visible 外觀由瀏覽器預設 outline 提供;sr-only input 的 outline 不可見,必須補 label 側)。
  `[auto-default | reason: 鍵盤使用者否則完全看不到焦點]`

## 成功條件
- **SC-1 radiogroup 語意**:每處 `getByRole("radiogroup", { name })` 內 `getAllByRole("radio")` 數 = 選項數、恰一個 `checked`、
  click label / radio 觸發原 onChange、**只有 checked 的那顆 tabIndex=0**(原生 radio 行為,jsdom 可查 `tabIndex`)。
  驗證:每個改動檔的既有測試改寫 + `RadioPills.test.tsx`(單選 / disabled / 方向鍵 ArrowRight 在原生 radio 由瀏覽器處理 —— jsdom 不實作,
  測「checked 者 tabIndex 0、其餘 −1」即可)。
- **SC-2 tablist 完整**:RightRail `getAllByRole("tab")` 每顆有 `aria-controls` 指向存在的 `role=tabpanel` 且 panel `aria-labelledby` 回指;
  選中 tab `tabIndex=0` 其餘 −1;`fireEvent.keyDown(tab, { key: "ArrowRight" })` 切到下一 tab 並 `document.activeElement` 為它;
  End/Home 到尾/首。驗證:RightRail.test 新案。
- **SC-3 對比**:三處零態元素 class 含 `text-ink-muted` 且不含 `text-ink-dim`。驗證:WatchlistSidebar.test / GroupGridView.test 新斷言。
- **SC-4 側欄 row 鍵盤**:`wl-row-2330` 有 `tabIndex=0`、`role=button`;`fireEvent.keyDown(row, { key: "Enter" })` 與 `" "` 都呼叫 `onSelect("2330")`,
  且 Space 的 keydown `defaultPrevented === true`。驗證:WatchlistSidebar.test 新案。
- **SC-5 畫面可指認(UI)**:個股頁交易別 pill / 檢視 pill / 圖表模式列 / 右欄分頁列,截圖與改前**像素級相同外觀**
  (Tab 到 pill 時出現 accent ring 為唯一新增)。驗證:headless 1600×900 截圖前後對照 `docs/specs/mod-a11y-radiogroup-tablist-contrast/screenshots/` + user 過目。

## 不能破壞的既有行為白名單
- W1 每處 pill 的 onChange / onClick 行為與 persist(localStorage key 與值)不變;選中態 class 不變。
- W2 toggle 類(follow / armed / locked / showBb / overlay toggles / 卡片 active)保留 `aria-pressed`,相關測試不動。
- W3 MarketPane `PeriodButton` 的 `disabled` + `aria-disabled` + compact `@max-[26.5rem]:px-1` 行為與 `MarketPane.size.test` 不動。
- W4 RightRail 的 D-13 條件 render(非 active panel unmount)不變;`selectTab` persist 不變;`RAIL_TAB_KEY` 讀寫不變。
- W5 WatchlistSidebar 拖曳(pointer)流程、群組收合 `aria-expanded/aria-controls`、`onSelect` 滑鼠點擊路徑不變;握把 click 仍 stopPropagation。
- W6 react-doctor 既有誤報 triage 不翻案(GroupGridView 卡片 `prefer-tag-over-role`)。
- W7 所有非 pill 文案、版面 gap / padding 不變。

## Out of scope
GroupGridView 卡片改 radio;自選列組內排序鍵盤路徑;其他 `text-ink-dim` 用法;IndexPage(無 tablist);Radix Tabs 引入。

## Edge cases
1. radiogroup 所有選項 disabled(MarketPane 期貨態模式列)→ 無 tabIndex 0 者,focus 跳過整組(原生行為,允許)。
2. 同頁多個 radiogroup(OrderPanel 兩組、MarketPane 三列 × 兩 pane)→ `name` 必須以 `useId()` 唯一,否則互相搶選。
3. RightRail 只剩一個 tab(不可能,但 Arrow 在單 tab 時 no-op 不拋)。
4. 側欄 row 內按 Enter 在子按鈕上(群組 / 移除鈕)→ 事件由子鈕處理,row handler 要 `e.target === e.currentTarget` 才觸發,避免雙觸發。
5. label 點擊在 disabled radio → 不觸發 onChange。

## Diff 級章節(三類)
- 🟢 `components/ui/RadioPills.tsx` + `RadioPills.test.tsx`(新元件;先紅後綠)。
- 🔴 八檔 pill 換 `RadioPills`(PriceLadder / StockPage / GroupGridView 群組列 / OrderPanel ×2 / FuturesPage / StockChart / FuturesChart / MarketPane PeriodButton 三列):
  既有測試 **該紅**:上列檔的 `aria-pressed` 斷言改 `getByRole("radio", { name }).checked`;toggle 斷言**不該紅**。先改測試紅 → 再換實作綠。
- 🔴 RightRail tablist 補全(RightRail.test 新案先紅)。
- 🔴 零態三處換 token(測試先紅)。
- 🔴 WatchlistSidebar row 鍵盤(測試先紅)。
- 🔵 無預期(如需抽共用 class 常數再標)。
- 包切法:包 A = RadioPills + stock 側(PriceLadder / StockPage / GroupGridView / OrderPanel)+ 零態 + 側欄 row;
  包 B = futures/index 側(FuturesPage / StockChart / FuturesChart / MarketPane)+ RightRail tablist。**序列**執行。

## Known Risks
- jsdom 不實作 radio 方向鍵導航 → SC-1 只能鎖 tabIndex 分佈,方向鍵行為靠瀏覽器原生(APG 保證)。
- `fireEvent.click(label)` 在 jsdom 會轉發到 input 並觸發 change(React onChange)—— 若個別測試用 `getByText` 抓到的是 label,仍可用。


---
## Spec review round 1 amendments(2026-08-21,`change-spec-review-round-1.json`,17 條全 accepted)

以下條款**覆寫**上文同名拍板 / SC(以本節為準):

### D1' RadioPills 結構(R3 / R7 / R16 / R12)
- 容器 `<div role="radiogroup" aria-label className={呼叫端原容器 class 逐字}>`(**不用 fieldset**,不新增層)。
- 每項 = **`<label>` 包 `<input type="radio" className="sr-only" />` + 文字**;label 帶原 button 的全部 class,另加
  `has-focus-visible:ring-1 has-focus-visible:ring-inset has-focus-visible:ring-accent`(ring-inset 讓 FuturesPage `overflow-hidden` 容器不裁;
  `has-` 只看自己的子孫 → 不會整排亮)。DOM 每項一個 label ↔ 原每項一個 button,版面零變。
- item shape `{ value, label, disabled?, title? }`;`pillClass(item, checked)` 回 class(disabled 由呼叫端在 pillClass 內判,等同原三態);
  `title` 掛 **label**;disabled 時 input disabled + label `aria-disabled="true"` + `cursor-not-allowed`。
- `name = useId()`;`id = \`${uid}-${value}\``;input `onKeyDown`:`Enter` → `preventDefault()`(在 `<form>` 內阻止 implicit submit;radio 的 Enter 本無原生動作)。
- 點已 checked 的項不發 change(R15a):逐處確認 GroupGridView 333-336 / StockChart selectMode 的重複 persist 是冪等寫入,路徑消失無影響。
  方向鍵 auto-select 連續觸發 FuturesPage 換訂閱 / MarketPane 重抓(R15b):**接受**(與連點滑鼠等價,既有 dedup 承接)。

### SC-1'(R1)
jsdom 鎖三件:(a) `getAllByRole("radio")` 數 = 選項數且恰一顆 `.checked`;(b) 同組 `name` 全同且與他組不同;
(c) `fireEvent.click(radio)` 觸發 onChange 一次、點已 checked 者不觸發;(d) 焦點在 radio 按 Enter 不送出外層 form(OrderPanel:submit spy 不被呼叫)。
方向鍵 / roving 為瀏覽器原生,**不在 jsdom 鎖**,靠 SC-5 真環境。

### D2' 範圍修正(R8 / R13 / R4)
- MarketPane 實為兩列:標的列(加權 / 櫃買 / 台指期 + isFut 時的 大台 / 小台 / 微台)與週期列(MARKET_MODES)+ **重疊 toggle**(保留 aria-pressed,不進 RadioPills,留在週期列 DOM 位置)。
  標的列拆成兩個 radiogroup:`標的`(TWSE / OTC / FUT)與 `期貨商品`(僅 isFut 時 render);`[auto-default | reason: 兩群語意不同,各自恰一 checked 成立]`。
- RiverPanel 並排 / 重疊(無 aria-pressed 的單選)→ **Out of scope,記 next-time**。
- **App.tsx:230-253 主分頁 tablist 納入**(包 B):panel 是 `hidden` div → 補 `role=tabpanel` / `id` / `aria-labelledby`;tab 補 `id` / `aria-controls` / roving tabindex / 方向鍵(manual activation 同 D3')。

### D3' tablist(R2 / R10 / R11)
- **manual activation**:←/→/Home/End 只移 focus(roving tabindex),Enter / Space 才 `selectTab`(RightRail 切 tab 會 unmount 閃電梯 = 解除武裝,不可被方向鍵掃過觸發)。
- RightRail panel:flash 分支包 `<div role="tabpanel" id aria-labelledby className="flex min-h-0 flex-1 flex-col">`;委託 / 部位把 role/id/aria-labelledby **掛在既有 `min-h-0 flex-1 overflow-y-auto` 那層**,不新增節點。
- SC-2':選中 tab 的 `aria-controls` 指向存在的 tabpanel 且回指;未選中 tab 的 `aria-controls` 為命名規則值(dangling,D-13 條件 render 的既定代價,spec 明記);
  ArrowRight 後 `activeElement` = 下一顆 tab 且 `aria-selected` **未變**;Enter 才切換。App.tsx 三個 panel 皆 mount(hidden),無 dangling。

### D4' 零態(R6 / R14)
該紅:`WatchlistSidebar.test.tsx:1183 / 1187(案名「零 = ink-dim」改「零 = ink-muted」)/ 1201`;不該紅:`1040`(參考價 dim)、`1280`(倉位 chip)。
查法:`getByText(fmtPct(0) 字面值)` 取零漲跌 span;GroupGridView 用 `group-quote-{code}`;加反向 lock:參考價 / 無資料仍 `text-ink-dim`。

### D5' 側欄 row(R9)
`wl-row-*` div **不加 role**;row 內容區改為 `<button type="button" data-testid="wl-select-{code}" aria-label="選取 {code} {name}" className="flex min-w-0 flex-1 items-center gap-1.5 text-left">`
包住代號 / 名稱 / 報價(握把、加入群組鈕、移除鈕留在 row 層,與 button 並排 → 無 nested-interactive);`onClick={() => onSelect(code)}` 從 div **移到 button**
(div 不再有 onClick → doctor no-static-element-interactions 解除;row 空白處不再可點,`[auto-default | reason: button flex-1 覆蓋整列內容,空白僅 gap]`)。
既有測試 `fireEvent.click(getByTestId("wl-row-…"))` 選股 = **該紅** → 改點 `wl-select-…`(拖曳 / 群組 / 移除測試不該紅)。
SC-4':`wl-select-2330` 是 `<button>`、Enter/Space 觸發 onSelect 一次(原生);子鈕(加入群組 / 移除)Enter 不觸發 onSelect。

### SC-5'(R17)
1600×900 + 1536×864 各一組(個股頁 / 台股綜合 / 右欄三 tab),前後對照;Chrome 滑鼠點 radio 不觸發 :focus-visible(heuristic 僅鍵盤),不另拍。

### 🔴 該紅清單擴充(R5)
任何以 `getByRole("button", { name })` 定位 / 點擊 pill、或 `.parentElement` 結構斷言者:App.test.tsx(163-165 / 395 / 415-417 / 426 / 457 / 518-519 / 649)、
StockPage.test.tsx(670-751 段)、StockChart.futconverge.test.tsx(93 / 115)、RightRail.test.tsx(193 / 260 / 494 / 570 交易別段)、IndexPage.test.tsx(146-181)、
MarketPane.test.tsx(130 `btn()` helper、164 parentElement)、FuturesChart.test.tsx(173)、StockChart.test.tsx(361)+ current-state §1 各檔 aria-pressed 單選斷言。
改法統一:`getByRole("radio", { name })` + `.checked`;`fireEvent.click(radio)`。toggle / 卡片 / 武裝 / 重疊鈕斷言不該紅。

### 白名單補
- W8 StockChart / OrderPanel 的 `title` 文案與觸發條件不變(掛 label)。
- W9 OrderPanel 焦點在 pill 按 Enter 不進 handleOpen(新鎖)。
