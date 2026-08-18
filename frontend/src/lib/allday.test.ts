import { describe, expect, it } from "vitest";

import {
  ALLDAY_HOUR_TICKS,
  ALLDAY_LEN,
  ALLDAY_SEGMENTS,
  ALLDAY_TICKS,
  ALLDAY_WINDOW,
  alldayHhmmOf,
  alldayIndexOf,
  alldayIndexOfStamp,
  anchorDateOf,
  sliceCurrentAllday,
} from "@/lib/allday";
import type { Bar } from "@/lib/candle";

function bar(t: string, c = 100): Bar {
  return { t, o: c, h: c, l: c, c, v: 1 };
}

describe("ALLDAY_SEGMENTS(與 futures_source.FUTURES_ALLDAY_DOMAIN 對齊)", () => {
  it("三段長度為 300 / 539 / 301,總和 1140", () => {
    expect(ALLDAY_SEGMENTS.map((s) => s.len)).toEqual([300, 539, 301]);
    expect(ALLDAY_SEGMENTS.reduce((a, s) => a + s.len, 0)).toBe(1140);
    expect(ALLDAY_LEN).toBe(1140);
  });

  it("段界字串與後端三段相同(改一邊必改另一邊)", () => {
    expect(ALLDAY_SEGMENTS.map((s) => [s.start, s.end])).toEqual([
      ["0846", "1345"],
      ["1501", "2359"],
      ["0000", "0500"],
    ]);
  });
});

describe("alldayIndexOf", () => {
  it("三段錨點值(0845 開盤 → 首根終點標記 0846 = index 0)", () => {
    expect(alldayIndexOf("0846")).toBe(0);
    expect(alldayIndexOf("1345")).toBe(299);
    expect(alldayIndexOf("1501")).toBe(300);
    expect(alldayIndexOf("2359")).toBe(838);
    expect(alldayIndexOf("0000")).toBe(839);
    expect(alldayIndexOf("0500")).toBe(1139);
  });

  it("段內單調遞增且相鄰分鐘相差 1", () => {
    expect(alldayIndexOf("0847")! - alldayIndexOf("0846")!).toBe(1);
    expect(alldayIndexOf("1502")! - alldayIndexOf("1501")!).toBe(1);
    expect(alldayIndexOf("0001")! - alldayIndexOf("0000")!).toBe(1);
  });

  it("死區(13:46–15:00 / 05:01–08:45)與壞值回 null", () => {
    expect(alldayIndexOf("1346")).toBe(null);
    expect(alldayIndexOf("1400")).toBe(null);
    expect(alldayIndexOf("1500")).toBe(null);
    expect(alldayIndexOf("0501")).toBe(null);
    expect(alldayIndexOf("0845")).toBe(null);
    expect(alldayIndexOf("")).toBe(null);
    expect(alldayIndexOf("xxxx")).toBe(null);
    expect(alldayIndexOf("2560")).toBe(null);
  });
});

describe("ALLDAY_TICKS(段起點法:15:00 標籤釘在夜盤段起點)", () => {
  it("九個標籤,index 全部落在 [0, 1139]", () => {
    expect(ALLDAY_TICKS.map((t) => t.label)).toEqual([
      "09:00",
      "11:00",
      "13:00",
      "15:00",
      "18:00",
      "21:00",
      "00:00",
      "03:00",
      "05:00",
    ]);
    for (const t of ALLDAY_TICKS) {
      expect(t.index).toBeGreaterThanOrEqual(0);
      expect(t.index).toBeLessThanOrEqual(ALLDAY_LEN - 1);
    }
  });

  it("index 嚴格遞增(軸標籤不可回頭)", () => {
    for (let i = 1; i < ALLDAY_TICKS.length; i += 1) {
      expect(ALLDAY_TICKS[i]!.index).toBeGreaterThan(ALLDAY_TICKS[i - 1]!.index);
    }
  });

  it("15:00 不在域內(首根是 1501)但仍釘在夜盤段起點 index 300", () => {
    expect(alldayIndexOf("1500")).toBe(null);
    expect(ALLDAY_TICKS.find((t) => t.label === "15:00")!.index).toBe(300);
  });

  it("域內標籤的 index 與 alldayIndexOf 一致", () => {
    expect(ALLDAY_TICKS.find((t) => t.label === "09:00")!.index).toBe(alldayIndexOf("0900"));
    expect(ALLDAY_TICKS.find((t) => t.label === "21:00")!.index).toBe(alldayIndexOf("2100"));
    expect(ALLDAY_TICKS.find((t) => t.label === "00:00")!.index).toBe(alldayIndexOf("0000"));
    expect(ALLDAY_TICKS.find((t) => t.label === "05:00")!.index).toBe(alldayIndexOf("0500"));
  });
});

