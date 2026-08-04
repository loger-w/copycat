/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getSoundOn, useSignalSound } from "@/hooks/useSignalSound";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("useSignalSound", () => {
  it("預設開;切換落 localStorage", () => {
    const hook = renderHook(() => useSignalSound());
    expect(hook.result.current.soundOn).toBe(true);
    act(() => hook.result.current.setSoundOn(false));
    expect(hook.result.current.soundOn).toBe(false);
    expect(window.localStorage.getItem("copycat-signal-sound")).toBe("off");
  });

  // 這條就是把開關抽成獨立 store 的理由:切換鈕在個股頁的 SignalRail,發聲的訂閱者
  // 是 App 常駐的 useSignalAlerts —— 兩個不同的元件樹。各自 useState 時「關掉後照嗶
  // 到重新整理為止」,而畫面上開關明明是關的,完全看不出哪邊壞了。
  it("一處切換 → 另一處立即重讀(跨元件樹不漂)", () => {
    const rail = renderHook(() => useSignalSound());
    const alerts = renderHook(() => useSignalSound());
    act(() => rail.result.current.setSoundOn(false));
    expect(alerts.result.current.soundOn).toBe(false);
    // 非 React 的讀取路徑(useSignalAlerts 的 bus handler 讀當下值)也要跟上
    expect(getSoundOn()).toBe(false);
  });

  it("unmount 後不再被通知(訂閱有解除)", () => {
    const first = renderHook(() => useSignalSound());
    const second = renderHook(() => useSignalSound());
    first.unmount();
    act(() => second.result.current.setSoundOn(false));
    expect(getSoundOn()).toBe(false);
  });
});
