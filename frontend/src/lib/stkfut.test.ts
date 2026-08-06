import { describe, expect, it } from "vitest";

import {
  instrumentKeyOf,
  isEtfUnderlying,
  isOrderBlocked,
  selectionOf,
  stkfutTc4Symbol,
  ymLabel,
  type StkfutContracts,
} from "@/lib/stkfut";

/** 個股期共用純函式(code review B2/B3)。
 *
 *  本檔之前**零覆蓋** —— 這四支的失效全部靜默:白名單漏掉一種形狀會拿必被 400 的
 *  URL 洗掉主圖、instrument key 與股號互換會畫錯商品、送單 symbol 退回 `.HOT` 會送出
 *  與畫面不同月份的真單。元件層的測試各自只碰到其中一支的一條路徑。 */

const CONTRACTS: StkfutContracts = {
  code: "2330",
  name: "台積電",
  std: { prod: "CDF", contracts: ["202608", "202609"], unit: 2000 },
  mini: { prod: "QFF", contracts: ["202608", "202609"], unit: 100 },
};

const NO_MINI: StkfutContracts = { ...CONTRACTS, mini: null };

describe("selectionOf(前端白名單)", () => {
  it("標準腿命中 → mini:false + 該腿契約單位", () => {
    expect(selectionOf(CONTRACTS, "CDF:202609")).toEqual({
      prod: "CDF",
      ym: "202609",
      mini: false,
      unit: 2000,
    });
  });

  it("小型腿命中 → mini:true + 小型單位(兩腿差 20 倍,選錯 = 下單量差 20 倍)", () => {
    expect(selectionOf(CONTRACTS, "QFF:202608")).toEqual({
      prod: "QFF",
      ym: "202608",
      mini: true,
      unit: 100,
    });
  });

  // 三態的第三態:清單外一律 null。這是**前端側**的白名單 —— 後端 D7 也會擋,但先擋
  // 掉可以避免拿一個必被 400 的 URL 去洗掉主圖(畫面會停在「載入中…」)。
  it.each([
    ["現貨空字串", ""],
    ["月份不在該腿清單內", "CDF:202612"],
    ["產品碼不屬於這檔股票", "DHF:202609"],
    ["缺分隔冒號", "CDF202609"],
    ["小型腿不存在時仍不得由標準腿代收", "QFF:202609"],
  ])("%s → null", (_name, value) => {
    expect(selectionOf(value === "QFF:202609" ? NO_MINI : CONTRACTS, value)).toBeNull();
  });

  it("後端未帶 unit(舊 build)→ null 而不是 undefined(下游判準吃 null)", () => {
    const legacy = {
      ...CONTRACTS,
      std: { prod: "CDF", contracts: ["202609"] },
    } as unknown as StkfutContracts;
    expect(selectionOf(legacy, "CDF:202609")?.unit).toBeNull();
  });
});

describe("stkfutTc4Symbol", () => {
  it("送單 symbol 是月份 leaf,逐字不含 HOT", () => {
    const sym = stkfutTc4Symbol({ prod: "CDF", ym: "202609" });
    expect(sym).toBe("TC.F.TWF.CDF.202609");
    expect(sym).not.toContain("HOT");
  });

  it("次月選擇也照樣落在該月(HOT 會被 TC4 解析成近月 = 送錯合約)", () => {
    expect(stkfutTc4Symbol({ prod: "QFF", ym: "202612" })).toBe("TC.F.TWF.QFF.202612");
  });
});

describe("instrumentKeyOf", () => {
  it("現貨態 = 股號原樣(REST 路徑段與 WS 比對鍵在此重合)", () => {
    expect(instrumentKeyOf("2330", null)).toBe("2330");
  });

  it("合約態 = F:<prod>:<ym>(後端 engine 的訂閱槽位鍵)", () => {
    expect(instrumentKeyOf("2330", { prod: "CDF", ym: "202609" })).toBe("F:CDF:202609");
  });

  it("同股不同月是不同 key(相等會讓換月時畫面停在舊合約資料上)", () => {
    expect(instrumentKeyOf("2330", { prod: "CDF", ym: "202609" })).not.toBe(
      instrumentKeyOf("2330", { prod: "CDF", ym: "202610" }),
    );
  });

  it("未選檔 → null(合約再怎麼有值也不得憑空產生 key)", () => {
    expect(instrumentKeyOf(null, { prod: "CDF", ym: "202609" })).toBeNull();
  });
});

describe("isOrderBlocked(下單前置閘)", () => {
  it.each([
    ["標準 2,000 股", 2000],
    ["小型 100 股", 100],
  ])("%s → 放行", (_n, unit) => {
    expect(isOrderBlocked("2330", unit)).toBe(false);
  });

  it("ETF 10,000 受益權單位 → 擋", () => {
    expect(isOrderBlocked("0050", 10000)).toBe(true);
  });

  // 舊的股號判準抓不到這一類:股號是 1312(不是 0 開頭)但單位 2,157,後端照樣
  // PRODUCT_NOT_ALLOWED → 使用者按下去只會收到一句莫名的「委託失敗」。
  it("除權息調整契約(2,157 股)→ 擋,而股號 fallback 抓不到", () => {
    expect(isOrderBlocked("1312", 2157)).toBe(true);
    expect(isEtfUnderlying("1312")).toBe(false);
  });

  it("單位不可得 → 落回股號 fallback(0 開頭擋、其餘放行)", () => {
    expect(isOrderBlocked("0050", null)).toBe(true);
    expect(isOrderBlocked("2330", null)).toBe(false);
  });
});

describe("ymLabel", () => {
  it("202609 → 2026/09(下拉選項要逐字可指認)", () => {
    expect(ymLabel("202609")).toBe("2026/09");
  });
});
