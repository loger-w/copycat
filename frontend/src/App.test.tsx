/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { purgeOrphanKeys } from "@/lib/constants";
import { emitSignal } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {}
}

const INDEX_STATE = {
  trade_date: "2026-07-28",
  twse: {
    p: 42_039_920, ref: 43_634_190, high: 43_221_930, low: 41_815_780,
    stale: false, last_minute: null, minutes: { "0901": 43_000_000 },
  },
  otc: {
    p: 359_800, ref: 378_090, high: 373_420, low: 358_430,
    stale: false, last_minute: null, minutes: { "1017": 359_800 },
  },
  txf: { p: 42_142_000, time: "10:16:10" },
};

const BREADTH_ROWS = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [
    {
      stock_id: "1101", name: "台泥", market: "twse", close: 55.5, change_rate: 9.98,
      volume_ratio: 2.5, total_amount: 9e8, limit_up: true, limit_down: false,
      touched_limit_up: false, touched_limit_down: false, streak: 3, streak_capped: false,
    },
  ],
};

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal("fetch", appFetch());
});

/** 版本落差偵測的兩條路由預設回 `git_sha: null` = 「不可得」→ 全域無膠囊、無 warn
 *  (後端 sha 為 null 時 badge 連 /__build/sha 都不會問)。
 *  傳 `{fe, be, behind}` 進來即成 dev range 判別的 fixture(design C3)。
 *  當日訊號 jsonl 的 baseline 恆為空(= 與 404 時的畫面同義);rail 的訊號一律走 bus。 */
