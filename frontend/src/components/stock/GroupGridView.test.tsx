/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GroupGridView, gridShape } from "@/components/stock/GroupGridView";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { STOCK_GROUP_KEY } from "@/lib/constants";
import type { Group } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";

const GROUPS: Group[] = [
  { name: "半導體", codes: ["2330", "2317"] },
  { name: "金融", codes: ["2881"] },
];

function quote(over: Partial<WatchlistQuote> = {}): WatchlistQuote {
  return {
    p: null, chg_pct: null, vol: null, ref: null, upper: null, lower: null, no_data: false, trial: false,
    ...over,
  };
}

interface StateOver {
  minutes?: Record<string, unknown>;
  meta?: unknown;
  no_data?: boolean;
  backfilling?: boolean;
  vp?: Record<string, [number, number, number]>;
}

/** group-state 的**後端 wire 形**(字串鍵 + 緊湊陣列),不是 hook 產出的 Map ——
 *  本檔走真 `useGroupSnapshots`,四個加鍵(vwap/high/low/vp)刻意在這裡以原始 JSON
 *  形給,讓「後端鍵 → hook 解析 → accum → svg」整條線由這一份 fixture 串起來。 */
function state(over: StateOver = {}) {
  return {
    minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    no_data: false,
    backfilling: false,
    vwap: 2_380_000,
    high: 2_385_000,
    low: 2_375_000,
    vp: { "2380000": [10, 7, 3] } as Record<string, [number, number, number]>,
    ...over,
  };
}

/** ResizeObserver 的最小替身(樣板 `components/index/MarketPane.size.test.tsx`)。
 *
 *  卡片的分時圖走 `useContainerSize` 量測後才畫(AD-3:量到之前不畫,否則 800 寬的
 *  viewBox 會先塞進 250px 卡片再跳回 1:1)—— jsdom 沒有 RO,不 stub 的話整面卡片的
 *  圖區都是空白,本檔所有「圖畫出來了」的斷言會靜默 vacuous(查不到 svg 與「這一態
 *  本來就不該有 svg」在 queryBy 下長得一模一樣)。
 *
 *  **必須同步餵**:`useContainerSize` 是 callback ref,節點掛上當下才 observe;
 *  非同步餵在 RTL 的同步斷言之前不會到達。 */
