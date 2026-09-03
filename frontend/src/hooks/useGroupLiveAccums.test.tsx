/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useGroupLiveAccums } from "@/hooks/useGroupLiveAccums";
import type { GroupSnapshot } from "@/hooks/useGroupSnapshots";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { emitTicks, resetTickStream } from "@/lib/tick-stream";

/** T4 #185:群組卡片的 live accum —— 由 group-state 快照播種(seq 錨點),之後吃 tick 匯流排;
 *  per-code `seq === acc.seq + 1` 才套用,跳號那一檔單飛重拉 `group-state?codes=X`;
 *  新快照(60 s 輪詢)到 → 全體重播種。 */

function snap(over: Partial<GroupSnapshot> = {}): GroupSnapshot {
  return {
    minutes: new Map([[540, { c: 2_380_000, v: 10, i: 3, o: 7, u: 0, h: 2_385_000, l: 2_375_000 }]]),
    meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 100 },
    noData: false,
    backfilling: false,
    vwap: 2_380_000,
    high: 2_385_000,
    low: 2_375_000,
    vp: new Map(),
    seq: 10,
    vwapVol: 10,
    ...over,
  };
}

const quote = (p: number | null): WatchlistQuote => ({
  p, chg_pct: null, vol: null, ref: null, upper: null, lower: null,
  no_data: false, trial: false, disposition: false,
});

const item = (code: string, seq: number, p = 2_390_000) => ({
  code, t: "09:05:00.000", p, q: 2, side: "outer" as const, seq,
});

