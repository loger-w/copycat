/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useChartToggles } from "@/hooks/useChartToggles";

const KEY = "copycat-chart-toggles";

beforeEach(() => {
  window.localStorage.removeItem(KEY);
});

afterEach(cleanup);

// 🔴 round4 項 6:bb 由預設關改為預設開(user 拍板「K 線圖都要顯示布林通道到 5ma 20ma」)
const DEFAULTS = { vwap: true, cdp: true, ma: false, bb: true };
/** 存檔 schema 版本(storage-only 欄位,不屬 ChartToggles) */
const V = 2;

function stored(): Record<string, unknown> {
  return JSON.parse(window.localStorage.getItem(KEY)!) as Record<string, unknown>;
}

describe("useChartToggles", () => {
  it("預設 vwap/cdp/bb 開、ma 關", () => {
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
  });

  it("set 更新並持久化 localStorage", () => {
    const hook = renderHook(() => useChartToggles());
    act(() => hook.result.current.set("cdp", false));
    expect(hook.result.current.toggles.cdp).toBe(false);
    expect(stored()).toEqual({ ...DEFAULTS, cdp: false, v: V });
    const hook2 = renderHook(() => useChartToggles());
    expect(hook2.result.current.toggles.cdp).toBe(false);
  });

  it("localStorage 壞 JSON → 回預設不炸", () => {
    window.localStorage.setItem(KEY, "{oops");
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
  });

  // 🔴 self-review R4-3:JSON.parse("null") 成功回 null,對 null 解構是 TypeError
  it("存檔內容是 JSON null → 回預設不炸(解構 null 會 throw)", () => {
    window.localStorage.setItem(KEY, "null");
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
  });

  it("存檔內容是 JSON 陣列 / 字串 → 回預設不炸", () => {
    window.localStorage.setItem(KEY, '"nope"');
    expect(renderHook(() => useChartToggles()).result.current.toggles).toEqual(DEFAULTS);
    cleanup();
    window.localStorage.setItem(KEY, "[1,2]");
    expect(renderHook(() => useChartToggles()).result.current.toggles).toEqual(DEFAULTS);
  });

  // 🔴 self-review R4-2:一次性升級是**新增的寫入路徑**(舊 load 只讀不寫),而所有既有
  // 使用者第一次載入必走它。setItem 在 Safari 私密視窗 / storage 被政策鎖時會拋
  // QuotaExceededError → useState(load) 的 initializer 拋錯 → 整個圖表元件首次 render 就掛。
  it("localStorage 寫入失敗 → 記憶體狀態照常生效,不讓元件崩潰", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ vwap: false, cdp: true, ma: false, bb: false }));
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const hook = renderHook(() => useChartToggles());
    // 升級後的值在記憶體內生效(只是這次沒落檔)
    expect(hook.result.current.toggles.bb).toBe(true);
    expect(hook.result.current.toggles.vwap).toBe(false);
    // set 也不能因為寫入失敗而炸
    act(() => hook.result.current.set("ma", true));
    expect(hook.result.current.toggles.ma).toBe(true);
    spy.mockRestore();
  });

  it("v 欄位不得洩進 toggles 物件(storage-only)", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ ...DEFAULTS, v: V }));
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles).toEqual(DEFAULTS);
    expect("v" in hook.result.current.toggles).toBe(false);
  });

  it("既有使用者的存檔不被新預設覆蓋(cdp 曾關過就維持關)", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ vwap: true, cdp: false, ma: false }));
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles.cdp).toBe(false);
  });

  // 🔴 round4 項 6:舊存檔的 bb:false 是「當時的預設」不是「使用者選了關」——
  // {...DEFAULTS, ...saved} 會讓它蓋掉新預設,user 的畫面永遠不會變。做一次性升級。
  describe("bb 預設開的一次性升級(v<2 → 開一次)", () => {
    it("無版本號的舊存檔:bb 被打開,其餘選擇不動,且升級後立刻落檔", () => {
      window.localStorage.setItem(KEY, JSON.stringify({ vwap: false, cdp: false, ma: true, bb: false }));
      const hook = renderHook(() => useChartToggles());
      expect(hook.result.current.toggles.bb).toBe(true);
      expect(hook.result.current.toggles.vwap).toBe(false);
      expect(hook.result.current.toggles.cdp).toBe(false);
      expect(hook.result.current.toggles.ma).toBe(true);
      // 沒落檔的話下次 load 會再打開一次 → 使用者關不掉(白名單 W-11)
      expect(stored().v).toBe(V);
      expect(stored().bb).toBe(true);
    });

    it("升級後使用者手動關掉 BB → 重新 mount 維持關(升級只做一次)", () => {
      window.localStorage.setItem(KEY, JSON.stringify({ vwap: true, cdp: true, ma: false, bb: false }));
      const first = renderHook(() => useChartToggles());
      expect(first.result.current.toggles.bb).toBe(true); // 升級生效
      act(() => first.result.current.set("bb", false)); // user 明確關掉
      cleanup();
      const second = renderHook(() => useChartToggles());
      expect(second.result.current.toggles.bb).toBe(false);
    });
  });

  // 🟢 SC-3:新增 `vp`(量分佈)預設開。**刻意不 bump TOGGLES_VERSION** ——
  // 版本升級要處理的是「既有鍵的預設改了」(bb 前例:存檔裡的 false 是舊預設不是使用者選的),
  // 而 vp 是全新的鍵,舊存檔根本沒有它,`{...DEFAULTS, ...flags}` 自然就補上新預設。
  // 這條鎖的是「不 bump 也真的拿得到預設」,而不是版本號本身。
  it("舊存檔沒有 vp 鍵 → 預設開,且不影響存檔裡既有的選擇", () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ vwap: true, cdp: false, ma: false, bb: true, v: V }),
    );
    const hook = renderHook(() => useChartToggles());
    expect(hook.result.current.toggles.vp).toBe(true);
    expect(hook.result.current.toggles.cdp).toBe(false);
  });

  // 🔴 R21:StockChart(持有 bb)與 StockIntradayChart(持有 vwap/cdp/ma)是兩個 instance,
  // set 若用自己那份 stale prev 整包寫回,後寫的一方會回滾對方剛做的變更。
  it("兩個 instance 交替 set 不互相覆蓋(set 先重讀 localStorage 再 merge)", () => {
    const a = renderHook(() => useChartToggles());
    const b = renderHook(() => useChartToggles()); // b 的 prev 停在 mount 當下
    act(() => a.result.current.set("cdp", false));
    act(() => b.result.current.set("bb", false));
    expect(stored()).toEqual({
      vwap: true,
      cdp: false, // ← 沒有被 b 的 stale prev 還原成 true
      ma: false,
      bb: false,
      v: V,
    });
  });
});
