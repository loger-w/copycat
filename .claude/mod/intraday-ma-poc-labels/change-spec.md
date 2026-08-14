# Change spec:分時圖均線價格標籤 + POC(mod/intraday-ma-poc-labels)

規模:**M**(3 個 source 檔 + 3 個測試檔;無對外 API、無 migration)。
分流判定:**已成形方案**(user 指名落點檔案 + 做法 + 渲染機制約束)→ grilling 姿態,
自主模式逐題 `[auto-default]`。

## 拍板(全部 [auto-default],收尾回報逐條列出)

- **D1 MA 價位標籤位置**:[auto-default: 名稱標籤照舊留在右緣帶,價位數值標籤畫在
  **繪圖區內側右緣**(`x = w − R_AXIS_W − 2`、`textAnchor="end"`、`stroke-surface` halo)
  | reason: R_AXIS_W=40 帶裝不下「MA20 1005.0」(≈49px);FuturesChart 右緣 overlay 標籤
  是同樣式既有前例;名稱保留 = 不推翻 round3「MA 維持名稱」的既有拍板]
- **D2 VWAP 標籤**:[auto-default: **就地標示在 vwapLine 末點右側**(`x = 末點x + 4`,
  clamp 進繪圖區右界;`fill-ink` 白跟線色 + halo),文字 = `fmt(末點 vwap)`(與說明列
  VWAP 同一口徑同一來源)| reason: VWAP 不是橫貫全寬的水平線,盤中末點在畫面中段,
  右緣釘標籤會與線脫節 640px(review F1);就地標示與 last-dot / 極值標記同一套語彙]
  [amendment 2026-08-14: review F1 —— 原「右緣 pinned」改為就地標示]
  [amendment 2026-08-14: code review A-1 —— 標籤**文字**改吃 `accum.vwap`(後端逐筆,
  與說明列同源同值;經 scalar prop `vwapMilli` 傳入 ChartStatic,memo 安全),位置仍用
  vwapLine 末點 x/y(分鐘粒度誤差內);`accum.vwap` null → 不畫標籤(與說明列「-」一致)。
  原實作吃 vwapLine 末點值造成同圖兩個矛盾 VWAP 數字(2381.67 vs 2380)]
- **D3 避讓語意**:[auto-default: MA5/MA20 兩顆右緣標籤之間 1D 垂直避讓(中心距 ≥
  EDGE_LABEL_H)+ clamp 進繪圖區;**極值文字(day-high/low label)落在右緣區
  (mark.x > w − R_AXIS_W − 40)時作為固定 obstacle 一併避讓**(review F2);與左緣
  y 軸刻度天然無重疊(標籤在右緣)、與右緣帶內既有標籤無水平重疊(x 範圍不相交)。
  VWAP 標籤(就地)與 last-dot(3px 圓)不入避讓集 —— halo 承擔,可接受的殘餘重疊
  記 Known Risks | reason: user 的「避開 y 軸刻度重疊」由位置選擇 + 避讓滿足;
  既有 CDP 帶內標籤的碰撞是既有狀態,不在本輪(out of scope)]
  [amendment 2026-08-14: review F2 —— 避讓對象補極值文字 obstacle]
  [amendment 2026-08-14: code review A-2/B-1/B-3 —— obstacle 判準由「mark.x > w −
  R_AXIS_W − 40」改為顯式水平相交(clampLabelX 後的 x + EDGE_LABEL_W/2 > MA 標籤左界);
  單位一律正規化為視覺中心(文字 baseline − 3);命中的極值給文字**與圓心**兩個 obstacle]
- **D4 POC 定義**:[auto-default: 域內 `total` 最大的價位;tie → 取較高價位(決定性);
  全 0(盤前/全濾)→ 無 POC | reason: 域內限定與歸一分母同規;tie-break 需決定性
  否則 React 渲染不穩定]
- **D5 POC 呈現**:[auto-default: POC 長條改 `fill-accent` + 提高透明度
  (`VP_POC_FILL_OPACITY = 0.45`),價格標籤畫在**長條尖端右側**(accent 色 + halo),
  渲染另開分支不硬塞 yTicks | reason: 「邊緣價格標籤」解讀為長條邊緣 —— 就地標示
  可指認且天然避開左緣刻度與右緣帶;user 的機制約束(仿 oLines 另開分支)照辦]
  [amendment 2026-08-14: review F7 —— 落點取捨明寫:POC 恆為最寬 bar,標籤 x ≈ 198
  固定在畫面中段,且 POC y 定義上就是成交最密的價位,**任何**在該 y 的就地標籤都會
  與價線交會;halo 保可讀性、highlight 長條才是主訊號、標籤是次要輔助。SC-4 截圖
  驗收加「價線在標籤附近仍可辨識走向」目視判準;此取捨接受,不再改位]
