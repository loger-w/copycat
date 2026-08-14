/** @vitest-environment jsdom */
/** 訊號時間軸區塊(market-overview R4 SC-7;design §9.2)。
 *
 *  這裡鎖的是「一條軸看得到兩族訊號」:自選池的 tick 級訊號與全市場廣度事件同軸,
 *  但廣度列必須自我標示(精度 5-10s,不是 tick 級)—— 兩者外觀相同時,使用者會拿
 *  快照級的時刻去推敲秒級的因果。
 *
 *  **分族擠壓案是本檔的核心**(SC-7/SC-8 對稱):漲停潮日一分鐘湧進上百則 market
 *  事件,自選那幾則若被擠出 feed,chip 切回「鎖板(自選)」就會是空的 —— 而畫面上
 *  看起來只是「今天自選沒訊號」。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignalTimelineSection } from "@/components/index/SignalTimelineSection";
import { emitSignal } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";

function sig(over: Partial<SignalMsg> & { id: string }): SignalMsg {
  return {
    type: "signal",
    kind: "surge",
    code: "2330",
    name: "台積電",
    price: 1_234_500,
    time: "09:15:03",
    levels: [],
    direction: null,
    pct: 1.5,
    touch_count: 1,
    ...over,
  };
}

function mkt(over: Partial<SignalMsg> & { id: string }): SignalMsg {
  return sig({
    kind: "market_limit_lock",
    code: "1101",
    name: "台泥",
    direction: "up",
    pct: null,
    time: "09:30:00",
    ...over,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

/** 後端 `GET /api/stock/signals/today` 回 jsonl 順序 = **舊在前**。 */
function stubFetch(signals: SignalMsg[]): void {
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ signals })));
  vi.stubGlobal("fetch", fetchMock);
}

function renderSection(onOpenStock?: (code: string) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SignalTimelineSection onOpenStock={onOpenStock} />
    </QueryClientProvider>,
  );
}

/** render 即掛載(subtab 改版後本元件不再有收合殼),等 baseline 落地後回傳。 */
async function openWith(
  signals: SignalMsg[] = [],
  onOpenStock?: (code: string) => void,
): Promise<void> {
  stubFetch(signals);
  renderSection(onOpenStock);
  await screen.findByTestId("signal-timeline-body");
  await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(0));
}

function rowIds(): string[] {
  return screen
    .queryAllByTestId(/^signal-timeline-row-/)
    .map((el) => el.getAttribute("data-testid")!.replace("signal-timeline-row-", ""));
}

function chip(key: string): HTMLElement {
  return screen.getByTestId(`signal-timeline-chip-${key}`);
}

beforeEach(() => {
  window.localStorage.clear();
  stubFetch([]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// 🔴 2026-08-14 subtab 改版:收合殼卸掉(掛載閘上移到 IndexPage 的 subtab 列)。
// 本元件**刻意沒有** `active` gate(一次性 query + WS bus,沒有輪詢可停)—— 這件事
// 不因 subtab 改版而變。
describe("SignalTimelineSection 掛載即工作(subtab 改版)", () => {
  it("render 即掛 body 並取 baseline(無收合鈕)", async () => {
    renderSection();
    expect(await screen.findByTestId("signal-timeline-body")).toBeTruthy();
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: /展開|收合/ })).toBeNull();
  });

  it("零 OPEN_KEY 讀寫(廢止的鍵不得留旁路)", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderSection();
    await screen.findByTestId("signal-timeline-body");

    const keys = [...getItem.mock.calls, ...setItem.mock.calls].map((c) => String(c[0]));
    expect(keys).not.toContain("copycat-signal-timeline-open");
    getItem.mockRestore();
    setItem.mockRestore();
  });
});

