import { describe, expect, it } from "vitest";

import { bandSeries, bollinger } from "@/lib/bollinger";
import { movingAverage, type Bar } from "@/lib/candle";

function bar(c: number, i = 0): Bar {
  return { t: `2026-01-${String(i + 1).padStart(2, "0")}`, o: c, h: c, l: c, c, v: 1 };
}

/** 收盤序列 → bars */
function bars(closes: number[]): Bar[] {
  return closes.map((c, i) => bar(c, i));
}

describe("bollinger", () => {
  it("前 n−1 根為 null,第 n 根起有值", () => {
    const out = bollinger(bars([1, 2, 3, 4, 5].map((x) => x * 1000)), 3);
    expect(out[0]).toBeNull();
    expect(out[1]).toBeNull();
    expect(out[2]).not.toBeNull();
    expect(out[4]).not.toBeNull();
  });

  it("資料不足 n 根 → 全 null", () => {
    expect(bollinger(bars([1000, 2000]), 20).every((b) => b === null)).toBe(true);
  });

  it("空輸入 → 空陣列,不崩", () => {
    expect(bollinger([], 20)).toEqual([]);
  });

  it("中軌逐根等於同期 movingAverage(圖上「中軌 = MA20」必須是同一條線)", () => {
    const b = bars(Array.from({ length: 40 }, (_, i) => 100_000 + i * 137));
    const bands = bollinger(b, 20);
    const ma = movingAverage(b, 20);
    for (let i = 0; i < b.length; i += 1) {
      if (bands[i] === null) {
        expect(ma[i]).toBeNull();
      } else {
        expect(bands[i]!.mid).toBe(ma[i]);
      }
    }
  });

  it("全平盤 σ=0 → 三線重合", () => {
    const out = bollinger(bars(Array.from({ length: 25 }, () => 100_000)), 20);
    const last = out[24]!;
    expect(last.upper).toBe(100_000);
    expect(last.lower).toBe(100_000);
    expect(last.mid).toBe(100_000);
  });

  it("upper > mid > lower 且對稱(k=2)", () => {
    const out = bollinger(bars([1, 5, 2, 8, 3, 9, 4, 7, 6, 10].map((x) => x * 10_000)), 5);
    const b = out[9]!;
    expect(b.upper).toBeGreaterThan(b.mid);
    expect(b.lower).toBeLessThan(b.mid);
    // 上下軌對中軌對稱(容 1 毫元的 floor/round 差)
    expect(Math.abs(b.upper - b.mid - (b.mid - b.lower))).toBeLessThanOrEqual(2);
  });

  // R9:高檔盤整後一根急殺 → 均值仍貼近高檔、σ 被那根撐大 → 上軌衝出視窗最高價。
  // (低檔的鏡像同理會讓下軌衝破最低價。)這證明 y 域不納入 BB 就會把軌線畫到圖框外。
  it("上軌可以超出全域最高價(R9:所以 y 域必須納入,否則會被裁到圖外)", () => {
    const closes = [30, 30, 30, 30, 30, 30, 30, 30, 30, 10].map((x) => x * 10_000);
    const out = bollinger(bars(closes), 10);
    const b = out[9]!;
    expect(b.upper).toBeGreaterThan(Math.max(...closes));
  });

  it("下軌可以低於全域最低價(鏡像情形)", () => {
    const closes = [10, 10, 10, 10, 10, 10, 10, 10, 10, 30].map((x) => x * 10_000);
    const out = bollinger(bars(closes), 10);
    expect(out[9]!.lower).toBeLessThan(Math.min(...closes));
  });

  it("bandSeries 抽出單一數列並保留 null 位置", () => {
    const out = bollinger(bars([1, 2, 3, 4, 5].map((x) => x * 1000)), 3);
    const upper = bandSeries(out, "upper");
    expect(upper.length).toBe(5);
    expect(upper[0]).toBeNull();
    expect(upper[1]).toBeNull();
    expect(typeof upper[2]).toBe("number");
  });
});
