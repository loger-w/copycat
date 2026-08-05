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
  it("七檔:分時 / 1 / 5 / 15 / 30 / 60 分 / 日K", () => {
    expect(FUT_CHART_MODES.map(([m]) => m)).toEqual([
      "intraday",
      "m1",
      "m5",
      "m15",
      "m30",
      "m60",
      "day",
    ]);
    expect(FUT_CHART_MODES.map(([, label]) => label)).toEqual([
      "分時",
      "1分",
      "5分",
      "15分",
      "30分",
      "60分",
      "日K",
    ]);
  });

  it("isFutChartMode 就是 FUT_CHART_MODES 的值域(不留第二份白名單)", () => {
    for (const [m] of FUT_CHART_MODES) expect(isFutChartMode(m)).toBe(true);
    expect(isFutChartMode("m7")).toBe(false); // 個股才有的檔位
    expect(isFutChartMode("river")).toBe(false);
    expect(isFutChartMode("")).toBe(false);
  });
});

describe("futMinutesOf", () => {
  it("分 K 取數字,分時與日 K 回 1(不聚合)", () => {
    expect(futMinutesOf("m1")).toBe(1);
    expect(futMinutesOf("m5")).toBe(5);
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

  it("壞值 / 別頁的值 → 退回 intraday(不把 'm7' 這種個股檔位放行)", () => {
    for (const bad of ["m7", "day-k", "", "null", "{}"]) {
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
