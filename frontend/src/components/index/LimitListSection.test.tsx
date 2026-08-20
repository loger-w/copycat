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
import { LIMIT_LIST_FILTER_KEY } from "@/lib/constants";
import { isoLocalDate } from "@/lib/trading-calendar";
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

/** fixture 的語意是「**今日**資料」—— 自 mod/trading-calendar SC-10 起 `trade_date` 是
 *  畫面上的判別子(≠ 本機今日就多一顆日期膠囊、空態文案也帶日期),寫死的日期會讓
 *  這份 fixture 隨時間漂成「非今日」。要測非今日一律在 `over` 明寫日期。 */
function mkState(rows: BreadthRow[], over: Partial<BreadthRowsState> = {}): BreadthRowsState {
  return {
    enabled: true,
    trade_date: isoLocalDate(new Date()),
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

/** render 即掛載(subtab 改版後本元件不再有收合殼),等資料落地後回傳。 */
async function openWith(
  state: BreadthRowsState,
  onOpenStock?: (code: string) => void,
): Promise<void> {
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

beforeEach(() => {
  window.localStorage.clear();
  stubFetch(mkState(ROWS));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  // spy 還原放 afterEach(不是測試主體末尾):斷言先炸時,主體末尾的 mockRestore
  // 永遠不會執行,Storage.prototype 的 spy 會漏到後續測試(review A-2)。
  vi.restoreAllMocks();
});

// 🔴 2026-08-14 收合殼卸掉 → 2026-08-16 subtab 機制整組退役:本元件現在**恆掛**在台股
// 綜合右欄,省輪詢完全靠 `active`(下一個 describe 鎖「線有沒有接上」,全鏈那一段在
// App.test.tsx「切離台股綜合 tab → 列表停止背景輪詢」)。
// 這裡剩下的元件級契約是:掛上就直接工作,且**完全不碰**那把已廢止的 open key。
describe("LimitListSection 掛載即工作(收合殼退役)", () => {
  it("render 即掛 body 並取數(無收合鈕)", async () => {
    renderSection();
    expect(await screen.findByTestId("limit-list-body")).toBeTruthy();
    await waitFor(() => expect(fetchSpy.mock.calls.length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: /展開|收合/ })).toBeNull();
  });

  it("零 OPEN_KEY 讀寫(廢止的鍵不得留旁路)", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderSection();
    await screen.findByTestId("limit-list-body");

    const keys = [...getItem.mock.calls, ...setItem.mock.calls].map((c) => String(c[0]));
    expect(keys).not.toContain("copycat-limit-list-open");
    // 正向對照:本元件確實會碰 storage(LimitListBody 讀 filter key),證明 spy 真的
    // 在錄 —— 少了這一條,`not.toContain` 對「spy 沒掛上」也會 vacuously 通過(review B-1)。
    expect(keys).toContain(LIMIT_LIST_FILTER_KEY);
  });
});

// FE-2:tab 是 `hidden` 保留而非 unmount(App 慣例)→ 本元件跨 tab 一直掛著。
// 這一組鎖的是「`active` 有真的接到 hook 上」,不是 hook 自己的 gate(那在
// useBreadthRows.test.ts)—— 少接這一根線,hook 測試照樣全綠。
describe("LimitListSection 背景輪詢 gate(FE-2)", () => {
  function openWithTimers(active?: boolean): void {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
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

// SC-10(R3/R12):非交易日開站時 rows 是**上一交易日收盤**的快照,而畫面上原本沒有
// 任何線索 —— 使用者看到的是一張「今天的漲跌停」。日期膠囊與空態文案把資料日說出來。
describe("LimitListSection 非今日資料的日期膠囊(SC-10)", () => {
  it("trade_date ≠ 本機今日 → MM-DD 收盤 膠囊(testid 獨立於 stale)", async () => {
    await openWith(mkState(ROWS, { trade_date: "2026-08-06" }));
    expect(screen.getByTestId("limit-list-asof-date").textContent).toBe("08-06 收盤");
    // R2-8:不得沿用 stale 的 testid / 語意 —— 「上一交易日的完整收盤資料」與
    // 「今天的資料延遲了」是兩件事,共用一顆膠囊會把前者說成後者(琥珀色警示)。
    expect(screen.queryByTestId("limit-list-stale")).toBeNull();
  });

  it("trade_date = 本機今日 → 無膠囊", async () => {
    await openWith(mkState(ROWS));
    expect(screen.queryByTestId("limit-list-asof-date")).toBeNull();
  });

  it("非今日且狀態池為 0 → 空態文案帶日期(不說成「今日」)", async () => {
    await openWith(mkState([mkRow("9999"), mkRow("8888")], { trade_date: "2026-08-06" }));
    expect(screen.getByTestId("limit-list-msg").textContent).toBe("08-06 尚無漲跌停");
    expect(screen.getByTestId("limit-list-asof-date").textContent).toBe("08-06 收盤");
  });

  it("trade_date 為 null(冷啟動未定)→ 不當成非今日,無膠囊", async () => {
    await openWith(mkState(ROWS, { trade_date: null }));
    expect(screen.queryByTestId("limit-list-asof-date")).toBeNull();
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

  // R3-T4:SC-3 的「哪幾檔」= 代號 **與名稱**;表頭九欄是這張表的欄位契約(design §5.2)。
  // 兩者原本零斷言 —— 名稱欄整欄改錯 / 少一欄 / 欄序調換都不會有任何測試變紅。
  it("名稱欄印個股名稱", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-name-1101").textContent).toBe("台泥");
    expect(screen.getByTestId("limit-name-6488").textContent).toBe("名6488");
  });

  it("表頭九欄文字與順序", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getAllByRole("columnheader").map((el) => el.textContent)).toEqual([
      "代號",
      "名稱",
      "市場",
      "現價",
      "漲跌幅",
      "連板",
      "金額(億)",
      "量比",
      "狀態",
    ]);
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

// 🔴 2026-08-16 一頁總覽:列表移進右欄框內、整高自帶捲軸。jsdom 不載 Tailwind CSS,
// 「有沒有真的捲」量不到(那條由 SC-3 的 DevTools 量測收),這裡鎖的是**捲動容器恆存**
// (文案態與表格態同一個節點,不是只有 rows 態才包)與 **sticky 掛在每個 th 上**。
describe("LimitListSection 內捲容器與 sticky 表頭(§4.1)", () => {
  it("捲動容器恆存:文案態與表格態都包在 limit-list-scroll 內", async () => {
    await openWith(mkState([]));
    const msgScroll = screen.getByTestId("limit-list-scroll");
    expect(msgScroll.className).toContain("overflow-auto");
    expect(msgScroll.className).toContain("min-h-0");
    expect(msgScroll.querySelector('[data-testid="limit-list-msg"]')).toBeTruthy();

    cleanup();
    await openWith(mkState(ROWS));
    const tableScroll = screen.getByTestId("limit-list-scroll");
    expect(tableScroll.className).toContain("overflow-auto");
    expect(tableScroll.className).toContain("min-h-0");
    expect(tableScroll.querySelector('[data-testid="limit-list-table"]')).toBeTruthy();
  });

  it("九欄表頭各自 sticky;分隔線走 inset shadow(border-collapse 下 border 不隨 sticky 黏)", async () => {
    await openWith(mkState(ROWS));
    const table = screen.getByTestId("limit-list-table");
    const ths = [...table.querySelectorAll("th")];
    expect(ths.length).toBe(9);
    for (const th of ths) {
      expect(th.className).toContain("sticky");
      expect(th.className).toContain("top-0");
      // 捲動時表頭底下是列內容,沒有底色會直接透出來
      expect(th.className).toContain("bg-surface");
      // WL-4:`border-collapse` 會把 th 的 border 併進表格的邊框模型交給 table 畫,
      // 而 table 不跟著 sticky 黏 → 捲到中段底線消失(finder 實測 scrollTop=260)。
      // inset shadow 畫在 th 自己的 box 上,黏到哪畫到哪。
      expect(th.className).toContain("shadow-[inset_0_-1px_0_var(--color-line)]");
      expect(th.className).not.toContain("border-b");
      // 右欄 475px(1536 兩欄態)時「金額(億)」會折成兩行,表頭高度隨之跳動
      expect(th.className).toContain("whitespace-nowrap");
    }
    expect(table.querySelector("thead tr")!.className).not.toContain("border-b");
  });

  it("狀態徽章不折行(窄欄下「觸及未鎖」會被拆成直排)", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-badge-2330").className).toContain("whitespace-nowrap");
  });

  // 截圖(1920 / 1536 皆可見):右欄寬度下「連 4 板」被拆成「連 4」/「板」兩行、名稱欄
  // 的四字檔名(台聯電 / 長榮航太)同樣折行 → 列高由 24 撐到 40px,一屏看得到的檔數少
  // 掉三分之一。**只鎖這兩欄**:其餘欄位是數字 / 兩字標籤,本來就折不了。
  it("連板與名稱資料格不折行(列高不被撐開)", async () => {
    await openWith(mkState(ROWS));
    expect(screen.getByTestId("limit-streak-1101").className).toContain("whitespace-nowrap");
    expect(screen.getByTestId("limit-name-1101").className).toContain("whitespace-nowrap");
  });
});

// 🔴 SC-2:1536 兩欄態的右欄捲動容器只有 431px,而九欄表 scrollWidth 612px → 恆有
// 水平捲軸,金額 / 量比 / 狀態尾段全藏在捲軸後面。實測基準 612:只藏兩欄(省 ~140)
// → 472 仍捲;只收 padding(9 cell × 8 = 72)→ 540 仍捲;**兩者併用** → ~416 < 431。
//
// 門檻用 **rem 不用 px**:表格內容是 rem 字級,「塞不塞得下」隨 root font-size 縮放
// (≥1920 112.5% / ≥2560 125%)—— 41rem = 656@100% / 738@112.5% / 820@125%。
// 右欄寬模型:1536 → 470(降級)/ 1920 → 605(降級,本就塞不下)/ 2560 → 844(九欄)。
//
// **jsdom 不套 CSS** → 這裡只鎖 class 字串(九欄 DOM 恆在,既有的「表頭九欄文字與
// 順序」不該紅);實際 display:none 與 scrollWidth ≤ clientWidth 由 SC-2 真環境量測把關。
describe("LimitListSection 窄右欄降級(SC-2)", () => {
  it("root 自掛 @container(門檻要量右欄寬,不是頁 root 寬)", async () => {
    await openWith(mkState(ROWS));
    // 右欄框不是 container(它的 @[1050px] 刻意量頁 root)→ 不自掛的話這裡量到的
    // 也是頁 root 寬,1536 全螢幕永遠 > 41rem,降級永不發生
    expect(screen.getByTestId("limit-list").className).toContain("@container");
  });

  it("窄容器藏 金額(億) / 量比 兩欄(th + td),其餘七欄不藏", async () => {
    await openWith(mkState(ROWS));
    const hidden = "@max-[41rem]:hidden";
    const th = (name: string) => screen.getByRole("columnheader", { name });

    // 藏這兩欄的理由:兩者都仍可由篩選列的門檻輸入控制,資訊沒有消失(W-5)
    expect(th("金額(億)").className).toContain(hidden);
    expect(th("量比").className).toContain(hidden);
    expect(screen.getByTestId("limit-amount-1101").className).toContain(hidden);
    expect(screen.getByTestId("limit-ratio-1101").className).toContain(hidden);

    // 其餘七欄一律不藏 —— 少一條這種反向斷言,「順手多藏一欄」不會被任何測試擋下
    for (const name of ["代號", "名稱", "市場", "現價", "漲跌幅", "連板", "狀態"]) {
      expect(th(name).className).not.toContain(hidden);
    }
    for (const id of ["limit-name-1101", "limit-market-1101", "limit-close-1101"]) {
      expect(screen.getByTestId(id).className).not.toContain(hidden);
    }
    expect(screen.getByTestId("limit-change-1101").className).not.toContain(hidden);
    expect(screen.getByTestId("limit-streak-1101").className).not.toContain(hidden);
  });

  it("cell 左右 padding:窄容器 px-1,寬容器仍是既有 px-2", async () => {
    await openWith(mkState(ROWS));
    const narrow = "@max-[41rem]:px-1";
    const th = screen.getByRole("columnheader", { name: "代號" });
    expect(th.className).toContain(narrow);
    // twMerge 不判成衝突(不同 variant);被吃掉的話寬右欄的 padding 也跟著變
    expect(th.className).toContain("px-2");

    const td = screen.getByTestId("limit-name-1101");
    expect(td.className).toContain(narrow);
    expect(td.className).toContain("px-2");
  });
});
