/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const NAMES = {
  names: [
    { code: "2330", name: "台積電" },
    { code: "2317", name: "鴻海" },
    { code: "2331", name: "精英" },
  ],
  count: 3,
};

const COLLAPSED_KEY = "copycat-stock-wl-collapsed";

/** 名稱表分支不能回空表 —— 空表下「名稱命中」的提示列永遠不可能成立(review R19)。 */
function respond(url: string, groups: Group[] = GROUPS): Response {
  if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
  return new Response(JSON.stringify({ groups }));
}

beforeEach(() => {
  window.localStorage.removeItem(COLLAPSED_KEY);
  putBodies = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as { groups: Group[] };
      putBodies.push(body.groups);
      return new Response(JSON.stringify({ groups: body.groups }));
    }
    return respond(url);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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

function sidebar() {
  return wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
}

async function waitGroups(): Promise<void> {
  await waitFor(() => expect(screen.getByTestId("wl-group-主力")).toBeTruthy());
}

// 🔴 round3 SC-5:自選側欄與中間主區之間要有可見分隔線
describe("WatchlistSidebar 版面(round3 SC-5)", () => {
  it("aside 右緣有 border 與中間區隔", () => {
    sidebar();
    const aside = screen.getByRole("complementary", { name: "自選清單" });
    expect(aside.className).toContain("border-r");
    expect(aside.className).toContain("border-line");
  });
});

// 🔴 round4 項 2:tab 制改成「所有群組各成一段」
describe("WatchlistSidebar(round4 項 2:群組全列出)", () => {
  it("所有群組同時可見,沒有 tab 列也沒有「全部」", async () => {
    sidebar();
    await waitGroups();
    expect(screen.getByTestId("wl-group-觀察")).toBeTruthy();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryByText("全部")).toBeNull();
  });

  it("一檔多組 → 該檔在兩組各出現一次(不再跨組去重)", async () => {
    sidebar();
    await waitGroups();
    expect(screen.getAllByText("2330")).toHaveLength(2);
    expect(within(screen.getByTestId("wl-group-主力")).getByText("5483")).toBeTruthy();
    expect(within(screen.getByTestId("wl-group-觀察")).getByText("3231")).toBeTruthy();
    // 2330 的報價在兩組各出現一次(同一份 quotes 餵兩處)
    expect(screen.getAllByText("2380")).toHaveLength(2); // 即時報價仍在
    expect(screen.getByText("無資料")).toBeTruthy(); // 5483 只在主力
  });

  it("點列觸發 onSelect", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    // 2330 同屬兩組 → 必須指定組別,不能用 getByText(review R3)
    fireEvent.click(within(screen.getByTestId("wl-group-主力")).getByText("2330"));
    expect(onSelect).toHaveBeenCalledWith("2330");
  });

  it("每組每列都有拖拉握把(不再有「全部」停用拖拉的狀態)", async () => {
    sidebar();
    await waitGroups();
    expect(screen.getAllByLabelText(/拖拉/)).toHaveLength(4); // 2+2
  });
});

describe("WatchlistSidebar 折疊(round4 SC-3)", () => {
  it("點折疊 → 該組列隱藏、標題仍在、其他組不受影響", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("折疊 主力"));
    expect(screen.getByTestId("wl-group-主力")).toBeTruthy();
    expect(screen.queryByTestId("wl-list-主力")).toBeNull();
    expect(screen.getByTestId("wl-list-觀察")).toBeTruthy();
    expect(screen.getByLabelText("展開 主力")).toBeTruthy();
  });

  it("折疊狀態落 localStorage 且重新掛載後維持", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("折疊 主力"));
    expect(JSON.parse(window.localStorage.getItem(COLLAPSED_KEY)!)).toEqual(["主力"]);
    cleanup();
    sidebar();
    await waitGroups();
    expect(screen.queryByTestId("wl-list-主力")).toBeNull();
  });
});

