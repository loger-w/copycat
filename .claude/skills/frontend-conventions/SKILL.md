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

## WebSocket hook(2026-08-20 mod/ws-app-heartbeat 沉澱)

- **新 WS hook 一律走 `lib/ws-reconnect.ts::connectWithRetry(url, {onConnecting,onOpen,onMessage,onClose}, opts)`**,
  不自寫 `new WebSocket + onclose 重連` 骨架:helper 統一承載 backoff 三分支(存活 ≥5 s 歸零 / 短命 cap 5 s /
  從未 open cap 30 s)、靜默 watchdog(收到首則 `{type:"ping"}` 武裝、sticky per-URL、30 s + 5 s tick、
  凍結防誤判)、ping 過濾(hook 的 onMessage 永遠看不到 ping)、onerror 關自身、close() 卸 handler。
  後端契約 = `copycat/server/ws.py::WS_HEARTBEAT_SECS`(CLAUDE.md §4)。測試用 `resetWsPingMemory()` 清 sticky。
  Trigger:新增 / 改任何 WS hook;想調 WS 重連節奏。

# 前端版面 / 響應式慣例

## 字級縮放(2026-07-03 responsive 沉澱)

- **字級一律 rem(root 恆 16px —— copycat 前端沒有 neigui 那組 ≥1920 112.5% / ≥2560 125% 的 root font-size media query,2026-08-21 三檔 headless 實測;本條舊文是 neigui 來源,別拿它推 1920/2560 的期望值)**:新 code 禁用 `text-[Npx]` px-literal(不吃縮放),SVG 內 fontSize 一律 rem 字串(viewBox 1:1 直接生效);SVG 大標籤用 `chip-theme.ts::svgLabelFont(width)` / `svgLegendFont(width)`(<500px 容器自動降級)。幾何驅動的動態字級(chip-price-bar rowH 那顆)保留 px。Trigger:新增任何含文字的元件 / SVG renderer。
- **Container query 門檻若邏輯上是「px 版面塞不塞得下」,用 px 任意值不用 rem 級距**:曾用 `@md`(28rem),2560 螢幕 root 放大後門檻變 560px > 面板寬 420px,桌面反而藏欄。改 `@[400px]:`。(neigui 教訓;copycat root 恆 16px 時 rem = px,取捨改看「門檻跟誰走」—— 面板寬固定 px 用 px、內容是 rem 字級用 rem,見下方 `@max-[…]` 條。)Trigger:寫任何 container query 減欄 / 降級。
- **觸控目標用 Tailwind `pointer-coarse:` variant(4.1+ 內建)加 min-h-11 / py 放大**,桌面視覺零影響;K 線 crosshair 這類 hover 互動在觸控上靠 tap 的 synthetic mousemove 免改即可用(overlay 是 onMouseMove + onClick 才成立,改 pointer event + pointerType 過濾就會破)。Trigger:新增可互動元件 / 改 chart overlay 事件模型。

## JS 響應式分支

- **jsdom 沒有 `window.matchMedia`(是 undefined,不是 matches:false)**:`hooks/useMediaQuery.ts` 已 feature-detect 回 false;判斷方向一律 `(max-width: 1023px)` 判 mobile、桌面為預設分支,vitest 下元件自動走桌面分支。雙分支共用的 JSX 抽變數不複製。Trigger:元件需要 JS 換容器(非純 CSS 降級)時。

## Layout / 量測

