/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { IntradayChartCore, StockIntradayChart } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { fmt, fmtIndexPts } from "@/lib/format";
import { indexSeriesToAccum } from "@/lib/index-accum-adapter";
import { fromSnapshot } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  EDGE_LABEL_H,
  labelWidth,
  R_AXIS_W,
  SPOT_WINDOW,
  type StockOverlay,
} from "@/lib/stock-intraday-svg";
import { fmtTickPrice, snapDown } from "@/lib/stock-tick";
import { wrap } from "@/test-utils";

/** `IntradayChartCore` 的 `mode="index"` 契約(change-spec R4 §3.1)。
 *
 *  這一檔鎖的是 **stock 與 index 兩態的差集**,以及「stock 態逐字不變」(W-1)。
 *  差集靜默漂掉的樣態:指數圖長出永遠空的成交量副圖、readout 報「量 0 / 外 0 / 內 0」
 *  這種假數字、或 core 拿 `IX:TWSE` 當股號去打 `/api/stock/overlay/` 吃 404。 */

const VB = { width: 800, height: 260 };

/** 對稱域推導(fixture 的可讀性靠這段註解,不靠讀者心算):
 *  ref 23000、收盤極值 ±50 → 半幅 = max(50, 40, ref×1%=230) × 1.1 = 253
 *  → y 域 [22747, 23253]。CDP 的 ah/nh 在域上、nl/al 在域下 → 四顆掛牌;
 *  cdp 本尊與 ma5 在域內 → 畫線 + 右緣價位標。 */
const SERIES: IndexSeries = {
  p: 22_960_000,
  ref: 23_000_000,
  high: 23_060_000,
  low: 22_950_000,
  stale: false,
  minutes: { "0900": 23_000_000, "0901": 23_050_000, "0902": 22_960_000 },
};

const IDX = indexSeriesToAccum(SERIES, "IX:TWSE", "加權指數");

/** ma5 刻意取 **23018**(非合法檔位):`fmtTickPrice` 會 snap 成 23020,
 *  `fmt` 才印 23018 —— 指數沒有 tick 表可言,snap 出來的價位是憑空捏造的(SC-2)。 */
const OVERLAY_IDX: StockOverlay = {
  // cdp / ma5 非 5 點整數倍且帶小數(review T-1 / C-2:整數倍 fixture 讓 snap 與整數點同值)
  cdp: { cdp: 23_001_440, ah: 24_100_000, nh: 23_500_000, nl: 22_700_000, al: 22_500_000 },
  ma5: 23_018_440,
  ma20: null,
  date: "2026-08-15",
};

/** MA5 貼近上緣(域頂 23253)→ 自然 y ≈ 5,與第一顆掛牌(top = 9)同一條走廊。
 *  掛牌是 KR-1 的唯一訊號不可被推,所以該讓位的是 MA。 */
const OVERLAY_MA_TOP: StockOverlay = { ...OVERLAY_IDX, ma5: 23_250_000 };

const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: true, bb: true, vp: true, fills: true };

let fetchMock: Mock;

