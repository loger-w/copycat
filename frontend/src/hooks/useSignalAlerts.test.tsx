/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSignalAlerts } from "@/hooks/useSignalAlerts";
import { emitSignal } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";

function sig(id: string): SignalMsg {
  return {
    type: "signal",
    id,
    kind: "surge",
    // code 帶 id:讓每則 toast 文案互異 —— 節流測試要能分辨「發的是哪一則」,
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

/** `sig(id)` 一則的 toast / 通知文案,**逐字寫死**(不再拿 `formatToastText` 當期望值 ——
 *  實作與斷言同一顆函式時文案改壞 mutant 全綠,next-time 08-24 N013 留尾)。
 *  拆解:`代號(= id) 名稱(台積電) 訊號名(surge → 爆拉 +1.50%,pct 1.5 兩位小數帶正號)
 *  價格(1_234_500 毫元 → 1234.5)`,空格相接。 */
function toastText(id: string): string {
  return `${id} 台積電 爆拉 +1.50% 1234.5`;
}

/** 同一 tick 的一則:code / time 固定(= 合併鍵 `(code, time)`),kind 與 id 互異。
 *  `sig()` 的 code 帶 id 是為了節流測試分辨「發的是哪一則」,同 tick 案要的正好相反。 */

function tick(id: string, over: Partial<SignalMsg>): SignalMsg {
  return { ...sig(id), code: "2330", ...over };
}

/** SC-1 的三則同 tick 訊號(CDP 穿越 + 爆拉 + 爆量),到達序 a → b → c。
 *
 *  **三則 price 刻意互異**(review TQ-5):錨價取「最早到那則」是明示契約,三則同價時
 *  `items.at(-1)` 換成 `items[0]` 的 mutant 照樣綠 —— 文案尾巴的價格就是鑑別子。 */
const TICK_A = tick("a", { kind: "cdp_cross", levels: ["ah"], direction: "from_below", pct: null });
const TICK_B = tick("b", { kind: "surge", pct: 1.5, price: 1_240_000 });
const TICK_C = tick("c", { kind: "vol_burst", pct: 3, price: 1_250_000 });
/** 三則合併後的字面文案。價格 = 錨(TICK_A,1_234_500 → "1234.5"),**不是**最後到的
 *  TICK_C("1250.0");kind 段依到達序 a・b・c。 */
const TICK_TEXT = "2330 台積電 突破 CDP AH・爆拉 +1.50%・爆量 3.0 倍 1234.5";

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

  // TQ-3:手動關掉那張之後,合併索引也必須跟著清 —— 否則同鍵下一則會走 merge 分支,
  // setQueue 在佇列裡找不到那張直接原樣返回 = 訊號被靜靜吞掉(零畫面、零聲音)。
  it("dismiss 後同 (code,time) 再來 → 另開新張(索引已清,不被吞掉)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("dup")));
    const first = hook.result.current.toasts[0]!.key;
    act(() => hook.result.current.dismiss(first));
    expect(hook.result.current.toasts.length).toBe(0);
    act(() => emitSignal(sig("dup")));
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.key).not.toBe(first);
    expect(oscillators).toBe(2); // 新張 = 新一組 → 再嗶一聲
  });

  // D1'':合併鍵 = (code, time)。同 id 重發必然同鍵 → 併入既有那張(key 不變,避免
  // 卸載重掛閃爍);「key 互異」的原意由下面兩案(不同 code / 判為新張)保住。
  it("同 (code,time) 重發 → 併入同一張 toast(key 不變,不重嗶)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("dup")));
    const first = hook.result.current.toasts[0]!.key;
    act(() => emitSignal(sig("dup")));
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.key).toBe(first);
    expect(oscillators).toBe(1);
  });

  it("不同 code → 各自一張,key 互異(不會撞 React key)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(sig("a"));
      emitSignal(sig("b"));
    });
    const keys = hook.result.current.toasts.map((t) => t.key);
    expect(keys.length).toBe(2);
    expect(new Set(keys).size).toBe(2);
  });

  // A2:同鍵但舊那張快消失了(TTL 剩餘 < 1500ms)→ 另開新張,否則後到者可能只看得到
  // 一瞬間。兩張同鍵 toast 並存時 key 必須互異(React key 不撞)。
  it("同 (code,time) 但 TTL 剩餘 < 1500ms → 另開新張(key 互異、再嗶一聲)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("dup")));
    const first = hook.result.current.toasts[0]!.key;
    act(() => {
      vi.advanceTimersByTime(3_600); // 剩餘 1400ms
      emitSignal(sig("dup"));
    });
    expect(hook.result.current.toasts.length).toBe(2);
    expect(hook.result.current.toasts[0]?.key).not.toBe(first);
    expect(oscillators).toBe(2);
  });

  it("toast 文字 = 代號 名稱 訊號名 價格(字面量)", () => {
    const hook = renderHook(() => useSignalAlerts());
    const s = sig("a");
    act(() => emitSignal(s));
    expect(hook.result.current.toasts[0]?.text).toBe(toastText("a"));
  });
});

