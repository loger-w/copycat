/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";
import type { Watchlist } from "@/lib/watchlist-model";

const WL: Watchlist = {
  codes: ["2330", "5483", "3231"],
  groups: [
    { name: "主力", codes: ["2330", "5483"] },
    { name: "觀察", codes: ["3231"] },
  ],
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as Watchlist;
      return new Response(JSON.stringify(body));
    }
    return new Response(JSON.stringify(WL));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useStockWatchlist(v3 shape:codes + groups)", () => {
  it("讀取自選全體與群組", async () => {
    const hook = renderHook(() => useStockWatchlist(), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual(WL));
  });

  it("舊回應缺 codes → 由群組聯集補(與後端遷移規則一致)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ groups: WL.groups })),
    );
    const hook = renderHook(() => useStockWatchlist(), { wrapper });
    await waitFor(() =>
      expect(hook.result.current.data).toEqual({ codes: ["2330", "5483", "3231"], groups: WL.groups }),
    );
  });
});

describe("useSaveWatchlist", () => {
  it("PUT 整份 {codes, groups} 並回寫 cache", async () => {
    const hook = renderHook(() => ({ list: useStockWatchlist(), save: useSaveWatchlist() }), {
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    const next: Watchlist = { codes: ["2330"], groups: [{ name: "主力", codes: ["2330"] }] };
    await act(async () => {
      await hook.result.current.save.mutateAsync(next);
    });
    await waitFor(() => expect(hook.result.current.list.data).toEqual(next));
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String((putCall[1] as RequestInit).body))).toEqual(next);
  });

  it("回應缺 codes → 寫進 cache 的仍有 codes(不會在存檔成功後才崩)", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Watchlist;
        return new Response(JSON.stringify({ groups: body.groups })); // 舊後端形狀
      }
      return new Response(JSON.stringify(WL));
    });
    const hook = renderHook(() => ({ list: useStockWatchlist(), save: useSaveWatchlist() }), {
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    await act(async () => {
      await hook.result.current.save.mutateAsync({
        codes: ["2330"],
        groups: [{ name: "主力", codes: ["2330"] }],
      });
    });
    await waitFor(() => expect(hook.result.current.list.data?.codes).toEqual(["2330"]));
  });
});
