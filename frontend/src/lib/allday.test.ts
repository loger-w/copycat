import { beforeEach, describe, expect, it } from "vitest";

import {
  ALLDAY_GAP,
  ALLDAY_HOUR_TICKS,
  ALLDAY_LEN,
  ALLDAY_SEGMENTS,
  ALLDAY_TICKS,
  ALLDAY_WINDOW,
  alldayBarsBetween,
  alldayHhmmOf,
  alldayIndexOf,
  alldayIndexOfStamp,
  anchorDateOf,
  sliceCurrentAllday,
} from "@/lib/allday";
import type { Bar } from "@/lib/candle";
import { clearHolidays, setHolidays } from "@/lib/trading-calendar";

/** mod/futures-day-1500:一天 = 15:00 夜盤起算 → 05:00 → (空檔 05:01–08:45 保留在軸上)→ 08:46 日盤 → 13:45。
 *  索引期望值**寫死**(段長推導在註解),不由 import 的常數算回來(frontend-testing 慣例)。
 *  2026-08-24 一 / 08-25 二 / 08-26 三 / 08-27 四 / 08-28 五 / 08-29 六 / 08-30 日 / 08-31 一。 */

function bar(t: string, c = 100): Bar {
  return { t, o: c, h: c, l: c, c, v: 1 };
}

beforeEach(() => {
  clearHolidays();
});

describe("ALLDAY_SEGMENTS(四段:夜盤前半 / 夜盤後半 / 空檔 / 日盤)", () => {
  it("段長 539 / 301 / 225 / 300,總和 1365;空檔段 tradable=false", () => {
    expect(ALLDAY_SEGMENTS.map((s) => s.len)).toEqual([539, 301, 225, 300]);
    expect(ALLDAY_SEGMENTS.map((s) => s.tradable)).toEqual([true, true, false, true]);
    expect(ALLDAY_LEN).toBe(1365);
  });

  it("可交易三段的段界字串與後端 FUTURES_ALLDAY_DOMAIN 相同(改一邊必改另一邊);空檔段 0501–0845", () => {
    expect(ALLDAY_SEGMENTS.map((s) => [s.start, s.end])).toEqual([
      ["1501", "2359"],
      ["0000", "0500"],
      ["0501", "0845"],
      ["0846", "1345"],
    ]);
  });

  it("ALLDAY_GAP = 空檔段在軸上的索引區間 [840, 1064]", () => {
    expect(ALLDAY_GAP).toEqual({ start: 840, end: 1064 });
  });
});

describe("alldayIndexOf", () => {
  it("可交易段界(15:00 開盤 → 首根終點標記 1501 = index 0;日盤首根 0846 = 539 + 301 + 225 = 1065)", () => {
    expect(alldayIndexOf("1501")).toBe(0);
    expect(alldayIndexOf("2359")).toBe(538);
    expect(alldayIndexOf("0000")).toBe(539);
    expect(alldayIndexOf("0500")).toBe(839);
    expect(alldayIndexOf("0846")).toBe(1065);
    expect(alldayIndexOf("1345")).toBe(1364);
  });

  it("段內單調遞增且相鄰分鐘相差 1", () => {
    expect(alldayIndexOf("1502")! - alldayIndexOf("1501")!).toBe(1);
    expect(alldayIndexOf("0001")! - alldayIndexOf("0000")!).toBe(1);
    expect(alldayIndexOf("0847")! - alldayIndexOf("0846")!).toBe(1);
  });

  it("空檔(05:01–08:45 佔軸但無 bar)、一天之外(13:46–15:00)與壞值回 null", () => {
    expect(alldayIndexOf("0501")).toBe(null);
    expect(alldayIndexOf("0700")).toBe(null);
    expect(alldayIndexOf("0845")).toBe(null);
    expect(alldayIndexOf("1346")).toBe(null);
    expect(alldayIndexOf("1400")).toBe(null);
    expect(alldayIndexOf("1500")).toBe(null);
    expect(alldayIndexOf("")).toBe(null);
    expect(alldayIndexOf("xxxx")).toBe(null);
    expect(alldayIndexOf("2560")).toBe(null);
  });
});

