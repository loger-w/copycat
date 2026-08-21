/** @vitest-environment jsdom */
/** 兩座閃電梯「武裝列」的 characterization lock(refactor housekeeping C5)。
 *
 *  現股 / 個股期梯(`LadderView`)與期貨梯(`FuturesLadder`)各自寫了一份結構相同的
 *  武裝列(武裝鈕 + 鎖定鈕 + 商品別控制項),差異只在容器 gap、鎖定鈕是否條件渲染、
 *  `title` 口徑與右側 slot 的內容。抽 `components/ladder/ArmRow.tsx` 合一之前,先把
 *  **改前的 DOM 逐字**釘住 —— 這種列的失效樣態(class 掉一個、`aria-pressed` 變
 *  `data-pressed`、鈕順序互換)在功能測試裡全是綠的,只有 outerHTML 看得見。
 *
 *  期望值刻意寫**字面量字串**而不是 `toMatchSnapshot()`:snapshot 檔會被 `-u` 一鍵
 *  重寫,而這裡要的正是「改動必須是人為決定」。
 *
 *  焦點穩定性另立一案:合一後武裝鈕若換了 element identity(例如被包進新的條件分支),
 *  rerender 時焦點會掉回 body —— 武裝中的使用者按 Esc / 空白鍵就失效,畫面上看不出來。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesLadder } from "@/components/futures/FuturesLadder";
import { LadderView } from "@/components/stock/LadderView";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import type { LadderRow } from "@/lib/stock-tick";
import type { FuturesProductState } from "@/types";

const ROWS: LadderRow[] = [
  { priceMilli: 100_000, bidQty: 30, askQty: 0, isCenter: true, dimmed: false },
];

const TXF_STATE: FuturesProductState = {
  product: "TXF",
  name: "臺股期貨",
  p: 23_000_000,
  q: 3,
  cum_vol: 12_000,
  t: "09:10:00",
  date: "20260728",
  bids: [[22_999_000, 45]],
  asks: [[23_001_000, 88]],
  ref: 22_800_000,
  upper: 25_080_000,
  lower: 20_520_000,
  resolved_contract: "202609",
};

/** 改前逐字(2026-08-21,commit 前的 master 行為)。以 `+` 串接只為行寬,內容連續無空白。 */
const ARM_BUTTON =
  '<button type="button" aria-pressed="false" class="min-w-0 flex-1 rounded border px-2 py-1' +
  ' text-xs font-bold border-line text-ink-dim hover:border-accent hover:text-ink">武裝</button>';

const LOCK_TITLE_TEXT = "鎖定:換標的 / 換梯 / 閒置不解除;斷線 / 連 3 敗 / Esc / 解除仍會解除";

const LOCK_BUTTON =
  `<button type="button" aria-pressed="false" title="${LOCK_TITLE_TEXT}" class="shrink-0` +
  ' rounded border px-2 py-1 text-xs font-bold border-line text-ink-dim hover:border-accent' +
  ' hover:text-ink">鎖定</button>';

const ARM_CONTROLS = '<span data-testid="arm-controls">現沖</span>';

const LADDER_VIEW_ARM_ROW =
  '<div class="flex items-center gap-1">' + ARM_BUTTON + LOCK_BUTTON + ARM_CONTROLS + "</div>";

const LADDER_VIEW_ARM_ROW_NO_LOCK =
  '<div class="flex items-center gap-1">' + ARM_BUTTON + "</div>";

/** 武裝態 / 鎖定態的期望值**取自改後的 DOM**(改前沒有這兩態的 characterization);
 *  reviewer 已逐字對照改前兩梯 JSX 的對應分支,確認 class 串與字樣完全相同。
 *
 *  補這兩態的理由:靜止態(未武裝 / 未鎖定)全綠不代表**武裝態配色**與**「鎖定中」字樣**
 *  沒掉 —— 而那正是使用者判斷「現在點價會不會真的送出去」的唯一訊號。 */
const ARM_BUTTON_ARMED =
  '<button type="button" aria-pressed="true" class="min-w-0 flex-1 rounded border px-2 py-1' +
  ' text-xs font-bold border-loss bg-loss text-bg">解除</button>';

const LOCK_BUTTON_LOCKED =
  `<button type="button" aria-pressed="true" title="${LOCK_TITLE_TEXT}" class="shrink-0` +
  ' rounded border px-2 py-1 text-xs font-bold border-accent bg-accent text-bg">鎖定中</button>';

const LADDER_VIEW_ARM_ROW_ARMED =
  '<div class="flex items-center gap-1">' +
  ARM_BUTTON_ARMED +
  LOCK_BUTTON +
  ARM_CONTROLS +
  "</div>";

const LADDER_VIEW_ARM_ROW_LOCKED =
  '<div class="flex items-center gap-1">' +
  ARM_BUTTON +
  LOCK_BUTTON_LOCKED +
  ARM_CONTROLS +
  "</div>";

