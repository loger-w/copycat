/** @vitest-environment jsdom */
/** `useFlashArm` 的行為合約。
 *
 *  這支 hook 是**唯一**掛 Esc / conn_lost 監聽與閒置計時的地方(自三座梯上提),
 *  而武裝是唯一繞過確認彈窗的路徑 —— 監聽掛錯層或 `active` 閘寫反,畫面上都毫無異狀。
 */
import { act, cleanup, fireEvent, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setCapitalWsStatus } from "@/hooks/useCapital";
import { useFlashArm } from "@/hooks/useFlashArm";
import { ARM_IDLE_MS } from "@/lib/flash-arm";

beforeEach(() => {
  setCapitalWsStatus("connecting"); // wsStatus module store 跨測試重置
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  setCapitalWsStatus("connecting");
});

describe("useFlashArm active(RightRail 持有的那一份)", () => {
  it("touch 後閒置 5 分鐘 → idle_timeout 解除", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useFlashArm());
    act(() => {
      result.current.touch();
      result.current.dispatch({ type: "toggle" });
    });
    expect(result.current.state.armed).toBe(true);
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(result.current.state.armed).toBe(false);
  });

  /** SC-5:鎖定態的閒置計時 **照排**,只是 `idle_timeout` 對它是 no-op —— 這則守的是
   *  「計時器送出去的到底是哪個事件」。改成送 `disarm`(或任何連 locked 一起清的事件)
   *  上面那則 5 分解除案照樣綠,鎖定態卻會在 5 分鐘後靜默解除。 */
  it("SC-5:鎖定後閒置 6 分鐘仍武裝且仍鎖定(idle_timeout 對鎖定態 no-op)", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useFlashArm());
    act(() => {
      result.current.dispatch({ type: "lock" });
      result.current.touch();
    });
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 60_000);
    });
    expect(result.current.state).toEqual({ armed: true, locked: true, failStreak: 0 });
  });

  it("Esc 解除(監聽只在武裝期間掛)", () => {
    const { result } = renderHook(() => useFlashArm());
    fireEvent.keyDown(window, { key: "Escape" }); // 未武裝時按也不該爆
    act(() => result.current.dispatch({ type: "toggle" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(result.current.state.armed).toBe(false);
  });

  it("capital WS 轉 closed → conn_lost 解除", () => {
    const { result } = renderHook(() => useFlashArm());
    act(() => result.current.dispatch({ type: "toggle" }));
    act(() => setCapitalWsStatus("open"));
    expect(result.current.state.armed).toBe(true);
    act(() => setCapitalWsStatus("closed"));
    expect(result.current.state.armed).toBe(false);
  });

  /** SC-13:conn_lost 只看 wsStatus 邊沿的話,「已經斷線了才鎖定」會讓鎖定態在斷線上
   *  無限存活(此後不再有 closed 的邊沿可觸發)。deps 帶 locked = level 觸發。 */
  it("WS 已是 closed 時鎖定 → 立即解除並清鎖定(level 觸發,非只邊沿)", () => {
    setCapitalWsStatus("closed");
    const { result } = renderHook(() => useFlashArm());
    act(() => result.current.dispatch({ type: "lock" }));
    expect(result.current.state).toEqual({ armed: false, locked: false, failStreak: 0 });
  });
});

describe("useFlashArm inactive(ladder 的本地備援)", () => {
  it("idle / Esc / conn_lost 三者皆不觸發(監聽不掛、計時不排)", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useFlashArm(false));
    act(() => {
      result.current.dispatch({ type: "toggle" });
      result.current.touch();
    });
    expect(result.current.state.armed).toBe(true);
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(result.current.state.armed).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(result.current.state.armed).toBe(true);
    act(() => setCapitalWsStatus("closed"));
    expect(result.current.state.armed).toBe(true);
  });
});

