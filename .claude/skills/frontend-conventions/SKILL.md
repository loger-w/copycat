---
name: frontend-conventions
description: React / TypeScript 基本風格 + 前端版面與響應式慣例。寫或改 frontend/ 下任何元件 / hook、新增含文字的元件 / SVG renderer、寫 container query、加新 mode 頁、用 useContainerSize、改 chart overlay 事件模型前先讀。
---

> 來源:2026-07-06 自 neigui 專案複製。文中「樣板」檔案路徑(services/finmind.py、conftest.py、lib/api.ts 等)指 neigui repo(C:\side-project\neigui)的 code,本專案對應實作落地後再改寫為本地路徑。

# React / TypeScript 基本風格

> 2026-07-28 自專案 CLAUDE.md §3 整節遷移(neigui 同款瘦身),內容未改。

從 trash-cmoney §7 升級路線的「採納項」直接內建,不重蹈技術債:

- **Custom hook 統一回傳 shape**:`{ data, loading, error, refresh, ...extras }`。
- **Server state 一律走 TanStack Query**,**禁止**手寫 `useEffect + fetch + seqRef`。React 19 + TQ 是新專案 baseline,避開 trash-cmoney 累積 8 個手寫 hook 的債。
- **Stale-drop**:TQ 自帶 cancellation,不額外寫 `seqRef`。
- **Function component + hooks only**。沒有 class 元件,**沒有 `forwardRef`**(React 19 `ref` 是普通 prop)。
- **TypeScript**:`strict: true` + **`noUncheckedIndexedAccess: true`**(從第一天就開)。
- **Tailwind 用 semantic token**:`text-ink` / `text-ink-muted` / `text-ink-dim` / `text-accent` / `border-line` / `bg-bg` / `bg-bg-deep`。token 在 `src/index.css` 的 `@theme`。**Bull = 紅 / Bear = 綠**(台股慣例,不套美股 green-up)。
- **重元件 lazy**:跨 tab 切換的大元件走 `React.lazy()` + `<Suspense fallback={...}>`。
- **純渲染抽到 `lib/*-svg.tsx`**:SVG 計算函式無 React 依賴,獨立單元測試。元件只負責掛 DOM。
- **`cn(...classes)`** 走 `lib/utils.ts`(`clsx` + `tailwind-merge`),不直接拼字串。
- **UI 文字一律繁體中文**(`重新整理` / `載入中` / `無交易日` …)。錯誤訊息、aria-label 也用繁中。
- **Vitest 測試 colocated** `*.test.tsx` / `*.test.ts`,跑 RTL 的檔要在頂端寫 `/** @vitest-environment jsdom */` pragma。`afterEach(cleanup)`。
- **Path alias** `@/` → `src/`(`vite.config.ts` + `tsconfig.app.json`)。**新 code 一律用 `@/`**,不用相對 import。
- **Date 用 `YYYY-MM-DD` 字串** 在 API + state 流動;`new Date()` 只在邊界。
- **`hidden` attribute > 條件 render**:tab 切換用 `<div hidden={tab !== "x"}>` 保留 DOM。
- **`eslint-plugin-react-you-might-not-need-an-effect`** 開起來,`useEffect` 是 anti-pattern 直接 lint 抓。

# 前端版面 / 響應式慣例

## 字級縮放(2026-07-03 responsive 沉澱)

- **全站字級縮放機制 = root font-size media query(≥1920 112.5% / ≥2560 125%)+ 全 rem**:新 code 禁用 `text-[Npx]` px-literal(不吃縮放),SVG 內 fontSize 一律 rem 字串(viewBox 1:1 直接生效);SVG 大標籤用 `chip-theme.ts::svgLabelFont(width)` / `svgLegendFont(width)`(<500px 容器自動降級)。幾何驅動的動態字級(chip-price-bar rowH 那顆)保留 px。Trigger:新增任何含文字的元件 / SVG renderer。
- **Container query 門檻若邏輯上是「px 版面塞不塞得下」,用 px 任意值不用 rem 級距**:曾用 `@md`(28rem),2560 螢幕 root 放大後門檻變 560px > 面板寬 420px,桌面反而藏欄。改 `@[400px]:`。Trigger:寫任何 container query 減欄 / 降級。
- **觸控目標用 Tailwind `pointer-coarse:` variant(4.1+ 內建)加 min-h-11 / py 放大**,桌面視覺零影響;K 線 crosshair 這類 hover 互動在觸控上靠 tap 的 synthetic mousemove 免改即可用(overlay 是 onMouseMove + onClick 才成立,改 pointer event + pointerType 過濾就會破)。Trigger:新增可互動元件 / 改 chart overlay 事件模型。

## JS 響應式分支