class FakeResizeObserver {
  private readonly cb: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }

  observe(node: Element): void {
    this.cb(
      [{ target: node, contentRect: { width: 300, height: 200 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {}
}

let fetchMock: ReturnType<typeof vi.fn>;
let states: Record<string, unknown>;

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  states = {
    "2330": state(),
    "2317": state({ meta: { name: "鴻海", ref: 2_000_000, upper: null, lower: null, y_vol: 5 } }),
    "2881": state({ meta: { name: "富邦金", ref: 800_000, upper: null, lower: null, y_vol: 5 } }),
  };
  fetchMock = vi.fn(async (url: string) => {
    // 卡片圖與單檔頁同一份渲染碼 → `cdp` 預設開時每張卡都會打一次 overlay。
    // 不接這條路由的話它會拿到 group-state 的殼(`{states:{}}`)當 overlay 用。
    if (String(url).includes("/api/stock/overlay/")) {
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }
    const codes = new URL(String(url), "http://x").searchParams.get("codes") ?? "";
    const picked: Record<string, unknown> = {};
    for (const c of codes.split(",").filter(Boolean)) picked[c] = states[c] ?? state({ no_data: true });
    return new Response(JSON.stringify({ states: picked }));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function groupCalls(): string[] {
  return fetchMock.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes("/api/stock/group-state"));
}

describe("GroupGridView 空態(文案逐字)", () => {
  it("零群組 → 尚無群組空態,且零請求", async () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} active={null} />);
    expect(screen.getByText("尚無群組 — 到自選欄建立群組")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  // R17:空群組的 codes 是空陣列,打端點只會拿回 `{"states":{}}` —— 沒有任何卡片可畫,
  // 卻每 60s 燒一次來回。gate 在 hook 的 `enabled`,不是在畫面。
  it("空群組(成員 0)→ 專屬空態,且零請求", async () => {
    wrap(<GroupGridView groups={[{ name: "空組", codes: [] }]} quotes={{}} onPick={vi.fn()} active={null} />);
    expect(screen.getByText("這個群組還沒有成員")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });
});

// review A4:`groups` 退化成空陣列時,「自選還在載」「自選載入失敗」「真的零群組」
// 長得一模一樣 —— 而只有第三種是真的要使用者去建群組。前兩種顯示終態空文案等於
// 對著一份還沒讀到的資料下結論,失敗時更會讓人以為群組被清光了。
describe("GroupGridView 自選三態前置(review A4)", () => {
  it("自選載入中 → 「載入群組…」,不下結論也不請求", async () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} active={null} wlPending />);
    expect(screen.getByText("載入群組…")).toBeTruthy();
    expect(screen.queryByText("尚無群組 — 到自選欄建立群組")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  it("自選載入失敗 → 「自選載入失敗」,不冒充空清單", async () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} active={null} wlError />);
    expect(screen.getByText("自選載入失敗")).toBeTruthy();
    expect(screen.queryByText("尚無群組 — 到自選欄建立群組")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  it("終態零群組(非載入中、非失敗)→ 才說「尚無群組」", () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} active={null} wlPending={false} wlError={false} />);
    expect(screen.getByText("尚無群組 — 到自選欄建立群組")).toBeTruthy();
  });

  // 失敗但**手上還有舊資料**(TQ 的 error + cached data)時照畫 —— 群組結構是慢變數,
  // 上一份仍然有用;把它換成一句錯誤訊息是拿走使用者唯一能看的東西。
  it("有群組資料時,wlError 不遮掉既有卡片", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} wlError />);
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.queryByText("自選載入失敗")).toBeNull();
  });
});

// SC-3:`<select>` 換成一排 pill(與 StockPage 的「單檔/群組」view pill 同語彙)。
// 選中態的真相源改成 `aria-pressed`,切換靠 click —— 但**可及名稱契約不變**:
// pill 列容器保留 `role="group" aria-label="選擇群組"`,StockPage.test.tsx 的
// 671/713/746/750 四處 `ByLabelText("選擇群組")` 靠它接住(改成別的名字 = 那四條
// 斷言靜默 vacuous:查不到元素與「群組檢視沒渲染」在 queryBy 下長得一模一樣)。
describe("GroupGridView 群組切換 pill", () => {
  it("預設第一個群組;成員卡片全數渲染", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    expect(
      screen.getByRole("button", { name: "半導體" }).getAttribute("aria-pressed"),
    ).toBe("true");
    // 反向斷言不可省(review B-5):少了它,「每顆 pill 恆 pressed」全綠 ——
    // aria-pressed 是 SC-3 指名的選中態真相源,兩側都要釘
    expect(screen.getByRole("button", { name: "金融" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
    // 容器名稱契約 + select 真的走了(留著兩套切換 UI 才是最糟的中間態)
    const rail = screen.getByLabelText("選擇群組");
    expect(rail.getAttribute("role")).toBe("group");
    expect(screen.queryByRole("combobox")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.getByTestId("group-card-2317")).toBeTruthy();
    expect(screen.queryByTestId("group-card-2881")).toBeNull();
  });

  it("切換群組 → 改打新群組的 codes", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await waitFor(() => expect(groupCalls()).toHaveLength(1));
    expect(groupCalls()[0]).toContain("codes=2330,2317");
    fireEvent.click(screen.getByRole("button", { name: "金融" }));
    await waitFor(() => expect(screen.getByTestId("group-card-2881")).toBeTruthy());
    expect(groupCalls().some((u) => u.includes("codes=2881"))).toBe(true);
    // 寫入側也要鎖(review B-1):刪掉 persistGroupName 整條路徑,其餘測試照樣全綠,
    // 而使用者下次開頁會靜默回到第一個群組
    expect(window.localStorage.getItem(STOCK_GROUP_KEY)).toBe("金融");
  });

  // review A-3:舊 <select> 的 change 事件在 value 未變時不發火,localStorage 的
  // 失效舊名會永遠留著;pill 的 click 無條件回寫 —— 這是**刻意的 stale-key 清理**
  // (spec 白名單 #7 amendment),不是不變行為,所以要有測試把新語意釘住。
  it("點已選中的 pill 也回寫 localStorage(清掉 stale 舊名)", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "已刪掉的組");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    fireEvent.click(screen.getByRole("button", { name: "半導體" }));
    expect(window.localStorage.getItem(STOCK_GROUP_KEY)).toBe("半導體");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
  });

  // edge 5(R10):群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名。
  // 不 fallback 的話畫面會停在「這個群組還沒有成員」而使用者根本沒有那一組。
  it("記住的群組已被刪 → fallback 第一個群組", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "已刪掉的組");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    expect(
      screen.getByRole("button", { name: "半導體" }).getAttribute("aria-pressed"),
    ).toBe("true");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
  });

  it("記住的群組仍在 → 沿用它(不重設回第一個)", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "金融");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    expect(screen.getByRole("button", { name: "金融" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    await waitFor(() => expect(screen.getByTestId("group-card-2881")).toBeTruthy());
  });
});

