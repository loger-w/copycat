import { describe, expect, it } from "vitest";

import { fmt, fmtPct } from "@/lib/format";
import { positionEcon } from "@/lib/ladder-position";
import { DASH, pnlText } from "@/lib/pnl-format";
import {
  cardText,
  chipText,
  chipTitle,
  chipTone,
  futQtyText,
  futSummary,
  headerSegments,
  positionsByCode,
  secQtyText,
  secSummary,
  unmappedFutCount,
  type FutSummary,
  type SecSummary,
} from "@/lib/position-summary";
import type { CapitalPosition } from "@/types";

/** 現價 1000 元(毫元通貨)。均價 985.2 → 多方小賺,含費稅後才知道賺多少。 */
const LAST = 1_000_000;
const DISCOUNT = 1.8;

function pos(over: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec",
    stock_no: "2330",
    qty: 3,
    name: "台積電",
    avg_price: 985.2,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    avg_source: null,
    today_qty: 0,
    code: "2330",
    ...over,
  };
}

function fut(over: Partial<CapitalPosition> = {}): CapitalPosition {
  return pos({
    market: "fut",
    stock_no: "CDFI6",
    qty: 2,
    avg_price: 985,
    pnl_base: 500,
    code: "2330",
    ...over,
  });
}

/** 非 null 斷言的替身:回 null 就是「這組 fixture 根本沒有 sec 倉」,測試該炸而不是靜默略過。 */
function secOf(
  rows: readonly CapitalPosition[],
  last: number | null = LAST,
  discount = DISCOUNT,
): SecSummary {
  const s = secSummary(rows, last, discount);
  if (s === null) throw new Error("expected sec summary");
  return s;
}

function futOf(rows: readonly CapitalPosition[]): FutSummary {
  const f = futSummary(rows);
  if (f === null) throw new Error("expected fut summary");
  return f;
}

describe("positionsByCode", () => {
  it("sec 以股號為鍵、fut 以後端附的 code 為鍵 → 同一檔的現股與個股期落在同一格", () => {
    const map = positionsByCode([pos(), fut()]);
    expect([...map.keys()]).toEqual(["2330"]);
    expect(map.get("2330")?.map((p) => p.stock_no)).toEqual(["2330", "CDFI6"]);
  });

  it("qty 0 的列過濾掉(不是部位)", () => {
    expect(positionsByCode([pos({ qty: 0 })]).size).toBe(0);
  });

  // 除權息調整碼 / 對映表沒 refresh → code null。猜一個股號比不顯示更糟
  it("fut 的 code null → 跳過(前端沒有契約碼→股號的反查)", () => {
    const map = positionsByCode([fut({ stock_no: "EE1I6", code: null })]);
    expect(map.size).toBe(0);
  });

  it("undefined(capital 未啟用 / 查詢失敗)→ 空 map", () => {
    expect(positionsByCode(undefined).size).toBe(0);
  });
});

describe("secSummary(SC-5:與 positionEcon 同一把尺)", () => {
  it("單列的 pnl 逐字等於 positionEcon 直算", () => {
    const sec = secOf([pos()]);
    const econ = positionEcon(3, 985.2, LAST, DISCOUNT, "cash", { avgSource: "fill", todayQty: 0 });
    expect(sec.pnl).toBe(econ.pnl);
    expect(sec.kinds).toHaveLength(1);
    expect(sec.kinds[0]?.pnl).toBe(econ.pnl);
    expect(sec.kinds[0]?.label).toBe("現股");
  });

  it("折數換一個值 → pnl 跟著 positionEcon 換(折數不是寫死的)", () => {
    const sec = secOf([pos()], LAST, 3);
    expect(sec.pnl).toBe(positionEcon(3, 985.2, LAST, 3, "cash", { avgSource: "fill", todayQty: 0 }).pnl);
    expect(sec.pnl).not.toBe(positionEcon(3, 985.2, LAST, DISCOUNT, "cash", { avgSource: "fill", todayQty: 0 }).pnl);
  });

  it("pct = pnl / (均價 × |張數| × 1000) × 100(成本基準)", () => {
    const sec = secOf([pos()]);
    const econ = positionEcon(3, 985.2, LAST, DISCOUNT, "cash", { avgSource: "fill", todayQty: 0 });
    expect(sec.pct).toBeCloseTo(((econ.pnl ?? 0) / (985.2 * 3 * 1000)) * 100, 10);
  });

  it("同股號多 kind → qty 帶號和、pnl 逐列和、依 KIND_ORDER 排序", () => {
    const rows = [pos({ kind: "short", qty: -2 }), pos({ kind: "cash", qty: 3 })];
    const sec = secOf(rows);
    const cash = positionEcon(3, 985.2, LAST, DISCOUNT, "cash", { avgSource: "fill", todayQty: 0 });
    const short = positionEcon(-2, 985.2, LAST, DISCOUNT, "short", { avgSource: "fill", todayQty: 0 });
    expect(sec.kinds.map((k) => k.label)).toEqual(["現股", "融券"]);
    expect(sec.qty).toBe(1);
    expect(sec.pnl).toBe((cash.pnl ?? 0) + (short.pnl ?? 0));
    expect(sec.pct).toBeCloseTo(
      (((cash.pnl ?? 0) + (short.pnl ?? 0)) / (985.2 * 3 * 1000 + 985.2 * 2 * 1000)) * 100,
      10,
    );
  });

  /** 嚴格制:一列算不出來,聚合就沒有意義 —— 只加非 null 的那幾列會端出一個
   *  「看起來完整」的數字,而它少算了一整筆部位。 */
  it("任一列均價缺 → 聚合 pnl / pct 皆 null(張數照顯示)", () => {
    const sec = secOf([pos({ kind: "cash", qty: 3 }), pos({ kind: "margin", avg_price: null, qty: 2 })]);
    expect(sec.pnl).toBeNull();
    expect(sec.pct).toBeNull();
    expect(sec.qty).toBe(5);
    expect(sec.kinds[1]?.avg).toBeNull();
    expect(sec.kinds[1]?.pnl).toBeNull();
  });

  it("現價缺(盤前)→ pnl / pct null,部位本身仍在", () => {
    const sec = secOf([pos()], null);
    expect(sec.pnl).toBeNull();
    expect(sec.pct).toBeNull();
    expect(sec.qty).toBe(3);
  });

  it("沒有 sec 列(只有個股期)→ null", () => {
    expect(secSummary([fut()], LAST, DISCOUNT)).toBeNull();
  });
});