const FUTURES_ARM_ROW =
  '<div class="flex items-center gap-2">' +
  ARM_BUTTON +
  '<button type="button" aria-pressed="false" disabled="" title="連線未就緒,無法鎖定"' +
  ' class="shrink-0 rounded border px-2 py-1 text-xs font-bold border-line text-ink-dim' +
  ' hover:border-accent hover:text-ink opacity-40">鎖定</button>' +
  '<label class="flex items-center gap-1 text-xs text-ink-muted">' +
  '<input aria-label="當沖" class="accent-loss" type="checkbox">當沖</label></div>';

let qc: QueryClient;

/** 武裝列 = 武裝鈕的父層 flex 容器(鎖定鈕 / 商品別控制項與它同層)。
 *  武裝態的鈕字會變「解除」,所以用 regex 認人;兩梯都沒有第二顆帶這兩個字的鈕。 */
function armRowHtml(): string {
  return screen.getByRole("button", { name: /武裝|解除/ }).parentElement!.outerHTML;
}

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting");
  Element.prototype.scrollIntoView = vi.fn();
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify({ orders: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("武裝列 characterization(兩梯 outerHTML 逐字)", () => {
  it("LadderView(現股 / 個股期):武裝 + 鎖定 + armControls", () => {
    render(
      <LadderView
        code="2330"
        rows={ROWS}
        marketBidQty={0}
        marketAskQty={0}
        armed={false}
        onToggleArm={() => {}}
        locked={false}
        onToggleLock={() => {}}
        armControls={<span data-testid="arm-controls">現沖</span>}
        qty={1}
        qtyLabel="張數"
        onQtyPreset={() => {}}
        onQtyInput={() => {}}
        onClickPrice={() => {}}
        onCancelLot={() => {}}
      />,
    );
    expect(armRowHtml()).toBe(LADDER_VIEW_ARM_ROW);
  });

  it("LadderView:armed → 解除鈕 + border-loss bg-loss text-bg", () => {
    render(
      <LadderView
        code="2330"
        rows={ROWS}
        marketBidQty={0}
        marketAskQty={0}
        armed={true}
        onToggleArm={() => {}}
        locked={false}
        onToggleLock={() => {}}
        armControls={<span data-testid="arm-controls">現沖</span>}
        qty={1}
        qtyLabel="張數"
        onQtyPreset={() => {}}
        onQtyInput={() => {}}
        onClickPrice={() => {}}
        onCancelLot={() => {}}
      />,
    );
    expect(armRowHtml()).toBe(LADDER_VIEW_ARM_ROW_ARMED);
  });

  it("LadderView:locked → 鎖定中鈕 + border-accent bg-accent text-bg", () => {
    render(
      <LadderView
        code="2330"
        rows={ROWS}
        marketBidQty={0}
        marketAskQty={0}
        armed={false}
        onToggleArm={() => {}}
        locked={true}
        onToggleLock={() => {}}
        armControls={<span data-testid="arm-controls">現沖</span>}
        qty={1}
        qtyLabel="張數"
        onQtyPreset={() => {}}
        onQtyInput={() => {}}
        onClickPrice={() => {}}
        onCancelLot={() => {}}
      />,
    );
    expect(armRowHtml()).toBe(LADDER_VIEW_ARM_ROW_LOCKED);
  });

  it("LadderView:未給 onToggleLock → 鎖定鈕整顆不渲染", () => {
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
        onCancelLot={() => {}}
      />,
    );
    expect(armRowHtml()).toBe(LADDER_VIEW_ARM_ROW_NO_LOCK);
  });

  it("FuturesLadder(期貨):武裝 + 鎖定 + 當沖 checkbox", () => {
    render(
      <QueryClientProvider client={qc}>
        <FuturesLadder product="TXF" state={TXF_STATE} />
      </QueryClientProvider>,
    );
    expect(armRowHtml()).toBe(FUTURES_ARM_ROW);
  });

  it("武裝鈕 focus 後 rerender → activeElement 不變(element identity 穩定)", () => {
    const props = {
      code: "2330",
      rows: ROWS,
      marketBidQty: 0,
      marketAskQty: 0,
      armed: false,
      onToggleArm: () => {},
      locked: false,
      onToggleLock: () => {},
      qtyLabel: "張數",
      onQtyPreset: () => {},
      onQtyInput: () => {},
      onClickPrice: () => {},
      onCancelLot: () => {},
    };
    const { rerender } = render(<LadderView {...props} qty={1} />);
    const armBtn = screen.getByRole("button", { name: "武裝" });
    armBtn.focus();
    expect(document.activeElement).toBe(armBtn);
    // 自檢:focus 真的落在鈕上而不是 body(jsdom 對 detached / hidden 元素會靜默不 focus)
    expect(document.activeElement).not.toBe(document.body);

    rerender(<LadderView {...props} qty={5} />);
    // 同一顆 DOM node 還在(React 沒重建),焦點也還在它身上
    expect(screen.getByRole("button", { name: "武裝" })).toBe(armBtn);
    expect(document.activeElement).toBe(armBtn);
  });
});
