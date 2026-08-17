import { describe, expect, it } from "vitest";

import {
  formatToastText,
  groupKindLabels,
  groupRuleNames,
  groupSignals,
  kindLabel,
  mergeSignals,
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

/** SC-5:同一 tick 打出多則訊號(CDP 穿越 + 爆拉…)時清單一列一組。
 *  輸入已是 `mergeSignals` 的輸出(新在前),分組只看**相鄰**:不相鄰的同 (code, time)
 *  各自成組(edge 7)—— 跨列搜尋會把中間那則別檔的列擠掉,顯示保守正確優先。 */
describe("groupSignals", () => {
  const cdp = sig({
    id: "g1",
    kind: "cdp_cross",
    levels: ["cdp"],
    direction: "from_above",
    pct: null,
    time: "09:31:22",
    price: 1_000_000,
    rule_name: "CDP 穿越",
  });
  const crash = sig({
    id: "g2",
    kind: "crash",
    pct: -2.1,
    time: "09:31:22",
    price: 999_000,
    rule_name: "爆跌",
  });

  it("相鄰且同 (code, time) 併成一組", () => {
    const groups = groupSignals([cdp, crash]);
    expect(groups.length).toBe(1);
    expect(groups[0]?.items.map((s) => s.id)).toEqual(["g1", "g2"]);
  });

  // review C-4:輸入是「新在前」,組內最後一則 = 最早到的那則。取組首當 key 時,
  // 同 tick 再來一則就換 key = 整列卸載重掛;價格也要與 Discord 合併訊息的 rows[0] 同一則。
  it("組的 key / 價格 / 名稱 / 時間取組內最後一則(= 最早到)", () => {
    const [group] = groupSignals([cdp, crash]);
    expect(group?.key).toBe("g2");
    expect(group?.code).toBe("2330");
    expect(group?.name).toBe("台積電");
    expect(group?.time).toBe("09:31:22");
    expect(group?.price).toBe(999_000);
  });

  // T-11:同一 tick 又到一則(前插)時,列的身分不能變 —— 否則 React 以新 key 重建整列
  it("同組前插新到訊號:key 與 price 不變", () => {
    const fresh = sig({
      id: "g5",
      kind: "vol_burst",
      pct: 3,
      time: "09:31:22",
      price: 1_002_000,
    });
    const [before] = groupSignals([cdp, crash]);
    const [after] = groupSignals([fresh, cdp, crash]);
    expect(after?.key).toBe(before?.key);
    expect(after?.key).toBe("g2");
    expect(after?.price).toBe(999_000);
    expect(after?.items.map((s) => s.id)).toEqual(["g5", "g1", "g2"]);
  });

  it("不同 code 不併(同一秒兩檔各自成列)", () => {
    const other = sig({ id: "g3", code: "2317", name: "鴻海", time: "09:31:22" });
    expect(groupSignals([cdp, other]).length).toBe(2);
  });

  it("同 code 不同 time 不併", () => {
    const later = sig({ id: "g4", time: "09:31:23" });
    expect(groupSignals([cdp, later]).length).toBe(2);
  });

  it("保序:組序 = 輸入序,組內序 = 輸入序", () => {
    const other = sig({ id: "g3", code: "2317", name: "鴻海", time: "09:31:22" });
    const groups = groupSignals([other, cdp, crash]);
    expect(groups.map((g) => g.key)).toEqual(["g3", "g2"]);
    expect(groups[1]?.items.map((s) => s.id)).toEqual(["g1", "g2"]);
  });

  // edge 7:被別檔同秒 row 隔開的同 (code, time) 不跨列搜尋
  it("不相鄰的同 (code, time) 各自成組", () => {
    const other = sig({ id: "g3", code: "2317", name: "鴻海", time: "09:31:22" });
    expect(groupSignals([cdp, other, crash]).map((g) => g.key)).toEqual(["g1", "g3", "g2"]);
  });

  it("空輸入回空陣列", () => {
    expect(groupSignals([])).toEqual([]);
  });
});

describe("groupKindLabels / groupRuleNames", () => {
  const base = sig({ id: "k1", kind: "surge", pct: 1.2, time: "09:31:22", rule_name: "早盤急拉" });

  // 段序 = 到達序(items 反序):與 Discord 合併訊息 rows[0] = 最早到的那則同一個口徑
  it("每段 kind 文案帶自己的代表 sig,段序為到達序", () => {
    const dive = sig({ id: "k2", kind: "crash", pct: -1.2, time: "09:31:22", rule_name: "早盤急殺" });
    const [group] = groupSignals([base, dive]);
    const segments = groupKindLabels(group!);
    expect(segments.map((s) => s.label)).toEqual(["爆跌 -1.20%", "爆拉 +1.20%"]);
    expect(segments.map((s) => s.sig.id)).toEqual(["k2", "k1"]);
  });

  // 前插一則新到訊號只會加在**尾段**,已顯示的段序不動
  it("同組前插新到訊號:既有段序不變、新段接在尾端", () => {
    const dive = sig({ id: "k2", kind: "crash", pct: -1.2, time: "09:31:22" });
    const fresh = sig({ id: "k3", kind: "vol_burst", pct: 3, time: "09:31:22" });
    const [group] = groupSignals([fresh, base, dive]);
    expect(groupKindLabels(group!).map((s) => s.label)).toEqual([
      "爆跌 -1.20%",
      "爆拉 +1.20%",
      "爆量 3.0 倍",
    ]);
  });

  // 同 kind 兩條規則同 tick 各發一則 → 文案一模一樣,印兩段只是雜訊
  it("同文案只留一段(保留到達序的首見順序)", () => {
    const twin = sig({ id: "k2", kind: "surge", pct: 1.2, time: "09:31:22", rule_name: "另一條" });
    const [group] = groupSignals([base, twin]);
    const segments = groupKindLabels(group!);
    expect(segments.map((s) => s.label)).toEqual(["爆拉 +1.20%"]);
    expect(segments[0]?.sig.id).toBe("k2");
  });

  it("規則名去重、保留首見順序", () => {
    const twin = sig({ id: "k2", kind: "crash", pct: -1.2, time: "09:31:22", rule_name: "早盤急拉" });
    const [group] = groupSignals([base, twin]);
    expect(groupRuleNames(group!)).toEqual(["早盤急拉"]);
  });

  it("規則名缺值 / 空字串不入清單(升級當日的舊 jsonl 行)", () => {
    const old = sig({ id: "k2", kind: "crash", pct: -1.2, time: "09:31:22", rule_name: "" });
    const older = sig({ id: "k3", kind: "vol_burst", pct: 3, time: "09:31:22" });
    const [group] = groupSignals([base, old, older]);
    expect(groupRuleNames(group!)).toEqual(["早盤急拉"]);
  });
});