- **jsdom 沒有 `window.matchMedia`(是 undefined,不是 matches:false)**:`hooks/useMediaQuery.ts` 已 feature-detect 回 false;判斷方向一律 `(max-width: 1023px)` 判 mobile、桌面為預設分支,vitest 下元件自動走桌面分支。雙分支共用的 JSX 抽變數不複製。Trigger:元件需要 JS 換容器(非純 CSS 降級)時。

## Layout / 量測

- **App 下的 mode page root 用 `flex-1 min-h-0`,不用 `h-full`**:App root 是 `flex flex-col`,flex item 的 `h-full` = 100% 容器高,不是「扣掉 nav 的剩餘空間」→ 頁面下溢 nav 高度被 `overflow-hidden` 靜默裁切。Trigger:加新 mode 頁時。
- **`useContainerSize` 的 ref 必掛「恆存 wrapper」**(loading / unavailable / data 三態都 mount 的元素):hook null-ref 時 early-return 且永不重跑,ref 若只掛 data 分支,冷載入會永遠 0×0 空白。regression lock 寫法見 skill `frontend-testing`。Trigger:元件用 useContainerSize 且有多態渲染時。
- **延遲 mount 的容器(bottom sheet / modal)內用 useContainerSize,ref + hook 必須宣告在「隨容器 mount 的元件」內部**(掛 parent 的 ref 會踩 null-ref 永不重跑陷阱)。ChipBubbleView 的 DetailPanel 是樣板。Trigger:sheet / dialog 內放需量測的 SVG 圖表。

## 驗證截圖

- **devtools MCP 截圖 close-up 用 PIL crop 整頁截圖,不用 `body.style.zoom`**:zoom 會污染 useContainerSize 量測(ResizeObserver 以 zoom 後幾何重排,拍完 reset 也可能留下爆版 layout)。Trigger:real-env 要 panel 級 close-up 證據時。

## cn() / tailwind-merge

- **`border-accent`(全側 border-color)與 `border-x-line` / `border-b-line` 等 per-side 色在 twMerge 是同一 conflict group,後者會被靜默移除**(2026-07-18 QuoteTable ATM 列脊柱實證,vitest class 子字串斷言抓不到):同一元素要疊「全側基色 + 條件強調色」時,條件側一律用 side-specific utility(`border-b-accent`),不用全側 `border-accent`;必要時對關鍵 class 寫「合併後仍保留」的斷言(QuoteTable.test.tsx ATM 測試是樣板)。Trigger:cn() 內同元素出現兩個以上 border 色 class 時。

## real-env 游標互動驗證(devtools MCP)

- **程序派發 `new MouseEvent("mouseleave")` 不會觸發 React 的 onMouseLeave**(React 由 mouseout+relatedTarget 合成 enter/leave;jsdom/RTL 的 fireEvent.mouseLeave 可以,真瀏覽器 dispatchEvent 不行)→ 真環境驗證「移出清除」用 `mouseout` + `relatedTarget: document.body`,或 MCP hover 工具移真游標;驗到「殘留」先懷疑測試手法假陰性再懷疑 code(2026-07-18 PnlChart 實證)。另 mousemove 派發後 React re-render 是非同步,查 DOM 前要 `await setTimeout ~200ms`。Trigger:real-env 驗證任何 hover / cursor 行為時。


---

# §8 遷移附錄(2026-08-10,內容未改)

- **Tailwind 的 `display` utility 會蓋掉 UA stylesheet 的 `dialog:not([open]){display:none}`**
  (2026-07-31 真踩到):`<dialog>` className 一旦帶 `flex`,關閉的 dialog 照樣佔版面(空盒子壓
  在圖表上)。828 個測試全綠:jsdom 的 HTMLDialogElement 是空 class、測試環境不載 Tailwind CSS。
  修法 = display 跟著 `open` 切,**用 prop 選 class 不用 `open:` variant**(variant 的 class 字串
  恆定,測試只能斷言「有這個 class」,回歸抓不到);必須補 `onClose` 把 prop 拉回同步(原生
  cancel/close 擋不掉,`stopPropagation` 只擋 React 合成事件)。(Trigger:`<dialog>` 樣式 / 靠 UA
  stylesheet 預設行為的元素)
- **SVG `fill` 是 presentation attribute,優先權低於任何 CSS 宣告**:用 `<pattern>` 填色就不能
  同時留 `fill-*` class 當「保險」— Tailwind 的 `fill:` 會蓋掉 pattern → 退回實心色零錯誤訊號。
  `<pattern>` 必須 `patternUnits="userSpaceOnUse"`(`objectBoundingBox` 讓 tile 被每個 rect 各自
  拉伸,270 根柱子 270 種紋理密度);窄元素(柱寬 ~2.5px)要在 tile 內先鋪底色再疊線條,否則
  整根可能落在空白帶被畫成透明。(2026-08-06,Trigger:SVG pattern / gradient 填色)
