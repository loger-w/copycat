/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStockStream, type StockStreamState } from "@/hooks/useStockStream";
import { onSignal, onWsOpen } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import type { StkfutSelection } from "@/lib/stkfut";
import { resetTickStream, setTickView, subscribeTicks } from "@/lib/tick-stream";

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  /** hook 透過 `handle.send()` 真的送出的原文(T3:檢視集合 `view` 訊息) */
  sent: string[] = [];

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  send(data: string): void {
    this.sent.push(data);
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

/** 逐筆自 #180 起只走 0.1 s 打包 `ticks`(單筆 `tick` 退役):一則含多檔多筆 items。
 *  既有案每則一筆,語意(seq 連續 / 跳號 / pending 重放)逐字不動。 */
const T = (seq: number) => ({
  type: "ticks",
  items: [{ code: "2330", t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq }],
});

const TICK1 = { t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" };

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

/** WS 進 open(重試排程的三道前置之一)並**等到它觸發的 refetch 真的落地**。
 *
 *  `waitFor(fetch 呼叫數)` 只等得到「打出去了」,等不到 setState —— 之後 `useFakeTimers()`
 *  一切,還沒 settle 的那條 promise 鏈就被凍在半路,後面的斷言看的是上一輪的畫面
 *  (review A-1:在 fetch mock 裡注入一個 macrotask 即偶紅)。這裡改用**不同 seq**
 *  的 snapshot 當 settle 訊號 —— 等到 `accum.seq` 變才算數,與時序無關。 */
async function openAndSettle(
  hook: { result: { current: StockStreamState } },
  ws: FakeWS,
  seq: number,
): Promise<void> {
  fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(snap(seq, [TICK1]))));
  await act(async () => { ws.onopen?.(); });
  await waitFor(() => expect(hook.result.current.accum?.seq).toBe(seq));
}

/** 推進到下一個重試 timer,回傳它等了多久(fake timers 連 `Date` 一起假造)。
 *  量「間隔」而不是斷言毫秒常數:曲線的性質(遞增 / 有上限 / 成功後歸零)才是行為
 *  合約,`1s→2s→4s cap 8s` 是可調參數,鎖死它等於把 config 寫進測試。 */
