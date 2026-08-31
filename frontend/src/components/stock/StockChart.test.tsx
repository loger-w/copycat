/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { StockAccum } from "@/lib/stock-accum";
import type { CapitalFill } from "@/types";
import { fillOf, wrap } from "@/test-utils";

const ACCUM = {
  code: "2330",
  seq: 1,
  last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
  vwap: 2_380_000,
  minutes: new Map([[540, { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 }]]),
  ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
  // `vp` 是 StockAccum 的必填欄。`as unknown as` 硬轉不會被 tsc 抓到漏欄,而消費端
  // (分時圖的 VP 長條)刻意不用 `?? new Map()` 吞 —— 真漏建要在執行期炸,不要靜默空圖。
  vp: new Map(),
  book: { bids: [], asks: [] },
  meta: {
    name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000,
    y_vol: 100,
  },
  noData: false,
} as unknown as StockAccum;

const BARS = [
  { t: "2026-07-27", o: 100_000, h: 110_000, l: 90_000, c: 105_000, v: 10 },
  { t: "2026-07-28", o: 105_000, h: 120_000, l: 100_000, c: 102_000, v: 20 },
];

/** 逐筆成交 fixture(SC-7;精確版 L76)。`date` **必須動態算** —— 寫死日期會在
 *  隔天靜默轉紅。`price` 是**元**;個股期的 `stock_no` 放的是期交所契約碼。 */

let barsUrls: string[];
let fills: CapitalFill[];

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  fills = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/stock/bars")) {
        barsUrls.push(u);
        return new Response(JSON.stringify({ bars: BARS }));
      }
      // 單檔頁在這一層掛 `useCapitalFills`(SC-7 / L76);不接路由的話它會拿到 overlay
      // 的殼當成交列表用(`fills` undefined → 恆零標記,SC-7 靜默 vacuous)。
      if (u.includes("/api/capital/fills")) {
        return new Response(JSON.stringify({ fills }));
      }
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function chart() {
  return wrap(<StockChart accum={ACCUM} code="2330" />);
}

