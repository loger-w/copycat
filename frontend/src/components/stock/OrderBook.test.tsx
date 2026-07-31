/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OrderBook } from "@/components/stock/OrderBook";

afterEach(cleanup);

const BOOK = {
  bids: [[2_380_000, 125], [2_375_000, 257]] as [number, number][],
  asks: [[2_385_000, 461], [2_390_000, 572]] as [number, number][],
};

/** 2026-07-31 盤中實測 2327 國巨(鎖漲停 502)的簿:第一檔是 15966 張市價買單,價格欄 0 */
const LOCK_UP_BOOK = {
  bids: [[0, 15_966], [502_000, 9_385], [501_000, 41]] as [number, number][],
  asks: [] as [number, number][],
};

describe("OrderBook 市價單檔位(round6 項 4)", () => {
  it("價格 0 的檔位顯示「市價」而不是 0", () => {
    render(
      <OrderBook
        code="2327"
        book={LOCK_UP_BOOK}
        last={{ p: 502_000, t: "11:58:39.000", cum_vol: 5448 }}
        ref_={456_500}
        upper={502_000}
        lower={411_000}
      />,
    );
    expect(screen.getByText("市價")).toBeTruthy();
    expect(screen.getByText("15966")).toBeTruthy();
    // 「0」不得出現在**價格欄**。不能用 queryByText("0") 全域找 ——
    // 委賣側掛空時總量列本來就是 0,那是對的。
    const row = screen.getByLabelText("買1 市價");
    expect(row.textContent).toContain("市價");
    expect(row.textContent).not.toContain("0 ");
    expect(row.querySelector("span:last-of-type")!.textContent).toBe("市價");
  });

  it("市價列不可點(不發 stock-price-click)", () => {
    const details: unknown[] = [];
    const handler = (e: Event): void => void details.push((e as CustomEvent).detail);
    window.addEventListener("stock-price-click", handler);
    render(
      <OrderBook code="2327" book={LOCK_UP_BOOK} last={null} ref_={456_500} upper={502_000} />,
    );
    fireEvent.click(screen.getByText("市價"));
    // 一般檔位照樣可點(對照組)
    fireEvent.click(screen.getByText("501"));
    window.removeEventListener("stock-price-click", handler);
    expect(details).toEqual([{ priceMilli: 501_000, side: "bid", code: "2327" }]);
  });

  it("aria-label 用「市價」不用 0", () => {
    render(
      <OrderBook code="2327" book={LOCK_UP_BOOK} last={null} ref_={456_500} upper={502_000} />,
    );
    expect(screen.queryByLabelText("買1 0")).toBeNull();
  });

  it("鎖漲停 badge 不再被市價偽檔位打穿(bids[0] 是 0 而非漲停價)", () => {
    render(
      <OrderBook
        code="2327"
        book={LOCK_UP_BOOK}
        last={{ p: 502_000, t: "11:58:39.000", cum_vol: 5448 }}
        ref_={456_500}
        upper={502_000}
        lower={411_000}
      />,
    );
    expect(screen.getByText("鎖漲停")).toBeTruthy();
  });

  it("鎖跌停對稱:市價賣單在 asks[0]", () => {
    render(
      <OrderBook
        code="2327"
        book={{ bids: [], asks: [[0, 20_000], [411_000, 5_000]] }}
        last={{ p: 411_000, t: "10:00:00.000", cum_vol: 100 }}
        ref_={456_500}
        upper={502_000}
        lower={411_000}
      />,
    );
    expect(screen.getByText("市價")).toBeTruthy();
    expect(screen.getByText("鎖跌停")).toBeTruthy();
  });
});

