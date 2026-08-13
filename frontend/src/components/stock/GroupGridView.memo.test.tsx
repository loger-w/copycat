/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GroupGridView } from "@/components/stock/GroupGridView";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import type { Group } from "@/lib/watchlist-model";

/** review A6-1 的 regression lock:卡片 `memo` 有沒有真的擋下重畫。
 *
 *  這件事**在畫面上完全看不出來** —— memo 失效只是每秒多算 30 次分時幾何(最多
 *  271 格),圖照畫、值照對。失效的典型原因也不在卡片自己身上:父層每秒隨 `quotes`
 *  re-render,傳下去的 `onPick` 若是 inline arrow,`memo` 的比較每一輪都不會過。
 *
 *  量法 = 把 `MiniIntradayChart` 換成計次替身。**獨立檔**:`vi.mock` 是檔案級 + hoisted,
 *  與同目錄那份「要看到真 svg」的測試不能共存(frontend-testing skill 的 lazy 三坑同理)。 */

const hoisted = vi.hoisted(() => ({ renders: [] as (number | null)[] }));

vi.mock("@/components/stock/MiniIntradayChart", () => ({
  MiniIntradayChart: ({ liveP }: { liveP: number | null }) => {
    hoisted.renders.push(liveP);
    return <span data-testid="mini-stub" />;
  },
}));

const GROUPS: Group[] = [{ name: "半導體", codes: ["2330", "2317"] }];

function quote(over: Partial<WatchlistQuote> = {}): WatchlistQuote {
  return {
    p: null,
    chg_pct: null,
    vol: null,
    ref: null,
    upper: null,
    lower: null,
    no_data: false,
    trial: false,
    ...over,
  };
}

function state() {
  return {
    minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
    meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 1 },
    no_data: false,
    backfilling: false,
  };
}

beforeEach(() => {
  hoisted.renders.length = 0;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const codes = new URL(String(url), "http://x").searchParams.get("codes") ?? "";
      const picked: Record<string, unknown> = {};
      for (const c of codes.split(",").filter(Boolean)) picked[c] = state();
      return new Response(JSON.stringify({ states: picked }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GroupGridView 卡片 memo(review A6-1)", () => {
  it("只有一檔報價變 → 只有那張卡片重畫(父層每次都給新的 onPick)", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    // 每次都現做一個 inline arrow —— 正是 StockPage 的寫法,也是 memo 最容易破功的地方
    const ui = (quotes: Record<string, WatchlistQuote>) => (
      <QueryClientProvider client={client}>
        <GroupGridView groups={GROUPS} quotes={quotes} onPick={() => {}} />
      </QueryClientProvider>
    );

    const { rerender } = render(ui(q1));
    await waitFor(() => expect(screen.getAllByTestId("mini-stub")).toHaveLength(2));
    const before = hoisted.renders.length;

    // 只換 2317 那一格(`setWatchlist` 是 `{...prev, [code]: q}` → 其餘 entry 保持同參照)
    rerender(ui({ ...q1, "2317": quote({ p: 2_010_000 }) }));

    expect(hoisted.renders.length).toBe(before + 1);
    expect(hoisted.renders[hoisted.renders.length - 1]).toBe(2_010_000);
  });

  it("報價完全沒變(只是父層 re-render)→ 零重畫", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    const ui = () => (
      <QueryClientProvider client={client}>
        <GroupGridView groups={GROUPS} quotes={q1} onPick={() => {}} />
      </QueryClientProvider>
    );
    const { rerender } = render(ui());
    await waitFor(() => expect(screen.getAllByTestId("mini-stub")).toHaveLength(2));
    const before = hoisted.renders.length;
    rerender(ui());
    expect(hoisted.renders.length).toBe(before);
  });
});
