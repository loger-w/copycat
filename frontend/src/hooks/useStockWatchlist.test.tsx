/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { codes: string[] };
      return new Response(JSON.stringify({ codes: body.codes }));
    }
    return new Response(JSON.stringify({ codes: ["2330"] }));
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

describe("useStockWatchlist", () => {
  it("讀取清單", async () => {
    const hook = renderHook(() => useStockWatchlist(), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual(["2330"]));
  });
});

describe("useSaveWatchlist", () => {
  it("PUT 整份並回寫 cache", async () => {
    const hook = renderHook(
      () => ({ list: useStockWatchlist(), save: useSaveWatchlist() }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    await act(async () => {
      await hook.result.current.save.mutateAsync(["2330", "5483"]);
    });
    await waitFor(() => expect(hook.result.current.list.data).toEqual(["2330", "5483"]));
  });
});
