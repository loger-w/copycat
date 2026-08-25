/** @vitest-environment jsdom */
import { cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntradayChartCore, StockIntradayChart } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { FillPoint } from "@/lib/fill-marks";
import { fromSnapshot } from "@/lib/stock-accum";
import { R_AXIS_W } from "@/lib/stock-intraday-svg";
import { wrap } from "@/test-utils";

/** 圖牆卡片與單檔頁共用同一份渲染碼(change-spec §6 A):**圖形語彙全同、文字 chrome 精簡**。
 *
 *  這一檔鎖的是兩個變體的差集(AD-4)。差集若靜默漂掉,症狀是卡片內長出 toggle 鈕
 *  (點它會同時把主檔切走,巢狀互動元素)或多一層框中框 —— 既有的 StockIntradayChart
 *  測試全在 page 變體上,對 card 變體零覆蓋。 */

const OVERLAY = { cdp: null, ma5: null, ma20: null, date: "2026-08-14" };

/** 疊線回應可逐案覆寫(帶內標籤那組要真的有 CDP / MA 值);預設仍是全 null 的 OVERLAY */
let overlayResponse: object = OVERLAY;

beforeEach(() => {
  window.localStorage.removeItem("copycat-chart-toggles");
  overlayResponse = OVERLAY;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(overlayResponse))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  // 當日高低是 day-high / day-low 標記的來源(等值反查 minute 的 h / l)
  high: 2_395_000,
  low: 2_370_000,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
});

const TOGGLES: ChartToggles = { vwap: true, cdp: false, ma: false, bb: true, vp: true, fills: true, idxTwse: false, idxOtc: false, syncHover: true };

const CARD_W = 246;

/** 刻意落在**最新分鐘**(542,= 未 hover 時 readout 顯示的那一格):放在別的分鐘的話
 *  「card 不追加成交欄」會因為「那一格本來就沒有成交」而恆綠(vacuous)。 */
const CARD_FILLS: readonly FillPoint[] = [
  { minute: 542, priceMilli: 2_385_000, side: "B", qty: 2 },
];

function card(fills?: readonly FillPoint[]) {
  return wrap(
    <IntradayChartCore
      accum={ACCUM}
      toggles={TOGGLES}
      variant="card"
      width={CARD_W}
      mainHeight={140}
      subHeight={38}
      fills={fills}
    />,
  );
}

describe("IntradayChartCore variant=card", () => {
  it("不 render toggle 鈕列 —— 卡片外層自己是 role=button,內層不得有 button", () => {
    const { container } = card();
    expect(container.querySelectorAll("button").length).toBe(0);
  });

  it("不 render figcaption 說明列(卡片寬度裝不下外/內盤/判定率)", () => {
    const { container } = card();
    expect(container.querySelector("figcaption")).toBeNull();
  });

  it("外層是 div 不是 figure,且無 border / bg / padding(卡片自己已有框)", () => {
    const { container } = card();
    const root = container.firstElementChild!;
    expect(root.tagName).toBe("DIV");
    expect(container.querySelector("figure")).toBeNull();
    const cls = root.className;
    expect(cls).not.toContain("border");
    expect(cls).not.toContain("bg-surface");
    expect(cls).not.toContain("p-4");
  });

  it("readout 只給前 4 欄(時間 / 價 / % / 量),外與內兩欄省略", () => {
    const { container } = card();
    const readout = container.querySelector('[data-testid="chart-readout"]')!;
    expect(readout.children.length).toBe(4);
    expect(readout.textContent).not.toContain("外");
    expect(readout.textContent).not.toContain("內");
  });

  it("主圖與副圖的 viewBox 寬相等且等於 width prop(共用單一 w,不再靠兩常數碰巧相等)", () => {
    const { container } = card();
    const svgs = [...container.querySelectorAll("svg")];
    expect(svgs.length).toBe(2);
    const widths = svgs.map((s) => s.getAttribute("viewBox")!.split(" ")[2]);
    expect(widths).toEqual([String(CARD_W), String(CARD_W)]);
  });

  /** 🟢 R2 SC-4:246px 寬的 readout 是 `overflow-hidden`,追加第五欄必被裁 = 靜默失敗。
   *  標記本身已承載「這裡成交了」,與 card 砍外 / 內兩欄同理(page 才追加)。 */
  it("有成交點時:三角照畫在卡片上,但 readout 仍四欄且不含「成交」", () => {
    const { container } = card(CARD_FILLS);
    expect(container.querySelectorAll('polygon[data-testid^="fill-"]').length).toBe(1);
    const readout = container.querySelector('[data-testid="chart-readout"]')!;
    expect(readout.children.length).toBe(4);
    expect(readout.textContent).not.toContain("成交");
  });

  it("圖形語彙與單檔頁相同:價線 / VP 長條 / 高低標記 / 現價圈 / 量副圖 / 時間標都在", () => {
    const { container } = card();
    expect(container.querySelector('polyline[class*="stroke-bull"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="day-high"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="last-dot"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="energy-bar"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="y-tick-price"]')).toBeTruthy();
  });
});

