/** @vitest-environment jsdom */
/** 漲跌停列表(market-overview R3 SC-3 / SC-4 / SC-5 的 vitest 面)。
 *
 *  空狀態判別子逐字照 design §5.2:`enabled=false` → 「FinMind 未設定」、
 *  `as_of == null` → 「載入中…」、`as_of != null` 且 rows 空 → 「暫無資料(延遲)」、
 *  篩選後 0 列 → 「無符合條件」;`stale` **只**管標題列膠囊,不參與空狀態分流(R18)。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LimitListSection } from "@/components/index/LimitListSection";
import { LIMIT_LIST_FILTER_KEY, LIMIT_LIST_OPEN_KEY } from "@/lib/constants";
import type { BreadthRow, BreadthRowsState } from "@/types";

function mkRow(stock_id: string, over: Partial<BreadthRow> = {}): BreadthRow {
  return {
    stock_id,
    name: `名${stock_id}`,
    market: "twse",
    close: 100,
    change_rate: 1.23,
    volume_ratio: 2.5,
    total_amount: 5e8,
    limit_up: false,
    limit_down: false,
    touched_limit_up: false,
    touched_limit_down: false,
    streak: null,
    streak_capped: false,
    ...over,
  };
}

function mkState(rows: BreadthRow[], over: Partial<BreadthRowsState> = {}): BreadthRowsState {
  return {
    enabled: true,
    trade_date: "2026-08-06",
    as_of: "10:31:00",
    stale: false,
    streaks_ready: true,
    rows,
    ...over,
  };
}

/** 排序 / 篩選共用的完整樣本:三組狀態 × 組內金額差 × streak 三態 × 一列無狀態。 */
const ROWS: BreadthRow[] = [
  mkRow("1103", { limit_up: true, streak: 5, streak_capped: true, total_amount: 1e8 }),
  mkRow("1101", { limit_up: true, streak: 3, total_amount: 9e8, name: "台泥", close: 55.5 }),
  mkRow("1102", { limit_up: true, streak: null, total_amount: 8e8 }),
  mkRow("6489", { limit_down: true, market: "tpex", total_amount: 7e8, close: null }),
  mkRow("6488", { limit_down: true, market: "tpex", total_amount: 3e8, close: 200 }),
  // 多狀態列:盤中觸及漲停後殺到跌停 → 歸屬 limit_down(優先序 R8),badge 唯一
  mkRow("2454", { limit_down: true, touched_limit_up: true, total_amount: 1e8 }),
  mkRow("2330", { touched_limit_up: true, total_amount: 20e8, volume_ratio: null, close: 1000 }),
  mkRow("2317", { touched_limit_down: true, total_amount: 2e8 }),
  mkRow("9999", { total_amount: 99e8 }), // 無任何狀態 → 不入表
];

let fetchSpy: ReturnType<typeof vi.fn>;

function stubFetch(state: BreadthRowsState): void {
  fetchSpy = vi.fn(async () => new Response(JSON.stringify(state)));
  vi.stubGlobal("fetch", fetchSpy);
}

/** 最近一次 render 用的 client —— refetch 情境要從測試側主動觸發第二次取數。 */
let client: QueryClient;

function newClient() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return client;
}

function renderSection(onOpenStock?: (code: string) => void, active?: boolean) {
  return render(
    <QueryClientProvider client={newClient()}>
      <LimitListSection onOpenStock={onOpenStock} active={active} />
    </QueryClientProvider>,
  );
}

/** 直接以「已展開」狀態開場(收合閘門另有專測),等資料落地後回傳。 */
async function openWith(
  state: BreadthRowsState,
  onOpenStock?: (code: string) => void,
): Promise<void> {
  window.localStorage.setItem(LIMIT_LIST_OPEN_KEY, "1");
  stubFetch(state);
  renderSection(onOpenStock);
  await screen.findByTestId("limit-list-body");
  await waitFor(() => expect(fetchSpy.mock.calls.length).toBeGreaterThan(0));
}

