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
