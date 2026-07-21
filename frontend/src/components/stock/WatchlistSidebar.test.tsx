/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";

let fetchMock: ReturnType<typeof vi.fn>;
let putBodies: string[][];

beforeEach(() => {
  putBodies = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { codes: string[] };
      putBodies.push(body.codes);
      return new Response(JSON.stringify({ codes: body.codes }));
    }
    return new Response(JSON.stringify({ codes: ["2330", "5483"] }));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const QUOTES = {
  "2330": { p: 2_380_000, chg_pct: 2.59, vol: 12479, no_data: false },
  "5483": { p: null, chg_pct: null, vol: null, no_data: true },
};

describe("WatchlistSidebar", () => {
  it("渲染清單與即時報價;no_data 檔顯示無資料", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    expect(screen.getByText("2380")).toBeTruthy(); // 毫元 → 元
    expect(screen.getByText("+2.59%")).toBeTruthy();
    expect(screen.getByText("無資料")).toBeTruthy();
  });

  it("點列觸發 onSelect", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.click(screen.getByText("2330"));
    expect(onSelect).toHaveBeenCalledWith("2330");
  });

  it("輸入股號新增 → PUT 整份", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("輸入股號"), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("新增"));
    await waitFor(() => expect(putBodies).toEqual([["2330", "5483", "2317"]]));
  });

  it("刪除鈕移除該檔 → PUT 整份", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.click(screen.getAllByLabelText(/移除/)[0]!);
    await waitFor(() => expect(putBodies).toEqual([["5483"]]));
  });
});