/** 單檔重拉的回應(後端 raw 形:`vp` 緊湊陣列、`seq` / `vwap_vol` 鍵) */
function rawBody(code: string, seq: number) {
  return {
    states: {
      [code]: {
        minutes: { "540": { c: 2_400_000, v: 30, i: 10, o: 20, u: 0, h: 2_405_000, l: 2_375_000 } },
        meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 100 },
        vwap: 2_390_000,
        high: 2_405_000,
        low: 2_375_000,
        vp: {},
        seq,
        vwap_vol: 30,
        no_data: false,
        backfilling: false,
      },
    },
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  resetTickStream();
  fetchMock = vi.fn(async (url: string) => {
    const code = new URL(String(url), "http://x").searchParams.get("codes") ?? "";
    return new Response(JSON.stringify(rawBody(code, 20)));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useGroupLiveAccums", () => {
  it("由快照播種:seq 錨定、末點取播種當下的 quote 現價", () => {
    const snaps = { "2330": snap(), "2317": snap({ seq: 3 }) };
    const quotes = { "2330": quote(2_381_000) };
    const hook = renderHook(() => useGroupLiveAccums(["2330", "2317"], snaps, quotes));
    const accs = hook.result.current;
    expect(accs["2330"]?.seq).toBe(10);
    expect(accs["2330"]?.last?.p).toBe(2_381_000);
    expect(accs["2317"]?.seq).toBe(3);
    expect(accs["2317"]?.last?.p).toBe(2_380_000); // 無 quote → 退回最後一格收盤
  });

  it("連續 seq 的 tick 套用:只有那一檔換 identity,末點 / 量 / seq 前進", () => {
    const snaps = { "2330": snap(), "2317": snap({ seq: 3 }) };
    const hook = renderHook(() => useGroupLiveAccums(["2330", "2317"], snaps, {}));
    const before = hook.result.current;
    act(() => emitTicks([item("2330", 11), item("2330", 12, 2_395_000)]));
    const after = hook.result.current;
    expect(after["2330"]?.seq).toBe(12);
    expect(after["2330"]?.last?.p).toBe(2_395_000);
    expect(after["2330"]?.minutes.get(545)?.v).toBe(4);
    expect(after["2330"]).not.toBe(before["2330"]);
    expect(after["2317"]).toBe(before["2317"]); // 沒收到 tick 的卡 identity 不變(memo 護欄)
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("一則打包多檔 → 各檔套各的,整則只 commit 一次", () => {
    let renders = 0;
    const snaps = { "2330": snap(), "2317": snap({ seq: 3 }) };
    const hook = renderHook(() => {
      renders += 1;
      return useGroupLiveAccums(["2330", "2317"], snaps, {});
    });
    const before = renders;
    act(() => emitTicks([item("2330", 11), item("2317", 4), item("2330", 12)]));
    expect(renders - before).toBe(1);
    expect(hook.result.current["2330"]?.seq).toBe(12);
    expect(hook.result.current["2317"]?.seq).toBe(4);
  });

  it("不在 codes 內的 tick 忽略(別的連線 / 切組後遲到的推播)", () => {
    const snaps = { "2330": snap() };
    const hook = renderHook(() => useGroupLiveAccums(["2330"], snaps, {}));
    const before = hook.result.current;
    act(() => emitTicks([item("2454", 1)]));
    expect(hook.result.current).toBe(before);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // pr-187 review #1:快照 seq 可能領先尚未 flush 的打包窗(播種 seq=10 時那筆 10 還在後端
  // pending),下一則打包首筆就是 seq ≤ acc.seq 的「已含在快照裡」重複 —— 不是跳號,不能重拉。
  it("seq ≤ acc.seq 的小幅回退 = 快照已含的重複 → 靜默丟棄、不重拉、accum 不動", () => {
    const snaps = { "2330": snap() }; // seq 10
    const hook = renderHook(() => useGroupLiveAccums(["2330"], snaps, {}));
    const before = hook.result.current["2330"];
    act(() => emitTicks([item("2330", 9), item("2330", 10)]));
    expect(hook.result.current["2330"]).toBe(before);
    expect(fetchMock).not.toHaveBeenCalled();
    // 重複之後接上的 11 照常套用(丟棄不會把「下一筆該是誰」弄壞)
    act(() => emitTicks([item("2330", 10), item("2330", 11)]));
    expect(hook.result.current["2330"]?.seq).toBe(11);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("大幅回退(rollover 歸零)仍是跳號 → 重拉", () => {
    const snaps = { "2330": snap({ seq: 5000 }) };
    renderHook(() => useGroupLiveAccums(["2330"], snaps, {}));
    act(() => emitTicks([item("2330", 1)]));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("跳號 → 只重拉那一檔(group-state?codes=X),落地後重放 seq > snap.seq 的 pending", async () => {
    const snaps = { "2330": snap(), "2317": snap({ seq: 3 }) };
    const hook = renderHook(() => useGroupLiveAccums(["2330", "2317"], snaps, {}));
    // 10 → 13 跳號(漏 11、12);同則的 14 進 pending;重拉回 seq 20 的快照 → 13 / 14 都 ≤ 20 丟棄
    act(() => emitTicks([item("2330", 13), item("2330", 14)]));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/stock/group-state?codes=2330");
    await waitFor(() => expect(hook.result.current["2330"]?.seq).toBe(20));
    expect(hook.result.current["2330"]?.minutes.get(540)?.v).toBe(30); // 重拉的分鐘
    expect(hook.result.current["2317"]?.seq).toBe(3); // 另一檔不動
    // 重拉期間到的 21、22 → 落地後重放
  });

  it("重拉在飛時到的 tick 進 pending,落地後只重放 seq > 快照 seq 的", async () => {
    let resolve: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((res) => { resolve = res; }));
    const snaps = { "2330": snap() };
    const hook = renderHook(() => useGroupLiveAccums(["2330"], snaps, {}));
    act(() => emitTicks([item("2330", 13)])); // 跳號 → 重拉在飛
    act(() => emitTicks([item("2330", 19), item("2330", 21, 2_399_000), item("2330", 22, 2_401_000)]));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => { resolve(new Response(JSON.stringify(rawBody("2330", 20)))); });
    await waitFor(() => expect(hook.result.current["2330"]?.seq).toBe(22));
    expect(hook.result.current["2330"]?.last?.p).toBe(2_401_000);
    expect(hook.result.current["2330"]?.minutes.get(545)?.v).toBe(4); // 21、22 兩筆各 2 張;19 被丟
  });

  it("新快照(輪詢)到 → 全體重播種,live 進度以新快照為準", () => {
    const s1 = { "2330": snap() };
    const hook = renderHook(
      ({ snaps }: { snaps: Record<string, GroupSnapshot> }) => useGroupLiveAccums(["2330"], snaps, {}),
      { initialProps: { snaps: s1 } },
    );
    act(() => emitTicks([item("2330", 11)]));
    expect(hook.result.current["2330"]?.seq).toBe(11);
    const s2 = { "2330": snap({ seq: 30, vwapVol: 30 }) };
    hook.rerender({ snaps: s2 });
    expect(hook.result.current["2330"]?.seq).toBe(30);
    expect(hook.result.current["2330"]?.volume).toBe(30);
  });

  it("重拉失敗 → 該檔維持舊 accum,下一筆 tick 再試(不無限連打:同一檔 2 s 內不重發)", async () => {
    fetchMock.mockImplementation(async () => new Response("boom", { status: 502 }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const snaps = { "2330": snap() };
    const hook = renderHook(() => useGroupLiveAccums(["2330"], snaps, {}));
    act(() => emitTicks([item("2330", 13)]));
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(hook.result.current["2330"]?.seq).toBe(10);
    act(() => emitTicks([item("2330", 14)])); // 2 s 內:不再打
    expect(fetchMock).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("快照未到(undefined)→ 空表;tick 不炸也不打端點", () => {
    const hook = renderHook(() => useGroupLiveAccums(["2330"], undefined, {}));
    expect(hook.result.current).toEqual({});
    act(() => emitTicks([item("2330", 1)]));
    expect(hook.result.current).toEqual({});
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
