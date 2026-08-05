/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  errText,
  useDeleteRule,
  useSaveRule,
  useSignalRules,
  type RuleDraft,
  type SignalRule,
} from "@/hooks/useSignalRules";

function rule(o: Partial<SignalRule> = {}): SignalRule {
  return {
    id: "r-1-000",
    name: "CDP 穿越",
    kind: "cdp_cross",
    enabled: true,
    notify_discord: true,
    cooldown_secs: 300,
    params: { rearm_ticks: 2 },
    cdp_levels: ["ah", "nh", "cdp", "nl", "al"],
    ...o,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

beforeEach(() => {
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    if (init?.method === "POST" || init?.method === "PUT") {
      return new Response(String(init.body));
    }
    return new Response(JSON.stringify({ rules: [rule()] }));
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

/** 每個回呼固定用同一份 method + url 取法:mock.calls 的元素型別是 unknown[]。 */
function lastCall(): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls.at(-1) as [string, RequestInit | undefined];
  return { url: call[0], init: call[1] ?? {} };
}

describe("useSignalRules", () => {
  it("GET /api/stock/signals/rules → rules 陣列", async () => {
    const hook = renderHook(() => useSignalRules(), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual([rule()]));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/stock/signals/rules");
  });

  it("缺 rules 欄(舊後端 / 壞回應)→ 空陣列而非 undefined", async () => {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({})));
    const hook = renderHook(() => useSignalRules(), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toEqual([]));
  });
});

describe("useSaveRule", () => {
  it("無 id → POST /api/stock/signals/rules(新增)", async () => {
    const hook = renderHook(() => useSaveRule(), { wrapper });
    const full = rule();
    const draft: RuleDraft = {
      name: full.name,
      kind: full.kind,
      enabled: full.enabled,
      notify_discord: full.notify_discord,
      cooldown_secs: full.cooldown_secs,
      params: full.params,
      cdp_levels: full.cdp_levels,
    };
    await act(async () => {
      await hook.result.current.mutateAsync(draft);
    });
    const { url, init } = lastCall();
    expect(url).toBe("/api/stock/signals/rules");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(draft);
  });

  it("有 id → PUT /api/stock/signals/rules/{id}(編輯,id 進 path)", async () => {
    const hook = renderHook(() => useSaveRule(), { wrapper });
    await act(async () => {
      await hook.result.current.mutateAsync(rule({ id: "r-9-007", enabled: false }));
    });
    const { url, init } = lastCall();
    expect(url).toBe("/api/stock/signals/rules/r-9-007");
    expect(init.method).toBe("PUT");
    expect((JSON.parse(String(init.body)) as SignalRule).enabled).toBe(false);
  });

  it("成功後 invalidate [\"signal-rules\"] → 清單重抓", async () => {
    const hook = renderHook(
      () => ({ list: useSignalRules(), save: useSaveRule() }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    const before = fetchMock.mock.calls.length;
    await act(async () => {
      await hook.result.current.save.mutateAsync(rule({ enabled: false }));
    });
    // PUT 一次 + invalidate 觸發的 GET 一次
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(before + 2));
    expect(lastCall().init.method).toBeUndefined(); // 最後一發是 GET
  });

  it("400 INVALID_RULE → error.message 是 detail.error", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { error: "INVALID_RULE" } }), { status: 400 }),
    );
    const hook = renderHook(() => useSaveRule(), { wrapper });
    await expect(hook.result.current.mutateAsync(rule())).rejects.toThrow("INVALID_RULE");
  });
});

describe("useDeleteRule", () => {
  it("DELETE /api/stock/signals/rules/{id} + invalidate", async () => {
    const hook = renderHook(
      () => ({ list: useSignalRules(), del: useDeleteRule() }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.list.data).toBeTruthy());
    const before = fetchMock.mock.calls.length;
    await act(async () => {
      await hook.result.current.del.mutateAsync("r-1-000");
    });
    expect(fetchMock.mock.calls[before]?.[0]).toBe("/api/stock/signals/rules/r-1-000");
    expect((fetchMock.mock.calls[before]?.[1] as RequestInit).method).toBe("DELETE");
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(before + 2));
  });

  it("404 RULE_NOT_FOUND → error.message 是 detail.error", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { error: "RULE_NOT_FOUND" } }), { status: 404 }),
    );
    const hook = renderHook(() => useDeleteRule(), { wrapper });
    await expect(hook.result.current.mutateAsync("nope")).rejects.toThrow("RULE_NOT_FOUND");
  });
});

describe("errText", () => {
  it("三個錯誤碼各有中文文案,其餘退回通用文案", () => {
    expect(errText("INVALID_RULE")).toBe("規則設定不合法");
    expect(errText("RULE_NOT_FOUND")).toBe("找不到該規則");
    expect(errText("RULE_SAVE_FAILED")).toBe("規則儲存失敗");
    expect(errText("HTTP_503")).toBe("儲存失敗");
  });
});
