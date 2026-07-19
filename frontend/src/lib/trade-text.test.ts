import { describe, expect, it } from "vitest";

import { orderSideText, orderStatusText, tradeErrorText } from "@/lib/trade-text";

describe("tradeErrorText", () => {
  it("已知錯誤碼轉繁中", () => {
    expect(tradeErrorText("TOUCHANCE_DOWN")).toBe("達錢未連線");
    expect(tradeErrorText("PREVIEW_EXPIRED")).toContain("重新送單");
    expect(tradeErrorText("BROKER_REJECTED")).toBe("券商拒單");
  });

  it("未知碼原樣顯示", () => {
    expect(tradeErrorText("HTTP_500")).toBe("HTTP_500");
  });
});

describe("orderStatusText", () => {
  it("常見狀態碼轉繁中,未知回原值", () => {
    expect(orderStatusText("2")).toBe("全部成交");
    expect(orderStatusText("XYZ")).toBe("XYZ");
  });
});

describe("orderSideText", () => {
  it("1=買 2=賣,未知原樣", () => {
    expect(orderSideText("1")).toBe("買");
    expect(orderSideText("2")).toBe("賣");
    expect(orderSideText("?")).toBe("?");
  });
});