describe("SignalTimelineSection 列渲染", () => {
  it("時間倒序(baseline 舊在前 → 畫面新在前)", async () => {
    await openWith([
      sig({ id: "old", time: "09:10:00" }),
      sig({ id: "mid", time: "09:20:00" }),
      sig({ id: "new", time: "09:30:00" }),
    ]);
    await screen.findByTestId("signal-timeline-row-new");
    expect(rowIds()).toEqual(["new", "mid", "old"]);
  });

  it("每列 = 時刻 + 代號 + 名稱 + kindLabel 文案", async () => {
    await openWith([
      sig({ id: "s1", kind: "surge", pct: 2.25, time: "10:05:11" }),
      sig({
        id: "s2",
        kind: "cdp_cross",
        code: "2317",
        name: "鴻海",
        levels: ["ah"],
        direction: "from_below",
        pct: null,
        time: "10:06:00",
      }),
    ]);
    const r1 = await screen.findByTestId("signal-timeline-row-s1");
    expect(r1.textContent).toContain("10:05:11");
    expect(r1.textContent).toContain("2330");
    expect(r1.textContent).toContain("台積電");
    expect(r1.textContent).toContain("爆拉 +2.25%");

    const r2 = screen.getByTestId("signal-timeline-row-s2");
    expect(r2.textContent).toContain("2317");
    expect(r2.textContent).toContain("鴻海");
    expect(r2.textContent).toContain("突破 CDP AH");
  });

  it("market 列帶「廣度」badge(title 註記精度),自選列沒有", async () => {
    await openWith([
      sig({ id: "own", kind: "limit_lock", direction: "up", pct: null, time: "09:40:00" }),
      mkt({ id: "m1", time: "09:41:00" }),
    ]);
    const badge = await screen.findByTestId("signal-timeline-badge-m1");
    expect(badge.textContent).toBe("廣度");
    expect(badge.getAttribute("title")).toBe("FinMind 快照精度 5-10s,非 tick 級");
    // 文案與後端 `_kind_text` 逐字對齊
    expect(screen.getByTestId("signal-timeline-row-m1").textContent).toContain("全市場鎖漲停");

    expect(screen.queryByTestId("signal-timeline-badge-own")).toBeNull();
    expect(screen.getByTestId("signal-timeline-row-own").textContent).toContain("鎖漲停");
  });

  it("自選 + market 同軸:兩族都渲染(SC-7)", async () => {
    await openWith([
      sig({ id: "own-1", time: "09:20:01" }),
      mkt({ id: "m-1", time: "09:21:00" }),
    ]);
    await screen.findByTestId("signal-timeline-row-m-1");
    expect(rowIds()).toEqual(["m-1", "own-1"]);
  });

  it("列點擊 → onOpenStock(廣度→深度銜接)", async () => {
    const onOpenStock = vi.fn();
    await openWith([mkt({ id: "m-1" })], onOpenStock);
    fireEvent.click(await screen.findByTestId("signal-timeline-row-m-1"));
    expect(onOpenStock.mock.calls).toEqual([["1101"]]);
  });
});

