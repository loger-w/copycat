/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { fromSnapshot } from "@/lib/stock-accum";

afterEach(cleanup);

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  cum_inner: 2,
  cum_outer: 10,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
});

describe("StockIntradayChart", () => {
  it("渲染價線/VWAP/內外盤副圖", () => {
    const { container } = render(<StockIntradayChart accum={ACCUM} />);
    const polylines = container.querySelectorAll("polyline");
    expect(polylines.length).toBeGreaterThanOrEqual(2); // 價線 + VWAP
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/累積外盤/)).toBeTruthy();
  });

  it("無分鐘資料顯示等待提示", () => {
    const empty = fromSnapshot({
      code: "2330", seq: 0, last: null, vwap: null, cum_inner: 0, cum_outer: 0,
      minutes: {}, ticks: [], book: null, meta: null,
    });
    render(<StockIntradayChart accum={empty} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });
});