describe("anchorDateOf(≤05:00 屬前一交易日)", () => {
  it("日盤與夜盤前半 → 當日", () => {
    expect(anchorDateOf("2026-08-05 08:46")).toBe("2026-08-05");
    expect(anchorDateOf("2026-08-05 13:45")).toBe("2026-08-05");
    expect(anchorDateOf("2026-08-05 15:01")).toBe("2026-08-05");
    expect(anchorDateOf("2026-08-05 23:59")).toBe("2026-08-05");
  });

  it("夜盤後半(00:00–05:00)→ 前一日", () => {
    expect(anchorDateOf("2026-08-06 00:00")).toBe("2026-08-05");
    expect(anchorDateOf("2026-08-06 05:00")).toBe("2026-08-05");
  });

  it("跨月 / 跨年退位正確", () => {
    expect(anchorDateOf("2026-09-01 00:30")).toBe("2026-08-31");
    expect(anchorDateOf("2027-01-01 03:00")).toBe("2026-12-31");
  });

  it("純日期(無時刻)原樣回傳", () => {
    expect(anchorDateOf("2026-08-05")).toBe("2026-08-05");
  });
});

describe("sliceCurrentAllday(以最後一根 bar 反推錨定日)", () => {
  it("空輸入回空", () => {
    expect(sliceCurrentAllday([])).toEqual([]);
  });

  it("缺 08:46 那根也不錯位(不依賴任何特定分鐘存在)", () => {
    const bars = [
      bar("2026-08-04 09:30", 1),
      bar("2026-08-05 08:50", 2),
      bar("2026-08-05 10:00", 3),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-05 08:50",
      "2026-08-05 10:00",
    ]);
  });

  it("夜盤-only 冷啟動:末根 = 次日 01:00 → 錨定回前一日,整段夜盤保留", () => {
    const bars = [
      bar("2026-08-04 10:00", 1),
      bar("2026-08-05 13:45", 2),
      bar("2026-08-05 15:01", 3),
      bar("2026-08-06 01:00", 4),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-05 13:45",
      "2026-08-05 15:01",
      "2026-08-06 01:00",
    ]);
  });

  it("週末跨越 (a):末根 = 週六 05:00 → anchor 為週五,含週五 08:46 起全段", () => {
    // 2026-08-06 週四 / 08-07 週五 / 08-08 週六
    const bars = [
      bar("2026-08-06 09:00", 1),
      bar("2026-08-07 08:46", 2),
      bar("2026-08-07 15:01", 3),
      bar("2026-08-08 00:00", 4),
      bar("2026-08-08 05:00", 5),
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual([
      "2026-08-07 08:46",
      "2026-08-07 15:01",
      "2026-08-08 00:00",
      "2026-08-08 05:00",
    ]);
  });

  it("週末跨越 (b):同份 bars 追加週一 08:46 → anchor 切至週一,週五段被切掉", () => {
    const bars = [
      bar("2026-08-06 09:00", 1),
      bar("2026-08-07 08:46", 2),
      bar("2026-08-07 15:01", 3),
      bar("2026-08-08 00:00", 4),
      bar("2026-08-08 05:00", 5),
      bar("2026-08-10 08:46", 6), // 週一
    ];
    expect(sliceCurrentAllday(bars).map((b) => b.t)).toEqual(["2026-08-10 08:46"]);
  });

  it("回傳的是原 bar 物件(不複製、不改動輸入陣列)", () => {
    const bars = [bar("2026-08-05 09:00", 1), bar("2026-08-05 10:00", 2)];
    const out = sliceCurrentAllday(bars);
    expect(out[0]).toBe(bars[0]);
    expect(bars.length).toBe(2);
  });
});

