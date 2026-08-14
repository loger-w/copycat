/** @vitest-environment jsdom */
/** 真身級「非 corr subtab = 零 WebSocket」鎖(SC-5;round-2 P1-1)。
 *
 *  改版前這條保護在 `CorrSection.lazy.test.tsx` (b)(「收合態零建線」),而收合殼被
 *  subtab 取代後,唯一的掛載閘移到了 `IndexPage` —— 鎖必須跟著搬到新的掛載點。
 *
 *  **本檔刻意不 mock CorrPage**:`IndexPage.test.tsx` 的檔案級 stub 不會建線,
 *  「stub 下 WS 數為 0」恆真 = 沒有鑑別力。錨點文字取 RiverPanel 的「等待六腿資料…」,
 *  與 Suspense fallback 的「相關係數載入中…」逐字可區分。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

const TWSE: IndexSeries = {
  p: 42_039_920,
  ref: 43_634_190,
  high: 43_221_930,
  low: 41_815_780,
  stale: false,
  minutes: { "0901": 43_000_000 },
};
const TXF: TxfQuote = { p: 42_142_000, time: "10:16:10" };

/** 預設 subtab = 漲跌停 → `LimitListBody` 每次都真掛且真打這條路由(P0-2)。 */
const BREADTH_ROWS = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [],
};

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/market/breadth/rows")) {
        return new Response(JSON.stringify(BREADTH_ROWS));
      }
      // corr / river 兩支 hook 的初載 REST 回 404 → state 維持 null(引擎未就緒的正常降級)
      return new Response(null, { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IndexPage twse={TWSE} otc={null} txf={TXF} breadth={null} />
    </QueryClientProvider>,
  );
}

function subtab(name: string): HTMLElement {
  return within(screen.getByRole("tablist", { name: "台股綜合分頁" })).getByRole("tab", { name });
}

describe("IndexPage × CorrPage(lazy 真身)", () => {
  it("預設 subtab(漲跌停)零 WebSocket;切到相關係數才建 corr + river 兩條", async () => {
    renderPage();
    await act(async () => {});

    expect(screen.queryByText("等待六腿資料…")).toBeNull();
    expect(FakeWS.instances).toEqual([]);

    // 正向對照:少了這半,「零 WS」對「corr 整條路徑壞掉」也會綠(vacuous)
    fireEvent.click(subtab("相關係數"));

    expect(await screen.findByText("等待六腿資料…")).toBeTruthy();
    expect(screen.queryByText("相關係數載入中…")).toBeNull();
    expect(FakeWS.instances.map((w) => w.url.replace(/^ws:\/\/[^/]+/, ""))).toEqual([
      "/ws/corr",
      "/ws/river",
    ]);
  });
});
