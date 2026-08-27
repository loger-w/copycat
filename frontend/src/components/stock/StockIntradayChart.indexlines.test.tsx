/** @vitest-environment jsdom */
import { cleanup } from "@testing-library/react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { fromSnapshot } from "@/lib/stock-accum";
import { wrap } from "@/test-utils";

/** RTL 的 `rerender` 會把整棵樹(含 `wrap` 的 QueryClientProvider)換掉 → 每個情境重新掛載 */
function mount(ui: React.ReactElement) {
  cleanup();
  return wrap(ui);
}

/** F1(chart-ux-batch-0826):個股分時圖疊「加權 / 櫃買」即時走勢,兩顆 toggle 各自開關。 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ cdp: null }))));
});

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
});

const NO_REF = fromSnapshot({
  code: "2330",
  seq: 1,
  last: null,
  vwap: null,
  minutes: { "541": { c: 2_380_000, v: 1, i: 0, o: 1, u: 0, h: 2_380_000, l: 2_380_000 } },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: null, upper: null, lower: null, y_vol: null },
});

function series(minutes: Record<string, number>): IndexSeries {
  return { p: null, ref: 20_000_000, high: null, low: null, stale: false, minutes };
}

const INDEX = { twse: series({ "0901": 20_100_000, "0902": 20_200_000 }), otc: series({ "0901": 20_000_000 }), txf: null };
// 🟢 feat/txf-intraday-overlay:台指期序列(結算價 23000 → 0901 −1%)
const WITH_TXF = { ...INDEX, txf: { ...series({ "0845": 23_230_000, "0901": 22_770_000 }), ref: 23_000_000 } };

function toggles(over: Partial<ChartToggles> = {}): ChartToggles {
  return { vwap: true, cdp: false, ma: false, bb: true, vp: false, fills: false, idxTwse: false, idxOtc: false, idxTxf: false, syncHover: true, ...over };
}

describe("IntradayChartCore 指數疊線(F1)", () => {
  it("toggle 開 → 該指數一條 index-line + 右緣「加權 +1.00%」小標;關 → 無", () => {
    let { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={toggles({ idxTwse: true })} variant="page" indexSeries={INDEX} />,
    );
    const twse = container.querySelector('[data-testid="index-line-twse"]');
    expect(twse).toBeTruthy();
    expect(twse!.querySelector("polyline")).toBeTruthy();
    expect(twse!.querySelector("text")?.textContent).toBe("加權 +1.00%");
    expect(container.querySelector('[data-testid="index-line-otc"]')).toBeNull();

    ({ container } = mount(
      <IntradayChartCore accum={ACCUM} toggles={toggles({ idxOtc: true })} variant="page" indexSeries={INDEX} />,
    ));
    expect(container.querySelector('[data-testid="index-line-twse"]')).toBeNull();
    expect(container.querySelector('[data-testid="index-line-otc"]')?.querySelector("text")?.textContent).toBe(
      "櫃買 0.00%",
    );

    ({ container } = mount(<IntradayChartCore accum={ACCUM} toggles={toggles()} variant="page" indexSeries={INDEX} />));
    expect(container.querySelectorAll('[data-testid^="index-line-"]').length).toBe(0);
  });

  it("兩顆鈕在 toggle 列上、有資料源且有昨收時可按;無資料源 / 無昨收 → 反灰並說明", () => {
    let { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={toggles()} variant="page" indexSeries={INDEX} />,
    );
    const labels = [...container.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels).toEqual(["均價", "CDP", "MA", "量分佈", "成交點", "加權", "櫃買", "台指期"]);
    const twseBtn = [...container.querySelectorAll("button")].find((b) => b.textContent === "加權")!;
    expect(twseBtn.hasAttribute("disabled")).toBe(false);

    ({ container } = mount(<IntradayChartCore accum={ACCUM} toggles={toggles({ idxTwse: true })} variant="page" indexSeries={null} />));
    const noSrc = [...container.querySelectorAll("button")].find((b) => b.textContent === "加權")!;
    expect(noSrc.hasAttribute("disabled")).toBe(true);
    expect(noSrc.getAttribute("title")).toBe("無指數資料");
    expect(container.querySelectorAll('[data-testid^="index-line-"]').length).toBe(0);

    ({ container } = mount(<IntradayChartCore accum={NO_REF} toggles={toggles({ idxTwse: true })} variant="page" indexSeries={INDEX} />));
    const noRef = [...container.querySelectorAll("button")].find((b) => b.textContent === "加權")!;
    expect(noRef.hasAttribute("disabled")).toBe(true);
    expect(noRef.getAttribute("title")).toBe("無昨收");
    expect(container.querySelectorAll('[data-testid^="index-line-"]').length).toBe(0);
  });

  it("card 變體照畫線(鈕在圖牆頂,卡片內沒有 button);futures 態不畫也沒有鈕", () => {
    let { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={toggles({ idxTwse: true })} variant="card" indexSeries={INDEX} />,
    );
    expect(container.querySelector('[data-testid="index-line-twse"]')).toBeTruthy();
    expect(container.querySelectorAll("button").length).toBe(0);

    ({ container } = mount(
      <IntradayChartCore
        accum={ACCUM}
        toggles={toggles({ idxTwse: true, idxOtc: true })}
        variant="page"
        mode="futures"
        indexSeries={INDEX}
      />,
    ));
    expect(container.querySelectorAll('[data-testid^="index-line-"]').length).toBe(0);
    expect([...container.querySelectorAll("button")].map((b) => b.textContent)).not.toContain("加權");
  });

  // 🟢 feat/txf-intraday-overlay:第三條「台指期」線;資料源缺(txf null)→ 鈕反灰「無台指期資料」
  it("idxTxf 開 → index-line-txf + 右緣「台指期 -1.00%」;txf 序列為 null → 鈕反灰、線不畫", () => {
    let { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={toggles({ idxTxf: true })} variant="page" indexSeries={WITH_TXF} />,
    );
    const txf = container.querySelector('[data-testid="index-line-txf"]');
    expect(txf).toBeTruthy();
    expect(txf!.querySelector("polyline")?.getAttribute("class")).toBe("stroke-idx-txf");
    expect(txf!.querySelector("text")?.textContent).toBe("台指期 -1.00%");
    // 只開台指期時另外兩條不畫
    expect(container.querySelectorAll('[data-testid^="index-line-"]').length).toBe(1);
    const btn = [...container.querySelectorAll("button")].find((b) => b.textContent === "台指期")!;
    expect(btn.hasAttribute("disabled")).toBe(false);
    expect(btn.getAttribute("aria-pressed")).toBe("true");

    ({ container } = mount(
      <IntradayChartCore accum={ACCUM} toggles={toggles({ idxTxf: true })} variant="page" indexSeries={INDEX} />,
    ));
    expect(container.querySelector('[data-testid="index-line-txf"]')).toBeNull();
    const off = [...container.querySelectorAll("button")].find((b) => b.textContent === "台指期")!;
    expect(off.hasAttribute("disabled")).toBe(true);
    expect(off.getAttribute("title")).toBe("無台指期資料");
    // 加權 / 櫃買仍可按(反灰是 per-線的,不是整組)
    expect([...container.querySelectorAll("button")].find((b) => b.textContent === "加權")!.hasAttribute("disabled")).toBe(false);

    // 個股沒昨收 → 台指期鈕的理由是「無結算價」(基準是結算價,不叫昨收;review round 1 S2)
    ({ container } = mount(
      <IntradayChartCore accum={NO_REF} toggles={toggles({ idxTxf: true })} variant="page" indexSeries={WITH_TXF} />,
    ));
    const noRef = [...container.querySelectorAll("button")].find((b) => b.textContent === "台指期")!;
    expect(noRef.hasAttribute("disabled")).toBe(true);
    expect(noRef.getAttribute("title")).toBe("無結算價");
  });
});