// SC-1:欄數不再由容器寬 ÷ 15rem 決定,而是由檔數選「最小可容納矩陣」——
// 同一群組每次打開都是同一個版面,眼睛才記得住哪張卡片在哪。class 必須是**靜態
// 字面值**(Tailwind JIT 掃原始碼,`grid-cols-${n}` 拼出來的 class 不會被產出)。
describe("GroupGridView 矩陣佈局(gridShape)", () => {
  const ROWS2 = "[grid-template-rows:repeat(2,minmax(8rem,1fr))]";
  const ROWS3 = "[grid-template-rows:repeat(3,minmax(8rem,1fr))]";
  const ROWS4 = "[grid-template-rows:repeat(4,minmax(8rem,1fr))]";
  const TABLE: [number, string][] = [
    // n=0 元件層由空群組空態擋住不會呼叫,函式仍須有定義行為(spec P2-2)
    [0, `grid-cols-2 ${ROWS2}`],
    [1, `grid-cols-2 ${ROWS2}`],
    [4, `grid-cols-2 ${ROWS2}`],
    [5, `grid-cols-3 ${ROWS2}`],
    [6, `grid-cols-3 ${ROWS2}`],
    [7, `grid-cols-3 ${ROWS3}`],
    [9, `grid-cols-3 ${ROWS3}`],
    [10, `grid-cols-4 ${ROWS3}`],
    [12, `grid-cols-4 ${ROWS3}`],
    [13, `grid-cols-4 ${ROWS4}`],
    [16, `grid-cols-4 ${ROWS4}`],
    // >16:固定 4 欄、列高 auto(基準高)往下捲 —— 不再有列軌下限
    [17, "grid-cols-4"],
  ];

  for (const [n, expected] of TABLE) {
    it(`n=${n} → ${expected}`, () => {
      expect(gridShape(n)).toBe(expected);
    });
  }

  it("元件層:2 檔群組 → 2×2 矩陣格線,不走 auto-fill", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    const grid = screen.getByTestId("group-grid");
    expect(grid.className).toContain("grid-cols-2");
    expect(grid.className).toContain(ROWS2);
    expect(grid.className).toContain("flex-1");
    expect(grid.className).not.toContain("auto-fill");
  });

  // review A-1:容器有 flex-1(確定高度)後,>16 分支的隱式列軌是 auto ——
  // align-content 預設(normal → stretch)會把 auto 軌**等量撐高填滿容器**,
  // 17~24 檔在一般桌面高度下既不出捲軸、圖也不是 80px 基準。`content-start`
  // 把 free space 留在下方,列高才真的回到內容高、超出才捲。
  // 矩陣分支的 1fr 軌自己吃滿 free space,content-start 對它是 no-op。
  //
  // 兼 review B-2:fixture 刻意讓「群組數(1)≠ 檔數(17)且落在不同 bucket」——
  // gridShape 若誤接 groups.length 會回 grid-cols-2,這裡就紅。
  it("元件層:17 檔群組 → 4 欄無列軌 + content-start(不被 stretch 撐高)", async () => {
    const codes17 = Array.from({ length: 17 }, (_, i) => String(3000 + i));
    wrap(
      <GroupGridView groups={[{ name: "大群", codes: codes17 }]} quotes={{}} onPick={vi.fn()} active={null} />,
    );
    await waitFor(() => expect(screen.getByTestId("group-card-3000")).toBeTruthy());
    const grid = screen.getByTestId("group-grid");
    expect(grid.className).toContain("grid-cols-4");
    expect(grid.className).toContain("content-start");
    expect(grid.className).not.toContain("grid-template-rows");
  });
});