async function nextRetryDelay(): Promise<number> {
  const calls = fetchMock.mock.calls.length;
  const t0 = Date.now();
  await act(async () => {
    await vi.advanceTimersToNextTimerAsync();
    await vi.advanceTimersByTimeAsync(0); // 讓 refetch 的 promise 鏈跑完並排下一段
  });
  expect(fetchMock.mock.calls.length).toBe(calls + 1);
  return Date.now() - t0;
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
    // fetch 送出**之後**才到的新簿(近似恆定比 snapshot 新;誤差 = request 單程延遲)
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

  // 🔴 review B-3:這條原本是「先發一則 book(refetching=false),再跑一次期間無推播的
  // refetch」—— 那則 book **從沒進過 `pendingBookRef`**,所以兩處 `= null` 拿掉它照樣綠,
  // 是 vacuous。真正危險的路徑是**跨輪殘留**:第一輪 refetch 期間有簿進了 pending、
  // 該輪卻失敗了,第二輪(重試)期間沒有推播 —— 上一輪的簿若沒被清掉就會蓋掉這一輪
  // 的 snapshot 簿,把畫面推回一個更舊的狀態,而且零錯誤訊號。
  it("失敗重試後的 snapshot 簿不被前一輪的 pending 簿蓋回(F-2 跨輪不殘留)", async () => {
    const hook = renderHook(() => useStockStream("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await openAndSettle(hook, ws, 2); // 重試排程的前置:WS 要 open

    vi.useFakeTimers();
    // refetch#1:in-flight(fetch 已送出 = 後端簿已凍結)期間收到簿 B1 → 進 pending
    let fail: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((r) => { fail = r; }));
    act(() => ws.emit(T(9))); // 跳號 → refetch#1
    act(() => ws.emit({ type: "book", code: "2330", bids: [[2_379_000, 9]], asks: [[2_381_000, 4]] }));
    expect(hook.result.current.accum?.book?.bids).toEqual([[2_379_000, 9]]);

    // refetch#2(重試)成功,期間**無**簿推播 → 應原樣採用 snapshot#2 的簿
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify({
      ...snap(10, [TICK1]),
      book: { bids: [[2_360_000, 2]], asks: [[2_361_000, 2]] },
    })));
    await act(async () => {
      fail(new Response("{}", { status: 503 })); // refetch#1 失敗 → 排重試
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersToNextTimerAsync();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(hook.result.current.accum?.seq).toBe(10);
    // B1 是**上一輪**的殘留,不得蓋掉這一輪 snapshot 的簿
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

  // 🟢 review B-5:上一條只鎖了正向(**本檔**回補完成 → refetch)。`prev.backfilling`
  // 與主圖 key 的比對拿掉一樣全綠 —— 而它守的是「別人回補完成不要害我重抓」:自選池
  // 每檔都會輪到,一天下來是幾十份 MB 級 snapshot 的無謂流量。
  it("他檔回補完成不觸發主圖 refetch", async () => {
    const { hook, ws } = await setup();
    const before = fetchMock.mock.calls.length;
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: "5483" }));
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: null }));
    // refetch 是非同步的,要等它有機會發生才算數(否則斷言的是「還沒打」)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(fetchMock.mock.calls.length).toBe(before);
    expect(hook.result.current.status.backfilling).toBeNull();
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

  // 🟢 緩撮旗標(SC-1 的資料源)。與 `ref` 同理:下游元件測試都是把 quotes 當 props
  // 直接餵,繞過 WS 解析 —— 這一層是 `trial` 解析唯一測得到的地方。
  it("watchlist_quote 的 trial 欄位進側欄報價", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "5483",
        p: 216_500, chg_pct: -1.2, vol: 100, no_data: false, trial: true,
      }),
    );
    expect(hook.result.current.watchlist["5483"]?.trial).toBe(true);
  });

  it("舊後端不發 trial → 降級 false(不是 undefined)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({ type: "watchlist_quote", code: "9996", p: 100_000, chg_pct: 0, vol: 1, no_data: false }),
    );
    expect(hook.result.current.watchlist["9996"]?.trial).toBe(false);
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
    await openAndSettle(hook, ws, 2); // WS open 是排程重試的前置條件之一

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

  // 同一條的另一半:切檔要 `cancelRetry()`。真實的失效樣態是**少一發不是多一發**
  // (review B-8,實測 mutant 是 4 vs 5):`scheduleRetry` 自己會先
  // `clearTimeout(retryTimerRef.current)`,所以舊 timer 不會真的多打一份;沒歸零的是
  // **backoff** —— 新標的的第一段重試沿用上一檔退避後的間隔(2s / 4s / …),1s 到期
  // 時打不出來。畫面上就是「換一檔之後要多等好幾秒才自癒」,而且愈換愈久。
  it("切檔取消 pending 重試(1s 後只有新標的自己的那一次)", async () => {
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await openAndSettle(hook, ws, 2);

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
    // 沒 `cancelRetry()` = backoff 沒歸零 → 新標的的第一段變 2s,1s 這裡打不出來(+0)
    expect(fetchMock.mock.calls.length).toBe(before + 1);
    expect(String(fetchMock.mock.calls[before]?.[0])).toBe("/api/stock/state/5483");
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(hook.result.current.accum).not.toBeNull();
  });

  // 🟢 review B-1:排程前的三道檢查各自的**負向**路徑。原本只有正向(排得出來)被鎖,
  // 把任何一道拿掉都不會紅 —— 而它們守的是「重試打到不該打的地方」:已卸載的元件、
  // 已經換掉的標的、以及 WS 斷線期間(重連的 onopen 本來就會發一次全量對齊)。
  it("unmount 後不排重試(元件存活檢查)", async () => {
    const hook = renderHook(() => useStockStream("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await openAndSettle(hook, ws, 2);

    vi.useFakeTimers();
    let fail: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((r) => { fail = r; }));
    act(() => ws.emit(T(9))); // 跳號 → refetch(in-flight)
    hook.unmount(); // 結果還沒回來就離開頁面
    await act(async () => {
      fail(new Response("{}", { status: 503 }));
      await vi.advanceTimersByTimeAsync(0);
    });
    const before = fetchMock.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); }); // > cap
    expect(fetchMock.mock.calls.length).toBe(before);
  });

  it("WS 斷線期間不排重試(重連的 onopen 本來就會發一次全量對齊)", async () => {
    const hook = renderHook(() => useStockStream("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await openAndSettle(hook, ws, 2);

    vi.useFakeTimers();
    let fail: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((r) => { fail = r; }));
    act(() => ws.emit(T(9)));
    act(() => { ws.onclose?.(); }); // 同一條 socket(alive=true)→ 旗標轉假 + 排重連
    await act(async () => {
      fail(new Response("{}", { status: 503 }));
      await vi.advanceTimersByTimeAsync(0);
    });
    const before = fetchMock.mock.calls.length;
    // 10s 內重連 timer 會建一條新 FakeWS(它自己不會 onopen)—— 但**不該**有 refetch
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(FakeWS.instances.length).toBe(2);
    expect(fetchMock.mock.calls.length).toBe(before);
  });

  // 🟢 review B-2/B-6:backoff 曲線本身。既有兩條 F-3 測試都只走**第一段**(1s),
  // 「會遞增」「有上限」「成功後歸零」三個性質一條都沒鎖 —— 把遞增或成功路徑的
  // `cancelRetry` 拿掉都是全綠。斷言用**性質**(段與段相比)而不是毫秒常數:
  // 1s→2s→4s cap 8s 是可調參數,鎖死它等於把 config 抄進測試。
  it("重試間隔遞增、有上限、成功一次後歸零", async () => {
    const hook = renderHook(() => useStockStream("2330"), { wrapper });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    await openAndSettle(hook, ws, 2);

    vi.useFakeTimers();
    fetchMock.mockImplementation(async () => new Response("{}", { status: 503 }));
    act(() => ws.emit(T(9))); // 跳號 → refetch → 503 → 排第一段
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const d: number[] = [];
    for (let i = 0; i < 6; i += 1) d.push(await nextRetryDelay());
    expect(d[1]!).toBeGreaterThan(d[0]!); // 遞增
    expect(d[2]!).toBeGreaterThan(d[1]!);
    expect(d[5]!).toBe(d[4]!); // 有上限:夠多次之後不再增長
    expect(d[5]!).toBeGreaterThan(d[0]!);

    // 成功一次 → backoff 歸零(否則 TC4 短暫抽風之後,下一次失敗要等到 cap 才自癒)
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(snap(20, [TICK1]))));
    await act(async () => {
      await vi.advanceTimersToNextTimerAsync();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(hook.result.current.accum?.seq).toBe(20);
    act(() => ws.emit(T(50))); // 跳號 → refetch → 503(持久 mock)
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(await nextRetryDelay()).toBe(d[0]!); // 回到最短間隔,不是沿用退避後的
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

    await openAndSettle(hook, ws2, 2); // 新 socket open → 旗標轉真
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
    type: "ticks",
    items: [{ code, t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq }],
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

// 🟢 主圖 accum 的 trial 補寫(D4)。預覽股不在自選,開頁之後的窗轉態只有後端對
// 「現貨主圖碼」的補推帶得進來 —— 沒有這條,badge 要等到下次全量 refetch 才會動。
//
// **與 no_data 補寫是兩條獨立分支**:no_data 那條是單向黏性(只 false→true,清除靠
// refetch),而試撮窗天然要雙向(09:00 出窗就該熄)。合併兩者會把未宣告的行為改動
// (no_data 雙向化)偷渡進來。
describe("useStockStream(主圖 trial 補寫)", () => {
  it("主圖碼的 trial 轉真 → 補寫進 accum(窗邊界推播)", async () => {
    const { hook, ws } = await setup();
    expect(hook.result.current.accum?.trial).toBe(false);
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: false, trial: true,
      }),
    );
    expect(hook.result.current.accum?.trial).toBe(true);
  });

  it("trial 轉假也補寫(雙向;與 no_data 的單向黏性不同)", async () => {
    const { hook, ws } = await setup();
    const q = (trial: boolean) => ({
      type: "watchlist_quote", code: "2330",
      p: null, chg_pct: null, vol: null, no_data: false, trial,
    });
    act(() => ws.emit(q(true)));
    expect(hook.result.current.accum?.trial).toBe(true);
    act(() => ws.emit(q(false)));
    expect(hook.result.current.accum?.trial).toBe(false);
  });

  it("他檔的 trial 不影響主圖(側欄那格照收)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "9995",
        p: null, chg_pct: null, vol: null, no_data: false, trial: true,
      }),
    );
    expect(hook.result.current.watchlist["9995"]?.trial).toBe(true);
    expect(hook.result.current.accum?.trial).toBe(false);
  });

  it("trial 補寫不動 noData(no_data 的單向黏性不因新分支而鬆掉)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: true, trial: false,
      }),
    );
    expect(hook.result.current.accum?.noData).toBe(true);
    // 同一碼再來一則 no_data=false + trial=true:trial 要跟上,noData 維持 true
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: 2_380_000, chg_pct: 1, vol: 1, no_data: false, trial: true,
      }),
    );
    expect(hook.result.current.accum?.trial).toBe(true);
    expect(hook.result.current.accum?.noData).toBe(true);
  });

  // 🔴 code review IC-3:trial 補寫少了 `tick`/`book` 都有的 in-flight 守門。refetch 的
  // fetch 一送出,後端的窗判斷就凍結在那一刻 —— 之後到達的翻轉補寫進 accum,再被回來的
  // snapshot 整份覆蓋回捲。被吃掉的那則若是**出窗**(true→false),header 就掛著一個假的
  // 「(緩)」直到下一次全量 refetch:靜市 / 盤前無成交時那可能是整個窗,而且零錯誤訊號。
  it("refetch in-flight 期間的 trial 翻轉不被較舊的 snapshot 回捲(IC-3)", async () => {
    const { hook, ws } = await setup();
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(T(4))); // 1→4 跳號 → refetch(fetch 已送出 = 後端窗判斷已凍結)
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: false, trial: true,
      }),
    );
    act(() => {
      // snapshot 帶的是凍結當下的窗判斷(這裡不帶 trial → fromSnapshot 降級 false)
      resolveRefetch(new Response(JSON.stringify(snap(4, [TICK1]))));
    });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(4));
    expect(hook.result.current.accum?.trial).toBe(true);
  });

  // 上一條的另一半:pending 的 trial 帶 instrumentKey 標記,切檔撞上 in-flight 時不可
  // 外洩到新標的(「2330 在試撮窗內」對 5483 / 期貨鍵不是同一個答案,期貨鍵的窗恆空)。
  //
  // 覆蓋度誠實記帳(同 pendingBook 的 review B-4 記帳):這條**修前修後都綠**,任何
  // 單點 mutation 也殺不掉它 —— 實測把「key 比對 + 切檔 effect 清理 + finally 清理」
  // 三處一起拿掉仍綠(`refetch` 開頭那道清理是最後的兜底),而 pending 只在
  // `msg.code === current` 時才寫,寫入時 key 恆等於當下標的 = key 比對是可證的死碼。
  // 留著的理由:它是「哪天多一條沒清 pending 的切檔路徑」時唯一會攔下「舊檔的窗態畫到
  // 新檔上」的測試,而那個失效沒有任何錯誤訊號。
  it("切檔撞上 in-flight 時舊 key 的 pending trial 不外洩(IC-3)", async () => {
    let resolveFirst: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveFirst = res; }),
    );
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
      wrapper,
    });
    const ws = FakeWS.instances[0]!;
    // 2330 的 snapshot 還在路上 → 這則翻轉進 pending
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: false, trial: true,
      }),
    );
    hook.rerender({ c: "5483" });
    act(() => { resolveFirst(new Response(JSON.stringify(snap(1, [TICK1])))); });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    expect(hook.result.current.accum?.trial).toBe(false);
  });
});