function appFetch(sha?: { fe: string | null; be: string | null; behind: boolean | null }) {
  return vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/api/index/state")) return new Response(JSON.stringify(INDEX_STATE));
    // 漲跌停列表(R3 SC-5 的跳轉起點)。2026-08-14 subtab 改版後**預設 subtab 就是漲跌停**
    // → 任何停在台股綜合 tab 的測試都會走這條分支(不再是「僅跳轉測試才用到」)。
    if (u.includes("/api/market/breadth/rows")) return new Response(JSON.stringify(BREADTH_ROWS));
    if (u.includes("/api/stock/signals/today")) {
      return new Response(JSON.stringify({ signals: [] }));
    }
    if (u.includes("/api/health")) {
      return new Response(JSON.stringify({ git_sha: sha?.be ?? null, git_dirty: false }));
    }
    if (u.includes("/__build/sha")) {
      return new Response(JSON.stringify({ git_sha: sha?.fe ?? null, behind: sha?.behind ?? null }));
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("App(index-board T9)", () => {
  it("無 localStorage 時預設停在「台股綜合」(index-board SC-1)", () => {
    renderApp();
    expect(screen.getByRole("tab", { name: "台股綜合" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("舊 localStorage 值 txo 仍還原到「選擇權」(backward compat)", () => {
    window.localStorage.setItem("copycat-tab", "txo");
    renderApp();
    expect(screen.getByRole("tab", { name: "選擇權" }).getAttribute("aria-selected")).toBe("true");
  });

  it("nav 有「台股綜合」tab 且 IndexBar 常駐(切到選擇權 tab 仍可見)", async () => {
    renderApp();
    expect(screen.getByRole("tab", { name: "台股綜合" })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "選擇權" }));
    await waitFor(() => expect(screen.getByText(/加權/).textContent).toContain("42039.92"));
    expect(screen.getByText(/櫃買/).textContent).toContain("359.8");
    // /台指/ 會撞 TXO h1「台指選擇權」→ 以基差數字指認 IndexBar 台指組
    expect(screen.getAllByText(/台指/).some((el) => el.textContent?.includes("+102.08"))).toBe(
      true,
    );
  });

  it("localStorage 記住 index tab,重載復原(review B8)", async () => {
    window.localStorage.setItem("copycat-tab", "index");
    renderApp();
    expect(screen.getByRole("tab", { name: "台股綜合" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
  });

  it("切到台股綜合 tab 顯示 IndexPage(標的列 + 週期列)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "台股綜合" }));
    // 版面自 index-board SC-2/3 起由「兩張並排卡」改為「標的切換 + 單一主圖」;
    // 台股綜合 R1 起是**雙 pane** —— 兩張圖的按鈕文字完全相同,裸 getByRole 會撞
    // ambiguous,收斂到左 pane 查(斷言意圖不變:大盤頁有標的列 + 週期列)。
    await waitFor(() => expect(screen.getByTestId("market-pane-left")).toBeTruthy());
    const left = within(screen.getByTestId("market-pane-left"));
    expect(left.getByText("加權指數")).toBeTruthy();
    expect(left.getByRole("button", { name: "櫃買" })).toBeTruthy();
    expect(left.getByRole("button", { name: "台指期" })).toBeTruthy();
    expect(left.getByRole("button", { name: "日K" })).toBeTruthy();
  });
});

// 🟢 一頁總覽 R2(SC-1):相關係數自台股綜合頁的 subtab **升回頂層 tab**(排最後一顆)
// —— R1 曾把它併進台股綜合頁,本輪 subtab 機制退役後改以第 5 顆頂層 tab 承接,
// localStorage 值域同步**加回** `corr`(R1 前的舊值因此重新還原到相關係數頁,D7 預期)。
describe("App 相關係數升回頂層 tab(R2 SC-1)", () => {
  it("舊 localStorage 值 corr 還原到「相關係數」(值域加回)", () => {
    window.localStorage.setItem("copycat-tab", "corr");
    renderApp();
    expect(screen.getByRole("tab", { name: "相關係數" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("nav 有「相關係數」tab 且排在最後一顆", () => {
    renderApp();
    const nav = within(screen.getByRole("tablist", { name: "主要分頁" }));
    expect(nav.getByRole("tab", { name: "相關係數" })).toBeTruthy();
    expect(nav.getAllByRole("tab").at(-1)?.textContent).toBe("相關係數");
  });
});

// 🟢 台股綜合 R3(SC-5):列表 → 個股(期)的一鍵銜接。走**整條真鏈**
// (App → IndexPage → LimitListSection → 列 onClick),不 mock 中間任何一層 ——
// 少接一根線(IndexPage 沒把 onOpenStock 往下傳、App 沒 setStockCode)在元件級測試
// 各自都是綠的,只有這裡會紅。
describe("App 漲跌停列表跳轉個股(R3 SC-5)", () => {
  async function openList() {
    window.localStorage.setItem("copycat-tab", "index");
    // 預設 subtab 即漲跌停(2026-08-14 改版)—— 不再需要 seed 展開狀態
    renderApp();
    return await screen.findByTestId("limit-row-1101");
  }

  it("點列 → tab 切到「個股(期)」", async () => {
    fireEvent.click(await openList());
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "個股(期)" }).getAttribute("aria-selected")).toBe(
        "true",
      ),
    );
    expect(screen.getByRole("tab", { name: "台股綜合" }).getAttribute("aria-selected")).toBe(
      "false",
    );
  });

  // FE-2:tab 是 `hidden` 保留而非 unmount → 列表展開過一次就會跨 tab 存活,沒有
  // `active` gate 的話使用者看著別的 tab 時它照樣整個盤中每 10 秒抓一份全市場 payload。
  // 走全鏈(App → IndexPage → LimitListSection → useBreadthRows):少接一根線在
  // hook / 元件級測試各自都是綠的,只有這裡會紅。
  it("切離台股綜合 tab → 列表停止背景輪詢(active gate 全鏈)", async () => {
    // 只假造 `Date`(交易時段判別要可決定),**不假造 timer** —— RTL 的 waitFor 在
    // vitest 下偵測不到 fake timers(它查的是全域 `jest`),整支 fake 會讓 findBy 永遠
    // 等不到、lazy 的 IndexPage 也掛不上(本輪實測)。輪詢本身的行為在
    // useBreadthRows.test.ts / LimitListSection.test.tsx 已用 fake timers 驗過,
    // 這裡要鎖的是**線有沒有接上**:tab 切走後這支 query 的輪詢間隔要真的變成 false。
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    window.localStorage.setItem("copycat-tab", "index");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );
    await screen.findByTestId("limit-row-1101");

    const query = client.getQueryCache().find({ queryKey: ["breadth-rows"] })!;
    const pollMs = () => {
      const ri = query.observers[0]!.options.refetchInterval;
      return typeof ri === "function" ? ri(query) : ri;
    };
    expect(pollMs()).toBe(10_000); // 人在台股綜合 tab:照輪詢

    fireEvent.click(screen.getByRole("tab", { name: "選擇權" }));
    await waitFor(() => expect(pollMs()).toBe(false));
  });

  it("點列 → 個股頁收到該檔(打 /api/stock/state/1101,含 set_main)", async () => {
    fireEvent.click(await openList());
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
        String(c[0]),
      );
      expect(calls.some((u) => u.includes("/api/stock/state/1101"))).toBe(true);
    });
    expect(window.localStorage.getItem("copycat-stock-main-code")).toBe("1101");
  });
});

// 台股綜合頁背景輪詢的 active gate 全鏈鎖。
describe("App 台股綜合 active gate(round-2 XR-4)", () => {
  // (review round-2 XR-4)R1 的兩張指數圖是同頁**唯一**沒吃 `active` gate 的輪詢:
  // 分 K 那條路在當日段每次都真走 TC4 SubHistory,與 REALTIME 搶同一把 `api.lock`
  // —— tab 切走後照打是看不見的成本。走全鏈(App → IndexPage → MarketPane →
  // MarketChart → useMarketBars):中間少接一根線在元件級測試全綠,只有這裡會紅。
  it("切離台股綜合 tab → 大盤分 K 停止背景輪詢(active gate 全鏈)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] }); // 同上:RTL 的 waitFor 偵測不到 fake timer
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    window.localStorage.setItem("copycat-tab", "index");
    // 預設週期是分時走勢(不打 bars API)→ 指定分 K 才有這支 query 可驗
    window.localStorage.setItem("copycat-market-key", "TWSE");
    window.localStorage.setItem("copycat-market-tf", "m1");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );

    const query = await waitFor(() => {
      const q = client.getQueryCache().find({ queryKey: ["market-bars", "TWSE", "1", 30] });
      expect(q).toBeTruthy();
      return q!;
    });
    const pollMs = () => {
      const ri = query.observers[0]!.options.refetchInterval;
      return typeof ri === "function" ? ri(query) : ri;
    };
    expect(pollMs()).toBe(60_000); // 人在台股綜合 tab:照輪詢

    fireEvent.click(screen.getByRole("tab", { name: "選擇權" }));
    await waitFor(() => expect(pollMs()).toBe(false));
  });
});

describe("App(capital WS 唯一掛載 review B2)", () => {
  it("App 掛載即建 capital WS;個股+期貨 tab 都訪過仍單一連線", async () => {
    renderApp();
    const capitalCount = () =>
      FakeWS.instances.filter((w) => w.url.endsWith("/ws/capital")).length;
    expect(capitalCount()).toBe(1); // TXO tab 下也有推播(B2 主訴)
    fireEvent.click(screen.getByRole("tab", { name: "個股(期)" }));
    await waitFor(() => expect(screen.getByText("從自選清單選擇一檔開始看盤")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "期貨" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "大台" })).toBeTruthy());
    expect(capitalCount()).toBe(1); // ladder 掛載不再各開一條
  });
});

