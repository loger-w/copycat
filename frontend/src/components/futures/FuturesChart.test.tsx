/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesChart, INTRADAY_VB_W } from "@/components/futures/FuturesChart";
import { ALLDAY_LEN, alldayIndexOf } from "@/lib/allday";
import { FUT_CHART_MODE_KEY } from "@/lib/constants";
import { wrap } from "@/test-utils";
import type { Bar } from "@/lib/candle";
import type { CapitalPosition, FuturesProductState, OiLevelsResponse } from "@/types";

const META = {
  source: "tc4_1k",
  coverage_from: "2026-08-05",
  coverage_to: "2026-08-05",
  partial_last: true,
  volume: true,
  refusal: null,
  synth_since: null,
};

/** 窄幅 bar(分時折線只讀 `c`;K 線模式的 y 域就是這一帶)。 */
function bar(t: string, c: number): Bar {
  return { t, o: c, h: c + 1_000, l: c - 1_000, c, v: 10, uv: 6, dv: 4 };
}

const STATE: FuturesProductState = {
  product: "TXF",
  name: "臺股期貨",
  p: 23_000_000,
  q: 1,
  cum_vol: 100,
  t: "09:30:00",
  date: "20260805",
  bids: [[22_999_000, 5]],
  asks: [[23_001_000, 5]],
  ref: 22_950_000,
  upper: 25_000_000,
  lower: 20_000_000,
  resolved_contract: "202608",
};

function futPos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "fut",
    stock_no: "TXFH6", // futExchangeContract("TXF", "202608")
    qty: 2,
    name: "臺股期貨",
    avg_price: 23_000,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    code: null,
    ...overrides,
  };
}

const EMPTY_OI: OiLevelsResponse = { date: null, contract: null, strikes: [] };

let barsUrls: string[] = [];
let barsBody: unknown;
let oiBody: unknown;
let oiStatus: number;
let positionsBody: unknown;

