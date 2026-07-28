/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useChartToggles } from "@/hooks/useChartToggles";

const KEY = "copycat-chart-toggles";

beforeEach(() => {
  window.localStorage.removeItem(KEY);
});

afterEach(cleanup);

describe("useChartToggles", () => {
  it("預設 vwap 開、cdp/ma 關", () => {
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual({ vwap: true, cdp: false, ma: false });
  });

  it("set 更新並持久化 localStorage", () => {
    const hook = renderHook(() => useChartToggles());
    act(() => hook.result.current.set("cdp", true));
    expect(hook.result.current.toggles.cdp).toBe(true);
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({
      vwap: true,
      cdp: true,
      ma: false,
    });
    const hook2 = renderHook(() => useChartToggles());
    expect(hook2.result.current.toggles.cdp).toBe(true);
  });

  it("localStorage 壞 JSON → 回預設不炸", () => {
    window.localStorage.setItem(KEY, "{oops");
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual({ vwap: true, cdp: false, ma: false });
  });
});