describe("ALLDAY_TICKS(15:00 釘在軸起點;九顆依時間重排)", () => {
  it("九個標籤依 15:00 起算的順序,index 寫死", () => {
    expect(ALLDAY_TICKS).toEqual([
      { index: 0, label: "15:00" },
      { index: 179, label: "18:00" }, // 1800 − 1501
      { index: 359, label: "21:00" },
      { index: 539, label: "00:00" }, // 夜盤後半段起點
      { index: 719, label: "03:00" },
      { index: 839, label: "05:00" }, // 夜盤末格(空檔前)
      { index: 1079, label: "09:00" }, // 1065 + 14
      { index: 1199, label: "11:00" },
      { index: 1319, label: "13:00" },
    ]);
  });

  it("index 嚴格遞增且全落在 [0, 1364]", () => {
    for (let i = 1; i < ALLDAY_TICKS.length; i += 1) {
      expect(ALLDAY_TICKS[i]!.index).toBeGreaterThan(ALLDAY_TICKS[i - 1]!.index);
    }
    for (const t of ALLDAY_TICKS) {
      expect(t.index).toBeGreaterThanOrEqual(0);
      expect(t.index).toBeLessThanOrEqual(ALLDAY_LEN - 1);
    }
  });

  it("15:00 不在域內(首根是 1501)但仍釘在軸起點 index 0;其餘標籤與 alldayIndexOf 一致", () => {
    expect(alldayIndexOf("1500")).toBe(null);
    expect(ALLDAY_TICKS.find((t) => t.label === "05:00")!.index).toBe(alldayIndexOf("0500"));
    expect(ALLDAY_TICKS.find((t) => t.label === "09:00")!.index).toBe(alldayIndexOf("0900"));
    expect(ALLDAY_TICKS.find((t) => t.label === "00:00")!.index).toBe(alldayIndexOf("0000"));
  });
});

describe("anchorDateOf(期交所口徑:日盤 → 當日;夜盤 → 次一交易日)", () => {
  it("日盤 → 當日曆日", () => {
    expect(anchorDateOf("2026-08-25 08:46")).toBe("2026-08-25");
    expect(anchorDateOf("2026-08-25 13:45")).toBe("2026-08-25");
  });

  it("夜盤前半(D 15:01–23:59)→ D 的次一交易日", () => {
    expect(anchorDateOf("2026-08-24 15:01")).toBe("2026-08-25");
    expect(anchorDateOf("2026-08-24 23:59")).toBe("2026-08-25");
  });

  it("夜盤後半(D+1 00:00–05:00)→ 同一個次一交易日", () => {
    expect(anchorDateOf("2026-08-25 00:00")).toBe("2026-08-25");
    expect(anchorDateOf("2026-08-25 05:00")).toBe("2026-08-25");
  });

  it("週五夜盤 → 週一(週六凌晨同);未載日曆只跳週末", () => {
    expect(anchorDateOf("2026-08-28 22:00")).toBe("2026-08-31");
    expect(anchorDateOf("2026-08-29 03:00")).toBe("2026-08-31");
  });

  it("假日前夜盤 → 假日後首交易日(模組集合或顯式集合皆可)", () => {
    setHolidays(["2026-08-26"]);
    expect(anchorDateOf("2026-08-25 22:00")).toBe("2026-08-27");
    expect(anchorDateOf("2026-08-26 02:00")).toBe("2026-08-27");
    clearHolidays();
    expect(anchorDateOf("2026-08-25 22:00")).toBe("2026-08-26");
    expect(anchorDateOf("2026-08-25 22:00", new Set(["2026-08-26"]))).toBe("2026-08-27");
  });

  it("空檔時刻:13:46–15:00 → 當日(剛收的那天);05:01–08:45 → 當日(即將開的那天)", () => {
    expect(anchorDateOf("2026-08-25 14:00")).toBe("2026-08-25");
    expect(anchorDateOf("2026-08-25 07:00")).toBe("2026-08-25");
  });

  it("跨月 / 跨年進位正確", () => {
    expect(anchorDateOf("2026-08-31 22:00")).toBe("2026-09-01");
    expect(anchorDateOf("2026-12-31 22:00")).toBe("2027-01-01");
    expect(anchorDateOf("2027-01-01 03:00")).toBe("2027-01-01");
  });

  it("純日期(無時刻)原樣回傳;壞日期字串不炸(回怪字串,由 slice 自然切掉)", () => {
    expect(anchorDateOf("2026-08-25")).toBe("2026-08-25");
    expect(() => anchorDateOf("garbage 22:00")).not.toThrow();
    expect(() => anchorDateOf("garbage 03:00")).not.toThrow();
  });
});

