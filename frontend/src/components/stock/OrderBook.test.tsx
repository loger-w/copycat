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
});
