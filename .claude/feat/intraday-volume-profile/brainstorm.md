# brainstorm — 分時圖價位別成交量(題 2,volume profile)

規格來源:`.claude/feat/stock-quintet-discussion/brainstorm.md` 題 2(user 2026-08-05 拍板:
K 線不做;**bar 從左到右、長條圖形式**)→ /auto 預核准。
分流判定:**已成形方案**(條件 1 中 — UI 形式與資料源指名;條件 2 中 — 實作層決策點存在)。

## 目標

分時圖上加「價位別成交量」水平長條(自左緣價位帶向右延伸,長度 ∝ 該價位當日成交量),
一眼看出今日的支撐/壓力價位。零後端改動(當日全量 tick 已在 snapshot / WS)。

## 現況(worktree master 24a8f64 實讀)

- `frontend/src/lib/stock-accum.ts`:`fromSnapshot` 收全量 ticks 後 `slice(-200)`(:118)、
  `applyTick` 同(:152)— 全日價量對被丟棄,唯一消費者是 TickTape
- `frontend/src/lib/stock-intraday-svg.ts`:`toY`/`yDomain`/`Y_AXIS_W=36`/`plotWidth` 現成;
  overlay 樣板(域過濾 + toY)在 `overlayLines`
- `frontend/src/lib/stock-tick.ts`:`snapDown`/`tickOf`/`isMarketLevel` 現成(顯示價位可下單紀律)
- `frontend/src/hooks/useChartToggles.ts`:`{...DEFAULTS, ...saved}` — **新鍵不需 version bump**
  (舊存檔無 vp 鍵 → DEFAULTS 自然生效)
- `StockIntradayChart.tsx`:ChartStatic memo(props 純量/穩定 identity 紀律)、toggleDefs 在元件內

## 成功條件(SC)

- **SC-1** 資料層:`StockAccum` 新增價位直方圖 `vp: Map<priceMilli, {t, o, i}>`
  (t=總張、o=外盤、i=內盤;bucket = `snapDown` 合法檔位;`p <= 0` 防禦跳過)。
  `fromSnapshot` 對**全量** ticks fold(在 slice(-200) 之前的來源上);`applyTick` 增量;
  seq 跳號 refetch 後與 fromSnapshot 同源重建。**TAPE_MAX=200 不放寬**。
  驗證:`stock-accum.test.ts` — fixture >200 ticks 時 vp 總量 = 全量和且 ticks 仍 ≤200(anytime)
- **SC-2** 幾何層:新 `lib/volume-profile.ts` 純函式 `buildVpBars(vp, geom, width)` —
  域外價位過濾、bar 高 = 該檔位到下一檔位的 y 距(min 1px)、bar 寬 = total/maxTotal ×
  最大寬(繪圖區寬 × 0.22)、輸出含 priceMilli/total 供 hover/測試。
  驗證:`volume-profile.test.ts` 單元測試(域過濾/歸一/退化域)(anytime)
- **SC-3** 畫面(可指認):分時圖繪圖區內、**自左緣價位帶(x=Y_AXIS_W)向右**延伸的
  水平半透明長條(單色,z-order 在紅綠填色與走勢線**之下**,不遮線);圖表 toggle 列
  新增「量分佈」鈕,預設**開**,關掉後長條消失。
  驗證:component test(toggle 開關 → vp rect 出現/消失)+ AI 截圖對照 + user 過目
  (驗證窗口:截圖 anytime — 盤後 snapshot 也有全日 tick;實看建議盤後)
- **SC-4** 零退化:`npm test` 全綠 + `npx tsc -b` + `npx eslint src`(frontend/)。
  驗證:gate 指令輸出(anytime)

## Edge cases

1. 鎖漲跌停日市價佇列:tick 的 `p` 是成交價恆 >0,但防禦上 `p <= 0`(isMarketLevel 同規)
   跳過不入 bucket
2. 域切換(漲跌停域 ↔ autofit 域):bars 每次 render 依當下 geometry 過濾,域外 bucket 不畫
3. 退化域(upper===lower / flat):toY 常數 → bar 高 clamp min 1px,不炸
4. 空資料(vp 空 / 全域外)→ 零 bars,不畫
5. 低價股 tick 粗:相鄰價位 snap 同 bucket → 自然合併(snapDown 冪等)
6. 跨 200 筆截斷邊界:tape 只剩尾 200,vp 仍為全日(SC-1 測試鎖)

## 決策記錄

- `[auto-default: 單色本輪、外內盤分色不做(資料模型已帶 o/i) | reason: quintet 拍板
  「分色選配預設單色」+ 鎖停日 side 判定品質已知問題;分色留 next-time,資料先備]`
- `[auto-default: bar 最大寬 = 繪圖區 22% | reason: 業界 VP 常規比例,不壓走勢可讀性;
  數值集中在 lib 常數可調]`
- `[auto-default: toggle 鍵名 vp、預設開、不 bump TOGGLES_VERSION | reason: 新鍵走
  DEFAULTS spread 自然生效,version bump 僅在改既有鍵預設時需要]`
- `[auto-default: hover 聯動(高亮所在檔位 bar)本輪不做 | reason: 非 user 要求;
  crosshair 既有 priceAtY 已提供價位資訊]`
- `[auto-default: 時間窗不過濾(全日 tick 皆入 VP) | reason: 支撐壓力語意含開收盤;
  後端已濾試撮]`

## Out of scope

- K 線圖 VP(user 拍板不做)
- 外內盤分色渲染與其 toggle(→ next-time;資料模型本輪已備)
- hover 聯動高亮、後端歷史 tick endpoint
- TAPE_MAX 放寬(明確不做)

## 規模分流

**M**(4 檔 code:stock-accum.ts / volume-profile.ts(新)/ useChartToggles.ts /
StockIntradayChart.tsx + 測試)→ Phase 1 完整走。

## 驗證窗口

全 SC anytime(盤後 snapshot 含全日 tick,截圖不需盤中);user 實看過目於盤後/盤中皆可。