describe("StockChart 模式切換(SC-7)", () => {
  // 🔴 SC-6.1:分 K 由 1/5 兩顆擴為 1–10 連續十顆,共 12 顆模式鈕
  it("模式鈕共 12 顆:江波圖 + 1分K…10分K + 日K", () => {
    chart();
    const labels = ["江波圖", ...Array.from({ length: 10 }, (_, i) => `${i + 1}分K`), "日K"];
    for (const l of labels) expect(screen.getByRole("radio", { name: l })).toBeTruthy();
    // a11y 批:模式列改 radiogroup(單選),江波圖自己的 均價/CDP/MA 仍是 toggle button
    // → 收斂到 radiogroup 內數,不再需要用 textContent regex 把 toggle 濾掉。
    const group = screen.getByRole("radiogroup", { name: "圖表模式" });
    const modeRadios = [...group.querySelectorAll("input")] as HTMLInputElement[];
    expect(modeRadios.length).toBe(12);
    expect(modeRadios.filter((r) => r.checked).length).toBe(1);
    expect(new Set(modeRadios.map((r) => r.name)).size).toBe(1);
  });

  it("3分K / 7分K 等新模式可切換且寫入 localStorage", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "7分K" }));
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("m7");
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect((screen.getByRole("radio", { name: "7分K" }) as HTMLInputElement).checked).toBe(true);
  });

  it("預設江波圖:選中者 checked 且外框 border-accent", () => {
    chart();
    const btn = screen.getByRole("radio", { name: "江波圖" }) as HTMLInputElement;
    expect(btn.checked).toBe(true);
    // a11y 批:pill 的 class 搬到包住 sr-only radio 的 `<label>`(視覺零變的硬約束)
    expect(btn.parentElement!.className).toContain("border-accent");
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.queryByLabelText("K 線圖")).toBeNull();
  });

  it("切日K → 顯示 K 線圖,江波圖卸載", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByLabelText("分時走勢圖")).toBeNull();
  });

  it("切回江波圖 → 回到既有分時走勢圖(含 VWAP 切換與內外盤副圖)", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    fireEvent.click(screen.getByRole("radio", { name: "江波圖" }));
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.getByLabelText("成交量")).toBeTruthy();
    expect(screen.getByRole("button", { name: "均價" })).toBeTruthy();
  });

  it("模式寫入 localStorage copycat-chart-mode 並在重載後復原", async () => {
    const { unmount } = chart();
    fireEvent.click(screen.getByRole("radio", { name: "5分K" }));
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("m5");
    unmount();
    cleanup();
    chart();
    expect((screen.getByRole("radio", { name: "5分K" }) as HTMLInputElement).checked).toBe(true);
  });

  // 🔴 SC-6.2:「往前」鈕與「近 N 日」文字移除,分 K 一次就載滿 30 日(縮放/平移取代分頁載入)
  it("分K 直接載 30 日,無「往前」鈕與「近 N 日」文字", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "1分K" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("days=30"))).toBe(true));
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull();
    expect(screen.queryByText(/近 \d+ 日/)).toBeNull();
    // 只打一次,不再有 5→10→…→30 的階梯式重取
    expect(barsUrls.filter((u) => u.includes("tf=1")).length).toBe(1);
  });

  it("日K 走 tf=D 且 query 不帶 days(D-15)", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("tf=D"))).toBe(true));
    expect(barsUrls.find((u) => u.includes("tf=D"))).not.toContain("days=");
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull();
  });

  it("2–10 分K 共用同一份 tf=1 資料(前端聚合,切模式不重打)", async () => {
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "1分K" }));
    await waitFor(() => expect(barsUrls.length).toBeGreaterThan(0));
    const before = barsUrls.length;
    fireEvent.click(screen.getByRole("radio", { name: "3分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(barsUrls.length).toBe(before);
  });

  // 🔴 SC-3:失敗態與「真的沒資料」原本共用同一句「無 K 線資料」,害 2026-07-29 那次
  // 舊 build 佔 port(endpoint 404)被誤讀成「這檔沒 K 線」。失敗態要看得出是失敗。
  // 錯誤碼取值鏈:body 的 detail.error 優先 → 否則 HTTP_<status>(useStockBars.ts:35-44),
  // 故本 case 的碼是 NOT_READY 而非 HTTP_503。
  it("取數失敗顯示「K 線載入失敗」+ 錯誤碼,不崩", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 })
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("K 線載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText("NOT_READY")).toBeTruthy();
    expect(screen.queryByText("無 K 線資料")).toBeNull();
  });

  // 🟢 self-review C2:錯誤碼取值鏈的**第二條路**(body 無 detail.error → HTTP_<status>)。
  // 這正是 2026-07-29 的真實事故路徑:舊 build 佔 port,FastAPI 對未知 route 回
  // {"detail":"Not Found"} —— detail 是字串不是物件,`.error` 為 undefined → 落回 HTTP_404。
  // 只測 detail.error 那條的話,這條 fallback 壞掉不會有任何測試變紅。
  it("錯誤碼 fallback:body 無 detail.error → 顯示 HTTP_<status>", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("K 線載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText("HTTP_404")).toBeTruthy();
  });

  // 🔴 round3 SC-6:高度分配反轉 —— 圖表由「shrink-0 的固定比例高」改成「吃剩餘空間」。
  // 舊 shrink-0 防的是「被壓縮致 svg 溢出」,新機制從源頭消掉那個情境:svg 高度本身
  // 就跟著可用空間走,而不是由寬度算出來的固定值。
  it("圖表容器吃剩餘高度,且量測 wrapper 為恆存(SC-6)", () => {
    const { container } = chart();
    const root = container.firstChild as HTMLElement;
    expect(root.className).toContain("flex-1");
    expect(root.className).toContain("min-h-0");
    expect(root.className).not.toContain("shrink-0");
    // 恆存 wrapper = 模式列的下一個兄弟;三態都掛在它底下(useContainerSize 契約)
    const wrapper = root.children[1] as HTMLElement;
    expect(wrapper.className).toContain("flex-1");
    expect(wrapper.className).toContain("min-h-0");
  });

  // 🟢 SC-3 反向:真的取到空陣列 → 仍是「無 K 線資料」,不可誤報成失敗(W-13)
  it("取到空 bars 仍顯示「無 K 線資料」,不誤報失敗", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ bars: [] }))
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
  });
});

