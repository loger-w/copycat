/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ROW_H, WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import type { Group, Watchlist } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";

let fetchMock: ReturnType<typeof vi.fn>;
/** 整包 PUT body(v3 起 codes 與 groups 都是契約的一部分,只推 groups 會漏掉未分組) */
let putBodies: Watchlist[];

const GROUPS: Group[] = [
  { name: "主力", codes: ["2330", "5483"] },
  { name: "觀察", codes: ["3231", "2330"] },
];

/** 預設 fixture 的未分組是空的 —— 計數型斷言(2330 兩次 / 握把 4 個)依賴這個前提 */
const CODES = ["2330", "5483", "3231"];

const NAMES = {
  names: [
    { code: "2330", name: "台積電" },
    { code: "2317", name: "鴻海" },
    { code: "2331", name: "精英" },
  ],
  count: 3,
};

const COLLAPSED_KEY = "copycat-stock-wl-collapsed";
const UNGROUPED_KEY = "copycat-stock-wl-ungrouped-collapsed";

/** 名稱表分支不能回空表 —— 空表下「名稱命中」的提示列永遠不可能成立(review R19)。 */
function respond(url: string, groups: Group[] = GROUPS, codes: string[] = CODES): Response {
  if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
  return new Response(JSON.stringify({ codes, groups }));
}

/** GET 回指定自選、PUT 記錄整包 body 並原樣回傳 */
function mockWatchlist(groups: Group[], codes: string[]): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as Watchlist;
      putBodies.push(body);
      return new Response(JSON.stringify(body));
    }
    return respond(url, groups, codes);
  });
}

beforeEach(() => {
  window.localStorage.removeItem(COLLAPSED_KEY);
  window.localStorage.removeItem(UNGROUPED_KEY);
  putBodies = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as Watchlist;
      putBodies.push(body);
      return new Response(JSON.stringify(body));
    }
    return respond(url);
  });
  vi.stubGlobal("fetch", fetchMock);
});

/** 只看 groups 的斷言用它 —— codes 的斷言各測試自己指名,才不會被整包比對淹掉 */
function putGroups(): Group[][] {
  return putBodies.map((b) => b.groups);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const QUOTES = {
  // 2330:一般價位(未觸停)—— upper/lower 有值但現價沒踩到,亮燈不該亮
  "2330": {
    p: 2_380_000,
    chg_pct: 2.59,
    vol: 12479,
    ref: null,
    upper: 2_550_000,
    lower: 2_090_000,
    no_data: false,
  },
  "5483": {
    p: null,
    chg_pct: null,
    vol: null,
    ref: null,
    upper: null,
    lower: null,
    no_data: true,
  },
  // 3231:漲跌停不可得(舊後端 / 無漲跌幅商品)—— 一律不亮,不猜
  "3231": { p: 100_000, chg_pct: 0.5, vol: 10, ref: null, upper: null, lower: null, no_data: false },
};

function sidebar() {
  return wrap(<WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />);
}

async function waitGroups(): Promise<void> {
  await waitFor(() => expect(screen.getByTestId("wl-group-主力")).toBeTruthy());
}

function search(): HTMLElement {
  return screen.getByPlaceholderText("股號或名稱");
}

/** 群組 / 未分組的標題列(round4 項 4:整條 header 是一顆 button)。
 *  可及名稱由可見文字提供(組名 + 計數),不再是 `aria-label="折疊 X"` ——
 *  有了 `aria-expanded` 之後把狀態寫進名稱會重複播報而且可能不同步。 */
function groupHeader(name: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(name) });
}

/** StrictMode 下 render 側欄,附 **StrictMode 生效自檢**(review F-3)。
 *
 *  自檢訊號 = `useState` 的 lazy initializer 被 double-invoke:`loadCollapsed` 因此讀
 *  **兩次** localStorage。少了它,「只寫一次」這種上界斷言在單次 render 下**恆真** ——
 *  哪天 wrapper 被拿掉、或 React / RTL 改了 StrictMode 的行為,測試會靜默變成 vacuous
 *  (照樣綠,但什麼都沒守)。先例:`useRiver.test.ts` 的 `FakeWS.instances.length === 2`。 */