/** 🟢 code review TC-5(mod/cdp-edge-label-avoid,D6 / SC-4 R11):圖牆卡片的右緣**帶內**標籤。
 *
 *  D6 的取捨是「寧疊不丟」—— 帶內的 `價位*` 是 CDP 唯一的價位訊息,而 `cardSvgBox` 沒有高度
 *  地板(4×4 圖牆 mainH ≈ 80 時 capacity 6 < 7)。這一組鎖的就是那個取捨:**顆數與文字集合
 *  在 card 變體上與單檔頁完全相同**,不因寬度縮到 246 就少印一顆。
 *  幾何(兩兩不相疊)刻意**不在這裡斷言**:R11 明訂矮卡片允許貼齊界邊疊印,幾何由
 *  `lib/stock-intraday-svg.test.ts` 的 `bandLabels` describe 逐點量。 */
describe("IntradayChartCore variant=card 右緣帶內標籤(TC-5)", () => {
  /** 帶內文字的 x = `w − R_AXIS_W + 2`(anchor=start);card 的 w = CARD_W */
  const BAND_X = String(CARD_W - R_AXIS_W + 2);

  /** 七條擠在一起(相鄰 11_600 毫元;card mainH=140 → 相鄰約 3px,遠小於 EDGE_LABEL_H) */
  const CROWDED = {
    cdp: { ah: 2_364_000, nh: 2_352_400, cdp: 2_340_800, nl: 2_329_200, al: 2_317_600 },
    ma5: 2_306_000,
    ma20: 2_294_400,
    date: "2026-07-25",
  };

  const ON: ChartToggles = { ...TOGGLES, cdp: true, ma: true };

  function bandTexts(container: HTMLElement): SVGTextElement[] {
    const main = container.querySelector("svg")!;
    return [...main.querySelectorAll("text")].filter((t) => t.getAttribute("x") === BAND_X);
  }

  it("CDP + MA 全開 → 帶內 7 顆全印,文字集合與單檔頁相同(D6:不截斷、不丟棄)", async () => {
    overlayResponse = CROWDED;
    const { container } = wrap(
      <IntradayChartCore
        accum={ACCUM}
        toggles={ON}
        variant="card"
        width={CARD_W}
        mainHeight={140}
        subHeight={38}
      />,
    );
    await waitFor(() => expect(bandTexts(container).length).toBe(7));
    // fmtTickPrice 口徑(5 元 tick,snapNearest):2_364_000 → 2365、2_317_600 → 2320
    expect(bandTexts(container).map((t) => t.textContent)).toEqual([
      "2365*",
      "2350*",
      "2340*",
      "2330*",
      "2320*",
      "MA5",
      "MA20",
    ]);
  });

  /** 負控:CDP / MA 兩鈕皆關時帶內一顆都不印(**後端資料備妥也一樣** —— 閘在 toggle 不在資料)。
   *  同時是上一條的 vacuity 檢查:BAND_X 這個 x 沒有誤收到別的 `<text>`(時間標 / 價位刻度)。
   *  「連 `/api/stock/overlay` 都不打」與「一顆都不印」要一起斷言:少了前者,兩鈕皆關卻照樣
   *  發查詢時這條仍會綠(render 當下 fetch 尚未 resolve,顆數本來就是 0)—— 恆綠的負控。 */
  it("CDP / MA 兩鈕皆關(即使疊線資料可得)→ 不打 overlay 查詢、帶內一顆文字都沒有", () => {
    overlayResponse = CROWDED;
    expect(TOGGLES.cdp).toBe(false);
    expect(TOGGLES.ma).toBe(false);
    const { container } = card();
    expect(vi.mocked(globalThis.fetch).mock.calls.length).toBe(0);
    expect(bandTexts(container).length).toBe(0);
  });
});

describe("IntradayChartCore variant=page(單檔頁 chrome 全在)", () => {
  // 🟢 R2 SC-5:多一顆「成交點」→ 四鈕變**五鈕**(事前標記的該紅:schema 擴充)
  // 🟢 F1(chart-ux-batch-0826):加權 / 櫃買兩顆指數疊線鈕 → **七鈕**(同樣事前標記)
  it("toggle 七鈕 + figcaption + figure 外層", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelectorAll("button").length).toBe(7);
    expect(container.querySelector("figcaption")).toBeTruthy();
    expect(container.firstElementChild!.tagName).toBe("FIGURE");
  });

  it("readout 六欄(外 / 內兩欄在)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const readout = container.querySelector('[data-testid="chart-readout"]')!;
    expect(readout.children.length).toBe(6);
    expect(readout.textContent).toContain("外");
    expect(readout.textContent).toContain("內");
  });
});