// 🔴 N-7:空 bars 的三種來源(逾時 / 真無資料 / 斷線)原本共用「無 K 線資料」一句
// 肯定語氣,把「還在等」與「斷線」都講成「這檔沒 K 線」。三態各自的文案已由 user 拍板。
describe("StockChart 空態三分態文案(N-7)", () => {
  function stubBars(body: unknown) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify(body))
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
  }

  async function daily(body: unknown) {
    stubBars(body);
    chart();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
  }

  it("status=timeout + 空 bars → 灰字「等待 TC4 回應中…(自動重試)」", async () => {
    await daily({ bars: [], status: "timeout" });
    await waitFor(() => expect(screen.getByText("等待 TC4 回應中…(自動重試)")).toBeTruthy(), {
      timeout: 5000,
    });
    // 中性灰(同「載入中…」樣式)—— 逾時不是錯誤,不用紅
    expect(screen.getByText("等待 TC4 回應中…(自動重試)").className).toContain("text-ink-muted");
    expect(screen.queryByText("無 K 線資料")).toBeNull();
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
    // WL-COV-2:佔位框「同載入中樣式」是 user 拍板的刻意選擇(不是隨手撿的 class),
    // 要有測試釘住,否則改樣式時無訊號。
    const box = screen.getByText("等待 TC4 回應中…(自動重試)").closest("div")!;
    expect(box.className).toContain("border-line");
    expect(box.className).toContain("bg-surface");
  });

  it("status=disconnected + 空 bars → 紅字「TC4 連線中斷,K 線暫不可用(自動重試中)」", async () => {
    await daily({ bars: [], status: "disconnected" });
    await waitFor(
      () => expect(screen.getByText("TC4 連線中斷,K 線暫不可用(自動重試中)")).toBeTruthy(),
      { timeout: 5000 },
    );
    expect(screen.getByText("TC4 連線中斷,K 線暫不可用(自動重試中)").className).toContain(
      "text-bear",
    );
    expect(screen.queryByText("無 K 線資料")).toBeNull();
    expect(screen.queryByText("等待 TC4 回應中…(自動重試)")).toBeNull();
  });

  // §3 backward compat:舊後端沒有 status 欄位 → default "ok" = 現況行為
  it("缺 status 欄位(舊後端)+ 空 bars → 回歸「無 K 線資料」", async () => {
    await daily({ bars: [] });
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("等待 TC4 回應中…(自動重試)")).toBeNull();
  });

  // R6:未知值若放行,輪詢會因 `!== "ok"` 開始、畫面卻落「無 K 線資料」→ 零訊號矛盾態。
  // 正規化集中在 fetchBars,所以未知值在這裡就已經是 "ok"(不觸發 20s 的斷言見
  // useStockBars.test.tsx 的接線測試)。
  it("status 為未知值 → 正規化成 ok,仍顯示「無 K 線資料」", async () => {
    await daily({ bars: [], status: "weird" });
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("等待 TC4 回應中…(自動重試)")).toBeNull();
    expect(screen.queryByText("TC4 連線中斷,K 線暫不可用(自動重試中)")).toBeNull();
  });

  // F1/WL-COV-1:bars 欄位缺(payload drift / 版本落差 —— 與 status 缺同一個理由)。
  // 未正規化時 `data.bars.length` 會丟 TypeError,而專案無 ErrorBoundary → 整頁白畫面
  // (比舊碼的 TanStack error 態更糟)。正規化後 bars 視為空,status 照樣分態。
  it("回應缺 bars 欄位 + status=timeout → 顯示等待句,不崩", async () => {
    await daily({ status: "timeout" });
    await waitFor(() => expect(screen.getByText("等待 TC4 回應中…(自動重試)")).toBeTruthy(), {
      timeout: 5000,
    });
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
  });

  it("回應為空物件(bars 與 status 皆缺)→ 回歸「無 K 線資料」,不崩", async () => {
    await daily({});
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
  });

  // bars 非空時不分態(Out of scope 3):當日段降級但有歷史資料 → 照常畫圖
  it("status=timeout 但 bars 非空 → 照常掛 K 線圖,不顯示等待句", async () => {
    await daily({ bars: BARS, status: "timeout" });
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("等待 TC4 回應中…(自動重試)")).toBeNull();
  });
});