async function renderStrict() {
  const getItem = vi.spyOn(Storage.prototype, "getItem");
  const setItem = vi.spyOn(Storage.prototype, "setItem");
  wrap(
    <StrictMode>
      <WatchlistSidebar active={null} onSelect={() => {}} quotes={QUOTES} />
    </StrictMode>,
  );
  expect(getItem.mock.calls.filter((c) => c[0] === COLLAPSED_KEY)).toHaveLength(2);
  await waitGroups();
  return { setItem };
}

/** jsdom 沒有 PointerEvent;MouseEvent 帶 clientX/clientY 且 type 對得上即可 */
function ptrEvt(type: string, x: number, y: number): MouseEvent {
  return new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
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
    expect(screen.getAllByLabelText(/拖拉/)).toHaveLength(4); // 2+2,未分組為空
  });
});

// next-time 2026-07-31 條:側欄自選列的漲跌停亮燈。
describe("WatchlistSidebar 漲跌停亮燈", () => {
  function quotesWith(over: Record<string, unknown>) {
    return { ...QUOTES, "2330": { ...QUOTES["2330"], ...over } } as typeof QUOTES;
  }

  it("現價踩到漲停 → 整塊吃 bull 底色", async () => {
    wrap(
      <WatchlistSidebar
        active={null}
        onSelect={() => {}}
        quotes={quotesWith({ p: 2_550_000, chg_pct: 9.91 })}
      />,
    );
    await waitGroups();
    const cls = screen.getAllByTestId("wl-quote-2330")[0]!.className;
    expect(cls).toContain("bg-bull");
    expect(cls).not.toContain("bg-bear");
  });

  it("現價踩到跌停 → 整塊吃 bear 底色", async () => {
    wrap(
      <WatchlistSidebar
        active={null}
        onSelect={() => {}}
        quotes={quotesWith({ p: 2_090_000, chg_pct: -9.91 })}
      />,
    );
    await waitGroups();
    expect(screen.getAllByTestId("wl-quote-2330")[0]!.className).toContain("bg-bear");
  });

  it("未觸停 → 不亮(有 upper/lower 也一樣)", async () => {
    sidebar();
    await waitGroups();
    const cls = screen.getAllByTestId("wl-quote-2330")[0]!.className;
    expect(cls).not.toContain("bg-bull");
    expect(cls).not.toContain("bg-bear");
  });

  it("漲跌停不可得(舊後端 / 無漲跌幅商品)→ 一律不亮,**不用 chg_pct 猜**", async () => {
    wrap(
      <WatchlistSidebar
        active={null}
        onSelect={() => {}}
        // chg_pct 高達 +19.9%(ETF ±20% 情境):若用百分比猜就會誤亮
        quotes={quotesWith({ p: 2_780_000, chg_pct: 19.9, upper: null, lower: null })}
      />,
    );
    await waitGroups();
    const cls = screen.getAllByTestId("wl-quote-2330")[0]!.className;
    expect(cls).not.toContain("bg-bull");
    expect(cls).not.toContain("bg-bear");
  });
});

