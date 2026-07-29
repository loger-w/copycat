/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DepthBar } from "@/components/quote/DepthBar";

afterEach(cleanup);

// 買側最佳在前(bids[0] = 買1);賣側最佳在前(asks[0] = 賣1)
const BIDS: [number, number][] = [
  [582_000, 12],
  [581_000, 32],
  [580_000, 15],
  [579_000, 8],
  [578_000, 21],
];
const ASKS: [number, number][] = [
  [583_000, 5],
  [584_000, 18],
  [585_000, 9],
  [586_000, 24],
  [587_000, 7],
];

function renderBar(over: Partial<Parameters<typeof DepthBar>[0]> = {}) {
  return render(
    <DepthBar
      bids={BIDS}
      asks={ASKS}
      last={583_000}
      ref_={571_000}
      onPriceClick={() => {}}
      {...over}
    />,
  );
}

describe("DepthBar 水平五檔(SC-4)", () => {
  it("買側由中央往左 買1→買5、賣側由中央往右 賣1→賣5(DOM 由左至右 = 買5..買1, 賣1..賣5)", () => {
    renderBar();
    const cells = screen
      .getAllByRole("button")
      .map((el) => el.getAttribute("aria-label"));
    expect(cells).toEqual([
      "買5 578",
      "買4 579",
      "買3 580",
      "買2 581",
      "買1 582",
      "賣1 583",
      "賣2 584",
      "賣3 585",
      "賣4 586",
      "賣5 587",
    ]);
  });

  it("每格價量疊放:同一格內同時有量與價", () => {
    renderBar();
    const best = screen.getByRole("button", { name: "買1 582" });
    expect(best.textContent).toContain("12");
    expect(best.textContent).toContain("582");
  });

  it("買側 text-bull、賣側 text-bear(台股紅漲綠跌)", () => {
    renderBar();
    expect(screen.getByRole("button", { name: "買1 582" }).className).toContain("text-bull");
    expect(screen.getByRole("button", { name: "賣1 583" }).className).toContain("text-bear");
  });

  it("表頭顯示委買 / 委賣總量", () => {
    renderBar();
    expect(screen.getByText(/委買/).textContent).toContain("88"); // 12+32+15+8+21
    expect(screen.getByText(/委賣/).textContent).toContain("63"); // 5+18+9+24+7
  });

  it("中央顯示成交價與漲跌%", () => {
    renderBar();
    const center = screen.getByLabelText("成交價");
    expect(center.textContent).toContain("583");
    expect(center.textContent).toContain("+2.10%"); // (583000-571000)/571000
  });

  it("量 bar 高度按最大量歸一(最大量該格 100%)", () => {
    renderBar();
    const bars = screen.getAllByTestId("depth-vol-bar");
    const max = screen.getByRole("button", { name: "買2 581" }); // qty 32 = 最大
    expect(max.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height).toBe(
      "100%",
    );
    expect(bars.length).toBe(10);
  });

  it("點價回呼帶毫元價與買賣側", () => {
    const onPriceClick = vi.fn();
    renderBar({ onPriceClick });
    fireEvent.click(screen.getByRole("button", { name: "賣1 583" }));
    expect(onPriceClick).toHaveBeenCalledWith(583_000, "ask");
    fireEvent.click(screen.getByRole("button", { name: "買1 582" }));
    expect(onPriceClick).toHaveBeenCalledWith(582_000, "bid");
  });

  it("未給 onPriceClick(期貨頁)→ 不渲染成 button,避免可聚焦卻點了沒反應(review P2-9)", () => {
    render(<DepthBar bids={BIDS} asks={ASKS} last={583_000} ref_={571_000} />);
    expect(screen.queryAllByRole("button").length).toBe(0);
    // 價量仍照常顯示且可被 aria-label 指認
    expect(screen.getByLabelText("買1 582").textContent).toContain("12");
    expect(screen.getByLabelText("賣1 583").textContent).toContain("583");
  });

  it("鎖漲停:買1 = 漲停價時顯示 badge", () => {
    renderBar({ upper: 582_000 });
    expect(screen.getByText("鎖漲停")).toBeTruthy();
    expect(screen.queryByText("鎖跌停")).toBeNull();
  });

  it("鎖跌停:賣1 = 跌停價時顯示 badge", () => {
    renderBar({ lower: 583_000 });
    expect(screen.getByText("鎖跌停")).toBeTruthy();
  });

  it("檔位不足時補空格(—),不塌陷欄位", () => {
    renderBar({ bids: [[582_000, 12]], asks: [] });
    expect(screen.getAllByRole("button").length).toBe(1); // 只有買1 有資料
    expect(screen.getAllByText("—").length).toBe(9); // 其餘 9 格空
  });

  it("last 為 null 時中央顯示 —,不崩", () => {
    renderBar({ last: null });
    expect(screen.getByLabelText("成交價").textContent).toContain("—");
  });
});