describe("futSummary(AD-5:逐契約,pnl_base 名目損益)", () => {
  it("標準 + 小型兩契約:依契約碼排序、pnl 為 pnl_base 之和", () => {
    const f = futOf([fut({ stock_no: "QFFI6", qty: -1, pnl_base: -200 }), fut()]);
    expect(f.rows.map((r) => r.contract)).toEqual(["CDFI6", "QFFI6"]);
    expect(f.pnl).toBe(300);
    expect(f.rows[1]?.qty).toBe(-1);
  });

  it("任一契約的 pnl_base 缺 → 合計 null(不當 0 加)", () => {
    const f = futOf([fut(), fut({ stock_no: "QFFI6", qty: -1, pnl_base: null })]);
    expect(f.pnl).toBeNull();
    expect(f.rows[0]?.pnl).toBe(500);
  });

  it("沒有 fut 列 → null", () => {
    expect(futSummary([pos()])).toBeNull();
  });
});

describe("張數 / 口數文字", () => {
  it("多方 / 空方 / 對鎖", () => {
    expect(secQtyText(secOf([pos({ qty: 3 })]))).toBe("3張");
    expect(secQtyText(secOf([pos({ kind: "short", qty: -2 })]))).toBe("空2張");
    // 對鎖聚合成 0 張會像「沒有部位」,而手上其實壓著兩筆
    expect(secQtyText(secOf([pos({ qty: 3 }), pos({ kind: "short", qty: -3 })]))).toBe("多3/空3張");
  });

  it("單一契約 / 多契約(標準與小型差 20 倍,不可聚合)", () => {
    expect(futQtyText(futOf([fut()]))).toBe("期 2口");
    expect(futQtyText(futOf([fut({ qty: -1 })]))).toBe("期 空1口");
    expect(futQtyText(futOf([fut(), fut({ stock_no: "QFFI6", qty: -1 })]))).toBe("期 2口/空1口");
  });
});

