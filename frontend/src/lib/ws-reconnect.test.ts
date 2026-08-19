/** @vitest-environment jsdom */
/** `connectWithRetry` 的 characterization 測試(mod/ws-app-heartbeat FE-1)。
 *
 * 本檔鎖的是**抽出當下的現行語意**(8 hook 逐字複刻),用途是證明重構零行為改動。
 * 其中兩條是**事前標記為「該變」**的現況鎖(`[該變]` 註記),下一個 🔴 commit 會翻轉它們
 * ——這是鐵則 E 允許改既有 assertion 的唯一通道(事前標明)。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  connectWithRetry,
  resetWsPingMemory,
  WS_BACKOFF_CAP_MS,
  WS_BACKOFF_START_MS,
  WS_MIN_UPTIME_MS,
  WS_SHORT_LIVED_CAP_MS,
  WS_SILENCE_TIMEOUT_MS,
  WS_WATCHDOG_TICK_MS,
} from "@/lib/ws-reconnect";

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
    this.onclose?.();
  }

  emit(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }

  emitRaw(data: string): void {
    this.onmessage?.({ data });
  }
}

/** 最新一代 socket(重連後 handler 只掛在它身上)。 */
function latest(): FakeWS {
  const sock = FakeWS.instances.at(-1);
  expect(sock).toBeDefined();
  return sock!;
}