// SC-2:卡片要吃滿中區高度,圖跟著長高。
//
// test-infra-fix(圖換成單檔同款之後):`vector-effect` / `mini-price` 那組斷言鎖的是
// mini 圖「viewBox 固定、靠非等比拉伸吃滿卡片」的縮放模型 —— 新的卡片圖是 **1:1**
// (viewBox 尺寸 = 量到的 px),沒有縮放也就沒有線寬失真可補償。契約改由這一條承接:
// 圖區 wrapper 的高**由外層指派**(useContainerSize 契約 2),而主副圖的 viewBox 寬
// 等於量到的寬(AD-3)—— 這兩件事漂掉的症狀同樣是「卡片內容溢出格軌與下一列重疊」。
describe("GroupGridView 高度均分 class", () => {
  it("常態卡片:圖區 wrapper 由外層指派高度,主副圖 viewBox 寬 = 量到的寬(1:1)", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    const svgs = [...card.querySelectorAll("svg")];
    expect(svgs.length).toBe(2); // 主圖 + 量副圖
    // FakeResizeObserver 餵的是 300×200(見檔頭)
    for (const svg of svgs) {
      expect(svg.getAttribute("viewBox")!.split(" ")[2]).toBe("300");
    }
    // 恆存 wrapper 的高由 flex 指派:掛成 h-20 之類的內容高會形成「量多高就設多高」
    const wrapper = svgs[0]!.parentElement!.parentElement!;
    expect(wrapper.className).toContain("flex-1");
    expect(wrapper.className).toContain("min-h-0");
  });

  it("無資料佔位也跟著長高(不然整列高度對不齊)", async () => {
    states["2330"] = state({ no_data: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const el = await screen.findByText("無資料");
    expect(el.className).toContain("grow");
    expect(el.className).toContain("h-20");
  });
});

describe("GroupGridView 卡片三態(backfilling → noData → 常態)", () => {
  it("常態 → 代碼 + 名稱 + mini 分時圖", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    expect(card.textContent).toContain("2330");
    expect(card.textContent).toContain("台積電");
    expect(card.querySelector("svg")).toBeTruthy();
  });

  it("backfilling → 「回補中…」,不呈現半截圖", async () => {
    states["2330"] = state({ backfilling: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("回補中…"));
    expect(card.querySelector("svg")).toBeNull();
    // 佔位也要 grow(review B-4):「無資料」那支已鎖,這支掉了 grow 的失效樣態是
    // 回補中的卡片縮回 80px、與同列其他卡片高度對不齊
    const ph = screen.getByText("回補中…");
    expect(ph.className).toContain("grow");
    expect(ph.className).toContain("h-20");
  });

  // 優先序:回補中同時 no_data 時要說「回補中…」—— 回補完就會有資料,說「無資料」是錯的
  it("backfilling 與 noData 同時為真 → 顯示「回補中…」", async () => {
    states["2330"] = state({ backfilling: true, no_data: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("回補中…"));
    expect(card.textContent).not.toContain("無資料");
  });

  // review A5:「回補中…」是**佔位**,只在真的沒東西可畫時才該蓋掉圖。已經有分鐘資料
  // (live tick 已進來、或前一輪的回補已落地)還蓋掉,等於每次重回補都讓卡片閃回空白 ——
  // 而重回補在鎖停日的漲跌停值變化上是常態。
  it("backfilling 但已有分鐘資料 → 照畫圖,不蓋「回補中…」", async () => {
    states["2330"] = state({ backfilling: true });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.querySelector("svg")).toBeTruthy());
    expect(card.textContent).not.toContain("回補中…");
  });

  // review A-1:「已經有東西可畫」在三態裡必須是**同一把尺**。回補中的閘用
  // `minutes.size`、edge 9 的閘用 `hasWindowedMinutes` 時,盤前只有 08:59 那格的
  // 卡片會落進兩尺之間:回補明明還在跑,卡片卻宣告「尚無成交」(終態),而下一輪
  // 回補落地才改口 —— 兩把尺同時存在時這個窗永遠關不起來。
  it("backfilling 且只有窗外分鐘(08:59)→ 仍是「回補中…」而非「尚無成交」", async () => {
    states["2330"] = state({
      backfilling: true,
      minutes: { "539": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
    });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("回補中…"));
    expect(card.textContent).not.toContain("尚無成交");
  });

  it("noData → 「無資料」占位", async () => {
    states["2330"] = state({ no_data: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("無資料"));
    expect(card.querySelector("svg")).toBeNull();
  });

  // edge 6(R10:batch 化後 per-card 隔離不再成立)—— 整批一命
  it("batch 整批失敗 → 全部卡片「無資料」", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await waitFor(() =>
      expect(screen.getByTestId("group-card-2330").textContent).toContain("無資料"),
    );
    expect(screen.getByTestId("group-card-2317").textContent).toContain("無資料");
  });
});

