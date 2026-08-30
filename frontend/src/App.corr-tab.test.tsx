/** @vitest-environment jsdom */
/** 真身級「相關係數頂層 tab」鎖(R2 SC-1)。
 *
 *  前身是 `IndexPage.corr-lazy.test.tsx`(subtab 時代的「非 corr subtab = 零 WebSocket」),
 *  subtab 退役後掛載閘回到 `App` 的 `visited.corr` + `hidden`,鎖跟著搬到新的掛載點。
 *
 *  **本檔刻意不 mock CorrPage**:stub 不建線,「stub 下 WS 數為 0」恆真 = 沒有鑑別力。
 *  錨點文字固定取 RiverPanel 的「等待各腿資料…」—— App 的 Suspense fallback 與
 *  CorrPanel 空態同為「載入中…」,**不可**用該字串做反向斷言(spec r2: R2-7)。
 *
 *  與 subtab 時代的關鍵行為差異:切走**不** unmount(hidden 保留 DOM),兩條 WS 常駐
 *  —— 與其他三顆 lazy tab 同慣例,也與 R1 前的 corr 頂層 tab 逐字相同。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, configure, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";

// App 級整鏈測試(lazy 頁 + TQ + WS fake)在剛 `npm ci` 的 worktree / 兩個 reviewer 並跑時,`waitFor` / `findBy*`
// 預設 1 s 會被負載打穿(08-30 五次全量各紅 1–4 條、每次不同、單檔重跑全綠;next-time 08-28 L68 / 08-30 節)。
// 拉到 3 s 只是把「等」的上限放寬,斷言本身不變 —— 綠的路徑仍在首輪就 settle,不會多等。
configure({ asyncUtilTimeout: 3000 });

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
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

/** 台股綜合頁的漲跌停列表恆掛(subtab 退役後)→ 這條路由每次都真被打。 */
const BREADTH_ROWS = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [],
};

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/index/state")) return new Response(JSON.stringify(INDEX_STATE));
      if (u.includes("/api/market/breadth/rows")) return new Response(JSON.stringify(BREADTH_ROWS));
      if (u.includes("/api/stock/signals/today")) {
        return new Response(JSON.stringify({ signals: [] }));
      }
      if (u.includes("/api/health")) {
        return new Response(JSON.stringify({ git_sha: null, git_dirty: false }));
      }
      if (u.includes("/__build/sha")) {
        return new Response(JSON.stringify({ git_sha: null, behind: null }));
      }
      // corr / river 兩支 hook 的初載 REST 回 404 → state 維持 null(引擎未就緒的正常降級)
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

/** App 層另有 index / stock / futures / capital / signals 等常駐連線 → 只挑 corr 這兩條。 */
function corrWs(): FakeWS[] {
  return FakeWS.instances.filter((w) => /\/ws\/(corr|river)$/.test(w.url));
}

function corrWsPaths(): string[] {
  return corrWs().map((w) => w.url.replace(/^ws:\/\/[^/]+/, ""));
}

describe("App × CorrPage 頂層 tab(R2 SC-1;lazy 真身)", () => {
  it("沒點相關係數時零 corr WebSocket;點進去才建 corr + river 兩條", async () => {
    renderApp();
    await act(async () => {});

    expect(screen.queryByText("等待各腿資料…")).toBeNull();
    expect(corrWs()).toEqual([]);

    // 正向對照:少了這半,「零 WS」對「corr 整條路徑壞掉」也會綠(vacuous)
    fireEvent.click(screen.getByRole("tab", { name: "相關係數" }));

    expect(await screen.findByText("等待各腿資料…")).toBeTruthy();
    expect(corrWsPaths()).toEqual(["/ws/corr", "/ws/river"]);
  });

  it("切回台股綜合後兩條 WS 仍活著(hidden 保留 DOM,不 unmount)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "相關係數" }));
    await screen.findByText("等待各腿資料…");

    fireEvent.click(screen.getByRole("tab", { name: "台股綜合" }));
    await act(async () => {});

    expect(corrWsPaths()).toEqual(["/ws/corr", "/ws/river"]); // 沒重連,也沒多開
    expect(corrWs().map((w) => w.closed)).toEqual([false, false]);
  });

  it("相關係數 tab 的右欄閃電顯「此頁無可下單標的」(railCtx 落 none)", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("tab", { name: "相關係數" }));
    await screen.findByText("等待各腿資料…");

    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
  });
});
