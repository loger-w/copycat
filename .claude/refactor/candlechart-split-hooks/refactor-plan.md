# refactor/candlechart-split-hooks — CandleChart 抽 viewport / hover 兩支 hook

## Why?(gate)

react-doctor triage(`docs/research/2026-08-11-react-doctor-triage.md` §二)no-giant-component:
CandleChart.tsx 766 行、主體函式 313 行,混雜 viewport 縮放/平移、hover 事件層與渲染。
未來 K 線迭代(候選:拖曳 rAF 節流、Home/雙擊捷徑,見 docs/next-time.md 2026-07-29 節)
都落在這檔,memo identity 契約(ChartStatic / EMPTY_LINE / EMPTY_HLINES / WindowMark useMemo)
密度高易踩。**為什麼是現在**:doctor triage 剛裁決拆分方案(user 已核的 needs-human 排期項,
本輪 /auto 指令即該裁決的執行),趁 K 線功能無並行改動時做,行為零變風險最低。

分流判定:規格來自 user 撰寫的 /auto 指令 + triage 文件裁決(拆 useCandleViewport /
useCandleHover、JSX 幾乎不動、不打穿 memo)→ 預核准,無方向性抉擇。

[auto-default: spec review 0 輪 | reason: S 級 — 改動限單一元件內部結構 + 2 支新 hook
(唯一 caller 為 CandleChart),無對外契約 / 安全面;行為由 45 條既有元件測試鎖定]

## 不能破壞的既有行為白名單

1. 滾輪縮放:deltaY>0 增根、<0 減根;下限 20、上限 min(total, 700);錨點守恆
   (原地縮放後十字線仍在游標 ±1 slot — C3 測試)。
2. 拖曳平移:左鍵起拖、絕對位移(拖曳起點基準,端點 clamp 不漂移)、拖出圖外仍跟手
   (window listeners)、mouseup 停止;拖曳中十字線清除。
3. 資料延伸(R10):貼右緣 → 跟進;已平移 → 不被拉回。render 期間調整(非 effect)。
4. hover:座標存 viewBox 座標非 index;亞像素抖動 bail-out(同 rounded 值回 prev);
   mouseleave 清除;資訊列無 hover 顯示最後一根。
5. memo 結構:ChartStatic / XAxisLabels 元件與 props 形狀不動;EMPTY_LINE / EMPTY_HLINES /
   highMark/lowMark useMemo 的 identity 紀律不動。
6. wheel 為原生 listener + passive:false(preventDefault 擋頁面捲動);mouse 事件模型
   不改 pointer(觸控 tap synthetic mousemove 慣例,frontend-conventions)。
7. 個股 / 大盤 / 期貨三個 caller(StockChart / MarketChart 系 / FuturesChart 系)零改動
   —— 本輪不動 CandleChart 的 Props 介面。

## 測試覆蓋盤點(inventory)

`CandleChart.test.tsx` 45 tests,已覆蓋:縮放(SC-6.3/6.4 上下限)、平移(左端 clamp)、
hover 準度(C3 錨點守恆)、漲跌% 完整序列取 prev(C4)、延伸(R10 兩態)、十字線/價標/
時標、高低標、hlines、量副圖、高度 prop 幾何重算。

**缺口(本輪抽出的 code 直接經過、現無測試)→ 先補 characterization(🟢 獨立 commit)**:

- C-a 拖曳中 mousemove 清 hover(`setHover(null)` in drag move)— 十字線消失。
- C-b 非左鍵(button≠0)mousedown 不啟動平移。
- C-c mouseup 後窗口不再跟 mousemove 平移(listener 已卸)。

三條皆為既有行為(綠上車),各做一次 Edit 成對 mutation 抽驗(改壞 → 紅 → 還原)確認
非 vacuous。

不補的:wheel passive:false 的頁捲動抑制(jsdom 不可觀察)、hover 亞像素 bail-out
(render 次數在元件外不可觀察,屬 perf 非行為)。

## 步驟(每步單獨綠、單獨 commit,純 🔵)

1. **🟢 characterization**:C-a/C-b/C-c 進 `CandleChart.test.tsx`(元件層,重構後仍有效)。
2. **🔵 step 1 — 抽 `src/hooks/useCandleHover.ts`**:hover state + onMove(含 bail-out)+
   clearHover。簽名 `useCandleHover(dimW, dimH)` → `{ hover, onMove, clearHover }`。
   JSX 的 `onMouseLeave={() => setHover(null)}` 改 `onMouseLeave={clearHover}`(語意等價)。
   diff 預估 < 60 行。
3. **🔵 step 2 — 抽 `src/hooks/useCandleViewport.ts`**:viewport + prevTotal render 調整 +
   wheel 原生 listener effect + onDragStart(含 window listeners)。簽名
   `useCandleViewport({ total, initBars, svgRef, dimW, dimH, onDragMove })` →
   `{ viewport, onDragStart }`;`onDragMove` = CandleChart 傳入的 clearHover(拖曳清十字線,
   跨 hook 的唯一接點)。ZOOM_STEP 常數隨遷。diff 預估 < 120 行(含註解搬遷)。

[auto-default: hook 落點 `src/hooks/`(非 colocate 在 components/stock/)| reason: 專案
52 支 hook 全在 src/hooks/,零例外]
[auto-default: 不另寫 hook 層單元測試 | reason: 純 🔵 行為不變,元件層 45+3 條測試即行為
合約;hook 單測屬新增覆蓋,非本輪動機,避免 scope creep]
[auto-default: onDragMove 以 callback 接 clearHover,不把 hover 塞進 viewport hook |
reason: 兩 hook 職責正交(doctor 裁決本來就是兩支);callback 為 plain function 與現行
onDragStart 同為每 render 新 identity,無 memo 影響]

## Blast radius

- CandleChart 的 caller:grep `CandleChart` 全 frontend/src(含動態用法)— Props 不變,
  預期零波及。
- 新 hook 名稱 grep 撞名檢查。
- Gate:npm test 全量 + npx tsc -b + npx eslint src + react-doctor --scope changed 零新增
  (no-giant-component 該條消失或行數下降註記)。zero .py 觸及 → pytest/ruff/pyright/validate
  沿 baseline(收尾前跑 pytest -q 一次確認 tree 未被波及)。
