# verification — R2 期貨分時功能批

## 逐條處置

| 條 | 處置 | 落點 |
|---|---|---|
| N042 期貨 CDP/MA | **做**:`lib/futures-overlay.ts` 前端算 + core `overlay` 注入 | 🟢 `a20b6190` |
| N043 + N070 成交點 | **做**:`alldayFillPoints` 錨定日界 + toggle 解禁 | 🟢 `a20b6190` |
| N087 >20k tick VP 偏小 | **做(最小方案 = 標示)**:`vpTruncated` → 量分佈鈕 tooltip | 🟢 `a20b6190` |
| N046 hover 命中 | **做**:`snapRadius`(futures 態限定,預設關) | 🔴 `e89b939c` |
| N096 期貨態 POC | **與記載不符 → 只補 lock + 更正註解**(見下) | 🟢 `a20b6190` / 🔵 本輪尾 |
| N047 副圖 rect 重建 | **量測後留原樣 + 註解**(見下) | 🔵 本輪尾 |

### 與 spec 記載不符處

1. **N096「vp toggle 解禁 + foldVp 參數化」已無事可做**:現行 `vpEnabled =
   toggles.vp && !stkfut && !index` 與 toggle `available: !stkfut` 早就讓期貨態
   VP/POC 可用,而期貨的 `accum.vp` 由 `futuresBarsToAccum` 以近全軸自折,**不經
   `foldVp`** —— 現貨窗硬編與期貨態無關。本輪只補 characterization lock(POC
   highlight + 價位標 + toggle 關掉整組消失)並更正 `StockIntradayChart.tsx` 內
   「期貨態三顆一律反灰 / VP 折入窗仍是現貨窗」的過時註解。`foldVp` 參數化唯一的
   潛在讀者是個股期(stkfut)態,而該態刻意不畫 VP → 不做(不為未來可能加抽象)。
2. **N047 的「已 memo」與實際不同**:`EnergySub` 確實 memo,但 `subEnergy` 的 deps
   帶 `accum.minutes`,live 價每變一次就換 identity → 每 tick 全層重建(memo 擋得住
   hover、擋不住報價)。量測見下。
3. **期貨 POC 標籤印的是桶心**(`23002.5`)而不是檔位價(`23000`):`futuresBarsToAccum`
   的 vp key 取 `snapDown(c) + tickOf(c)/2`(帶界才與桶區間一致)。既有行為,本輪
   只釘住不改,列為 next-time 候選。

### 保守分岔(明示的取捨)

- **`fillPoints` 的日期界不動**:近全軸另開 `alldayFillPoints`,`fillPoints` /
  `fillsByCode` 簽名與「今日 ∨ 昨日活單」逐字不變 → 個股頁 / 群組圖牆零影響。
  共用的只有欄位守門(`baseFill`)與加權聚合(`aggregate`)。
- **`snapRadius` 預設 0**:next-time 原文寫「futures 態限定(動 `minuteOf` 白名單)」,
  故不改現貨/指數的 hover 語意 —— 有一條反向 lock(stock 態同一個相鄰空分鐘仍退化)。
- **`overlaySupported` 用預設 true**:「有沒有資料源」與「這一天算不算得出來」不合成
  一個旗標;算不出來由全 null overlay 表達(反灰 + 預設 tooltip「無日線資料」)。
- **日 K query 不掛 `enabled: cdp||ma`**:按下才抓會多一次空窗閃動;成本是每商品每日
  一發(與日 K 模式同 queryKey,TQ 去重)。
- **`StockAccum.vpTruncated` 選填**:與 `trial`/`tapeOmitted` 的「必填」紀律刻意不同 ——
  唯一產生點是 `fromSnapshot`,漏帶的後果是少一個 tooltip(安全側),而必填要動
  期貨/指數 adapter 與大量 fixture(R2 外的檔)。
- **`VP_TICK_CAP` 不登記為 CLAUDE.md §4 跨檔契約**:後端上限調大時本旗標只是不再標示
  (失效方向 = 少講一句,不是講錯),與 §4 那種「漂掉就零錯誤訊號的假陳述」不同級。

## 紅 → 綠證據