describe("chip / 卡片 / header 文字", () => {
  it("chipText:張數 + 百分比,有期倉再接一段", () => {
    const sec = secOf([pos()]);
    const f = futOf([fut()]);
    expect(chipText(sec, null)).toBe(`3張 ${fmtPct(sec.pct ?? 0)}`);
    expect(chipText(sec, f)).toBe(`3張 ${fmtPct(sec.pct ?? 0)} · 期 2口`);
  });

  it("chipText:只有期倉 → 只有期那段;pct 缺 → 破折號", () => {
    expect(chipText(null, futOf([fut()]))).toBe("期 2口");
    expect(chipText(secOf([pos()], null), null)).toBe(`3張 ${DASH}`);
  });

  it("chipTitle:逐 kind 一行 + 逐契約一行(標明群益名目)", () => {
    const sec = secOf([pos()]);
    const f = futOf([fut()]);
    const lines = chipTitle(sec, f).split("\n");
    expect(lines[0]).toBe(
      `現股 3張 均價 ${fmt(Math.round(985.2 * 1000))} 損益 ${pnlText(sec.pnl)} (${fmtPct(sec.pct ?? 0)})`,
    );
    expect(lines[1]).toBe("CDFI6 多2口 損益 +500(群益名目,報告時點)");
  });

  it("chipTitle:均價缺 → 均價破折號、損益破折號、不印百分比", () => {
    const sec = secOf([pos({ avg_price: null })]);
    expect(chipTitle(sec, null)).toBe(`現股 3張 均價 ${DASH} 損益 ${DASH}`);
  });

  it("chipTone:有 sec 看 sec 損益,沒有才看期倉", () => {
    expect(chipTone(secOf([pos()]), null)).toBe("text-bull");
    expect(chipTone(secOf([pos()], null), null)).toBe("text-ink-dim");
    expect(chipTone(null, futOf([fut({ pnl_base: -200 })]))).toBe("text-bear");
  });

  it("cardText:現股段 + 期貨段(卡片一行放得下的密度)", () => {
    const sec = secOf([pos()]);
    const f = futOf([fut()]);
    expect(cardText(sec, f)).toBe(
      `現 3張 ${pnlText(sec.pnl)} (${fmtPct(sec.pct ?? 0)}) · 期 2口 +500`,
    );
  });

  it("cardText:現價缺 → 現股段破折號,期貨段照顯示(pnl_base 不吃現價)", () => {
    expect(cardText(secOf([pos()], null), futOf([fut()]))).toBe(`現 3張 ${DASH} · 期 2口 +500`);
  });

  // review TEST-2:只有期倉(現股全平、只留個股期)是真實會發生的組合,而 fut-only
  // 走的是「sec 段整段不 push」那條分支 —— 沒案子的話多插一個空的「現 」前綴不會紅。
  it("cardText:只有期倉 → 只有期那段(不留現股段的殘影)", () => {
    expect(cardText(null, futOf([fut()]))).toBe("期 2口 +500");
  });

  it("headerSegments:只有期倉 → 只有契約那幾段", () => {
    const segs = headerSegments(null, futOf([fut()]));
    expect(segs).toHaveLength(1);
    expect(segs[0]?.text).toBe(`期 CDFI6 多 2口 · 均價 ${fmt(985_000)} · 損益 +500`);
    expect(segs[0]?.key).toBe("fut:CDFI6");
    expect(segs[0]?.pnl).toBe(500);
  });

  it("headerSegments:逐 kind / 逐契約各一段,tone 跟著各段自己的損益", () => {
    const sec = secOf([pos({ kind: "cash", qty: 3 }), pos({ kind: "short", qty: -2 })]);
    const f = futOf([fut()]);
    const segs = headerSegments(sec, f);
    expect(segs).toHaveLength(3);
    expect(segs[0]?.text).toBe(
      `現股 3張 · 均價 ${fmt(Math.round(985.2 * 1000))} · 損益 ${pnlText(sec.kinds[0]?.pnl ?? null)} (${fmtPct(sec.kinds[0]?.pct ?? 0)})`,
    );
    expect(segs[1]?.text.startsWith("融券 空2張 · 均價 ")).toBe(true);
    expect(segs[2]?.text).toBe(`期 CDFI6 多 2口 · 均價 ${fmt(985_000)} · 損益 +500`);
    expect(segs.map((s) => s.pnl)).toEqual([
      sec.kinds[0]?.pnl,
      sec.kinds[1]?.pnl,
      500,
    ]);
    // key 由 kind / 契約碼決定 —— 位移不會讓 React 把整段當新節點重掛
    expect(segs.map((s) => s.key)).toEqual(["sec:cash", "sec:short", "fut:CDFI6"]);
  });

  it("headerSegments:無倉兩側皆 null → 空陣列(整段不渲染)", () => {
    expect(headerSegments(null, null)).toEqual([]);
  });
});

// 🔴 N065:`code` 反查不到的個股期倉位(除權息調整碼 EE1/CD1 形、新上市未 refresh)
// 在自選 chip / 單檔 header / 群組卡三處**靜默不顯示**,畫面上零提示 —— 使用者會以為
// 那筆部位不存在。跳過本身是對的(猜股號會把部位掛到別檔頭上),缺的是「說一聲」。
describe("unmappedFutCount(N065:反查不到股號的個股期倉位計數)", () => {
  it("code null 的 fut 列計入", () => {
    expect(unmappedFutCount([fut({ stock_no: "EE1I6", code: null })])).toBe(1);
  });

  it("空字串同樣算反查不到(後端 code 恆為 string|null,防禦性同 positionsByCode)", () => {
    expect(unmappedFutCount([fut({ stock_no: "EE1I6", code: "" })])).toBe(1);
  });

  it("qty 0 不是部位,不計(與 positionsByCode 同一條)", () => {
    expect(unmappedFutCount([fut({ stock_no: "EE1I6", code: null, qty: 0 })])).toBe(0);
  });

  it("反查得到的 fut 列不計;sec 列的 code 語意不同(恆為股號)也不計", () => {
    expect(unmappedFutCount([fut(), pos({ code: null })])).toBe(0);
  });

  it("undefined / 空陣列 → 0(呼叫端不必自己判 loading)", () => {
    expect(unmappedFutCount(undefined)).toBe(0);
    expect(unmappedFutCount([])).toBe(0);
  });

  it("多筆累加", () => {
    expect(
      unmappedFutCount([
        fut({ stock_no: "EE1I6", code: null }),
        fut({ stock_no: "CD1I6", code: null }),
        fut(),
      ]),
    ).toBe(2);
  });
});