describe("App(期貨 tab T15)", () => {
  it("nav tab 順序 = 台股綜合 / 個股(期) / 選擇權 / 期貨 / 相關係數", () => {
    renderApp();
    // 🔴-1:右欄也是 tablist(閃電/委託/部位)→ 全域 getAllByRole("tab") 會撞名,
    // 收斂到 nav。斷言意圖(nav 各 tab 的文字與順序)不變;一頁總覽 R2(SC-1)起
    // 「相關係數」自台股綜合頁的 subtab 升回**最後一顆頂層 tab**(D7),前四顆順序不動。
    const labels = within(screen.getByRole("tablist", { name: "主要分頁" }))
      .getAllByRole("tab")
      .map((el) => el.textContent);
    expect(labels).toEqual(["台股綜合", "個股(期)", "選擇權", "期貨", "相關係數"]);
  });

  it("切到期貨 tab 顯示 FuturesPage(lazy 商品切換鈕)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "期貨" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "大台" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "小台" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "微台" })).toBeTruthy();
  });

  it("localStorage copycat-tab=futures 重載復原", async () => {
    window.localStorage.setItem("copycat-tab", "futures");
    renderApp();
    expect(screen.getByRole("tab", { name: "期貨" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "大台" })).toBeTruthy());
  });
});

// ---- 版面重構(SC-1 / SC-3 / D-3 / D-16)----

function navTabs() {
  return within(screen.getByRole("tablist", { name: "主要分頁" })).getAllByRole("tab");
}
function railTabs() {
  return within(screen.getByRole("tablist", { name: "交易面板分頁" })).getAllByRole("tab");
}