- **D6 期貨態範圍**:[auto-default: VWAP 標籤兩態都出;POC 隨 VP 既有可用性 = 僅現貨態
  | reason: user 說「VWAP/POC 兩態都做」,但 VP 在期貨態整組關(`foldVp` 折入窗是現貨窗
  09:00–13:30,期貨態畫 = 08:45–08:59 與 13:31–13:45 整段缺席的假資料,元件註解明文),
  且同句「期貨態 MA/CDP 關閉的既有語意不動」;強開 VP 需參數化 foldVp = 另一輪 scope。
  **此條回報時顯著標出請 user 確認**]
- **D7 標籤圖層**:[auto-default: 兩組新標籤畫在 ChartStatic 尾端(主價線與極值標記之後)
  | reason: svg 無 z-index;畫在價線前會被 1.6px 主線壓過,標籤的作用就是被讀到 ——
  與極值標記 round6「必須畫在主價線之後」同一教訓]

## 成功條件(SC)

- **SC-1 MA 即時價位標籤**:MA toggle 開且域內時,MA5(黃 `fill-ma5`)/ MA20(紫
  `fill-ma20`)各在繪圖區右緣內側出現價位數值(**`fmtTickPrice(priceMilli)`,與 CDP
  同口徑 —— round3 B4「日線衍生值印可下單價位」既有結論不推翻;無 `*` 後綴 + 色
  區分 CDP**,review F3),右緣帶內名稱 "MA5"/"MA20" 照舊。畫面可指認:右緣帶左側、
  貼著對應虛線的黃/紫數字,帶底色描邊。
  驗證:vitest(`edge-price-ma5`/`edge-price-ma20` testid 文字與 class)+ 截圖對照。
- **SC-2 VWAP 即時標籤**:均價 toggle 開且有成交時,vwapLine **末點右側**出現白色
  (`fill-ink`)VWAP 數值(`fmt`,與說明列 VWAP 同口徑;VWAP 是統計量非可掛單價,
  不 snap tick,review F3);關 toggle → `edge-price-vwap` 不存在;無成交 → 整圖
  「尚無成交」分支。**期貨態(stkfut)也出**。
  驗證:vitest(`edge-price-vwap` 存在/不存在 + 文字;stkfut fixture 斷言存在)+ 截圖。
- **SC-3 標籤避讓**:MA5/MA20 標籤中心距 ≥ `EDGE_LABEL_H`(10,**指標籤中心距**,
  字高 ≈9px + 1 呼吸;文字以 `dy="0.35em"` 置中於 y),對 obstacle(右緣區極值文字)
  同樣保距;全部 clamp 進 `[top, bottom]`(由呼叫端傳 `MARK_LABEL_TOP` 與
  `plotBottom − 5`,**與極值標記同一組界,不另寫一份數字**,review F4)。
  驗證:`edgePriceLabels` 單元測試(同 y → 間距 ≥ 10;obstacle 擠壓;近頂/近底 clamp)。
- **SC-4 POC**:VP toggle 開時,域內量最大價位的長條以 accent 色 + 0.45 透明度
  highlight,長條尖端右側出現該價位數字(accent 色);其餘 bar 樣式不變。tie 取高價、
  全 0 無 POC。畫面可指認:左緣長條群中最長那根變桃紅色、尖端有同色價位數字。
  驗證:volume-profile 單元測試(poc 判定)+ component 測試(`vp-poc-label`)+ 截圖。

## 不能破壞的既有行為白名單

1. 幾何零改動:`buildIntradayGeometry` 輸出、`R_AXIS_W`/`Y_AXIS_W` 值、`toY`/`yTicks`
   清單全不動(MiniIntradayChart 因此零影響)。
2. 右緣帶內既有標籤:CDP `價位*`、MA `"MA5"/"MA20"` 名稱,文字/位置/配色不變。
3. 期貨態語意:overlay 不打請求、VP 不畫、cdp/ma/vp 三顆反灰,全不動。
4. VP z-order(y 格線後、平盤填色/走勢線前)與非 POC bar 樣式(`fill-ink-muted` +
   `VP_FILL_OPACity 0.25`)不變;`vp-bar` testid 不變。
