/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { IndexBar } from "@/components/IndexBar";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";

afterEach(cleanup);

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: {},
    ...over,
  };
}

const OTC = series({ p: 359_800, ref: 378_090 });
const TXF: TxfQuote = { p: 42_142_000, time: "10:16:10" };

describe("IndexBar(SC-1)", () => {
  it("三組:加權/櫃買 chg%、台指基差", () => {
    render(<IndexBar twse={series()} otc={OTC} txf={TXF} />);
    expect(screen.getByText(/加權/).textContent).toContain("42039.92");
    expect(screen.getByText(/加權/).textContent).toContain("-3.65%");
    expect(screen.getByText(/櫃買/).textContent).toContain("359.8");
    expect(screen.getByText(/櫃買/).textContent).toContain("-4.84%");
    // 基差 = 42142 - 42039.92 = +102.08 點
    expect(screen.getByText(/台指/).textContent).toContain("+102.08");
  });

  it("跌幅紅綠依台股慣例(跌 = bear 綠)", () => {
    render(<IndexBar twse={series()} otc={OTC} txf={TXF} />);
    const twse = screen.getByText(/加權/);
    expect(twse.innerHTML).toContain("text-bear");
  });

  it("stale → 加權值「-」且基差「-」(台指價照示)", () => {
    render(<IndexBar twse={series({ stale: true })} otc={OTC} txf={TXF} />);
    expect(screen.getByText(/加權/).textContent).toContain("-");
    expect(screen.getByText(/加權/).textContent).not.toContain("42039.92");
    const txf = screen.getByText(/台指/);
    expect(txf.textContent).toContain("42142");
    expect(txf.textContent).not.toContain("+102.08");
  });

  it("txf null → 台指組「-」;資料未達 → 全組「-」", () => {
    render(<IndexBar twse={null} otc={null} txf={null} />);
    expect(screen.getByText(/加權/).textContent).toContain("-");
    expect(screen.getByText(/櫃買/).textContent).toContain("-");
    expect(screen.getByText(/台指/).textContent).toContain("-");
  });

  it("txf null 但 twse 有值 → 台指組「-」、加權照示(review B3 組合)", () => {
    render(<IndexBar twse={series()} otc={OTC} txf={null} />);
    expect(screen.getByText(/加權/).textContent).toContain("42039.92");
    const txf = screen.getByText(/台指/);
    expect(txf.textContent).toContain("-");
    expect(txf.textContent).not.toContain("42142");
  });
});
