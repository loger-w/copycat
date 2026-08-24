/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TickTape } from "@/components/stock/TickTape";
import type { TickRow } from "@/lib/stock-accum";

afterEach(cleanup);

const REF = 2_372_000;

/** 三態各一列:低於參考價 / 高於 / 等於(第三列的買賣價缺值) */
const TICKS: TickRow[] = [
  { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner", b: 2_369_000, a: 2_371_000, n: 1 },
  { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer", b: 2_374_000, a: 2_376_000, n: 2 },
  { t: "09:00:03.000", p: 2_372_000, q: 1, side: "neutral", b: null, a: null, n: 3 },
];

describe("TickTape 五欄(SC-4)", () => {
  it("表頭為 時間 / 買價 / 賣價 / 成交 / 量", () => {
    render(<TickTape ticks={TICKS} ref_={REF} />);
    for (const label of ["時間", "買價", "賣價", "成交", "量"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("最新在最上", () => {
    render(
      <TickTape
        ticks={[
          { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner", n: 1 },
          { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer", n: 2 },
        ]}
        ref_={REF}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1); // 去表頭
    expect(rows[0]!.textContent).toContain("09:00:02");
  });
});

describe("TickTape 價格三欄依參考價上色(SC-5)", () => {
  it("高於參考價為紅、低於為綠、等於為灰(買 / 賣 / 成交各自判斷)", () => {
    render(<TickTape ticks={TICKS} ref_={REF} />);
    for (const high of ["2374", "2376", "2375"]) {
      expect(screen.getByText(high).className).toContain("text-bull");
    }
    for (const low of ["2369", "2371", "2370"]) {
      expect(screen.getByText(low).className).toContain("text-bear");
    }
    expect(screen.getByText("2372").className).toContain("text-ink-dim");
  });

  it("買賣價缺值 → 顯示 - 且為灰", () => {
    render(<TickTape ticks={TICKS} ref_={REF} />);
    const dashes = screen.getAllByText("-");
    expect(dashes).toHaveLength(2);
    for (const d of dashes) expect(d.className).toContain("text-ink-dim");
  });

  it("參考價為 null → 三個價都灰(不亂上色)", () => {
    render(<TickTape ticks={TICKS} ref_={null} />);
    for (const v of ["2374", "2376", "2375", "2369"]) {
      expect(screen.getByText(v).className).toContain("text-ink-dim");
    }
  });
});

describe("TickTape 量依內外盤上色(SC-6)", () => {
  it("外盤紅 / 內盤綠 / 無法判定灰", () => {
    render(<TickTape ticks={TICKS} ref_={REF} />);
    expect(screen.getByText("3").className).toContain("text-bull"); // outer
    expect(screen.getByText("5").className).toContain("text-bear"); // inner
    expect(screen.getByText("1").className).toContain("text-ink-dim"); // neutral
  });
});

describe("TickTape 既有行為(W-13 / W-14)", () => {
  it("空明細顯示提示", () => {
    render(<TickTape ticks={[]} ref_={REF} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });

  // 🔴 SC-6:明細改由下半列決定高度(h-full),不再是固定 320px 上限。這是「最外圍不出現
  // 捲軸」機制的一半 —— 圖表維持自然高度,剩餘空間全給下半列,明細在其中自行內捲。
  // 沒有這條護欄,日後誰把 h-full 換回 max-h-* 不會有任何測試變紅。
  it("root 由下半列撐高(h-full),非固定 max-h-80(SC-6)", () => {
    render(
      <TickTape ticks={[{ t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner", n: 1 }]} ref_={REF} />,
    );
    const root = screen.getByTestId("tick-tape");
    expect(root.className).toContain("h-full");
    expect(root.className).not.toContain("max-h-80");
    expect(root.className).toContain("overflow-y-auto"); // 內捲不可拿掉(W-8 載入更多要可達)
  });

  // 🔴 react-doctor P1(TickTape.tsx:57):`key` 用的是反轉後陣列的**前端**索引,
  // 而新成交是前插 —— 每一筆成交都讓所有 key 位移一格,整個 tbody(30–200 列)卸載重掛。
  // 盤中每秒數筆,這是持續的 DOM 重建。修法是回推索引(尾端錨定),前插時既有列 key 不變。
  it("追加新成交後,原有列的 DOM node 恆等保留(key 不隨前插位移)", () => {
    const base: TickRow[] = [
      { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner", n: 1 },
      { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer", n: 2 },
    ];
    const { rerender } = render(<TickTape ticks={base} ref_={REF} />);
    const before = screen.getAllByRole("row").slice(1); // [09:00:02, 09:00:01]
    expect(before).toHaveLength(2);

    rerender(
      <TickTape
        ticks={[...base, { t: "09:00:03.000", p: 2_372_000, q: 1, side: "neutral", n: 3 }]}
        ref_={REF}
      />,
    );

    const after = screen.getAllByRole("row").slice(1);
    expect(after).toHaveLength(3);
    expect(after[0]!.textContent).toContain("09:00:03"); // 新的一筆在最上
    // 同一筆成交 = 同一個 DOM node(重掛的話這裡會是新物件)
    expect(after[1]).toBe(before[0]);
    expect(after[2]).toBe(before[1]);
  });

  // W-13 的分頁在 round4 之前零測試覆蓋 —— 誰把 PAGE 改掉或把按鈕拿掉都不會紅
  it("點「載入更多」→ 列數 +30", () => {
    const many: TickRow[] = Array.from({ length: 70 }, (_, i) => ({
      t: `09:${String(Math.floor(i / 60)).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}.000`,
      p: 2_370_000 + i,
      q: 1,
      side: "outer",
      n: i + 1,
    }));
    render(<TickTape ticks={many} ref_={REF} />);
    expect(screen.getAllByRole("row").slice(1)).toHaveLength(30);
    fireEvent.click(screen.getByText("載入更多"));
    expect(screen.getAllByRole("row").slice(1)).toHaveLength(60);
  });
});

describe("TickTape 空態分流(2026-08-22 review R9 P2)", () => {
  it("loading(tape=0 取回、全量補打中)→「載入明細…」而非終態「尚無成交」", () => {
    render(<TickTape ticks={[]} ref_={REF} loading />);
    expect(screen.getByText("載入明細…")).toBeTruthy();
    expect(screen.queryByText("尚無成交")).toBeNull();
  });
  it("未傳 loading → 既有「尚無成交」", () => {
    render(<TickTape ticks={[]} ref_={REF} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });
});

// 🔴 N120:回推索引 key 在 `TAPE_MAX = 200` 滿載後仍逐筆位移 —— stock-accum 是環形丟頭,
// 陣列每來一筆就整體左移一格,回推索引跟著 −1 → 既有列全部卸載重掛(與修前同級)。
// 真解是每列自帶單調序號(`TickRow.n`),丟頭時倖存列的號不變。
describe("TickTape 滿載後 key 穩定(N120)", () => {
  /** 第 n 筆(1-based):時間互異、序號 = n。 */
  function row(n: number): TickRow {
    const sec = String(n % 60).padStart(2, "0");
    const min = String(Math.floor(n / 60)).padStart(2, "0");
    return { t: `09:${min}:${sec}.000`, p: 2_370_000 + n, q: 1, side: "outer", n };
  }

  it("滿載丟頭 + 前插一筆後,既有列的 DOM node 恆等保留", () => {
    const CAP = 200;
    const full = Array.from({ length: CAP }, (_, i) => row(i + 1));
    const { rerender } = render(<TickTape ticks={full} ref_={REF} />);
    const before = screen.getAllByRole("row").slice(1); // 顯示 30 列(PAGE)
    expect(before).toHaveLength(30);

    // 環形丟頭:最舊那筆掉出去,尾端接上新的一筆(陣列長度仍 = CAP)
    rerender(<TickTape ticks={[...full.slice(1), row(CAP + 1)]} ref_={REF} />);

    const after = screen.getAllByRole("row").slice(1);
    expect(after).toHaveLength(30);
    expect(after[0]!.textContent).toContain("03:21"); // 第 201 筆在最上
    // 同一筆成交 = 同一個 DOM node(key 位移的話這裡全是新物件)
    for (let i = 1; i < 30; i += 1) {
      expect(after[i]).toBe(before[i - 1]);
    }
  });
});