5. memo 紀律:ChartStatic 不新增會打穿 memo 的 props(新標籤全由既有 props `g` /
   `oLines` / `showVwap` / `vpBars` 內算)。[amendment 2026-08-14: review A-1 —— 放寬為
   「不新增**非純量**props」:`vwapMilli: number | null` 純量入 props,memo 不受影響]
6. hover 十字線 / price-tag / time-tag 行為不變。
7. `buildVpBars` 既有欄位語意(y/h/w/priceMilli/total、降冪排序)不變。
8. toggle 可用性矩陣(vwap 恆可用;cdp/ma/vp 期貨態反灰)不變。
9. [amendment 2026-08-14 review F9] 新標籤文字只含價位、**不得含 `%`**(round3 SC-1
   的既有合約:x > 740 的 text 不得含 %,StockIntradayChart.test.tsx:214-222 在鎖)。
10. [amendment 2026-08-14 review F9] 標籤 halo 一律 `stroke-surface` + `paintOrder`,
    **不得用底色 `<rect>`**(SC-5「主圖 drawnRects === 0」既有測試會紅)。
11. [amendment 2026-08-14 review F2] 極值文字與現價圈的可見性不因新標籤劣化:極值文字
    落右緣區時 MA 標籤讓位(obstacle 避讓);last-dot(3px)與 VWAP 就地標籤的殘餘
    重疊為 Known Risk(halo 承擔,見 D3)。

## Edge cases(≥3)

1. MA5 === MA20 同價 → 兩線重合(既有),兩標籤 nudge 分開仍各自可讀。
2. vwapLine 空 → 無 VWAP 標籤。[amendment 2026-08-14: review B-7 —— 原「此時整圖走
   『尚無成交』分支」理由錯誤:priceLine 不看量、vwapLine 只在累計量 > 0 才 push,
   分鐘 c>0 且 v=0(試撮窗等)時主圖照畫而 vwapLine 空,`?? null` 守住,測試補鎖]。
3. VP 全 0 → 無 POC bar、無標籤(`poc` 全 false)。
4. POC tie(兩檔同量)→ 取較高價位,輸出決定性。
5. 標籤 y 逼近繪圖區頂/底(MA 貼漲跌停)→ clamp 進 `[MARK_LABEL_TOP, plotBottom − 5]`
   (與 SC-3 同一組界,review F4)。
6. 退化域 flat(upper === lower)→ toY 常數,MA 兩標籤同 y → 避讓後仍不炸、不重疊。
7. MA 域外 → `overlayLines` 不給 → 無線無標籤(沿既有語意)。

## Out of scope

- 期貨態開 VP/POC(需 foldVp 窗參數化,見 D6)。
- 既有 CDP 帶內標籤的碰撞處理(既有狀態)。
- VP hover 互動 / 分色(`total` 欄的其他用途)。
- 後端任何改動。

## Diff 級章節(逐檔;三類標記)
[amendment 2026-08-14: review F1/F5/F6 —— edgePriceLabels 只管 MA(VWAP 就地另分支);
volume-profile.ts 改標 🟢(對既有輸出零改變);commit 邊界寫死]

### 🟢 frontend/src/lib/stock-intraday-svg.ts
- 新增 `EDGE_LABEL_H = 10`(標籤**中心距**)、`EdgePriceLabel { y, priceMilli,
  level: "ma5"|"ma20" }`、`edgePriceLabels(oLines, obstacles: readonly number[],
  bounds: { top, bottom }): EdgePriceLabel[]`:收集 oLines 中 ma5/ma20 → 依 y 排序 →
  與 obstacles(固定點,不可動)合併做 1D 避讓(中心距 ≥ EDGE_LABEL_H)→ 底部溢出
  回推 + clamp 進 bounds。VWAP 不經此函式(就地標示)。零既有行為改動。

### 🟢 frontend/src/lib/volume-profile.ts
- `VpBar` 加 `poc: boolean`(非 optional);`buildVpBars` 判定 POC(域內 max total、
  tie 高價、全 0 全 false);新 export `VP_POC_FILL_OPACITY = 0.45`。
- 既有欄位輸出零改動(→ 🟢,樣式行為改動在元件端才發生)。