/** 每個 x 座標在 `points` 字串裡的形(pts 一律 toFixed(1))。 */
function xOf(index: number): string {
  return ((index / ALLDAY_LEN) * INTRADAY_VB_W).toFixed(1);
}

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  barsBody = { bars: [], meta: META };
  oiBody = EMPTY_OI;
  oiStatus = 200;
  positionsBody = { positions: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/market/bars")) {
        barsUrls.push(u);
        return new Response(JSON.stringify(barsBody));
      }
      if (u.includes("/api/futures/oi-levels")) {
        return new Response(JSON.stringify(oiBody), { status: oiStatus });
      }
      if (u.includes("/api/capital/positions")) {
        return new Response(JSON.stringify(positionsBody));
      }
      throw new Error(`unexpected fetch: ${u}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("FuturesChart 模式列(SC-2)", () => {
  it("預設分時;切「5分」寫 localStorage 且 aria-pressed 跟隨", async () => {
    barsBody = { bars: [bar("2026-08-05 09:30", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    expect(screen.getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "5分" }));
    expect(window.localStorage.getItem(FUT_CHART_MODE_KEY)).toBe("m5");
    expect(screen.getByRole("button", { name: "5分" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe("false");
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
  });

  it("localStorage 有合法值 → 還原該模式(日K 走 tf=D)", async () => {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "day");
    barsBody = { bars: [bar("2026-08-04", 22_900_000), bar("2026-08-05", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    expect(screen.getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(barsUrls).toEqual(["/api/market/bars/TXF?tf=D"]));
  });
});

describe("FuturesChart 分時圖(SC-1)", () => {
  it("13:45 與 15:01 在近全軸上相鄰 —— 死區(13:46–15:00)不佔 x", async () => {
    barsBody = {
      bars: [bar("2026-08-05 13:45", 23_000_000), bar("2026-08-05 15:01", 23_020_000)],
      meta: META,
    };
    wrap(<FuturesChart product="TXF" state={null} resolvedYm={null} />);
    const line = await screen.findByTestId("allday-line");
    const xs = (line.getAttribute("points") ?? "").split(" ").map((p) => p.split(",")[0]);
    expect(xs).toEqual([xOf(alldayIndexOf("1345")!), xOf(alldayIndexOf("1501")!)]);
    // 「相鄰」的定義寫死在斷言裡:兩個索引差 1 = 折線上只隔一個 slot
    expect(alldayIndexOf("1501")! - alldayIndexOf("1345")!).toBe(1);
  });

  it("前一交易日的 bars 被 slice 掉(錨定日以最後一根反推)", async () => {
    barsBody = {
      bars: [
        bar("2026-08-04 09:00", 22_800_000), // 前一交易日日盤 → 不該入圖
        bar("2026-08-05 09:00", 22_960_000),
        bar("2026-08-05 09:30", 23_000_000),
      ],
      meta: META,
    };
    wrap(<FuturesChart product="TXF" state={null} resolvedYm={null} />);
    const line = await screen.findByTestId("allday-line");
    const xs = (line.getAttribute("points") ?? "").split(" ");
    expect(xs.length).toBe(2);
  });

  it("meta.source=unavailable → 進行式空態文案(不下「沒有資料」的結論)", async () => {
    barsBody = { bars: [], meta: { ...META, source: "unavailable" } };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("暫無資料(TC4 未回應)")).toBeTruthy());
    expect(screen.queryByTestId("allday-line")).toBeNull();
  });
});

describe("FuturesChart 背景輪詢 gate(LF-2)", () => {
  it("active=false → 不輪詢(期貨 tab hidden 時不打 TC4)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // 夜盤:active=true 時會輪詢
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: [bar("2026-08-05 22:00", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" active={false} />);
    await vi.advanceTimersByTimeAsync(0);
    const before = barsUrls.length;
    expect(before).toBe(1);
    await vi.advanceTimersByTimeAsync(180_000);
    expect(barsUrls.length).toBe(before);
  });

  it("active=true → 照輪詢(prop 真的接到 hook 上,不是擺著好看)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: [bar("2026-08-05 22:00", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" active />);
    await vi.advanceTimersByTimeAsync(0);
    const before = barsUrls.length;
    await vi.advanceTimersByTimeAsync(65_000);
    expect(barsUrls.length).toBeGreaterThan(before);
  });
});

describe("FuturesChart live 現價點(§3.2 錨定日 gate)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("時鐘落後資料:末根 bar = D 05:00(軸尾)、時鐘 D 08:45:30 → 不畫 live 點", async () => {
    barsBody = {
      bars: [bar("2026-08-05 04:59", 22_900_000), bar("2026-08-05 05:00", 22_910_000)],
      meta: META,
    };
    // 05:00 那根屬**前一交易日**(2026-08-04)的夜盤後半;08:46 的 live 點屬 08-05。
    // 此案 tail.index(1139)> live.index(0),兩道 gate 同時成立 → 只證「有擋」。
    vi.setSystemTime(new Date(2026, 7, 5, 8, 45, 30));
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line");
    expect(screen.queryByTestId("allday-live")).toBeNull();
  });

  it("錨定日 gate 獨立於時鐘落後守衛:末根 = 前一交易日 08:46、時鐘 = 次日 08:47 → 不畫", async () => {
    // 唯一一根 bar 是**前一交易日**的首根(軸索引 0);live 落 08:48(軸索引 2)。
    // tail.index(0) > live.index(2) 不成立 → 時鐘落後守衛整條不參與,
    // 擋下 live 點的只剩錨定日不同這一條(短路它 → 假 live 點被畫在今日圖上)。
    barsBody = { bars: [bar("2026-08-04 08:46", 22_900_000)], meta: META };
    vi.setSystemTime(new Date(2026, 7, 5, 8, 47, 0));
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line");
    // 前置條件寫死在斷言裡:兩個索引的大小關係就是「守衛沒被觸發」的證據
    expect(alldayIndexOf("0846")).toBe(0);
    expect(alldayIndexOf("0848")).toBe(2);
    expect(screen.queryByTestId("allday-live")).toBeNull();
  });

  it("同一錨定日:live 點以「當前分 + 1」為終點標記落在序列尾", async () => {
    barsBody = {
      bars: [bar("2026-08-05 09:00", 22_960_000), bar("2026-08-05 09:30", 23_000_000)],
      meta: META,
    };
    vi.setSystemTime(new Date(2026, 7, 5, 9, 35, 30));
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    const live = await screen.findByTestId("allday-live");
    expect(live.getAttribute("cx")).toBe(xOf(alldayIndexOf("0936")!));
  });

  it("live 分鐘落死區(14:30)→ 不畫 live 點", async () => {
    barsBody = {
      bars: [bar("2026-08-05 13:44", 22_960_000), bar("2026-08-05 13:45", 23_000_000)],
      meta: META,
    };
    vi.setSystemTime(new Date(2026, 7, 5, 14, 30, 0));
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line");
    expect(screen.queryByTestId("allday-live")).toBeNull();
  });
});

describe("FuturesChart overlays(SC-7 均價線 / SC-11 OI 線)", () => {
  /** OI / 均價線都要落在 y 視窗內才畫得出來 → 給一根夠寬的 bar。 */
  const WIDE = [
    { t: "2026-08-05 09:30", o: 23_000_000, h: 23_600_000, l: 22_400_000, c: 23_000_000, v: 10 },
    { t: "2026-08-05 09:31", o: 23_000_000, h: 23_600_000, l: 22_400_000, c: 23_010_000, v: 10 },
  ];

  beforeEach(() => {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: WIDE, meta: META };
  });

  it("本契約部位 → 均價線 label 帶方向與口數", async () => {
    positionsBody = { positions: [futPos({ qty: 2, avg_price: 23_000 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
  });

  it("空單 → label 用「空」", async () => {
    positionsBody = { positions: [futPos({ qty: -3, avg_price: 22_800 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("均 22800 空3口")).toBeTruthy());
  });

  it("非本契約 / 非期貨 / avg_price null → 不畫均價線", async () => {
    positionsBody = {
      positions: [
        futPos({ stock_no: "MXFH6" }), // 別的商品
        futPos({ stock_no: "TXFI6" }), // 別的月份(完整字串相等,不做前綴猜測)
        futPos({ market: "sec", stock_no: "TXFH6" }),
        futPos({ avg_price: null }),
      ],
    };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^均 /)).toBeNull();
  });

  it("resolvedYm null(合約未解析)→ 不畫均價線", async () => {
    positionsBody = { positions: [futPos()] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm={null} />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^均 /)).toBeNull();
  });

  it("OI 撐壓:現價帶內取 max(深度價外的垃圾履約價不入選)", async () => {
    oiBody = {
      date: "2026-08-04",
      contract: "202608",
      strikes: [
        { strike: 22_500, call_oi: 100, put_oi: 8_000 },
        { strike: 23_500, call_oi: 9_000, put_oi: 100 },
        { strike: 55_000, call_oi: 99_999, put_oi: 0 },
      ],
    } satisfies OiLevelsResponse;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("壓 23500")).toBeTruthy());
    expect(screen.getByText("撐 22500")).toBeTruthy();
    expect(screen.queryByText("壓 55000")).toBeNull();
  });

  it("oi-levels 500 → 線消失、圖照常(降級不拋 error boundary)", async () => {
    oiStatus = 500;
    oiBody = { detail: { error: "BOOM" } };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^壓 /)).toBeNull();
    expect(screen.queryByText(/^撐 /)).toBeNull();
  });
});

describe("FuturesChart 分時模式的 overlays(SC-7 / SC-11;與 K 線同一套語意)", () => {
  /** 分時的 y 域只由 close 與 ref 決定(高低價不參與)→ 用一低一高兩根撐開視窗,
   *  讓 22400–23600 這帶的 overlay 落得進來。localStorage 未設 = 預設分時模式。 */
  const SPAN = [bar("2026-08-05 09:30", 22_400_000), bar("2026-08-05 09:31", 23_600_000)];

  const OI_BODY: OiLevelsResponse = {
    date: "2026-08-04",
    contract: "202608",
    strikes: [
      { strike: 22_500, call_oi: 100, put_oi: 8_000 },
      { strike: 23_500, call_oi: 9_000, put_oi: 100 },
      { strike: 55_000, call_oi: 99_999, put_oi: 0 }, // 帶外垃圾履約價
    ],
  };

  beforeEach(() => {
    barsBody = { bars: SPAN, meta: META };
  });

  it("本契約部位 → 分時圖畫出均價 hline(label + 線元素)", async () => {
    positionsBody = { positions: [futPos({ qty: 2, avg_price: 23_000 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line"); // 確定走的是分時而非 CandleChart
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
    expect(screen.getAllByTestId("chart-hline").length).toBe(1);
  });

  it("OI 有值 → 分時圖畫出壓/撐 hline(帶外 55000 仍不入選)", async () => {
    oiBody = OI_BODY;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line");
    await waitFor(() => expect(screen.getByText("壓 23500")).toBeTruthy());
    expect(screen.getByText("撐 22500")).toBeTruthy();
    expect(screen.queryByText("壓 55000")).toBeNull();
    expect(screen.getAllByTestId("chart-hline").length).toBe(2);
  });

  it("priceMilli 遠超 y 域 → 只不畫那一條(clamp 到邊緣 = 把圖外價位講成圖緣價位)", async () => {
    // 同一次 render 內一條在窗內、兩條在窗外 → 「只畫窗內那條」才是斷言,
    // 全部不畫或全部照畫都會紅(y 域上緣 = 23600 × 1.003、下緣 = 22400 × 0.997)
    positionsBody = {
      positions: [futPos({ qty: 2, avg_price: 23_000 }), futPos({ qty: 1, avg_price: 30_000 })],
    };
    oiBody = {
      date: "2026-08-04",
      contract: "202608",
      // 帶內(±10% of 23000)但落在 y 域下緣之外
      strikes: [{ strike: 21_000, call_oi: 5_000, put_oi: 5_000 }],
    } satisfies OiLevelsResponse;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await screen.findByTestId("allday-line");
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
    expect(screen.queryByText("均 30000 多1口")).toBeNull();
    expect(screen.queryByText("壓 21000")).toBeNull();
    expect(screen.queryByText("撐 21000")).toBeNull();
    expect(screen.getAllByTestId("chart-hline").length).toBe(1);
  });
});