// 🟢 SC-5 / D10:選了個股期合約 → 本輪只提供江波圖。
// 「K 線模式鈕反灰」單獨是不夠的:模式是**持久化狀態**,使用者上次停在日 K 時,
// 切進期貨的第一次 render 就已經是 day 模式 —— 不收斂就會掛著 CandleChart、
// 且 `useStockBars` 已經拿股號打了一發 `/api/stock/bars`(那支查的是現貨不是合約,
// 畫出來的 K 線與畫面上的合約無關,是零訊號的假資料)。所以三件事要同時成立:
// 模式鈕 disabled + 模式收斂 + 取數 enabled:false。
describe("StockChart 期貨態(D10/R5)", () => {
  const CONTRACT = { prod: "CDF", ym: "202609" };

  function futChart() {
    return wrap(<StockChart accum={ACCUM} code="2330" contract={CONTRACT} />);
  }

  it("江波圖以外的模式鈕全部 disabled + tooltip", () => {
    futChart();
    const intraday = screen.getByRole("radio", { name: "江波圖" });
    expect(intraday.hasAttribute("disabled")).toBe(false);
    for (const label of [...Array.from({ length: 10 }, (_, i) => `${i + 1}分K`), "日K"]) {
      const btn = screen.getByRole("radio", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      // a11y 批 W8:`title` 與 `aria-disabled` 掛在 label(sr-only input 上的 title
      // 對滑鼠不可見)—— 文案與觸發條件不變
      expect(btn.parentElement!.getAttribute("title")).toBe("期貨合約本輪僅提供分時");
      expect(btn.parentElement!.getAttribute("aria-disabled")).toBe("true");
    }
  });

  it("殘留日 K 存檔 → 收斂回江波圖,且不寫回 localStorage(現貨的偏好要留著)", async () => {
    window.localStorage.setItem("copycat-chart-mode", "day");
    futChart();
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    expect((screen.getByRole("radio", { name: "江波圖" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByLabelText("K 線圖")).toBeNull();
    // 存檔維持 day:切回現貨時使用者原本選的模式要回得來
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("day");
  });

  it("期貨態一發 /api/stock/bars 都不打(收斂前的那一次 render 也不打)", async () => {
    window.localStorage.setItem("copycat-chart-mode", "day");
    futChart();
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    expect(barsUrls).toEqual([]);
  });

  // 對照組:證明上面三條不是因為 fixture 本來就不會走 K 線路徑而 vacuous
  it("contract=null(現貨)行為不變:日 K 存檔照樣還原且會打 bars", async () => {
    window.localStorage.setItem("copycat-chart-mode", "day");
    chart();
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });
    expect(barsUrls.length).toBeGreaterThan(0);
  });
});

// 🔴 code review A6:切回現貨要**還原**進期貨前的現貨模式。
// 「不寫回 localStorage」只保住了「重開瀏覽器後偏好還在」;同一個 session 內 `mode`
// state 已經被收斂成 intraday,切回現貨時沒有人會把存檔讀回來 —— 使用者的體感是
// 「進了一次合約,我的日 K 就沒了」,而且每切一次合約就要重按一次。
describe("StockChart 現貨模式還原(A6)", () => {
  const CONTRACT = { prod: "CDF", ym: "202609" };

  /** 進出合約要在**同一個元件實例**上驗(重掛載會讓 ref 歸零 = 測不到還原)。
   *  不能用 `wrap` 的 rerender:那會把 QueryClientProvider 一起換掉(StockPage.test 同註),
   *  所以這裡自己持有 client 並讓每次 rerender 都帶著同一個 provider。 */
  function mount() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tree = (contract: { prod: string; ym: string } | null) => (
      <QueryClientProvider client={client}>
        <StockChart accum={ACCUM} code="2330" contract={contract} />
      </QueryClientProvider>
    );
    const view = render(tree(null));
    return { setContract: (c: typeof CONTRACT | null) => view.rerender(tree(c)) };
  }

  // a11y 批:模式列改 RadioPills → 選中態由原生 `checked` 表達,不再是 aria-pressed
  const pressed = (name: string) =>
    (screen.getByRole("radio", { name }) as HTMLInputElement).checked;

  it("現貨日K → 進合約(收斂江波圖)→ 切回現貨:回到日K", async () => {
    const { setContract } = mount();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });

    setContract(CONTRACT);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());

    setContract(null);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });
    expect(pressed("日K")).toBe(true);
  });

  it("分K 也還原(還原的是「進去前那一個」,不是寫死日K)", async () => {
    const { setContract } = mount();
    fireEvent.click(screen.getByRole("radio", { name: "7分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });
    setContract(CONTRACT);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    setContract(null);
    await waitFor(() => expect(pressed("7分K")).toBe(true));
  });

  it("本來就停在江波圖 → 切回現貨仍是江波圖(不憑空跳成 K 線)", async () => {
    const { setContract } = mount();
    expect(pressed("江波圖")).toBe(true);
    setContract(CONTRACT);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    setContract(null);
    expect(pressed("江波圖")).toBe(true);
    expect(screen.queryByLabelText("K 線圖")).toBeNull();
  });

  it("還原只做一次:切回現貨後手動改模式,不會被舊值再蓋一次", async () => {
    const { setContract } = mount();
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });
    setContract(CONTRACT);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    setContract(null);
    await waitFor(() => expect(pressed("日K")).toBe(true));
    fireEvent.click(screen.getByRole("radio", { name: "江波圖" }));
    expect(pressed("江波圖")).toBe(true);
  });
});

