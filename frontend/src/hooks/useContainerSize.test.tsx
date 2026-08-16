/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useContainerSize } from "@/hooks/useContainerSize";

/** T-4。jsdom 沒有 ResizeObserver(是 undefined,不是壞掉的實作)—— hook 必須
 *  feature-detect 後回 {0,0},呼叫端據此退回固定尺寸常數,既有行為不變。 */

afterEach(() => {
  cleanup();
  // stub 只在需要量測的那條測試裡裝(第一條反過來要斷「ResizeObserver 不存在」)
  vi.unstubAllGlobals();
});

describe("useContainerSize", () => {
  // 🔴 WL-5:主 tab 以 `hidden` 保留 DOM,隱藏時 ResizeObserver 會回一次 0×0。照收的話
  // 切回來的第一幀畫的是 fallback 尺寸(圖跳一下),而 0×0 是「看不見」不是「沒有空間」。
  it("0×0 回呼被忽略,保留上一組有效量測(hidden tab 回來不跳一幀)", () => {
    let fire: ResizeObserverCallback | null = null;
    class FakeResizeObserver {
      constructor(cb: ResizeObserverCallback) {
        fire = cb;
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);

    const { result } = renderHook(() => useContainerSize<HTMLDivElement>());
    const node = document.createElement("div");
    act(() => result.current[0](node));
    expect(fire).not.toBeNull();

    const emit = (width: number, height: number): void => {
      act(() =>
        fire!(
          [{ target: node, contentRect: { width, height } } as ResizeObserverEntry],
          {} as ResizeObserver,
        ),
      );
    };

    emit(400, 300);
    expect(result.current[1]).toEqual({ width: 400, height: 300 });

    emit(0, 0);
    expect(result.current[1]).toEqual({ width: 400, height: 300 });
  });

  it("無 ResizeObserver 時回 {0,0} 且不拋", () => {
    expect(typeof ResizeObserver).toBe("undefined");
    const { result } = renderHook(() => useContainerSize<HTMLDivElement>());
    const [ref, size] = result.current;
    expect(size).toEqual({ width: 0, height: 0 });
    expect(typeof ref).toBe("function");
    // callback ref 被呼叫(mount / unmount)也不得拋
    expect(() => {
      ref(document.createElement("div"));
      ref(null);
    }).not.toThrow();
  });
});