describe("App 版面重構(SC-1 寬度 / SC-3 右欄常駐)", () => {
  it("root 不再有 max-w-6xl 上限,吃滿視窗寬(SC-1)", () => {
    const { container } = renderApp();
    const root = container.firstElementChild!;
    expect(root.className).toContain("w-full");
    expect(root.className).not.toContain("max-w-6xl");
    expect(root.className).not.toContain("mx-auto");
  });

  it("右欄在四個主 tab 之間切換時位置固定、三顆 tab 不變(SC-3)", async () => {
    renderApp();
    const expectRail = () =>
      expect(railTabs().map((el) => el.textContent)).toEqual(["閃電", "委託", "部位"]);
    expectRail(); // TXO
    fireEvent.click(screen.getByRole("tab", { name: "個股(期)" }));
    await waitFor(() => expect(screen.getByText("從自選清單選擇一檔開始看盤")).toBeTruthy());
    expectRail();
    fireEvent.click(screen.getByRole("tab", { name: "期貨" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "大台" })).toBeTruthy());
    expectRail();
    fireEvent.click(screen.getByRole("tab", { name: "台股綜合" }));
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
    expectRail();
  });

  it("TXO / 指數 tab 的閃電 tab 顯示「此頁無可下單標的」(D6)", () => {
    renderApp();
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
  });

  it("nav 有 5 顆 tab、右欄有 3 顆,兩者互不干擾", () => {
    renderApp();
    // 斷言意圖不變(兩個 tablist 各自獨立);nav 由 4 → 5 是一頁總覽 R2(SC-1)
    // 把「相關係數」自 subtab 升回頂層 tab 的預期行為改變,右欄三顆不受影響。
    expect(navTabs().length).toBe(5);
    expect(railTabs().length).toBe(3);
  });
});

describe("App 資料流上提(D-3 / D-16)", () => {
  it("未訪問個股 tab 時不打 /api/stock/state(D-16:避免無謂 set_main + 全量回補)", () => {
    window.localStorage.setItem("stock-main-code", "2330");
    renderApp();
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
      String(c[0]),
    );
    expect(calls.some((u) => u.includes("/api/stock/state"))).toBe(false);
  });

  it("切到個股 tab 後才建立 stock WS 並取 snapshot", async () => {
    window.localStorage.setItem("stock-main-code", "2330");
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "個股(期)" }));
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
        String(c[0]),
      );
      expect(calls.some((u) => u.includes("/api/stock/state/2330"))).toBe(true);
    });
  });

  it("stock WS status=down → 個股頁告警列(W-B5 文案逐字不變;自 StockPage.test 上移)", async () => {
    window.localStorage.setItem("copycat-tab", "stock");
    renderApp();
    await waitFor(() =>
      expect(FakeWS.instances.some((w) => w.url.endsWith("/ws/stock"))).toBe(true),
    );
    const ws = FakeWS.instances.find((w) => w.url.endsWith("/ws/stock"))!;
    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: "status", tc4: "down", backfilling: null }) });
    });
    await waitFor(() =>
      expect(screen.getByText(/達錢 4 連線中斷,恢復後自動回補/)).toBeTruthy(),
    );
  });

  it("期貨商品選擇寫入 localStorage(自 FuturesPage.test 上移:state 已上提到 App)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "期貨" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "小台" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "小台" }));
    expect(window.localStorage.getItem("copycat-fut-product")).toBe("MXF");
  });
});

