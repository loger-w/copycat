/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import type { BreadthState } from "@/types";
import {
  INDEX_SUBTAB_KEY,
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";

/** CorrPage 走**檔案級 hoisted mock**(`CorrSection.test.tsx` 樣板):lazy + Suspense 的
 *  失敗樣態是「永遠停在 fallback」,而 `queryBy(...) === null` 對「沒 render」與「還在
 *  suspend」是同一個答案 —— 掛載一律 `findBy*` 等真 mount,卸載斷言 unmount **計數 +1**。
 *  真身級(不 mock)的「非 corr subtab 零 WS」鎖在 `IndexPage.corr-lazy.test.tsx`:
 *  本檔的 stub 不建線,「stub WS 建構數 0」在這裡恆真 = 沒有鑑別力。 */
const counts = vi.hoisted(() => ({ mount: 0, unmount: 0 }));

vi.mock("@/components/corr/CorrPage", async () => {
  const React = await import("react");
  function Stub() {
    React.useEffect(() => {
      counts.mount += 1;
      return () => {
        counts.unmount += 1;
      };
    }, []);
    return React.createElement("div", { "data-testid": "corr-stub" });
  }
  return { default: Stub };
});

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

/** 漲跌停列表(**預設 subtab**)的合法 payload。改版後每次 render 都真掛 `LimitListBody`
 *  並打這條路由 —— 回 `DK_BODY` 會讓 `data.rows` 是 undefined,`buildEntries` 直接
 *  TypeError 把整頁炸掉(P0-2)。`rows: []` 走「今日尚無漲跌停」空態,不與其他斷言撞字。 */
const BREADTH_ROWS = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [],
};

/** 類股 subtab 的合法 payload。`rotation` **不得缺**:`SectorSection` 以
 *  `rotation === null` 分流空態,undefined 會直接拋(與 P0-2 同型;round-2 P1-2)。 */
const SECTOR_STATE = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  rotation: { industries: [] },
};

/** 路由表**寫死**(App.test.tsx 樣板),不留「依測試需要才加」的空間:
 *  哪個 subtab 被掛上是測試的自由度,而每個 panel 的 payload 形狀不是。 */
function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      lastUrls.push(u);
      if (u.includes("/api/market/breadth/rows")) {
        return new Response(JSON.stringify(BREADTH_ROWS));
      }
      // 成員層在前:兩條路由共前綴,順序反過來會讓成員請求被類股狀態那條吃掉。
      if (u.includes("/api/market/sector/members")) {
        return new Response(JSON.stringify({ industry: "", sub_industry: null, members: [] }));
      }
      if (u.includes("/api/market/sector")) return new Response(JSON.stringify(SECTOR_STATE));
      // 訊號時間軸 subtab 的 baseline。缺這條會落到 `DK_BODY`,`signals` 是 undefined
      // → 時間軸走「取數失敗」分支,而那與「路由沒寫」在畫面上同形(review A-3)。
      if (u.includes("/api/stock/signals/today")) {
        return new Response(JSON.stringify({ signals: [] }));
      }
      return new Response(JSON.stringify(DK_BODY));
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  lastUrls = [];
  counts.mount = 0;
  counts.unmount = 0;
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const BREADTH: BreadthState = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  counts: {
    twse: { limit_up: 3, up: 512, flat: 88, down: 401, limit_down: 2 },
    tpex: { limit_up: 7, up: 388, flat: 61, down: 290, limit_down: 1 },
  },
  series: [{ t: "0930", twse: [3, 512, 88, 401, 2], tpex: [7, 388, 61, 290, 1] }],
};

function renderPage(txf: TxfQuote | null = TXF, breadth: BreadthState | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IndexPage twse={series()} otc={OTC} txf={txf} futures={FUTURES} breadth={breadth} />
    </QueryClientProvider>,
  );
}

/** 兩個 pane 的按鈕文字**完全相同**(加權 / 櫃買 / 日K …)——本檔一律先收斂到 pane
 *  再查,裸 `screen.getByRole` 必撞 ambiguous。 */
function pane(id: "left" | "right") {
  return within(screen.getByTestId(`market-pane-${id}`));
}

/** subtab 列。**必帶 aria-label**:repo 內已有「主要分頁」「交易面板分頁」兩個具名
 *  tablist,全域 `getAllByRole("tab")` 撞名是寫進 App.test.tsx 的教訓(AD-4)。 */
