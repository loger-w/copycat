# change-spec:江波圖 autofit y 域改為「含當日高低」

分流判定:user 帶已成形改法(next-time 條目 2026-08-04 已查證行號與實例,修法核心明確)→ grilling 確認,無 counter-proposal(修法與 0 值歸一慣例、既有域外 guard 完全相容)。全部決策 `[auto-default]`。

## 成功條件(可驗收)

- SC-1:autofit 分支(無漲跌停)+ `input.high` 超出每分鐘收盤範圍時,y 域上緣 ≥ high(unit:毫元;量法:`g.yDomain[1] >= high` 斷言)且 `highMark !== null`、`highMark.y` 落在繪圖區內(`PAD_Y ≤ y ≤ height − X_LABEL_H − PAD_Y`)。
- SC-2:同理 `input.low` 低於收盤範圍時 `g.yDomain[0] <= low` 且 `lowMark !== null`。
- SC-3:實例回歸:2330 2026-07-30 情境,**meta: null**(盤後無 meta 路徑,ref = 首筆收盤)。具體 fixture:首筆收盤 2_210_000 / 最低收盤 2_165_000 / 最高收盤 ≤ 2_255_000(其中一分鐘帶 `h: 2_260_000`)、`high: 2_260_000`。改動前 half = 45_000×1.1 = 49_500 → yTop = 2_259_500 < high → highMark null(紅);改動後 hi−ref = 50_000 → half = 55_000 → yTop = 2_265_000 ≥ high → 可畫。**實例的域上緣 2259.5 由低側(ref−lo)決定,不是收盤群最高** — 臨界形狀(域外 0.02%)以此組數字重現。`[amendment 2026-08-05 R11: 原寫「收盤群最高 2259.5」與現況表矛盾(那是域上緣),照抄會造出 vacuous fixture;改為反推後的臨界數字]`
- SC-4:域對稱性保留:`(yDomain[0] + yDomain[1]) / 2 ≈ ref`(既有對稱域語意不變,只是半幅池擴大)。
- SC-5:不變式(table-driven):`norm(high)`/`norm(low)` 非 null 時恆有 `yDomain[0] <= low && high <= yDomain[1]`。case 表明列(`[amendment 2026-08-05 R13]`):(a) high 在收盤群之上且舊域外;(b) low 在收盤群之下且舊域外;(c) high/low 皆在收盤群內(域同未傳);(d) high === ref;(e) low = 0(不可得,域同未傳且 `yDomain[0] > 0`)。(a)-(d) 另斷言 `yDomain[0] > 0`(realistic 範圍內成立)。`[amendment 2026-08-05: R8 — 單點 fixture 升級為不變式]`

## Known Risks

- 對稱域設計下,`dayLow < ref×0.0909`(盤中跌逾 91%)時 `yBottom = ref − 1.1×(ref−dayLow)` 為負 → 3 點 fallback 刻度會印負價位、垂直空間浪費(圖仍可畫,退化為 cosmetic)。autofit 情境的主體是「盤後無 meta 的一般個股」,±10% 制度下不可達;興櫃無漲跌幅商品理論可達但單日 −91% 實務不存在。不為此加 clamp(會破壞 SC-4 對稱性語意)。`[R13 部分處置:負域類納入記錄不納入斷言]`
- `[amendment 2026-08-05: F5/WL-2]` ref 不可得(prices 空 + 無 metaRef → ref=0)時若仍併入 dayHigh/dayLow,域變 `[−1.1×high, +1.1×high]`(假價位刻度 + 標記錯位),繞過上一條的 ±10% 論證。修法:**ref > 0 才併入半幅池**(無中心錨點時擴域只放大垃圾),ref=0 行為回到改動前(退化域、標記 null),補測試釘住。
- 畫面可指認:無漲跌停日(如盤後回補檢視)江波圖右上/右下的「H 標記」「L 標記」(白底小標籤,標當日極值價)在極值超出收盤範圍時仍出現在對應分鐘 x 位置。AI 截圖層以座標斷言 + **新增的 autofit 元件測試**(`[amendment 2026-08-05: R5 — 既有元件測試全走漲跌停分支或 high/low=null,對本輪路徑零覆蓋;新增 autofit + 域外極值 → 標記出現的元件測試]`)代替(盤後無 meta 情境可實看)。

## 不能破壞的既有行為白名單

(對照 `stock-intraday-svg.test.ts` 現有斷言;行號為 2026-08-05 現值)