describe("WatchlistSidebar 搜尋提示列(round4 項 1)", () => {
  async function openAdd(group: string): Promise<void> {
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText(`新增到 ${group}`));
  }

  it("輸入名稱 → 提示列出現該檔代碼與名稱", async () => {
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "鴻海" } });
    const suggest = screen.getByTestId("stock-suggest");
    expect(within(suggest).getByText("2317")).toBeTruthy();
    expect(within(suggest).getByText("鴻海")).toBeTruthy();
  });

  it("輸入代碼 → 提示列出現同一檔", async () => {
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "2317" } });
    expect(within(screen.getByTestId("stock-suggest")).getByText("鴻海")).toBeTruthy();
  });

  it("點提示列 → 加入該群組(不是別組)", async () => {
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "鴻海" } });
    fireEvent.click(screen.getByLabelText("加入 2317 鴻海"));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["2330", "5483", "2317"] },
          { name: "觀察", codes: ["3231", "2330"] },
        ],
      ]),
    );
  });

  it("點「新增」鈕加入(W-4 的兩條路徑之一,不能只留 Enter)", async () => {
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("新增"));
    await waitFor(() => expect(putBodies[0]?.[0]?.codes).toEqual(["2330", "5483", "2317"]));
  });

  it("Enter + 提示列無命中 → 原樣當股號加入(W-4 / SC-1c)", async () => {
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "9958" } });
    expect(screen.queryByTestId("stock-suggest")).toBeNull();
    fireEvent.keyDown(screen.getByPlaceholderText("股號或名稱"), { key: "Enter" });
    await waitFor(() => expect(putBodies[0]?.[0]?.codes).toEqual(["2330", "5483", "9958"]));
  });

  it("名稱表不可用(空表)→ 提示列不出現,直接打股號仍可加入", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { groups: Group[] };
        putBodies.push(body.groups);
        return new Response(JSON.stringify({ groups: body.groups }));
      }
      if (url.includes("/api/stock/names")) {
        return new Response(JSON.stringify({ names: [], count: 0 }));
      }
      return new Response(JSON.stringify({ groups: GROUPS }));
    });
    await openAdd("主力");
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "2317" } });
    expect(screen.queryByTestId("stock-suggest")).toBeNull();
    fireEvent.keyDown(screen.getByPlaceholderText("股號或名稱"), { key: "Enter" });
    await waitFor(() => expect(putBodies[0]?.[0]?.codes).toEqual(["2330", "5483", "2317"]));
  });
});

describe("WatchlistSidebar 群組增刪(既有行為)", () => {
  it("新增群組:+ 群組 → 輸入名稱 → PUT 帶新空群組", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("新增群組"));
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: "當沖" } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
    await waitFor(() => expect(putBodies).toEqual([[...GROUPS, { name: "當沖", codes: [] }]]));
  });

  it("刪除群組:標題列的 × → PUT 不含該群組(股票留在其他群組)", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toEqual([[{ name: "主力", codes: ["2330", "5483"] }]]));
  });

  it("刪除群組成功 → localStorage 折疊清單不留該組名(不累積孤兒)", async () => {
    window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(["觀察", "主力"]));
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(COLLAPSED_KEY)!)).toEqual(["主力"]),
    );
  });

  // W-3:失敗時 cache 未動 → UI 不該先跳。改寫成有實體的斷言(review R14)
  it("刪除群組失敗(PUT 4xx)→ 錯誤文案出現、不發第二次 PUT、折疊狀態不變", async () => {
    window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(["觀察"]));
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        putBodies.push([]);
        return new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 });
      }
      return respond(url);
    });
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(putBodies).toHaveLength(1);
    expect(JSON.parse(window.localStorage.getItem(COLLAPSED_KEY)!)).toEqual(["觀察"]);
    expect(screen.getByTestId("wl-group-觀察")).toBeTruthy();
  });

  it("該組的 × 只從該組移除,另一組保留(不再有「全部」的跨組移除)", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(within(screen.getByTestId("wl-group-主力")).getByLabelText("移除 2330"));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["5483"] },
          { name: "觀察", codes: ["3231", "2330"] },
        ],
      ]),
    );
  });

  it("移組選單:checkbox 切換股票所屬群組(W-1 一檔多組)", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(within(screen.getByTestId("wl-group-主力")).getByLabelText("移組 5483"));
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

describe("WatchlistSidebar 零群組(SC-2b / W-16)", () => {
  beforeEach(() => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { groups: Group[] };
        putBodies.push(body.groups);
        return new Response(JSON.stringify({ groups: body.groups }));
      }
      return respond(url, []);
    });
  });

  it("顯示空狀態文案 + 搜尋框,加入後自動建「自選」組", async () => {
    sidebar();
    await waitFor(() => expect(screen.getByText("尚無自選,輸入股號新增")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("股號或名稱"), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("新增"));
    await waitFor(() => expect(putBodies).toEqual([[{ name: "自選", codes: ["2317"] }]]));
  });
});