function subtabs() {
  return screen.getByRole("tablist", { name: "台股綜合分頁" });
}

function subtab(name: string): HTMLElement {
  return within(subtabs()).getByRole("tab", { name });
}

describe("IndexPage 雙 pane 容器(SC-2)", () => {
  it("(a) 兩個 pane 同屏:左加權、右櫃買", () => {
    renderPage();
    expect(pane("left").getByText("加權指數")).toBeTruthy();
    expect(pane("right").getByText("櫃買指數")).toBeTruthy();
    expect(pane("left").queryByText("櫃買指數")).toBeNull();
    expect(pane("right").queryByText("加權指數")).toBeNull();
  });

  it("(b) 兩 pane 週期彼此獨立:左切日K,右仍停在分時", () => {
    renderPage();
    fireEvent.click(pane("left").getByRole("button", { name: "日K" }));
    expect(pane("left").getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(pane("right").getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(pane("right").getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
  });

  it("(b2) 兩 pane 標的彼此獨立:右切加權,左仍是加權且右不影響左標題", () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("button", { name: "加權" }));
    expect(pane("right").getByText("加權指數")).toBeTruthy();
    expect(pane("left").getByText("加權指數")).toBeTruthy();
    expect(pane("left").getByRole("button", { name: "加權" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("(d) 右 pane 寫 market2 三支 key,左 pane 的舊 key 不動", async () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("button", { name: "加權" }));
    fireEvent.click(pane("right").getByRole("button", { name: "日K" }));
    await waitFor(() => expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBe("day"));
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBe("TWSE");
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBeNull();
  });

  it("(d2) 左 pane 寫舊 key,market2 三支不動", async () => {
    renderPage();
    fireEvent.click(pane("left").getByRole("button", { name: "台指期" }));
    fireEvent.click(pane("left").getByRole("button", { name: "小台" }));
    await waitFor(() => expect(window.localStorage.getItem(MARKET_FUT_STORE)).toBe("MXF"));
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBe("MXF");
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBe("m1");
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET2_FUT_STORE)).toBeNull();
  });

  it("(d3) 重疊鈕只在左 pane(右 pane 開了會畫出第二張同樣的加權 vs 櫃買)", () => {
    renderPage();
    expect(pane("left").getByRole("button", { name: "重疊" })).toBeTruthy();
    expect(pane("right").queryByRole("button", { name: "重疊" })).toBeNull();
  });
});

describe("IndexPage 基差列(SC-3)", () => {
  it("(c) 基差列在雙 pane 之外只有一份,含台指期價 / 價差 / 更新時刻", () => {
    renderPage();
    const rows = screen.getAllByTestId("basis-row");
    expect(rows.length).toBe(1);
    const row = rows[0]!;
    expect(row.textContent).toContain("42142");
    expect(row.textContent).toContain("+102.08");
    expect(row.textContent).toContain("10:16");
    // 不屬於任一 pane
    expect(pane("left").queryByTestId("basis-row")).toBeNull();
    expect(pane("right").queryByTestId("basis-row")).toBeNull();
  });

  it("(c2) 基差列位於雙 pane 之上", () => {
    renderPage();
    const row = screen.getByTestId("basis-row");
    const left = screen.getByTestId("market-pane-left");
    expect(row.compareDocumentPosition(left) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(c3) 正價差用 text-bull,負價差用 text-bear", () => {
    renderPage();
    const up = screen.getByText(/價差 \+102\.08/);
    expect(up.className).toContain("text-bull");
    cleanup();
    renderPage({ p: 41_000_000, time: "10:16:10" });
    const down = screen.getByText(/價差 -1039\.92/);
    expect(down.className).toContain("text-bear");
  });

  it("(c4) txf null → 價差顯示「-」", () => {
    renderPage(null);
    expect(screen.getByText(/價差 -/)).toBeTruthy();
  });
});

describe("IndexPage 家數帶 + 騰落線(R2 SC-4)", () => {
  it("(f) 中段出現家數帶與騰落線,數字取自 breadth props", () => {
    renderPage(TXF, BREADTH);
    expect(screen.getByTestId("breadth-band")).toBeTruthy();
    expect(screen.getByTestId("adl-chart")).toBeTruthy();
    expect(screen.getByTestId("breadth-cell-twse-limit_up").textContent).toContain("3");
    // net = (3+512+7+388) − (401+2+290+1) = 910 − 694 = +216
    expect(screen.getByTestId("adl-last").textContent).toContain("+216");
  });

  // 常駐區彼此的落點原文不動;下錨從「相關係數收合鈕」(改版後不存在)換成 subtab
  // 列容器 —— 換錨不是常駐區被動到(review P0-1 / round-2 P2-1)。
  it("(f2) 家數帶位於雙 pane 之後、subtab 列之前", () => {
    renderPage(TXF, BREADTH);
    const left = screen.getByTestId("market-pane-left");
    const band = screen.getByTestId("breadth-band");
    expect(left.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(band.compareDocumentPosition(subtabs()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(f3) breadth 為 null 時家數帶照樣在位(載入中),不炸圖", () => {
    renderPage(TXF, null);
    expect(screen.getByTestId("breadth-band").textContent).toContain("載入中");
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
  });
});

// 🔴 2026-08-14 subtab 改版:四個各自收合的區塊改為一列 subtab,**一次只掛載一個**。
// 原本四組「預設收合 + 落點」describe((e)(e2)(g)(g2)(h)(h2)(i)(i2))隨收合殼一起汰換 ——
// 「收合 = unmount」的省輪詢語意等價轉移到「非 active subtab = unmount」。
describe("IndexPage subtab 列(SC-2 / SC-3 / SC-5)", () => {
  it("(s1) 四顆 tab,預設「漲跌停」active 且只掛載 limit panel", async () => {
    renderPage(TXF, BREADTH);
    await act(async () => {});

    expect(within(subtabs()).getAllByRole("tab").map((el) => el.textContent)).toEqual([
      "漲跌停",
      "類股強弱",
      "訊號時間軸",
      "相關係數",
    ]);
    expect(subtab("漲跌停").getAttribute("aria-selected")).toBe("true");
    expect(subtab("類股強弱").getAttribute("aria-selected")).toBe("false");
    expect(screen.getByTestId("limit-list")).toBeTruthy();
    expect(screen.queryByTestId("sector-section")).toBeNull();
    expect(screen.queryByTestId("signal-timeline")).toBeNull();
    // CorrPage 真身不 mount(stub 計數 0 才是有鑑別力的斷言;真身級零 WS 見 corr-lazy 檔)
    expect(counts.mount).toBe(0);
  });

  it("(s2) 點「類股強弱」→ sector 掛載、limit 卸載,偏好寫入 localStorage", async () => {
    renderPage(TXF, BREADTH);
    fireEvent.click(subtab("類股強弱"));

    expect(await screen.findByTestId("sector-section")).toBeTruthy();
    expect(screen.queryByTestId("limit-list")).toBeNull();
    expect(subtab("類股強弱").getAttribute("aria-selected")).toBe("true");
    expect(subtab("漲跌停").getAttribute("aria-selected")).toBe("false");
    expect(window.localStorage.getItem(INDEX_SUBTAB_KEY)).toBe("sector");
  });

  // (review B-4)(s2) 只鎖了「類股強弱」一顆的點擊路徑,timeline / corr 兩顆的
  // 掛載與寫入值零覆蓋 —— 寫錯字串(如寫成 "signal")在 (s3)(s4) 都測不出來:
  // 非法值一律 fallback 漲跌停,症狀只有「切過去、重整卻回到漲跌停」。
  it("(s2b) 點「訊號時間軸」→ timeline 掛載、sector 卸載,偏好寫入 timeline", async () => {
    renderPage(TXF, BREADTH);
    fireEvent.click(subtab("類股強弱"));
    await screen.findByTestId("sector-section");

    fireEvent.click(subtab("訊號時間軸"));

    expect(await screen.findByTestId("signal-timeline")).toBeTruthy();
    expect(screen.queryByTestId("sector-section")).toBeNull();
    expect(subtab("訊號時間軸").getAttribute("aria-selected")).toBe("true");
    expect(window.localStorage.getItem(INDEX_SUBTAB_KEY)).toBe("timeline");
  });

  it("(s2c) 再點「相關係數」→ CorrPage 掛載,偏好寫入 corr", async () => {
    renderPage(TXF, BREADTH);
    fireEvent.click(subtab("訊號時間軸"));
    await screen.findByTestId("signal-timeline");

    fireEvent.click(subtab("相關係數"));

    // lazy:等 stub 真 mount,不用 `queryBy === null`(suspend 與沒 render 同形)
    expect(await screen.findByTestId("corr-stub")).toBeTruthy();
    expect(counts.mount).toBe(1);
    expect(screen.queryByTestId("signal-timeline")).toBeNull();
    expect(subtab("相關係數").getAttribute("aria-selected")).toBe("true");
    expect(window.localStorage.getItem(INDEX_SUBTAB_KEY)).toBe("corr");
  });

  it("(s3) 預存 corr → 重新 mount 停在相關係數(記憶與還原)", async () => {
    window.localStorage.setItem(INDEX_SUBTAB_KEY, "corr");
    renderPage(TXF, BREADTH);

    expect(await screen.findByTestId("corr-stub")).toBeTruthy();
    expect(counts.mount).toBe(1);
    expect(subtab("相關係數").getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByTestId("limit-list")).toBeNull();
  });

  it("(s4) localStorage 非法值 → fallback 漲跌停", async () => {
    window.localStorage.setItem(INDEX_SUBTAB_KEY, "1");
    renderPage(TXF, BREADTH);
    await act(async () => {});

    expect(subtab("漲跌停").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("limit-list")).toBeTruthy();
  });

  // Safari 私密視窗:getItem 光是存取就會拋,而它在 useState 的 initializer 裡 = 整頁白屏。
  // **只對本頁那把 key 拋**:全域 throw 會先炸在 MarketPane 的四處裸 getItem(既有債,
  // 本輪 out of scope),測不到目標還誘發 scope 外的修補(round-2 P0-1)。
  it("(s5) getItem 對 subtab key 拋例外 → 不白屏,fallback 漲跌停", async () => {
    const orig = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      key: string,
    ) {
      if (key === INDEX_SUBTAB_KEY) throw new Error("SecurityError");
      return orig.call(this, key);
    });

    renderPage(TXF, BREADTH);
    await act(async () => {});

    expect(subtab("漲跌停").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("limit-list")).toBeTruthy();
    expect(screen.getByTestId("breadth-band")).toBeTruthy();
  });

  // (review B-3)SC-3 的另一半:setItem 也會拋(Safari 私密視窗 / storage 被政策鎖),
  // 而它在 onClick 裡 —— 沒接住就是「點一下整頁炸掉」。分流同 (s5):只對本頁那把 key
  // 拋,全域 throw 會先炸在 scope 外的既有裸 setItem。
  it("(s5b) setItem 對 subtab key 拋例外 → 切換照樣生效,不炸", async () => {
    const orig = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string,
    ) {
      if (key === INDEX_SUBTAB_KEY) throw new Error("QuotaExceededError");
      orig.call(this, key, value);
    });

    renderPage(TXF, BREADTH);
    fireEvent.click(subtab("類股強弱"));

    expect(await screen.findByTestId("sector-section")).toBeTruthy();
    expect(subtab("類股強弱").getAttribute("aria-selected")).toBe("true");
    expect(subtab("漲跌停").getAttribute("aria-selected")).toBe("false");
    expect(screen.queryByTestId("limit-list")).toBeNull();
  });

  it("(s6) subtab 列位於騰落線之後", () => {
    renderPage(TXF, BREADTH);
    const adl = screen.getByTestId("adl-chart");
    expect(adl.compareDocumentPosition(subtabs()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  // SC-5:切走 = 舊 panel unmount(corr 的兩條 WS 靠 hook cleanup 才會斷)。
  // 用 unmount **計數 +1** 而不是 `queryBy === null` —— 後者在 lazy 下 vacuously pass。
  it("(s7) corr → 漲跌停:CorrPage 真的被 unmount", async () => {
    window.localStorage.setItem(INDEX_SUBTAB_KEY, "corr");
    renderPage(TXF, BREADTH);
    await screen.findByTestId("corr-stub");
    expect(counts.unmount).toBe(0);

    fireEvent.click(subtab("漲跌停"));
    await act(async () => {});

    expect(counts.unmount).toBe(1);
    expect(screen.getByTestId("limit-list")).toBeTruthy();
    expect(window.localStorage.getItem(INDEX_SUBTAB_KEY)).toBe("limit");
  });
});
