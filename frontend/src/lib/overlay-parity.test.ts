/** CDP / MA 前後端同式的跨語言 parity(CLAUDE.md §4 跨檔契約)。
 *
 *  產生點 `copycat/server/overlay.py::compute_cdp / compute_ma / build_overlay`,本檔測的
 *  是前端鏡像 `lib/futures-overlay.ts::buildFuturesOverlay`(期貨分時的疊線不打
 *  `/api/stock/overlay` —— 那支吃股號)。兩份實作各自漂移的失效樣態是「同一組日 K 的
 *  CDP 在個股頁與期貨頁長不一樣」:兩張圖都畫得出來、兩組數字都看起來對,沒有任何錯誤
 *  訊號。所以 parity 只能靠**共用 fixture** 釘住:`tests/fixtures/overlay_parity.json` 的
 *  `expected` 是手算寫死的(不是任一邊跑出來回填的),pytest 側
 *  `tests/server/test_overlay.py::test_overlay_parity_with_frontend` 與本檔各自對它斷言,
 *  改壞任一邊就只有那一邊紅。
 *
 *  **白名單**:前端多一道 `usable()` 0 價閘(TC4 期貨會送 0 價 bar)。fixture 刻意不含
 *  0 價 bar,兩邊在同一組輸入上必須逐值相等;0 價行為由 `futures-overlay.test.ts` 單邊覆蓋。
 *
 *  用 `node:fs` 讀而不是 `import` JSON:tsconfig 沒開 `resolveJsonModule`,而為了一個
 *  測試檔改編譯選項會影響全站型別解析(同 `vp-parity.test.ts` 的理由)。 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Bar } from "@/lib/candle";
import { buildFuturesOverlay } from "@/lib/futures-overlay";
import type { StockOverlay } from "@/lib/stock-intraday-svg";

interface FixtureBar {
  date: string;
  high: number;
  low: number;
  close: number;
}

interface Fixture {
  boundary_date: string;
  bars: FixtureBar[];
  expected: StockOverlay;
}

// `import.meta.url` 而不是 `__dirname`:vitest 把測試檔轉成 ESM,`__dirname` 不保證存在
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(HERE, "../../../tests/fixtures/overlay_parity.json");

describe("CDP/MA parity(共用 fixture,後端 pytest 側斷言同一份 expected)", () => {
  const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as Fixture;

  it("同一組日 K → 與後端逐值相同的 CDP 五值 / MA5 / MA20 / 基準日", () => {
    // fixture 自身健檢:少了任一項,parity 就退化成「兩邊都算得出一個數」的空談
    const boundary = fixture.boundary_date;
    expect(fixture.bars.filter((b) => b.date < boundary).length).toBeGreaterThanOrEqual(20);
    expect(fixture.bars.some((b) => b.date >= boundary)).toBe(true);
    expect(fixture.bars.every((b) => b.close > 0)).toBe(true);

    // 後端 `DailyBar` 只有 high/low/close;前端 `Bar` 多 o/v,補值不影響 CDP/MA(不吃這兩欄)
    const bars: Bar[] = fixture.bars.map((b) => ({
      t: b.date,
      o: b.close,
      h: b.high,
      l: b.low,
      c: b.close,
      v: 1,
    }));
    expect(buildFuturesOverlay(bars, boundary)).toEqual(fixture.expected);
  });
});
