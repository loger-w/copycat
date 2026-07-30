/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TickTape } from "@/components/stock/TickTape";
import type { TickRow } from "@/lib/stock-accum";

afterEach(cleanup);

const REF = 2_372_000;

/** 三態各一列:低於參考價 / 高於 / 等於(第三列的買賣價缺值) */
const TICKS: TickRow[] = [
  { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner", b: 2_369_000, a: 2_371_000 },
  { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer", b: 2_374_000, a: 2_376_000 },
  { t: "09:00:03.000", p: 2_372_000, q: 1, side: "neutral", b: null, a: null },
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
          { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner" },
          { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer" },
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
      <TickTape ticks={[{ t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner" }]} ref_={REF} />,
    );
    const root = screen.getByTestId("tick-tape");
    expect(root.className).toContain("h-full");
    expect(root.className).not.toContain("max-h-80");
    expect(root.className).toContain("overflow-y-auto"); // 內捲不可拿掉(W-8 載入更多要可達)
  });

  // W-13 的分頁在 round4 之前零測試覆蓋 —— 誰把 PAGE 改掉或把按鈕拿掉都不會紅
  it("點「載入更多」→ 列數 +30", () => {
    const many: TickRow[] = Array.from({ length: 70 }, (_, i) => ({
      t: `09:${String(Math.floor(i / 60)).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}.000`,
      p: 2_370_000 + i,
      q: 1,
      side: "outer",
    }));
    render(<TickTape ticks={many} ref_={REF} />);
    expect(screen.getAllByRole("row").slice(1)).toHaveLength(30);
    fireEvent.click(screen.getByText("載入更多"));
    expect(screen.getAllByRole("row").slice(1)).toHaveLength(60);
  });
});
