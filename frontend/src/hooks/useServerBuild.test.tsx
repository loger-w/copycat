/** @vitest-environment jsdom */
/** `/api/health` 輪詢(SC-2)與 dev range 判別的來源選擇(SC-6;design C1/C3/C4/C5)。
 *
 *  用 renderHook 而不是 `wrap()`:`wrap()` 是 render 包裝,拿不到 hook 回傳值
 *  (repo 慣例見 useCapital.test.tsx)。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HEALTH_POLL_MS, useBuildDrift, useServerBuild } from "@/hooks/useServerBuild";

let fetchMock: ReturnType<typeof vi.fn>;

/** url substring → 回應工廠;未命中回 404。never-resolve 用 `() => new Promise(() => {})`。
 *  工廠每次呼叫都重新求值 → 測試中途要換行為改工廠內的旗標即可。 */
function routeFetch(routes: [string, () => Promise<Response>][]): ReturnType<typeof vi.fn> {
  return vi.fn((url: string) => {
    for (const [frag, make] of routes) {
      if (String(url).includes(frag)) return make();
    }
    return Promise.resolve(new Response(JSON.stringify({}), { status: 404 }));
  });
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function useRoutes(routes: [string, () => Promise<Response>][]): void {
  fetchMock = routeFetch(routes);
  vi.stubGlobal("fetch", fetchMock);
}

function callsTo(frag: string): number {
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes(frag)).length;
}

function urlsTo(frag: string): string[] {
  return fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes(frag));
}

function newClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function makeWrapper(client: QueryClient = newClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/** fake timers 下把 promise chain 排乾(fetch mock 回的是已解決的 promise)。 */
async function flush(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  useRoutes([]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("useServerBuild(SC-2)", () => {
  it("HEALTH_POLL_MS 是 60 秒(C7:輪詢節奏是契約,不是實作細節)", () => {
    expect(HEALTH_POLL_MS).toBe(60_000);
  });

  it("取回 /api/health 的 build 資訊", async () => {
    useRoutes([
      [
        "/api/health",
        () => json({ git_sha: "bbbbbbb", git_dirty: false, started_at: "2026-08-05T01:00:00" }),
      ],
    ]);
    const { result } = renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data?.git_sha).toBe("bbbbbbb"));
  });

  it(`每 ${HEALTH_POLL_MS}ms 輪詢一次(R8:fake timers 卡邊界)`, async () => {
    vi.useFakeTimers();
    useRoutes([["/api/health", () => json({ git_sha: "bbbbbbb" })]]);
    renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await flush();
    expect(callsTo("/api/health")).toBe(1);
    await flush(HEALTH_POLL_MS - 1);
    expect(callsTo("/api/health")).toBe(1);
    await flush(1);
    expect(callsTo("/api/health")).toBe(2);
  });

  it("HTTP 非 2xx → error 終態(retry:false,不等退避)", async () => {
    useRoutes([["/api/health", () => json({}, 500)]]);
    const { result } = renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it("兩條 query 的 staleTime 讓短時間內重掛不重打(C6:避免聚焦/重掛風暴)", async () => {
    vi.useFakeTimers();
    useRoutes([
      ["/api/health", () => json({ git_sha: "bbbbbbb" })],
      ["/__build/sha", () => json({ git_sha: "aaaaaaa", behind: false })],
    ]);
    const client = newClient();
    const hooks = () => {
      useServerBuild();
      useBuildDrift("bbbbbbb");
    };
    const first = renderHook(hooks, { wrapper: makeWrapper(client) });
    await flush();
    expect(callsTo("/api/health")).toBe(1);
    expect(callsTo("/__build/sha")).toBe(1);
    first.unmount();
    renderHook(hooks, { wrapper: makeWrapper(client) });
    await flush();
    expect(callsTo("/api/health")).toBe(1);
    expect(callsTo("/__build/sha")).toBe(1);
  });
});

describe("useBuildDrift(SC-6:dev range 判別)", () => {
  it("後端 sha 未知 → 根本不問 middleware(沒有 since 就沒有 range 可判)", async () => {
    useRoutes([["/__build/sha", () => json({ git_sha: "aaaaaaa", behind: true })]]);
    const { result } = renderHook(() => useBuildDrift(null), { wrapper: makeWrapper() });
    await act(async () => {
      await Promise.resolve();
    });
    expect(callsTo("/__build/sha")).toBe(0);
    expect(result.current).toEqual({ mode: "unknown", fe: null, behind: null });
  });

  it("帶 since=<後端 sha> 問 middleware,behind 原樣回傳", async () => {
    useRoutes([["/__build/sha", () => json({ git_sha: "aaaaaaa", behind: true })]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.behind).toBe(true));
    expect(urlsTo("/__build/sha")[0]).toContain("since=bbbbbbb");
    expect(result.current).toEqual({ mode: "range", fe: "aaaaaaa", behind: true });
  });

  it("冷態(未回前)回 unknown,不拿 define 舊值假造(R1/C1)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    useRoutes([["/__build/sha", () => new Promise<Response>(() => {})]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toEqual({ mode: "unknown", fe: null, behind: null });
  });

  it("404(build 產物沒有這條路徑)→ 降級 define 的等值比對", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    useRoutes([["/__build/sha", () => json({}, 404)]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.mode).toBe("equal"));
    expect(result.current).toEqual({ mode: "equal", fe: "aaaaaaa", behind: null });
  });

  it("500 等 transient error → unknown,**不**降級 define(C1:只有 404 是「這條路徑不存在」)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    useRoutes([["/__build/sha", () => json({}, 500)]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await waitFor(() => expect(callsTo("/__build/sha")).toBe(1));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(result.current).toEqual({ mode: "unknown", fe: null, behind: null });
  });

  it("暖態 error(問到過之後才失敗)沿用最後一次現算值,不回頭變 unknown(C4)", async () => {
    vi.useFakeTimers();
    let broken = false;
    useRoutes([
      ["/__build/sha", () => (broken ? json({}, 500) : json({ git_sha: "aaaaaaa", behind: true }))],
    ]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await flush();
    expect(result.current).toEqual({ mode: "range", fe: "aaaaaaa", behind: true });
    broken = true;
    await flush(HEALTH_POLL_MS);
    expect(callsTo("/__build/sha")).toBe(2);
    expect(result.current).toEqual({ mode: "range", fe: "aaaaaaa", behind: true });
  });

  it("middleware 回 git_sha null → fe 照樣 null,不拿 define 頂替(C5)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    useRoutes([["/__build/sha", () => json({ git_sha: null, behind: null })]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.mode).toBe("range"));
    expect(result.current).toEqual({ mode: "range", fe: null, behind: null });
  });

  it("非 DEV → 直接用 define 的等值比對,完全不打 /__build/sha(R3)", async () => {
    vi.stubEnv("DEV", false);
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    useRoutes([["/__build/sha", () => json({ git_sha: "ccccccc", behind: true })]]);
    const { result } = renderHook(() => useBuildDrift("bbbbbbb"), { wrapper: makeWrapper() });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toEqual({ mode: "equal", fe: "aaaaaaa", behind: null });
    expect(callsTo("/__build/sha")).toBe(0);
  });
});
