/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStockStream } from "@/hooks/useStockStream";
import { onSignal, onWsOpen } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import type { StkfutSelection } from "@/lib/stkfut";

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

  emit(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

function snap(seq: number, ticks: { t: string; p: number; q: number; side: string }[]) {
  return {
    code: "2330",
    seq,
    last: ticks.length
      ? { p: ticks[ticks.length - 1]!.p, t: ticks[ticks.length - 1]!.t, cum_vol: seq }
      : null,
    vwap: null,
    minutes: {},
    ticks,
    book: null,
    meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: null },
    no_data: false,
  };
}

const T = (seq: number) => ({
  type: "tick", code: "2330", t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq,
});

let fetchMock: ReturnType<typeof vi.fn>;
let queryClient: QueryClient;

/** `.ts` 檔不能寫 JSX(impl-review R12:沿用本檔 fake WS harness 不新建 .tsx),
 *  故 provider 用 createElement 包。hook 內 `useQueryClient()` 沒 provider 會直接拋。 */
function wrapper({ children }: { children: ReactNode }) {
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

/** 全站 main.tsx 是包在 `<StrictMode>` 下的 —— dev 會 double-invoke updater 與 effect。
 *  其餘測試不套是為了維持單發語意(訊息數、WS instance 數都好數),只有「副作用不可
 *  寫在 updater 內」「旗標不可跨 socket 世代」這兩條需要真的重現正式環境的雙發。
 *
 *  **必須走 RTL 的 `reactStrictMode` option,不可自己寫一個回傳 `<StrictMode>` 的
 *  wrapper 元件**:後者的 StrictMode 是在 wrapper **render 當中**才產生的,React 不會
 *  對它做 mount→cleanup→mount 的模擬 —— 實測 effect 只跑一次(`["setup"]`),
 *  而 option 版是 `["setup","cleanup","setup"]`。掛錯的話測試照樣全綠,只是「StrictMode
 *  下……」的那些斷言全部退化成單發語意的重複驗證。 */
const STRICT = { wrapper, reactStrictMode: true } as const;

beforeEach(() => {
  FakeWS.instances = [];
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify(snap(1, [{ t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" }]))));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  // 用了 fake timers 的測試不還原會外溢到別檔(skill frontend-testing)
  vi.useRealTimers();
});

async function setup() {
  const hook = renderHook(() => useStockStream("2330"), { wrapper });
  await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  return { hook, ws };
}

describe("useStockStream", () => {
  it("初始 fetch snapshot 建立 accum", async () => {
    const { hook } = await setup();
    expect(fetchMock).toHaveBeenCalledWith("/api/stock/state/2330");
    expect(hook.result.current.accum?.seq).toBe(1);
    expect(hook.result.current.accum?.ticks.length).toBe(1);
  });

  it("連續 seq 的 tick 直接累算", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit(T(2)));
    expect(hook.result.current.accum?.seq).toBe(2);
    expect(hook.result.current.accum?.ticks.length).toBe(2);
  });

  it("seq 跳號觸發 refetch,交錯訊息無重複無漏(對齊規則 seq ≤ S 丟棄)", async () => {
    const { hook, ws } = await setup();
    // refetch 會回 seq=5 的 snapshot(含 4 筆)
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(T(4))); // 1→4 跳號(漏 2,3)→ refetch
    // refetch 期間交錯:seq 5(> S 不該丟)與 seq 3(≤ S 該丟)
    act(() => ws.emit(T(5)));
    act(() => ws.emit(T(3)));
    act(() => {
      resolveRefetch(new Response(JSON.stringify(snap(4, [
        { t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" },
        { t: "09:01:00.000", p: 2_375_000, q: 1, side: "outer" },
        { t: "09:02:00.000", p: 2_380_000, q: 1, side: "outer" },
        { t: "09:03:00.000", p: 2_380_000, q: 1, side: "outer" },
      ]))));
    });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(5));
    // snapshot 4 筆 + 交錯倖存 1 筆(seq 5);seq 3 被丟
    expect(hook.result.current.accum?.ticks.length).toBe(5);
  });

  // 🔴 F-2:`tick` 有兩道時序保護(refetch 中進 pendingRef、重放只收 seq > snap.seq),
  // `book` 一道都沒有 —— t0 發 fetch(後端在那一刻凍結簿)→ t0+δ 新簿推播套用 →
  // t0+Δ snapshot 回來整份覆蓋,**新簿被較舊的 snapshot 回捲**。鎖板 / 盤後推播稀疏時
  // 回捲窗可達數十秒,而五檔、鎖停 badge、量 bar 的分母會一起退回舊值,零錯誤訊號。
  it("refetch in-flight 期間的 book 推播不被較舊的 snapshot 回捲(F-2)", async () => {
    const { hook, ws } = await setup();
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(T(4))); // 1→4 跳號 → refetch(fetch 已送出 = 後端簿已凍結)
    // fetch 送出**之後**才到的新簿:方向恆定(推播必晚於 fetch 發起)
    act(() => ws.emit({ type: "book", code: "2330", bids: [[2_379_000, 9]], asks: [[2_381_000, 4]] }));
    act(() => {
      resolveRefetch(new Response(JSON.stringify({
        ...snap(4, [{ t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" }]),
        // snapshot 帶的是**凍結當下**的舊簿
        book: { bids: [[2_370_000, 1]], asks: [[2_371_000, 1]] },
      })));
    });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(4));
    expect(hook.result.current.accum?.book?.bids).toEqual([[2_379_000, 9]]);
    expect(hook.result.current.accum?.book?.asks).toEqual([[2_381_000, 4]]);
  });

  it("refetch 期間無 book 推播 → snapshot 的簿原樣採用(F-2 不誤留舊 pending)", async () => {
    const { hook, ws } = await setup();
    // 先讓一則 book 進 accum,再跑一次「期間無推播」的 refetch
    act(() => ws.emit({ type: "book", code: "2330", bids: [[2_379_000, 9]], asks: [[2_381_000, 4]] }));
    expect(hook.result.current.accum?.book?.bids).toEqual([[2_379_000, 9]]);
    fetchMock.mockImplementationOnce(
      async () => new Response(JSON.stringify({
        ...snap(4, [{ t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" }]),
        book: { bids: [[2_360_000, 2]], asks: [[2_361_000, 2]] },
      })),
    );
    act(() => ws.emit(T(4)));
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(4));
    expect(hook.result.current.accum?.book?.bids).toEqual([[2_360_000, 2]]);
  });

  it("切檔撞上 in-flight refetch 不被吞(CR1:合併不丟棄)", async () => {
    let resolveFirst: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveFirst = res; }),
    );
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
      wrapper,
    });
    // 2330 的 fetch in-flight 中切到 5483
    hook.rerender({ c: "5483" });
    act(() => {
      resolveFirst(new Response(JSON.stringify(snap(1, []))));
    });
    // 舊結果作廢後必須補發新檔 fetch(修前:單飛旗標把 5483 的需求吞掉)
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/stock/state/5483")).toBe(true),
    );
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
  });

  it("status 訊息更新 tc4 狀態;backfilling 完成觸發 refetch", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "status", tc4: "down", backfilling: null }));
    expect(hook.result.current.status.tc4).toBe("down");
    const calls = fetchMock.mock.calls.length;
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: "2330" }));
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: null }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(calls));
  });

  // 🔴 F-1:`refetch()` 是副作用,不可寫在 `setStatus` 的 updater 內 —— React 的 updater
  // 契約是純函式,而全站包在 StrictMode(main.tsx)下 dev 會 double-invoke:第一次進
  // 單飛分支(refetchingRef=true),第二次撞上 in-flight → pendingRefetchRef=true,
  // finally 的「合併不丟棄」語意再補發一次真的 fetch。每次回補完成都串行多打一份
  // MB 級 snapshot(後端 `_TICKS_MAXLEN=20_000`)。
  //
  // 上一條測試只鎖了「有打」的下界(`toBeGreaterThan`),打幾次不管 —— 這正是本條要補的。
  it("回補完成的 refetch 恰一次(StrictMode 下 updater 被 double-invoke)", async () => {
    const hook = renderHook(() => useStockStream("2330"), STRICT);
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    // StrictMode 的 effect double-invoke 會建兩條 FakeWS(第一條已在 cleanup 關掉)
    expect(FakeWS.instances.length).toBe(2);
    const ws = FakeWS.instances[FakeWS.instances.length - 1]!;
    const before = fetchMock.mock.calls.length;
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: "2330" }));
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: null }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    // 上界:finally 的補發是非同步的,要等它有機會發生才算數
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(fetchMock.mock.calls.length).toBe(before + 1);
    expect(hook.result.current.status.backfilling).toBeNull();
  });

  it("watchlist_quote 更新側欄報價(含 no_data)", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "watchlist_quote", code: "5483", p: 216_500, chg_pct: -1.2, vol: 100, no_data: false }));
    act(() => ws.emit({ type: "watchlist_quote", code: "9999", p: null, chg_pct: null, vol: null, no_data: true }));
    expect(hook.result.current.watchlist["5483"]?.p).toBe(216_500);
    expect(hook.result.current.watchlist["9999"]?.no_data).toBe(true);
  });

  // round4 項 4(review F4):`ref` 的解析只有這一層測得到 —— 下游的參考價測試都是把
  // quotes 當 props 直接餵元件,繞過 WS 解析,把這行改壞不會有任何測試紅。
  it("watchlist_quote 的 ref 欄位(尚無成交時的參考價)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "9998",
        p: null, chg_pct: null, vol: null, ref: 995_000, no_data: false,
      }),
    );
    expect(hook.result.current.watchlist["9998"]?.ref).toBe(995_000);
    expect(hook.result.current.watchlist["9998"]?.p).toBeNull();
  });

  it("舊後端不發 ref → 降級 null(不是 undefined)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({ type: "watchlist_quote", code: "9997", p: 100_000, chg_pct: 0, vol: 1, no_data: false }),
    );
    expect(hook.result.current.watchlist["9997"]?.ref).toBeNull();
  });

  it("stkfut 訊息更新期現對照", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "stkfut", code: "2330", prod: "CDF", p: 2_398_000, basis: 18_000 }));
    expect(hook.result.current.stkfut?.p).toBe(2_398_000);
    expect(hook.result.current.stkfut?.basis).toBe(18_000);
  });

  // SC-9/10:訊號分發。WS 只有這一條 —— 前端所有訊號消費端(rail / toast / 音效 /
  // Notification)都掛在 bus 上,這層斷掉時它們全部靜默不動且沒有任何錯誤。
  it("signal 訊息轉發訊號 bus(欄位原樣不轉譯)", async () => {
    const got: SignalMsg[] = [];
    const off = onSignal((s) => got.push(s));
    const { ws } = await setup();
    act(() =>
      ws.emit({
        type: "signal", id: "2026-08-04|2330|cdp_cross|ah|1", kind: "cdp_cross",
        code: "2330", name: "台積電", price: 1_234_500, time: "09:15:03",
        levels: ["ah"], direction: "from_below", pct: null, touch_count: 1,
      }),
    );
    off();
    expect(got.length).toBe(1);
    expect(got[0]?.id).toBe("2026-08-04|2330|cdp_cross|ah|1");
    expect(got[0]?.levels).toEqual(["ah"]);
    expect(got[0]?.touch_count).toBe(1);
  });

  // SC-11:自選變更由 Discord /watch 觸發時,前端要自己重抓。invalidate 的註冊點
  // **只有這裡一處**(design §8.1 / impl-review R10)—— 多處註冊會重複 refetch。
  it("watchlist_changed 使自選 query 失效一次", async () => {
    const { ws } = await setup();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => ws.emit({ type: "watchlist_changed" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["stock-watchlist"] });
  });

  // 🔴 F-3:`refetch` 非 2xx 只有一個沒有 else 的 `if (res.ok)`,throw 只 console.warn ——
  // 兩路都不改 accum(留 null)、不設錯誤態、不排重試。而 `accum === null` 時 tick 早退
  // → seq-gap 自癒也是死路,唯一活路是 WS onopen(沒斷線就不會發)。#28 的 `?contract=`
  // 讓 502/503 從正常操作可達 → 畫面釘在「載入中…」直到使用者自己重整。
  //
  // fake timers 下不可用 `waitFor`(vitest 的 fake timers 它偵測不到,會退回真 interval
  // 而 timeout,skill frontend-testing)→ 一律 `advanceTimersByTimeAsync` + 同步斷言。
  it("refetch 503 → backoff 重試,成功後 accum 就緒(F-3)", async () => {
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await act(async () => { ws.onopen?.(); }); // WS open 是排程重試的前置條件之一
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));

    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(
      async () => new Response(JSON.stringify({ detail: { error: "TC4_DOWN" } }), { status: 503 }),
    );
    hook.rerender({ c: "5483" });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.accum).toBeNull(); // 503 → 畫面上就是「載入中…」
    const calls = fetchMock.mock.calls.length;

    // 第一段 backoff = 1s
    await act(async () => { await vi.advanceTimersByTimeAsync(999); });
    expect(fetchMock.mock.calls.length).toBe(calls);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock.mock.calls.length).toBe(calls + 1);
    expect(String(fetchMock.mock.calls[calls]?.[0])).toBe("/api/stock/state/5483");

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.accum).not.toBeNull(); // 自癒,不必使用者重整
  });

  // 同一條的另一半:切檔要取消還沒打出去的重試。沒取消的話舊 timer 到期時 `refetch()`
  // 讀的是**當下**的 ref → 對新標的多打一份全量 snapshot(而且與正牌重試同一 tick)。
  it("切檔取消 pending 重試(1s 後只有新標的自己的那一次)", async () => {
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await act(async () => { ws.onopen?.(); });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));

    vi.useFakeTimers();
    // (a) 2330 的 refetch 失敗 → 排一次重試
    fetchMock.mockImplementationOnce(async () => new Response("{}", { status: 503 }));
    act(() => ws.emit(T(9))); // 跳號 → refetch
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    // (b) 重試到期前切檔,新標的的初次 fetch 也失敗 → 它自己排一次
    fetchMock.mockImplementationOnce(async () => new Response("{}", { status: 503 }));
    hook.rerender({ c: "5483" });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const before = fetchMock.mock.calls.length;

    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(fetchMock.mock.calls.length).toBe(before + 1); // 舊 timer 沒取消 = 這裡變 +2
    expect(String(fetchMock.mock.calls[before]?.[0])).toBe("/api/stock/state/5483");
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.accum).not.toBeNull();
  });

  // 🔴 review A-2:`wsOpenRef` 是**跨 socket 世代共用**的單一旗標,而 `onclose` 把
  // `wsOpenRef.current = false` 寫在 `alive` 早退**之前** —— StrictMode(main.tsx 全站,
  // dev)的 mount→cleanup→mount 下,舊 socket 的 close 事件若晚於新 socket 的 `onopen`
  // 到達,旗標被清成 false 而且**再也回不去**(新 socket 的 onopen 已經發生過了)。
  // 之後 `scheduleRetry` 的第三道檢查永遠早退 → F-3 的自癒在 dev 整條失效,而 dev
  // 正是驗證環境,且零錯誤訊號。
  it("舊 socket 的 onclose 不得清掉新 socket 的 open 旗標(A-2)", async () => {
    const hook = renderHook(() => useStockStream("2330"), STRICT);
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    expect(FakeWS.instances.length).toBe(2); // StrictMode 雙掛:ws1 已 cleanup,ws2 活著
    const ws1 = FakeWS.instances[0]!;
    const ws2 = FakeWS.instances[1]!;
    // 雙掛的補發 refetch 是非同步的,先讓它落地再換 mock(否則 once 被它吃掉)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });

    // 新 socket open → 旗標轉真。用**不同 seq** 的 snapshot 才等得到「真的 settle」:
    // 只等 fetch 呼叫數等不到 setState,是刀鋒時序(A-1 同源)。
    fetchMock.mockImplementationOnce(
      async () => new Response(JSON.stringify(snap(2, [{ t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" }]))),
    );
    await act(async () => { ws2.onopen?.(); });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(2));
    // 舊 socket 的 close 晚到(它那條 effect 早已 cleanup → 該閉包的 alive=false)
    act(() => { ws1.onclose?.(); });

    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(async () => new Response("{}", { status: 503 }));
    act(() => ws2.emit(T(9))); // 跳號 → refetch → 503 → 應排一次重試
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const before = fetchMock.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(fetchMock.mock.calls.length).toBe(before + 1); // 修前:旗標被清 → 一次都不排
  });

  it("WS onopen 發 ws-open 事件(斷線期間漏掉的訊號靠它自癒回補)", async () => {
    let opened = 0;
    const off = onWsOpen(() => (opened += 1));
    const { ws } = await setup();
    act(() => ws.onopen?.());
    off();
    expect(opened).toBe(1);
  });
});

// 🟢 stkfut-contracts SC-4:主圖標的由「股號」推廣為「instrument」。
// 兩個口徑必須分開,混用會靜默壞掉:
//   REST 路徑段**恆為股號**(後端 `_valid_code` 對 `F:CDF:202609` 會 400,且 D7 白名單
//   需要股號才驗得了「這個合約屬於這檔股票」),合約走 query string;
//   WS 比對鍵**恆為 instrument key**(後端推播的 `code` 欄在期貨態是 `F:<prod>:<ym>`)。
describe("useStockStream(合約態:instrument key vs REST 路徑)", () => {
  const C9 = { prod: "CDF", ym: "202609", mini: false, unit: 2000 };
  const FUT_KEY = "F:CDF:202609";
  const FT = (seq: number, code: string) => ({
    type: "tick", code, t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq,
  });

  type Sel = StkfutSelection | null;

  function stateUrls(): string[] {
    return fetchMock.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.startsWith("/api/stock/state/"));
  }

  async function setupFut(initial: Sel = C9) {
    const hook = renderHook(({ c }: { c: Sel }) => useStockStream("2330", c), {
      initialProps: { c: initial },
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    return { hook, ws: FakeWS.instances[0]! };
  }

  it("REST 路徑仍是股號,合約走 ?contract=(路徑段放 key 會被後端 400)", async () => {
    await setupFut();
    expect(stateUrls()).toEqual(["/api/stock/state/2330?contract=CDF:202609"]);
  });

  it("WS 重連(onopen)後的 refetch 仍帶 contract", async () => {
    const { ws } = await setupFut();
    act(() => ws.onopen?.());
    await waitFor(() => expect(stateUrls().length).toBeGreaterThan(1));
    // 「五個 refetch 觸發共用單一 URL helper」的鎖:任何一條漏帶 contract 就會靜默
    // 把畫面拉回現貨資料,而 URL 以外沒有任何訊號。
    expect(stateUrls().every((u) => u.includes("?contract=CDF:202609"))).toBe(true);
  });

  it("切合約不重建 WS,只以新合約重抓 snapshot", async () => {
    const { hook } = await setupFut();
    expect(FakeWS.instances.length).toBe(1);
    hook.rerender({ c: { prod: "CDF", ym: "202610", mini: false, unit: 2000 } });
    await waitFor(() =>
      expect(stateUrls().some((u) => u.endsWith("?contract=CDF:202610"))).toBe(true),
    );
    expect(FakeWS.instances.length).toBe(1);
  });

  it("切回現貨 → URL 不再帶 contract", async () => {
    const { hook } = await setupFut();
    hook.rerender({ c: null });
    await waitFor(() => expect(stateUrls().some((u) => u === "/api/stock/state/2330")).toBe(true));
  });

  it("tick 以 instrument key 比對:股號的推播在合約態被忽略", async () => {
    const { hook, ws } = await setupFut();
    act(() => ws.emit(FT(2, "2330"))); // 現貨腿的 tick(watchlist 仍在推)
    expect(hook.result.current.accum?.seq).toBe(1);
    act(() => ws.emit(FT(2, FUT_KEY)));
    expect(hook.result.current.accum?.seq).toBe(2);
  });

  it("book / stkfut 同樣以 instrument key 比對", async () => {
    const { hook, ws } = await setupFut();
    act(() => ws.emit({ type: "book", code: "2330", bids: [[1, 1]], asks: [[2, 2]] }));
    expect(hook.result.current.accum?.book).toBeNull(); // snapshot 的 book 是 null,沒被現貨腿蓋掉
    act(() => ws.emit({ type: "book", code: FUT_KEY, bids: [[1, 1]], asks: [[2, 2]] }));
    expect(hook.result.current.accum?.book?.bids).toEqual([[1, 1]]);
    act(() => ws.emit({ type: "stkfut", code: FUT_KEY, prod: "CDF", p: 1, basis: null }));
    expect(hook.result.current.stkfut?.prod).toBe("CDF");
  });

  it("backfilling 完成的比對鍵也是 instrument key", async () => {
    const { ws } = await setupFut();
    const before = stateUrls().length;
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: FUT_KEY }));
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: null }));
    await waitFor(() => expect(stateUrls().length).toBeGreaterThan(before));
  });

  // 🔴 code review A2:合約訂上了但 TC4 零推播(過期月 / 不存在的 symbol —— TC4 對它們
  // 照回 `Success: OK`)。engine 的 `_handle_no_data` 對任何 code 都發 `watchlist_quote`,
  // 而側欄只認自選碼 → 沒有這條的話畫面就是一張永遠空著的圖:snapshot 是 set_main 當下
  // 取的(TC4 還沒回答),之後再也沒有東西會把 noData 帶進來。
  it("合約主圖收到自己的 no_data quote → accum.noData 轉真(畫面才印得出「無資料」)", async () => {
    const { hook, ws } = await setupFut();
    expect(hook.result.current.accum?.noData).toBe(false);
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: FUT_KEY,
        p: null, chg_pct: null, vol: null, ref: null, no_data: true,
      }),
    );
    expect(hook.result.current.accum?.noData).toBe(true);
  });

  it("他檔的 no_data quote 不影響主圖(側欄那格照收)", async () => {
    const { hook, ws } = await setupFut();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "9999",
        p: null, chg_pct: null, vol: null, no_data: true,
      }),
    );
    expect(hook.result.current.watchlist["9999"]?.no_data).toBe(true);
    expect(hook.result.current.accum?.noData).toBe(false);
  });

  it("現貨主圖同理(這條路不是期貨態專屬)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: true,
      }),
    );
    expect(hook.result.current.accum?.noData).toBe(true);
  });
});
