import { describe, expect, it } from "vitest";

import { formatToastText, kindLabel, mergeSignals, type SignalMsg } from "@/lib/signal-model";
// namespace import(不是具名):具名 import 一個尚未存在的 export 在 Vite SSR transform 下
// 是**載入期例外**(整檔 error),紅階段要的是「fail 不是 error」。
import * as signalModel from "@/lib/signal-model";

function sig(overrides: Partial<SignalMsg> = {}): SignalMsg {
  return {
    type: "signal",
    id: "s1",
    kind: "surge",
    code: "2330",
    name: "台積電",
    price: 1_234_500,
    time: "09:15:03",
    levels: [],
    direction: null,
    pct: 5.234,
    touch_count: 1,
    ...overrides,
  };
}

describe("kindLabel", () => {
  it("CDP 由下往上穿越 = 突破,線名大寫", () => {
    expect(kindLabel(sig({ kind: "cdp_cross", levels: ["ah"], direction: "from_below", pct: null })))
      .toBe("突破 CDP AH");
  });

  it("CDP 由上往下穿越 = 跌破", () => {
    expect(kindLabel(sig({ kind: "cdp_cross", levels: ["nl"], direction: "from_above", pct: null })))
      .toBe("跌破 CDP NL");
  });

  it("cdp 線顯示「中軸」不是「CDP」(避免 CDP CDP 疊字)", () => {
    expect(kindLabel(sig({ kind: "cdp_cross", levels: ["cdp"], direction: "from_below", pct: null })))
      .toBe("突破 CDP 中軸");
  });

  it("同 tick 多線合併事件以 + 串接(後端固定序,前端不重排)", () => {
    expect(
      kindLabel(sig({ kind: "cdp_cross", levels: ["ah", "nh"], direction: "from_below", pct: null })),
    ).toBe("突破 CDP AH+NH");
  });

  it("爆拉 / 爆跌附實際漲跌幅(帶正負號、兩位小數)", () => {
    expect(kindLabel(sig({ kind: "surge", pct: 5.234 }))).toBe("爆拉 +5.23%");
    expect(kindLabel(sig({ kind: "crash", pct: -5.4 }))).toBe("爆跌 -5.40%");
  });

  it("爆量附倍率(一位小數)", () => {
    expect(kindLabel(sig({ kind: "vol_burst", pct: 3.45 }))).toBe("爆量 3.5 倍");
  });

  it("鎖漲跌停 / 打開依 direction 分中文", () => {
    expect(kindLabel(sig({ kind: "limit_lock", direction: "up", pct: null }))).toBe("鎖漲停");
    expect(kindLabel(sig({ kind: "limit_lock", direction: "down", pct: null }))).toBe("鎖跌停");
    expect(kindLabel(sig({ kind: "limit_open", direction: "up", pct: null }))).toBe("漲停打開");
    expect(kindLabel(sig({ kind: "limit_open", direction: "down", pct: null }))).toBe("跌停打開");
  });

  // 文案與後端 `signal_hub._kind_text` 逐字對齊(design §7):兩邊漂掉時
  // WS 列與 Discord/jsonl 上的同一則事件會長得不一樣。
  it("全市場鎖板 / 打開依 direction 分中文(SC-8)", () => {
    expect(kindLabel(sig({ kind: "market_limit_lock", direction: "up", pct: null })))
      .toBe("全市場鎖漲停");
    expect(kindLabel(sig({ kind: "market_limit_lock", direction: "down", pct: null })))
      .toBe("全市場鎖跌停");
    expect(kindLabel(sig({ kind: "market_limit_open", direction: "up", pct: null })))
      .toBe("全市場漲停打開");
    expect(kindLabel(sig({ kind: "market_limit_open", direction: "down", pct: null })))
      .toBe("全市場跌停打開");
  });

  it("pct 缺值不印 NaN(舊後端 / 壞行)", () => {
    expect(kindLabel(sig({ kind: "surge", pct: null }))).toBe("爆拉");
    expect(kindLabel(sig({ kind: "vol_burst", pct: null }))).toBe("爆量");
  });

  it("未知 kind 原樣回傳(新後端 kind 不因前端舊而變空白)", () => {
    expect(kindLabel(sig({ kind: "brand_new" as SignalMsg["kind"], pct: null }))).toBe("brand_new");
  });
});

// 🟢 market-overview R4(SC-8):全市場廣度事件與自選訊號同一條匯流排,
// 前綴 `market_` 是唯一的分族依據(feed 過濾 / alerts 早退都吃它)。
describe("isMarketKind", () => {
  it("兩個 market kind 為 true", () => {
    expect(signalModel.isMarketKind("market_limit_lock")).toBe(true);
    expect(signalModel.isMarketKind("market_limit_open")).toBe(true);
  });

  it("自選訊號 kind 為 false(限自選的鎖板不是全市場事件)", () => {
    expect(signalModel.isMarketKind("limit_lock")).toBe(false);
  });
});

describe("formatToastText", () => {
  it("代號 名稱 訊號名 價格(價格毫元轉字串)", () => {
    expect(formatToastText(sig())).toBe("2330 台積電 爆拉 +5.23% 1234.5");
  });

  it("名稱缺值不留雙空格", () => {
    expect(formatToastText(sig({ name: "" }))).toBe("2330 爆拉 +5.23% 1234.5");
  });
});

describe("mergeSignals", () => {
  const a = sig({ id: "a" });
  const b = sig({ id: "b" });
  const c = sig({ id: "c" });

  it("同 time 併列時 live 在前、baseline 在後(穩定排序保留插入序)", () => {
    expect(mergeSignals([b, c], [a]).map((s) => s.id)).toEqual(["a", "b", "c"]);
  });

  it("斷線自癒:baseline 補回的較新訊號排在既有 live 之上(review CC-3)", () => {
    // live = 斷線前收到的 50 則舊訊號(新在前);baseline = 重抓 jsonl 補回的兩則較新訊號。
    // 若只做「live 全前 + baseline 後」,補回的訊號會被埋在 50 則舊訊號底下看不見。
    const live = Array.from({ length: 50 }, (_, i) =>
      sig({ id: `live${i}`, time: `09:${String(10 + i).padStart(2, "0")}:00` }),
    ).reverse();
    const missed = [sig({ id: "m2", time: "10:05:00" }), sig({ id: "m1", time: "10:00:00" })];

    const merged = mergeSignals(missed, live);
    expect(merged.length).toBe(52);
    expect(merged.slice(0, 3).map((s) => s.id)).toEqual(["m2", "m1", "live49"]);
  });

  it("cap 在排序之後才截斷(留下的是最新那些,不是先到的)", () => {
    const older = sig({ id: "older", time: "09:00:00" });
    const newer = sig({ id: "newer", time: "13:00:00" });
    expect(mergeSignals([newer], [older], 1).map((s) => s.id)).toEqual(["newer"]);
  });

  it("同 id 只留一筆(WS 已收 + jsonl baseline 重疊)", () => {
    expect(mergeSignals([a, b], [a]).map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("live 內部自身重複也去重", () => {
    expect(mergeSignals([], [a, a, b]).map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("上限 cap(預設 200)截斷尾端", () => {
    const many = Array.from({ length: 250 }, (_, i) => sig({ id: `x${i}` }));
    expect(mergeSignals(many, []).length).toBe(200);
    expect(mergeSignals(many, [], 3).map((s) => s.id)).toEqual(["x0", "x1", "x2"]);
  });

  it("空輸入回空陣列", () => {
    expect(mergeSignals([], [])).toEqual([]);
  });
});
