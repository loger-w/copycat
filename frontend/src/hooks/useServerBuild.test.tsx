/** @vitest-environment jsdom */
/** `/api/health` 輪詢與前端 sha 來源選擇(SC-2 / SC-6;design R1/R3/R8)。
 *
 *  用 renderHook 而不是 `wrap()`:`wrap()` 是 render 包裝,拿不到 hook 回傳值
 *  (repo 慣例見 useCapital.test.tsx)。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HEALTH_POLL_MS, useFrontendSha, useServerBuild } from "@/hooks/useServerBuild";

let fetchMock: ReturnType<typeof vi.fn>;

/** url substring → 回應工廠;未命中回 404。never-resolve 用 `() => new Promise(() => {})`。 */
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

function callsTo(frag: string): number {
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes(frag)).length;
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  fetchMock = routeFetch([]);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("useServerBuild(SC-2)", () => {
  it("取回 /api/health 的 build 資訊", async () => {
    fetchMock = routeFetch([
      ["/api/health", () => json({ git_sha: "bbbbbbb", git_dirty: false, started_at: "2026-08-05T01:00:00" })],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data?.git_sha).toBe("bbbbbbb"));
  });

  it(`每 ${HEALTH_POLL_MS}ms 輪詢一次(R8:fake timers 卡邊界)`, async () => {
    vi.useFakeTimers();
    fetchMock = routeFetch([["/api/health", () => json({ git_sha: "bbbbbbb" })]]);
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(callsTo("/api/health")).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEALTH_POLL_MS - 1);
    });
    expect(callsTo("/api/health")).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(callsTo("/api/health")).toBe(2);
  });

  it("HTTP 非 2xx → error 終態(retry:false,不等退避)", async () => {
    fetchMock = routeFetch([["/api/health", () => json({}, 500)]]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useServerBuild(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});

describe("useFrontendSha(SC-6 來源選擇)", () => {
  it("DEV 且 /__build/sha 未回前回 null(R1:不拿 define 舊值假造)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fetchMock = routeFetch([["/__build/sha", () => new Promise<Response>(() => {})]]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useFrontendSha(), { wrapper: makeWrapper() });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBeNull();
  });

  it("DEV 且 /__build/sha 回值 → 現算值優先於 define(R1)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fetchMock = routeFetch([["/__build/sha", () => json({ git_sha: "ccccccc" })]]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useFrontendSha(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current).toBe("ccccccc"));
  });

  it("DEV 但 /__build/sha 404(build 產物)→ settle 後降級 define(R3)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fetchMock = routeFetch([["/__build/sha", () => json({}, 404)]]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useFrontendSha(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current).toBe("aaaaaaa"));
  });

  it("非 DEV → 直接用 define,完全不打 /__build/sha(R3)", async () => {
    vi.stubEnv("DEV", false);
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fetchMock = routeFetch([["/__build/sha", () => json({ git_sha: "ccccccc" })]]);
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useFrontendSha(), { wrapper: makeWrapper() });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe("aaaaaaa");
    expect(callsTo("/__build/sha")).toBe(0);
  });
});
