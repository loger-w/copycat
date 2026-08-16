/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSignalAlerts } from "@/hooks/useSignalAlerts";
import { emitSignal } from "@/lib/signal-bus";
import { formatToastText, type SignalMsg } from "@/lib/signal-model";

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

/** 這兩個計數器由 fake 類別在呼叫當下累加;`beforeEach` 歸零(不重新綁定,
 *  hook 內若快取了 AudioContext 單例,舊實例的方法照樣寫到現在這份計數)。 */
let oscillators = 0;
let notified: string[] = [];
let hidden = false;

class FakeAudioContext {
  state = "running";
  currentTime = 0;
  destination = {};
  resume(): Promise<void> {
    return Promise.resolve();
  }
  createOscillator() {
    oscillators += 1;
    return {
      type: "",
      frequency: { value: 0, setValueAtTime: () => {} },
      connect: () => {},
      start: () => {},
      stop: () => {},
      onended: null as (() => void) | null,
    };
  }
  createGain() {
    return {
      gain: { value: 0, setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
      connect: () => {},
    };
  }
}

class FakeNotification {
  static permission = "granted";
  constructor(title: string) {
    notified.push(title);
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  oscillators = 0;
  notified = [];
  hidden = false;
  FakeNotification.permission = "granted";
  window.localStorage.clear();
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("Notification", FakeNotification);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useSignalAlerts — toast 佇列", () => {
  it("同時顯示上限 4,其餘以溢出計數呈現(連發 20 則)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      for (let i = 0; i < 20; i += 1) emitSignal(sig(`s${i}`));
    });
    expect(hook.result.current.toasts.length).toBe(4);
    expect(hook.result.current.overflow).toBe(16);
    // 新的在最上面 —— 爆量瞬間最舊那則不該卡住版面
    expect(hook.result.current.toasts[0]?.sig.id).toBe("s19");
  });

  it("每則 5 秒自動消失", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => vi.advanceTimersByTime(4_999));
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => vi.advanceTimersByTime(2));
    expect(hook.result.current.toasts.length).toBe(0);
    expect(hook.result.current.overflow).toBe(0);
  });

  it("dismiss 只移除指定那則", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(sig("a"));
      emitSignal(sig("b"));
    });
    const target = hook.result.current.toasts[0]!;
    act(() => hook.result.current.dismiss(target.key));
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.key).not.toBe(target.key);
  });

  it("同 id 重發(重啟後 cooldown 不持久)→ key 仍互異,不會撞 React key", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(sig("dup"));
      emitSignal(sig("dup"));
    });
    const keys = hook.result.current.toasts.map((t) => t.key);
    expect(keys.length).toBe(2);
    expect(new Set(keys).size).toBe(2);
  });

  it("toast 文字 = formatToastText(單一份文案來源)", () => {
    const hook = renderHook(() => useSignalAlerts());
    const s = sig("a");
    act(() => emitSignal(s));
    expect(hook.result.current.toasts[0]?.text).toBe(formatToastText(s));
  });
});

describe("useSignalAlerts — Notification", () => {
  it("分頁隱藏且權限 granted → 發桌面通知(文案同 toast)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const s = sig("a");
    act(() => emitSignal(s));
    expect(notified).toEqual([formatToastText(s)]);
  });

  it("分頁可見 → 不發通知(toast 已經看得到)", () => {
    hidden = false;
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(notified).toEqual([]);
    expect(hook.result.current.toasts.length).toBe(1);
  });

  it("權限非 granted → 不發通知", () => {
    hidden = true;
    FakeNotification.permission = "default";
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(notified).toEqual([]);
  });
});

describe("useSignalAlerts — 音效與靜音", () => {
  it("預設開:訊號進來出一聲短嗶", () => {
    const hook = renderHook(() => useSignalAlerts());
    expect(hook.result.current.soundOn).toBe(true);
    act(() => emitSignal(sig("a")));
    expect(oscillators).toBe(1);
  });

  // review MFS-1:原斷言是「靜音 → 也不發 Notification」,已裁決為事前已知該變 ——
  // 靜音的語意是「不要出聲」,不是「不要通知」(design §8.3 / SC-10);背景分頁若連
  // Notification 都被靜音關掉,人離開分頁就完全收不到訊號。
  it("靜音 → 不出聲,但背景分頁的 Notification 照發,toast 也照出(review MFS-1)", () => {
    hidden = true;
    const hook = renderHook(() => useSignalAlerts());
    act(() => hook.result.current.setSoundOn(false));
    const s = sig("a");
    act(() => emitSignal(s));
    expect(oscillators).toBe(0);
    expect(notified).toEqual([formatToastText(s)]);
    expect(hook.result.current.toasts.length).toBe(1);
  });

  it("靜音狀態落 localStorage,新 hook 讀得回來", () => {
    const first = renderHook(() => useSignalAlerts());
    act(() => first.result.current.setSoundOn(false));
    expect(window.localStorage.getItem("copycat-signal-sound")).toBe("off");
    first.unmount();

    const second = renderHook(() => useSignalAlerts());
    expect(second.result.current.soundOn).toBe(false);
  });

  it("AudioContext 不存在(舊瀏覽器)→ 靜默略過,toast 不受影響", () => {
    vi.stubGlobal("AudioContext", undefined);
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(hook.result.current.toasts.length).toBe(1);
  });

  it("unmount 後不再收訊號(bus 有退訂)", () => {
    const hook = renderHook(() => useSignalAlerts());
    hook.unmount();
    act(() => emitSignal(sig("a")));
    expect(oscillators).toBe(0);
    expect(notified).toEqual([]);
  });
});