describe("WatchlistSidebar 的 v3 契約(codes 全體)", () => {
  it("PUT 一律帶 codes,且不屬任何群組的股票不會被洗掉", async () => {
    // 2317 在自選但不屬任何群組 —— 側欄若把 codes 算成「群組聯集」,它會被靜默刪除
    mockWatchlist(GROUPS, [...CODES, "2317"]);
    sidebar();
    await waitGroups();
    fireEvent.click(within(screen.getByTestId("wl-group-主力")).getByLabelText("移除 2330"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toContain("2317");
  });
});

describe("WatchlistSidebar 未分組桶(SC-8~11)", () => {
  it("未分組區塊列出不屬任何群組的股票", async () => {
    mockWatchlist(GROUPS, [...CODES, "2317"]);
    sidebar();
    await waitGroups();
    const ung = screen.getByTestId("wl-list-ungrouped");
    expect(within(ung).getByText("2317")).toBeTruthy();
    expect(within(ung).queryByText("2330")).toBeNull(); // 已屬群組 → 不在未分組
  });

  it("零群組時未分組列的 + 為停用(SC-9)", async () => {
    mockWatchlist([], ["2317"]);
    sidebar();
    // 未分組區塊本身一開始就在(空的也在)→ 要等到那一列真的長出來
    await waitFor(() => expect(screen.getByLabelText("加入群組 2317")).toBeTruthy());
    expect((screen.getByLabelText("加入群組 2317") as HTMLButtonElement).disabled).toBe(true);
  });

  it("+ → 選群組 → 該檔離開未分組、進該組(SC-10)", async () => {
    mockWatchlist(GROUPS, [...CODES, "2317"]);
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByLabelText("加入群組 2317"));
    fireEvent.click(screen.getByLabelText("加入 2317 到 主力"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putGroups()[0]![0]!.codes).toEqual(["2330", "5483", "2317"]);
    await waitFor(() =>
      expect(within(screen.getByTestId("wl-list-ungrouped")).queryByText("2317")).toBeNull(),
    );
  });

  it("群組列的 × 只從該組移除,該檔掉回未分組(不是從自選消失)", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(within(screen.getByTestId("wl-group-觀察")).getByLabelText("移除 3231"));
    await waitFor(() =>
      expect(putGroups()).toEqual([
        [
          { name: "主力", codes: ["2330", "5483"] },
          { name: "觀察", codes: ["2330"] },
        ],
      ]),
    );
    expect(putBodies[0]!.codes).toContain("3231");
    await waitFor(() =>
      expect(within(screen.getByTestId("wl-list-ungrouped")).getByText("3231")).toBeTruthy(),
    );
  });

  it("未分組列的 × 從自選整個移除", async () => {
    mockWatchlist(GROUPS, [...CODES, "2317"]);
    sidebar();
    await waitGroups();
    fireEvent.click(within(screen.getByTestId("wl-list-ungrouped")).getByLabelText("移除 2317"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(CODES);
  });

  it("未分組折疊獨立於群組折疊,且落 localStorage", async () => {
    mockWatchlist(GROUPS, [...CODES, "2317"]);
    sidebar();
    await waitGroups();
    fireEvent.click(groupHeader("未分組"));
    expect(screen.queryByTestId("wl-list-ungrouped")).toBeNull();
    expect(screen.getByTestId("wl-list-主力")).toBeTruthy();
    expect(window.localStorage.getItem(UNGROUPED_KEY)).toBe("1");
  });
});

describe("WatchlistSidebar 折疊(round4 SC-3)", () => {
  it("點折疊 → 該組列隱藏、標題仍在、其他組不受影響", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(groupHeader("主力"));
    expect(screen.getByTestId("wl-group-主力")).toBeTruthy();
    expect(screen.queryByTestId("wl-list-主力")).toBeNull();
    expect(screen.getByTestId("wl-list-觀察")).toBeTruthy();
    expect(groupHeader("主力").getAttribute("aria-expanded")).toBe("false");
  });

  it("折疊狀態落 localStorage 且重新掛載後維持", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(groupHeader("主力"));
    expect(JSON.parse(window.localStorage.getItem(COLLAPSED_KEY)!)).toEqual(["主力"]);
    cleanup();
    sidebar();
    await waitGroups();
    expect(screen.queryByTestId("wl-list-主力")).toBeNull();
  });

  // 🔴 react-doctor P1(WatchlistSidebar.tsx:104-131):`persistCollapsed` 寫在
  // `setCollapsed` 的 updater 內 —— React 的 updater 契約是純函式,而全站包在 StrictMode
  // (main.tsx)下 dev 會 double-invoke,每次折疊都寫兩次 localStorage。上一條「折疊狀態落
  // localStorage」只驗最終值,寫幾次不管;而 updater 內做副作用一旦遇到 React 的重播
  // (rebase / 中止的 render),持久化值與最終 state 就可能分歧。
  it("StrictMode 下點折疊 → 只寫一次 localStorage 且值正確", async () => {
    const { setItem } = await renderStrict();
    setItem.mockClear();

    fireEvent.click(groupHeader("主力"));

    const calls = setItem.mock.calls.filter((c) => c[0] === COLLAPSED_KEY);
    expect(calls).toHaveLength(1);
    expect(JSON.parse(String(calls[0]![1]))).toEqual(["主力"]);
  });

  // 🔒 lock(review F-4):`toggleUngroupedCollapsed` 走的是「直接形式」(boolean、純點擊
  // 路徑,不經 collapsedRef),與上一條的群組折疊是**各自獨立的寫入點** —— 只鎖群組那條,
  // 這條哪天被改回 updater 內 persist 沒有任何測試會紅。
  it("StrictMode 下點未分組折疊 → WL_UNGROUPED_KEY 只寫一次且值正確", async () => {
    const { setItem } = await renderStrict();
    setItem.mockClear();

    fireEvent.click(groupHeader("未分組"));

    const calls = setItem.mock.calls.filter((c) => c[0] === UNGROUPED_KEY);
    expect(calls).toHaveLength(1);
    expect(calls[0]![1]).toBe("1");
  });

  // 🔴 round4 項 4(B-6):整條標題可點,不再只有 ▸/▾ 那個 3px 寬的按鈕
  it("整條標題是一顆 button:點組名文字或計數同樣折疊", async () => {
    sidebar();
    await waitGroups();
    const header = groupHeader("主力");
    expect(header.tagName).toBe("BUTTON");
    // 點的是 header 內的組名 <span>,事件冒泡到 button
    fireEvent.click(within(header).getByText("主力"));
    expect(screen.queryByTestId("wl-list-主力")).toBeNull();
    fireEvent.click(within(header).getByText("2")); // 計數 badge
    expect(screen.getByTestId("wl-list-主力")).toBeTruthy();
  });

  it("aria-expanded 反映展開狀態,aria-controls 指向該組清單且是合法 id token", async () => {
    sidebar();
    await waitGroups();
    const header = groupHeader("主力");
    expect(header.getAttribute("aria-expanded")).toBe("true");
    const controls = header.getAttribute("aria-controls")!;
    // 組名可含空白,不能拿來拼 id(ID token list 會被拆成兩個不存在的 token)
    expect(controls).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(document.getElementById(controls)).toBe(screen.getByTestId("wl-list-主力"));
    fireEvent.click(header);
    expect(groupHeader("主力").getAttribute("aria-expanded")).toBe("false");
  });

  it("含空白的組名不會產生非法 id", async () => {
    mockWatchlist([{ name: "主力 觀察", codes: ["2330"] }], ["2330"]);
    sidebar();
    await waitFor(() => expect(screen.getByTestId("wl-group-主力 觀察")).toBeTruthy());
    const controls = groupHeader("主力 觀察").getAttribute("aria-controls")!;
    expect(controls).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(document.getElementById(controls)).toBeTruthy();
  });

  it("▸/▾ 是 aria-hidden 的狀態指示,不再是獨立按鈕(避免 SR 重複播報)", async () => {
    sidebar();
    await waitGroups();
    const header = groupHeader("主力");
    expect(header.querySelectorAll("button").length).toBe(0); // 巢狀 button 是非法 HTML
    const caret = within(header).getByText("▾");
    expect(caret.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByLabelText("折疊 主力")).toBeNull();
  });

  it("拖曳中點到標題不折疊(放開瞬間的時序守衛)", async () => {
    sidebar();
    await waitGroups();
    const handle = within(screen.getByTestId("wl-group-主力")).getByLabelText("拖拉 5483");
    fireEvent(handle, ptrEvt("pointerdown", 10, 80));
    fireEvent.click(groupHeader("主力"));
    expect(screen.getByTestId("wl-list-主力")).toBeTruthy();
    fireEvent(window, ptrEvt("pointerup", 10, 80));
  });
});

describe("WatchlistSidebar 頂部搜尋框(SC-7 / SC-8)", () => {
  it("零群組零股票時搜尋框仍在(W-16 的新實體)", async () => {
    mockWatchlist([], []);
    sidebar();
    await waitFor(() => expect(search()).toBeTruthy());
    expect(screen.getByText("查看")).toBeTruthy();
  });

  it("輸入名稱 → 提示列出現該檔代碼與名稱", async () => {
    sidebar();
    await waitGroups();
    fireEvent.change(search(), { target: { value: "鴻海" } });
    const suggest = screen.getByTestId("stock-suggest");
    expect(within(suggest).getByText("2317")).toBeTruthy();
    expect(within(suggest).getByText("鴻海")).toBeTruthy();
  });

  it("輸入代碼 → 提示列出現同一檔", async () => {
    sidebar();
    await waitGroups();
    fireEvent.change(search(), { target: { value: "2317" } });
    expect(within(screen.getByTestId("stock-suggest")).getByText("鴻海")).toBeTruthy();
  });

  // 🔴 round4 項 4(B-5):搜尋三條路徑一律改成**預覽**,不再直接寫進自選。
  // 「加入哪一組」交給分時圖上方的按鈕決定(StockPage)。
  it("點提示列 → 只預覽該檔(onSelect),不寫進自選", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    fireEvent.change(search(), { target: { value: "鴻海" } });
    fireEvent.click(screen.getByLabelText("查看 2317 鴻海"));
    expect(onSelect).toHaveBeenCalledWith("2317");
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
    expect(within(screen.getByTestId("wl-list-ungrouped")).queryByText("2317")).toBeNull();
  });

  it("點「查看」鈕 → 預覽提示列第一筆,零 PUT(W-4 兩條路徑之一)", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    fireEvent.change(search(), { target: { value: "2317" } });
    fireEvent.click(screen.getByText("查看"));
    expect(onSelect).toHaveBeenCalledWith("2317");
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  it("Enter + 提示列無命中 → 原樣當股號預覽(W-4)", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    fireEvent.change(search(), { target: { value: "9958" } });
    expect(screen.queryByTestId("stock-suggest")).toBeNull();
    fireEvent.keyDown(search(), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("9958");
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  it("已在自選的股票搜尋 → 一樣只預覽(零 PUT)", async () => {
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    fireEvent.change(search(), { target: { value: "2330" } });
    fireEvent.click(screen.getByText("查看"));
    expect(onSelect).toHaveBeenCalledWith("2330");
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  // self-review MC-8:搜尋框自己的 Escape(與拖曳取消的 Escape 是兩個不同 handler)
  it("搜尋框按 Esc → 清空輸入、收起提示列且零 PUT", async () => {
    sidebar();
    await waitGroups();
    fireEvent.change(search(), { target: { value: "2317" } });
    expect(screen.getByTestId("stock-suggest")).toBeTruthy();
    fireEvent.keyDown(search(), { key: "Escape" });
    await new Promise((r) => setTimeout(r, 30));
    expect((search() as HTMLInputElement).value).toBe("");
    expect(screen.queryByTestId("stock-suggest")).toBeNull();
    expect(putBodies).toEqual([]);
  });

  it("名稱表不可用(空表)→ 提示列不出現,直接打股號仍可加入", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Watchlist;
        putBodies.push(body);
        return new Response(JSON.stringify(body));
      }
      if (url.includes("/api/stock/names")) {
        return new Response(JSON.stringify({ names: [], count: 0 }));
      }
      // 這支刻意回**舊形狀**(只有 groups):守住「回應缺 codes → 前端用聯集補」的相容路徑
      return new Response(JSON.stringify({ groups: GROUPS }));
    });
    const onSelect = vi.fn();
    wrap(<WatchlistSidebar active={null} onSelect={onSelect} quotes={QUOTES} />);
    await waitGroups();
    fireEvent.change(search(), { target: { value: "2317" } });
    expect(screen.queryByTestId("stock-suggest")).toBeNull();
    fireEvent.keyDown(search(), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("2317");
  });

  it("PUT 失敗 → 側欄顯示對應的中文文案", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return new Response(JSON.stringify({ detail: { error: "WATCHLIST_FULL" } }), {
          status: 400,
        });
      }
      return respond(url);
    });
    sidebar();
    await waitGroups();
    // 搜尋改成預覽後不再發 PUT → 用仍會 PUT 的路徑(群組列的 ×)驗錯誤文案
    fireEvent.click(within(screen.getByTestId("wl-group-觀察")).getByLabelText("移除 3231"));
    await waitFor(() => expect(screen.getByText("自選已達 30 檔上限")).toBeTruthy());
  });
});