// 🟢 R2 SC-7:單檔頁的成交點比對鍵。現貨態 = 股號 + 排除零股;個股期態 = **選定契約的
// 期交所契約碼**(群益回報的期貨單 `stock_no` 放的就是它)且不排除單位「口」。
//
// 鍵選錯的失效樣態是「圖上多了別的商品的成交點」—— 畫面照樣有東西,零錯誤訊號。
describe("StockChart 成交點比對鍵(SC-7)", () => {
  const SPOT = fillOf({ seq_no: "spot", time: "09:00:30" }); // 2330 現股 @540
  const FUT = fillOf({
    seq_no: "fut",
    stock_no: "CDFH6", // futExchangeContract("CDF", "202608") —— 月碼 A..L,8 月 = H
    code: "2330", // 個股期 wire 反查股號;比對鍵仍走 stock_no(契約碼)
    buy_sell: "S",
    unit: "口",
    price: 2390,
    qty: 1,
    time: "09:01:30", // @541
  });

  function marks(container: HTMLElement): string[] {
    return [...container.querySelectorAll('polygon[data-testid^="fill-"]')].map(
      (n) => n.getAttribute("data-testid")!,
    );
  }

  it("現貨態:只畫股號那筆(同一份 fills 內的個股期成交不畫)", async () => {
    fills = [SPOT, FUT];
    const { container } = wrap(<StockChart accum={ACCUM} code="2330" />);
    await waitFor(() => expect(marks(container)).toEqual(["fill-B-540"]));
  });

  it("個股期態:只畫該契約碼那筆(現貨股號那筆不畫)", async () => {
    fills = [SPOT, FUT];
    const { container } = wrap(
      <StockChart accum={ACCUM} code="2330" contract={{ prod: "CDF", ym: "202608" }} />,
    );
    await waitFor(() => expect(marks(container)).toEqual(["fill-S-541"]));
  });

  it("現貨態:零股(unit「股」)不畫;同批的現股單照畫(與現股梯同口徑)", async () => {
    fills = [
      fillOf({ seq_no: "odd", unit: "股", qty: 1000, time: "09:00:30" }),
      fillOf({ seq_no: "lot", time: "09:01:30" }),
    ];
    const { container } = wrap(<StockChart accum={ACCUM} code="2330" />);
    await waitFor(() => expect(marks(container)).toEqual(["fill-B-541"]));
  });

  it("個股期態合約月份非法 → 鍵解不出來 = 零標記,圖不白屏", async () => {
    fills = [SPOT, FUT];
    const { container } = wrap(
      <StockChart accum={ACCUM} code="2330" contract={{ prod: "CDF", ym: "2026" }} />,
    );
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    expect(marks(container)).toEqual([]);
  });
});
