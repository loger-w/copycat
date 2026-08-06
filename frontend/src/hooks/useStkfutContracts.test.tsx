/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStkfutContracts } from "@/hooks/useStkfutContracts";

/** 個股期合約清單(stkfut-contracts SC-4)。後端 `GET /api/stock/stkfut/contracts/{code}`
 *  的 404 = **這檔沒有期貨**,是正常狀態不是錯誤 —— 這條分界是本檔的主訴:
 *  當成錯誤會讓下拉在「沒期貨」與「TC4 斷線」兩種情況下長得一樣。 */

const BODY = {
  code: "2330",
  name: "台積電",
  std: { prod: "CDF", contracts: ["202608", "202609"] },
  mini: { prod: "QFF", contracts: ["202608", "202609"] },
};

let fetchMock: ReturnType<typeof vi.fn>;
let queryClient: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  fetchMock = vi.fn(async () => new Response(JSON.stringify(BODY)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useStkfutContracts", () => {
  it("200 → 標準 + 小型兩腿", async () => {
    const hook = renderHook(() => useStkfutContracts("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.data).not.toBeUndefined());
    expect(fetchMock).toHaveBeenCalledWith("/api/stock/stkfut/contracts/2330");
    expect(hook.result.current.data?.std.prod).toBe("CDF");
    expect(hook.result.current.data?.std.contracts).toEqual(["202608", "202609"]);
    expect(hook.result.current.data?.mini?.prod).toBe("QFF");
  });

  it("404 NO_STKFUT → data 為 null 且非錯誤態(這檔沒期貨)", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { error: "NO_STKFUT" } }), { status: 404 }),
    );
    const hook = renderHook(() => useStkfutContracts("9999"), { wrapper });
    await waitFor(() => expect(hook.result.current.isPending).toBe(false));
    expect(hook.result.current.data).toBeNull();
    expect(hook.result.current.isError).toBe(false);
  });

  it("502 TC4_DOWN 是錯誤,不降級成「沒期貨」", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "TC4_DOWN" } }), { status: 502 }),
    );
    const hook = renderHook(() => useStkfutContracts("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    expect(hook.result.current.data).toBeUndefined();
  });

  it("code=null 不發請求(未選檔)", async () => {
    const hook = renderHook(() => useStkfutContracts(null), { wrapper });
    await waitFor(() => expect(hook.result.current.fetchStatus).toBe("idle"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