describe("OrderBook 漲跌停亮燈(round6 項 3)", () => {
  it("漲停時標題列成交價區塊紅底白字", () => {
    render(
      <OrderBook
        code="2327"
        book={LOCK_UP_BOOK}
        last={{ p: 502_000, t: "11:58:39.000", cum_vol: 5448 }}
        ref_={456_500}
        upper={502_000}
        lower={411_000}
      />,
    );
    const cls = screen.getByTestId("depth-quote").className;
    expect(cls).toContain("bg-bull");
    expect(cls).toContain("text-white");
  });

  it("跌停時綠底白字", () => {
    render(
      <OrderBook
        code="2327"
        book={{ bids: [], asks: [[411_000, 5_000]] }}
        last={{ p: 411_000, t: "10:00:00.000", cum_vol: 100 }}
        ref_={456_500}
        upper={502_000}
        lower={411_000}
      />,
    );
    const cls = screen.getByTestId("depth-quote").className;
    expect(cls).toContain("bg-bear");
    expect(cls).toContain("text-white");
  });

  it("未漲跌停時不亮燈(SC-3.4)", () => {
    render(
      <OrderBook
        code="2330"
        book={BOOK}
        last={{ p: 2_380_000, t: "10:57:51.000", cum_vol: 1 }}
        ref_={2_320_000}
        upper={2_550_000}
        lower={2_090_000}
      />,
    );
    const cls = screen.getByTestId("depth-quote").className;
    expect(cls).not.toContain("bg-bull");
    expect(cls).not.toContain("bg-bear");
    expect(cls).not.toContain("text-white");
  });

  it("upper/lower 為 null(無漲跌幅商品)不亮燈", () => {
    render(
      <OrderBook
        code="2330"
        book={BOOK}
        last={{ p: 2_380_000, t: "10:57:51.000", cum_vol: 1 }}
        ref_={2_320_000}
      />,
    );
    expect(screen.getByTestId("depth-quote").className).not.toContain("text-white");
  });
});

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

  // 🔴-1:垂直雙欄(SC-1)後總量列改成「<千分位數字> 張」大字,不再有「委買 / 委賣」前綴。
  // 「張」依 SC-1 是獨立小字 span,而 RTL 的 getNodeText 只取**直接** text node
  // (element 子節點不算)→ getByText 不可能一次匹配「382張」。改以 testid 取整段
  // textContent 斷言,數值 / 千分位 / 單位三者仍全鎖(review R16 的精確版)。
  it("總量列:買賣五檔加總 + 張 + 千分位(SC-1)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    expect(screen.getByTestId("depth-total-bid").textContent).toBe("382張");
    expect(screen.getByTestId("depth-total-ask").textContent).toBe("1,033張");
  });

  // 🔴-2:水平 10 格改垂直雙欄(SC-1)後,量 bar 由「格內垂直高度」改為「列背景水平寬度」。
  it("量 bar 改為列背景寬度、依買賣共用最大量歸一(SC-1)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    // BOOK 最大量 = 賣2 的 572
    const maxCell = screen.getByRole("button", { name: "賣2 2390" });
    expect(maxCell.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.width).toBe(
      "100%",
    );
    // 買1 = 125 / 572 ≈ 22%
    const bidCell = screen.getByRole("button", { name: "買1 2380" });
    expect(bidCell.querySelector<HTMLElement>("[data-testid='depth-vol-bar']")?.style.width).toBe(
      "22%",
    );
  });

  // 🔴-3:買側 bar 由列右緣往左長、賣側由左緣往右長(SC-1)
  it("量 bar 方向:買側靠右、賣側靠左(SC-1)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    const bid = screen.getByRole("button", { name: "買1 2380" });
    const ask = screen.getByRole("button", { name: "賣1 2385" });
    expect(bid.querySelector("[data-testid='depth-vol-bar']")?.className).toContain("right-0");
    expect(ask.querySelector("[data-testid='depth-vol-bar']")?.className).toContain("left-0");
  });

  // 🔴-4:垂直雙欄 = 左欄買1→買5 由上而下、右欄賣1→賣5 由上而下(原水平版是買5..買1|賣1..賣5)
  it("垂直雙欄排列:左欄 買1→買5、右欄 賣1→賣5(SC-1)", () => {
    render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    const labels = screen.getAllByRole("button").map((el) => el.getAttribute("aria-label"));
    expect(labels).toEqual(["買1 2380", "買2 2375", "賣1 2385", "賣2 2390"]);
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

  // 🟢 SC-1:badge 位置由中央成交價格移到標題列(既有的文字斷言與位置無關,故另立一條)
  it("鎖停 badge 出現在標題列容器內(SC-1)", () => {
    render(
      <OrderBook
        code="2330"
        book={{ bids: [[2_552_000, 999]], asks: [] }}
        last={{ p: 2_552_000, t: "09:10:00.000", cum_vol: 1 }}
        ref_={2_320_000}
        upper={2_552_000}
      />,
    );
    const head = screen.getByTestId("depth-head");
    expect(within(head).getByText("鎖漲停")).toBeTruthy();
  });

  // 🟢 SC-1:標題列右側成交價 + 漲跌%(auto-default:五檔區自足,不必回頭看頁面 header)
  it("標題列右側顯示成交價 + 漲跌%(SC-1)", () => {
    render(
      <OrderBook code="2330" book={BOOK} last={{ p: 2_380_000, t: "10:57:51.000", cum_vol: 1 }} ref_={2_320_000} />,
    );
    const head = screen.getByTestId("depth-head");
    expect(within(head).getByText("2380")).toBeTruthy();
    // (2380000 - 2320000) / 2320000 = +2.586%
    expect(within(head).getByText("+2.59%")).toBeTruthy();
  });

  // 🟢 self-review C1:標題列漲跌色的三個分支只有「漲」被 render 過,且沒有一條測試讀
  // className —— 把 bull/bear 寫反(台股紅漲綠跌與美股相反,是最容易寫反的方向)測試照樣全綠。
  it("標題列漲跌色:漲紅 / 跌綠 / 平盤中性(SC-1)", () => {
    const { rerender } = render(
      <OrderBook code="2330" book={BOOK} last={{ p: 2_380_000, t: "t", cum_vol: 1 }} ref_={2_320_000} />,
    );
    // 精確 testid:平盤時 /^\d/ 會同時撞到價格「2320」與百分比「0.00%」(selector 過鬆)
    const price = () => screen.getByTestId("depth-last");
    expect(price().className).toContain("text-bull");
    expect(within(screen.getByTestId("depth-head")).getByText("+2.59%").className).toContain("text-bull");

    rerender(
      <OrderBook code="2330" book={BOOK} last={{ p: 2_300_000, t: "t", cum_vol: 1 }} ref_={2_320_000} />,
    );
    expect(price().className).toContain("text-bear");
    expect(within(screen.getByTestId("depth-head")).getByText("-0.86%").className).toContain("text-bear");

    rerender(
      <OrderBook code="2330" book={BOOK} last={{ p: 2_320_000, t: "t", cum_vol: 1 }} ref_={2_320_000} />,
    );
    expect(price().className).toContain("text-ink");
    expect(price().className).not.toContain("text-bull");
    expect(price().className).not.toContain("text-bear");
  });

  // 🟢 review R7:重寫時最容易掉的除零保護(DepthBar.tsx:78 的 Math.max(1, ...))
  it("book=null 與五檔全 0 量:不崩、bar 寬不出現 NaN", () => {
    const { container, rerender } = render(
      <OrderBook code="2330" book={null} last={null} ref_={null} />,
    );
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    rerender(
      <OrderBook
        code="2330"
        book={{ bids: [[2_380_000, 0]], asks: [[2_385_000, 0]] }}
        last={null}
        ref_={null}
      />,
    );
    const bars = container.querySelectorAll<HTMLElement>("[data-testid='depth-vol-bar']");
    expect(bars.length).toBeGreaterThan(0);
    bars.forEach((b) => expect(b.style.width.includes("NaN")).toBe(false));
  });

  // 🟢 review R15:本元件的 last 是物件({p,t,cum_vol} | null),與 DepthBar 收 number 不同
  it("last=null / ref_=null:成交價顯示 —、不出現 NaN%", () => {
    const { container } = render(<OrderBook code="2330" book={BOOK} last={null} ref_={null} />);
    const head = screen.getByTestId("depth-head");
    expect(within(head).getByText("—")).toBeTruthy();
    expect(container.textContent?.includes("NaN")).toBe(false);
  });
});
