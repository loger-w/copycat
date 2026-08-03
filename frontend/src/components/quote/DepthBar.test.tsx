/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
  return render(<DepthBar bids={BIDS} asks={ASKS} last={583_000} ref_={571_000} {...over} />);
}

/** 有資料的格子(空格補「—」不掛 aria-label);回傳序為 DOM 序 */
const cells = () => screen.getAllByLabelText(/^[買賣]\d /);

describe("DepthBar 水平五檔(SC-4)", () => {
  it("買側由中央往左 買1→買5、賣側由中央往右 賣1→賣5(DOM 由左至右 = 買5..買1, 賣1..賣5)", () => {
    renderBar();
    expect(cells().map((el) => el.getAttribute("aria-label"))).toEqual([
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
    const best = screen.getByLabelText("買1 582");
    expect(best.textContent).toContain("12");
    expect(best.textContent).toContain("582");
  });

  it("買側 text-bull、賣側 text-bear(台股紅漲綠跌)", () => {
    renderBar();
    expect(screen.getByLabelText("買1 582").className).toContain("text-bull");
    expect(screen.getByLabelText("賣1 583").className).toContain("text-bear");
  });

  it("表頭顯示委買 / 委賣總量", () => {
    renderBar();
    // 精確比對(TQ-2):`toContain` 對「多一位數」的錯值照樣綠(如 188 / 880),
    // 而總量算錯的典型樣態正是多算了一筆量 —— 子字串收不住它
    expect(screen.getByText(/委買/).textContent).toBe("委買 88"); // 12+32+15+8+21
    expect(screen.getByText(/委賣/).textContent).toBe("委賣 63"); // 5+18+9+24+7
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
    const max = screen.getByLabelText("買2 581"); // qty 32 = 最大
    expect(max.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height).toBe(
      "100%",
    );
    expect(bars.length).toBe(10);
  });

  it("格子不渲染成 button,避免可聚焦卻點了沒反應(review P2-9)", () => {
    renderBar();
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
    expect(cells().length).toBe(1); // 只有買1 有資料
    expect(screen.getAllByText("—").length).toBe(9); // 其餘 9 格空
  });

  it("last 為 null 時中央顯示 —,不崩", () => {
    renderBar({ last: null });
    expect(screen.getByLabelText("成交價").textContent).toContain("—");
  });
});

// 🔴 M6:鎖漲跌停時 TC4 會在簿的第一檔推「市價單佇列」,價格欄是 0
// (CLAUDE.md §8「第四處」;OrderBook 已全套修過,本檔沿用同一套規則)
describe("DepthBar 市價 0 價檔位(M6)", () => {
  const LOCK_BIDS: [number, number][] = [
    [0, 200], // 市價佇列(量可以是限價量的數倍)
    [582_000, 12],
    [581_000, 32],
    [580_000, 15],
    [579_000, 8],
  ];
  const LOCK_ASKS: [number, number][] = [
    [0, 90],
    [583_000, 5],
    [584_000, 18],
    [585_000, 9],
    [586_000, 24],
  ];

  it("鎖漲停 badge:比對第一個限價檔而不是 bids[0](市價佇列不得打穿判定)", () => {
    renderBar({ bids: LOCK_BIDS, upper: 582_000 });
    expect(screen.getByText("鎖漲停")).toBeTruthy();
  });

  it("鎖跌停 badge:賣側對稱", () => {
    renderBar({ asks: LOCK_ASKS, lower: 583_000 });
    expect(screen.getByText("鎖跌停")).toBeTruthy();
  });

  it("總量只算限價檔(定義不隨鎖停日改變,可跨日跨股比)", () => {
    renderBar({ bids: LOCK_BIDS, asks: LOCK_ASKS });
    // 精確比對(TQ-2):市價量若混進來,委買會變成 267 —— `toContain("67")` 對它照樣綠
    expect(screen.getByText(/委買/).textContent).toBe("委買 67"); // 12+32+15+8,不含市價 200
    expect(screen.getByText(/委賣/).textContent).toBe("委賣 56"); // 5+18+9+24,不含市價 90
  });

  it("漲停價出現在非最佳限價檔 → 不亮 badge(判定看最佳限價檔,TQ-5)", () => {
    // 刻意畸形 / 過期的簿(well-formed 簿的 bids 遞減,不會有比漲停價更高的買檔)——
    // 鎖的是**判定語意**:badge 的意思是「最佳限價檔就掛在漲停價」,不是「簿裡任何
    // 一檔碰到漲停價」。用 `some` 的話這種簿會過度觸發。
    renderBar({ bids: [[0, 200], [583_000, 10], [582_000, 12]], upper: 582_000 });
    expect(screen.queryByText("鎖漲停")).toBeNull();
  });

  it("跌停價出現在非最佳限價檔 → 不亮 badge(賣側對稱)", () => {
    renderBar({ asks: [[0, 90], [582_000, 10], [583_000, 5]], lower: 583_000 });
    expect(screen.queryByText("鎖跌停")).toBeNull();
  });

  it("upper 為 0(meta 缺值)+ 市價偽檔位 → 不得誤亮 badge", () => {
    renderBar({ bids: LOCK_BIDS, asks: LOCK_ASKS, upper: 0, lower: 0 });
    expect(screen.queryByText("鎖漲停")).toBeNull();
    expect(screen.queryByText("鎖跌停")).toBeNull();
  });

  it("0 價檔位顯示「市價」不印 0,量照列", () => {
    renderBar({ bids: LOCK_BIDS });
    const cell = screen.getByLabelText("買1 市價");
    expect(cell.textContent).toContain("市價");
    expect(cell.textContent).toContain("200");
    expect(screen.queryByLabelText("買1 0")).toBeNull();
  });

  it("量 bar 歸一只看限價檔,市價列自己的 bar 夾制在 100%", () => {
    renderBar({ bids: LOCK_BIDS, asks: LOCK_ASKS });
    // 限價最大量 = 32(買3 581,市價佔掉買1 這格),不是市價的 200
    const limitMax = screen.getByLabelText("買3 581");
    expect(
      limitMax.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height,
    ).toBe("100%");
    const market = screen.getByLabelText("買1 市價");
    expect(market.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.height).toBe(
      "100%",
    );
  });
});
