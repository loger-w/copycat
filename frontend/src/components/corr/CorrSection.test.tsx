/** @vitest-environment jsdom */
/** 殼行為 —— CorrPage 換成同步 stub,測的是殼本身。
 *
 *  **2026-08-14 subtab 改版**:收合殼卸掉,掛載閘上移到 `IndexPage` 的 subtab 列 ——
 *  「非 corr subtab 零 mount / 零 WS」的鎖因此搬到 `IndexPage.test.tsx` (s1)(s7) 與
 *  `IndexPage.corr-lazy.test.tsx`。本檔剩下的是元件層最小契約:掛上就 mount 真身、
 *  unmount 就把 CorrPage 一起收掉(兩條 WS 靠 hook cleanup 才會斷)。
 *
 *  **為什麼要 stub 計數而不是 query DOM 就好**:lazy + Suspense 的失敗樣態是「永遠停在
 *  fallback」,而 `queryByTestId(...) === null` 對「沒 render」與「還在 suspend」是同一個
 *  答案 —— 斷言會 vacuously pass。故一律先 `findByTestId` 等 stub 真的 mount,
 *  卸載則斷言 unmount **計數 +1**(不是查不到)。
 *  lazy 真身(確認 mock 沒把整條路徑架空)另在 `CorrSection.lazy.test.tsx`。 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CorrSection } from "@/components/corr/CorrSection";

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

beforeEach(() => {
  window.localStorage.clear();
  counts.mount = 0;
  counts.unmount = 0;
  // 匿名 stub,純粹擋 jsdom 真的去連線 —— 「零 WS」的鎖在 IndexPage.test.tsx,
  // 本檔不對它斷言(review B-5)。
  vi.stubGlobal("WebSocket", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  // spy 還原放 afterEach(不是測試主體末尾):斷言先炸時,主體末尾的 mockRestore
  // 永遠不會執行,Storage.prototype 的 spy 會漏到後續測試(review A-2)。
  vi.restoreAllMocks();
});

describe("CorrSection", () => {
  it("(a) render 即 mount CorrPage(無收合鈕、零 OPEN_KEY 讀寫)", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    render(<CorrSection />);

    expect(await screen.findByTestId("corr-stub")).toBeTruthy();
    expect(counts.mount).toBe(1);
    expect(screen.queryByRole("button", { name: /相關係數/ })).toBeNull();

    // 元件層真契約是「零 storage 存取」(殼只做 lazy + Suspense)—— 只寫
    // `not.toContain(舊鍵)` 在 keys 恆空時是 vacuous:舊鍵改名或 spy 沒掛上都照樣綠。
    const keys = [...getItem.mock.calls, ...setItem.mock.calls].map((c) => String(c[0]));
    expect(keys).toEqual([]);
  });

  it("(d) unmount 把 CorrPage 一起收掉(hook cleanup 才會斷線)", async () => {
    const view = render(<CorrSection />);
    await screen.findByTestId("corr-stub");
    expect(counts.unmount).toBe(0);

    view.unmount();
    await act(async () => {});

    expect(counts.unmount).toBe(1);
    expect(screen.queryByTestId("corr-stub")).toBeNull();
  });
});