beforeEach(() => {
  FakeWS.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("connectWithRetry", () => {
  it("首次即建立連線,url 可傳函式(每次重連當下重算)", () => {
    let n = 0;
    const handle = connectWithRetry(
      () => `ws://host/ws/x?n=${++n}`,
      { onMessage: () => {} },
    );
    expect(FakeWS.instances.length).toBe(1);
    expect(latest().url).toBe("ws://host/ws/x?n=1");

    latest().onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);
    expect(latest().url).toBe("ws://host/ws/x?n=2");
    handle.close();
  });

  it("onConnecting 在首次與每次重連都觸發(W12)", () => {
    const onConnecting = vi.fn();
    const handle = connectWithRetry("ws://host/ws/x", { onConnecting, onMessage: () => {} });
    expect(onConnecting).toHaveBeenCalledTimes(1);

    latest().onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(onConnecting).toHaveBeenCalledTimes(2);

    latest().onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS * 2);
    expect(onConnecting).toHaveBeenCalledTimes(3);
    handle.close();
  });

  it("onOpen / onMessage / onClose 逐一轉發", () => {
    const onOpen = vi.fn();
    const onMessage = vi.fn();
    const onClose = vi.fn();
    const handle = connectWithRetry("ws://host/ws/x", { onOpen, onMessage, onClose });

    latest().onopen?.();
    latest().emit({ type: "corr", seq: 3 });
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({ type: "corr", seq: 3 });

    latest().onclose?.();
    expect(onClose).toHaveBeenCalledTimes(1);
    handle.close();
  });

  it("重連延遲倍增並在 30 s 封頂(W8;未 open 的連線 backoff 不歸零)", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });
    const expected = [1_000, 2_000, 4_000, 8_000, 16_000, WS_BACKOFF_CAP_MS, WS_BACKOFF_CAP_MS];

    let generation = 1;
    for (const delay of expected) {
      latest().onclose?.();
      vi.advanceTimersByTime(delay - 1);
      expect(FakeWS.instances.length).toBe(generation); // 差 1 ms 還沒重連
      vi.advanceTimersByTime(1);
      generation += 1;
      expect(FakeWS.instances.length).toBe(generation);
    }
    handle.close();
  });

  it("close() 停止重連,舊 socket 之後的 close 不再回呼也不排程(W3)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {}, onClose });
    const gen1 = latest();

    handle.close();
    expect(gen1.closed).toBe(true); // close() 關掉當下的 socket
    expect(onClose).not.toHaveBeenCalled(); // stopped 守門(= 現行 `if (!alive) return`)

    gen1.onclose?.(); // 遲到的 close(Chromium closing handshake)
    vi.advanceTimersByTime(WS_BACKOFF_CAP_MS * 2);
    expect(FakeWS.instances.length).toBe(1);
    expect(onClose).not.toHaveBeenCalled();
    // 註:🔵 階段只守 onclose / 重連;主動卸掉舊 socket 的 onmessage/onerror 是 🟢
    // watchdog 那一包的事(spec §4.3),本檔不預先斷言。
  });

  it("已排程的重連在 close() 後不會發生", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });
    latest().onclose?.(); // 排了 1 s 後重連
    handle.close();
    vi.advanceTimersByTime(WS_BACKOFF_CAP_MS);
    expect(FakeWS.instances.length).toBe(1);
  });

  it("無法解析的訊息 → warn 且不進 onMessage", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const onMessage = vi.fn();
    const handle = connectWithRetry("ws://host/ws/x", { onMessage }, { label: "corr ws" });

    latest().emitRaw("not json{");
    expect(onMessage).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.[0])).toBe("corr ws: 無法解析訊息");

    latest().emit({ ok: true });
    expect(onMessage).toHaveBeenCalledTimes(1);
    warn.mockRestore();
    handle.close();
  });

  // 由 🔵 characterization「[該變] onerror alias」翻轉而來(spec §7 SC-5):
  // 舊語意 = 第一代 error 關掉第二代(alias);新語意 = 只關自身。
  it("onerror 只關自身 socket,不動新世代(SC-5)", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });
    const gen1 = FakeWS.instances[0];
    expect(gen1).toBeDefined();

    gen1?.onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);
    const gen2 = FakeWS.instances[1];
    expect(gen2).toBeDefined();

    gen1?.onerror?.(); // 舊世代的 error
    expect(gen1?.closed).toBe(true); // 關的是自己
    expect(gen2?.closed).toBe(false); // 新世代不受影響
    handle.close();
  });

  // 由 🔵 characterization「[該變] onopen 歸零 backoff」翻轉而來(spec §7 SC-4):
  // 歸零改由 onclose 的「存活 ≥ WS_MIN_UPTIME_MS」分支負責,第二次延遲 = 2 s 而非 1 s。
  it("onopen 不再歸零 backoff(accept-then-close 不再 1 Hz)", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });

    latest().onopen?.(); // 立刻 open
    latest().onclose?.(); // 立刻 close(accept-then-close)
    vi.advanceTimersByTime(1_000);
    expect(FakeWS.instances.length).toBe(2);

    latest().onopen?.(); // 第二代同樣 open→close
    latest().onclose?.();
    vi.advanceTimersByTime(1_999);
    expect(FakeWS.instances.length).toBe(2); // 還沒到(不再是 1 s)
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(3);
    handle.close();
  });

  it("有 open 但存活 < 5 s(accept-then-close)→ 倍增但 cap 5 s:1,2,4,5,5(SC-4 (ii))", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });
    const expected = [1_000, 2_000, 4_000, WS_SHORT_LIVED_CAP_MS, WS_SHORT_LIVED_CAP_MS];

    let generation = 1;
    for (const delay of expected) {
      latest().onopen?.(); // accept
      latest().onclose?.(); // 立刻 close(存活 0 ms)
      vi.advanceTimersByTime(delay - 1);
      expect(FakeWS.instances.length).toBe(generation);
      vi.advanceTimersByTime(1);
      generation += 1;
      expect(FakeWS.instances.length).toBe(generation);
    }
    handle.close();
  });

  it("存活 ≥ WS_MIN_UPTIME_MS 後斷線 → 下次 1 s(SC-4 (i);健康連線行為不變)", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });

    // 先用兩代短命連線把 backoff 推到 4 s
    latest().onopen?.();
    latest().onclose?.();
    vi.advanceTimersByTime(1_000);
    latest().onopen?.();
    latest().onclose?.();
    vi.advanceTimersByTime(2_000);
    expect(FakeWS.instances.length).toBe(3);

    latest().onopen?.(); // 第三代健康存活滿 5 s 才斷
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    latest().onclose?.();
    vi.advanceTimersByTime(999);
    expect(FakeWS.instances.length).toBe(3);
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(4); // 歸零回初值 1 s
    handle.close();
  });

  it("曾健康 open ≥5 s,之後連續握手失敗 → 走「從未 open」分支 2,4,8(Edge 12)", () => {
    const handle = connectWithRetry("ws://host/ws/x", { onMessage: () => {} });

    latest().onopen?.();
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    latest().onclose?.(); // 健康斷線 → 1 s
    vi.advanceTimersByTime(1_000);
    expect(FakeWS.instances.length).toBe(2);

    // 之後每一代都沒 onopen(server down):openedAt 每代重設 → 不會退化成 1 Hz
    let generation = 2;
    for (const delay of [2_000, 4_000, 8_000]) {
      latest().onclose?.();
      vi.advanceTimersByTime(delay - 1);
      expect(FakeWS.instances.length).toBe(generation);
      vi.advanceTimersByTime(1);
      generation += 1;
      expect(FakeWS.instances.length).toBe(generation);
    }
    handle.close();
  });

  it('{ type: "ping" } 心跳不進 onMessage(SC-3)', () => {
    const onMessage = vi.fn();
    const handle = connectWithRetry("ws://host/ws/ping-filter", { onMessage });

    latest().onopen?.();
    latest().emit({ type: "ping" });
    expect(onMessage).not.toHaveBeenCalled();

    latest().emit({ type: "corr", seq: 1 });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({ type: "corr", seq: 1 });
    handle.close();
  });

  it("opts 可覆寫 backoff 初值與上限", () => {
    const handle = connectWithRetry(
      "ws://host/ws/x",
      { onMessage: () => {} },
      { backoffStartMs: 100, backoffCapMs: 150 },
    );
    latest().onclose?.();
    vi.advanceTimersByTime(100);
    expect(FakeWS.instances.length).toBe(2);

    latest().onclose?.();
    vi.advanceTimersByTime(150);
    expect(FakeWS.instances.length).toBe(3);
    handle.close();
  });
});