describe("sliceCurrentAllday(取「錨定日 = 末根錨定日」的 bars)", () => {
  it("空輸入回空", () => {
    expect(sliceCurrentAllday([])).toEqual([]);
  });

  it("缺 15:01 首根也不錯位(不依賴任何特定分鐘存在);前一天的日盤被切掉", () => {
    const bars = [
      bar("2026-08-24 10:00", 1),
      bar("2026-08-24 15:05", 2),
      bar("2026-08-25 10:00", 3),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-24 15:05",
      "2026-08-25 10:00",
    ]);
  });

  it("13:45–15:00 之間(末根 = 13:45)→ 看剛收的那一天:左起昨 15:00", () => {
    const bars = [
      bar("2026-08-24 09:00", 1),
      bar("2026-08-24 22:00", 2),
      bar("2026-08-25 13:45", 3),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-24 22:00",
      "2026-08-25 13:45",
    ]);
  });

  it("15:01 首根一到就翻頁:剛收的那一天整段被切掉", () => {
    const bars = [
      bar("2026-08-24 22:00", 1),
      bar("2026-08-25 13:45", 2),
      bar("2026-08-25 15:01", 3),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual(["2026-08-25 15:01"]);
  });

  it("週末 (a):末根 = 週六 05:00 → 錨定週一,含週五 15:01 起的夜盤、切掉週五日盤", () => {
    const bars = [
      bar("2026-08-27 22:00", 1), // 週四夜(→ 週五)
      bar("2026-08-28 09:00", 2), // 週五日盤
      bar("2026-08-28 15:01", 3), // 週五夜(→ 週一)
      bar("2026-08-29 00:00", 4),
      bar("2026-08-29 05:00", 5),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-28 15:01",
      "2026-08-29 00:00",
      "2026-08-29 05:00",
    ]);
  });

  it("週末 (b):同份 bars 追加週一 08:46 → 週五夜盤與週一日盤同一天(不切)", () => {
    const bars = [
      bar("2026-08-28 09:00", 1),
      bar("2026-08-28 15:01", 2),
      bar("2026-08-29 00:00", 3),
      bar("2026-08-29 05:00", 4),
      bar("2026-08-31 08:46", 5),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-28 15:01",
      "2026-08-29 00:00",
      "2026-08-29 05:00",
      "2026-08-31 08:46",
    ]);
  });

  it("假日:週二夜盤與週四日盤同一天(週三休市;顯式集合)", () => {
    const bars = [bar("2026-08-25 10:00", 1), bar("2026-08-25 22:00", 2), bar("2026-08-27 09:00", 3)];
    const holidays = new Set(["2026-08-26"]);
    expect(sliceCurrentAllday(bars, holidays).map((b) => b.t)).toEqual([
      "2026-08-25 22:00",
      "2026-08-27 09:00",
    ]);
    // 未載日曆:週二夜歸週三,週四日盤自成一天
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual(["2026-08-27 09:00"]);
  });

  it("回傳的是原 bar 物件(不複製、不改動輸入陣列)", () => {
    const bars = [bar("2026-08-25 09:00", 1), bar("2026-08-25 10:00", 2)];
    const out = sliceCurrentAllday(bars);
    expect(out[0]).toBe(bars[0]);
    expect(bars.length).toBe(2);
  });
});