// 🔴 SC-4:群組檢視沒有明細 / 主圖讀者,點卡片那趟不該把整份 tape(deque 上限兩萬筆,
// 盤中實測 0.5–1.5 MB/檔)拖回來。`tape` 必須比照 code / contract 走 **ref**:WS callback
// 是 `[]` deps 的閉包,由它捕獲的話「切回單檔之後由 seq-gap 觸發的那次 refetch」還會用
// 掛載當時的舊值 → 主圖永遠拿不到 tape,而畫面只是「明細一直空著」。
describe("useStockStream(tape 選項)", () => {
  const C9 = { prod: "CDF", ym: "202609", mini: false, unit: 2000 };

  function stateUrls(): string[] {
    return fetchMock.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.startsWith("/api/stock/state/"));
  }

  async function setupTape(tape: boolean, contract: StkfutSelection | null = null) {
    const hook = renderHook(({ t }: { t: boolean }) => useStockStream("2330", contract, { tape: t }), {
      initialProps: { t: tape },
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    return { hook, ws: FakeWS.instances[0]! };
  }

  it("tape=false → URL 帶 tape=0(現貨態用 ?)", async () => {
    await setupTape(false);
    expect(stateUrls()).toEqual(["/api/stock/state/2330?tape=0"]);
  });

  it("tape=false + 合約態 → 兩個 query 用 & 接(順序固定)", async () => {
    await setupTape(false, C9);
    expect(stateUrls()).toEqual(["/api/stock/state/2330?contract=CDF:202609&tape=0"]);
  });

  it("tape=true(預設語意)→ URL 逐字不變", async () => {
    await setupTape(true);
    expect(stateUrls()).toEqual(["/api/stock/state/2330"]);
  });

  it("false→true 補打一次全量;true→false 不打(多出來的 ticks 無害)", async () => {
    const { hook } = await setupTape(false);
    const before = stateUrls().length;
    await act(async () => {
      hook.rerender({ t: true });
    });
    await waitFor(() => expect(stateUrls().length).toBe(before + 1));
    expect(stateUrls().at(-1)).toBe("/api/stock/state/2330");
    const afterUp = stateUrls().length;
    await act(async () => {
      hook.rerender({ t: false });
    });
    // 再排一輪 microtask/macrotask,確認「不打」不是還沒打
    await act(async () => {
      await Promise.resolve();
    });
    expect(stateUrls().length).toBe(afterUp);
  });

  // 🔒 lock(review T5):正式環境(main.tsx)整棵樹在 `<StrictMode>` 底下 —— dev 的
  // mount→cleanup→mount 會讓 `tapeRef` 的**唯一寫入點**(那支 effect)跑兩輪。上面那條
  // 跑的是非 StrictMode 樹,測不到「第二輪把 `wasOff` 讀成 false → 補打整份 tape 的那趟
  // 被吃掉」:症狀是切回單檔後主圖明細整天空著,而畫面不講原因。
  it("StrictMode 下 false→true 一樣**恰補一趟**全量(URL 不帶 tape=0)", async () => {
    const hook = renderHook(({ t }: { t: boolean }) => useStockStream("2330", null, { tape: t }), {
      initialProps: { t: false },
      ...STRICT,
    });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    // 掛載雙發自己會多打幾趟(單飛 + finally 補發),先等它靜下來再記基準 ——
    // 要鎖的是**轉換**多打幾趟,不是掛載打幾趟
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    const before = stateUrls().length;
    await act(async () => {
      hook.rerender({ t: true });
    });
    await waitFor(() => expect(stateUrls().length).toBe(before + 1));
    expect(stateUrls().at(-1)).toBe("/api/stock/state/2330");
    // 再排一輪,確認「恰一趟」不是「還有一趟在路上」(雙發把補打做成兩次也是壞的:
    // 每次切回單檔就多拖一份 MB 級 payload)
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(stateUrls().length).toBe(before + 1);
  });

  it("WS 掛載期閉包用的是**當下**的 tape:切回單檔後的 seq-gap refetch 要全量", async () => {
    const { hook, ws } = await setupTape(false);
    await act(async () => {
      hook.rerender({ t: true });
    });
    await waitFor(() => expect(stateUrls().length).toBeGreaterThan(1));
    act(() => ws.emit(T(9))); // 1→9 跳號 → WS handler 內的 refetch
    await waitFor(() => expect(stateUrls().length).toBeGreaterThan(2));
    expect(stateUrls().at(-1)).toBe("/api/stock/state/2330");
  });
});

// 🟢 pr-167 #8:disposition 三條新分支(解碼 / accum 守門的 || 半邊 / pendingTrial 攜帶)
// 零測試,失效方向全是靜默降級 —— 比照緊鄰的 trial 案補齊。
describe("useStockStream(disposition 補寫,pr-167 #8)", () => {
  it("watchlist_quote 的 disposition 進側欄報價;缺欄降級 false(不是 undefined)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "5483",
        p: null, chg_pct: null, vol: null, no_data: false, trial: true, disposition: true,
      }),
    );
    expect(hook.result.current.watchlist["5483"]?.disposition).toBe(true);
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "9996",
        p: null, chg_pct: null, vol: null, no_data: false, trial: false,
      }),
    );
    expect(hook.result.current.watchlist["9996"]?.disposition).toBe(false);
  });

  it("trial 同值、只有 disposition 翻轉也要補寫 accum(守門 || 的那半)", async () => {
    // 拔掉 `|| acc.disposition !== q.disposition`:處置股 header 一直印(緩)而側欄是對的,
    // 同畫面兩處對同一檔給不同答案 —— 這條就是那個紅燈。
    const { hook, ws } = await setup();
    const q = (disposition: boolean) => ({
      type: "watchlist_quote", code: "2330",
      p: null, chg_pct: null, vol: null, no_data: false, trial: true, disposition,
    });
    act(() => ws.emit(q(true)));
    expect(hook.result.current.accum?.disposition).toBe(true);
    act(() => ws.emit(q(false))); // trial 維持 true 不變,只翻 disposition
    expect(hook.result.current.accum?.disposition).toBe(false);
  });

  it("refetch in-flight 期間的 disposition 轉態不被較舊的 snapshot 回捲(pendingTrial 攜帶)", async () => {
    const { hook, ws } = await setup();
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(T(4))); // 1→4 跳號 → refetch(snapshot 凍結於此刻,disposition 尚未轉態)
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "2330",
        p: null, chg_pct: null, vol: null, no_data: false, trial: false, disposition: true,
      }),
    );
    act(() => { resolveRefetch(new Response(JSON.stringify(snap(4, [TICK1])))); }); // snap 缺欄 → false
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(4));
    expect(hook.result.current.accum?.disposition).toBe(true);
  });
});

