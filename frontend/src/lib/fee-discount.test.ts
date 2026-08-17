/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FEE_DISCOUNT_KEY } from "@/lib/constants";
import { persistDiscount, readFeeDiscount, useFeeDiscount } from "@/lib/fee-discount";
import { FEE_DISCOUNT_DEFAULT } from "@/lib/ladder-position";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("readFeeDiscount", () => {
  it("未設過 → 預設折數", () => {
    expect(readFeeDiscount()).toBe(FEE_DISCOUNT_DEFAULT);
  });

  it("合法值照讀", () => {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, "3");
    expect(readFeeDiscount()).toBe(3);
  });

  it("壞值(非數 / 出界)→ 預設,不是 NaN", () => {
    for (const bad of ["abc", "", "0", "-1", "11"]) {
      window.localStorage.setItem(FEE_DISCOUNT_KEY, bad);
      expect(readFeeDiscount()).toBe(FEE_DISCOUNT_DEFAULT);
    }
  });

  // 私密視窗 / storage 被政策鎖時光是存取就會拋 —— 三處倉位顯示在 render 期間讀它,
  // 拋出去就是整個側欄 / 圖牆掛掉
  it("localStorage 拋錯 → 預設(不往外拋)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readFeeDiscount()).toBe(FEE_DISCOUNT_DEFAULT);
  });
});

describe("useFeeDiscount", () => {
  it("初值 = 存檔折數", () => {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, "2.5");
    const hook = renderHook(() => useFeeDiscount());
    expect(hook.result.current).toBe(2.5);
  });

  /** 折數的唯一輸入口在閃電梯的折數框(persistDiscount)。三處倉位顯示要在同一 tick
   *  收斂到同一個數字 —— 少了通知就是「梯上改了折數,側欄 / 卡片還印著舊損益」,
   *  兩個數字並存而畫面上看不出哪個才對。 */
  it("persistDiscount 之後拿到新值(同分頁通知)", () => {
    const hook = renderHook(() => useFeeDiscount());
    expect(hook.result.current).toBe(FEE_DISCOUNT_DEFAULT);
    act(() => {
      persistDiscount(3);
    });
    expect(hook.result.current).toBe(3);
  });

  it("多個訂閱者同時收到通知", () => {
    const a = renderHook(() => useFeeDiscount());
    const b = renderHook(() => useFeeDiscount());
    act(() => {
      persistDiscount(4.5);
    });
    expect([a.result.current, b.result.current]).toEqual([4.5, 4.5]);
  });
});