- **App 下的 mode page root 用 `flex-1 min-h-0`,不用 `h-full`**:App root 是 `flex flex-col`,flex item 的 `h-full` = 100% 容器高,不是「扣掉 nav 的剩餘空間」→ 頁面下溢 nav 高度被 `overflow-hidden` 靜默裁切。Trigger:加新 mode 頁時。
- **`useContainerSize` 的 ref 必掛「恆存 wrapper」**(loading / unavailable / data 三態都 mount 的元素):hook null-ref 時 early-return 且永不重跑,ref 若只掛 data 分支,冷載入會永遠 0×0 空白。regression lock 寫法見 skill `frontend-testing`。Trigger:元件用 useContainerSize 且有多態渲染時。
- **延遲 mount 的容器(bottom sheet / modal)內用 useContainerSize,ref + hook 必須宣告在「隨容器 mount 的元件」內部**(掛 parent 的 ref 會踩 null-ref 永不重跑陷阱)。ChipBubbleView 的 DetailPanel 是樣板。Trigger:sheet / dialog 內放需量測的 SVG 圖表。

## Grid 列軌高度(2026-08-14 group-grid 矩陣沉澱)

- **Tailwind `grid-rows-N` = `repeat(N,minmax(0,1fr))`,列軌可被壓到低於內容高**:item
  (overflow visible)溢軌會與下一列**重疊**,不是乾淨捲動。要「均分但有底線」用靜態任意值
  `[grid-template-rows:repeat(N,minmax(8rem,1fr))]`(仍是字面值,JIT 掃得到),壓到下限
  改走外層 `overflow-y-auto` 真捲軸。Trigger:寫任何固定列數的均分 grid。
- **grid 容器有確定高度(flex-1 / h-*)且列軌是 auto 時,`align-content` 預設
  (normal→stretch)會把 auto 軌等量撐高填滿容器**:「列高=內容高+超出才捲」的預期靜默
  失效(free space 被分掉、不出捲軸)。修法 = 容器加 `content-start`;對 1fr 軌是 no-op
  (free space 已被軌道吃光),可放 base class。jsdom 驗不到,只能鎖 class 字串 + 截圖層。
  Trigger:給 grid 容器加 flex-1 / 確定高度、或 grid 同時有「固定列軌」與「auto 列軌」兩態。

## 一頁式版面:可縮鏈 / 地板 / container query 目標(2026-08-16 overview-onepage 沉澱)

- **grid 單欄態(auto 列 + 容器有確定高)會把自由空間「等分」給 min-h-0 的項目,列高與內容
  無關**(CSS Grid §12.6 Maximize Tracks):兩列各拿一半高,內容多的那列溢出蓋到下一列,而 grid
  的 `scrollHeight == clientHeight`(溢出在 box 內)→ `overflow-y-auto` 逃生口永不啟動。
  單欄態要「內容決定高、整頁可捲」一律改 **flex-col**(`flex flex-col … @[Npx]:grid`),
  兩欄態才用 grid。Trigger:同一容器要在窄 / 寬兩態切 grid 欄數且窄態要可捲。
- **可縮鏈(min-h-0 一路到底)必須配「顯式地板」,不能靠內容當地板**:量測型圖表
  (useContainerSize → viewBox 高)的內容高就是「當前高」,拿它當 min-content 只會鎖死不能縮
  (回饋迴圈)。地板寫成明確 `min-h-*`(雙圖 grid `min-h-80` / figure `min-h-48`),地板以下
  由最外層 `overflow-y-auto` 接手;地板值 = 固定 chrome + 週期列折行上限 + svg 地板 96。
  Trigger:任何 `flex-1 min-h-0` 內放量測型 svg 的版面。
- **container query 變體量的是最近的 `@container` 祖先,不是頁面 root**:左欄自身若也是
  `@container`(為了雙圖斷點),掛在 pane 上的 `@[1050px]:min-h-0` 量到的是左欄寬(兩欄態
  ≈ 630–930px)永不成立 → 語意「單欄 / 兩欄」的變體只能掛在以 root 為最近容器的元素上
  (左欄 / 右欄框),pane 層要無條件 `min-h-0`。Trigger:巢狀 `@container` 下寫任何 `@[…]:` 變體。
- **`border-collapse` 表的 sticky th,`border-b` 不隨 sticky 黏**(邊框歸表格 border grid 繪製):
  分隔線改 `shadow-[inset_0_-1px_0_var(--color-line)]` 由 cell 自繪。Trigger:內捲表格加 sticky 表頭。