1. 漲跌停分支域**恰為** `[lower, upper]`,不受 high/low 影響(:38-58)。
2. autofit 未傳 high/low → 域計算與現行完全相同(:255-266、:270-290)。
3. `markFor` 域外 guard 保留(:94-101,META 漲跌停分支下極端值仍不畫)。
4. `high === low`(一字盤)只留 highMark(:84-92)。
5. 域內但等值反查落空 → 不畫(:103-110);minutes 缺 h/l → 不畫(:112-123);high/low 未傳 → 不畫(:125-129)。
6. yTicks:缺漲跌停走 3 點 fallback(:441-)、kind 不標(:359-368)。
7. 0 值歸一慣例:high/low 為 0(TC4 "0" → to_milli_units 0)視為不可得,不得把 0 拉進域(否則 yBottom 變負、整圖壓扁)。**危險方向是 `low = 0`**(`Math.min` 會吃進 0;`high = 0` 被 `Math.max` 自然忽略,測不出漏做 norm)— 守門測試必須用 low=0 並加 `yDomain[0] > 0` 斷言。`[amendment 2026-08-05: R2]`

### 刻意接受的連帶變化(autofit 情境限定)`[amendment 2026-08-05: R4/R6]`

域變寬時,以下 user 可見數字連帶位移 — 這是本輪修法的本意(域裝下極值),不是回歸:

- **CDP/MA 疊線裁切門檻放寬**(`overlayLines`:417 用 `g.yDomain` 裁切):原本落在舊域外被裁掉的疊線,新域內會開始出現。與 round4 R6「域收窄時疊線變少」是同一條語意的反向。補一支測試釘住(autofit + 位於「舊域外、新域內」的 ma5 → 由不給變成給)。
- 3 點 fallback 刻度(:327-329 印 `[yTop, ref, yBottom]`)的上下緣價位數字跟著域變。
- 走勢線/VWAP/填色多邊形垂直壓縮、hover priceAtY 讀價對應關係隨域縮放 — toY/priceAtY 互逆性不變,僅比例變。

## Backward compat / migration

`Input` 介面不變(high/low 既有 optional 欄位),唯一 production caller(`StockIntradayChart.tsx:479`)已傳 accum.high/low,零改動。純前端計算無持久化,無 migration。域變寬只發生在「autofit + 極值超出收盤群」情境 — 該情境現況就是 bug(標記靜默消失)。

## Out of scope

- 漲跌停分支的任何改動。
- markFor 域外 guard 的移除(保留,防舊後端缺 h,l 與無等值分鐘)。
- 後端 high/low 欄位語意。
- 江波圖(river/六腿)— 名稱撞名但本輪只動個股分時圖(stock-intraday)。

---

# Diff 級 spec

## `frontend/src/lib/stock-intraday-svg.ts` 🔴 行為改動

`buildIntradayGeometry` autofit 分支(:270-277):

```ts
// 現況
const hi = Math.max(ref, ...prices);
const lo = Math.min(ref, ...prices);

// 改為(dayHigh/dayLow 沿用檔內 norm 的 0 值歸一;高只往上擴、低只往下擴)
const dayHigh = norm(input.high);
const dayLow = norm(input.low);
const hi = Math.max(ref, ...prices, ...(dayHigh !== null ? [dayHigh] : []));
const lo = Math.min(ref, ...prices, ...(dayLow !== null ? [dayLow] : []));
```

`half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1` 及以下不動。註解補一行成因(2330 2026-07-30 實例:域裝不下逐筆極值 → 標記靜默消失)。

另:`markFor` 的入參改吃 norm 過的值(`markFor(dayHigh, "h")` / `markFor(dayLow, "l")`,high===low 判定同樣用 norm 後值)— 域計算與標記對 high/low 的解讀統一為「0 = 不可得」,不再隱性依賴 yBottom > 0 擋 0(本輪動的正是決定 yBottom 的路)。白名單 4/5 測試皆用正值不受影響。`[amendment 2026-08-05: R7]`

- 既有測試該紅的:**無**(current-state.md 盤點:autofit 相關測試皆未傳 high/low;高低標記測試皆走漲跌停分支)。
- 若任何既有測試變紅 = 打到無關東西,回頭查。

## `frontend/src/lib/stock-intraday-svg.test.ts` 🔴 新測試(TDD 紅先行)

`[amendment 2026-08-05: R1 — 原 fixture(ref=2_320_000、high=2_260_000)在改動前即全綠(現況域 [2_253_450, 2_386_550] 已含 high),且 low=2_310_000 > high 自相矛盾(R3)。全部 fixture 改為真正重現「域裝不下」的形狀,並於實作前先跑一次確認紅、把紅輸出留存 verification.md]`

autofit 域 describe 區新增:

