import { describe, expect, it } from "vitest";

import { buildOverlayGeometry, outOfDomainLevels } from "@/lib/index-chart-svg";
import { overlayLines, type StockOverlay } from "@/lib/stock-intraday-svg";

const SIZE = { width: 270, height: 100 };

function minutes(entries: [string, number][]): Record<string, number> {
  return Object.fromEntries(entries);
}

describe("buildOverlayGeometry", () => {
  it("各線相對各自 ref 的 % 共域,含 zeroY", () => {
    const g = buildOverlayGeometry(
      [
        { minutes: minutes([["0901", 43_634_190], ["0930", 42_000_000]]), ref: 43_634_190 },
        { minutes: minutes([["0901", 378_090], ["0930", 359_800]]), ref: 378_090 },
      ],
      SIZE,
    );
    expect(g.lines).toHaveLength(2);
    // 第一點皆為 0%
    expect(g.lines[0]!.pts[0]!.pct).toBeCloseTo(0, 5);
    expect(g.lines[1]!.pts[0]!.pct).toBeCloseTo(0, 5);
    // 櫃買跌幅較深 → 末點 pct 較低
    expect(g.lines[1]!.pts[1]!.pct).toBeLessThan(g.lines[0]!.pts[1]!.pct);
    expect(Number.isFinite(g.zeroY)).toBe(true);
    expect(g.pctDomain[0]).toBeLessThan(g.pctDomain[1]);
  });

  it("ref null 的線被略過", () => {
    const g = buildOverlayGeometry(
      [
        { minutes: minutes([["0901", 100]]), ref: null },
        { minutes: minutes([["0901", 378_090]]), ref: 378_090 },
      ],
      SIZE,
    );
    expect(g.lines).toHaveLength(1);
  });
});

describe("outOfDomainLevels(SC-7 域內/域外分類)", () => {
  // 幾何寫字面量,不由已刪的 `buildIndexGeometry` 產:本 describe 要測的是
  // `outOfDomainLevels` 對「域」的分類,域怎麼算出來的與它無關(同源算回來也測不到東西)。
  //
  // 值 = 原 fixture(minutes {"0901": 23_000_000} / ref 23_000_000 / high 23_100_000 /
  // low 22_990_000,SIZE 270×100)經 buildIndexGeometry 的域公式所得:
  //   yTop    = high * 1.003 = 23_100_000 * 1.003 = 23_169_299.999_999_996(浮點,非整數)
  //   yBottom = low  * 0.997 = 22_990_000 * 0.997 = 22_921_030
  //   toY(p)  = (yTop − p) / (yTop − yBottom) * height
  // `toY` 是 `overlayLines`(下面對照組)要的第二欄,一併給。
  //
  // yTop 那 15 位小數只是**出處還原**(把域公式的浮點結果原樣抄回),不是被斷言的精度:
  // 下面的案子只依賴「yTop 落在 23_100_000 這個量級之上」——`ah` / `ma20` 之類的樁值是拿
  // yTop / yBottom 加減百萬去構造的,末位差幾個 ulp 不會改變任何一筆的域內外分類。
  const yTop = 23_169_299.999_999_996;
  const yBottom = 22_921_030;
  const g: { yDomain: [number, number]; toY: (p: number) => number } = {
    yDomain: [yBottom, yTop],
    toY: (p) => ((yTop - p) / (yTop - yBottom)) * SIZE.height,
  };
  const overlay: StockOverlay = {
    cdp: {
      cdp: 23_050_000,
      ah: yTop + 1_000_000,
      nh: 23_100_000,
      nl: 23_000_000,
      al: yBottom - 1_000_000,
    },
    ma5: 23_020_000,
    ma20: yBottom - 500_000,
    date: "2026-08-13",
  };

  it("域外值 → 掛牌項含正確 dir;域內值只進 overlayLines", () => {
    expect(outOfDomainLevels(overlay, g, { cdp: true, ma: true })).toEqual([
      { level: "ah", priceMilli: yTop + 1_000_000, dir: "up" },
      { level: "al", priceMilli: yBottom - 1_000_000, dir: "down" },
      { level: "ma20", priceMilli: yBottom - 500_000, dir: "down" },
    ]);
    expect(overlayLines(overlay, g, { cdp: true, ma: true }).map((l) => l.level)).toEqual([
      "nh",
      "cdp",
      "nl",
      "ma5",
    ]);
  });

  it("toggle 關的類別不掛牌", () => {
    expect(outOfDomainLevels(overlay, g, { cdp: false, ma: true })).toEqual([
      { level: "ma20", priceMilli: yBottom - 500_000, dir: "down" },
    ]);
    expect(outOfDomainLevels(overlay, g, { cdp: false, ma: false })).toEqual([]);
  });

  /** 🟢 N023(mod/chart-label-batch;R10 review T-4):**端點案**。
   *
   *  既有兩案只有「明顯域外(±50~100 萬)」與「明顯域內」,價位**恰好落在域端點**時
   *  沒有任何 assertion。現行實作是嚴格不等式(`p > yTop` / `p < yBottom`)→ 端點算
   *  **域內**、不掛牌;改成 `>=` / `<=` 會多掛一顆而全套照樣綠。
   *
   *  釘的是**互補性**而不只是這一支的回傳:`outOfDomainLevels` 與 `overlayLines` 共用
   *  同一組域判定,同一個值只能進其中一邊 —— 兩邊各判各的話會出現「線也畫了、又掛一次
   *  牌」或「兩邊都不要」的靜默漏畫(這正是 `outOfDomainLevels` 檔頭那段註解的立場)。
   *  所以下面每一案都同時斷言兩支的結果。 */
  it("端點(p === yTop / p === yBottom)算**域內**:不掛牌,改由 overlayLines 畫線", () => {
    const atEdges: StockOverlay = {
      cdp: { cdp: 23_050_000, ah: yTop, nh: 23_100_000, nl: 23_000_000, al: yBottom },
      ma5: yTop,
      ma20: yBottom,
      date: "2026-08-13",
    };
    // 一顆都不掛牌(嚴格不等式)
    expect(outOfDomainLevels(atEdges, g, { cdp: true, ma: true })).toEqual([]);
    // 互補:同樣這四顆端點值全部進線體(`overlayLines` 的域判定是閉區間)
    expect(overlayLines(atEdges, g, { cdp: true, ma: true }).map((l) => l.level)).toEqual([
      "ah",
      "nh",
      "cdp",
      "nl",
      "al",
      "ma5",
      "ma20",
    ]);
  });

  it("端點外一個 ulp 級的量(±1 毫點)→ 翻成掛牌,且線體不再有它(判定沒有死區)", () => {
    const justOutside: StockOverlay = {
      cdp: { cdp: 23_050_000, ah: yTop + 1, nh: 23_100_000, nl: 23_000_000, al: yBottom - 1 },
      ma5: 23_020_000,
      ma20: null,
      date: "2026-08-13",
    };
    expect(outOfDomainLevels(justOutside, g, { cdp: true, ma: true })).toEqual([
      { level: "ah", priceMilli: yTop + 1, dir: "up" },
      { level: "al", priceMilli: yBottom - 1, dir: "down" },
    ]);
    expect(overlayLines(justOutside, g, { cdp: true, ma: true }).map((l) => l.level)).toEqual([
      "nh",
      "cdp",
      "nl",
      "ma5",
    ]);
  });
});