// 🟢 localStorage key 收斂:主圖標的 key 補上 `copycat-` 前綴後的遷移路徑,
// 以及停用功能孤兒鍵的啟動清除。key 字面值刻意寫死(只 import 受測函式,不 import
// key 常數)—— 這幾條測的就是「key 值本身」,跟著常數走會讓改錯 key 值時測試一起變綠。
describe("App localStorage key 遷移 / 孤兒清除", () => {
  it("新 key 有值時優先採用,不被舊 key 的殘值蓋回去", async () => {
    window.localStorage.setItem("copycat-stock-main-code", "2454");
    window.localStorage.setItem("stock-main-code", "2330");
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "個股(期)" }));
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
        String(c[0]),
      );
      expect(calls.some((u) => u.includes("/api/stock/state/2454"))).toBe(true);
    });
  });

  it("只有舊 key 有值 → 搬到新 key 且舊 key 被移除(一次性遷移)", () => {
    window.localStorage.setItem("stock-main-code", "2330");
    renderApp();
    expect(window.localStorage.getItem("copycat-stock-main-code")).toBe("2330");
    expect(window.localStorage.getItem("stock-main-code")).toBeNull();
  });

  it("新舊都有值 → 採新值,舊 key 照樣被清掉(雙分頁升版會把舊 key 寫回)", () => {
    window.localStorage.setItem("copycat-stock-main-code", "2454");
    window.localStorage.setItem("stock-main-code", "2330");
    renderApp();
    expect(window.localStorage.getItem("copycat-stock-main-code")).toBe("2454");
    expect(window.localStorage.getItem("stock-main-code")).toBeNull();
  });

  // 孤兒清除是 module scope 的一次性副作用,直接單元測 `purgeOrphanKeys()` ——
  // 用 `vi.resetModules()` + 動態 import 重跑 App 模組會讓這條依賴 module registry
  // 的重置順序,脆得沒必要。「App.tsx 頂層有呼叫」這件事由該檔的一行呼叫負責,
  // 行為則由本單元測試 + 真環境驗證共同守住。
  it("purgeOrphanKeys 清掉孤兒鍵(停用功能 + 2026-08-14 收合殼四支 + 2026-08-16 退役的 subtab 鍵)", () => {
    const orphans = [
      "stock-ladder-open",
      "stock-wl-group",
      "copycat-corr-open",
      "copycat-limit-list-open",
      "copycat-sector-open",
      "copycat-signal-timeline-open",
      "copycat-index-subtab",
    ];
    for (const key of orphans) window.localStorage.setItem(key, "1");
    purgeOrphanKeys();
    for (const key of orphans) expect(window.localStorage.getItem(key)).toBeNull();
    // 活鍵不得被順手清掉(漲跌停列表的篩選偏好在改版後照樣天天讀寫)
    window.localStorage.setItem("copycat-limit-list-filter", "{}");
    purgeOrphanKeys();
    expect(window.localStorage.getItem("copycat-limit-list-filter")).toBe("{}");
  });
});

// 🟢 版本落差膠囊的**落點**(SC-4 / design R4):元件自身行為在
// VersionDriftBadge.test.tsx,這裡只驗「在 nav 列內、在 IndexBar 左邊」。
describe("App 版本落差膠囊落點(SC-4)", () => {
  function nav() {
    return screen.getByRole("tablist", { name: "主要分頁" });
  }

  it("落差態:膠囊在 nav 內、與 IndexBar 同在單一 ml-auto 容器,且排在其左", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("fetch", appFetch({ fe: "aaaaaaa", be: "bbbbbbb", behind: true }));
    renderApp();
    const badge = await within(nav()).findByTestId("version-drift-badge");
    // R4:推到右側的 ml-auto 必須在**共用 wrapper** 上,不能膠囊自己帶一個 ——
    // 兩個 ml-auto 會平分剩餘空間,把膠囊卡在 nav 中段。
    const wrapper = badge.parentElement!;
    expect(wrapper).not.toBe(nav());
    expect(wrapper.className).toContain("ml-auto");
    expect(badge.className).not.toContain("ml-auto");
    expect(badge.nextElementSibling?.textContent).toContain("加權");
  });

  it("健康態(behind=false):nav 內零膠囊", async () => {
    vi.stubGlobal("fetch", appFetch({ fe: "aaaaaaa", be: "aaaaaaa", behind: false }));
    renderApp();
    // 負例 settle 點:等 health 真的打過再把 promise chain 排乾
    await waitFor(() =>
      expect(
        (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.some((c) =>
          String(c[0]).includes("/api/health"),
        ),
      ).toBe(true),
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(within(nav()).queryByTestId("version-drift-badge")).toBeNull();
  });
});

// 🟢 stock-signals T11(SC-10):toast 掛在 App 層,與當前 tab 無關 ——
// 訊號涵蓋整個自選池,人在看台股綜合 / 期貨時個股鎖漲停一樣要跳出來。
describe("App 訊號 toast(SC-10)", () => {
  function sig(id: string, code: string): SignalMsg {
    return {
      type: "signal",
      id,
      kind: "limit_lock",
      code,
      name: "國巨",
      price: 5_000_000,
      time: "10:03:11",
      levels: [],
      direction: "up",
      pct: null,
      touch_count: 1,
    };
  }

  it("預設 tab(台股綜合)收到訊號 → toast 出現", async () => {
    renderApp();
    act(() => emitSignal(sig("a", "2327")));
    const stack = await screen.findByTestId("toast-stack");
    expect(stack.textContent).toContain("2327");
    expect(stack.textContent).toContain("鎖漲停");
  });

  it("切到期貨 tab 後照樣跳 toast(跨 tab 常駐)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "期貨" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "大台" })).toBeTruthy());
    act(() => emitSignal(sig("b", "2327")));
    const stack = await screen.findByTestId("toast-stack");
    expect(stack.textContent).toContain("鎖漲停");
  });

  it("沒有訊號時不掛空容器(fixed 空盒子會壓住右上角元件)", () => {
    renderApp();
    expect(screen.queryByTestId("toast-stack")).toBeNull();
  });
});

