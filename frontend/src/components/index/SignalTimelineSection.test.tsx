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
import { SIGNAL_TIMELINE_OPEN_KEY } from "@/lib/constants";
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

/** 直接以「已展開」開場(收合閘門另有專測),等 baseline 落地後回傳。 */
async function openWith(
  signals: SignalMsg[] = [],
  onOpenStock?: (code: string) => void,
): Promise<void> {
  window.localStorage.setItem(SIGNAL_TIMELINE_OPEN_KEY, "1");
  stubFetch(signals);
  renderSection(onOpenStock);
  await screen.findByTestId("signal-timeline-body");
  await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(0));
}

function header(): HTMLElement {
  return screen.getByRole("button", { name: /訊號時間軸/ });
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

describe("SignalTimelineSection 收合閘門", () => {
  it("預設收合:body 不 mount、零 fetch", async () => {
    renderSection();
    await waitFor(() => expect(header().getAttribute("aria-expanded")).toBe("false"));
    expect(screen.queryByTestId("signal-timeline-body")).toBeNull();
    expect(fetchMock.mock.calls.length).toBe(0);
  });

  it("展開寫入 localStorage,重新 mount 仍展開", async () => {
    renderSection();
    fireEvent.click(header());
    await screen.findByTestId("signal-timeline-body");
    expect(window.localStorage.getItem(SIGNAL_TIMELINE_OPEN_KEY)).toBe("1");
    expect(header().getAttribute("aria-expanded")).toBe("true");

    cleanup();
    renderSection();
    expect(await screen.findByTestId("signal-timeline-body")).toBeTruthy();
  });

  it("收合把 body unmount 並寫回 0", async () => {
    await openWith([sig({ id: "a" })]);
    await screen.findByTestId("signal-timeline-row-a");

    fireEvent.click(header());

    expect(screen.queryByTestId("signal-timeline-body")).toBeNull();
    expect(screen.queryByTestId("signal-timeline-row-a")).toBeNull();
    expect(window.localStorage.getItem(SIGNAL_TIMELINE_OPEN_KEY)).toBe("0");
    expect(header().getAttribute("aria-expanded")).toBe("false");
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
