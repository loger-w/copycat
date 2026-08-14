/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketChart } from "@/components/index/MarketChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import type { MarketKey } from "@/lib/timeframe";

/** 域:yTop = 23_100_000×1.003 = 23_169_300、yBottom = 22_990_000×0.997 = 22_920_970 */
function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 23_100_000,
    ref: 23_000_000,
    high: 23_100_000,
    low: 22_990_000,
    stale: false,
    minutes: { "0901": 23_000_000, "0930": 23_100_000 },
    ...over,
  };
}

/** 五條 CDP + 兩條 MA 全在域內 */
const OVERLAY_IN = {
  cdp: { cdp: 23_050_000, ah: 23_150_000, nh: 23_100_000, nl: 22_995_000, al: 22_950_000 },
  ma5: 23_020_000,
  ma20: 22_930_000,
  date: "2026-08-13",
};

/** ah / cdp 在域上方、al / ma20 在域下方;nh / nl / ma5 仍在域內 */
const OVERLAY_OUT = {
  cdp: { cdp: 24_000_000, ah: 24_100_000, nh: 23_100_000, nl: 22_995_000, al: 22_000_000 },
  ma5: 23_020_000,
  ma20: 22_000_000,
  date: "2026-08-13",
};

const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: true };

function toggles(over: Partial<ChartToggles> = {}): ChartToggles {
  return { ...TOGGLES, ...over };
}

let urls: string[] = [];

function stub(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return new Response(JSON.stringify(body), { status });
    }),
  );
}

function renderChart(opts: {
  marketKey?: MarketKey;
  name?: string;
  s?: IndexSeries | null;
  t?: ChartToggles;
}) {
  const client = new QueryClient({
    // retryDelay 0:hook 自帶 retry:1,error 終態才不用等 exponential backoff
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MarketChart
        marketKey={opts.marketKey ?? "TWSE"}
        mode="intraday"
        name={opts.name ?? "加權指數"}
        series={opts.s === undefined ? series() : opts.s}
        toggles={opts.t ?? toggles()}
        onToggle={() => undefined}
      />
    </QueryClientProvider>,
  );
}

function dashedOverlayLines(root: HTMLElement): NodeListOf<Element> {
  return root.querySelectorAll('line[stroke-dasharray="3 2"]');
}

beforeEach(() => {
  urls = [];
  stub(OVERLAY_IN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MarketChart 分時疊線(SC-3)", () => {
  it("加權 + CDP 開 → 域內疊線畫水平虛線,右緣印帶 * 的價位", async () => {
    const { container } = renderChart({ t: toggles({ cdp: true, ma: false }) });
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(5));
    expect(urls).toContain("/api/index/overlay");
    const starred = [...container.querySelectorAll("text")]
      .map((t) => t.textContent ?? "")
      .filter((s) => s.endsWith("*"));
    expect(starred.sort()).toEqual(["22950*", "22995*", "23050*", "23100*", "23150*"]);
    // 線體橫貫全寬(指數圖無 R_AXIS 保留帶)
    expect(dashedOverlayLines(container)[0]!.getAttribute("x1")).toBe("0");
    expect(dashedOverlayLines(container)[0]!.getAttribute("x2")).toBe("640");
  });

  it("域外 → 不畫線體,右緣掛牌帶名稱與方向", async () => {
    stub(OVERLAY_OUT);
    const { container } = renderChart({ t: toggles({ cdp: true, ma: true }) });
    // 域內只剩 nh / nl / ma5
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(3));
    expect(screen.getByText("AH 24100↑")).toBeTruthy();
    expect(screen.getByText("CDP 24000↑")).toBeTruthy();
    expect(screen.getByText("AL 22000↓")).toBeTruthy();
    expect(screen.getByText("MA20 22000↓")).toBeTruthy();
    // 域外的值不得出現線體價位標(那是「畫了線」的語彙)
    expect(screen.queryByText("24000*")).toBeNull();
  });

  it("MA 開 → 右緣印 MA5 / MA20 名稱加價位", async () => {
    const { container } = renderChart({ t: toggles({ cdp: false, ma: true }) });
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(2));
    expect(screen.getByText("MA5 23020")).toBeTruthy();
    expect(screen.getByText("MA20 22930")).toBeTruthy();
  });
});

describe("MarketChart toggle 列(SC-4 / 決策 2)", () => {
  it("櫃買 → CDP / MA 反灰帶 title,均價可按", () => {
    renderChart({
      marketKey: "OTC",
      name: "櫃買指數",
      s: series({ minutes: { "1017": 359_800 }, ref: 378_090, high: 373_420, low: 358_430 }),
      t: toggles({ cdp: true, ma: true }),
    });
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("櫃買無日 K 資料源");
      // 決策 2:aria-pressed 與 available 連動,不並存 aria-disabled 字串
      expect(btn.getAttribute("aria-pressed")).toBe("false");
      expect(btn.getAttribute("aria-disabled")).toBeNull();
    }
    const vwap = screen.getByRole("button", { name: "均價" });
    expect(vwap.hasAttribute("disabled")).toBe(false);
    expect(vwap.getAttribute("title")).toBe("分鐘收盤均價(指數無成交量)");
    // 櫃買不打 overlay 端點
    expect(urls.some((u) => u.includes("/api/index/overlay"))).toBe(false);
  });

  it("加權但端點 503 → CDP / MA 反灰帶「無日線資料」", async () => {
    stub({ detail: { error: "NOT_READY" } }, 503);
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.getAttribute("title")).toBe("無日線資料");
    }
  });

  it("200 但三欄全 null(TC4 沒開)→ CDP / MA 反灰帶「無日線資料」", async () => {
    stub({ cdp: null, ma5: null, ma20: null, date: null });
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("無日線資料");
    }
  });

  it("cdp null 但 ma5 有值 → CDP 反灰、MA 仍可按(edge case 3 同個股語意)", async () => {
    stub({ cdp: null, ma5: 23_020_000, ma20: null, date: "2026-08-13" });
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    expect(screen.getByRole("button", { name: "CDP" }).getAttribute("title")).toBe("無日線資料");
    const ma = screen.getByRole("button", { name: "MA" });
    expect(ma.hasAttribute("disabled")).toBe(false);
    expect(ma.getAttribute("title")).toBeNull();
  });
});