describe("useSignalAlerts — 同 tick 合併(SC-1 / SC-2)", () => {
  // SC-1:CDP 穿越 + 爆拉 + 爆量 同一 tick 打進來 —— 現況三張疊在右上角,合併後一張一行。
  it("同 tick 三則 → 一張 toast,文案 = 到達序 kind 段,key 不變", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(TICK_A));
    const key = hook.result.current.toasts[0]!.key;
    act(() => {
      emitSignal(TICK_B);
      emitSignal(TICK_C);
    });
    const [toast] = hook.result.current.toasts;
    expect(hook.result.current.toasts.length).toBe(1);
    expect(toast?.items.length).toBe(3);
    expect(toast?.text).toBe(TICK_TEXT);
    expect(toast?.key).toBe(key);
    expect(toast?.sig.id).toBe("a"); // 錨 = 最早到那則
  });

  // TQ-4 / D3:併入**不重設 TTL** —— 同一 tick 的一組本來就同時到,續命等於讓一組
  // 持續有訊號的標的永遠佔著版面。t=3000 併入(剩 2000ms ≥ 1500ms),TTL 仍在 t=5000 到期。
  it("併入既有那張不重設 TTL(t=3000 併入,仍於 t=5000 消失)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(TICK_A));
    act(() => {
      vi.advanceTimersByTime(3_000);
      emitSignal(TICK_B);
    });
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.items.length).toBe(2);
    act(() => vi.advanceTimersByTime(1_999)); // t=4999
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => vi.advanceTimersByTime(2)); // t=5001 = 首則的 t=0 + TTL 5000
    expect(hook.result.current.toasts.length).toBe(0);
  });

  // TQ-8:同 kind 兩條規則同一 tick 各發一則(rule_id 讓 id 互異,toast 文案
  // 一模一樣)—— 併成一張、kind 段只印一次(規則名在 rail 另行顯示,toast 不含)。
  it("同 tick 同 kind 兩條規則 → 一張一聲,kind 段只印一次", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(tick("r1", { kind: "surge", pct: 1.5, rule_name: "爆拉主規則" }));
      emitSignal(tick("r2", { kind: "surge", pct: 1.5, rule_name: "爆拉備援" }));
    });
    const [toast] = hook.result.current.toasts;
    expect(hook.result.current.toasts.length).toBe(1);
    expect(toast?.items.length).toBe(2);
    expect(toast?.text).toBe("2330 台積電 爆拉 +1.50% 1234.5"); // 一段,不是「爆拉…・爆拉…」
    expect(oscillators).toBe(1);
  });

  it("同 code 不同 time / 同 time 不同 code → 各自一張", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(TICK_A);
      emitSignal(tick("later", { time: "09:15:04" }));
      emitSignal(tick("other", { code: "2317" }));
    });
    expect(hook.result.current.toasts.length).toBe(3);
  });

  it("SC-2 嗶每組一聲:同 tick 三則 → 1 聲", () => {
    renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(TICK_A);
      emitSignal(TICK_B);
      emitSignal(TICK_C);
    });
    expect(oscillators).toBe(1);
  });

  it("SC-2 三個不同 tick → 3 聲", () => {
    renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(sig("x"));
      emitSignal(sig("y"));
      emitSignal(sig("z"));
    });
    expect(oscillators).toBe(3);
  });

  // A2:被擠進 overflow 的那張若被併入,要浮回可見區 —— 否則新到的那則等於沒顯示。
  it("併入 overflow 區的那張 → 移到佇列首(key / TTL 不變,總數不變)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(TICK_A));
    const key = hook.result.current.toasts[0]!.key;
    act(() => {
      for (let i = 0; i < 5; i += 1) emitSignal(sig(`s${i}`));
    });
    expect(hook.result.current.toasts.some((t) => t.key === key)).toBe(false);
    act(() => emitSignal(TICK_B));
    expect(hook.result.current.toasts[0]?.key).toBe(key);
    expect(hook.result.current.toasts[0]?.items.length).toBe(2);
    expect(hook.result.current.overflow).toBe(2);
  });

  // A3:舊張的 TTL drop 不得刪掉「同鍵新張」的合併索引(stale drop),否則新張再也併不進去。
  it("舊張 TTL 到期後,同鍵新訊號仍併入新張(stale drop 不刪新索引)", () => {
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("dup")));
    act(() => {
      vi.advanceTimersByTime(3_600); // 剩 1400ms → 另開新張
      emitSignal(sig("dup"));
    });
    const fresh = hook.result.current.toasts[0]!.key;
    act(() => vi.advanceTimersByTime(1_400)); // 舊張 TTL 到期 → drop(舊 key)
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => emitSignal(sig("dup")));
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.key).toBe(fresh);
    expect(hook.result.current.toasts[0]?.items.length).toBe(2);
  });

  // R9:合併真值在 ref、setQueue updater 保持純函式 —— StrictMode 的 double-invoke
  // 下若把 items 累加寫進 updater,這裡會變成 6 則 / 兩張。
  it("StrictMode 下同 tick 三則仍是一張一聲(updater 純函式)", () => {
    let renders = 0;
    const hook = renderHook(
      () => {
        renders += 1;
        return useSignalAlerts();
      },
      { reactStrictMode: true },
    );
    // StrictMode 生效自檢:掛載一次 = render body 跑兩次(字面值,不寫不等式 ——
    // `toBeGreaterThanOrEqual` 連「wrapper 被拿掉但多渲染一次」都放過,自檢就失效了)。
    expect(renders).toBe(2);
    act(() => {
      emitSignal(TICK_A);
      emitSignal(TICK_B);
      emitSignal(TICK_C);
    });
    expect(hook.result.current.toasts.length).toBe(1);
    expect(hook.result.current.toasts[0]?.items.length).toBe(3);
    expect(hook.result.current.toasts[0]?.text).toBe(TICK_TEXT);
    expect(oscillators).toBe(1);
  });
});

