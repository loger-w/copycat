/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import type { BreadthState } from "@/types";
import {
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";

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

/** 漲跌停列表(**恆掛右欄**)的合法 payload。每次 render 都真掛 `LimitListBody`
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

/** 路由表**寫死**(App.test.tsx 樣板),不留「依測試需要才加」的空間:
 *  各測試怎麼點是自由度,而每條路由的 payload 形狀不是。 */
function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      lastUrls.push(u);
      if (u.includes("/api/market/breadth/rows")) {
        return new Response(JSON.stringify(BREADTH_ROWS));
      }
      return new Response(JSON.stringify(DK_BODY));
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  lastUrls = [];
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
    fireEvent.click(pane("left").getByRole("radio", { name: "日K" }));
    expect((pane("left").getByRole("radio", { name: "日K" }) as HTMLInputElement).checked).toBe(true);
    expect((pane("right").getByRole("radio", { name: "分時" }) as HTMLInputElement).checked).toBe(true);
    expect((pane("right").getByRole("radio", { name: "日K" }) as HTMLInputElement).checked).toBe(false);
  });

  it("(b2) 兩 pane 標的彼此獨立:右切加權,左仍是加權且右不影響左標題", () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("radio", { name: "加權" }));
    expect(pane("right").getByText("加權指數")).toBeTruthy();
    expect(pane("left").getByText("加權指數")).toBeTruthy();
    expect((pane("left").getByRole("radio", { name: "加權" }) as HTMLInputElement).checked).toBe(true);
  });

  it("(d) 右 pane 寫 market2 三支 key,左 pane 的舊 key 不動", async () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("radio", { name: "加權" }));
    fireEvent.click(pane("right").getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBe("day"));
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBe("TWSE");
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBeNull();
  });

  it("(d2) 左 pane 寫舊 key,market2 三支不動", async () => {
    renderPage();
    fireEvent.click(pane("left").getByRole("radio", { name: "台指期" }));
    fireEvent.click(pane("left").getByRole("radio", { name: "小台" }));
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

  // 常駐區彼此的落點原文不動;下錨(2026-08-14 是「相關係數收合鈕」、2026-08-16 是
  // subtab 列容器)隨 subtab 機制退役一起拿掉 —— 家數帶在左欄內的順序由本條守,
  // 左右兩欄的相對位置屬佈局包(§5.2b (y2)),不在這裡混著鎖。
  it("(f2) 家數帶位於雙 pane 之後", () => {
    renderPage(TXF, BREADTH);
    const left = screen.getByTestId("market-pane-left");
    const band = screen.getByTestId("breadth-band");
    expect(left.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(f3) breadth 為 null 時家數帶照樣在位(載入中),不炸圖", () => {
    renderPage(TXF, null);
    expect(screen.getByTestId("breadth-band").textContent).toContain("載入中");
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
  });
});

// 🔴 2026-08-16 subtab 機制退役(一頁總覽):整組「IndexPage subtab 列」describe
// (s1)-(s7) 連同 `subtabs()` / `subtab()` helper 與 CorrPage 的 hoisted mock 一起刪除 ——
// tablist、`INDEX_SUBTAB_KEY` 白名單還原、「切走即 unmount」都不再是本頁的行為。
// 相關係數改由 App 的頂層 tab 掛載,其 lazy / WS 語意由 App 層測試接手。
describe("IndexPage 一頁總覽(subtab 退役)", () => {
  it("(l1) 沒有 subtab 列,漲跌停列表恆掛", async () => {
    renderPage(TXF, BREADTH);
    await act(async () => {});

    expect(screen.queryByRole("tablist", { name: "台股綜合分頁" })).toBeNull();
    expect(screen.queryByTestId("index-subtabs")).toBeNull();
    expect(screen.getByTestId("limit-list")).toBeTruthy();
  });

  // 偏好鍵整支退役:讀寫兩側都要斷,只鎖 setItem 會漏掉 `useState` initializer 那次
  // getItem(留著它 = 白名單還原邏輯仍在,殘值照樣有語意)。`keys.length` 自檢確保
  // spy 真的掛上(兩個 pane 的標的 / 週期 key 必有讀取),否則本條靜默轉 vacuous。
  it("(l2) 不再讀寫 copycat-index-subtab(殘值交給 App 的 orphan purge)", async () => {
    const getSpy = vi.spyOn(Storage.prototype, "getItem");
    const setSpy = vi.spyOn(Storage.prototype, "setItem");
    renderPage(TXF, BREADTH);
    await act(async () => {});

    const keys = [...getSpy.mock.calls, ...setSpy.mock.calls].map(([key]) => key);
    expect(keys.length).toBeGreaterThan(0);
    expect(keys).not.toContain("copycat-index-subtab");
  });
});

// 版面 class 只能用字串鎖:jsdom 不載 Tailwind CSS,「有沒有捲軸」「兩欄還是一欄」在
// 這裡量不到(真值由 SC-3 / SC-7 的截圖 + JS 量測收)。這四條守的是**捲軸的唯一落點**、
// **兩個斷點的存在**與**可縮鏈的條件化**,改壞任何一項都會靜默回到「圖卡溢出壓在家數帶
// 上、捲軸永遠不出現」的 r3 前狀態。
describe("IndexPage 一頁總覽版面(§4.1 + amendment r3)", () => {
  it("(y1) 捲軸只掛在主 grid;單欄態是 flex-col,1050px 才切 grid", () => {
    const { container } = renderPage(TXF, BREADTH);
    const root = container.firstElementChild!;
    expect(root.className).toContain("@container");
    expect(root.className).not.toContain("overflow-y-auto");

    const grid = screen.getByTestId("index-main-grid");
    expect(grid.className).toContain("overflow-y-auto");
    expect(grid.className).toContain("min-h-0");
    // 單欄態必須是 flex-col:grid 的兩條 auto 列會把自由空間**等分**給左右欄,列高與
    // 內容無關 → 左欄溢出而主 grid 的 scrollHeight 恆等於 clientHeight(逃生口失效,
    // code review WL-1 的根因)。`grid-cols-1` 回來就是回到那個狀態。
    expect(grid.className).toContain("flex-col");
    expect(grid.className).not.toContain("grid-cols-1");
    expect(grid.className).toContain("@[1050px]:grid");
    expect(grid.className).toContain("@[1050px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]");
  });

  it("(y2) DOM 序:左欄(騰落線)在右欄漲跌停列表之前", async () => {
    renderPage(TXF, BREADTH);
    await act(async () => {});

    const adl = screen.getByTestId("adl-chart");
    const list = screen.getByTestId("limit-list");
    expect(adl.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(y3) 雙圖 grid:640px 顯式斷點 + 顯式地板,不再掛 min-h-0", () => {
    renderPage(TXF, BREADTH);
    const grid = screen.getByTestId("market-pane-left").parentElement!;
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.className).toContain("@[640px]:grid-cols-2");
    expect(grid.className).not.toContain("auto-fit");
    // `min-h-0` + `flex-1` 的組合讓雙圖軌可以被壓到低於內容高 → 圖卡(overflow visible)
    // 溢出壓在家數帶上,而不是把左欄撐高讓主 grid 出捲軸。地板 20rem 換掉它。
    expect(grid.className).toContain("min-h-80");
    expect(grid.className).not.toContain("min-h-0");
  });

  // TD-5:可縮鏈原本只鎖三個節點,鏈中任一段的 `min-h-0` 被無條件化(r3 前的狀態)都
  // 不會有測試變紅。左欄 / 右欄框各自要「兩欄態才可縮」——單欄態下 min-h-0 一路傳到
  // 底,內容就再也撐不高主 grid。
  it("(y4) 左欄與右欄框的 min-h-0 都條件化到 @[1050px](單欄態內容決定高)", () => {
    renderPage(TXF, BREADTH);
    const leftCol = screen.getByTestId("market-pane-left").parentElement!.parentElement!;
    // 左欄自己也是 container:雙圖斷點量的是左欄寬,不是整頁寬
    expect(leftCol.className).toContain("@container");
    expect(leftCol.className).toContain("@[1050px]:min-h-0");

    const rightBox = screen.getByTestId("limit-list").parentElement!;
    expect(rightBox.className).toContain("@[1050px]:min-h-0");
    expect(rightBox.className).toContain("border-line");
  });

  // 兩欄態的 6:5 分配只能由**左欄**發出:雙圖 grid / 家數帶 section / 騰落線 wrapper 的
  // 最近 `@container` 祖先是左欄自己(它為了 640px 雙圖斷點就是 container),兩欄態左欄
  // 僅 630–930px → 直接掛在它們身上的 `@[1050px]:` 永不成立(frontend-conventions
  // 「巢狀 container」陷阱,與 pane 層 min-h-0 同一個教訓)。量得到 root 的只有左欄本身,
  // 所以由左欄以 `@[1050px]:` 設 CSS 變數、子節點讀變數;變數的預設值 = 改動前 class 的
  // 展開值,單欄態(SC-6 1366×768)逐值不變由建構保證。
  // 這條守的是「變數的發點與三個讀點都在」——jsdom 量不到真高,任一段掉了都是
  // 「畫面看起來一樣」的靜默回退(騰落線又變回固定 96px)。
  it("(y5) 兩欄態 6:5 由左欄的 --idx-* 變數發出,雙圖 grid / 家數帶 section 讀變數", () => {
    renderPage(TXF, BREADTH);
    const grid = screen.getByTestId("market-pane-left").parentElement!;
    const leftCol = grid.parentElement!;

    for (const v of [
      "@[1050px]:[--idx-chart-flex:6_1_0%]",
      "@[1050px]:[--idx-adl-flex:5_1_0%]",
      "@[1050px]:[--idx-adl-wrap-flex:1_1_0%]",
      // 🔴 N062(2026-08-24,事前標為該變):地板 10rem → 6rem。
      // 10rem 地板 + 家數帶兩列固定 chrome(≈148px)+ gap 8 = 316px > 矮視窗兩欄態
      // 分給 section 的 5/11(2026-08-20 機械實測 1536×700:主 grid 622/676 出 54px
      // 捲軸、溢出源正是這個 section 262/316)。6rem = wrapper 自身 `h-24` 的 96px
      // (= 單欄態高度)—— 它是**地板不是指定高**,1536×864 實測 wrapper 拿到 181px
      // 遠高於任一地板,正常視窗逐值不變。
      "@[1050px]:[--idx-adl-min:6rem]",
    ]) {
      expect(leftCol.className).toContain(v);
    }

    // 雙圖 grid 讀 `--idx-chart-flex`(預設 `1 1 0%` = 原 `flex-1` 的展開值)。獨立的
    // `flex-1` token 不能留:兩支 flex utility 誰先誰後由 Tailwind 產出順序決定,留著
    // 就有一半機率把 shorthand 蓋掉、6:5 靜默失效。
    expect(grid.className).toContain("[flex:var(--idx-chart-flex,1_1_0%)]");
    expect(grid.className.split(/\s+/)).not.toContain("flex-1");

    // 家數帶 + 騰落線那段:`shrink-0` → 變數 flex(預設 `0 0 auto` 逐值等價)+ `min-h-0`
    // (兩欄態才真的縮出空間給騰落線;單欄態 flex 不縮,min-height 不作用 → 無條件安全)。
    const section = screen.getByTestId("adl-chart").parentElement!;
    expect(section.tagName).toBe("SECTION");
    expect(section.className).toContain("[flex:var(--idx-adl-flex,0_0_auto)]");
    expect(section.className).toContain("min-h-0");
    expect(section.className.split(/\s+/)).not.toContain("shrink-0");
  });
});
