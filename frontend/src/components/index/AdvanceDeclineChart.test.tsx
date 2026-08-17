/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdvanceDeclineChart } from "@/components/index/AdvanceDeclineChart";
import type { BreadthBuckets, BreadthPoint } from "@/types";

/** 桶序固定 `[limit_up, up, flat, down, limit_down]`(types.ts 契約)。 */
function pt(t: string, twse: BreadthBuckets, tpex: BreadthBuckets): BreadthPoint {
  return { t, twse, tpex };
}

/** 線拆成 0 軸上下兩段後,**兩段的 points 完全相同**(可見範圍由 clip 決定,不是各畫
 *  一半)—— 幾何類斷言一律錨 `adl-line-up`,兩段都查等於同一件事驗兩次。 */
function pointCount(): number {
  const line = screen.getByTestId("adl-line-up");
  const raw = (line.getAttribute("points") ?? "").trim();
  return raw === "" ? 0 : raw.split(/\s+/).length;
}

afterEach(() => {
  cleanup();
  // ResizeObserver 只在量測那一組測試裡 stub —— 其餘測試要留在「jsdom 沒有 RO」的
  // fallback 語意下(W-10),不還原會讓後面的檔案跟著漂。
  vi.unstubAllGlobals();
});

describe("AdvanceDeclineChart net 計算(SC-4)", () => {
  it("(a) net = (漲停+上漲) − (下跌+跌停),上市 + 上櫃合計", () => {
    // twse: (1+10) − (4+0) = 7;tpex: (0+2) − (1+1) = 0 → 合計 +7
    render(
      <AdvanceDeclineChart series={[pt("0930", [1, 10, 5, 4, 0], [0, 2, 1, 1, 1])]} />,
    );
    expect(screen.getByTestId("adl-last").textContent).toContain("+7");
  });

  // SVG `<text>` 的字色走 `fill-*`(`text-*` 在 SVG 是 no-op;MarketChart 同慣例),
  // 語意仍是 bull/bear 兩顆 token。
  it("(b) net 為負 → 末值染 bear;為正 → bull", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 1, 0, 20, 3], [0, 0, 0, 0, 0])]} />);
    const neg = screen.getByTestId("adl-last");
    expect(neg.textContent).toContain("-22");
    expect(neg.getAttribute("class")).toContain("fill-bear");
    cleanup();
    render(<AdvanceDeclineChart series={[pt("0930", [2, 30, 0, 1, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-last").getAttribute("class")).toContain("fill-bull");
  });

  it("(c) 只標右端末值,不逐點標數字", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1000", [0, 20, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1030", [0, 33, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(screen.getAllByTestId("adl-last").length).toBe(1);
    expect(screen.getByTestId("adl-last").textContent).toContain("+33");
    expect(screen.queryByText(/^\+10$/)).toBeNull();
  });
});

describe("AdvanceDeclineChart 域與防禦(SC-4)", () => {
  it("(d) 域外 / 非法分鐘鍵不產生點(1430 盤後、abcd 非數字、0860 非法分)", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1430", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("abcd", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("0860", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("0800", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(pointCount()).toBe(1);
    // 末值取的是「有效點」的最後一格,不是陣列末項
    expect(screen.getByTestId("adl-last").textContent).toContain("+10");
  });

  it("(e) 域邊界 0901 與 1330 都算有效點", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0901", [0, 1, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1330", [0, 2, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(pointCount()).toBe(2);
  });

  it("(f) x 是固定域不隨資料伸縮:同一分鐘鍵在不同 series 下 x 相同", () => {
    render(<AdvanceDeclineChart series={[pt("1000", [0, 5, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    const solo = (screen.getByTestId("adl-line-up").getAttribute("points") ?? "").split(",")[0];
    cleanup();
    render(
      <AdvanceDeclineChart
        series={[
          pt("0910", [0, 1, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1000", [0, 5, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1300", [0, 9, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    const many = (screen.getByTestId("adl-line-up").getAttribute("points") ?? "").split(/\s+/)[1];
    expect(many?.split(",")[0]).toBe(solo);
  });

  it("(g) 0 軸恆可見", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-zero")).toBeTruthy();
  });

  // 兩段線都要斷:只查舊的單一 `adl-line` 在改名後恆為 null,測試會靜默轉 vacuous
  // (實作把線畫出來了照樣綠)。
  it("(h) 空 series → 佔位文字、無折線", () => {
    render(<AdvanceDeclineChart series={[]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line-up")).toBeNull();
    expect(screen.queryByTestId("adl-line-down")).toBeNull();
  });

  it("(i) 全部域外 → 同樣走佔位(沒有可畫的點)", () => {
    render(<AdvanceDeclineChart series={[pt("1430", [0, 9, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line-up")).toBeNull();
    expect(screen.queryByTestId("adl-line-down")).toBeNull();
  });

  it("(j) 單序列不放 legend(標題即名)", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("騰落線");
    expect(screen.queryByTestId("adl-legend")).toBeNull();
  });
});

// 分時圖(StockIntradayChart)同款手法:一條完整的線 / 一塊完整的面積各畫兩份,可見
// 範圍交給 0 軸上下兩個 clipPath 決定。**兩份恆 render** —— 依 net 正負條件 render 的話,
// 全紅那天的 `adl-line-down` 會消失,錨點隨資料時有時無。
describe("AdvanceDeclineChart 紅綠雙色(SC-6)", () => {
  const MIXED = [
    pt("0930", [0, 30, 0, 1, 0], [0, 0, 0, 0, 0]), // net +29
    pt("1000", [0, 1, 0, 40, 0], [0, 0, 0, 0, 0]), // net −39
  ];

  it("(k) 線拆兩段:上段 stroke-bull / 下段 stroke-bear,各自 clip 到 defs 內同 id", () => {
    const { container } = render(<AdvanceDeclineChart series={MIXED} />);
    const up = screen.getByTestId("adl-line-up");
    const down = screen.getByTestId("adl-line-down");
    expect(up.getAttribute("class")).toContain("stroke-bull");
    expect(down.getAttribute("class")).toContain("stroke-bear");
    // 單色 accent 線已退役:留著等於改壞雙色時仍有一條線在,零錯誤訊號
    expect(container.querySelector(".stroke-accent")).toBeNull();

    const clips = [...container.querySelectorAll("clipPath")];
    expect(clips.length).toBe(2);
    for (const clip of clips) {
      const id = clip.getAttribute("id")!;
      // url(#…) 解析失敗在 SVG 規範下是「該元素不繪製」,完全靜默 → id 字元集要鎖
      expect(id).toMatch(/^[A-Za-z0-9_-]+$/);
    }
    const [above, below] = clips.map((c) => c.getAttribute("id")!);
    expect(above!.endsWith("-above")).toBe(true);
    expect(below!.endsWith("-below")).toBe(true);
    expect(up.getAttribute("clip-path")).toBe(`url(#${above})`);
    expect(down.getAttribute("clip-path")).toBe(`url(#${below})`);
  });

  it("(l) 面積同樣兩段:fill-bull / fill-bear,半透明 0.15", () => {
    render(<AdvanceDeclineChart series={MIXED} />);
    const upArea = screen.getByTestId("adl-area-up");
    const downArea = screen.getByTestId("adl-area-down");
    expect(upArea.getAttribute("class")).toContain("fill-bull");
    expect(downArea.getAttribute("class")).toContain("fill-bear");
    expect(upArea.getAttribute("fill-opacity")).toBe("0.15");
    expect(downArea.getAttribute("fill-opacity")).toBe("0.15");
  });

  it("(k2) 全正 / 全負也照畫兩段(錨點不隨資料正負消失)", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 30, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-line-up")).toBeTruthy();
    expect(screen.getByTestId("adl-line-down")).toBeTruthy();
    expect(screen.getByTestId("adl-area-up")).toBeTruthy();
    expect(screen.getByTestId("adl-area-down")).toBeTruthy();
  });
});

/** 🔒 lock(review TD-6):「量測 → viewBox 高」這條路整條沒有測試 —— 改版前是「寬決定
 *  高」(寬 × 150/640),左欄 930px 時這條線獨佔 218px,一頁總覽的高度預算吃不下。
 *  現在高度由 CSS 固定(`h-24`)、viewBox 高反推自實際長寬比;算式退回舊值 / wrapper 的
 *  固定高被拿掉 / svg 少了 `h-full`(退回由 viewBox 比例決定渲染高)三種改壞法,在
 *  jsdom 下都是「畫面看起來一樣」的靜默失效。 */
describe("AdvanceDeclineChart 高度量測(TD-6)", () => {
  const ONE = [pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])];

  /** `observe` 當下同步餵一筆 —— useContainerSize 是 callback ref,非同步餵在 RTL 的
   *  同步斷言之前不會到達(測試會靜默退回 fallback 值 = 綠得毫無意義)。 */
  class FakeResizeObserver {
    private readonly cb: ResizeObserverCallback;

    constructor(cb: ResizeObserverCallback) {
      this.cb = cb;
    }

    observe(node: Element): void {
      this.cb(
        [{ target: node, contentRect: { width: 640, height: 96 } } as unknown as ResizeObserverEntry],
        this as unknown as ResizeObserver,
      );
    }

    unobserve(): void {}

    disconnect(): void {}
  }

  function viewBoxHeight(): number {
    const svg = screen.getByRole("img", { name: "全市場騰落線" });
    return Number((svg.getAttribute("viewBox") ?? "").split(" ")[3]);
  }

  it("量得到 640×96 → viewBox 高 96(不是 fallback 150)", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    render(<AdvanceDeclineChart series={ONE} />);
    expect(viewBoxHeight()).toBe(96);
  });

  it("量不到(jsdom 無 ResizeObserver)→ 退回 150,由 preserveAspectRatio 縮放置中(W-10)", () => {
    expect(typeof ResizeObserver).toBe("undefined");
    render(<AdvanceDeclineChart series={ONE} />);
    expect(viewBoxHeight()).toBe(150);
  });

  it("wrapper 預設 h-24 不縮,兩欄態由 --idx-* 變數接管;svg 撐滿它(h-full w-full)", () => {
    render(<AdvanceDeclineChart series={ONE} />);
    const wrapper = screen.getByRole("img", { name: "全市場騰落線" }).parentElement!;
    // `h-24` 保留:它是**單欄態**的高度(變數未設 → flex 走預設 `0 0 auto`,height 生效)。
    expect(wrapper.className).toContain("h-24");
    // `shrink-0` 換成變數 flex —— 兩欄態要讓這支 wrapper 吃 section 的剩餘高
    // (左欄設 `--idx-adl-wrap-flex:1 1 0%`),留著 shrink-0 的 `flex-shrink:0` 會與
    // shorthand 打架(Tailwind 產出的先後順序不可控)。預設值 `0 0 auto` 與 shrink-0 等值。
    expect(wrapper.className).not.toContain("shrink-0");
    expect(wrapper.className).toContain("[flex:var(--idx-adl-wrap-flex,0_0_auto)]");
    // 兩欄態 basis 0% 會蓋掉 `h-24`,地板改由 min-height 10rem 給(單欄態預設 auto = 無地板)。
    expect(wrapper.className).toContain("[min-height:var(--idx-adl-min,auto)]");
    // 根:兩欄態要把 section 分到的高一路傳給 wrapper,可縮鏈少一段就傳不下去。
    const root = screen.getByTestId("adl-chart");
    expect(root.className).toContain("flex-1");
    expect(root.className).toContain("min-h-0");
    const svg = screen.getByRole("img", { name: "全市場騰落線" });
    // 只有 `w-full` 的話渲染高退回「寬 × viewBox 比例」,量測算出來的高就白算了
    expect(svg.getAttribute("class")).toContain("h-full");
    expect(svg.getAttribute("class")).toContain("w-full");
  });
});
