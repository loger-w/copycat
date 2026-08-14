/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useIndexOverlay } from "@/hooks/useIndexOverlay";

const OVERLAY = {
  cdp: { cdp: 23_050_000, ah: 23_150_000, nh: 23_100_000, nl: 23_000_000, al: 22_950_000 },
  ma5: 23_020_000,
  ma20: 22_930_000,
  date: "2026-08-13",
};

const ALL_NULL = { cdp: null, ma5: null, ma20: null, date: null };

let urls: string[] = [];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    // retryDelay 0:hook 自帶 retry:1(覆寫 defaultOptions 的 retry),不歸零延遲的話
    // error 終態要等 exponential backoff 的 1s,fake timer 的推進語意會與重試糾纏
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  urls = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function stub(handler: (n: number) => Response): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return handler(urls.length);
    }),
  );
}

describe("useIndexOverlay(決策 10)", () => {
  it("enabled=false 不發請求", async () => {
    stub(() => new Response(JSON.stringify(OVERLAY)));
    renderHook(() => useIndexOverlay(false), { wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(urls).toEqual([]);
  });

  it("enabled=true 抓 /api/index/overlay 一次", async () => {
    stub(() => new Response(JSON.stringify(OVERLAY)));
    const hook = renderHook(() => useIndexOverlay(true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual(OVERLAY));
    expect(urls).toEqual(["/api/index/overlay"]);
  });

  // ⚠ RTL 的 waitFor 偵測不到 vitest fake timers(退回真 interval → timeout),
  //   以下兩條一律「手動 advance + 直接斷言」,不混用 waitFor(skill frontend-testing)。
  it("全 null(TC4 未起)→ 60s 後自動 refetch 補上", async () => {
    vi.useFakeTimers();
    stub((n) => new Response(JSON.stringify(n === 1 ? ALL_NULL : OVERLAY)));
    const hook = renderHook(() => useIndexOverlay(true), { wrapper });
    await vi.advanceTimersByTimeAsync(50);
    expect(urls.length).toBe(1);
    expect(hook.result.current.data).toEqual(ALL_NULL);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(urls.length).toBe(2);
    expect(hook.result.current.data).toEqual(OVERLAY);
    // 補上之後停掉輪詢(refetchInterval 是函式,每次到期重新求值)
    await vi.advanceTimersByTimeAsync(180_000);
    expect(urls.length).toBe(2);
  });

  it("503 error(engine 未就緒)→ 60s 後自動 refetch 補上", async () => {
    vi.useFakeTimers();
    stub((n) =>
      n <= 2
        ? new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 })
        : new Response(JSON.stringify(OVERLAY)),
    );
    const hook = renderHook(() => useIndexOverlay(true), { wrapper });
    // 首抓 + retry:1 的重試(wrapper 已把 retryDelay 歸零)
    await vi.advanceTimersByTimeAsync(50);
    expect(urls.length).toBe(2);
    expect(hook.result.current.isError).toBe(true);
    // error 態 data 是 undefined → 條件式必須查 status,查 data 會漏掉這條路
    expect(hook.result.current.data).toBeUndefined();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(urls.length).toBe(3);
    expect(hook.result.current.data).toEqual(OVERLAY);
  });
});
