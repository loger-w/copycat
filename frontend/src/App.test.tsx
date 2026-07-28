/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";

class FakeWS {
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {}

  close(): void {}
}

const INDEX_STATE = {
  trade_date: "2026-07-28",
  twse: {
    p: 42_039_920, ref: 43_634_190, high: 43_221_930, low: 41_815_780,
    stale: false, last_minute: null, minutes: { "0901": 43_000_000 },
  },
  otc: {
    p: 359_800, ref: 378_090, high: 373_420, low: 358_430,
    stale: false, last_minute: null, minutes: { "1017": 359_800 },
  },
  txf: { p: 42_142_000, time: "10:16:10" },
};

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/index/state")) {
        return new Response(JSON.stringify(INDEX_STATE));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App(index-board T9)", () => {
  it("nav 有「指數」tab 且 IndexBar 常駐(TXO tab 下可見)", async () => {
    render(<App />);
    expect(screen.getByRole("tab", { name: "指數" })).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/加權/).textContent).toContain("42039.92"));
    expect(screen.getByText(/櫃買/)).toBeTruthy();
    expect(screen.getByText(/台指/)).toBeTruthy();
  });

  it("切到指數 tab 顯示 IndexPage(台指期列與兩張卡)", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("tab", { name: "指數" }));
    await waitFor(() => expect(screen.getByText("加權指數")).toBeTruthy());
    expect(screen.getByText("櫃買指數")).toBeTruthy();
    expect(screen.getByText(/台指期/)).toBeTruthy();
  });
});
