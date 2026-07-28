/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderBook } from "@/components/stock/OrderBook";

afterEach(cleanup);

const BOOK = {
  bids: [[2_380_000, 125], [2_375_000, 257]] as [number, number][],
  asks: [[2_385_000, 461], [2_390_000, 572]] as [number, number][],
};

describe("OrderBook", () => {
  it("渲染五檔價量(毫元 → 元)", () => {
    render(<OrderBook book={BOOK} last={{ p: 2_380_000, t: "10:57:51.000", cum_vol: 1 }} ref_={2_320_000} />);
    expect(screen.getByText("2385")).toBeTruthy();
    expect(screen.getByText("461")).toBeTruthy();
    expect(screen.getByText("2375")).toBeTruthy();
  });

  it("漲停鎖死空側顯示 —", () => {
    render(<OrderBook book={{ bids: BOOK.bids, asks: [] }} last={null} ref_={null} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("點價 dispatch stock-price-click(下一輪下單匣接點)", () => {
    const handler = vi.fn();
    window.addEventListener("stock-price-click", handler);
    render(<OrderBook book={BOOK} last={null} ref_={null} />);
    fireEvent.click(screen.getByText("2385"));
    expect(handler).toHaveBeenCalled();
    window.removeEventListener("stock-price-click", handler);
  });

  it("總量列:委買/委賣五檔加總(SC-5)", () => {
    render(<OrderBook book={BOOK} last={null} ref_={null} />);
    expect(screen.getByText(/委買 382/)).toBeTruthy();
    expect(screen.getByText(/委賣 1033/)).toBeTruthy();
  });

  it("量 bar 方向:買側靠右往左長、賣側靠左往右長(SC-5)", () => {
    const { container } = render(<OrderBook book={BOOK} last={null} ref_={null} />);
    const bullBar = container.querySelector('span[class*="bg-bull"]')!;
    const bearBar = container.querySelector('span[class*="bg-bear"]')!;
    expect(bullBar.className).toContain("right-0");
    expect(bearBar.className).toContain("left-0");
  });

  it("買一 = 漲停 → 鎖漲停 badge;賣一 = 跌停 → 鎖跌停(SC-5)", () => {
    render(
      <OrderBook
        book={{ bids: [[2_552_000, 999]], asks: [] }}
        last={{ p: 2_552_000, t: "09:10:00.000", cum_vol: 1 }}
        ref_={2_320_000}
        upper={2_552_000}
        lower={2_088_000}
      />,
    );
    expect(screen.getByText("鎖漲停")).toBeTruthy();
    expect(screen.queryByText("鎖跌停")).toBeNull();
    cleanup();
    render(
      <OrderBook
        book={{ bids: [], asks: [[2_088_000, 999]] }}
        last={null}
        ref_={2_320_000}
        upper={2_552_000}
        lower={2_088_000}
      />,
    );
    expect(screen.getByText("鎖跌停")).toBeTruthy();
  });

  it("無鎖停時不顯示 badge", () => {
    render(
      <OrderBook book={BOOK} last={null} ref_={2_320_000} upper={2_552_000} lower={2_088_000} />,
    );
    expect(screen.queryByText("鎖漲停")).toBeNull();
    expect(screen.queryByText("鎖跌停")).toBeNull();
  });
});
