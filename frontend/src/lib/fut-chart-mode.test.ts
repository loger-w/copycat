/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from "vitest";

import { FUT_CHART_MODE_KEY, ORPHAN_STORAGE_KEYS, purgeOrphanKeys } from "@/lib/constants";
import {
  FUT_CHART_MODES,
  futMinutesOf,
  initialFutChartMode,
  isFutChartMode,
  persistFutChartMode,
} from "@/lib/fut-chart-mode";

afterEach(() => {
  window.localStorage.clear();
});

describe("FUT_CHART_MODES", () => {
  it("15 檔:分時 / 1–10 分 / 15 / 30 / 60 分 / 日K", () => {
    expect(FUT_CHART_MODES.map(([m]) => m)).toEqual([
      "intraday",
      "m1",
      "m2",
      "m3",
      "m4",
      "m5",
      "m6",
      "m7",
      "m8",
      "m9",
      "m10",
      "m15",
      "m30",
      "m60",
      "day",
    ]);
    expect(FUT_CHART_MODES.map(([, label]) => label)).toEqual([
      "分時",
      "1分",
      "2分",
      "3分",
      "4分",
      "5分",
      "6分",
      "7分",
      "8分",
      "9分",
      "10分",
      "15分",
      "30分",
      "60分",
      "日K",
    ]);
  });

  it("isFutChartMode 就是 FUT_CHART_MODES 的值域(不留第二份白名單)", () => {
    for (const [m] of FUT_CHART_MODES) expect(isFutChartMode(m)).toBe(true);
    expect(isFutChartMode("m7")).toBe(true); // 1–10 連續後 m7 進值域
    expect(isFutChartMode("m11")).toBe(false); // 11–14 不在表上
    expect(isFutChartMode("m0")).toBe(false);
    expect(isFutChartMode("m61")).toBe(false);
    expect(isFutChartMode("river")).toBe(false);
    expect(isFutChartMode("")).toBe(false);
  });
});

describe("futMinutesOf", () => {
  it("分 K 取數字,分時與日 K 回 1(不聚合)", () => {
    expect(futMinutesOf("m1")).toBe(1);
    expect(futMinutesOf("m5")).toBe(5);
    expect(futMinutesOf("m7")).toBe(7);
    expect(futMinutesOf("m10")).toBe(10);
    expect(futMinutesOf("m15")).toBe(15);
    expect(futMinutesOf("m30")).toBe(30);
    expect(futMinutesOf("m60")).toBe(60);
    expect(futMinutesOf("intraday")).toBe(1);
    expect(futMinutesOf("day")).toBe(1);
  });
});

describe("localStorage 還原(白名單驗證)", () => {
  it("未設 → 預設 intraday", () => {
    expect(initialFutChartMode()).toBe("intraday");
  });

  it("合法值原樣還原", () => {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m30");
    expect(initialFutChartMode()).toBe("m30");
  });

  it("壞值 / 別頁的值 → 退回 intraday(不把 'm11' 這種白名單外的值放行)", () => {
    for (const bad of ["m11", "m0", "m61", "day-k", "", "null", "{}"]) {
      window.localStorage.setItem(FUT_CHART_MODE_KEY, bad);
      expect(initialFutChartMode()).toBe("intraday");
    }
  });

  it("persistFutChartMode 寫入的值讀得回來(寫讀同一把鍵)", () => {
    persistFutChartMode("m60");
    expect(window.localStorage.getItem(FUT_CHART_MODE_KEY)).toBe("m60");
    expect(initialFutChartMode()).toBe("m60");
  });

  it("key 前綴 copycat- 且不在孤兒清單裡(purgeOrphanKeys 不得清掉它)", () => {
    expect(FUT_CHART_MODE_KEY).toBe("copycat-fut-chart-mode");
    expect((ORPHAN_STORAGE_KEYS as readonly string[]).includes(FUT_CHART_MODE_KEY)).toBe(false);
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m15");
    purgeOrphanKeys();
    expect(window.localStorage.getItem(FUT_CHART_MODE_KEY)).toBe("m15");
  });
});
