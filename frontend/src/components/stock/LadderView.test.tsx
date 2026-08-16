/** @vitest-environment jsdom */
/** LadderView 的 **prop 介面級**防禦測試。
 *
 *  兩個 container(PriceLadder / StkfutLadder)餵進來的 lot 都經過 `aggregateLots`,
 *  那裡的 entry 條件保證不會產出「qty 0 + filled 0 + seqs 空」的 lot。但 LadderView
 *  是公開 prop 介面(期貨梯之外的第三個 caller 隨時可能出現),徽章分支不看 `filled`
 *  就會把空 lot 畫成 `(0)` —— 期貨梯的同款分支(`FuturesLadder.tsx:426 r.myFilled > 0`)
 *  是有守門的,兩邊不對稱。此檔只測 LadderView 自己,fixture 最小化。 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LadderView } from "@/components/stock/LadderView";
import type { LadderLot } from "@/lib/ladder-lots";
import type { LadderRow } from "@/lib/stock-tick";

const ROWS: LadderRow[] = [
  { priceMilli: 100_000, bidQty: 30, askQty: 0, isCenter: true, dimmed: false },
];

function renderView(props: {
  buyLots?: Map<number, LadderLot>;
  sellLots?: Map<number, LadderLot>;
  locked?: boolean;
  onToggleLock?: () => void;
}) {
  return render(
    <LadderView
      code="2330"
      rows={ROWS}
      marketBidQty={0}
      marketAskQty={0}
      armed={false}
      onToggleArm={() => {}}
      qty={1}
      qtyLabel="張數"
      onQtyPreset={() => {}}
      onQtyInput={() => {}}
      onClickPrice={() => {}}
      onCancelLot={() => {}}
      {...props}
    />,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn(); // jsdom 無此方法(跟隨置中)
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LadderView 徽章守門(C3)", () => {
  it("空 lot(qty 0 / filled 0 / seqs 空)→ 既無徽章也無刪單鈕", () => {
    renderView({ buyLots: new Map([[100_000, { qty: 0, filled: 0, seqs: [] }]]) });
    // 同步錨:這一列確實畫出來了,absence 斷言才不是 vacuous
    expect(screen.getByLabelText("買 100")).toBeTruthy();
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
    expect(screen.queryByLabelText("刪 100 買單")).toBeNull();
  });

  it("賣側空 lot 同款零痕跡", () => {
    renderView({ sellLots: new Map([[100_000, { qty: 0, filled: 0, seqs: [] }]]) });
    expect(screen.getByLabelText("賣 100")).toBeTruthy();
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
    expect(screen.queryByLabelText("刪 100 賣單")).toBeNull();
  });

  it("filled>0 的終態 lot 照樣長徽章(守門不得把真徽章一起殺掉)", () => {
    renderView({ buyLots: new Map([[100_000, { qty: 0, filled: 2, seqs: [] }]]) });
    expect(screen.getByTestId("ladder-filled-lot").textContent).toBe("(2)");
  });

  it("seqs 非空的殘 0 活單維持可點紅方格(R2:刪單入口不得被收走)", () => {
    const calls: LadderLot[] = [];
    render(
      <LadderView
        code="2330"
        rows={ROWS}
        marketBidQty={0}
        marketAskQty={0}
        armed={false}
        onToggleArm={() => {}}
        qty={1}
        qtyLabel="張數"
        onQtyPreset={() => {}}
        onQtyInput={() => {}}
        onClickPrice={() => {}}
        onCancelLot={(lot) => calls.push(lot)}
        buyLots={new Map([[100_000, { qty: 0, filled: 0, seqs: ["016"] }]])}
      />,
    );
    const btn = screen.getByLabelText("刪 100 買單");
    expect(btn.textContent).toBe("0(0)");
    fireEvent.click(btn);
    expect(calls.map((l) => l.seqs)).toEqual([["016"]]);
  });
});

/** 鎖定鈕的渲染閘(change-spec review R5):`onToggleLock` 未給就不渲染 —— 這是「既有
 *  裸 render 的呼叫端零改動」的實現手段。改成無條件渲染的話,本檔上面那些裸 render 案
 *  會多長一顆按不動的「鎖定」鈕,而它們一條都不會紅。 */
describe("LadderView 鎖定鈕的渲染閘(R5)", () => {
  it("未給 onToggleLock → 不渲染鎖定鈕", () => {
    renderView({});
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy(); // 同步錨:武裝列在
    expect(screen.queryByRole("button", { name: "鎖定" })).toBeNull();
    expect(screen.queryByRole("button", { name: "鎖定中" })).toBeNull();
  });

  it("給了 onToggleLock → 鎖定鈕出現且點擊回呼;locked=true 顯示「鎖定中」", () => {
    const calls: number[] = [];
    const { rerender } = renderView({ onToggleLock: () => calls.push(1) });
    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    expect(calls.length).toBe(1);
    rerender(
      <LadderView
        code="2330"
        rows={ROWS}
        marketBidQty={0}
        marketAskQty={0}
        armed
        onToggleArm={() => {}}
        locked
        onToggleLock={() => calls.push(1)}
        qty={1}
        qtyLabel="張數"
        onQtyPreset={() => {}}
        onQtyInput={() => {}}
        onClickPrice={() => {}}
        onCancelLot={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "鎖定中" }).getAttribute("aria-pressed")).toBe("true");
  });
});