describe("useSignalAlerts — Notification", () => {
  it("分頁隱藏且權限 granted → 300ms 合併窗尾發桌面通知(文案同 toast)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const s = sig("a");
    act(() => emitSignal(s));
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([toastText("a")]);
  });

  // TQ-2:桌面通知走的是**合併後**文案(pendingRef 存的是 handler 算好的 text)——
  // 期望寫字面量,不由 formatGroupToastText 算回來(同源 = 同義反覆,skill frontend-testing)。
  it("背景同 tick 三則 → 一則通知,文案 = 合併文案(字面量)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    act(() => {
      emitSignal(TICK_A);
      emitSignal(TICK_B);
      emitSignal(TICK_C);
    });
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([
      "2330 台積電 突破 CDP AH・爆拉 +1.50%・爆量 3.0 倍 1234.5",
    ]);
  });

  // A4:推進量 < TTL,確保「沒通知」不是因為 toast 早就沒了(否則斷言 vacuous)
  it("分頁可見 → 不發通知(toast 已經看得到)", () => {
    hidden = false;
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => vi.advanceTimersByTime(400));
    expect(notified).toEqual([]);
  });

  it("權限非 granted → 不發通知;轉 granted 後新訊號照發", () => {
    hidden = true;
    FakeNotification.permission = "default";
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([]);
    FakeNotification.permission = "granted";
    const s = sig("b");
    act(() => emitSignal(s));
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([toastText("b")]);
  });

  // Edge 4(a):排程時是背景,timer 到期時人已回到前景 → 丟棄(前景有 toast,
  // 再跳一則 OS 通知是重複打擾)。
  it("背景排程後轉前景 → 到期丟棄,不發通知", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    act(() => {
      vi.advanceTimersByTime(100);
      hidden = false;
    });
    act(() => vi.advanceTimersByTime(500)); // t=600:timer 觸發,前景 → 丟棄
    expect(notified).toEqual([]);
    // TQ-7:丟棄的那則**不記帳** —— 誤寫 lastNotifyRef 的話下一則要等到 t≈5600,
    // 人切回背景後的第一則訊號整整五秒收不到通知。
    const s = sig("b");
    act(() => {
      hidden = true;
      emitSignal(s);
    });
    act(() => vi.advanceTimersByTime(300)); // t=900 = 600 + COALESCE_MS
    expect(notified).toEqual([toastText("b")]);
  });

  // D5':pending 是**全域單槽**(固定 tag 本來就只有一格)—— 同一合併窗內不同標的
  // 只有最後一則進 OS。相對舊版 leading(看到最舊那則)是明示的行為改動。
  it("同一合併窗內不同標的 → 只有最後一則進 OS(latest-wins)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const b = sig("B");
    act(() => {
      emitSignal(sig("A"));
      vi.advanceTimersByTime(100);
      emitSignal(b);
    });
    act(() => vi.advanceTimersByTime(200));
    expect(notified).toEqual([toastText("B")]);
  });

  // handoff R4:tag 用唯一 sig.id 會讓背景分頁每則各佔一格,爆量疊成一排 ——
  // 固定 tag 讓跨窗的新通知覆蓋前一則(窗內由節流取首則,見下)。
  it("通知 tag 固定為 copycat-signal(OS 層合併),不用 sig.id", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    act(() => vi.advanceTimersByTime(300));
    expect(notifiedTags).toEqual(["copycat-signal"]);
  });

  // trailing:窗內只留**最後一則**(A1 絕對時刻表),窗尾補發 —— 舊 leading 會把
  // 未合併的首則推到 OS,固定 tag 又不能在 5s 內更新,人看到的永遠是最舊那則。
  // 文案互異(sig 的 code 帶 id)讓 toEqual 是真內容比對,不是長度檢查(review TC-1)。
  it("300ms 合併(發最後一則)+ lastSent+5s 窗尾補發(節流)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const b = sig("b");
    act(() => {
      emitSignal(sig("a"));
      emitSignal(b);
    });
    act(() => vi.advanceTimersByTime(299)); // t=299
    expect(notified).toEqual([]);
    act(() => vi.advanceTimersByTime(1)); // t=300:窗內最後一則
    expect(notified).toEqual([toastText("b")]);
    act(() => {
      vi.advanceTimersByTime(4_999); // t=5299
      emitSignal(sig("b2"));
    });
    expect(notified).toEqual([toastText("b")]);
    const third = sig("c");
    act(() => {
      vi.advanceTimersByTime(1); // t=5300:pending 覆寫為 c
      emitSignal(third);
    });
    act(() => vi.advanceTimersByTime(298)); // t=5598
    expect(notified).toEqual([toastText("b")]);
    act(() => vi.advanceTimersByTime(1)); // t=5599 = max(5299+300, 300+5000)
    expect(notified).toEqual([toastText("b"), toastText("c")]);
  });

  // TQ-1:上一案的 t=5299 emit 恰好落在「合併窗尾 = 節流窗尾」的重合點,兩個排程式子
  // 給同一個答案 —— 節流其實沒被鎖住。本案把第二則挪到 t=1000:合併窗尾 t=1300 已過,
  // 只有節流窗(lastSent 300 + 5000)撐到 t=5300,兩者差 4 秒,量得出來。
  it("節流窗晚於合併窗時以節流窗為準(t=1000 到達,t=5300 才發)", () => {
    hidden = true;
    renderHook(() => useSignalAlerts());
    const a = sig("a");
    act(() => emitSignal(a));
    act(() => vi.advanceTimersByTime(300)); // t=300:第一則發出,lastSent=300
    expect(notified).toEqual([toastText("a")]);
    const b = sig("b");
    act(() => {
      vi.advanceTimersByTime(700); // t=1000
      emitSignal(b);
    });
    act(() => vi.advanceTimersByTime(4_299)); // t=5299(合併窗尾 t=1300 早就過了)
    expect(notified.length).toBe(1);
    act(() => vi.advanceTimersByTime(1)); // t=5300 = lastSent 300 + 5000
    expect(notified.length).toBe(2);
    expect(notified).toEqual([toastText("a"), toastText("b")]);
  });

  // spec Edge case 3:本輪要解的使用者症狀規模(爆量疊成一排);同時鎖住
  // 「節流閘不得往上吃掉 toast 佇列」(review TC-2)。
  it("背景爆量 20 則 → 恰 1 則通知,toast 佇列照常 4 + overflow 16", () => {
    hidden = true;
    const hook = renderHook(() => useSignalAlerts());
    act(() => {
      for (let i = 0; i < 20; i += 1) emitSignal(sig(`s${i}`));
    });
    // 20 則 code 互異 → 不同合併鍵,佇列照舊 4 + 16(節流閘不得往上吃 toast,review TC-2)
    expect(hook.result.current.toasts.length).toBe(4);
    expect(hook.result.current.overflow).toBe(16);
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([toastText("s19")]); // trailing = 窗內最後一則
    expect(notifiedTags).toEqual(["copycat-signal"]);
  });

  // A5 絕對時刻表:誤把「被擋掉」也記帳的話,第二則要等到 t=5300 才發 —— t=610 抓得到。
  it("窗內被 permission 擋掉的不消耗窗口:授權後 310+300ms 照發", () => {
    hidden = true;
    FakeNotification.permission = "default";
    renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a"))); // t=0
    act(() => vi.advanceTimersByTime(300)); // t=300:timer 觸發但被擋
    expect(notified).toEqual([]);
    FakeNotification.permission = "granted";
    const s = sig("b");
    act(() => {
      vi.advanceTimersByTime(10); // t=310
      emitSignal(s);
    });
    act(() => vi.advanceTimersByTime(299)); // t=609
    expect(notified).toEqual([]);
    act(() => vi.advanceTimersByTime(1)); // t=610
    expect(notified).toEqual([toastText("b")]);
  });

  // TQ-6:只斷言「沒發通知」是半 vacuous —— pendingRef 被清空也會讓通知不發,timer
  // 本身仍活著。直接數 timer:一則背景訊號 = TTL timer + 通知 timer 各一,unmount 後歸零。
  it("unmount 清掉待發的通知 timer(離開頁面後不再冒出來)", () => {
    hidden = true;
    const hook = renderHook(() => useSignalAlerts());
    act(() => emitSignal(sig("a")));
    expect(vi.getTimerCount()).toBe(2); // TTL(5s)+ 通知合併窗(300ms)
    hook.unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(1_000));
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
    expect(hook.result.current.toasts.length).toBe(1);
    act(() => vi.advanceTimersByTime(300));
    expect(notified).toEqual([toastText("a")]);
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