// 🟢 stkfut-contracts SC-4:合約選擇的狀態持有者是 App(D5)。
// 兩件事只有在這一層測得到,而兩者失效都極安靜:
//   (a) 換股沒重置 → 新股的 REST 帶著舊股的合約 → 後端 D7 白名單 400,畫面停在載入中;
//   (b) railCtx.code 若改塞 instrument key → 右欄下單面顯示 `F:CDF:202609` 且五檔
//       點價 gate(比對 detail.code === ctx.code)整條失效。
describe("App 個股期合約選擇(SC-4)", () => {
  const CONTRACTS = {
    code: "2330",
    name: "台積電",
    std: { prod: "CDF", contracts: ["202608", "202609"] },
    mini: { prod: "QFF", contracts: ["202608", "202609"] },
  };

  function snapshot(code: string) {
    return {
      code,
      seq: 1,
      last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
      vwap: 2_380_000,
      minutes: {},
      ticks: [],
      book: { bids: [[2_375_000, 5]], asks: [[2_380_000, 3]] },
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
      no_data: false,
    };
  }

  function stockFetch() {
    return vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/index/state")) return new Response(JSON.stringify(INDEX_STATE));
      if (u.includes("/api/health")) {
        return new Response(JSON.stringify({ git_sha: null, git_dirty: false }));
      }
      if (u.includes("/__build/sha")) {
        return new Response(JSON.stringify({ git_sha: null, behind: null }));
      }
      if (u.includes("/api/stock/stkfut/contracts/2330")) {
        return new Response(JSON.stringify(CONTRACTS));
      }
      if (u.includes("/api/stock/stkfut/contracts/")) {
        return new Response(JSON.stringify({ detail: { error: "NO_STKFUT" } }), { status: 404 });
      }
      if (u.includes("/api/stock/watchlist")) {
        return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330", "2454"] }] }));
      }
      if (u.includes("/api/stock/state/")) {
        const code = u.slice("/api/stock/state/".length).split("?")[0] ?? "2330";
        return new Response(JSON.stringify(snapshot(code)));
      }
      if (u.includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: [], status: "ok" }));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    });
  }

  function stateUrls(): string[] {
    return (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.startsWith("/api/stock/state/"));
  }

  async function openStockWithContract() {
    // 右欄閃電梯掛載即置中;jsdom 無 scrollIntoView(同 PriceLadder.test / RightRail.test)
    Element.prototype.scrollIntoView = vi.fn();
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "2330");
    vi.stubGlobal("fetch", stockFetch());
    renderApp();
    const select = await screen.findByLabelText("合約");
    fireEvent.change(select, { target: { value: "CDF:202609" } });
    await waitFor(() =>
      expect(stateUrls().includes("/api/stock/state/2330?contract=CDF:202609")).toBe(true),
    );
  }

  it("換股重置合約:新股的 snapshot 不帶舊合約", async () => {
    await openStockWithContract();
    fireEvent.click(screen.getByTestId("wl-row-2454"));
    await waitFor(() => expect(stateUrls().includes("/api/stock/state/2454")).toBe(true));
    // 重置若走 effect 而非 render 期間,會先有一個 render 拿新股號配舊合約送出去
    expect(stateUrls().some((u) => u.startsWith("/api/stock/state/2454?"))).toBe(false);
    // 下拉本身也要回到「現貨」(2454 無期貨 → 連下拉都不該在)
    await waitFor(() => expect(screen.queryByLabelText("合約")).toBeNull());
  });

  it("railCtx.code 恆為股號(期貨態右欄仍指認 2330,不是 instrument key)", async () => {
    await openStockWithContract();
    const rail = screen.getByRole("complementary", { name: "交易面板" });
    expect(rail.textContent).toContain("2330");
    expect(rail.textContent).not.toContain("F:CDF");
  });
});