1. 「autofit(meta: null)+ 長上影極端分鐘 → 域含 high,highMark 可畫」(SC-1/SC-3):minutes = `[540: {c: 2_200_000, h: 2_600_000}], [541: {c: 2_210_000}]`,`meta: null`,`high: 2_600_000`。改動前域 = ref(=首筆收盤 2_200_000)± 24_200 → high 域外、`highMark === null`(紅);改動後 `yDomain[1] >= 2_600_000`、`highMark !== null`、`highMark.y` 介於 `PAD_Y` 與 `height − X_LABEL_H − PAD_Y`。
2. 「autofit + low 低於收盤群 → 域含 low,lowMark 可畫」(SC-2):minutes = `[540: {c: 2_200_000, l: 1_900_000}], [541: {c: 2_190_000}]`,`meta: null`,`low: 1_900_000` → 改動前 lowMark null(紅);改動後 `yDomain[0] <= 1_900_000`、`lowMark !== null`。
3. 「autofit + low=0 → 視為不可得,域同未傳且 > 0」:兩次呼叫比對 yDomain 相等 **且 `yDomain[0] > 0`**(白名單 7;R2 — 用 low=0 不用 high=0,後者被 Math.max 自然忽略測不出漏 norm)。
4. 「autofit + 含極值後域仍以 ref 為中心」(SC-4):用測試 1 fixture 斷言 `(yDomain[0]+yDomain[1])/2 ≈ ref`。
5. table-driven 不變式(SC-5):high/low 相對 ref 位置 4-5 組,`low > 0 && high > 0` 時恆 `yDomain[0] <= low && high <= yDomain[1]`。`[amendment 2026-08-05: R8]`
6. 「autofit 疊線裁切門檻隨域放寬」:overlayLines + autofit,ma5 位於舊域外新域內 → 由不給變成給。`[amendment 2026-08-05: R4]`

## `frontend/src/components/stock/StockIntradayChart.test.tsx` 🔴 元件測試 `[amendment 2026-08-05: R5]`

- 新增 1 支,**不得 spread ACCUM 的 minutes**(ACCUM 的 per-minute h 全在 autofit 域內,spread 版改動前即綠 — R10):新造 snapshot,minutes = `{"541": {c: 2_380_000, v: 10, o: 10, i: 0, u: 0, h: 2_600_000, l: 2_370_000}, "542": {c: 2_390_000, …}}`、meta 帶 ref 2_320_000 但 `upper: null, lower: null`、`high: 2_600_000, low: 2_370_000`。改動前域 [2_243_000, 2_397_000](half = 70_000×1.1)→ high 域外、`circle[data-testid="day-high"]` 不畫(紅);改動後 hi = 2_600_000 → half = 308_000 → yTop = 2_628_000 → 畫。**實作前先跑確認紅、紅輸出留存 verification.md(與 lib 側同一要求)**。`[amendment 2026-08-05 R10: 原「spread ACCUM + 換 meta」配方兩個變體改動前皆綠,vacuous;改為新造 snapshot + 具體數字 + 紅先行留證]`
- helper `geometryOf` 改吃整份 accum:`geometryOf(container, accum)` → `buildIntradayGeometry({minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low}, {width, height})`;既有三處呼叫點(:839/:848/:901 慣例)一併帶入該測試用的 accum(META 分支下域不變,不會紅)。`[amendment 2026-08-05 R14: 原修法只補 high/low,minutes/meta 仍硬編 ACCUM — 新測試換 meta 後參考幾何會拿錯分支]`

## 測試影響總表 `[amendment 2026-08-05: R12 — 逐支標紅先行/守門綠]`

| 測試 | 分類 | 預期 |
|---|---|---|
| 既有全部(1002) | — | 不該紅 |
| lib 新 1(SC-1/SC-3 high)/ 2(SC-2 low)/ 5(不變式 a、b 組)/ 6(疊線放寬) | 🔴 紅先行 | pre-impl 必紅,紅輸出入 verification.md;實作後綠 |
| lib 新 3(low=0 守門)/ 4(對稱性,改動前後皆成立)/ 5 的 c、d、e 組 | 守門綠 | 改動前後皆綠,存在意義是釘住 0 值歸一與對稱語意 |
| 元件新增 1 支 | 🔴 紅先行 | pre-impl 必紅;實作後綠 |
| 元件 helper 修正 | 🔵 | 既有三處呼叫不紅 |

驗證 gate(frontend/):`npm test -- --run` + `npx tsc -b` + `npx eslint src`,輸出附 verification.md。`[amendment 2026-08-05: R9]`

self_review_head: 819d2f87f254c0d9848e29ff97902d2c91c18890
