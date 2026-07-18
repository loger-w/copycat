/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { QuoteTable } from "@/components/QuoteTable";
import type { ContractRow } from "@/types";

afterEach(cleanup);

const CONTRACTS: ContractRow[] = [
  {
    symbol: "TC.O.TWF.TX4.202607.C.44000",
    cp: "C",
    strike: 44000,
    net_qty: 1,
    volume: 6,
    outer_qty: 2,
    inner_qty: 1,
  },
  {
    symbol: "TC.O.TWF.TX4.202607.P.44000",
    cp: "P",
    strike: 44000,
    net_qty: -4,
    volume: 4,
    outer_qty: 0,
    inner_qty: 4,
  },
  {
    symbol: "TC.O.TWF.TX4.202607.C.45000",
    cp: "C",
    strike: 45000,
    net_qty: -28,
    volume: 96,
    outer_qty: 31,
    inner_qty: 59,
  },
];

describe("QuoteTable", () => {
  it("每履約價一列、降冪排列、Call/Put 值就位", () => {
    const { container } = render(<QuoteTable contracts={CONTRACTS} spotPrice={null} />);
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("45,000");
    expect(rows[1]?.textContent).toContain("44,000");
    // C44000 內外盤比 2/(2+1) → 67%;P44000 → 0%
    expect(rows[1]?.textContent).toContain("67%");
    expect(rows[1]?.textContent).toContain("0%");
  });

  it("單側無成交顯示 —", () => {
    const { container } = render(<QuoteTable contracts={CONTRACTS} spotPrice={null} />);
    const first = container.querySelectorAll("tbody tr")[0];
    // 45000 僅 Call 有成交 → Put 側四欄 —
    expect(first?.textContent?.match(/—/g)?.length).toBe(4);
  });

  it("ATM 分隔線掛在該列每個 td(IR-6),且履約價脊柱不被 twMerge 吃掉", () => {
    const { container } = render(<QuoteTable contracts={CONTRACTS} spotPrice={44400} />);
    const firstRowTds = container.querySelectorAll("tbody tr")[0]?.querySelectorAll("td") ?? [];
    expect(firstRowTds.length).toBeGreaterThan(0);
    for (const td of firstRowTds) {
      expect(td.className).toMatch(/border-(b-)?accent/);
    }
    // 增量 review P1:border-accent(全側色)與 border-x-line 同 conflict group,
    // ATM 列的脊柱 class 曾被 twMerge 靜默移除 — 鎖住脊柱必須保留
    const strikeTd = [...firstRowTds].find((td) => td.textContent?.includes("45,000"));
    expect(strikeTd?.className).toContain("border-x-line");
  });

  it("spot 超出範圍不畫分隔線", () => {
    const { container } = render(<QuoteTable contracts={CONTRACTS} spotPrice={99999} />);
    expect(container.querySelectorAll("td.border-accent")).toHaveLength(0);
  });

  it("contracts 缺或空 → 空態文案", () => {
    render(<QuoteTable contracts={undefined} spotPrice={null} />);
    expect(screen.getByText("尚無成交累積")).toBeTruthy();
    cleanup();
    render(<QuoteTable contracts={[]} spotPrice={null} />);
    expect(screen.getByText("尚無成交累積")).toBeTruthy();
  });
});
