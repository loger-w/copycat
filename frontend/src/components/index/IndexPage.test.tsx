/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: { "0901": 43_000_000, "0930": 42_039_920 },
    ...over,
  };
}

const OTC = series({
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  minutes: { "1017": 359_800 },
});
const TXF: TxfQuote = { p: 42_142_000, time: "10:16:10" };
const FUTURES = { TXF: { p: 42_142_000, ref: 42_000_000 } };

function bars(n = 3) {
  return Array.from({ length: n }, (_, i) => ({
    t: `2026-07-2${7 + i}`,
    o: 100,
    h: 110,
    l: 90,
    c: 105,
    v: 10,
  }));
}

let lastUrls: string[] = [];

function stubFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      lastUrls.push(String(url));
      return new Response(JSON.stringify(body));
    }),
  );
}

const DK_BODY = {
  key: "TWSE",
  tf: "D",
  bars: bars(),
  meta: {
    source: "tc4_dk",
    coverage_from: "2026-07-27",
    coverage_to: "2026-07-29",
    partial_last: false,
    volume: true,
    refusal: null,
    synth_since: null,
  },
};

beforeEach(() => {
  window.localStorage.clear();
  lastUrls = [];
  stubFetch(DK_BODY);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage(txf: TxfQuote | null = TXF) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IndexPage twse={series()} otc={OTC} txf={txf} futures={FUTURES} />
    </QueryClientProvider>,
  );
}