describe("WatchlistSidebar 管理入口(SC-13 / SC-15)", () => {
  it("側欄不再有 ⊞ / 群組標題的 + 與 ×", async () => {
    sidebar();
    await waitGroups();
    expect(screen.queryAllByLabelText(/移組/)).toHaveLength(0);
    expect(screen.queryByLabelText("新增到 主力")).toBeNull();
    expect(screen.queryByLabelText("刪除群組 主力")).toBeNull();
  });

  it("點「管理」開啟 Dialog", async () => {
    sidebar();
    await waitGroups();
    expect(screen.queryByText("管理群組與股票")).toBeNull(); // 關閉時內容不在 DOM
    fireEvent.click(screen.getByRole("button", { name: "管理群組與股票" }));
    expect(screen.getByText("管理群組與股票")).toBeTruthy();
  });

  // 🔴 自選未載入時 `wl` 是 EMPTY_WL fallback,而 Dialog 的「新增群組」/「加入股票」
  // 不依賴既有列(空清單上照樣能按)→ 會以空自選為基底整份 PUT(後端無樂觀鎖),
  // 真實自選被清空。入口 gate 掉是唯一保護點:commit 守衛比的就是 EMPTY_WL 自身。
  it("載入失敗 → 管理鈕不渲染(EMPTY_WL 上開 Dialog 新增群組會整份 PUT 清空自選)", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response("boom", { status: 500 });
    });
    const { container } = sidebar();
    // hook 是 retry: 1(覆寫 wrap 的 retry:false),error 終態要等退避跑完
    await waitFor(() => expect(screen.getByText("自選清單載入失敗")).toBeTruthy(), {
      timeout: 5000,
    });
    expect(screen.queryByRole("button", { name: "管理群組與股票" })).toBeNull();
    // Dialog 與按鈕同一個 gate:危險窗內連掛載都沒有(aria-label 兩者同名,改用元素選)
    expect(container.querySelector("dialog")).toBeNull();
  });

  it("自選尚未載入(pending)→ 管理鈕不渲染", () => {
    fetchMock.mockImplementation(async () => new Promise<Response>(() => {})); // 永不 resolve
    const { container } = sidebar();
    expect(screen.queryByRole("button", { name: "管理群組與股票" })).toBeNull();
    expect(container.querySelector("dialog")).toBeNull();
  });

  // W-20:collapsed state 與 localStorage 住在側欄,Dialog 測試觀察不到 → 必須在這一層驗
  it("在 Dialog 刪除群組成功 → localStorage 折疊清單不留該組名", async () => {
    window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(["觀察", "主力"]));
    sidebar();
    await waitGroups();
    fireEvent.click(screen.getByRole("button", { name: "管理群組與股票" }));
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(COLLAPSED_KEY)!)).toEqual(["主力"]),
    );
  });
});