- **svg 內 rem 字級隨 viewBox 縮放**:pane 變窄(svg 渲染寬 ÷ viewBox 寬 < 0.5)後 0.625rem
  只剩 ~5px;要鎖渲染 px 得把 `unitScale = vbW / svgW` 乘進 fontSize(`lib/pane-frame.ts::
  paneUnitScale` + `svgFontRem`)。**補償只補得了字,補不了 viewBox 單位的排版常數**(hover 標籤框 /
  X 軸標籤帶 / 極值標記 offset)—— 分時態(08-17)與 K 線態(08-21,`paneCandleBox` + CandleChart
  `width` prop)都改走 **1:1 px viewBox**,補償只剩 OverlayCard 一個讀者;新的圖一律 1:1。
  1:1 的 chrome 常數(`CANDLE_CHROME_Y 100` / `INTRADAY_CHROME_Y 26` / inset 34)假設 root 16px,
  且**地板 96 被吃到時 svg 仍會被 flex 壓矮 → 縮放比 < 1**(1536×864 實測 0.84),是既知邊界。
  Trigger:把固定 viewBox 圖放進會變窄的欄位。
- **Tailwind v4 `@max-[…]:` 容器變體可用**(2026-08-21 首用;編成 `@container not (min-width:…)`,
  build CSS 可 grep 驗證)。語意是「窄容器降級」的 class 掛它,量的仍是最近 `@container` 祖先 ——
  右欄 / pane 本身不是 container 時要先自掛 `@container`(先 grep 子樹無 `absolute`/`fixed` 與既有
  `@[…]` 變體,D4 式核查)。門檻單位跟內容走:內容是 rem 字級就用 rem(`@max-[41rem]`),面板寬固定 px
  才用 px。twMerge 不會把 `px-2` 與 `@max-[41rem]:px-1` 當衝突。jsdom 不套 CSS,class 鎖只防漏寫,
  CSS 層靠 headless host 的 computed style(`display` / `paddingLeft`)斷言。
  Trigger:任何「容器窄於 N 就藏欄 / 縮 padding」的需求。

## 驗證截圖

- **devtools MCP 截圖 close-up 用 PIL crop 整頁截圖,不用 `body.style.zoom`**:zoom 會污染 useContainerSize 量測(ResizeObserver 以 zoom 後幾何重排,拍完 reset 也可能留下爆版 layout)。Trigger:real-env 要 panel 級 close-up 證據時。

## cn() / tailwind-merge

- **`border-accent`(全側 border-color)與 `border-x-line` / `border-b-line` 等 per-side 色在 twMerge 是同一 conflict group,後者會被靜默移除**(2026-07-18 QuoteTable ATM 列脊柱實證,vitest class 子字串斷言抓不到):同一元素要疊「全側基色 + 條件強調色」時,條件側一律用 side-specific utility(`border-b-accent`),不用全側 `border-accent`;必要時對關鍵 class 寫「合併後仍保留」的斷言(QuoteTable.test.tsx ATM 測試是樣板)。Trigger:cn() 內同元素出現兩個以上 border 色 class 時。

## real-env 游標互動驗證(devtools MCP)

- **程序派發 `new MouseEvent("mouseleave")` 不會觸發 React 的 onMouseLeave**(React 由 mouseout+relatedTarget 合成 enter/leave;jsdom/RTL 的 fireEvent.mouseLeave 可以,真瀏覽器 dispatchEvent 不行)→ 真環境驗證「移出清除」用 `mouseout` + `relatedTarget: document.body`,或 MCP hover 工具移真游標;驗到「殘留」先懷疑測試手法假陰性再懷疑 code(2026-07-18 PnlChart 實證)。另 mousemove 派發後 React re-render 是非同步,查 DOM 前要 `await setTimeout ~200ms`。Trigger:real-env 驗證任何 hover / cursor 行為時。

