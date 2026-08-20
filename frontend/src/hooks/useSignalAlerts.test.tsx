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
    // code 帶 id:讓 formatToastText 每則互異 —— 節流測試要能分辨「發的是哪一則」,
    // 全同文案會讓內容斷言退化成長度檢查(review TC-1)。
    code: id,
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
let notifiedTags: (string | undefined)[] = [];
let hidden = false;
/** context 狀態走 module 變數(getter 讀):hook 快取 AudioContext 單例,
 *  suspended 測試要能改到「早已建好的那個實例」的 state。 */
let ctxState = "running";
let resumes = 0;
let resumeRejects = false;
let contexts = 0;

class FakeAudioContext {
  constructor() {
    contexts += 1;
  }
  get state(): string {
    return ctxState;
  }
  currentTime = 0;
  destination = {};
  resume(): Promise<void> {
    resumes += 1;
    return resumeRejects ? Promise.reject(new Error("resume refused")) : Promise.resolve();
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
  constructor(title: string, options?: { tag?: string }) {
    notified.push(title);
    notifiedTags.push(options?.tag);
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  oscillators = 0;
  notified = [];
  notifiedTags = [];
  hidden = false;
  ctxState = "running";
  resumes = 0;
  resumeRejects = false;
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

  // handoff R4:tag 用唯一 sig.id 會讓背景分頁每則各佔一格,爆量疊成一排 ——
  // 固定 tag 讓跨窗的新通知覆蓋前一則(窗內由節流取首則,見下)。
  it("通知 tag 固定為 copycat-signal(OS 層合併),不用 sig.id", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(notifiedTags).toEqual(["copycat-signal"]);
  });

  // leading edge:窗內丟棄(b / b2 的文案從未出現),窗滿才放行下一則。
  // 文案互異(sig 的 code 帶 id)讓 toEqual 是真內容比對,不是長度檢查(review TC-1)。
  it("連發訊號 5 秒窗內只發第一則(含 4999ms 邊界),窗滿放行(節流)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const first = sig("a");
    act(() => {
      emitSignal(first);
      emitSignal(sig("b"));
    });
    expect(notified).toEqual([formatToastText(first)]);
    act(() => {
      vi.advanceTimersByTime(4_999);
      emitSignal(sig("b2"));
    });
    expect(notified).toEqual([formatToastText(first)]);
    const third = sig("c");
    act(() => {
      vi.advanceTimersByTime(1);
      emitSignal(third);
    });
    expect(notified).toEqual([formatToastText(first), formatToastText(third)]);
  });

  // spec Edge case 3:本輪要解的使用者症狀規模(爆量疊成一排);同時鎖住
  // 「節流閘不得往上吃掉 toast 佇列」(review TC-2)。
  it("背景爆量 20 則 → 恰 1 則通知,toast 佇列照常 4 + overflow 16", () => {
    hidden = true;
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      for (let i = 0; i < 20; i += 1) emitSignal(sig(`s${i}`));
    });
    expect(notified).toEqual([formatToastText(sig("s0"))]);
    expect(notifiedTags).toEqual(["copycat-signal"]);
    expect(hook.result.current.toasts.length).toBe(4);
    expect(hook.result.current.overflow).toBe(16);
  });

  it("窗內被 permission 擋掉的不消耗窗口:授權後首則照發", () => {
    hidden = true;
    FakeNotification.permission = "default";
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(notified).toEqual([]);
    FakeNotification.permission = "granted";
    const s = sig("b");
    act(() => emitSignal(s));
    expect(notified).toEqual([formatToastText(s)]);
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

  // handoff R4:suspended 時 currentTime 凍結,排出去的 osc.stop 永不執行 →
  // 已 start 的節點不可 GC,整天看盤只增不減。改成跳過該聲 + 嘗試 resume。
  it("AudioContext suspended → 跳過該聲不建節點,並嘗試 resume;toast 照出", () => {
    ctxState = "suspended";
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(oscillators).toBe(0);
    expect(resumes).toBe(1);
    expect(hook.result.current.toasts.length).toBe(1);
  });

  // review F2:autoplay 未解鎖時 resume() 會 pending 到取得手勢,每則都排一次
  // 等於把節點累積換成 pending promise 累積 —— in-flight 守門同時間只留一發。
  it("suspended 連發 3 則只 resume 一次(in-flight 守門),節點恆 0", () => {
    ctxState = "suspended";
    renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(sig("a"));
      emitSignal(sig("b"));
      emitSignal(sig("c"));
    });
    expect(oscillators).toBe(0);
    expect(resumes).toBe(1);
  });

  it("suspended 解除後恢復出聲(同一快取單例,不重建)", async () => {
    ctxState = "suspended";
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(oscillators).toBe(0);
    const before = contexts;
    await act(async () => {}); // flush resume 的 microtask,釋放 in-flight 旗標
    ctxState = "running";
    act(() => emitSignal(sig("b")));
    expect(oscillators).toBe(1);
    expect(contexts).toBe(before); // 白名單 5:單例不重建
  });

  // review F4:closed 的 context 永不復活、resume 必 reject —— 回收單例讓下一則
  // 重建新 context,否則整個 session 永久失聲。
  it("AudioContext closed → 不 resume、回收單例,下一則重建新 context 出聲", () => {
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("warm"))); // 先確保單例已建(隔離單跑也成立)
    const before = contexts;
    const beeped = oscillators;
    ctxState = "closed";
    act(() => emitSignal(sig("a")));
    expect(oscillators).toBe(beeped);
    expect(resumes).toBe(0);
    ctxState = "running";
    act(() => emitSignal(sig("b")));
    expect(contexts).toBe(before + 1);
    expect(oscillators).toBe(beeped + 1);
  });

  // review TC-3/F1:resume() 的 rejection 不會被同步 try/catch 攔到,.catch 是唯一
  // 防線 —— 拿掉它這條測試會以 unhandled rejection 炸紅。
  it("resume 被拒(autoplay / 系統)→ 靜默吞掉,無 unhandled rejection,toast 照出", async () => {
    ctxState = "suspended";
    resumeRejects = true;
    const hook = renderHook(() => useSignalAlerts());
    await act(async () => emitSignal(sig("a")));
    expect(oscillators).toBe(0);
    expect(resumes).toBe(1);
    expect(hook.result.current.toasts.length).toBe(1);
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