describe("useFlashArm 回傳契約(change-spec review R4 / SC-10)", () => {
  it("dispatch / touch 的 identity 跨 rerender 恆定", () => {
    const { result, rerender } = renderHook(() => useFlashArm());
    const dispatch = result.current.dispatch;
    const touch = result.current.touch;
    act(() => result.current.dispatch({ type: "toggle" }));
    rerender();
    rerender();
    expect(result.current.dispatch).toBe(dispatch);
    expect(result.current.touch).toBe(touch);
  });

  it("dispatch identity 不因 active 改變(ladder 從備援切成受控時不得換函式)", () => {
    const { result, rerender } = renderHook(({ a }) => useFlashArm(a), {
      initialProps: { a: true },
    });
    const dispatch = result.current.dispatch;
    rerender({ a: false });
    expect(result.current.dispatch).toBe(dispatch);
  });

  /** SC-10:state 純 in-memory 且**不在 module scope** —— 放到 module scope 的話
   *  reload 之外看不出差別,但同頁兩份 hook 會互相污染,而那是真錢武裝態。 */
  it("兩個獨立實例不共享 state", () => {
    const a = renderHook(() => useFlashArm());
    const b = renderHook(() => useFlashArm());
    act(() => a.result.current.dispatch({ type: "lock" }));
    expect(a.result.current.state).toEqual({ armed: true, locked: true, failStreak: 0 });
    expect(b.result.current.state).toEqual({ armed: false, locked: false, failStreak: 0 });
  });
});

// 🔴 N080:`CapitalConfirmDialog` 在 keydown 上 `stopPropagation()`(窗開著時 Esc 只作用
// 於窗)。React 19 把合成事件掛在 root container 上,冒泡到那裡就被截斷 → window 的
// **冒泡**監聽收不到 → 鎖定中 + 平倉確認窗開著時按 Esc 只關窗、武裝與鎖定原封不動,
// 而 `LOCK_TITLE` 白紙黑字寫著「Esc 仍會解除」。改 capture 相位:事件下行時 window 先收
// 一次,窗自己的處理一個字都沒被剝奪(兩邊各做各的)。
describe("useFlashArm 的 Esc 相位(N080)", () => {
  function withDialogLikeChild(): { root: HTMLDivElement; target: HTMLButtonElement } {
    const root = document.createElement("div");
    const target = document.createElement("button");
    root.appendChild(target);
    document.body.appendChild(root);
    return { root, target };
  }

  it("子樹在 keydown 上 stopPropagation 時,Esc 仍解除武裝", () => {
    const { root, target } = withDialogLikeChild();
    root.addEventListener("keydown", (e) => e.stopPropagation());
    const { result } = renderHook(() => useFlashArm());
    act(() => result.current.dispatch({ type: "toggle" }));
    expect(result.current.state.armed).toBe(true);
    fireEvent.keyDown(target, { key: "Escape" });
    expect(result.current.state.armed).toBe(false);
    root.remove();
  });

  it("鎖定態同理:Esc 連 locked 一起清(LOCK_TITLE 的承諾)", () => {
    const { root, target } = withDialogLikeChild();
    root.addEventListener("keydown", (e) => e.stopPropagation());
    const { result } = renderHook(() => useFlashArm());
    act(() => result.current.dispatch({ type: "lock" }));
    expect(result.current.state).toEqual({ armed: true, locked: true, failStreak: 0 });
    fireEvent.keyDown(target, { key: "Escape" });
    expect(result.current.state).toEqual({ armed: false, locked: false, failStreak: 0 });
    root.remove();
  });

  it("Esc 以外的鍵不受影響(capture 監聽不是把所有鍵都吃掉)", () => {
    const { root, target } = withDialogLikeChild();
    root.addEventListener("keydown", (e) => e.stopPropagation());
    const { result } = renderHook(() => useFlashArm());
    act(() => result.current.dispatch({ type: "toggle" }));
    fireEvent.keyDown(target, { key: "Enter" });
    expect(result.current.state.armed).toBe(true);
    root.remove();
  });
});
