/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useChartToggles } from "@/hooks/useChartToggles";

const KEY = "copycat-chart-toggles";

beforeEach(() => {
  window.localStorage.removeItem(KEY);
});

afterEach(cleanup);

const DEFAULTS = { vwap: true, cdp: true, ma: false, bb: false };

describe("useChartToggles", () => {
  // 🔴 SC-3:CDP 由預設關改為預設開(user 拍板);同時新增 bb(布林,預設關)
  it("預設 vwap/cdp 開、ma/bb 關", () => {
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
  });

  it("set 更新並持久化 localStorage", () => {
    const hook = renderHook(() => useChartToggles());
    act(() => hook.result.current.set("cdp", false));
    expect(hook.result.current.toggles.cdp).toBe(false);
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({ ...DEFAULTS, cdp: false });
    const hook2 = renderHook(() => useChartToggles());
    expect(hook2.result.current.toggles.cdp).toBe(false);
  });

  it("localStorage 壞 JSON → 回預設不炸", () => {
    window.localStorage.setItem(KEY, "{oops");
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
  });

  it("既有使用者的存檔不被新預設覆蓋(cdp 曾關過就維持關)", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ vwap: true, cdp: false, ma: false }));
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles.cdp).toBe(false);
    expect(hook.result.current.toggles.bb).toBe(false); // 新 key 由 DEFAULTS 補
  });

  // 🔴 R21:StockChart(持有 bb)與 StockIntradayChart(持有 vwap/cdp/ma)是兩個 instance,
  // set 若用自己那份 stale prev 整包寫回,後寫的一方會回滾對方剛做的變更。
  it("兩個 instance 交替 set 不互相覆蓋(set 先重讀 localStorage 再 merge)", () => {
    const a = renderHook(() => useChartToggles());
    const b = renderHook(() => useChartToggles()); // b 的 prev 停在 mount 當下
    act(() => a.result.current.set("cdp", false));
    act(() => b.result.current.set("bb", true));
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({
      vwap: true,
      cdp: false, // ← 沒有被 b 的 stale prev 還原成 true
      ma: false,
      bb: true,
    });
  });
});
