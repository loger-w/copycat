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
  WS_BACKOFF_CAP_MS,
  WS_BACKOFF_START_MS,
  WS_MIN_UPTIME_MS,
  WS_SHORT_LIVED_CAP_MS,
  WS_SILENCE_TIMEOUT_MS,
  WS_WATCHDOG_JITTER_MS,
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
    // 註:這條只釘 onclose / 重連;handle.close() 主動卸掉舊 socket 的
    // onmessage/onopen/onerror 由下方 A2 那條釘(review A2 補上)。
  });

  // review A5:scheduleReconnect 先呼叫 onClose 再排 setTimeout,handler 內同步 close() 清掉的
  // 是「上一個」timer,新排的那顆照樣燒出下一代連線。
  it("onClose 內同步呼叫 close() → 不會漏出下一代連線(A5)", () => {
    let handle: ReturnType<typeof connectWithRetry> | null = null;
    handle = connectWithRetry("ws://host/ws/x", {
      onMessage: () => {},
      onClose: () => {
        handle?.close(); // 例:hook 在 onClose 裡判定要收工
      },
    });

    latest().onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_CAP_MS * 2);
    expect(FakeWS.instances.length).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
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

  // 抽出前 8 hook 的 onMessage 本體都在 parse 的 try 內 → handler 例外被同一個 catch 吞掉。
  // 🔵 抽出時 try 收窄成只包 JSON.parse,這條釘住補回來的對等性(review A1)。
  it("onMessage 拋例外 → warn 吞掉不外漏,後續訊息照常投遞", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const seen: unknown[] = [];
    let boom = true;
    const handle = connectWithRetry(
      "ws://host/ws/x",
      {
        onMessage: (msg) => {
          seen.push(msg);
          if (boom) throw new Error("handler 爆了");
        },
      },
      { label: "corr ws" },
    );

    expect(() => latest().emit({ seq: 1 })).not.toThrow();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.[0])).toBe("corr ws: 訊息處理失敗"); // 與 parse 失敗可區分

    boom = false;
    latest().emit({ seq: 2 }); // 這代 socket 沒被拆掉,後續訊息照常
    expect(seen).toEqual([{ seq: 1 }, { seq: 2 }]);
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
  let randomSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // N038:watchdog 放棄路徑帶 jitter;本 describe 預設釘 0,讓既有時序案逐毫秒不動
    randomSpy = vi.spyOn(Math, "random").mockReturnValue(0);
  });

  afterEach(() => {
    randomSpy.mockRestore();
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

  // review T1/T2:武裝後的每一則 ping 都要餵狗(否則零推播的健康連線每 35 s 自砍一次),
  // 且 arm() 必須冪等(否則每則 ping 疊一顆 interval)。
  it("後續 ping 一樣餵 watchdog,且 arm() 冪等只留一顆 interval(T1/T2)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage: () => {}, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" }); // 武裝

    vi.advanceTimersByTime(20_000);
    gen1.emit({ type: "ping" }); // 第二則心跳:餵狗,不重排 timer
    expect(vi.getTimerCount()).toBe(1); // T2:arm() 冪等,沒疊出第二顆 interval

    vi.advanceTimersByTime(20_000); // 距最後一則 ping 才 20 s
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);

    vi.advanceTimersByTime(35_000); // 心跳真的停了才判定
    expect(onClose).toHaveBeenCalledTimes(1);
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

  // 由「從未收過 ping → 永不武裝(舊後端行為 = 現況)」翻轉而來(R4 N035,事前標記該變):
  // 分頁第一代連線在首則 ping 前就半死 → 舊語意永久不偵測;open 即武裝封掉這個盲區。
  it("open 即武裝:從未收過 ping 的連線 30 s + tick 全靜默 → 重連(N035)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry("ws://host/ws/wd-never", { onMessage: () => {}, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    expect(vi.getTimerCount()).toBe(1); // onopen 當下就有 interval

    vi.advanceTimersByTime(WS_SILENCE_TIMEOUT_MS);
    expect(onClose).not.toHaveBeenCalled(); // 30 s 整:尚未「超過」
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS);
    expect(gen1.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);
    handle.close();
  });

  it("尚未 onopen(握手中)不武裝:60 s 也不判定,連 interval 都沒建", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry("ws://host/ws/wd-handshake", { onMessage: () => {}, onClose });

    vi.advanceTimersByTime(60_000);
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
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

  // review A2:close() 的文件宣稱「之後所有回呼不再觸發」,但只關 socket 沒卸 handler ——
  // onclose 有 stopped 守門,onmessage / onopen / onerror 沒有。
  it("close() 卸掉舊 socket 的 handler:遲到的 message / open 都不再回呼也不武裝(A2)", () => {
    // open 即武裝(N035):遲到的 onopen 若沒被卸掉,會在 close() 之後武裝出殘留 interval
    const onMessage = vi.fn();
    const onOpen = vi.fn();
    const handle = connectWithRetry(URL_A, { onMessage, onOpen });
    const gen = latest();
    handle.close();

    expect(gen.onmessage).toBeNull(); // 鏡射 watchdog 放棄路徑:先卸 handler 再 close
    expect(gen.onopen).toBeNull();
    expect(gen.onerror).toBeNull();

    gen.emit({ type: "corr", late: true }); // 遲到的資料 frame
    gen.onopen?.(); // 遲到的 open(Chromium 握手完成得比 close 慢)
    expect(onMessage).not.toHaveBeenCalled();
    expect(onOpen).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0); // 沒被 sticky 武裝出殘留 interval
  });

  // 由「sticky:同 URL 的後續世代 onopen 即武裝」改寫(N035):不再需要任何一代先收過 ping。
  it("後續世代 onopen 即武裝(無需任何一代先收過 ping)", () => {
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    const gen1 = latest();
    gen1.onopen?.(); // gen1 全程沒收過 ping
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    gen1.onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);

    const gen2 = latest();
    gen2.onopen?.(); // gen2 同樣收不到任何訊息(含 ping)
    vi.advanceTimersByTime(35_000);
    expect(gen2.closed).toBe(true);
    expect(FakeWS.instances.length).toBe(2);

    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(3);
    handle.close();
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

    // T3:那個 tick 不只「不判定」,還要把基準重置成 now —— 否則下一個(正常間隔的)tick
    // 就會拿凍結前的 lastMsgAt 判定靜默,防誤判只延後一個 tick 而已。
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS);
    expect(onClose).not.toHaveBeenCalled();

    vi.advanceTimersByTime(35_000); // 重置後才是真靜默
    expect(onClose).toHaveBeenCalledTimes(1);
    handle.close();
  });

  // N038:8 條 WS 對同一顆半死 server 會在同一個 5 s 窗齊判定 → 放棄路徑加 [0, jitter) 抖動,
  // onclose 路徑不加(上方 backoff 三分支的逐毫秒案不動)。
  it("watchdog 放棄後的重連延遲 = backoff + floor(random × jitter)(N038)", () => {
    randomSpy.mockReturnValue(0.5);
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    const gen1 = latest();
    gen1.onopen?.();
    vi.advanceTimersByTime(35_000); // 放棄 gen1(存活遠超 minUptime → 基礎延遲 1 s)
    expect(gen1.closed).toBe(true);

    vi.advanceTimersByTime(WS_BACKOFF_START_MS + WS_WATCHDOG_JITTER_MS / 2 - 1);
    expect(FakeWS.instances.length).toBe(1); // 1 499 ms:還差 1 ms
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(2); // 1 000 + 500

    // 下一輪 backoff 以「未加 jitter 的 delay」倍增:gen2 短命 → 2 000 ms 整,不是 3 000
    const gen2 = latest();
    gen2.onopen?.();
    gen2.onclose?.();
    vi.advanceTimersByTime(1_999);
    expect(FakeWS.instances.length).toBe(2);
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(3);
    handle.close();
  });

  it("onclose 路徑不加 jitter(random 非 0 時自然斷線仍 1 s 整;W1)", () => {
    randomSpy.mockReturnValue(0.9);
    const handle = connectWithRetry(URL_A, { onMessage: () => {} });
    latest().onopen?.();
    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    latest().onclose?.();
    vi.advanceTimersByTime(WS_BACKOFF_START_MS - 1);
    expect(FakeWS.instances.length).toBe(1);
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(2);
    handle.close();
  });
});

