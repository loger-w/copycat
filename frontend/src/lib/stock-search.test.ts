import { describe, expect, it } from "vitest";

import { searchStocks, type StockName } from "@/lib/stock-search";

const TABLE: StockName[] = [
  { code: "2330", name: "台積電" },
  { code: "2331", name: "精英" },
  { code: "2317", name: "鴻海" },
  { code: "3231", name: "緯創" },
  { code: "00679B", name: "元大美債20年" },
  { code: "6547", name: "高端疫苗" },
  { code: "1101", name: "台泥" },
];

describe("searchStocks", () => {
  it("空字串 / 全空白 → 不提示(不是回整張表)", () => {
    expect(searchStocks("", TABLE)).toEqual([]);
    expect(searchStocks("   ", TABLE)).toEqual([]);
  });

  it("完整代碼 → 該檔在第一列", () => {
    expect(searchStocks("2330", TABLE)[0]).toEqual({ code: "2330", name: "台積電" });
  });

  it("代碼前綴 → 多筆命中且按代碼升序", () => {
    expect(searchStocks("23", TABLE).map((s) => s.code)).toEqual(["2317", "2330", "2331"]);
  });

  it("名稱片段 → 命中(中文不做大小寫轉換)", () => {
    expect(searchStocks("台積", TABLE)).toEqual([{ code: "2330", name: "台積電" }]);
    expect(searchStocks("疫苗", TABLE).map((s) => s.code)).toEqual(["6547"]);
  });

  it("代碼命中排在名稱命中之前(打 1101 不該先跳出名稱含 1101 的東西)", () => {
    const table: StockName[] = [
      { code: "9999", name: "測試1101公司" },
      { code: "1101", name: "台泥" },
    ];
    expect(searchStocks("1101", table).map((s) => s.code)).toEqual(["1101", "9999"]);
  });

  it("代碼比對大小寫不敏感(字母尾碼 ETF)", () => {
    expect(searchStocks("00679b", TABLE).map((s) => s.code)).toEqual(["00679B"]);
    expect(searchStocks("00679B", TABLE).map((s) => s.code)).toEqual(["00679B"]);
  });

  it("兩段命中的同一檔只出現一次", () => {
    const table: StockName[] = [{ code: "2330", name: "2330控股" }];
    expect(searchStocks("2330", table)).toEqual([{ code: "2330", name: "2330控股" }]);
  });

  it("limit 生效", () => {
    expect(searchStocks("2", TABLE, 2).length).toBe(2);
  });

  it("查無命中 → 空陣列(呼叫端據此走「原樣代碼加入」)", () => {
    expect(searchStocks("zzzz", TABLE)).toEqual([]);
  });

  it("空表 → 空陣列(名稱表未載入 / 壞檔的降級)", () => {
    expect(searchStocks("2330", [])).toEqual([]);
  });
});