function btn(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

describe("IndexPage 標的列(SC-2)", () => {
  it("三顆標的鈕;預設選加權,現值/漲跌/高低昨收顯示於標題列", () => {
    renderPage();
    expect(btn("加權").getAttribute("aria-pressed")).toBe("true");
    expect(btn("櫃買")).toBeTruthy();
    expect(btn("台指期")).toBeTruthy();
    expect(screen.getByText("加權指數")).toBeTruthy();
    expect(screen.getByText("42039.92")).toBeTruthy();
    expect(screen.getByText(/-1594\.27/)).toBeTruthy();
    expect(screen.getByText(/高 43221\.93/)).toBeTruthy();
    expect(screen.getByText(/昨收 43634\.19/)).toBeTruthy();
  });

  it("Quote 漲跌整串:跌用負號(characterization)", () => {
    renderPage();
    expect(screen.getByText("-1594.27 (-3.65%)")).toBeTruthy();
  });

  it("Quote 漲跌整串:漲帶 + 前綴(characterization;台指期)", () => {
    renderPage();
    fireEvent.click(btn("台指期"));
    expect(screen.getByText("+142.00 (+0.34%)")).toBeTruthy();
  });

  it("點台指期才出現大台/小台/微台三選一;選微台後標題換料", () => {
    renderPage();
    expect(screen.queryByRole("button", { name: "小台" })).toBeNull();
    fireEvent.click(btn("台指期"));
    expect(btn("大台").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(btn("微台"));
    expect(screen.getByText("台指期(微台)")).toBeTruthy();
    expect(btn("微台").getAttribute("aria-pressed")).toBe("true");
  });

  it("期指商品用獨立 localStorage key,不碰期貨 tab 的 copycat-fut-product(W-13)", () => {
    renderPage();
    fireEvent.click(btn("台指期"));
    fireEvent.click(btn("小台"));
    expect(window.localStorage.getItem("copycat-market-key")).toBe("MXF");
    expect(window.localStorage.getItem("copycat-market-fut")).toBe("MXF");
    expect(window.localStorage.getItem("copycat-fut-product")).toBeNull();
  });

  it("台指期基差列(相對加權)+ 更新時刻", () => {
    renderPage();
    const row = screen.getByTestId("basis-row");
    expect(row.textContent).toContain("42142");
    expect(row.textContent).toContain("+102.08");
    expect(row.textContent).toContain("10:16");
  });

  it("txf null → 價差顯示「-」", () => {
    renderPage(null);
    expect(screen.getByText(/價差 -/)).toBeTruthy();
  });
});

describe("IndexPage 週期列(SC-3)", () => {
  it("十七顆週期鈕,順序 = 分時 / 1-10分 / 30 / 60 / 90 / 日 / 週 / 月", () => {
    renderPage();
    const labels = [
      "分時", "1分", "2分", "3分", "4分", "5分", "6分", "7分", "8分", "9分", "10分",
      "30分", "60分", "90分", "日K", "週K", "月K",
    ];
    const nodes = labels.map((l) => btn(l));
    for (let i = 1; i < nodes.length; i += 1) {
      // DOM 順序 = 畫面由左至右
      expect(nodes[i - 1]!.compareDocumentPosition(nodes[i]!) & Node.DOCUMENT_POSITION_FOLLOWING)
        .toBeTruthy();
    }
  });

  it("預設分時;切日K 後打 /api/market/bars 並持久化", async () => {
    renderPage();
    expect(btn("分時").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(btn("日K"));
    expect(window.localStorage.getItem("copycat-market-tf")).toBe("day");
    await waitFor(() =>
      expect(lastUrls.some((u) => u.includes("/api/market/bars/TWSE?tf=D"))).toBe(true),
    );
  });

  it("分 K 走 tf=1 共用原料(30/60/90 由前端聚合)", async () => {
    renderPage();
    fireEvent.click(btn("90分"));
    await waitFor(() =>
      expect(lastUrls.some((u) => u.includes("/api/market/bars/TWSE?tf=1&days=30"))).toBe(true),
    );
  });
});

describe("IndexPage 櫃買降級(SC-6)", () => {
  it("日/週/月 K 鈕 disabled,分 K 仍可點", () => {
    renderPage();
    fireEvent.click(btn("櫃買"));
    for (const label of ["日K", "週K", "月K"]) {
      expect(btn(label).getAttribute("aria-disabled")).toBe("true");
      expect(btn(label).disabled).toBe(true);
    }
    expect(btn("30分").disabled).toBe(false);
  });

  it("從加權(日K)切到櫃買 → 自動落回分時,不停在 disabled 模式", () => {
    renderPage();
    fireEvent.click(btn("日K"));
    fireEvent.click(btn("櫃買"));
    expect(btn("分時").getAttribute("aria-pressed")).toBe("true");
  });

  it("後端回 refusal → 圖區顯示明確理由,不畫假圖", async () => {
    stubFetch({
      key: "OTC",
      tf: "D",
      bars: [],
      meta: {
        source: "none",
        coverage_from: null,
        coverage_to: null,
        partial_last: false,
        volume: false,
        refusal: "NO_HISTORICAL_SOURCE",
        synth_since: null,
      },
    });
    renderPage();
    fireEvent.click(btn("日K"));
    await waitFor(() =>
      expect(screen.getByText("達錢 4 未提供櫃買指數,無歷史 K 線資料源")).toBeTruthy(),
    );
  });

  it("localStorage 存著非法組合(櫃買 + 日K)重載後落回分時", () => {
    window.localStorage.setItem("copycat-market-key", "OTC");
    window.localStorage.setItem("copycat-market-tf", "day");
    renderPage();
    expect(btn("櫃買").getAttribute("aria-pressed")).toBe("true");
    expect(btn("分時").getAttribute("aria-pressed")).toBe("true");
  });

  it("期指沒有分時 → 分時鈕 disabled,由加權切過去自動落到 1分", () => {
    renderPage();
    fireEvent.click(btn("台指期"));
    expect(btn("分時").disabled).toBe(true);
    expect(btn("1分").getAttribute("aria-pressed")).toBe("true");
  });
});

describe("IndexPage 重疊(SC-7 既有能力保留)", () => {
  it("分時下有重疊 toggle,開啟後顯示加權 vs 櫃買疊線並持久化", () => {
    renderPage();
    fireEvent.click(btn("重疊"));
    expect(screen.getByText("加權 vs 櫃買(相對昨收 %)")).toBeTruthy();
    expect(screen.getByLabelText("指數重疊走勢")).toBeTruthy();
    expect(window.localStorage.getItem("copycat-index-mode")).toBe("overlay");
  });

  it("舊 localStorage 值 overlay 讀時遷移(backward compat)", () => {
    window.localStorage.setItem("copycat-index-mode", "overlay");
    renderPage();
    expect(screen.getByText("加權 vs 櫃買(相對昨收 %)")).toBeTruthy();
  });

  it("切到 K 線週期後不再顯示重疊圖", () => {
    window.localStorage.setItem("copycat-index-mode", "overlay");
    renderPage();
    fireEvent.click(btn("日K"));
    expect(screen.queryByLabelText("指數重疊走勢")).toBeNull();
  });
});

describe("IndexPage meta 行(SC-4:來源 / 涵蓋期間)", () => {
  it("顯示資料源中文與涵蓋期間", async () => {
    renderPage();
    fireEvent.click(btn("日K"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("達錢 4 日K");
    expect(meta.textContent).toContain("2026-07-27 ~ 2026-07-29");
  });

  it("fallback 分支要說實話(tc4_dk_1k_agg),partial_last 標未收盤", async () => {
    stubFetch({
      ...DK_BODY,
      meta: { ...DK_BODY.meta, source: "tc4_dk_1k_agg", partial_last: true },
    });
    renderPage();
    fireEvent.click(btn("週K"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("達錢 4 1分K 聚合(日K 無資料)");
    expect(meta.textContent).toContain("最後一根未收盤");
  });

  it("本機合成標明來源與起始時刻;無量資料不畫 0 柱、量欄顯示「—」", async () => {
    stubFetch({
      key: "OTC",
      tf: "1",
      bars: [{ t: "2026-07-30 10:17", o: 359_800, h: 359_900, l: 359_700, c: 359_800, v: 0 }],
      meta: {
        source: "mis_poll_synth",
        coverage_from: "2026-07-30",
        coverage_to: "2026-07-30",
        partial_last: false,
        volume: false,
        refusal: null,
        synth_since: "10:17",
      },
    });
    renderPage();
    fireEvent.click(btn("櫃買"));
    fireEvent.click(btn("1分"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("本機合成(MIS 5秒取樣)");
    expect(meta.textContent).toContain("自 10:17 起");
    expect(screen.getByText("無量資料")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy(); // 資訊列的量欄
  });
});