describe("SignalTimelineSection kind chips", () => {
  const MIXED = [
    sig({
      id: "cdp-1",
      kind: "cdp_cross",
      levels: ["cdp"],
      direction: "from_below",
      pct: null,
      time: "09:01:00",
    }),
    sig({ id: "surge-1", kind: "surge", time: "09:02:00" }),
    sig({ id: "crash-1", kind: "crash", pct: -3.1, time: "09:03:00" }),
    sig({ id: "vol-1", kind: "vol_burst", pct: 4.2, time: "09:04:00" }),
    sig({ id: "lock-1", kind: "limit_lock", direction: "up", pct: null, time: "09:05:00" }),
    sig({ id: "open-1", kind: "limit_open", direction: "up", pct: null, time: "09:06:00" }),
    mkt({ id: "mk-1", time: "09:07:00" }),
    mkt({ id: "mk-2", kind: "market_limit_open", time: "09:08:00" }),
  ];

  it("預設「全部」:兩族全列", async () => {
    await openWith(MIXED);
    await screen.findByTestId("signal-timeline-row-mk-2");
    expect(rowIds().length).toBe(8);
    expect(chip("all").getAttribute("aria-pressed")).toBe("true");
  });

  it("選「全市場鎖板」→ 只剩 market 兩列", async () => {
    await openWith(MIXED);
    await screen.findByTestId("signal-timeline-row-mk-2");
    fireEvent.click(chip("market"));
    expect(rowIds()).toEqual(["mk-2", "mk-1"]);
    expect(chip("market").getAttribute("aria-pressed")).toBe("true");
    expect(chip("all").getAttribute("aria-pressed")).toBe("false");
  });

  it("選「CDP」→ 只剩 cdp 列", async () => {
    await openWith(MIXED);
    await screen.findByTestId("signal-timeline-row-mk-2");
    fireEvent.click(chip("cdp"));
    expect(rowIds()).toEqual(["cdp-1"]);
  });

  it("chip 群組:爆拉跌 = surge+crash、爆量 = vol_burst、鎖板(自選)= limit_lock+limit_open", async () => {
    await openWith(MIXED);
    await screen.findByTestId("signal-timeline-row-mk-2");

    fireEvent.click(chip("move"));
    expect(rowIds()).toEqual(["crash-1", "surge-1"]);

    fireEvent.click(chip("vol"));
    expect(rowIds()).toEqual(["vol-1"]);

    fireEvent.click(chip("lock"));
    expect(rowIds()).toEqual(["open-1", "lock-1"]);
  });

  // (review round-2 FE-5)design §9.3 的驗收明文是「chip 切『自選』…見 3 則」,
  // 但 §9.2 的 chip 列表漏列這一顆,實作照 §9.2 就少做了。少了它,想「只看自選」
  // 唯一的辦法是逐 kind 點過去 —— 而 kind 是會增加的,漏一顆就靜默看不到。
  it("選「自選」→ 只剩自選族(kind 各異一起收,market 族全不見)", async () => {
    await openWith(MIXED);
    await screen.findByTestId("signal-timeline-row-mk-2");
    fireEvent.click(chip("own"));
    expect(rowIds()).toEqual(["open-1", "lock-1", "vol-1", "crash-1", "surge-1", "cdp-1"]);
    expect(chip("own").getAttribute("aria-pressed")).toBe("true");
  });

  // 族層(全部 / 自選)與 kind 層分開擺:「自選」問的是「這則跟我有關嗎」,
  // 「CDP」問的是「這是哪種訊號」,兩個問題混排會讓人以為它們互斥。
  it("chip 順序:自選夾在「全部」與 kind 層之間", async () => {
    await openWith(MIXED);
    expect(
      screen.getAllByTestId(/^signal-timeline-chip-/).map((el) => el.textContent),
    ).toEqual(["全部", "自選", "CDP", "爆拉跌", "爆量", "鎖板(自選)", "全市場鎖板"]);
  });

  // SC-7/SC-8 對稱:market 族擠爆時,自選那幾則必須還在 feed 裡(分族 cap),
  // 而且 chip 切過去看得到 —— 少了任一半,畫面上都是「今天自選沒訊號」。
  it("分族擠壓:250 則 market + 3 則自選 → 切「鎖板(自選)」仍見 3 則", async () => {
    await openWith([]);
    act(() => {
      for (let i = 0; i < 250; i += 1) emitSignal(mkt({ id: `m${i}`, time: "09:31:00" }));
      emitSignal(sig({ id: "own-1", kind: "limit_lock", direction: "up", pct: null, time: "09:20:01" }));
      emitSignal(sig({ id: "own-2", kind: "limit_lock", direction: "up", pct: null, time: "09:20:02" }));
      emitSignal(sig({ id: "own-3", kind: "limit_lock", direction: "up", pct: null, time: "09:20:03" }));
    });

    await waitFor(() => expect(rowIds().length).toBeGreaterThan(3));
    fireEvent.click(chip("lock"));
    expect(rowIds()).toEqual(["own-3", "own-2", "own-1"]);
  });

  // design §9.3 的驗收原文就是這一句(「『自選』chip 見 3 則」):三則 kind 各異,
  // 靠 kind 層 chip 一顆都收不齊,只有族層那顆做得到。
  it("分族擠壓:250 則 market + 3 則 kind 各異的自選 → 切「自選」見 3 則", async () => {
    await openWith([]);
    act(() => {
      for (let i = 0; i < 250; i += 1) emitSignal(mkt({ id: `m${i}`, time: "09:31:00" }));
      emitSignal(sig({ id: "own-1", kind: "surge", time: "09:20:01" }));
      emitSignal(sig({ id: "own-2", kind: "vol_burst", pct: 4.2, time: "09:20:02" }));
      emitSignal(
        sig({ id: "own-3", kind: "limit_lock", direction: "up", pct: null, time: "09:20:03" }),
      );
    });

    await waitFor(() => expect(rowIds().length).toBeGreaterThan(3));
    fireEvent.click(chip("own"));
    expect(rowIds()).toEqual(["own-3", "own-2", "own-1"]);
  });
});

