# current-state:江波圖 autofit y 域改為「含當日高低」

日期:2026-08-05。分支 `mod/river-autofit-daily-range`。

## 目標檔案

`frontend/src/lib/stock-intraday-svg.ts` — `buildIntradayGeometry(input, size)`。

## 現況

### y 域計算(:264-277)

兩條分支:

1. **漲跌停域**(:266-269):`upper !== null && lower !== null` → `yTop = upper; yBottom = lower`(恰為漲跌停,不留邊)。**本輪不動**。
2. **對稱 autofit fallback**(:270-277):
   ```ts
   const hi = Math.max(ref, ...prices);
   const lo = Math.min(ref, ...prices);
   const half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1;
   yTop = ref + half;
   yBottom = ref - half;
   ```
   其中 `prices = entries.map(([, m]) => m.c).filter(p => p > 0)`(:251)— **只取每分鐘收盤**。`input.high` / `input.low`(:206-207,後端 tick 級 running max/min)完全不參與。

### 高低點標記(:375-383)

`markFor` 對 `target < yBottom || target > yTop` 回 `null`(:377,域外不畫)→ autofit 域裝不下逐筆極值時標記靜默消失。實例:2330 2026-07-30 盤後域 `[2160.5, 2259.5]`,當日最高 2260.0 域外 0.5 元。

### 0 值歸一慣例(:252-262)

`norm(v) = v > 0 ? v : null` — meta 的 ref/upper/lower 走此歸一(TC4 送 "0" = 不可得)。`input.high/low` 型別 `number | null | undefined`,markFor 只擋 `== null`,未擋 0/負值(現況 0 會被域外 guard 自然擋掉,因 yBottom > 0)。

## Caller map(grep buildIntradayGeometry,含動態用法檢查:無 template string / reflection 用法)

| Caller | 位置 | 傳 high/low? |
|---|---|---|
| `StockIntradayChart.tsx` | :479(唯一 production caller,useMemo) | 傳 `accum.high, accum.low` |
| `StockIntradayChart.test.tsx` | :759(helper) | 依測試而定 |
| `stock-intraday-svg.test.ts` | 全檔 ~40 處 | 高低標記 describe 區塊傳;autofit 相關測試**皆未傳** |

`buildEnergyBars`(副圖出貨路徑)不走 y 域,不受影響。

## 受影響的既有測試盤點

- `stock-intraday-svg.test.ts:255`「upper/lower 缺 → 沿用對稱 autofit 域」:未傳 high/low → **不該紅**。
- `:270`「ref/upper/lower 皆 0 → autofit」:未傳 high/low → **不該紅**。
- `:94`「域外的極值不畫」:META 有 upper/lower → 走漲跌停分支,**不該紅**(此測試正是「域外 guard 保留」的守門)。
- 其餘高低標記測試(:70/:84/:103/:112/:125):META 有漲跌停 → 域分支不變,**不該紅**。
- `StockIntradayChart.test.tsx`:元件級,META 慣例同上,預期**不該紅**(Phase 6 驗證)。

## Baseline

`npm test -- --run`:72 檔 / 1002 tests 全綠(2026-08-05 10:48)。

## 目標

autofit 分支的 hi/lo 把 `input.high` / `input.low` 併入(0/負值依 norm 慣例視為不可得),使無漲跌停時域必含當日極值 → 高低點標記必可畫。漲跌停分支不動;markFor 域外 guard(:377)保留(仍防舊後端缺 h,l 與無等值分鐘)。

## Backward compat

- `Input` 介面不變(high/low 既有 optional 欄位),caller 零改動。
- 域語意變化只在「autofit + 有 high/low」情境:域可能比舊版寬(半幅由極值決定而非收盤)。對稱性(以 ref 為中心)保留。
- 無 migration(純前端計算,無持久化)。