// 🟢 round4 SC-4:跨群組拖曳。jsdom 的 getBoundingClientRect 恆 0 → 不 stub 的話
// 護欄退化成「clientX > 16 一律回 null」,負向測試會恆綠(假綠,review R17)。
describe("WatchlistSidebar 跨群組拖曳(SC-4)", () => {
  const RECTS: Record<string, [number, number]> = {
    "wl-group-主力": [0, 120],
    "wl-list-主力": [24, 120],
    "wl-group-觀察": [130, 250],
    "wl-list-觀察": [154, 250],
  };

  function stubRects(): void {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      const box = (top: number, bottom: number): DOMRect =>
        ({
          left: 0, right: 240, top, bottom, width: 240, height: bottom - top,
          x: 0, y: top, toJSON: () => ({}),
        }) as DOMRect;
      if (this.tagName === "ASIDE") return box(0, 600);
      const id = this.getAttribute("data-testid") ?? "";
      const span = RECTS[id];
      return span ? box(span[0], span[1]) : box(0, 0);
    });
  }

  function ptr(type: string, x: number, y: number): MouseEvent {
    // jsdom 沒有 PointerEvent;MouseEvent 帶 clientX/clientY 且 type 對得上即可
    return new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
  }

  async function startDrag(): Promise<void> {
    sidebar();
    await waitGroups();
    stubRects();
    const handle = within(screen.getByTestId("wl-group-主力")).getByLabelText("拖拉 5483");
    fireEvent(handle, ptr("pointerdown", 10, 80));
  }

  it("拖到別組放開 → 從來源組移除、插入目標組(移動語意)", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 100, 160));
    fireEvent(window, ptr("pointerup", 100, 160));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["2330"] },
          { name: "觀察", codes: ["5483", "3231", "2330"] },
        ],
      ]),
    );
  });

  it("拖到側欄外放開 → 零 PUT(不可逆搬組的護欄)", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 900, 160));
    fireEvent(window, ptr("pointerup", 900, 160));
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  it("拖曳中按 Esc → 之後放開手指也零 PUT(取消要涵蓋漏網的 pointerup)", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 100, 160));
    fireEvent(window, new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    fireEvent(window, ptr("pointerup", 100, 160));
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  it("同組內拖曳 = 排序(組別不變)", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 100, 24));
    fireEvent(window, ptr("pointerup", 100, 24));
    await waitFor(() =>
      expect(putBodies).toEqual([
        [
          { name: "主力", codes: ["5483", "2330"] },
          { name: "觀察", codes: ["3231", "2330"] },
        ],
      ]),
    );
  });

  it("空群組顯示「拖曳股票到此」(否則沒有高度 = 拖不進去的死組)", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") return new Response(JSON.stringify({ groups: [] }));
      return respond(url, [{ name: "空組", codes: [] }]);
    });
    sidebar();
    await waitFor(() => expect(screen.getByText("拖曳股票到此")).toBeTruthy());
  });
});
