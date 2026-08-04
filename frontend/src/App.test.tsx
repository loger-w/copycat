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

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/index/state")) {
        return new Response(JSON.stringify(INDEX_STATE));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App(index-board T9)", () => {
  it("無 localStorage 時預設停在「大盤」(index-board SC-1)", () => {
    renderApp();
    expect(screen.getByRole("tab", { name: "大盤" }).getAttribute("aria-selected")).toBe("true");
  });

  it("舊 localStorage 值 txo 仍還原到「選擇權」(backward compat)", () => {
    window.localStorage.setItem("copycat-tab", "txo");
    renderApp();
    expect(screen.getByRole("tab", { name: "選擇權" }).getAttribute("aria-selected")).toBe("true");
  });

  it("nav 有「大盤」tab 且 IndexBar 常駐(切到選擇權 tab 仍可見)", async () => {
    renderApp();
    expect(screen.getByRole("tab", { name: "大盤" })).toBeTruthy();
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
    expect(screen.getByRole("tab", { name: "大盤" }).getAttribute("aria-selected")).toBe("true");
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
  });

  it("切到大盤 tab 顯示 IndexPage(標的列 + 週期列)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "大盤" }));
    // 版面自 index-board SC-2/3 起由「兩張並排卡」改為「標的切換 + 單一主圖」
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
    expect(screen.getByRole("button", { name: "櫃買" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "台指期" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "日K" })).toBeTruthy();
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
  it("nav tab 順序 = 大盤 / 個股(期) / 選擇權 / 期貨 / 相關係數", () => {
    renderApp();
    // 🔴-1:右欄也是 tablist(閃電/委託/部位)→ 全域 getAllByRole("tab") 會撞名,
    // 收斂到 nav。斷言意圖(nav 各 tab 的文字與順序)不變,只有順序與標籤依
    // index-board SC-1 改動(期貨 / 相關係數保留,只是排序在後)。
    const labels = within(screen.getByRole("tablist", { name: "主要分頁" }))
      .getAllByRole("tab")
      .map((el) => el.textContent);
    expect(labels).toEqual(["大盤", "個股(期)", "選擇權", "期貨", "相關係數"]);
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
    fireEvent.click(screen.getByRole("tab", { name: "大盤" }));
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
    expectRail();
  });

  it("TXO / 指數 tab 的閃電 tab 顯示「此頁無可下單標的」(D6)", () => {
    renderApp();
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
  });

  it("nav 有 5 顆 tab、右欄有 3 顆,兩者互不干擾", () => {
    renderApp();
    // 斷言意圖不變(兩個 tablist 各自獨立);nav 由 4 → 5 是 realtime-correlation SC-7
    // 新增「相關係數」分頁的預期行為改變,右欄三顆不受影響。
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
  it("purgeOrphanKeys 清掉孤兒鍵(stock-ladder-open / stock-wl-group)", () => {
    window.localStorage.setItem("stock-ladder-open", "1");
    window.localStorage.setItem("stock-wl-group", "科技股");
    purgeOrphanKeys();
    expect(window.localStorage.getItem("stock-ladder-open")).toBeNull();
    expect(window.localStorage.getItem("stock-wl-group")).toBeNull();
  });
});

// 🟢 stock-signals T11(SC-10):toast 掛在 App 層,與當前 tab 無關 ——
// 訊號涵蓋整個自選池,人在看大盤 / 期貨時個股鎖漲停一樣要跳出來。
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

  it("預設 tab(大盤)收到訊號 → toast 出現", async () => {
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