/** N037:隱藏分頁 > 5 min 的 Chrome intensive throttling 把 5 s tick 拉成 1/min → 每個 tick 都撞
 *  凍結守門(Edge 13)恆不判定;回前景後第一個 tick 一樣被吞,最壞再等 35 s。
 *  回前景時重設 tick 基準,讓緊接的下一個 tick(≤ 5 s)以真實 lastMsgAt 判定。 */
describe("connectWithRetry visibilitychange 回前景", () => {
  const URL_V = "ws://host/ws/vis";
  let visibility: DocumentVisibilityState = "visible";
  let randomSpy: ReturnType<typeof vi.spyOn>;

  const setVisibility = (next: DocumentVisibilityState): void => {
    visibility = next;
    document.dispatchEvent(new Event("visibilitychange"));
  };

  beforeEach(() => {
    visibility = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibility,
    });
    randomSpy = vi.spyOn(Math, "random").mockReturnValue(0);
  });

  afterEach(() => {
    delete (document as unknown as { visibilityState?: unknown }).visibilityState;
    randomSpy.mockRestore();
  });

  /** 模擬「隱藏 6 分鐘、tick 被節流到沒跑」:牆鐘走、timer 不走(與 Edge 13 同手法)。 */
  const hideFor = (ms: number): void => {
    setVisibility("hidden");
    vi.setSystemTime(Date.now() + ms);
  };

  it("節流期間半死 → 回前景後下一個 tick(≤ 5 s)就判定重連,不再多等 35 s", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_V, { onMessage: () => {}, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" });

    hideFor(6 * 60_000); // 期間零訊息(server 半死)
    setVisibility("visible");
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS);

    expect(gen1.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    expect(FakeWS.instances.length).toBe(2);
    handle.close();
  });

  it("節流期間訊息照常(健康)→ 回前景不重連(W4 對照組)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_V, { onMessage: () => {}, onClose });
    const gen1 = latest();
    gen1.onopen?.();
    gen1.emit({ type: "ping" });

    hideFor(6 * 60_000);
    gen1.emit({ type: "ping" }); // 節流不影響 onmessage:回前景前最後一則心跳仍到
    setVisibility("visible");
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS * 2);

    expect(gen1.closed).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
    expect(FakeWS.instances.length).toBe(1);
    handle.close();
  });

  it("轉 hidden 不觸發判定(仍由 Edge 13 守門)", () => {
    const onClose = vi.fn();
    const handle = connectWithRetry(URL_V, { onMessage: () => {}, onClose });
    latest().onopen?.();
    latest().emit({ type: "ping" });

    vi.setSystemTime(Date.now() + 40_000);
    setVisibility("hidden"); // 只是隱藏:不重設基準
    vi.advanceTimersByTime(WS_WATCHDOG_TICK_MS);
    expect(onClose).not.toHaveBeenCalled(); // 這個 tick 走凍結守門,只重置不判定
    handle.close();
  });

  it("close() / 放棄 / 自然斷線都拆掉 visibilitychange listener(零殘留)", () => {
    const add = vi.spyOn(document, "addEventListener");
    const remove = vi.spyOn(document, "removeEventListener");
    const visAdds = (): number => add.mock.calls.filter((c) => c[0] === "visibilitychange").length;
    const visRemoves = (): number =>
      remove.mock.calls.filter((c) => c[0] === "visibilitychange").length;

    const handle = connectWithRetry(URL_V, { onMessage: () => {} });
    latest().onopen?.(); // 武裝 → 掛 listener
    expect(visAdds()).toBe(1);

    vi.advanceTimersByTime(WS_MIN_UPTIME_MS);
    latest().onclose?.(); // 自然斷線 → 拆
    expect(visRemoves()).toBe(1);

    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    latest().onopen?.(); // gen2 武裝 → 再掛
    expect(visAdds()).toBe(2);
    vi.advanceTimersByTime(35_000); // watchdog 放棄 → 拆
    expect(visRemoves()).toBe(2);

    vi.advanceTimersByTime(WS_BACKOFF_START_MS);
    latest().onopen?.(); // gen3 武裝
    expect(visAdds()).toBe(3);
    handle.close(); // close() → 拆
    expect(visRemoves()).toBe(3);
    add.mockRestore();
    remove.mockRestore();
  });
});
