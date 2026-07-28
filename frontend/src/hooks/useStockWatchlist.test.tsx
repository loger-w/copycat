/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSaveWatchlist, useStockWatchlist, type Group } from "@/hooks/useStockWatchlist";

const GROUPS: Group[] = [
  { name: "主力", codes: ["2330", "5483"] },
  { name: "觀察", codes: ["3231"] },
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { groups: Group[] };
      return new Response(JSON.stringify({ groups: body.groups }));
    }
    return new Response(JSON.stringify({ groups: GROUPS }));
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

describe("useStockWatchlist(groups shape;舊 codes 斷言隨 API 契約遷移)", () => {
  it("讀取群組", async () => {
    const hook = renderHook(() => useStockWatchlist(), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual(GROUPS));
  });
});

describe("useSaveWatchlist", () => {
  it("PUT 整份 groups 並回寫 cache", async () => {
    const hook = renderHook(
      () => ({ list: useStockWatchlist(), save: useSaveWatchlist() }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    const next: Group[] = [{ name: "主力", codes: ["2330"] }];
    await act(async () => {
      await hook.result.current.save.mutateAsync(next);
    });
    await waitFor(() => expect(hook.result.current.list.data).toEqual(next));
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String((putCall[1] as RequestInit).body))).toEqual({ groups: next });
  });
});
