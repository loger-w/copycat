/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWatchlistCommit } from "@/hooks/useWatchlistCommit";
import type { Watchlist } from "@/lib/watchlist-model";

const WL: Watchlist = { codes: ["2330"], groups: [{ name: "主力", codes: ["2330"] }] };

let putBodies: Watchlist[];

beforeEach(() => {
  putBodies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Watchlist;
        putBodies.push(body);
        return new Response(JSON.stringify(body));
      }
      return new Response(JSON.stringify(WL));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** review A4 SP1:`onSettled` 是**唯一保證會跑**的逐發回呼。三條零回呼早退(深比對零 PUT /
 *  基底未載入 / 世代作廢)沒有它,呼叫端的「在途」旗標只能掛在 onDone / onError 上 → 永久卡死。
 *  這裡直接釘 hook 契約,元件層(WatchlistManagerDialog.test)只釘可見行為。 */
describe("useWatchlistCommit onSettled", () => {
  it("深比對零 PUT 的早退(內容相同)仍呼 onSettled,且不呼 onDone / onError", async () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useWatchlistCommit({ seed: WL, onError }), { wrapper });
    const onDone = vi.fn();
    const onSettled = vi.fn();
    act(() => {
      // 同內容新物件:`isSameWatchlist` 早退,零 PUT、零 onDone、零 onError
      result.current.commit((base) => ({ ...base, groups: [...base.groups] }), onDone, onSettled);
    });
    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onDone).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(putBodies).toEqual([]);
  });

  it("基底從未載入(無 seed、query 未回)的早退仍呼 onSettled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})), // GET 永不回 → base 恆 null
    );
    const { result } = renderHook(() => useWatchlistCommit(), { wrapper });
    const onSettled = vi.fn();
    act(() => {
      result.current.commit((base) => base, undefined, onSettled);
    });
    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(putBodies).toEqual([]);
  });

  it("成功路徑:onError(null) → onDone → onSettled 三者都跑,順序固定", async () => {
    const calls: string[] = [];
    const { result } = renderHook(
      () => useWatchlistCommit({ seed: WL, onError: (c) => calls.push(`error:${String(c)}`) }),
      { wrapper },
    );
    act(() => {
      result.current.commit(
        (base) => ({ ...base, groups: [...base.groups, { name: "新組", codes: [] }] }),
        () => calls.push("done"),
        () => calls.push("settled"),
      );
    });
    await waitFor(() => expect(calls).toContain("settled"));
    expect(calls).toEqual(["error:null", "done", "settled"]);
    expect(putBodies).toHaveLength(1);
  });
});
