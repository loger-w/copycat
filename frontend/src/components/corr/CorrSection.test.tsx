/** @vitest-environment jsdom */
/** 閘門行為(展開/收合/持久化)—— CorrPage 換成同步 stub,測的是殼本身。
 *
 *  **為什麼要 stub 計數而不是 query DOM 就好**:lazy + Suspense 的失敗樣態是「永遠停在
 *  fallback」,而 `queryByTestId(...) === null` 對「沒 render」與「還在 suspend」是同一個
 *  答案 —— 斷言會 vacuously pass。故 (c)(d) 一律先 `findByTestId` 等 stub 真的 mount,
 *  收合則斷言 unmount **計數 +1**(不是查不到)。
 *  lazy 真身(確認 mock 沒把整條路徑架空)另在 `CorrSection.lazy.test.tsx`。 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CorrSection } from "@/components/corr/CorrSection";
import { CORR_OPEN_KEY } from "@/lib/constants";

const counts = vi.hoisted(() => ({ mount: 0, unmount: 0 }));

// factory 回 `{ default: Stub }` —— CorrPage 是 default export,漏了 lazy 解析直接炸。
// react 走 factory 內動態 import:vi.mock 被提升到 import 之上,直接引用檔頂的 binding
// 會在初始化前存取。
vi.mock("@/components/corr/CorrPage", async () => {
  const React = await import("react");
  function Stub() {
    React.useEffect(() => {
      counts.mount += 1;
      return () => {
        counts.unmount += 1;
      };
    }, []);
    return React.createElement("div", { "data-testid": "corr-stub" });
  }
  return { default: Stub };
});

const wsSpy = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  counts.mount = 0;
  counts.unmount = 0;
  wsSpy.mockClear();
  vi.stubGlobal("WebSocket", wsSpy);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function header(): HTMLElement {
  return screen.getByRole("button", { name: /相關係數/ });
}

describe("CorrSection", () => {
  it("(a) 預設收合:CorrPage 零 mount、零 WebSocket 建構", async () => {
    render(<CorrSection />);
    await act(async () => {});

    expect(header().getAttribute("aria-expanded")).toBe("false");
    expect(header().textContent).toContain("展開");
    expect(counts.mount).toBe(0);
    expect(wsSpy.mock.calls.length).toBe(0);
    expect(screen.queryByTestId("corr-stub")).toBeNull();
  });

  it("(c) 展開寫入 localStorage,重新 mount 仍展開", async () => {
    render(<CorrSection />);
    fireEvent.click(header());

    expect(await screen.findByTestId("corr-stub")).toBeTruthy();
    expect(counts.mount).toBe(1);
    expect(window.localStorage.getItem(CORR_OPEN_KEY)).toBe("1");
    expect(header().getAttribute("aria-expanded")).toBe("true");
    expect(header().textContent).toContain("收合");

    cleanup();
    render(<CorrSection />);

    expect(await screen.findByTestId("corr-stub")).toBeTruthy();
    expect(header().getAttribute("aria-expanded")).toBe("true");
  });

  it("(d) 收合把 CorrPage unmount(hook cleanup 才會斷線)", async () => {
    render(<CorrSection />);
    fireEvent.click(header());
    await screen.findByTestId("corr-stub");
    expect(counts.unmount).toBe(0);

    fireEvent.click(header());
    await act(async () => {});

    expect(counts.unmount).toBe(1);
    expect(screen.queryByTestId("corr-stub")).toBeNull();
    expect(window.localStorage.getItem(CORR_OPEN_KEY)).toBe("0");
    expect(header().getAttribute("aria-expanded")).toBe("false");
  });
});
