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

describe("tradeErrorText(capital 錯誤碼)", () => {
  it("群益四碼轉繁中", () => {
    expect(tradeErrorText("CAPITAL_DISABLED")).toBe("群益未啟用");
    expect(tradeErrorText("CAPITAL_NOT_READY")).toBe("群益連線未就緒");
    expect(tradeErrorText("CAPITAL_DOWN")).toBe("群益連線故障");
    expect(tradeErrorText("ORDER_BLOCKED")).toBe("安全閘拒絕");
  });

  it("ORDER_BLOCKED 帶 reason 以後綴顯示", () => {
    expect(tradeErrorText("ORDER_BLOCKED:order_disabled")).toBe("安全閘拒絕(order_disabled)");
  });

  it("INVALID_ORDER 既有文案不變", () => {
    expect(tradeErrorText("INVALID_ORDER")).toBe("下單參數不合法");
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
