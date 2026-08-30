import { describe, expect, it } from "vitest";

import { KIND_TEXT, closeBodyOf, kindOf } from "@/lib/close-order";
import type { CapitalPosition } from "@/types";

function pos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec",
    stock_no: "2330",
    qty: 2,
    name: "台積電",
    avg_price: 1000,
    kind: "cash",
    pnl_base: 1500,
    pnl_base_price: 1050,
    pnl_cost: 2_000_000,
    avg_source: null,
    today_qty: 0,
    code: null,
    ...overrides,
  };
}

describe("closeBodyOf 稽核分流(N082 / review SP3)", () => {
  const pos = {
    market: "fut",
    stock_no: "TXFI6",
    qty: -2,
    name: "臺股期貨",
    avg_price: 23_000,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    avg_source: null,
    today_qty: 0,
    code: null,
  } as unknown as Parameters<typeof closeBodyOf>[0];

  it("未帶 source → body 無 source 欄(後端預設 panel,舊契約零改)", () => {
    expect("source" in closeBodyOf(pos, 25_080)).toBe(false);
  });

  it("鎖定態 → source = flash-locked", () => {
    expect(closeBodyOf(pos, 25_080, "flash-locked").source).toBe("flash-locked");
  });
});

describe("kindOf / KIND_TEXT(值域單一定義)", () => {
  it("PositionKind 四值認得(daytrade_sell 自 2026-08-30 無券空單校準起)", () => {
    expect(kindOf(pos({ kind: "cash" }))).toBe("cash");
    expect(kindOf(pos({ kind: "margin" }))).toBe("margin");
    expect(kindOf(pos({ kind: "short" }))).toBe("short");
    expect(kindOf(pos({ kind: "daytrade_sell" }))).toBe("daytrade_sell");
  });

  it("值域外字串(舊後端 / 未來新值)認不得 → null", () => {
    expect(kindOf(pos({ kind: "" }))).toBe(null);
    expect(kindOf(pos({ kind: "borrowless" }))).toBe(null);
  });

  it("KIND_TEXT 鍵集 = kindOf 的值域(不留第二份白名單)", () => {
    expect(Object.keys(KIND_TEXT).sort()).toEqual(["cash", "daytrade_sell", "margin", "short"]);
    expect(KIND_TEXT.cash).toEqual({ short: "現", full: "現股" });
    expect(KIND_TEXT.margin).toEqual({ short: "資", full: "融資" });
    expect(KIND_TEXT.short).toEqual({ short: "券", full: "融券" });
    expect(KIND_TEXT.daytrade_sell).toEqual({ short: "無", full: "無券" });
  });

  it("無券空單列的平倉 body 帶 kind(部位面板標「無券」就送得出去;後端精確鍵到空單列)", () => {
    const body = closeBodyOf(pos({ kind: "daytrade_sell", qty: -1 }), 523_000);
    expect(body.kind).toBe("daytrade_sell");
  });

  it("原型鏈上的名字不被當成合法 kind(`in` 判定的經典漏洞)", () => {
    expect(kindOf(pos({ kind: "toString" }))).toBe(null);
    expect(kindOf(pos({ kind: "constructor" }))).toBe(null);
  });
});

describe("closeBodyOf(SC-10 送單面;兩呼叫端同形)", () => {
  it("fut 不送 kind —— OI 列沒有庫存種類這一維(既有測試的 body 形狀)", () => {
    const p = pos({ market: "fut", stock_no: "TXFI6", kind: "cash", qty: 2 });
    expect(closeBodyOf(p, 23_000)).toEqual({
      market: "fut",
      key: "TXFI6",
      price: 23_000,
      qty: 2,
    });
  });

  it("sec 且 kindOf 非 null → 附 kind(既有測試的 body 形狀)", () => {
    expect(closeBodyOf(pos({ kind: "cash", qty: 1 }), 985)).toEqual({
      market: "sec",
      key: "2330",
      price: 985,
      qty: 1,
      kind: "cash",
    });
    expect(closeBodyOf(pos({ kind: "margin", qty: 3 }), 985)).toEqual({
      market: "sec",
      key: "2330",
      price: 985,
      qty: 3,
      kind: "margin",
    });
  });

  it("sec 但 kind 值域外(舊後端 / 未來新值)→ 不送 kind(退回「同檔唯一列」語意)", () => {
    expect(closeBodyOf(pos({ kind: "borrowless", qty: 1 }), 985)).toEqual({
      market: "sec",
      key: "2330",
      price: 985,
      qty: 1,
    });
  });

  it("key = stock_no,**不是** rowKeyOf 的複合鍵(複合鍵只用於 UI 列選取)", () => {
    expect(closeBodyOf(pos(), 985).key).toBe("2330");
  });

  it("空單(qty 負)送絕對值口數", () => {
    const body = closeBodyOf(pos({ market: "fut", stock_no: "TXFI6", qty: -3 }), 24_000);
    expect(body.qty).toBe(3);
  });

  it("qty 由 helper 內部給,不開參數 —— 兩個呼叫端 body 必然同形", () => {
    // 同一個 pos 只換 market:鍵集的差異**只有** kind 一維(qty / price / key 不隨之變),
    // 這是「兩個呼叫端各自組 body 也不會漂移」的實質內容
    const base = { stock_no: "TXFI6", qty: 2, kind: "cash" } as const;
    const futKeys = Object.keys(closeBodyOf(pos({ ...base, market: "fut" }), 23_000)).sort();
    const secKeys = Object.keys(closeBodyOf(pos({ ...base, market: "sec" }), 23_000)).sort();
    expect(futKeys).toEqual(["key", "market", "price", "qty"]);
    expect(secKeys).toEqual(["key", "kind", "market", "price", "qty"]);
    expect(secKeys.filter((k) => !futKeys.includes(k))).toEqual(["kind"]);
  });
});