### 🔴 + 🟢 frontend/src/components/stock/StockIntradayChart.tsx
- 🔴 vp-bar 渲染:POC bar `fill-accent` + `VP_POC_FILL_OPACITY`(其餘不變)。
- 🟢 ChartStatic 尾端(主價線與極值標記**之後**,D7)三個新渲染分支:
  (a) MA:`edgePriceLabels(oLines, 右緣區極值文字 y[], { top: MARK_LABEL_TOP,
  bottom: plotBottom − 5 })` → `<text data-testid="edge-price-<level>"
  x={w − R_AXIS_W − 2} textAnchor="end" dy="0.35em" halo>{fmtTickPrice}`;
  (b) VWAP:呼叫式 `showVwap ? g.vwapLine.at(-1) ?? null : null`,非 null 才畫
  `<text data-testid="edge-price-vwap" x={clamp(末點x+4)} halo fill-ink>{fmt}`;
  (c) POC:`<text data-testid="vp-poc-label" x={Y_AXIS_W + b.w + 3} y=bar中心
  dy="0.35em" halo fill-accent>{fmt}`(vp toggle 關 → vpBars 空 → 自然不畫)。
- props 零新增(白名單 5)。

### 測試

| 檔 | 動作 | 該紅? |
|---|---|---|
| StockIntradayChart.test.tsx:1030「預設開:每個成交價位一根長條…」 | 🔴 改:loop 樣式斷言排除 POC bar,POC bar 另斷言 accent + 0.45(**事前標記該變**) | 該紅(先改測試紅 → 實作綠) |
| volume-profile.test.ts | 🟢 新增 poc 判定測試(max / tie 高價 / 全 0 / 僅域內計) | 新紅 |
| stock-intraday-svg.test.ts | 🟢 新增 edgePriceLabels 測試(收集 / 同 y 避讓 / obstacle / clamp / 空輸入) | 新紅 |
| StockIntradayChart.test.tsx | 🟢 新增:vwap 標籤開關與文字、MA 標籤口徑、stkfut 態(vwap 有 / ma poc 無)、vp-poc-label 文字與 toggle off 消失 | 新紅 |
| StockChart.test.tsx(StockIntradayChart 的元件 caller,未 mock) | 不動(review F8 已逐條查:無 text 計數 / 右緣元素斷言) | 不該紅 |
| 其餘既有測試(幾何 / oLines / z-order / 期貨態 / :214 `%` 合約 / :261 drawnRects) | 不動(review F9 已逐條查) | 不該紅 |

**Commit 邊界(review F6,三類分開)**:
1. `🟢 test [red]`:volume-profile poc 測試 → `🟢 feat [green]`:lib `poc` +
   `VP_POC_FILL_OPACITY`。
2. `🔴 test [red]`:改 :1030 既有 loop 斷言(事前標記該變)→ `🔴 fix [green]`:
   元件 POC 上色。
3. `🟢 test [red]`:edgePriceLabels + 元件三分支新測試 → `🟢 feat [green]`:
   lib edgePriceLabels + 元件三個渲染分支。

## Known Risks(review 處置後保留)

- [F1/F2 殘餘] VWAP 就地標籤與 last-dot / 主價線尾端可能重疊(halo 承擔,不入避讓集);
  極值文字在**左半場**與 POC 標籤理論上可撞(機率低,halo 承擔)。
- [F7] POC 標籤固定落在畫面中段(x ≈ 198),與早盤價線交會 —— 接受(見 D5 amendment)。

## Spec review 記錄

- Round 1(change-spec-reviewer, opus):P0 0 / P1 2(F1、F2,已修入 spec)/ P2 7
  (F3-F9:F3 口徑、F4 界統一、F5 呼叫式、F6 commit 邊界、F8 caller map 補列、
  F9 白名單 9/10 —— 全採納入 spec;F7 接受取捨記 Known Risks)。verdict fix-then-pass,
  無 accepted P0 → 不加輪。

## Backward compat

純前端渲染;`VpBar.poc` additive、唯一 caller 同輪改;無 migration、無可逆性議題。

## Code review 自評記錄

- Round 1(兩 lens,opus):P1 1(A-1)/ P2 8(A-2/A-3/B-1..B-7,A-2≡B-2)全 accepted,
  零 REFUTED;白名單 11 條 10 pass / 1 fail(A-2,修復後轉 pass)。JSON:
  `code-review-round-1.json`。修復 commits:3aacc269(A-1 red)/ 9cf2d84c(fixes green)/
  1ce90864(lock tests,mutation-verified ×2)。

self_review_head: 1ce90864