// review A-p2-1:後端加鍵 → hook 解析 → accum → svg 這條線,原本每一段各有測試而
// **整條沒有任何一條**(toggle 測試 mock 掉 hook 直接餵 Map,parity fixture 只管折法)。
// 中間任一段漏帶的失效樣態是「卡片上少了 VP 條 / VWAP 標」—— 圖照樣畫得出來,
// 沒有型別錯誤也沒有 console 訊息。
describe("GroupGridView 後端 vp/vwap 全鏈(不 mock hook)", () => {
  it("wire 形 vp/vwap → 卡片畫出 VP 條與右緣 VWAP 價位標", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    // vp / vwap 兩個 toggle 預設都是開的(useChartToggles 預設),localStorage 已清空
    await waitFor(() =>
      expect(card.querySelectorAll('[data-testid="vp-bar"]').length).toBeGreaterThanOrEqual(1),
    );
    expect(card.querySelector('[data-testid="edge-price-vwap"]')).toBeTruthy();
  });
});

describe("GroupGridView 卡片價格(R11:p ?? ref)", () => {
  it("有成交 → 現價 + 漲跌%,漲紅跌綠", async () => {
    const quotes = {
      "2330": quote({ p: 2_400_000, chg_pct: 3.45 }),
      "2317": quote({ p: 1_900_000, chg_pct: -5 }),
    };
    wrap(<GroupGridView groups={GROUPS} quotes={quotes} onPick={vi.fn()} active={null} />);
    const a = await screen.findByTestId("group-quote-2330");
    expect(a.textContent).toContain("2400");
    expect(a.textContent).toContain("+3.45%");
    expect(a.className).toContain("text-bull");
    const b = screen.getByTestId("group-quote-2317");
    expect(b.textContent).toContain("-5.00%");
    expect(b.className).toContain("text-bear");
  });

  // 尚無成交時 `p` 為 null 而 `ref` 有值(兩欄互斥)。參考價不套漲跌色、不印 0.00%
  // —— 那會讓昨收看起來像今天的走勢(同側欄既有紀律)。
  it("尚無成交 → 顯示參考價 + 「參考」,中性色不套漲跌", async () => {
    const quotes = { "2330": quote({ p: null, ref: 2_320_000 }) };
    wrap(<GroupGridView groups={GROUPS} quotes={quotes} onPick={vi.fn()} active={null} />);
    const el = await screen.findByTestId("group-quote-2330");
    expect(el.textContent).toContain("2320");
    expect(el.textContent).toContain("參考");
    expect(el.className).not.toContain("text-bull");
    expect(el.className).not.toContain("text-bear");
  });

  // B3-b:`toContain("-")` 對 `-5.00%`、`2,380-` 之類的內容全都會通過 —— 缺值占位要
  // 的是**整格只有一個 `-`**,寫成全等才鎖得住
  it("p 與 ref 皆缺 → 整格只有「-」", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const el = await screen.findByTestId("group-quote-2330");
    expect(el.textContent).toBe("-");
  });
});

