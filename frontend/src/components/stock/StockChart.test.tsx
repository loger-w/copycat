/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { StockAccum } from "@/lib/stock-accum";
import { wrap } from "@/test-utils";

const ACCUM = {
  code: "2330",
  seq: 1,
  last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
  vwap: 2_380_000,
  minutes: new Map([[540, { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 }]]),
  ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
  book: { bids: [], asks: [] },
  meta: {
    name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000,
    y_vol: 100,
  },
  noData: false,
} as unknown as StockAccum;

const BARS = [
  { t: "2026-07-27", o: 100_000, h: 110_000, l: 90_000, c: 105_000, v: 10 },
  { t: "2026-07-28", o: 105_000, h: 120_000, l: 100_000, c: 102_000, v: 20 },
];

let barsUrls: string[];

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/stock/bars")) {
        barsUrls.push(u);
        return new Response(JSON.stringify({ bars: BARS }));
      }
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function chart() {
  return wrap(<StockChart accum={ACCUM} code="2330" />);
}

describe("StockChart 模式切換(SC-7)", () => {
  // 🔴 SC-6.1:分 K 由 1/5 兩顆擴為 1–10 連續十顆,共 12 顆模式鈕
  it("模式鈕共 12 顆:江波圖 + 1分K…10分K + 日K", () => {
    chart();
    const labels = ["江波圖", ...Array.from({ length: 10 }, (_, i) => `${i + 1}分K`), "日K"];
    for (const l of labels) expect(screen.getByRole("button", { name: l })).toBeTruthy();
    // 只數模式鈕 —— 江波圖自己的 均價/CDP/MA toggle 也帶 aria-pressed,不能一起數
    const modeButtons = screen
      .getAllByRole("button")
      .filter((b) => /^(江波圖|日K|\d+分K)$/.test(b.textContent ?? ""));
    expect(modeButtons.length).toBe(12);
  });

  it("3分K / 7分K 等新模式可切換且寫入 localStorage", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "7分K" }));
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("m7");
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.getByRole("button", { name: "7分K" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("預設江波圖:選中者 aria-pressed=true 且外框 border-accent", () => {
    chart();
    const btn = screen.getByRole("button", { name: "江波圖" });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(btn.className).toContain("border-accent");
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.queryByLabelText("K 線圖")).toBeNull();
  });

  it("切日K → 顯示 K 線圖,江波圖卸載", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByLabelText("分時走勢圖")).toBeNull();
  });

  it("切回江波圖 → 回到既有分時走勢圖(含 VWAP 切換與內外盤副圖)", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "江波圖" }));
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.getByLabelText("成交量")).toBeTruthy();
    expect(screen.getByRole("button", { name: "均價" })).toBeTruthy();
  });

  it("模式寫入 localStorage copycat-chart-mode 並在重載後復原", async () => {
    const { unmount } = chart();
    fireEvent.click(screen.getByRole("button", { name: "5分K" }));
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("m5");
    unmount();
    cleanup();
    chart();
    expect(screen.getByRole("button", { name: "5分K" }).getAttribute("aria-pressed")).toBe("true");
  });

  // 🔴 SC-6.2:「往前」鈕與「近 N 日」文字移除,分 K 一次就載滿 30 日(縮放/平移取代分頁載入)
  it("分K 直接載 30 日,無「往前」鈕與「近 N 日」文字", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "1分K" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("days=30"))).toBe(true));
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull();
    expect(screen.queryByText(/近 \d+ 日/)).toBeNull();
    // 只打一次,不再有 5→10→…→30 的階梯式重取
    expect(barsUrls.filter((u) => u.includes("tf=1")).length).toBe(1);
  });

  it("日K 走 tf=D 且 query 不帶 days(D-15)", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("tf=D"))).toBe(true));
    expect(barsUrls.find((u) => u.includes("tf=D"))).not.toContain("days=");
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull();
  });

  it("2–10 分K 共用同一份 tf=1 資料(前端聚合,切模式不重打)", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "1分K" }));
    await waitFor(() => expect(barsUrls.length).toBeGreaterThan(0));
    const before = barsUrls.length;
    fireEvent.click(screen.getByRole("button", { name: "3分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(barsUrls.length).toBe(before);
  });

  // 🔴 SC-3:失敗態與「真的沒資料」原本共用同一句「無 K 線資料」,害 2026-07-29 那次
  // 舊 build 佔 port(endpoint 404)被誤讀成「這檔沒 K 線」。失敗態要看得出是失敗。
  // 錯誤碼取值鏈:body 的 detail.error 優先 → 否則 HTTP_<status>(useStockBars.ts:35-44),
  // 故本 case 的碼是 NOT_READY 而非 HTTP_503。
  it("取數失敗顯示「K 線載入失敗」+ 錯誤碼,不崩", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 })
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("K 線載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText("NOT_READY")).toBeTruthy();
    expect(screen.queryByText("無 K 線資料")).toBeNull();
  });

  // 🟢 self-review C2:錯誤碼取值鏈的**第二條路**(body 無 detail.error → HTTP_<status>)。
  // 這正是 2026-07-29 的真實事故路徑:舊 build 佔 port,FastAPI 對未知 route 回
  // {"detail":"Not Found"} —— detail 是字串不是物件,`.error` 為 undefined → 落回 HTTP_404。
  // 只測 detail.error 那條的話,這條 fallback 壞掉不會有任何測試變紅。
  it("錯誤碼 fallback:body 無 detail.error → 顯示 HTTP_<status>", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("K 線載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText("HTTP_404")).toBeTruthy();
  });

  // 🔴 round3 SC-6:高度分配反轉 —— 圖表由「shrink-0 的固定比例高」改成「吃剩餘空間」。
  // 舊 shrink-0 防的是「被壓縮致 svg 溢出」,新機制從源頭消掉那個情境:svg 高度本身
  // 就跟著可用空間走,而不是由寬度算出來的固定值。
  it("圖表容器吃剩餘高度,且量測 wrapper 為恆存(SC-6)", () => {
    const { container } = chart();
    const root = container.firstChild as HTMLElement;
    expect(root.className).toContain("flex-1");
    expect(root.className).toContain("min-h-0");
    expect(root.className).not.toContain("shrink-0");
    // 恆存 wrapper = 模式列的下一個兄弟;三態都掛在它底下(useContainerSize 契約)
    const wrapper = root.children[1] as HTMLElement;
    expect(wrapper.className).toContain("flex-1");
    expect(wrapper.className).toContain("min-h-0");
  });

  // 🟢 SC-3 反向:真的取到空陣列 → 仍是「無 K 線資料」,不可誤報成失敗(W-13)
  it("取到空 bars 仍顯示「無 K 線資料」,不誤報失敗", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ bars: [] }))
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
  });
});