/** SC-2:半死連線(TCP 活著但零 frame)靠「太久沒收到任何訊息」自己分辨並重連。 */
describe("connectWithRetry 靜默 watchdog", () => {
  const URL_A = "ws://host/ws/wd-a";

  beforeEach(() => {
    resetWsPingMemory();
  });

  it("收到首則 ping 後武裝;35 s 全靜默 → 卸 handler + close + onClose + 重連", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage: () => {}, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" });

    vi.advanceTimersByTime(WS_SILENCE_TIMEOUT_MS); // 30 s 整:尚未「超過」
    expect(onClose).not.toHaveBeenCalled();
    expect(gen1.closed).toBe(false);

    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS); // 下一個 tick → 判定靜默
    expect(gen1.closed).toBe(true);
    expect(gen1.onmessage).toBeNull(); // 放棄前先卸 handler(不等 onclose)
    expect(gen1.onclose).toBeNull();
    expect(gen1.onerror).toBeNull();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(FakeWS.instances.length).toBe(1); // 重連走 backoff,不是同步新建

    vi.advanceTimersByTime(WS_BACKOFF_START_MS); // 存活遠超 minUptime → 1 s
    expect(FakeWS.instances.length).toBe(2);
    handle.close();
  });

  it("29 s 時收到任一訊息 → 基準重置,再 29 s 仍不觸發(Edge 3)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage: () => {}, onClose });
    latest().onopen?.();
    latest().emit({ type: "ping" });

    vi.advanceTimersByTime(29_000);
    latest().emit({ type: "corr", seq: 1 });
    vi.advanceTimersByTime(29_000);

    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);
    handle.close();
  });

  it("從未收過 ping → 永不武裝:60 s 全靜默也不重連(舊後端行為 = 現況)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry("ws://host/ws/wd-never", { onMessage: () => {}, onClose });
    latest().onopen?.();

    vi.advanceTimersByTime(60_000);
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);
    expect(vi.getTimerCount()).toBe(0); // 連 interval 都沒建
    handle.close();
  });

  it("被放棄的舊 socket 遲到 onclose / onmessage 不回呼也不重複重連(Edge 2)", () => {
    const onClose = vi.fn();
    const onMessage = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" });

    vi.advanceTimersByTime(35_000); // watchdog 觸發
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);

    gen1.onclose?.(); // Chromium closing handshake 60 s 後才到
    gen1.emit({ type: "corr", late: true });
    vi.advanceTimersByTime(WS_BACKOFF_CAP_MS * 2);

    expect(FakeWS.instances.length).toBe(2);
    expect(onMessage).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
    handle.close();
  });

  it("舊世代 watchdog 不觸發新世代重連(任何關閉路徑都 clearInterval)", () => {
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" }); // gen1 武裝
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    gen1.onclose?.(); // 自然斷線(非 watchdog)
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);

    // gen2 尚未 onopen → 未武裝;gen1 的 interval 若沒清會誤生第三代
    vi.advanceTimersByTime(60_000);
    expect(FakeWS.instances.length).toBe(2);
    handle.close();
  });

  it("close() 清掉 watchdog interval(不留任何 timer)", () => {
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    latest().onopen?.();
    latest().emit({ type: "ping" });
    expect(vi.getTimerCount()).toBe(1); // watchdog interval

    handle.close();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("sticky:同 URL 的後續世代 onopen 即武裝(即使自己沒收過 ping)", () => {
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" }); // 記住「這個 server 會送 ping」
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    gen1.onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);

    const gen2 = latest();
    gen2.onopen?.(); // gen2 全程收不到任何訊息(含 ping)
    vi.advanceTimersByTime(35_000);
    expect(gen2.closed).toBe(true);
    expect(FakeWS.instances.length).toBe(2);

    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(3);
    handle.close();
  });

  it("不同 URL 不互相 sticky", () => {
    const a = connectWithRetry(URL_A, { onMessage: () => {} });
    latest().onopen?.();
    latest().emit({ type: "ping" });
    a.close();

    FakeWS.instances = [];
    const onClose = vi.fn();
    const b = connectWithRetry("ws://host/ws/wd-b", { onMessage: () => {}, onClose });
    latest().onopen?.(); // 另一個 URL:沒人證明它會送 ping

    vi.advanceTimersByTime(60_000);
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);
    b.close();
  });

  it("主執行緒凍結 / 睡眠喚醒:tick 間隔 > 2×tick 只重置基準不判定(Edge 13)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage: () => {}, onClose });
    latest().onopen?.();
    latest().emit({ type: "ping" });

    vi.setSystemTime(Date.now() + 40_000); // 凍結 40 s(timer 沒跑,牆鐘照走)
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS); // 醒來後第一個 tick
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);

    vi.advanceTimersByTime(35_000); // 重置後才是真靜默
    expect(onClose).toHaveBeenCalledTimes(1);
    handle.close();
  });
});