function rowIds(): string[] {
  return screen
    .getAllByTestId(/^limit-row-/)
    .map((el) => el.getAttribute("data-testid")!.replace("limit-row-", ""));
}

function header(): HTMLElement {
  return screen.getByRole("button", { name: /漲跌停/ });
}

beforeEach(() => {
  window.localStorage.clear();
  stubFetch(mkState(ROWS));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("LimitListSection 收合閘門", () => {
  it("預設收合:body 不 mount、零 fetch", async () => {
    renderSection();
    await waitFor(() => expect(header().getAttribute("aria-expanded")).toBe("false"));
    expect(screen.queryByTestId("limit-list-body")).toBeNull();
    expect(fetchSpy.mock.calls.length).toBe(0);
    expect(header().textContent).toContain("展開");
  });

  it("展開寫入 localStorage,重新 mount 仍展開", async () => {
    renderSection();
    fireEvent.click(header());
    await screen.findByTestId("limit-list-body");
    expect(window.localStorage.getItem(LIMIT_LIST_OPEN_KEY)).toBe("1");
    expect(header().getAttribute("aria-expanded")).toBe("true");
    expect(header().textContent).toContain("收合");

    cleanup();
    renderSection();
    expect(await screen.findByTestId("limit-list-body")).toBeTruthy();
  });

  it("收合把列表 unmount(query 隨之消失)", async () => {
    await openWith(mkState(ROWS));
    expect(screen.queryByTestId("limit-list-table")).toBeTruthy();

    fireEvent.click(header());

    expect(screen.queryByTestId("limit-list-body")).toBeNull();
    expect(screen.queryByTestId("limit-list-table")).toBeNull();
    expect(window.localStorage.getItem(LIMIT_LIST_OPEN_KEY)).toBe("0");
    expect(header().getAttribute("aria-expanded")).toBe("false");
  });
});

// FE-2:tab 是 `hidden` 保留而非 unmount(App 慣例)→ 展開狀態會跨 tab 存活。
// 這一組鎖的是「`active` 有真的接到 hook 上」,不是 hook 自己的 gate(那在
// useBreadthRows.test.ts)—— 少接這一根線,hook 測試照樣全綠。
describe("LimitListSection 背景輪詢 gate(FE-2)", () => {
  function openWithTimers(active?: boolean): void {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    window.localStorage.setItem(LIMIT_LIST_OPEN_KEY, "1");
    stubFetch(mkState(ROWS));
    renderSection(undefined, active);
  }

  it("active=false → 展開著也不背景輪詢(掛載仍抓一次)", async () => {
    openWithTimers(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchSpy.mock.calls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchSpy.mock.calls.length).toBe(1);
  });

  it("active 未給 → 預設 true,盤中照 10 秒輪詢", async () => {
    openWithTimers();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchSpy.mock.calls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchSpy.mock.calls.length).toBe(2);
  });
});

describe("LimitListSection 空狀態(判別子 = as_of)", () => {
  it("enabled=false → FinMind 未設定", async () => {
    await openWith(mkState([], { enabled: false, as_of: null, stale: true }));
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("FinMind 未設定");
  });

  it("as_of == null → 載入中…(stale 恆 true 的冷啟動不得誤判成有資料)", async () => {
    await openWith(mkState([], { as_of: null, stale: true }));
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("載入中…");
  });

  it("as_of != null 且 rows 空 → 暫無資料(延遲)", async () => {
    await openWith(mkState([], { as_of: "09:05:00", stale: true }));
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("暫無資料(延遲)");
  });

  it("stale=true 只出膠囊,有列時照常渲染表格", async () => {
    await openWith(mkState(ROWS, { stale: true }));
    const pill = screen.getByTestId("limit-list-stale");
    expect(pill.textContent).toContain("延遲");
    expect(pill.getAttribute("class")).toContain("amber");
    expect(screen.queryByTestId("limit-list-table")).toBeTruthy();
    expect(screen.queryByTestId("limit-list-msg")).toBeNull();
  });

  // 端點設計上恆 200,能走到 error 的只有網路 / proxy 斷。少了這條分流,失敗會停在
  // 「載入中…」永遠不動 —— 那是誠實度問題(看起來像還在等,其實已經放棄了)。
  it("HTTP 失敗 → 載入失敗(不可永遠停在「載入中…」)", async () => {
    window.localStorage.setItem(LIMIT_LIST_OPEN_KEY, "1");
    fetchSpy = vi.fn(async () => new Response("boom", { status: 500 }));
    vi.stubGlobal("fetch", fetchSpy);
    renderSection();
    await screen.findByTestId("limit-list-body");
    // hook 內 retry:1 → 要等一次重試(exponential backoff 初次 1s)
    await waitFor(() => expect(screen.getByTestId("limit-list-msg").textContent).toBe("載入失敗"), {
      timeout: 5000,
    });
  });

  // FE-1:TQ v5 的 `isError` 對 **refetch** 失敗同樣為 true。單看 `isError` 分流會讓
  // 「已經有一整張表、只是這一輪 10 秒輪詢沒抓到」整表消失換成「載入失敗」——
  // 盤中最需要看的那份資料因為一次網路抖動就被清掉。有 data 就保表,失敗改用膠囊說。
  it("已有資料後 refetch 失敗 → 表格保留,改以「更新失敗」膠囊示警", async () => {
    await openWith(mkState(ROWS));
    expect(rowIds().length).toBe(8);

    fetchSpy.mockImplementation(async () => new Response("boom", { status: 500 }));
    await act(async () => {
      await client.refetchQueries({ queryKey: ["breadth-rows"] });
    });
    // TQ 的 observer 通知走 notifyManager(macrotask 排程),act 只吃得到 microtask
    await waitFor(() => expect(screen.getByTestId("limit-list-refetch-error")).toBeTruthy());

    expect(screen.queryByTestId("limit-list-table")).toBeTruthy();
    expect(rowIds().length).toBe(8);
    expect(screen.queryByTestId("limit-list-msg")).toBeNull();
    expect(screen.getByTestId("limit-list-refetch-error").textContent).toContain("更新失敗");
  });

  it("stale=false → 無膠囊", async () => {
    await openWith(mkState(ROWS));
    expect(screen.queryByTestId("limit-list-stale")).toBeNull();
    expect(screen.queryByTestId("limit-list-refetch-error")).toBeNull();
  });

  // FE-4:「無符合條件」是操作結果(自己把篩選收太緊),「今日尚無漲跌停」是系統態
  // (全市場真的一檔都沒鎖)。共用一句文案會把後者說成前者 —— 使用者會去翻篩選找錯。
  it("狀態池為 0(全市場零漲跌停)→ 今日尚無漲跌停", async () => {
    await openWith(mkState([mkRow("9999"), mkRow("8888"), mkRow("7777")]));
    expect(screen.queryByTestId("limit-list-table")).toBeNull();
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("今日尚無漲跌停");
  });

  it("狀態池 > 0 但篩選後 0 列 → 無符合條件(與上一條分流)", async () => {
    await openWith(mkState(ROWS));
    fireEvent.change(screen.getByLabelText("金額(億)"), { target: { value: "999" } });
    expect(screen.queryByTestId("limit-list-table")).toBeNull();
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("無符合條件");
  });
});

describe("LimitListSection 表格內容", () => {
  it("預設排序:漲停(streak desc,null 視為 -1)→ 跌停 → 觸及,組內金額 desc", async () => {
    await openWith(mkState(ROWS));
    expect(rowIds()).toEqual(["1103", "1101", "1102", "6489", "6488", "2454", "2330", "2317"]);
  });

  it("連板欄三態:連 N 板 / N+ 板 / -,非漲停列空白", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-streak-1101").textContent).toBe("連 3 板");
    expect(screen.getByTestId("limit-streak-1103").textContent).toBe("5+ 板");
    expect(screen.getByTestId("limit-streak-1102").textContent).toBe("-");
    expect(screen.getByTestId("limit-streak-6488").textContent).toBe("");
    expect(screen.getByTestId("limit-streak-2330").textContent).toBe("");
  });

  it("狀態 badge 唯一,多狀態列依 limit_up > limit_down > touched 歸屬", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-badge-1101").textContent).toBe("漲停");
    expect(screen.getByTestId("limit-badge-2454").textContent).toBe("跌停"); // touched_limit_up 讓位
    expect(screen.getByTestId("limit-badge-2330").textContent).toBe("觸及未鎖");
  });

  it("金額以億元 1 位小數、量比 / 現價缺值顯示破折號", async () => {
    await openWith(
      mkState([
        mkRow("1101", { limit_up: true, streak: 1, total_amount: 3_640_000_000, close: 55.5 }),
        mkRow("1102", { limit_up: true, streak: 1, total_amount: null, close: null, volume_ratio: null }),
      ]),
    );
    expect(screen.getByTestId("limit-amount-1101").textContent).toBe("36.4");
    expect(screen.getByTestId("limit-amount-1102").textContent).toBe("—");
    expect(screen.getByTestId("limit-close-1102").textContent).toBe("—");
    expect(screen.getByTestId("limit-ratio-1102").textContent).toBe("—");
  });

  it("漲跌幅染色:漲紅(text-bull)/ 跌綠(text-bear)", async () => {
    await openWith(
      mkState([
        mkRow("1101", { limit_up: true, change_rate: 9.98 }),
        mkRow("6488", { limit_down: true, change_rate: -9.96 }),
      ]),
    );
    const up = screen.getByTestId("limit-change-1101");
    const down = screen.getByTestId("limit-change-6488");
    expect(up.textContent).toBe("+9.98%");
    expect(up.getAttribute("class")).toContain("text-bull");
    expect(down.textContent).toBe("-9.96%");
    expect(down.getAttribute("class")).toContain("text-bear");
  });

  it("市場欄印上市 / 上櫃", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-market-1101").textContent).toBe("上市");
    expect(screen.getByTestId("limit-market-6488").textContent).toBe("上櫃");
  });

  it("點列呼叫 onOpenStock(SC-5)", async () => {
    const onOpenStock = vi.fn();
    await openWith(mkState(ROWS), onOpenStock);
    fireEvent.click(screen.getByTestId("limit-row-1101"));
    expect(onOpenStock.mock.calls).toEqual([["1101"]]);
  });
});