/** 以下為「近全軸當 IntradayChartCore 的 x 窗」所需的新增(change-spec §3.2)。
 *  既有 export 的值與簽名一律不動(W-9)—— 那由上面各節逐值鎖住。 */

describe("ALLDAY_WINDOW / ALLDAY_HOUR_TICKS(core 的 x 窗與整點刻度)", () => {
  it("窗 = [0, ALLDAY_LEN − 1](key 值域就是軸索引本身)", () => {
    expect(ALLDAY_WINDOW).toEqual({ start: 0, end: ALLDAY_LEN - 1 });
    expect(ALLDAY_WINDOW.end).toBe(1139);
  });

  it("HourTick 形狀:minute 欄放**軸索引**、label 與 ALLDAY_TICKS 逐項相同", () => {
    expect(ALLDAY_HOUR_TICKS.map((t) => t.label)).toEqual(ALLDAY_TICKS.map((t) => t.label));
    expect(ALLDAY_HOUR_TICKS.map((t) => t.minute)).toEqual(ALLDAY_TICKS.map((t) => t.index));
    expect(ALLDAY_HOUR_TICKS.length).toBe(9);
  });

  it("每個刻度都落在窗內(否則 minuteToX 會把標籤畫出繪圖區)", () => {
    for (const t of ALLDAY_HOUR_TICKS) {
      expect(t.minute).toBeGreaterThanOrEqual(ALLDAY_WINDOW.start);
      expect(t.minute).toBeLessThanOrEqual(ALLDAY_WINDOW.end);
    }
  });
});

describe("alldayHhmmOf(alldayIndexOf 的反函式)", () => {
  it("三段錨點反查", () => {
    expect(alldayHhmmOf(0)).toBe("08:46");
    expect(alldayHhmmOf(299)).toBe("13:45");
    expect(alldayHhmmOf(300)).toBe("15:01");
    expect(alldayHhmmOf(838)).toBe("23:59");
    expect(alldayHhmmOf(839)).toBe("00:00");
    expect(alldayHhmmOf(1139)).toBe("05:00");
  });

  it("與 alldayIndexOf 互逆(全軸逐格)", () => {
    for (let i = 0; i < ALLDAY_LEN; i += 1) {
      const hhmm = alldayHhmmOf(i);
      expect(hhmm).not.toBe("");
      expect(alldayIndexOf(hhmm.replace(":", ""))).toBe(i);
    }
  });

  it("域外 / 非整數 → 空字串(不猜、不夾制)", () => {
    expect(alldayHhmmOf(-1)).toBe("");
    expect(alldayHhmmOf(ALLDAY_LEN)).toBe("");
    expect(alldayHhmmOf(1.5)).toBe("");
    expect(alldayHhmmOf(Number.NaN)).toBe("");
  });
});

describe("alldayIndexOfStamp(自 FuturesChart indexOfBar 搬入,行為逐字同)", () => {
  it("`YYYY-MM-DD HH:MM` → 軸索引", () => {
    expect(alldayIndexOfStamp("2026-08-18 08:46")).toBe(0);
    expect(alldayIndexOfStamp("2026-08-18 09:00")).toBe(alldayIndexOf("0900"));
    expect(alldayIndexOfStamp("2026-08-18 15:01")).toBe(300);
    expect(alldayIndexOfStamp("2026-08-19 00:00")).toBe(839);
  });

  it("死區時戳 → null", () => {
    expect(alldayIndexOfStamp("2026-08-18 14:00")).toBeNull();
    expect(alldayIndexOfStamp("2026-08-18 05:30")).toBeNull();
  });

  it("非分 K 時戳(日 K:無空格)→ null", () => {
    expect(alldayIndexOfStamp("2026-08-18")).toBeNull();
    expect(alldayIndexOfStamp("")).toBeNull();
  });
});
