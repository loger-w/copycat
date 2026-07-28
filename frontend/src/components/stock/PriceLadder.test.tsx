/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PriceLadder } from "@/components/stock/PriceLadder";

const META = {
  name: "測試",
  ref: 100_000,
  upper: 110_000,
  lower: 90_000,
  y_close: 100_000,
  y_vol: 10,
};

const BOOK = {
  bids: [[100_000, 30]] as [number, number][],
  asks: [[100_500, 10]] as [number, number][],
};

const LAST = { p: 100_000, t: "09:10:00.000", cum_vol: 5 };

beforeEach(() => {
  window.localStorage.removeItem("stock-ladder-open");
  // jsdom 無 scrollIntoView(跟隨置中 spy stub)
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PriceLadder", () => {
  it("預設收合:只有「閃電梯」鈕;點擊展開出現價格列(SC-7)", () => {
    render(<PriceLadder book={BOOK} last={LAST} meta={META} />);
    expect(screen.queryByText("110")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
    expect(screen.getByText("110")).toBeTruthy(); // 漲停端點
    expect(screen.getByText("90")).toBeTruthy(); // 跌停端點
  });

  it("五檔量對映顯示於對應價位列", () => {
    render(<PriceLadder book={BOOK} last={LAST} meta={META} />);
    fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
    expect(screen.getByText("30")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();
  });

  it("±5% 外價位反灰不可點、域內點價發 stock-price-click(SC-7)", () => {
    const handler = vi.fn();
    window.addEventListener("stock-price-click", handler);
    render(<PriceLadder book={BOOK} last={LAST} meta={META} />);
    fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
    const far = screen.getByText("110").closest("button")!;
    expect(far.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByText("100.5"));
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener("stock-price-click", handler);
  });

  it("跟隨置中預設開,center 變更觸發 scrollIntoView", () => {
    const { rerender } = render(<PriceLadder book={BOOK} last={LAST} meta={META} />);
    fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("true");
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(<PriceLadder book={BOOK} last={{ ...LAST, p: 101_000 }} meta={META} />);
    expect(spy).toHaveBeenCalled();
  });

  it("無 ref 與 last → 顯示「無資料」(edge 6)", () => {
    render(
      <PriceLadder book={null} last={null} meta={{ ...META, ref: null, upper: null, lower: null }} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
    expect(screen.getByText("無資料")).toBeTruthy();
  });
});
