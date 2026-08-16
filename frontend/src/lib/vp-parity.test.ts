/** VP 折法的跨語言 parity(change-spec AD-2)。
 *
 *  後端 `copycat/live/stock_state.py::StockDayState._fold_vp` 與本檔的 `foldVp` 折的是
 *  同一份規則。兩份各自漂移的失效樣態是「同一檔在單檔頁與卡片上 POC 不同」—— 兩張圖
 *  都畫得出來、兩個數字都看起來對,沒有任何錯誤訊號。所以 parity 只能靠**共用 fixture**
 *  釘住:`tests/fixtures/vp_parity.json` 的 `expected` 是手算寫死的(不是任一邊跑出來
 *  回填的),pytest 側 `tests/live/test_stock_state.py::test_vp_parity_with_frontend_fold`
 *  與本檔各自對它斷言,改壞任一邊就只有那一邊紅。
 *
 *  用 `node:fs` 讀而不是 `import` JSON:tsconfig 沒開 `resolveJsonModule`,而為了一個
 *  測試檔改編譯選項會影響全站型別解析。vitest 的 environment 是 node(vite.config.ts),
 *  fs 可用;本檔**不放在 jsdom 檔內**也是這個理由。 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { foldVp, type VpCell } from "@/lib/stock-accum";

interface Fixture {
  ticks: { t: string; p: number; q: number; side: string }[];
  expected: Record<string, [number, number, number]>;
}

// `import.meta.url` 而不是 `__dirname`:vitest 把測試檔轉成 ESM,`__dirname` 不保證存在
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(HERE, "../../../tests/fixtures/vp_parity.json");

describe("VP parity(共用 fixture,後端 pytest 側斷言同一份 expected)", () => {
  const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as Fixture;

  it("fixture 自身健檢:涵蓋窗外 / p=0 / 跨 tick 段 / 三種 side", () => {
    // 沒有這條的話 fixture 被改瘦(只剩一筆窗內成交)時 parity 仍然全綠 = 空談
    const ticks = fixture.ticks;
    expect(ticks.some((t) => t.p <= 0)).toBe(true);
    expect(ticks.some((t) => t.t < "09:00:00")).toBe(true);
    expect(ticks.some((t) => t.t > "13:30:59")).toBe(true);
    expect(new Set(ticks.map((t) => t.side))).toEqual(new Set(["outer", "inner", "neutral"]));
    // 跨 tick 段:0.01 / 0.05 / 0.1 / 0.5 / 5 元檔各有代表(key 的段界判定才有鑑別力)
    expect(Object.keys(fixture.expected).length).toBeGreaterThanOrEqual(5);
  });

  it("逐筆 foldVp 後的直方圖 === 手算 expected", () => {
    const vp = new Map<number, VpCell>();
    for (const row of fixture.ticks) foldVp(vp, row.t, row.p, row.q, row.side);
    const got: Record<string, [number, number, number]> = {};
    for (const [price, cell] of vp) got[String(price)] = [cell.t, cell.o, cell.i];
    expect(got).toEqual(fixture.expected);
  });
});
