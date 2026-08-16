/** @vitest-environment jsdom */
/** SC-6(d):hover 不重算幾何。
 *
 *  卡片上的圖與單檔頁是同一份渲染碼,而那份碼的 hover 每個 mousemove 都會 setState ——
 *  少了 `useMemo` 護欄,圖牆上 16 張卡片時滑過任何一張都會重算一次分時幾何(最多 271
 *  格 × 每次 mousemove)。**畫面上完全看不出來**:圖照畫、值照對,只是掉幀。
 *
 *  量法 = 把 `buildIntradayGeometry` 換成計次的同一份實作(`importOriginal` 保留行為)。
 *  `vi.mock` 是檔案級 + hoisted → 獨立檔。 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GroupGridView } from "@/components/stock/GroupGridView";
import { buildIntradayGeometry } from "@/lib/stock-intraday-svg";
import type { Group } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";

vi.mock("@/lib/stock-intraday-svg", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/stock-intraday-svg")>();
  return { ...actual, buildIntradayGeometry: vi.fn(actual.buildIntradayGeometry) };
});

const CODES = ["2330", "2317", "2454", "2308"];
const GROUPS: Group[] = [{ name: "半導體", codes: CODES }];

class FakeResizeObserver {
  private readonly cb: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }

  observe(node: Element): void {
    this.cb(
      [{ target: node, contentRect: { width: 300, height: 200 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {}
}

function state() {
  return {
    minutes: {
      "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 },
      "541": { c: 2_390_000, v: 6, i: 2, o: 4, u: 0 },
    },
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    no_data: false,
    backfilling: false,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/overlay/")) {
        return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
      }
      const picked: Record<string, unknown> = {};
      for (const c of CODES) picked[c] = state();
      return new Response(JSON.stringify({ states: picked }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("GroupGridView hover 不重算幾何(SC-6d)", () => {
  it("4 張卡掛好後,對其中一張連發 3 個 mousemove → 幾何重算次數不變", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    for (const code of CODES) {
      const card = await screen.findByTestId(`group-card-${code}`);
      // 錨點:卡片上真的是**單檔同款**那張圖(有 role=img 的主圖),不是舊 mini 圖 ——
      // 少了這條,「hover 沒重算」在根本沒有 hover 事件的元件上也會綠
      await waitFor(() => expect(card.querySelector('svg[role="img"]')).toBeTruthy());
    }
    const counted = vi.mocked(buildIntradayGeometry);
    const before = counted.mock.calls.length;

    const svg = screen.getByTestId("group-card-2330").querySelector('svg[role="img"]')!;
    for (const clientX of [10, 40, 90]) {
      fireEvent.mouseMove(svg, { clientX, clientY: 20 });
    }

    expect(counted.mock.calls.length).toBe(before);
  });
});