// review B1:卡片圖的末點延伸(design R10)靠 `quotes[code].p` 餵進去。這條接線斷掉
// 的失效樣態是「卡片上的線最久停在一分鐘前」—— 圖還在、值也對,只是不動;而群組檢視
// 存在的理由正是「現在有沒有一起動」。lib 層的 `extendMinutes` 測試驗不到 GroupGridView
// 有沒有真的把 quote 接上去。
//
// test-infra-fix:`mini-price` testid 隨 MiniIntradayChart 一起消失,改以主價線
// (有昨收 → 紅綠 clip 兩條中的 bull 那條)的 points 數計 —— 契約「liveP 有值 →
// 多一點」逐字不變。
describe("GroupGridView 現價延伸接線(review B1)", () => {
  function pointCount(card: HTMLElement): number {
    const el = card.querySelector('polyline[class*="stroke-bull"]');
    return (el?.getAttribute("points") ?? "").split(" ").filter(Boolean).length;
  }

  it("盤中且 quote 有現價 → 卡片圖比 snapshot 多一個延伸點", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0, 30)); // 10:00,窗內且非 09:00 那一格
    try {
      const { unmount } = wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
      const bare = await screen.findByTestId("group-card-2330");
      await waitFor(() => expect(pointCount(bare)).toBe(1)); // 基準:snapshot 只有 09:00 一格
      unmount();

      wrap(
        <GroupGridView
          groups={GROUPS}
          quotes={{ "2330": quote({ p: 2_400_000, chg_pct: 3.45 }) }}
          onPick={vi.fn()} active={null}
        />,
      );
      const live = await screen.findByTestId("group-card-2330");
      await waitFor(() => expect(pointCount(live)).toBe(2));
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("GroupGridView 點卡片切主檔", () => {
  // test-infra-fix:卡片內容改成整張分時圖後外層由 `<button>` 換成
  // `<div role="button">`(review R11:button 的內容模型只吃 phrasing content)——
  // 斷言改看 role,「整張卡片可點且有可及名稱」這個契約不變。
  it("整張卡片是一顆 button(有可及名稱),點了回呼該股", async () => {
    const onPick = vi.fn();
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={onPick} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    expect(card.getAttribute("role")).toBe("button");
    // test-infra-fix:文案隨 A-p2-7 改「選取」(點卡片換的是右欄閃電目標,不是換頁)
    expect(card.getAttribute("aria-label")).toBe("選取 2330 台積電");
    fireEvent.click(card);
    expect(onPick).toHaveBeenCalledWith("2330");
  });
});

// 🟢 SC-3 / AD-6:選中態。點卡片不再切回單檔(檢視停在圖牆)之後,「右欄閃電梯現在
// 瞄的是哪一檔」在畫面上就沒有別的指認方式了 —— 沒有選中框的失效樣態是使用者按下
// 買賣鍵才發現打到別檔,而那是真錢。
describe("GroupGridView 選中態(SC-3 / AD-6)", () => {
  it("active 的那張卡 aria-pressed=true,其餘 false", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active="2330" />);
    const picked = await screen.findByTestId("group-card-2330");
    expect(picked.getAttribute("aria-pressed")).toBe("true");
    // 反向斷言不可省:少了它,「每張卡恆 pressed」照樣全綠
    expect(screen.getByTestId("group-card-2317").getAttribute("aria-pressed")).toBe("false");
  });

  // 視覺層(D):`ring` 是 box-shadow **不佔版面** —— 換成加粗 border 的話選中那一格
  // 的內容寬會少 2px,矩陣上看得出一格在跳。這條鎖的是「選中看得見 + 不動版面」。
  it("選中的卡片畫 accent 框(ring 不佔版面),未選中維持 border-line", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active="2330" />);
    const picked = await screen.findByTestId("group-card-2330");
    expect(picked.className).toContain("border-accent");
    expect(picked.className).toContain("ring-accent");
    const other = screen.getByTestId("group-card-2317");
    expect(other.className).toContain("border-line");
    expect(other.className).not.toContain("ring-accent");
  });

  it("active 不在當前群組 → 全部未選中(edge 6)", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active="2881" />);
    const first = await screen.findByTestId("group-card-2330");
    expect(first.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByTestId("group-card-2317").getAttribute("aria-pressed")).toBe("false");
  });

  it("卡片是 role=button 容器(不是 <button>)且鍵盤按 Enter / Space 也切得動", async () => {
    const onPick = vi.fn();
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={onPick} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    // AD-4 / review R11:卡片內有完整分時圖(svg + 標籤),`<button>` 的內容模型只吃
    // phrasing content —— 巢狀互動元素在瀏覽器裡是未定義行為
    expect(card.getAttribute("role")).toBe("button");
    expect(card.getAttribute("tabindex")).toBe("0");
    fireEvent.keyDown(card, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith("2330");
    fireEvent.keyDown(card, { key: " " });
    expect(onPick).toHaveBeenCalledTimes(2);
  });
});