describe("MarketChart error 態不鎖死 toggle 閘(review G-2)", () => {
  /** 同一個 QueryClient 下換 toggles 重繪 —— `renderChart` 每次新建 client,
   *  「error 殘留 + 閘關掉」這條路只有沿用同一份 query state 才走得到 */
  function rerenderable(t: ChartToggles) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, retryDelay: 0 } },
    });
    const el = (cur: ChartToggles) => (
      <QueryClientProvider client={client}>
        <MarketChart
          marketKey="TWSE"
          mode="intraday"
          name="加權指數"
          series={series()}
          toggles={cur}
          onToggle={onToggle}
        />
      </QueryClientProvider>
    );
    const onToggle = vi.fn();
    const view = render(el(t));
    return { onToggle, rerender: (next: ChartToggles) => view.rerender(el(next)) };
  }

  it("503 後把 toggle 全關 → CDP / MA 鈕恢復可按,點得回請求路徑", async () => {
    stub({ detail: { error: "NOT_READY" } }, 503);
    const { onToggle, rerender } = rerenderable(toggles({ cdp: true, ma: true }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    const overlayCalls = () => urls.filter((u) => u === "/api/index/overlay").length;
    const before = overlayCalls();

    // toggle 全關 → query enabled=false。TanStack 不會因此清掉 error status,
    // refetchInterval 也停 → 沒有閘的話這兩顆鈕從此永久 disabled(重整才解)
    rerender(toggles({ cdp: false, ma: false }));
    for (const label of ["CDP", "MA"]) {
      expect(screen.getByRole("button", { name: label }).hasAttribute("disabled")).toBe(false);
    }

    // 點得下去 = 使用者自己就能把疊線開回來
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    expect(onToggle).toHaveBeenCalledWith("cdp", true);

    // 開回來 → 閘重開,請求路徑真的再走一次(不是只有鈕看起來能按)
    rerender(toggles({ cdp: true, ma: false }));
    await waitFor(() => expect(overlayCalls()).toBeGreaterThan(before));
  });
});

describe("MarketChart 昨收標籤(SC-6)", () => {
  it("有 ref → 右緣印「昨收 <值>」", async () => {
    renderChart({ t: toggles({ cdp: false, ma: false }) });
    await waitFor(() => expect(screen.getByText("昨收 23000")).toBeTruthy());
  });

  it("ref null → 不畫昨收標籤(fallback 虛線照畫)", async () => {
    const { container } = renderChart({
      s: series({ ref: null }),
      t: toggles({ cdp: false, ma: false }),
    });
    await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    expect(screen.queryByText(/昨收/)).toBeNull();
    expect(container.querySelector('line[stroke-dasharray="2 3"]')).toBeTruthy();
  });
});

describe("MarketChart y 域不受疊線影響(SC-7)", () => {
  async function snapshot(t: ChartToggles, expectLines: number) {
    const { container, unmount } = renderChart({ t });
    if (expectLines > 0) {
      await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(expectLines));
    } else {
      await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    }
    const ticks = [...container.querySelectorAll('[data-testid="index-ytick"]')].map(
      (e) => `${e.getAttribute("y")}|${e.textContent}`,
    );
    const refY = container
      .querySelector('line[stroke-dasharray="2 3"]')!
      .getAttribute("y1");
    unmount();
    return { ticks, refY };
  }

  it("同一 series 下 CDP/MA 開 vs 關,yTicks 與昨收線位置逐字相同", async () => {
    const off = await snapshot(toggles({ cdp: false, ma: false }), 0);
    const on = await snapshot(toggles({ cdp: true, ma: true }), 7);
    expect(off.ticks).toHaveLength(3);
    expect(on.ticks).toEqual(off.ticks);
    expect(on.refY).toBe(off.refY);
  });
});

describe("MarketChart a11y 錨點(W-12)", () => {
  it("role=img + aria-label 掛在 svg 節點,toggle 鈕不在其內", () => {
    renderChart({ t: toggles({ cdp: false, ma: false }) });
    const node = screen.getByRole("img", { name: "加權指數分時走勢" });
    expect(node.tagName).toBe("svg");
    expect(node.querySelectorAll("button")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "均價" })).toBeTruthy();
  });
});

describe("MarketChart 均價線(SC-1)", () => {
  it("均價 toggle 開 → 畫 stroke-ink 1.2 寬的均價線;關 → 不畫", () => {
    const { container, unmount } = renderChart({
      t: toggles({ vwap: true, cdp: false, ma: false }),
    });
    expect(container.querySelectorAll("polyline.stroke-ink")).toHaveLength(1);
    expect(container.querySelector("polyline.stroke-ink")!.getAttribute("stroke-width")).toBe(
      "1.2",
    );
    unmount();
    const off = renderChart({ t: toggles({ vwap: false, cdp: false, ma: false }) });
    expect(off.container.querySelectorAll("polyline.stroke-ink")).toHaveLength(0);
  });
});
