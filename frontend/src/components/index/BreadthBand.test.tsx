/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BreadthBand } from "@/components/index/BreadthBand";
import type { BreadthState } from "@/types";

function state(over: Partial<BreadthState> = {}): BreadthState {
  return {
    enabled: true,
    trade_date: "2026-08-06",
    as_of: "10:31:00",
    stale: false,
    counts: {
      twse: { limit_up: 3, up: 512, flat: 88, down: 401, limit_down: 2 },
      tpex: { limit_up: 7, up: 388, flat: 61, down: 290, limit_down: 1 },
    },
    series: [],
    ...over,
  };
}

afterEach(cleanup);

describe("BreadthBand 三態(SC-4)", () => {
  it("(a) breadth null → 載入中", () => {
    render(<BreadthBand breadth={null} />);
    expect(screen.getByTestId("breadth-band").textContent).toContain("載入中");
    expect(screen.queryByTestId("breadth-cell-twse-up")).toBeNull();
  });

  it("(b) enabled=false → FinMind 未設定(不畫格子)", () => {
    render(<BreadthBand breadth={state({ enabled: false, counts: null })} />);
    expect(screen.getByTestId("breadth-band").textContent).toContain("FinMind 未設定");
    expect(screen.queryByTestId("breadth-cell-twse-up")).toBeNull();
  });

  it("(c) enabled 但 counts=null → 載入中", () => {
    render(<BreadthBand breadth={state({ counts: null })} />);
    expect(screen.getByTestId("breadth-band").textContent).toContain("載入中");
    expect(screen.queryByTestId("breadth-cell-twse-up")).toBeNull();
  });
});

describe("BreadthBand 格值與版面(SC-4)", () => {
  it("(d) 上市 / 上櫃兩列各五格,依序漲停 / 上漲 / 平盤 / 下跌 / 跌停", () => {
    render(<BreadthBand breadth={state()} />);
    for (const market of ["twse", "tpex"] as const) {
      const row = within(screen.getByTestId(`breadth-row-${market}`));
      const cells = row.getAllByTestId(/^breadth-cell-/);
      expect(cells.length).toBe(5);
      expect(cells.map((c) => c.getAttribute("data-testid"))).toEqual([
        `breadth-cell-${market}-limit_up`,
        `breadth-cell-${market}-up`,
        `breadth-cell-${market}-flat`,
        `breadth-cell-${market}-down`,
        `breadth-cell-${market}-limit_down`,
      ]);
      expect(cells.map((c) => c.textContent)).toEqual([
        expect.stringContaining("漲停"),
        expect.stringContaining("上漲"),
        expect.stringContaining("平盤"),
        expect.stringContaining("下跌"),
        expect.stringContaining("跌停"),
      ]);
    }
    expect(screen.getByTestId("breadth-row-twse").textContent).toContain("上市");
    expect(screen.getByTestId("breadth-row-tpex").textContent).toContain("上櫃");
  });

  it("(e) 十個數字逐格對上後端 counts", () => {
    render(<BreadthBand breadth={state()} />);
    const got: Record<string, string> = {};
    for (const market of ["twse", "tpex"] as const) {
      for (const b of ["limit_up", "up", "flat", "down", "limit_down"]) {
        got[`${market}-${b}`] = screen.getByTestId(`breadth-cell-${market}-${b}`).textContent ?? "";
      }
    }
    expect(got["twse-limit_up"]).toContain("3");
    expect(got["twse-up"]).toContain("512");
    expect(got["twse-flat"]).toContain("88");
    expect(got["twse-down"]).toContain("401");
    expect(got["twse-limit_down"]).toContain("2");
    expect(got["tpex-limit_up"]).toContain("7");
    expect(got["tpex-up"]).toContain("388");
    expect(got["tpex-flat"]).toContain("61");
    expect(got["tpex-down"]).toContain("290");
    expect(got["tpex-limit_down"]).toContain("1");
  });

  it("(f) 漲停格紅底、跌停格綠底、中間三格中性(台股紅漲綠跌)", () => {
    render(<BreadthBand breadth={state()} />);
    const up = screen.getByTestId("breadth-cell-twse-limit_up").className;
    const down = screen.getByTestId("breadth-cell-twse-limit_down").className;
    expect(up).toContain("bg-bull");
    expect(down).toContain("bg-bear");
    for (const b of ["up", "flat", "down"]) {
      const cls = screen.getByTestId(`breadth-cell-twse-${b}`).className;
      expect(cls).not.toContain("bg-bull");
      expect(cls).not.toContain("bg-bear");
    }
  });

  // 🔴 2026-08-16(D8):停板兩桶改**實心**底(bg-bull / bg-bear 滿版,不再是 /15 淡底),
  // 白字是隨之而來的可讀性條件 —— ink token 在滿版紅綠上對比不足。標籤與數字都要白:
  // 只染數字會留下一個 ink-dim 的「漲停」字浮在實心紅底上,比改版前更難讀。
  // 樣板 = 個股期漲跌停燈(WatchlistSidebar.tsx:405-406 的 bg-bull … text-white)。
  it("(g) 漲停桶實心紅底,標籤與數字都是白字(實心底上的可讀性)", () => {
    render(<BreadthBand breadth={state()} />);
    const cell = screen.getByTestId("breadth-cell-twse-limit_up");
    // TD-8:「實心」原本沒鎖 —— `bg-bull/15`(改版前的淡底)也含子字串 `bg-bull`,
    // 退回淡底時 (f) 與這一條都照樣綠,而白字配淡底才是真正讀不出來的組合。
    expect(cell.className).toContain("bg-bull");
    expect(cell.className).not.toContain("bg-bull/");
    const label = within(cell).getByText("漲停");
    expect(label.className).toContain("text-white");
    const num = screen.getByTestId("breadth-value-twse-limit_up").className;
    expect(num).toContain("text-white");
    expect(num).not.toContain("text-bull");
    expect(num).not.toContain("text-bear");
  });
});

