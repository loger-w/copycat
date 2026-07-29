/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OrderBook } from "@/components/stock/OrderBook";

afterEach(cleanup);

const BOOK = {
  bids: [[2_380_000, 125], [2_375_000, 257]] as [number, number][],
  asks: [[2_385_000, 461], [2_390_000, 572]] as [number, number][],
};

describe("OrderBook", () => {
  it("渲染五檔價量(毫元 → 元)", () => {
    render(
      <OrderBook code="2330" book={BOOK} last={{ p: 2_380_000, t: "10:57:51.000", cum_vol: 1 }} ref_={2_320_000} />,
    );
    expect(screen.getByText("2385")).toBeTruthy();
    expect(screen.getByText("461")).toBeTruthy();
    expect(screen.getByText("2375")).toBeTruthy();
  });

  it("漲停鎖死空側顯示 —", () => {
    render(<OrderBook code="2330" book={{ bids: BOOK.bids, asks: [] }} last={null} ref_={null} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("點價 dispatch stock-price-click 帶 {priceMilli, side, code}(PriceLadder 置中接點)", () => {
    const details: unknown[] = [];
    const handler = (e: Event): void => {
      details.push((e as CustomEvent).detail);
    };
    window.addEventListener("stock-price-click", handler);
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    fireEvent.click(screen.getByText("2385"));
    fireEvent.click(screen.getByText("2375"));
    expect(details).toEqual([
      { priceMilli: 2_385_000, side: "ask", code: "2330" },
      { priceMilli: 2_375_000, side: "bid", code: "2330" },
    ]);
    window.removeEventListener("stock-price-click", handler);
  });

  it("總量列:委買/委賣五檔加總(SC-5)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    expect(screen.getByText(/委買 382/)).toBeTruthy();
    expect(screen.getByText(/委賣 1033/)).toBeTruthy();
  });

  // 🔴-2:直式改水平(SC-4)後 bar 由「左右生長」改為「格內高度」,原方向斷言已不適用。
  it("量 bar 改為格內高度、依最大量歸一(SC-4)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    // BOOK 最大量 = 賣2 的 572
    const maxCell = screen.getByRole("button", { name: "賣2 2390" });
    expect(maxCell.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height).toBe(
      "100%",
    );
    // 買1 = 125 / 572 ≈ 22%
    const bidCell = screen.getByRole("button", { name: "買1 2380" });
    expect(bidCell.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height).toBe(
      "22%",
    );
  });

  it("水平排列:買側由中央往左 買1→買5、賣側往右 賣1→賣5(SC-4)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    const labels = screen.getAllByRole("button").map((el) => el.getAttribute("aria-label"));
    expect(labels).toEqual(["買2 2375", "買1 2380", "賣1 2385", "賣2 2390"]);
  });

  it("買一 = 漲停 → 鎖漲停 badge;賣一 = 跌停 → 鎖跌停(SC-5)", () => {
    render(
      <OrderBook
        code="2330"
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
        code="2330"
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
      <OrderBook code="2330" book={BOOK} last={null} ref_={2_320_000} upper={2_552_000} lower={2_088_000} />,
    );
    expect(screen.queryByText("鎖漲停")).toBeNull();
    expect(screen.queryByText("鎖跌停")).toBeNull();
  });
});