| 階段 | 指令 | 結果 |
|---|---|---|
| 紅(lib 層) | `npx vitest run src/lib/{futures-overlay,fill-marks,stock-intraday-svg,stock-accum}.test.*` | **19 failed** / 214 passed(4 files failed) |
| 綠(lib 層) | 同上 | 242 passed(4 files) |
| 紅(元件層 core) | `npx vitest run src/components/stock/StockIntradayChart.futures.test.tsx` | **4 failed** / 35 passed |
| 綠(元件層 core) | 同上 | 39 passed |
| 紅(元件層 FuturesChart) | `npx vitest run src/components/futures/FuturesChart.test.tsx` | **7 failed** / 28 passed |
| 綠(元件層 FuturesChart) | 同上 | 36 passed(含後補的 ma5 不足案) |

紅的內容不是「還沒寫」而是真的指到症狀:成交點鈕 disabled、相鄰空分鐘無 crosshair-v、
tf=D 沒被打、`alldayFillPoints` 不存在、`MINUTE_SNAP_RADIUS` undefined、vp 鈕無 tooltip。

## N047 量測(留原樣的依據)

一次性 bench(scratchpad,不進版控),jsdom + RTL `rerender`,滿窗 1140 格近全軸:

```
N047  整張分時圖每 tick re-render:15.04 ms(rects=1140,30 輪平均)
N047b 隔離的純 1140 rect 層每輪重建:17.46 ms(30 輪平均)
```

→ 成本幾乎全在 rect 層,但**量級本身不構成瓶頸**:jsdom 的 diff 比真瀏覽器慢一個量級,
而期貨報價經 0.1 s coalesce 後最多 ~10 則/s。與原記載「真環境 hover 目視未見掉幀」一致。
**沒有採用「資料版本 memo key」**:1K 回補可以在總量不變的情況下改寫某一分鐘的量,
以總量當版本會讓副圖靜默停在舊值(用錯誤換效能)。真正安全的收法是 `EnergySub` 改單一
`<path>`(節點 1140 → 1),留 next-time。

## 全套 gate(frontend/)

```
npx vitest run          → Test Files 139 passed (139) / Tests 2626 passed (2626)
npx tsc -b              → 無輸出(PASS)
npx eslint src          → 無輸出(PASS)
npx react-doctor@latest --scope changed --no-telemetry → Scanned 11 files,No issues found
```

後端未動(本輪純 frontend)→ pytest / ruff / pyright / `copycat validate` 不在本輪 gate。

## 真環境待驗(user 過目項)

1. **期貨分時 CDP/MA**:盤中開 CDP/MA,五條線 + MA5/MA20 的位置與說明列「疊線基準
   YYYY-MM-DD」是否為**前一交易日**(夜盤時段特別看:基準不該跳到今天)。
2. **成交點**:當日有成交時 ▲/▼ 是否落在正確分鐘;**夜盤成交(00:00–05:00)是否畫在
   同一張圖的夜盤段**而不是消失或跑到日盤段。
3. **hover 命中**:夜盤薄量段游標掃過去,十字垂直線是否貼著游標命中最近的一分鐘
   (不該出現「指著這裡、報 10 分鐘前」)。
4. 期貨 POC 標籤字面 `23002.5`(桶心)是否可接受,或要改印檔位價。

## two-axis review 收修(2026-08-24)

### P1 紅→綠(基準日判準)

紅測試先行,`meta.partial_last` 判準下實際失效的輸出:

```
FAIL src/lib/futures-overlay.test.ts        (新 describe「基準日以圖上錨定日為界」3 條)
FAIL src/components/futures/FuturesChart.test.tsx
     Expected: "疊線基準 2026-08-20"
     Received: "…疊線基準 2026-08-22 · VWAP 23000"      ← 基準落在尚未發生的交易日
→ Tests 7 failed | 42 passed (49)
```

改判準(`t < anchorDate`)後同兩檔 `Tests 49 passed (49)`。

### parity oracle 咬得住(不是空談)

`build_overlay` 對同一份 fixture 移動界:

```
界正確(2026-07-23) → == expected     True
界 +2 日(2026-07-25)→ == expected    False(date 2026-07-24,野值 bar 入計算)
界 −1 日(2026-07-22)→ == expected    False(date 2026-07-21)
```

### 全套 gate(收修後)

```
frontend/  npx vitest run  → Test Files 140 passed (140) / Tests 2631 passed (2631)
frontend/  npx tsc -b      → 無輸出(PASS)
frontend/  npx eslint src  → 無輸出(PASS)
frontend/  npx react-doctor@latest --scope changed --no-telemetry → Scanned 13 files,No issues found
root/      pytest -q tests/server/test_overlay.py → 12 passed
root/      ruff check copycat tests → All checks passed!
root/      pyright → 0 errors, 0 warnings, 0 informations
```