/** 🔴 2026-08-14 拍板配色(D8:本輪不動):上漲 / 下跌兩格**沒有底色**,識別完全落在
 *  數字上 —— 這兩格的數字染紅綠與 (f)(g)(o) 的「停板格實心底 + 白字」不衝突,兩者是
 *  「有底色的格靠色塊、字退成白」與「沒底色的格由字承擔」的一體兩面。 */
describe("BreadthBand 上漲 / 下跌字色(SC-1)", () => {
  it("(l) 上漲數字紅字(text-bull),兩市場皆然", () => {
    render(<BreadthBand breadth={state()} />);
    for (const market of ["twse", "tpex"] as const) {
      const cls = screen.getByTestId(`breadth-value-${market}-up`).className;
      expect(cls).toContain("text-bull");
      expect(cls).not.toContain("text-bear");
    }
  });

  it("(m) 下跌數字綠字(text-bear),兩市場皆然", () => {
    render(<BreadthBand breadth={state()} />);
    for (const market of ["twse", "tpex"] as const) {
      const cls = screen.getByTestId(`breadth-value-${market}-down`).className;
      expect(cls).toContain("text-bear");
      expect(cls).not.toContain("text-bull");
    }
  });

  it("(n) 平盤數字維持中性 ink,不沾紅綠", () => {
    render(<BreadthBand breadth={state()} />);
    const cls = screen.getByTestId("breadth-value-twse-flat").className;
    expect(cls).toContain("text-ink");
    expect(cls).not.toContain("text-bull");
    expect(cls).not.toContain("text-bear");
  });

  it("(o) 跌停桶實心綠底 + 白字(與 (g) 同一條規則的另一邊)", () => {
    render(<BreadthBand breadth={state()} />);
    const cell = screen.getByTestId("breadth-cell-twse-limit_down");
    expect(cell.className).toContain("bg-bear");
    expect(cell.className).not.toContain("bg-bear/"); // 同 (g):淡底 `bg-bear/15` 也含 `bg-bear`
    expect(within(cell).getByText("跌停").className).toContain("text-white");
    const cls = screen.getByTestId("breadth-value-twse-limit_down").className;
    expect(cls).toContain("text-white");
    expect(cls).not.toContain("text-bear");
    expect(cls).not.toContain("text-bull");
  });

  it("(p) 上漲 / 下跌格仍然沒有底色(染色不與字色疊加)", () => {
    render(<BreadthBand breadth={state()} />);
    for (const b of ["up", "down"] as const) {
      const cls = screen.getByTestId(`breadth-cell-twse-${b}`).className;
      expect(cls).not.toContain("bg-bull");
      expect(cls).not.toContain("bg-bear");
    }
  });
});

describe("BreadthBand stale 徽章(SC-3)", () => {
  it("(h) stale=true → 顯示「資料延遲」且前值仍在", () => {
    render(<BreadthBand breadth={state({ stale: true })} />);
    expect(screen.getByTestId("breadth-stale").textContent).toContain("資料延遲");
    expect(screen.getByTestId("breadth-cell-twse-up").textContent).toContain("512");
  });

  it("(i) stale=false → 無徽章", () => {
    render(<BreadthBand breadth={state()} />);
    expect(screen.queryByTestId("breadth-stale")).toBeNull();
  });
});

/** 開盤前面板上掛的是前一交易日的曲線,只印時分秒看不出是舊的(review P2-5)。 */
describe("BreadthBand trade_date 標示(review P2-5)", () => {
  it("(j) 正常態於 as_of 旁顯示 trade_date", () => {
    render(<BreadthBand breadth={state({ trade_date: "2026-08-05", as_of: "13:30:00" })} />);
    const stamp = screen.getByTestId("breadth-stamp");
    expect(stamp.textContent).toContain("2026-08-05");
    expect(stamp.textContent).toContain("13:30:00");
    expect(stamp.className).toContain("text-ink-dim");
  });

  it("(k) trade_date 為 null 時只印 as_of,不留分隔符", () => {
    render(<BreadthBand breadth={state({ trade_date: null, as_of: "13:30:00" })} />);
    expect(screen.getByTestId("breadth-stamp").textContent).toBe("13:30:00");
  });
});
