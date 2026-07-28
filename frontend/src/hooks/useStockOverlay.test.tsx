/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStockOverlay } from "@/hooks/useStockOverlay";

const OVERLAY = {
  cdp: { cdp: 101_750, ah: 104_750, nh: 103_500, nl: 100_500, al: 98_750 },
  ma5: 101_000,
  ma20: 100_500,
  date: "2026-07-25",
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify(OVERLAY)));
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

describe("useStockOverlay", () => {
  it("enabled 時抓取 /api/stock/overlay/{code}", async () => {
    const hook = renderHook(() => useStockOverlay("2330", true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual(OVERLAY));
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).toBe("/api/stock/overlay/2330");
  });

  it("enabled=false 或 code null 不發請求", async () => {
    renderHook(() => useStockOverlay("2330", false), { wrapper });
    renderHook(() => useStockOverlay(null, true), { wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