## 編輯期 formatter hook 陷阱(2026-08-20 signal-alert-side-effects 沉澱)

- **PostToolUse formatter 對每次 Edit 跑語意型 autofix(實證 prefer-const)**:分兩次 Edit
  「先加 `let x = false` 宣告、下一次才補 `x = true` 賦值」,第一次 Edit 後 x 尚未被再賦值
  → 被自動改成 `const`,補上的賦值變 runtime TypeError;落在 try/catch 內就**靜默吞掉**
  (症狀 = 該路徑整段不執行、零錯誤訊號),tsc 也要等下次跑才報。module 級 `let` 旗標的
  宣告與首個賦值一律**同一次 Edit 帶齊**;hook 提示「檔案被 formatter 改過」時,重讀被動
  區塊再下一步。Trigger:任何分次 Edit 引入 module 級可變旗標 / 看到 PostToolUse formatter 提示。

## TanStack Query mutation 連發

- **TQ v5 的 per-call callbacks(`mutate(vars, { onSuccess })`)只對同一 observer 的「最新一發」執行**(2026-08-11 WatchlistManagerDialog 實證,PR #39):連發時第二次 mutate 覆蓋第一發的 per-call callbacks → 第一發 onSuccess 靜默不跑;且事件 handler 以 render 閉包算 next 時,在途 PUT 未回 = stale 基底,第二發會把第一發結果還原。**連發場景一律 per-action `mutateAsync` + promise chain 串行佇列**:動作傳 `(base) => next` transform、以上一發回應為基底重算;失敗以世代計數短路已排隊動作、文案落 local state(下一發 mutateAsync 會立刻重設 observer 的 `error`,單靠它文案被洗掉);chain 尾必掛 `.catch` 收斂(任一步 throw 毒化 chain 後所有後續 `.then` 靜默跳過);基底與 prop 的同步走 useLayoutEffect + in-flight 計數守門,不在事件路徑同步(pending 歸零早於 re-render 的空窗會倒回舊值)。樣板:`WatchlistManagerDialog.tsx` commit();測試用 gated PUT(deferred resolver 逐發放行)打在途窗,樣板 `WatchlistManagerDialog.test.tsx`「連續操作」節。Trigger:同一 mutation 需支援連續操作 / 想寫 per-call callback / 測連發時序。

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

## 格式化工具只有 eslint --fix(2026-08-21 B3 沉澱)

- **專案沒裝 prettier;`npx prettier` 會臨時抓外部版(printWidth 80)把整檔重排成 +150 行的假 diff**。
  格式化一律 `npx eslint --fix <file>`(與 PostToolUse `format-on-edit.py` 同源);diff 行數異常先
  `git diff --stat -w --ignore-cr-at-eol` 看實質改動。Trigger:任何想手動格式化 / diff 行數遠大於改動量。
- **headless 截圖 fallback**:claude-in-chrome 未連線且 chrome-devtools-mcp profile 被他 session 鎖時,
  `chrome.exe --headless=new --user-data-dir=<scratch> --window-size=W,H --virtual-time-budget=4000
  --screenshot=<png> <url>` 對 vite dev 臨時 host 頁可直接出圖;量測用 host 內 `useEffect` 讀
  clientWidth/scrollWidth/getBoundingClientRect 渲染成 `<pre>` 讓截圖帶讀數(jsdom 量不到 px)。
  host 檔收尾必刪。**升級版(2026-08-21 B1)**:host 內 `__measure()` 把 computed style / rect 渲染成
  `<pre>`,用 `--dump-dom` 抓 HTML 再 regex 取 JSON 落 evidence(截圖只當人眼證據,數字走 JSON);
  query 參數 `tab=`/`stock=`/`mode=` 由 host 點擊;**同一 `--user-data-dir` 會記住上次點的 tab /
  個股(localStorage)**,換場景要帶 `tab=` 明確點回,否則量到別頁全 0。`--virtual-time-budget`
  下 fetch / WS 照常回。Trigger:同上。

