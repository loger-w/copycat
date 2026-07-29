/** @vitest-environment jsdom */
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useContainerSize } from "@/hooks/useContainerSize";

/** T-4。jsdom 沒有 ResizeObserver(是 undefined,不是壞掉的實作)—— hook 必須
 *  feature-detect 後回 {0,0},呼叫端據此退回固定尺寸常數,既有行為不變。 */

afterEach(cleanup);

describe("useContainerSize", () => {
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
