/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { RiverPanel } from "@/components/corr/RiverPanel";
import type { RiverState } from "@/types";

const DAY = { start_min: 525, end_min: 825 };

function state(over: Partial<RiverState> = {}): RiverState {
  return {
    type: "river",
    seq: 3,
    session: "day",
    base: "TXF",
    window: DAY,
    legs: {
      TXF: {
        label: "台指",
        minutes: { "10": 40_000_000, "20": 40_400_000 },
        last: 40_400_000,
        last_minute: 20,
      },
      TWN: {
        label: "富台",
        minutes: { "10": 3_400_000, "20": 3_366_000 },
        last: 3_366_000,
        last_minute: 20,
      },
      YM: { label: "道瓊", minutes: {}, last: null, last_minute: null },
    },
    ...over,
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(cleanup);

describe("RiverPanel", () => {
  it("預設並排:兩顆鈕都在,並排為 accent,各腿名皆出現", () => {
    render(<RiverPanel state={state()} />);

    const side = screen.getByRole("button", { name: "並排" });
    const overlay = screen.getByRole("button", { name: "重疊" });
    expect(side.className).toContain("text-accent");
    expect(overlay.className).not.toContain("text-accent");
    expect(screen.getAllByText("台指").length).toBeGreaterThan(0);
    expect(screen.getAllByText("富台").length).toBeGreaterThan(0);
    expect(screen.getAllByText("道瓊").length).toBeGreaterThan(0);
  });

  it("並排卡片顯示現價與相對窗首 %,漲用 bull 色", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("40400.00")).toBeTruthy();
    const pct = screen.getByText("+1.00%");
    expect(pct.className).toContain("text-bull");
  });

  it("跌的腿用 bear 色", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("-1.00%").className).toContain("text-bear");
  });

  it("無資料的腿顯示「無資料」而非 0", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("無資料")).toBeTruthy();
  });

  it("點重疊 → 模式切換並寫入 localStorage,勾選列出現", () => {
    render(<RiverPanel state={state()} />);

    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    expect(window.localStorage.getItem("copycat-river-mode")).toBe("overlay");
    expect(screen.getByRole("checkbox", { name: "台指" })).toBeTruthy();
  });

  it("取消勾選 → 記進 localStorage 且該腿線消失", () => {
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    fireEvent.click(screen.getByRole("checkbox", { name: "富台" }));

    expect(JSON.parse(window.localStorage.getItem("copycat-river-legs") ?? "[]")).toEqual(["TWN"]);
    expect(screen.getByRole("checkbox", { name: "富台" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    // 圖上腿名標籤消失(SVG 內的 text),checkbox 上的字不算
    const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
    expect(svg.textContent).not.toContain("富台");
    expect(svg.textContent).toContain("台指");
  });

  it("重疊圖 % 軸標籤(characterization:域上下緣)", () => {
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
    expect(svg.textContent).toContain("+1.05%");
    expect(svg.textContent).toContain("-1.05%");
  });

  it("重掛後模式與勾選狀態復原", () => {
    window.localStorage.setItem("copycat-river-mode", "overlay");
    window.localStorage.setItem("copycat-river-legs", JSON.stringify(["TWN"]));

    render(<RiverPanel state={state()} />);

    expect(screen.getByRole("button", { name: "重疊" }).className).toContain("text-accent");
    expect(screen.getByRole("checkbox", { name: "富台" }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("localStorage 壞值不崩(降回預設)", () => {
    window.localStorage.setItem("copycat-river-mode", "garbage");
    window.localStorage.setItem("copycat-river-legs", "{not json");

    render(<RiverPanel state={state()} />);

    expect(screen.getByRole("button", { name: "並排" }).className).toContain("text-accent");
  });

  it("state 為 null → 等待文案", () => {
    render(<RiverPanel state={null} />);

    expect(screen.getByText("等待各腿資料…")).toBeTruthy();
  });

  it("盤別顯示在標題", () => {
    render(<RiverPanel state={state({ session: "night" })} />);

    expect(screen.getByText(/夜盤/)).toBeTruthy();
  });

  it("全腿無點 → 顯示等待該盤別資料", () => {
    const empty = state();
    for (const leg of Object.values(empty.legs)) {
      leg.minutes = {};
      leg.last = null;
      leg.last_minute = null;
    }

    render(<RiverPanel state={empty} />);

    expect(screen.getByText("等待日盤資料…")).toBeTruthy();
  });
});