describe("ALLDAY_WINDOW / ALLDAY_HOUR_TICKS(core 的 x 窗與整點刻度)", () => {
  it("窗 = [0, 1364](key 值域就是軸索引本身,空檔佔格)", () => {
    expect(ALLDAY_WINDOW).toEqual({ start: 0, end: 1364 });
  });

  it("HourTick 形狀:minute 欄放**軸索引**、label 與 ALLDAY_TICKS 逐項相同", () => {
    expect(ALLDAY_HOUR_TICKS.map((t) => t.label)).toEqual(ALLDAY_TICKS.map((t) => t.label));
    expect(ALLDAY_HOUR_TICKS.map((t) => t.minute)).toEqual(ALLDAY_TICKS.map((t) => t.index));
    expect(ALLDAY_HOUR_TICKS.length).toBe(9);
  });
});

describe("alldayHhmmOf(軸位置 → 時刻;空檔索引也誠實回時刻)", () => {
  it("段界反查(含空檔兩端)", () => {
    expect(alldayHhmmOf(0)).toBe("15:01");
    expect(alldayHhmmOf(538)).toBe("23:59");
    expect(alldayHhmmOf(539)).toBe("00:00");
    expect(alldayHhmmOf(839)).toBe("05:00");
    expect(alldayHhmmOf(840)).toBe("05:01");
    expect(alldayHhmmOf(1064)).toBe("08:45");
    expect(alldayHhmmOf(1065)).toBe("08:46");
    expect(alldayHhmmOf(1364)).toBe("13:45");
  });

  it("可交易索引與 alldayIndexOf 互逆;空檔索引反查後 alldayIndexOf 回 null", () => {
    for (let i = 0; i < ALLDAY_LEN; i += 1) {
      const hhmm = alldayHhmmOf(i);
      expect(hhmm).not.toBe("");
      const back = alldayIndexOf(hhmm.replace(":", ""));
      if (i >= ALLDAY_GAP.start && i <= ALLDAY_GAP.end) expect(back).toBe(null);
      else expect(back).toBe(i);
    }
  });

  it("域外 / 非整數 → 空字串(不猜、不夾制)", () => {
    expect(alldayHhmmOf(-1)).toBe("");
    expect(alldayHhmmOf(ALLDAY_LEN)).toBe("");
    expect(alldayHhmmOf(1.5)).toBe("");
    expect(alldayHhmmOf(Number.NaN)).toBe("");
  });
});

describe("alldayIndexOfStamp", () => {
  it("`YYYY-MM-DD HH:MM` → 軸索引", () => {
    expect(alldayIndexOfStamp("2026-08-18 15:01")).toBe(0);
    expect(alldayIndexOfStamp("2026-08-19 00:00")).toBe(539);
    expect(alldayIndexOfStamp("2026-08-19 08:46")).toBe(1065);
    expect(alldayIndexOfStamp("2026-08-19 09:00")).toBe(alldayIndexOf("0900"));
  });

  it("空檔 / 一天之外的時戳 → null", () => {
    expect(alldayIndexOfStamp("2026-08-18 14:00")).toBeNull();
    expect(alldayIndexOfStamp("2026-08-18 05:30")).toBeNull();
  });

  it("非分 K 時戳(日 K:無空格)→ null", () => {
    expect(alldayIndexOfStamp("2026-08-18")).toBeNull();
    expect(alldayIndexOfStamp("")).toBeNull();
  });
});

describe("alldayBarsBetween(可交易索引距離;gate 5 的「落後 N 根」不把空檔算成根數)", () => {
  it("跨空檔:尾根 05:00(839)→ 成交 08:47(1066)= 2 根,不是 227", () => {
    expect(alldayBarsBetween(839, 1066)).toBe(2);
    expect(alldayBarsBetween(839, 1064)).toBe(0);
    expect(alldayBarsBetween(839, 1065)).toBe(1);
  });

  it("段內與跨夜盤兩半:純差值", () => {
    expect(alldayBarsBetween(0, 3)).toBe(3);
    expect(alldayBarsBetween(538, 540)).toBe(2);
  });

  it("to ≤ from → 0(不回負數)", () => {
    expect(alldayBarsBetween(5, 5)).toBe(0);
    expect(alldayBarsBetween(10, 5)).toBe(0);
  });
});
