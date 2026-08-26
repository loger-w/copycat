/** @vitest-environment jsdom */
/** N014-2:拖曳中「落點沒變」不得每個 `pointermove` 都重繪整個側欄。
 *
 *  `move` 的 `setDrag` updater 每次都造新物件 → React 拿不到 `Object.is` 相等,
 *  於是每一則 pointermove(手指移動時每秒數十則)都重繪整份自選列。症狀只是拖曳掉幀,
 *  **沒有任何斷言會紅** —— 所以探針必須是「元件 render body 內、不在 useMemo 裡」的
 *  呼叫(frontend-testing 的 memo 計次教訓):`stockRow` 每列都直呼 `secSummary`。
 *
 *  `vi.mock` 是檔案級 + hoisted,所以這條計次測試獨立成檔(主檔的 100+ 條不受影響)。
 */
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import * as positionSummary from "@/lib/position-summary";
import type { Group } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";

/** delegate 原實作(`vi.fn(actual.…)` 只多記一次呼叫)—— 換假回傳值會讓側欄的
 *  倉位 chip 整片變成在量假資料。 */
vi.mock("@/lib/position-summary", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/position-summary")>();
  return { ...actual, secSummary: vi.fn(actual.secSummary) };
});

const GROUPS: Group[] = [
  { name: "主力", codes: ["2330", "5483"] },
  { name: "觀察", codes: ["3231", "2330"] },
];
const CODES = ["2330", "5483", "3231"];

const QUOTES = {
  "2330": {
    p: 2_380_000, chg_pct: 2.59, vol: 12479, ref: null,
    upper: 2_550_000, lower: 2_090_000, no_data: false, trial: false,
  },
};

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/names")) {
        return new Response(JSON.stringify({ names: [], count: 0 }));
      }
      if (String(url).includes("/api/capital/positions")) {
        // 探針 `secSummary` 只在該股號有部位列時才被呼叫 —— 空清單 = 零呼叫 = 假綠
        return new Response(
          JSON.stringify({
            positions: [
              { market: "sec", stock_no: "2330", qty: 3, name: "台積電", avg_price: 985.2,
                kind: "cash", pnl_base: null, pnl_base_price: null, pnl_cost: null,
        avg_source: null, today_qty: 0, code: "2330" },
            ],
          }),
        );
      }
      return new Response(JSON.stringify({ codes: CODES, groups: GROUPS }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const RECTS: Record<string, [number, number]> = {
  "wl-group-主力": [0, 120],
  "wl-list-主力": [24, 120],
  "wl-group-觀察": [130, 250],
  "wl-list-觀察": [154, 250],
  "wl-ungrouped": [260, 340],
  "wl-list-ungrouped": [284, 340],
};

function stubRects(): void {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
    this: Element,
  ) {
    const box = (top: number, bottom: number): DOMRect =>
      ({
        left: 0, right: 240, top, bottom, width: 240, height: bottom - top,
        x: 0, y: top, toJSON: () => ({}),
      }) as DOMRect;
    if (this.tagName === "ASIDE") return box(0, 600);
    const span = RECTS[this.getAttribute("data-testid") ?? ""];
    return span ? box(span[0], span[1]) : box(0, 0);
  });
}

function ptr(type: string, x: number, y: number): MouseEvent {
  return new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
}

describe("WatchlistSidebar 拖曳重繪(N014-2)", () => {
  it("落點未變的 pointermove 不重繪(drag state 回同一個 reference)", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByTestId("wl-group-主力")).toBeTruthy());
    // 等倉位 query 落地再開始 —— 它晚一拍 resolve 會在拖曳中途插一次 render,
    // 計次就不是在量 drag state 的 identity 了(假紅)
    await waitFor(() => expect(screen.getAllByText(/3張/).length).toBeGreaterThan(0));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20)); // 讓 TQ 的 notifyManager 排程收乾淨
    });
    stubRects();
    const handle = within(screen.getByTestId("wl-group-主力")).getByTestId("wl-handle-5483");
    fireEvent(handle, ptr("pointerdown", 10, 80));

    const probe = vi.mocked(positionSummary.secSummary);
    // 先移進目標組並停穩(第一則 move 會真的換 `to`,是狀態轉移不是重繪浪費)
    fireEvent(window, ptr("pointermove", 100, 180));
    fireEvent(window, ptr("pointermove", 100, 185));

    // 落點不變的連續 move:手指移動時每秒數十則,一則都不該重繪
    const settled = probe.mock.calls.length;
    fireEvent(window, ptr("pointermove", 101, 190));
    fireEvent(window, ptr("pointermove", 102, 195));
    fireEvent(window, ptr("pointermove", 103, 200));
    expect(probe.mock.calls.length).toBe(settled);

    // 非 vacuous 自檢:真的換組時探針**必須**動(否則上面在量一個永遠不動的東西)
    fireEvent(window, ptr("pointermove", 100, 60));
    expect(probe.mock.calls.length).toBeGreaterThan(settled);

    fireEvent(window, new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
});