beforeEach(() => {
  window.localStorage.removeItem("copycat-chart-toggles");
  fetchMock = vi.fn(async () => new Response(JSON.stringify(OVERLAY_IDX)));
  vi.stubGlobal("fetch", fetchMock);
  // jsdom getBoundingClientRect 恆 0 → hover 座標換算需要真實寬高(frontend-testing 慣例)
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: VB.width, bottom: VB.height,
    width: VB.width, height: VB.height, x: 0, y: 0,
    toJSON: () => ({}),
  } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

type CoreProps = Parameters<typeof IntradayChartCore>[0];

function renderIndex(over: Partial<CoreProps> = {}) {
  return wrap(
    <IntradayChartCore
      accum={IDX}
      toggles={TOGGLES}
      onToggle={() => {}}
      variant="page"
      mode="index"
      overlay={OVERLAY_IDX}
      ariaLabel="加權指數分時走勢"
      {...over}
    />,
  );
}

describe("IntradayChartCore mode=\"index\"", () => {
  it("readout 三欄(時間 / 點位 / 漲跌%)—— 量 / 外 / 內三欄指數沒有,不印假 0", () => {
    renderIndex();
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children.length).toBe(3);
    // 無 hover → 最新分鐘(09:02)
    expect(readout.children[0]!.textContent).toBe("09:02");
  });

  it("不 render 成交量副圖與說明列(指數無量、無內外盤)", () => {
    const { container } = renderIndex();
    expect(container.querySelector('svg[aria-label="成交量"]')).toBeNull();
    expect(container.querySelector("figcaption")).toBeNull();
    expect(container.querySelectorAll("svg").length).toBe(1);
  });

  it("toggle 列只三顆(均價 / CDP / MA),均價鈕帶指數口徑 title", () => {
    const { container } = renderIndex();
    const btns = [...container.querySelectorAll("button")];
    expect(btns.map((b) => b.textContent)).toEqual(["均價", "CDP", "MA"]);
    expect(btns[0]!.getAttribute("title")).toBe("分鐘收盤均價(指數無成交量)");
    for (const b of btns) expect(b.hasAttribute("disabled")).toBe(false);
  });

  it("域外 CDP → 右緣掛牌(名稱 + 點位 + 方向箭頭);域內的畫線不掛牌", () => {
    const { container } = renderIndex();
    expect(screen.getByTestId("overlay-peg-ah").textContent).toBe("AH 24100↑");
    expect(screen.getByTestId("overlay-peg-nh").textContent).toBe("NH 23500↑");
    expect(screen.getByTestId("overlay-peg-nl").textContent).toBe("NL 22700↓");
    expect(screen.getByTestId("overlay-peg-al").textContent).toBe("AL 22500↓");
    // cdp 本尊(23000)與 ma5 在域內 → 走 overlayLines 畫線,不得同時掛牌
    expect(container.querySelector('[data-testid="overlay-peg-cdp"]')).toBeNull();
    expect(container.querySelector('[data-testid="overlay-peg-ma5"]')).toBeNull();
    const ah = screen.getByTestId("overlay-peg-ah");
    expect(ah.getAttribute("x")).toBe(String(VB.width - R_AXIS_W - 2));
    expect(ah.getAttribute("text-anchor")).toBe("end");
  });

  it("CDP 關 → 掛牌一顆不剩(掛牌與線體共用同一組閘)", () => {
    const { container } = renderIndex({ toggles: { ...TOGGLES, cdp: false } });
    expect(container.querySelectorAll('[data-testid^="overlay-peg-"]').length).toBe(0);
  });

  it("MA 價位標讓開掛牌:兩者 y 差 ≥ EDGE_LABEL_H", () => {
    const { container } = renderIndex({ overlay: OVERLAY_MA_TOP });
    const ma = container.querySelector('[data-testid="edge-price-ma5"]')!;
    expect(ma).toBeTruthy();
    const maY = Number(ma.getAttribute("y"));
    const pegYs = [...container.querySelectorAll('[data-testid^="overlay-peg-"]')].map((p) =>
      Number(p.getAttribute("y")),
    );
    expect(pegYs.length).toBe(4);
    for (const y of pegYs) expect(Math.abs(maY - y)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
  });

  it("MA 價位文字走 fmt 不 snap tick(指數沒有可下單檔位)", () => {
    const { container } = renderIndex();
    const ma = container.querySelector('[data-testid="edge-price-ma5"]')!;
    expect(ma.textContent).toBe("23018");
    // 自檢:fixture 真的區分得出兩種口徑(否則本案恆綠)
    expect(fmtTickPrice(23_018_440)).not.toBe("23018");
  });

  it("overlaySupported=false(櫃買無日 K)→ CDP / MA 反灰 + overlayOffTitle", () => {
    const { container } = renderIndex({
      overlaySupported: false,
      overlayOffTitle: "櫃買無日 K 資料源",
    });
    const btns = [...container.querySelectorAll("button")];
    expect(btns[1]!.hasAttribute("disabled")).toBe(true);
    expect(btns[2]!.hasAttribute("disabled")).toBe(true);
    expect(btns[1]!.getAttribute("title")).toBe("櫃買無日 K 資料源");
    expect(btns[2]!.getAttribute("title")).toBe("櫃買無日 K 資料源");
    // 反灰時線與掛牌都不畫(閘 = toggle && available)
    expect(container.querySelectorAll('[data-testid^="overlay-peg-"]').length).toBe(0);
  });

  it("overlayError=true → CDP / MA 反灰,title 預設「無日線資料」", () => {
    const { container } = renderIndex({ overlay: null, overlayError: true });
    const btns = [...container.querySelectorAll("button")];
    expect(btns[1]!.hasAttribute("disabled")).toBe(true);
    expect(btns[2]!.hasAttribute("disabled")).toBe(true);
    expect(btns[1]!.getAttribute("title")).toBe("無日線資料");
  });

  it("空態:「等待指數資料…」且**不帶框**(MarketPane 的 figure 已是外框)", () => {
    const empty = indexSeriesToAccum({ ...SERIES, minutes: {} }, "IX:TWSE", "加權指數");
    const { container } = renderIndex({ accum: empty });
    expect(screen.getByText("等待指數資料…")).toBeTruthy();
    const box = container.firstElementChild!;
    expect(box.className).toContain("items-center");
    expect(box.className).not.toContain("border");
    expect(box.className).not.toContain("rounded-md");
  });

  it("svg aria-label 由 caller 指派(兩個 pane 可各自指認)", () => {
    const { container } = renderIndex();
    expect(container.querySelector('svg[aria-label="加權指數分時走勢"]')).toBeTruthy();
    expect(container.querySelector('svg[aria-label="分時走勢圖"]')).toBeNull();
  });

  it("外層是 div 不是 figure(pane 的 figure 已是外框,不做框中框)", () => {
    const { container } = renderIndex();
    expect(container.querySelector("figure")).toBeNull();
    expect(container.firstElementChild!.tagName).toBe("DIV");
  });

  it("hover 價位標不 snap tick,但收成整數點(量尺連續;36px 價標盒裝不下 8 字)", () => {
    const { container } = renderIndex();
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 300, clientY: 100 });
    const g = buildIntradayGeometry(
      { minutes: IDX.minutes, meta: IDX.meta, high: IDX.high, low: IDX.low },
      VB,
      SPOT_WINDOW,
    );
    const raw = g.priceAtY(100);
    expect(screen.getByTestId("price-tag-text").textContent).toBe(fmtIndexPts(raw));
    // 加權量級(五位數)收整數點:不帶小數(R4 real-env:「24285.42」溢出價標盒)
    expect(screen.getByTestId("price-tag-text").textContent).not.toMatch(/\./);
    // 自檢:這個 y 上 tick-snap 與整數點真的不同(否則本案恆綠)
    expect(fmtIndexPts(raw)).not.toBe(fmt(snapDown(raw)));
  });

  it("左緣 y 刻度 / CDP 價位標 / 掛牌一律整數點(軸帶 36/40px 裝不下「24283.54」;review C-2)", () => {
    renderIndex();
    const ticks = screen.getAllByTestId("y-tick-price").map((t) => t.textContent ?? "");
    expect(ticks.length).toBeGreaterThan(0);
    for (const t of ticks) expect(t).not.toMatch(/\./);
    // CDP 23_001_440 → 「23001*」(不 snap 成 23000、不印 .44)
    expect(screen.getByText("23001*")).toBeTruthy();
    for (const p of screen.getAllByTestId(/^overlay-peg-/)) expect(p.textContent).not.toMatch(/\./);
  });

  it("不打 /api/stock/overlay(疊線由 caller 注入;IX:TWSE 不是股號)", async () => {
    renderIndex();
    await waitFor(() => expect(screen.getByTestId("chart-readout")).toBeTruthy());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** W-1 lock:mode 預設(不傳)= stock,個股頁逐字不變。
 *
 *  這一組是 `const index = mode === "index"` 的 mutation 閘 —— 閘一反,下面五條同時紅。 */
describe("W-1:mode 預設 = stock,個股路徑零變化", () => {
  const STOCK = fromSnapshot({
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
    high: 2_395_000,
    low: 2_370_000,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  it("readout 六欄 / 副圖仍在 / 說明列仍在 / aria-label 仍是「分時走勢圖」/ 掛牌零", async () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    expect(screen.getByTestId("chart-readout").children.length).toBe(6);
    expect(container.querySelector('svg[aria-label="成交量"]')).toBeTruthy();
    expect(container.querySelector('svg[aria-label="分時走勢圖"]')).toBeTruthy();
    expect(container.querySelector("figcaption")).toBeTruthy();
    expect(container.querySelector("figure")).toBeTruthy();
    expect(container.querySelectorAll('[data-testid^="overlay-peg-"]').length).toBe(0);
    // toggle 列五顆(均價 / CDP / MA / 量分佈 / 成交點)
    expect([...container.querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "均價", "CDP", "MA", "量分佈", "成交點",
    ]);
  });

  it("仍打 /api/stock/overlay/<code>(疊線走內建查詢)", async () => {
    wrap(<StockIntradayChart accum={STOCK} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/stock/overlay/2330");
  });

  it("hover 價位標仍 snap 到合法 tick(可下單價位)", () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 300, clientY: 100 });
    const g = buildIntradayGeometry(
      { minutes: STOCK.minutes, meta: STOCK.meta, high: STOCK.high, low: STOCK.low },
      VB,
      SPOT_WINDOW,
    );
    const raw = g.priceAtY(100);
    expect(screen.getByTestId("price-tag-text").textContent).toBe(fmt(snapDown(raw)));
    expect(fmt(snapDown(raw))).not.toBe(fmt(raw));
  });
});

// 🔴 N006 / N045(mod/chart-label-batch):VWAP 就地標籤的口徑與寬度。
//
// index 態全圖走 `fmtIndexPts`(左緣刻度 / CDP `價位*` / MA 價位標 / 掛牌 / hover 價標),
// 只有 VWAP 這一顆硬編 `fmt` → 加權印「24283.54」而同一張圖的刻度印「24284」;
// 而且 8 字實寬 ≈45.6px > 硬編的 `VWAP_LABEL_W`(40),盤末 clamp 內縮不足,字尾溢進
// 右緣疊線標籤帶(N006)。兩者是同一顆標籤的一體兩面,一起修。
describe("IntradayChartCore mode=\"index\" 的 VWAP 標籤口徑(N006/N045)", () => {
  /** 加權型 fixture:分鐘收盤平均 = (24_283_000 + 24_284_080) / 2 = 24_283_540
   *  → `fmt` 印「24283.54」(8 字)、`fmtIndexPts` 收整數點印「24284」。
   *  末點刻意放 13:30(繪圖區右界)才量得到寬度低估造成的溢出。 */
  const HEAVY: IndexSeries = {
    p: 24_284_080,
    ref: 24_200_000,
    high: 24_284_080,
    low: 24_283_000,
    stale: false,
    minutes: { "0900": 24_283_000, "1330": 24_284_080 },
  };
  const HEAVY_ACCUM = indexSeriesToAccum(HEAVY, "IX:TWSE", "加權指數");

  it("VWAP 文字走 index 口徑(fmtIndexPts),與左緣刻度同一把尺", () => {
    const { container } = renderIndex({ accum: HEAVY_ACCUM });
    // 前置(敏感度所繫):兩個口徑對這個值真的不同,否則本案恆綠
    expect(fmt(24_283_540)).toBe("24283.54");
    expect(fmtIndexPts(24_283_540)).toBe("24284");
    expect(HEAVY_ACCUM.vwap).toBe(24_283_540);
    expect(container.querySelector('[data-testid="edge-price-vwap"]')!.textContent).toBe("24284");
  });

  it("末點貼右界 → 標籤**實寬**整塊不出繪圖區(硬編 40 低估 8 字的 45.6px)", () => {
    const { container } = renderIndex({ accum: HEAVY_ACCUM });
    const label = container.querySelector('[data-testid="edge-price-vwap"]')!;
    const x = Number(label.getAttribute("x"));
    const g = buildIntradayGeometry(
      { minutes: HEAVY_ACCUM.minutes, meta: HEAVY_ACCUM.meta, high: HEAVY_ACCUM.high, low: HEAVY_ACCUM.low },
      VB,
      SPOT_WINDOW,
    );
    // 前置:末點真的貼在繪圖區右界上(否則 clamp 不啟動,本案恆綠)
    expect(g.vwapLine.at(-1)!.x).toBeCloseTo(800 - R_AXIS_W, 6);
    expect(x + labelWidth(label.textContent!)).toBeLessThanOrEqual(800 - R_AXIS_W);
  });
});
