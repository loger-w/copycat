/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider, onlineManager, useMutation } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { createQueryClient } from "@/lib/query-client";

afterEach(() => {
  cleanup();
  onlineManager.setOnline(true);
});

function wrapperOf(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("createQueryClient(#237)", () => {
  it("mutations 層 networkMode = always;queries 層沒有 networkMode(prod 與測試同形)", () => {
    for (const client of [createQueryClient(), createQueryClient({ queries: { retry: false } })]) {
      const d = client.getDefaultOptions();
      expect(d.mutations?.networkMode).toBe("always");
      expect(d.queries?.networkMode).toBeUndefined();
      // 白名單:全站輪詢 hook 重連後照常重抓 —— TanStack 只在 queries 層 networkMode === "always"
      // 時才把 refetchOnReconnect 靜默關掉;放錯層這條就紅
      expect(client.defaultQueryOptions({ queryKey: ["x"] }).refetchOnReconnect).toBe(true);
    }
  });

  it("瀏覽器判離線時 mutation 立即失敗、不暫停排隊", async () => {
    onlineManager.setOnline(false);
    const client = createQueryClient({ queries: { retry: false } });
    const { result } = renderHook(
      () =>
        useMutation({
          mutationFn: async () => {
            throw new Error("loopback 也會真的失敗");
          },
        }),
      { wrapper: wrapperOf(client) },
    );
    act(() => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.isPaused).toBe(false);
  });

  it("對照:TanStack 預設 client 在離線時把同一筆 mutation 暫停(修前真錢曝險的形狀)", async () => {
    onlineManager.setOnline(false);
    const client = new QueryClient();
    let calls = 0;
    const { result } = renderHook(
      () =>
        useMutation({
          mutationFn: async () => {
            calls += 1;
          },
        }),
      { wrapper: wrapperOf(client) },
    );
    act(() => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isPaused).toBe(true));
    expect(result.current.status).toBe("pending");
    expect(calls).toBe(0); // mutationFn 根本沒被叫:單躺在佇列等「網路恢復 且 分頁聚焦」
  });
});
