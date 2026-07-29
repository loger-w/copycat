/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import type { Group } from "@/hooks/useStockWatchlist";

let fetchMock: ReturnType<typeof vi.fn>;
let putBodies: Group[][];

const GROUPS: Group[] = [
  { name: "主力", codes: ["2330", "5483"] },
  { name: "觀察", codes: ["3231", "2330"] },
];

beforeEach(() => {
  window.localStorage.removeItem("stock-wl-group");
  putBodies = [];
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { groups: Group[] };
      putBodies.push(body.groups);
      return new Response(JSON.stringify({ groups: body.groups }));
    }
    return new Response(JSON.stringify({ groups: GROUPS }));
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
  "3231": { p: 100_000, chg_pct: 0.5, vol: 10, no_data: false },
};

// 🔴 round3 SC-5:自選側欄與中間主區之間要有可見分隔線
describe("WatchlistSidebar 版面(round3 SC-5)", () => {
  it("aside 右緣有 border 與中間區隔", () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
    const aside = screen.getByRole("complementary", { name: "自選清單" });
    expect(aside.className).toContain("border-r");
    expect(aside.className).toContain("border-line");
  });
});

describe("WatchlistSidebar(SC-6 群組)", () => {
  it("群組 tab 列:全部 + 各群組;預設全部顯示聯集(去重)與即時報價", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "主力" })).toBeTruthy());
    expect(screen.getByRole("tab", { name: "全部" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByText("2330")).toHaveLength(1); // 跨群組去重
    expect(screen.getByText("5483")).toBeTruthy();
    expect(screen.getByText("3231")).toBeTruthy();
    expect(screen.getByText("2380")).toBeTruthy();
    expect(screen.getByText("無資料")).toBeTruthy();
  });

  it("點群組 tab 只顯示該群組股票", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "主力" })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "主力" }));
    expect(screen.getByText("2330")).toBeTruthy();
    expect(screen.queryByText("3231")).toBeNull();
  });

  it("點列觸發 onSelect", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.click(screen.getByText("2330"));
    expect(onSelect).toHaveBeenCalledWith("2330");
  });

  it("群組下新增 → 只加進該群組(R4)", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "主力" })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "主力" }));
    fireEvent.change(screen.getByPlaceholderText("輸入股號"), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("新增"));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["2330", "5483", "2317"] },
          { name: "觀察", codes: ["3231", "2330"] },
        ],
      ]),
    );
  });

  it("「全部」下新增 → 自動建「自選」群組(R4)", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("輸入股號"), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("新增"));
    await waitFor(() =>
      expect(putBodies).toEqual([[...GROUPS, { name: "自選", codes: ["2317"] }]]),
    );
  });

  it("「全部」下移除 = 從所有群組移除(R4)", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("移除 2330"));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["5483"] },
          { name: "觀察", codes: ["3231"] },
        ],
      ]),
    );
  });

  it("新增群組:+ 鈕 → 輸入名稱 → PUT 帶新空群組", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "主力" })).toBeTruthy());
    fireEvent.click(screen.getByLabelText("新增群組"));
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: "當沖" } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
    await waitFor(() => expect(putBodies).toEqual([[...GROUPS, { name: "當沖", codes: [] }]]));
  });

  it("刪除群組:tab 的 × → PUT 不含該群組(股票留在其他群組)", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "觀察" })).toBeTruthy());
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toEqual([[{ name: "主力", codes: ["2330", "5483"] }]]));
  });

  it("刪除群組失敗(PUT 4xx)→ active tab 不切走(review A2)", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 });
      }
      return new Response(JSON.stringify({ groups: GROUPS }));
    });
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "觀察" })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "觀察" }));
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(screen.getByRole("tab", { name: "觀察" }).getAttribute("aria-selected")).toBe("true");
  });

  it("「全部」下停用拖拉、群組下可拖拉", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    expect(screen.queryByLabelText(/拖拉/)).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "主力" }));
    expect(screen.getAllByLabelText(/拖拉/).length).toBe(2);
  });

  it("移組選單:checkbox 切換股票所屬群組", async () => {
    wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />);
    await waitFor(() => expect(screen.getByText("5483")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("移組 5483"));
    const checkbox = screen.getByRole("checkbox", { name: "觀察" });
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.click(checkbox);
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["2330", "5483"] },
          { name: "觀察", codes: ["3231", "2330", "5483"] },
        ],
      ]),
    );
  });
});