// 🟢 SC-2 / D4:toggle 四鈕上提到圖牆頂(卡片內不得有 button —— 點它會連帶切主檔)。
describe("GroupGridView 圖牆頂 toggle 列(SC-2 / AD-5)", () => {
  it("pill 列右側有均價 / CDP / MA / 量分佈 四鈕", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await screen.findByTestId("group-card-2330");
    for (const [key, label] of [
      ["vwap", "均價"],
      ["cdp", "CDP"],
      ["ma", "MA"],
      ["vp", "量分佈"],
    ] as const) {
      const btn = screen.getByTestId(`grid-toggle-${key}`);
      expect(btn.textContent).toBe(label);
      // AD-5:可用性是 per-code 的(某一檔沒日線 ≠ 整列不能按),整列一律可按
      expect(btn.hasAttribute("disabled")).toBe(false);
    }
  });

  it("卡片內不得有 button(巢狀互動元素 + 點 toggle 會連帶切主檔)", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    expect(card.querySelectorAll("button").length).toBe(0);
  });
});

// 🟢 edge 9:已訂閱、非 noData、非回補中,但**窗內**一格分鐘都沒有(盤前只有 08:59
// 的試撮分鐘 / 盤後只剩 13:31+)。整份幾何的 priceLine 會是空的,而 StockIntradayChart
// 自己的早退框帶 border/bg —— 掛在卡片內就是框中框。卡片自己接住,佔位樣式同三態。
describe("GroupGridView 窗內無分鐘(edge 9)", () => {
  it("只有 08:59 的窗外分鐘 → 卡片自佔位「尚無成交」,不掛圖", async () => {
    states["2330"] = state({ minutes: { "539": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } } });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("尚無成交"));
    expect(card.querySelector("svg")).toBeNull();
    // 同群組的另一檔窗內有分鐘 → 照畫(佔位是 per-card 的,不是整面)
    expect(screen.getByTestId("group-card-2317").querySelector("svg")).toBeTruthy();
  });
});
