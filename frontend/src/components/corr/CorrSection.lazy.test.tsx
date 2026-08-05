/** @vitest-environment jsdom */
/** (b) lazy 真身:**不** mock CorrPage —— 證明 `CorrSection.test.tsx` 的 stub 沒把整條
 *  lazy 路徑架空(vi.mock 是檔案級 + hoisted,故獨立成檔)。
 *
 *  錨點取 RiverPanel 無資料時的「等待六腿資料…」:它只有真的 CorrPage mount 才會出現,
 *  與 Suspense fallback 的「相關係數載入中…」逐字可區分(CorrPanel 空狀態是「載入中…」,
 *  刻意不拿它當錨點)。 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CorrSection } from "@/components/corr/CorrSection";

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {}
}

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  // 兩支 hook 的初載 REST 都回 404 → state 維持 null(引擎未就緒的正常降級路徑)
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(null, { status: 404 }))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CorrSection(lazy 真身)", () => {
  it("(b) 展開後真的 mount CorrPage,不是停在 Suspense fallback", async () => {
    render(<CorrSection />);
    expect(screen.queryByText("等待六腿資料…")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /相關係數/ }));

    expect(await screen.findByText("等待六腿資料…")).toBeTruthy();
    expect(screen.queryByText("相關係數載入中…")).toBeNull();
    // 展開才建線:corr + river 各一條
    expect(FakeWS.instances.map((w) => w.url.replace(/^ws:\/\/[^/]+/, ""))).toEqual([
      "/ws/corr",
      "/ws/river",
    ]);
  });
});