// mod/group-grid-ticks T3(#183):一則 `ticks` 打包 = 一次 commit;非主圖 items 丟給 tick 匯流排
// (群組卡片的 live accum 在那頭吃);「我正在看哪些檔」經同一條 WS 送 `view`,重連 onopen 重送。
describe("useStockStream(ticks 打包 + 檢視集合,T3)", () => {
  const item = (code: string, seq: number) => ({
    code, t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq,
  });

  beforeEach(() => {
    resetTickStream();
  });

  it("一則含主圖 3 筆 → 依序套用到 seq 4,整則只 commit 一次", async () => {
    let renders = 0;
    const hook = renderHook(() => {
      renders += 1;
      return useStockStream("2330");
    }, { wrapper });
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    const before = renders;
    act(() => ws.emit({ type: "ticks", items: [item("2330", 2), item("2330", 3), item("2330", 4)] }));
    expect(hook.result.current.accum?.seq).toBe(4);
    expect(hook.result.current.accum?.ticks.length).toBe(4);
    expect(renders - before).toBe(1);
  });

  it("打包內夾雜非主圖 items → 主圖只套自己的;**整則原序**丟給 tick 匯流排(含主圖檔)", async () => {
    const { hook, ws } = await setup();
    const seen: unknown[][] = [];
    const off = subscribeTicks((items) => seen.push([...items]));
    const items = [item("2330", 2), item("2317", 9), item("2330", 3), item("2454", 1)];
    act(() => ws.emit({ type: "ticks", items }));
    expect(hook.result.current.accum?.seq).toBe(3);
    // 主圖檔的 items 也要進匯流排(review spec F-01):主圖那一檔在群組裡也有一張卡,
    // 群組卡片的 accum 與主圖 accum 是兩份,少送就是那張卡凍在播種值
    expect(seen).toEqual([items]);
    off();
  });

  it("只有主圖 items 的打包也上匯流排(群組卡片同檔要動);空打包不發", async () => {
    const { ws } = await setup();
    const cb = vi.fn();
    const off = subscribeTicks(cb);
    act(() => ws.emit(T(2)));
    expect(cb).toHaveBeenCalledTimes(1);
    act(() => ws.emit({ type: "ticks", items: [] }));
    expect(cb).toHaveBeenCalledTimes(1);
    off();
  });

  it("跳號落在打包中間 → refetch 一次,其後 items 進 pending 並於 snapshot 落地後重放", async () => {
    const { hook, ws } = await setup();
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    const calls = fetchMock.mock.calls.length;
    // seq 2 套用;5 跳號(漏 3,4)→ refetch;6 跟著進 pending
    act(() => ws.emit({ type: "ticks", items: [item("2330", 2), item("2330", 5), item("2330", 6)] }));
    expect(fetchMock.mock.calls.length).toBe(calls + 1);
    act(() => {
      resolveRefetch(new Response(JSON.stringify(snap(4, [
        TICK1,
        { t: "09:01:00.000", p: 2_375_000, q: 1, side: "outer" },
        { t: "09:02:00.000", p: 2_380_000, q: 1, side: "outer" },
        { t: "09:03:00.000", p: 2_380_000, q: 1, side: "outer" },
      ]))));
    });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(6));
    expect(hook.result.current.accum?.ticks.length).toBe(6); // snapshot 4 + 重放 5、6
  });

  // pr-187 review #1:快照 seq 可能領先尚未 flush 的打包窗 —— 快照回 seq=3 時那兩筆(2、3)
  // 還在後端 pending,下一則打包首筆 seq=2 ≤ acc.seq;這是快照已含的重複、不是跳號,
  // 舊寫法會白打一份全量 snapshot(含 tape,MB 級)。
  it("seq ≤ acc.seq 的小幅回退 = 快照已含的重複 → 丟棄、不 refetch;接上的下一筆照常", async () => {
    const { hook, ws } = await setup(); // snapshot seq 1
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(snap(3, [TICK1, TICK1, TICK1]))));
    act(() => ws.emit(T(5))); // 1→5 跳號 → refetch 回 seq 3
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(5)); // 5 由 pending 重放
    const calls = fetchMock.mock.calls.length;
    act(() => ws.emit({ type: "ticks", items: [item("2330", 4), item("2330", 5), item("2330", 6)] }));
    expect(fetchMock.mock.calls.length).toBe(calls); // 4、5 是重複,不 refetch
    expect(hook.result.current.accum?.seq).toBe(6);
  });

  it("大幅回退(rollover 歸零)仍是跳號 → refetch", async () => {
    const { ws } = await setup();
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(snap(5000, [TICK1]))));
    act(() => ws.emit(T(5000))); // 1→5000 跳號 → refetch 回 5000
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));
    const calls = fetchMock.mock.calls.length;
    act(() => ws.emit(T(1))); // 5000 → 1:新的一天
    expect(fetchMock.mock.calls.length).toBe(calls + 1);
  });

  it("setTickView → 對 socket 送 view;同集合不重送;onopen(重連)重送當下集合", async () => {
    const { ws } = await setup();
    act(() => ws.onopen?.()); // open 之後 send 才會真的送出(ws-reconnect 的 open 守門)
    expect(ws.sent).toEqual([]); // 空集合不送
    act(() => setTickView(["2330", "2317"]));
    expect(ws.sent).toEqual([JSON.stringify({ type: "view", codes: ["2330", "2317"] })]);
    act(() => setTickView(["2330", "2317"]));
    expect(ws.sent.length).toBe(1);
    act(() => ws.onopen?.()); // 重連:後端是新 token,必須重送
    expect(ws.sent.length).toBe(2);
    expect(ws.sent[1]).toBe(JSON.stringify({ type: "view", codes: ["2330", "2317"] }));
    act(() => setTickView([]));
    expect(ws.sent[2]).toBe(JSON.stringify({ type: "view", codes: [] })); // 清空要告知(後端才除名)
  });

  it("unmount 後 setTickView 不再送(訂閱已解除)", async () => {
    const { hook, ws } = await setup();
    act(() => ws.onopen?.());
    hook.unmount();
    act(() => setTickView(["2330"]));
    expect(ws.sent).toEqual([]);
  });
});