describe("SignalTimelineSection 空態", () => {
  it("今日零訊號 → 今日尚無訊號", async () => {
    await openWith([]);
    await waitFor(() =>
      expect(screen.getByTestId("signal-timeline-msg").textContent).toBe("今日尚無訊號"),
    );
    expect(screen.queryAllByTestId(/^signal-timeline-row-/).length).toBe(0);
  });

  it("有訊號但選中 chip 無事件 → 無符合條件(與「今日尚無訊號」分開)", async () => {
    await openWith([sig({ id: "s1", kind: "surge" })]);
    await screen.findByTestId("signal-timeline-row-s1");
    fireEvent.click(chip("market"));
    expect(screen.getByTestId("signal-timeline-msg").textContent).toBe("無符合條件");
  });
});

// (review round-2 FE-1 / XR-3)達錢 4 沒開時 `/api/stock/signals/today` 回 503,
// 而「baseline 抓不到」與「今天真的沒訊號」在畫面上完全同形 —— 使用者看到「今日尚無
// 訊號」不會去查服務,只會以為今天很安靜。這一組鎖的是「降級說得出口」。
describe("SignalTimelineSection baseline 取數失敗", () => {
  /** baseline 端點 503(hub 未就緒)。retry: 1 是 hook 內建 → 要等第二次 fetch。 */
  async function openWith503(): Promise<void> {
    fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderSection();
    await screen.findByTestId("signal-timeline-body");
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2), {
      timeout: 5_000,
    });
  }

  it("零訊號 + 取數失敗 → 說是失敗,不是「今日尚無訊號」", async () => {
    await openWith503();
    await waitFor(
      () =>
        expect(screen.getByTestId("signal-timeline-msg").textContent).toBe(
          "訊號服務未就緒或取數失敗(即時訊號仍會顯示)",
        ),
      { timeout: 5_000 },
    );
  });

  it("取數失敗但已有 live 訊號 → 清單照畫,頂部加一行「僅顯示即時訊號」提示", async () => {
    await openWith503();
    act(() => emitSignal(sig({ id: "live-1", time: "09:45:00" })));

    await waitFor(() => expect(rowIds()).toEqual(["live-1"]));
    expect(screen.queryByTestId("signal-timeline-msg")).toBeNull();
    await waitFor(() =>
      expect(screen.getByTestId("signal-timeline-baseline-error").textContent).toBe(
        "歷史訊號載入失敗,僅顯示即時訊號",
      ),
    );
  });

  it("取數成功 → 無失敗提示(不誤報)", async () => {
    await openWith([sig({ id: "s1" })]);
    await screen.findByTestId("signal-timeline-row-s1");
    expect(screen.queryByTestId("signal-timeline-baseline-error")).toBeNull();
  });
});
