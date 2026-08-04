import { describe, expect, it } from "vitest";

import {
  filterKinds,
  formatToastText,
  kindLabel,
  mergeSignals,
  type SignalEnabled,
  type SignalMsg,
} from "@/lib/signal-model";

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

const ALL_ON: SignalEnabled = {
  cdp_cross: true,
  surge_crash: true,
  vol_burst: true,
  limit_lock: true,
};

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

  it("pct 缺值不印 NaN(舊後端 / 壞行)", () => {
    expect(kindLabel(sig({ kind: "surge", pct: null }))).toBe("爆拉");
    expect(kindLabel(sig({ kind: "vol_burst", pct: null }))).toBe("爆量");
  });

  it("未知 kind 原樣回傳(新後端 kind 不因前端舊而變空白)", () => {
    expect(kindLabel(sig({ kind: "brand_new" as SignalMsg["kind"], pct: null }))).toBe("brand_new");
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

  it("live 在前、baseline 在後", () => {
    expect(mergeSignals([b, c], [a]).map((s) => s.id)).toEqual(["a", "b", "c"]);
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

describe("filterKinds", () => {
  it("全開時原樣", () => {
    const list = [sig({ id: "1", kind: "surge" }), sig({ id: "2", kind: "cdp_cross" })];
    expect(filterKinds(list, ALL_ON).length).toBe(2);
  });

  it("surge 與 crash 共用 surge_crash 開關", () => {
    const list = [sig({ id: "1", kind: "surge" }), sig({ id: "2", kind: "crash" })];
    expect(filterKinds(list, { ...ALL_ON, surge_crash: false })).toEqual([]);
  });

  it("limit_lock 與 limit_open 共用 limit_lock 開關", () => {
    const list = [sig({ id: "1", kind: "limit_lock" }), sig({ id: "2", kind: "limit_open" })];
    expect(filterKinds(list, { ...ALL_ON, limit_lock: false })).toEqual([]);
  });

  it("cdp_cross / vol_burst 各自獨立開關", () => {
    const list = [
      sig({ id: "1", kind: "cdp_cross" }),
      sig({ id: "2", kind: "vol_burst" }),
      sig({ id: "3", kind: "surge" }),
    ];
    expect(filterKinds(list, { ...ALL_ON, cdp_cross: false }).map((s) => s.id)).toEqual(["2", "3"]);
    expect(filterKinds(list, { ...ALL_ON, vol_burst: false }).map((s) => s.id)).toEqual(["1", "3"]);
  });

  it("未知 kind 不被吃掉(前端舊 / 後端新增類型時 fail-open)", () => {
    const list = [sig({ id: "1", kind: "brand_new" as SignalMsg["kind"] })];
    expect(filterKinds(list, { ...ALL_ON, surge_crash: false }).map((s) => s.id)).toEqual(["1"]);
  });

  it("enabled 缺鍵(舊後端)當開啟,不靜默清空整條訊號流", () => {
    const list = [sig({ id: "1", kind: "surge" })];
    expect(filterKinds(list, {} as SignalEnabled).map((s) => s.id)).toEqual(["1"]);
  });
});