// 🟢 round4 SC-4 + round5 SC-12:跨群組 / 未分組拖曳。jsdom 的 getBoundingClientRect 恆 0
// → 不 stub 的話護欄退化成「clientX > 16 一律回 null」,負向測試會恆綠(假綠,review R17)。
describe("WatchlistSidebar 拖曳(SC-12)", () => {
  const RECTS: Record<string, [number, number]> = {
    "wl-group-主力": [0, 120],
    "wl-list-主力": [24, 120],
    "wl-group-觀察": [130, 250],
    "wl-list-觀察": [154, 250],
    "wl-ungrouped": [260, 340],
    "wl-list-ungrouped": [284, 340],
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
      expect(putGroups()).toEqual([
        [
          { name: "主力", codes: ["2330"] },
          { name: "觀察", codes: ["5483", "3231", "2330"] },
        ],
      ]),
    );
  });

  // self-review FG-1:原本只驗 clientX=900,那個 x 超出「真實 bounds(right=240)」與
  // 「asideRef 沒接上時的退化 bounds(right=0)」**兩者**,所以測不出 bounds 是否真的來自
  // aside rect。下面這一對把右邊界釘在真實側欄寬度上:250 在 240+16 寬容內要成立、
  // 270 在寬容外要作廢 —— bounds 若退化成 {0,0},250 那支就會紅。
  it("貼著側欄右緣(寬容內)放開 → 照樣搬組", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 250, 160));
    fireEvent(window, ptr("pointerup", 250, 160));
    await waitFor(() => expect(putGroups()[0]?.[1]?.codes).toEqual(["5483", "3231", "2330"]));
  });

  it("剛超出側欄右緣寬容 → 零 PUT(右邊界釘在真實 aside 寬度)", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 270, 160));
    fireEvent(window, ptr("pointerup", 270, 160));
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  // self-review MC-7:折疊群組的 zone 幾何(listTop = section 下緣 → index = count)
  // 只有純函數層驗過;元件層的 `collapsed.has(name) || list === undefined` 接線沒驗過
  it("拖進折疊中的群組 → append 到該組尾端", async () => {
    sidebar();
    await waitGroups();
    fireEvent.click(groupHeader("觀察"));
    expect(screen.queryByTestId("wl-list-觀察")).toBeNull();
    stubRects();
    const handle = within(screen.getByTestId("wl-group-主力")).getByLabelText("拖拉 5483");
    fireEvent(handle, ptr("pointerdown", 10, 80));
    fireEvent(window, ptr("pointermove", 100, 140));
    fireEvent(window, ptr("pointerup", 100, 140));
    await waitFor(() =>
      expect(putGroups()).toEqual([
        [
          { name: "主力", codes: ["2330"] },
          { name: "觀察", codes: ["3231", "2330", "5483"] },
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
      expect(putGroups()).toEqual([
        [
          { name: "主力", codes: ["5483", "2330"] },
          { name: "觀察", codes: ["3231", "2330"] },
        ],
      ]),
    );
  });

  // W-22:拖起來放回原位 → 內容相同的 PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB),
  // 無錯誤訊號、無畫面差異
  it("放回原位(結果與現況相同)→ 零 PUT", async () => {
    await startDrag();
    fireEvent(window, ptr("pointermove", 100, 68));
    fireEvent(window, ptr("pointerup", 100, 68));
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toEqual([]);
  });

  it("群組 → 未分組 → 從**所有**群組移除(SC-12c)", async () => {
    sidebar();
    await waitGroups();
    stubRects();
    // 2330 同屬主力與觀察 —— 只移除來源組的話它會從畫面上憑空消失(仍屬觀察)
    const handle = within(screen.getByTestId("wl-group-主力")).getByLabelText("拖拉 2330");
    fireEvent(handle, ptr("pointerdown", 10, 30));
    fireEvent(window, ptr("pointermove", 100, 290));
    fireEvent(window, ptr("pointerup", 100, 290));
    await waitFor(() =>
      expect(putGroups()).toEqual([
        [
          { name: "主力", codes: ["5483"] },
          { name: "觀察", codes: ["3231"] },
        ],
      ]),
    );
    expect(putBodies[0]!.codes).toContain("2330");
  });

  it("未分組內拖曳 = 排序,群組成員在 codes 的相對位置不動", async () => {
    mockWatchlist([{ name: "主力", codes: ["2330"] }], ["2330", "5483", "3231"]);
    sidebar();
    await waitGroups();
    stubRects();
    // 未分組 = [5483, 3231];把 3231 拖到第一列
    const handle = within(screen.getByTestId("wl-list-ungrouped")).getByLabelText("拖拉 3231");
    fireEvent(handle, ptr("pointerdown", 10, 320));
    fireEvent(window, ptr("pointermove", 100, 286));
    fireEvent(window, ptr("pointerup", 100, 286));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(["2330", "3231", "5483"]);
    expect(putBodies[0]!.groups).toEqual([{ name: "主力", codes: ["2330"] }]);
  });

  it("空群組顯示「拖曳股票到此」(否則沒有高度 = 拖不進去的死組)", async () => {
    mockWatchlist([{ name: "空組", codes: [] }], []);
    sidebar();
    await waitFor(() => expect(screen.getByText("拖曳股票到此")).toBeTruthy());
  });
});

// 🔴 round4 項 4(自選列)+ 項 5(字級)
describe("WatchlistSidebar 列內容(round4 項 4 / 項 5)", () => {
  it("列出股票名稱(名冊有的檔)", async () => {
    sidebar();
    await waitGroups();
    // NAMES 有 2330 台積電;5483 / 3231 不在名冊 → 只顯示代號
    expect(screen.getAllByText("台積電").length).toBeGreaterThan(0);
  });

  it("代號與現價放大到 text-base,名稱與漲幅維持 text-xs", async () => {
    const { container } = sidebar();
    await waitGroups();
    const row = container.querySelector('[data-testid="wl-row-2330"]')!;
    expect(within(row as HTMLElement).getByText("2330").getAttribute("class")).toContain("text-base");
    expect(within(row as HTMLElement).getByText("2380").getAttribute("class")).toContain("text-base");
    expect(within(row as HTMLElement).getByText("台積電").getAttribute("class")).toContain("text-xs");
    expect(within(row as HTMLElement).getByText("+2.59%").getAttribute("class")).toContain("text-xs");
  });

  it("列高由 ROW_H 單一真值推導(拖曳落點幾何的分母,不得與 class 各寫一份)", async () => {
    const { container } = sidebar();
    await waitGroups();
    const row = container.querySelector('[data-testid="wl-row-2330"]') as HTMLElement;
    expect(row.style.height).toBe(`${ROW_H}px`);
  });

  it("尚無成交但有參考價 → 灰色參考價 + 灰字「參考」,不顯示 0.00%", async () => {
    const quotes = {
      ...QUOTES,
      "3231": {
        p: null,
        chg_pct: null,
        vol: null,
        ref: 99_500,
        upper: null,
        lower: null,
        no_data: false,
      },
    };
    const { container } = wrap(
      <WatchlistSidebar active={null} onSelect={() => {}} quotes={quotes} />,
    );
    await waitGroups();
    const row = container.querySelector('[data-testid="wl-row-3231"]') as HTMLElement;
    const price = within(row).getByText("99.5");
    expect(price.getAttribute("class")).toContain("text-ink-dim");
    expect(within(row).getByText("參考")).toBeTruthy();
    expect(within(row).queryByText("0.00%")).toBeNull();
  });

  it("無參考價也無成交 → 維持 `-`(不憑空編值)", async () => {
    const quotes = {
      ...QUOTES,
      "3231": {
        p: null,
        chg_pct: null,
        vol: null,
        ref: null,
        upper: null,
        lower: null,
        no_data: false,
      },
    };
    const { container } = wrap(
      <WatchlistSidebar active={null} onSelect={() => {}} quotes={quotes} />,
    );
    await waitGroups();
    const row = container.querySelector('[data-testid="wl-row-3231"]') as HTMLElement;
    expect(within(row).getAllByText("-").length).toBeGreaterThan(0);
    expect(within(row).queryByText("參考")).toBeNull();
  });

  it("no_data 仍優先顯示「無資料」(既有行為)", async () => {
    sidebar();
    await waitGroups();
    expect(screen.getAllByText("無資料").length).toBeGreaterThan(0);
  });
});
