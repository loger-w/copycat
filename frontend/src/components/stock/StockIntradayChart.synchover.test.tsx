/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render } from "@testing-library/react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { fromSnapshot } from "@/lib/stock-accum";
import { minuteToX, SPOT_WINDOW } from "@/lib/stock-intraday-svg";
import { wrap } from "@/test-utils";

/** F3(chart-ux-batch-0826):群組圖牆同步十字線 —— core 的兩個新 prop。
 *  `syncHoverMin` 注入 → 本圖沒有自己 hover 時,以該分鐘畫十字線(y 錨在本圖該分鐘收盤);
 *  `onHoverMinute` → 只在 hover 分鐘變化時回呼(亞像素 mousemove 不吵整面牆)。 */

const W = 800;
const RECT = { left: 0, top: 0, right: W, bottom: 260, width: W, height: 260, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ cdp: null }))));
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(RECT);
});

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_390_000, t: "09:02:30.000", cum_vol: 12 },
  vwap: 2_385_000,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
});

const TOGGLES: ChartToggles = {
  vwap: true, cdp: false, ma: false, bb: true, vp: false, fills: false, idxTwse: false, idxOtc: false, idxTxf: false, syncHover: true,
};

function mount(ui: React.ReactElement) {
  cleanup();
  return wrap(ui);
}

describe("IntradayChartCore 同步十字線(F3)", () => {
  it("syncHoverMin 有資料的分鐘 → 十字線 + 時間標;沒資料的分鐘 / null → 不畫", () => {
    let { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} syncHoverMin={541} />,
    );
    const v = container.querySelector('[data-testid="crosshair-v"]');
    expect(v).toBeTruthy();
    expect(v!.getAttribute("x1")).toBe(String(minuteToX(541, W, SPOT_WINDOW)));
    expect(container.querySelector('[data-testid="crosshair-h"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="time-tag-text"]')?.textContent).toBe("09:01");

    ({ container } = mount(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} syncHoverMin={600} />,
    ));
    expect(container.querySelector('[data-testid="crosshair-v"]')).toBeNull();

    ({ container } = mount(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} syncHoverMin={null} />,
    ));
    expect(container.querySelector('[data-testid="crosshair-v"]')).toBeNull();
  });

  it("自己的滑鼠 hover 優先於同步分鐘(y 跟滑鼠,不鎖收盤)", () => {
    const { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} syncHoverMin={541} />,
    );
    const svg = container.querySelector('svg[role="img"]')!;
    fireEvent.mouseMove(svg, { clientX: minuteToX(542, W, SPOT_WINDOW), clientY: 20 });
    expect(container.querySelector('[data-testid="crosshair-v"]')?.getAttribute("x1")).toBe(
      String(minuteToX(542, W, SPOT_WINDOW)),
    );
    expect(container.querySelector('[data-testid="crosshair-h"]')?.getAttribute("y1")).toBe("20");
    fireEvent.mouseLeave(svg);
    // 移出後退回同步分鐘(541),不是消失
    expect(container.querySelector('[data-testid="crosshair-v"]')?.getAttribute("x1")).toBe(
      String(minuteToX(541, W, SPOT_WINDOW)),
    );
  });

  it("onHoverMinute 只在分鐘變化時回呼;移出回呼 null", () => {
    const onHoverMinute = vi.fn();
    const { container } = wrap(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} onHoverMinute={onHoverMinute} />,
    );
    const svg = container.querySelector('svg[role="img"]')!;
    const x541 = minuteToX(541, W, SPOT_WINDOW);
    fireEvent.mouseMove(svg, { clientX: x541, clientY: 20 });
    fireEvent.mouseMove(svg, { clientX: x541 + 0.2, clientY: 40 }); // 同分鐘、不同 y → 不再回呼
    fireEvent.mouseMove(svg, { clientX: minuteToX(542, W, SPOT_WINDOW), clientY: 40 });
    fireEvent.mouseLeave(svg);
    expect(onHoverMinute.mock.calls).toEqual([[541], [542], [null]]);
  });

  it("onHoverMinute 換人(toggle 由關切回開)→ 同一分鐘也要再補發一次(review F-10)", () => {
    const first = vi.fn();
    const second = vi.fn();
    // RTL 的 rerender 會換掉整棵樹(含 wrap 的 QueryClientProvider)→ 用 wrapper 選項讓 provider 隨 rerender 保留
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Providers = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { container, rerender } = render(
      <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} onHoverMinute={first} />,
      { wrapper: Providers },
    );
    const svg = container.querySelector('svg[role="img"]')!;
    const x541 = minuteToX(541, W, SPOT_WINDOW);
    fireEvent.mouseMove(svg, { clientX: x541, clientY: 20 });
    expect(first.mock.calls).toEqual([[541]]);
    rerender(<IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="card" width={W} onHoverMinute={second} />);
    fireEvent.mouseMove(svg, { clientX: x541 + 0.2, clientY: 25 });
    expect(second.mock.calls).toEqual([[541]]);
  });
});
