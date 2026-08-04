import { describe, expect, it } from "vitest";

import {
  emitSignal,
  emitWatchlistChanged,
  emitWsOpen,
  onSignal,
  onWatchlistChanged,
  onWsOpen,
} from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";

function sig(id: string): SignalMsg {
  return {
    type: "signal",
    id,
    kind: "surge",
    code: "2330",
    name: "台積電",
    price: 1_234_500,
    time: "09:15:03",
    levels: [],
    direction: null,
    pct: 1.5,
    touch_count: 1,
  };
}

describe("signal-bus", () => {
  it("onSignal 收到 emitSignal 的原 payload", () => {
    const got: SignalMsg[] = [];
    const off = onSignal((s) => got.push(s));
    emitSignal(sig("a"));
    off();
    expect(got.map((s) => s.id)).toEqual(["a"]);
  });

  it("退訂後不再收到(off 回傳值是唯一解除路徑)", () => {
    const got: string[] = [];
    const off = onSignal((s) => got.push(s.id));
    emitSignal(sig("a"));
    off();
    emitSignal(sig("b"));
    expect(got).toEqual(["a"]);
  });

  it("多訂閱者各自收到同一則(ToastStack 與 SignalRail 並存)", () => {
    const one: string[] = [];
    const two: string[] = [];
    const offOne = onSignal((s) => one.push(s.id));
    const offTwo = onSignal((s) => two.push(s.id));
    emitSignal(sig("a"));
    offOne();
    offTwo();
    expect(one).toEqual(["a"]);
    expect(two).toEqual(["a"]);
  });

  it("watchlist_changed 與 ws_open 各自獨立事件(不互相觸發)", () => {
    let signals = 0;
    let watchlist = 0;
    let wsOpen = 0;
    const offs = [
      onSignal(() => (signals += 1)),
      onWatchlistChanged(() => (watchlist += 1)),
      onWsOpen(() => (wsOpen += 1)),
    ];
    emitWatchlistChanged();
    expect([signals, watchlist, wsOpen]).toEqual([0, 1, 0]);
    emitWsOpen();
    expect([signals, watchlist, wsOpen]).toEqual([0, 1, 1]);
    emitSignal(sig("a"));
    expect([signals, watchlist, wsOpen]).toEqual([1, 1, 1]);
    for (const off of offs) off();
  });

  it("watchlist_changed / ws_open 也可退訂", () => {
    let watchlist = 0;
    let wsOpen = 0;
    const offWatchlist = onWatchlistChanged(() => (watchlist += 1));
    const offWsOpen = onWsOpen(() => (wsOpen += 1));
    offWatchlist();
    offWsOpen();
    emitWatchlistChanged();
    emitWsOpen();
    expect([watchlist, wsOpen]).toEqual([0, 0]);
  });
});