describe("LimitListSection 篩選(OR 狀態 × AND 門檻)", () => {
  it("取消上櫃 → 上櫃列消失,上市列保留", async () => {
    await openWith(mkState(ROWS));
    fireEvent.click(screen.getByLabelText("上櫃"));
    expect(rowIds()).toEqual(["1103", "1101", "1102", "2454", "2330", "2317"]);
  });

  it("取消漲停 → 漲停列消失(狀態間為 OR)", async () => {
    await openWith(mkState(ROWS));
    fireEvent.click(screen.getByLabelText("漲停"));
    expect(rowIds()).toEqual(["6489", "6488", "2454", "2330", "2317"]);
  });

  it("只留觸及未鎖", async () => {
    await openWith(mkState(ROWS));
    fireEvent.click(screen.getByLabelText("漲停"));
    fireEvent.click(screen.getByLabelText("跌停"));
    expect(rowIds()).toEqual(["2330", "2317"]);
  });

  it("金額門檻單位億元;total_amount null 不過門檻", async () => {
    await openWith(
      mkState([
        mkRow("1101", { limit_up: true, total_amount: 9e8 }),
        mkRow("1102", { limit_up: true, total_amount: 4.9e8 }),
        mkRow("1103", { limit_up: true, total_amount: null }),
      ]),
    );
    fireEvent.change(screen.getByLabelText("金額(億)"), { target: { value: "5" } });
    expect(rowIds()).toEqual(["1101"]);
  });

  it("股價區間用 close;close null 不過區間篩", async () => {
    await openWith(
      mkState([
        mkRow("1101", { limit_up: true, close: 100, total_amount: 9e8 }),
        mkRow("1102", { limit_up: true, close: 30, total_amount: 8e8 }),
        mkRow("1103", { limit_up: true, close: 500, total_amount: 7e8 }),
        mkRow("1104", { limit_up: true, close: null, total_amount: 6e8 }),
      ]),
    );
    fireEvent.change(screen.getByLabelText("股價下限"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("股價上限"), { target: { value: "200" } });
    expect(rowIds()).toEqual(["1101"]);
  });

  it("門檻清空即恢復不限", async () => {
    await openWith(mkState(ROWS));
    const amount = screen.getByLabelText("金額(億)");
    fireEvent.change(amount, { target: { value: "50" } });
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("無符合條件");
    fireEvent.change(amount, { target: { value: "" } });
    expect(rowIds().length).toBe(8);
  });

  it("篩選後 0 列 → 無符合條件(與「暫無資料」分流)", async () => {
    await openWith(mkState(ROWS));
    fireEvent.click(screen.getByLabelText("上市"));
    fireEvent.click(screen.getByLabelText("上櫃"));
    expect(screen.queryByTestId("limit-list-table")).toBeNull();
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("無符合條件");
  });

  it("篩選寫入 localStorage,重新 mount 還原(SC-4)", async () => {
    await openWith(mkState(ROWS));
    fireEvent.click(screen.getByLabelText("上櫃"));
    fireEvent.change(screen.getByLabelText("金額(億)"), { target: { value: "2" } });

    const saved: unknown = JSON.parse(window.localStorage.getItem(LIMIT_LIST_FILTER_KEY)!);
    expect(saved).toMatchObject({ twse: true, tpex: false, minAmount: "2" });

    cleanup();
    stubFetch(mkState(ROWS));
    renderSection();
    await screen.findByTestId("limit-list-table");
    expect((screen.getByLabelText("上櫃") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("金額(億)") as HTMLInputElement).value).toBe("2");
    // 上櫃(6488/6489)出局 + 金額 < 2 億(1103 / 2454 各 1 億)出局
    expect(rowIds()).toEqual(["1101", "1102", "2330", "2317"]);
  });

  it("localStorage 壞值不炸,退回全開預設", async () => {
    window.localStorage.setItem(LIMIT_LIST_FILTER_KEY, "{壞掉的 JSON");
    await openWith(mkState(ROWS));
    expect(rowIds().length).toBe(8);
  });

  // FE-3:形狀對(是 object)但**逐欄型別不符**的 JSON 一路通過 `{...DEFAULT, ...parsed}`,
  // 門檻欄拿到 number 時 `threshold` 的 `raw.trim()` 直接 TypeError —— 而它在 render 路徑上、
  // 專案又沒有 ErrorBoundary,失效樣態是整頁白屏且清不掉(壞值留在 localStorage 裡)。
  it("localStorage 逐欄型別不符 → 該欄退回預設,畫面照常渲染", async () => {
    window.localStorage.setItem(
      LIMIT_LIST_FILTER_KEY,
      JSON.stringify({ minAmount: 5, twse: "yes", priceMin: null, priceMax: [], limitDown: 0 }),
    );
    await openWith(mkState(ROWS));
    expect(rowIds().length).toBe(8);
    expect((screen.getByLabelText("金額(億)") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("股價下限") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("股價上限") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("上市") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("跌停") as HTMLInputElement).checked).toBe(true);
  });

  it("合法欄位照常還原,壞欄不牽連好欄", async () => {
    window.localStorage.setItem(
      LIMIT_LIST_FILTER_KEY,
      JSON.stringify({ tpex: false, minAmount: 5, priceMin: "50" }),
    );
    await openWith(mkState(ROWS));
    expect((screen.getByLabelText("上櫃") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("股價下限") as HTMLInputElement).value).toBe("50");
    expect((screen.getByLabelText("金額(億)") as HTMLInputElement).value).toBe("");
  });
});
