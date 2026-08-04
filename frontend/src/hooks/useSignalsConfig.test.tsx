/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSignalsConfig } from "@/hooks/useSignalsConfig";
import type { SignalEnabled } from "@/lib/signal-model";

const ALL_ON: SignalEnabled = {
  cdp_cross: true,
  surge_crash: true,
  vol_burst: true,
  limit_lock: true,
};

let stored: SignalEnabled;
let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

beforeEach(() => {
  stored = { ...ALL_ON, vol_burst: false };
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      // 後端是部分更新:合併後回完整四鍵
      const body = JSON.parse(String(init.body)) as { enabled: Partial<SignalEnabled> };
      stored = { ...stored, ...body.enabled };
    }
    return new Response(JSON.stringify({ enabled: stored }));
  });
  vi.stubGlobal("fetch", fetchMock);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useSignalsConfig", () => {
  it("GET 往返四鍵開關", async () => {
    const hook = renderHook(() => useSignalsConfig(), { wrapper });
    await waitFor(() => expect(hook.result.current.enabled).toEqual(stored));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/stock/signals/enabled");
  });

  it("尚未載入 / 抓失敗 → 全開(fail-open,不會靜默清空整條訊號流)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    const hook = renderHook(() => useSignalsConfig(), { wrapper });
    expect(hook.result.current.enabled).toEqual(ALL_ON); // 載入中
    // hook 自帶 retry: 1(壓過 client 的 retry: false)→ 等第二次 fetch 發出才是 error
    // 終態;只等「呼叫過」會落在 retry pending 窗,那時的全開來自「還沒 settle」而不是
    // fail-open,實作把 fallback 拿掉照樣綠(review TQ-5)。retryDelay 預設 1s,waitFor
    // 的 1s 預設 timeout 抓不到 → 給 5s。
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2), { timeout: 5_000 });
    await waitFor(() =>
      expect(client.getQueryState(["stock-signals-enabled"])?.status).toBe("error"),
    );
    expect(hook.result.current.enabled).toEqual(ALL_ON);
  });

  it("save 只 PUT 要改的鍵,成功後直接回寫 cache(不必再 GET 一次)", async () => {
    const hook = renderHook(() => useSignalsConfig(), { wrapper });
    await waitFor(() => expect(hook.result.current.enabled.vol_burst).toBe(false));

    await act(async () => {
      await hook.result.current.save.mutateAsync({ vol_burst: true });
    });

    const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
    expect(put).toBeTruthy();
    expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({ enabled: { vol_burst: true } });
    await waitFor(() => expect(hook.result.current.enabled).toEqual(ALL_ON));
    // GET 一次 + PUT 一次:回寫 cache 而非 invalidate
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
