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
}

function state(over: StateOver = {}) {
  return {
    minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    no_data: false,
    backfilling: false,
    ...over,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let states: Record<string, unknown>;

beforeEach(() => {
  window.localStorage.clear();
  states = {
    "2330": state(),
    "2317": state({ meta: { name: "鴻海", ref: 2_000_000, upper: null, lower: null, y_vol: 5 } }),
    "2881": state({ meta: { name: "富邦金", ref: 800_000, upper: null, lower: null, y_vol: 5 } }),
  };
  fetchMock = vi.fn(async (url: string) => {
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
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} />);
    expect(screen.getByText("尚無群組 — 到自選欄建立群組")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  // R17:空群組的 codes 是空陣列,打端點只會拿回 `{"states":{}}` —— 沒有任何卡片可畫,
  // 卻每 60s 燒一次來回。gate 在 hook 的 `enabled`,不是在畫面。
  it("空群組(成員 0)→ 專屬空態,且零請求", async () => {
    wrap(<GroupGridView groups={[{ name: "空組", codes: [] }]} quotes={{}} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} wlPending />);
    expect(screen.getByText("載入群組…")).toBeTruthy();
    expect(screen.queryByText("尚無群組 — 到自選欄建立群組")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  it("自選載入失敗 → 「自選載入失敗」,不冒充空清單", async () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} wlError />);
    expect(screen.getByText("自選載入失敗")).toBeTruthy();
    expect(screen.queryByText("尚無群組 — 到自選欄建立群組")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(groupCalls()).toHaveLength(0);
  });

  it("終態零群組(非載入中、非失敗)→ 才說「尚無群組」", () => {
    wrap(<GroupGridView groups={[]} quotes={{}} onPick={vi.fn()} wlPending={false} wlError={false} />);
    expect(screen.getByText("尚無群組 — 到自選欄建立群組")).toBeTruthy();
  });

  // 失敗但**手上還有舊資料**(TQ 的 error + cached data)時照畫 —— 群組結構是慢變數,
  // 上一份仍然有用;把它換成一句錯誤訊息是拿走使用者唯一能看的東西。
  it("有群組資料時,wlError 不遮掉既有卡片", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} wlError />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "半導體" }));
    expect(window.localStorage.getItem(STOCK_GROUP_KEY)).toBe("半導體");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
  });

  // edge 5(R10):群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名。
  // 不 fallback 的話畫面會停在「這個群組還沒有成員」而使用者根本沒有那一組。
  it("記住的群組已被刪 → fallback 第一個群組", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "已刪掉的組");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "半導體" }).getAttribute("aria-pressed"),
    ).toBe("true");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
  });

  it("記住的群組仍在 → 沿用它(不重設回第一個)", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "金融");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
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
      <GroupGridView groups={[{ name: "大群", codes: codes17 }]} quotes={{}} onPick={vi.fn()} />,
    );
    await waitFor(() => expect(screen.getByTestId("group-card-3000")).toBeTruthy());
    const grid = screen.getByTestId("group-grid");
    expect(grid.className).toContain("grid-cols-4");
    expect(grid.className).toContain("content-start");
    expect(grid.className).not.toContain("grid-template-rows");
  });
});

// SC-2:卡片要吃滿中區高度,圖跟著長高。`h-20` 由「唯一高度來源」降為**基準高**
// (`grow` 的 flex-basis 是 auto)—— 矩陣模式下長高吃滿格,捲動模式維持 80px。
// 變高後 y 向縮放可達 ~3×,線寬得靠 `vector-effect` 釘在螢幕像素(P1-5)。
describe("GroupGridView 高度均分 class", () => {
  it("常態卡片:svg 帶 grow + h-20,價線不隨拉伸變粗", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const card = await screen.findByTestId("group-card-2330");
    // SVG 的 `className` 是 SVGAnimatedString,子字串斷言得走 getAttribute(spec P2-1)
    const svgClass = card.querySelector("svg")?.getAttribute("class") ?? "";
    expect(svgClass).toContain("grow");
    expect(svgClass).toContain("h-20");
    // 有 ref 時價線是紅綠 clip 的**兩條** polyline(review A-4/B-3):querySelector
    // 只驗得到 bull 那條,bear 掉了 vector-effect 是零錯誤訊號的視覺回歸
    const lines = card.querySelectorAll('[data-testid="mini-price"]');
    expect(lines.length).toBe(2);
    for (const el of lines) {
      expect(el.getAttribute("vector-effect")).toBe("non-scaling-stroke");
    }
    expect(card.querySelector('[data-testid="mini-ref"]')?.getAttribute("vector-effect")).toBe(
      "non-scaling-stroke",
    );
  });

  it("無資料佔位也跟著長高(不然整列高度對不齊)", async () => {
    states["2330"] = state({ no_data: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const el = await screen.findByText("無資料");
    expect(el.className).toContain("grow");
    expect(el.className).toContain("h-20");
  });
});

describe("GroupGridView 卡片三態(backfilling → noData → 常態)", () => {
  it("常態 → 代碼 + 名稱 + mini 分時圖", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const card = await screen.findByTestId("group-card-2330");
    expect(card.textContent).toContain("2330");
    expect(card.textContent).toContain("台積電");
    expect(card.querySelector("svg")).toBeTruthy();
  });

  it("backfilling → 「回補中…」,不呈現半截圖", async () => {
    states["2330"] = state({ backfilling: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("回補中…"));
    expect(card.textContent).not.toContain("無資料");
  });

  // review A5:「回補中…」是**佔位**,只在真的沒東西可畫時才該蓋掉圖。已經有分鐘資料
  // (live tick 已進來、或前一輪的回補已落地)還蓋掉,等於每次重回補都讓卡片閃回空白 ——
  // 而重回補在鎖停日的漲跌停值變化上是常態。
  it("backfilling 但已有分鐘資料 → 照畫圖,不蓋「回補中…」", async () => {
    states["2330"] = state({ backfilling: true });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.querySelector("svg")).toBeTruthy());
    expect(card.textContent).not.toContain("回補中…");
  });

  it("noData → 「無資料」占位", async () => {
    states["2330"] = state({ no_data: true, minutes: {} });
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const card = await screen.findByTestId("group-card-2330");
    await waitFor(() => expect(card.textContent).toContain("無資料"));
    expect(card.querySelector("svg")).toBeNull();
  });

  // edge 6(R10:batch 化後 per-card 隔離不再成立)—— 整批一命
  it("batch 整批失敗 → 全部卡片「無資料」", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId("group-card-2330").textContent).toContain("無資料"),
    );
    expect(screen.getByTestId("group-card-2317").textContent).toContain("無資料");
  });
});

describe("GroupGridView 卡片價格(R11:p ?? ref)", () => {
  it("有成交 → 現價 + 漲跌%,漲紅跌綠", async () => {
    const quotes = {
      "2330": quote({ p: 2_400_000, chg_pct: 3.45 }),
      "2317": quote({ p: 1_900_000, chg_pct: -5 }),
    };
    wrap(<GroupGridView groups={GROUPS} quotes={quotes} onPick={vi.fn()} />);
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
    wrap(<GroupGridView groups={GROUPS} quotes={quotes} onPick={vi.fn()} />);
    const el = await screen.findByTestId("group-quote-2330");
    expect(el.textContent).toContain("2320");
    expect(el.textContent).toContain("參考");
    expect(el.className).not.toContain("text-bull");
    expect(el.className).not.toContain("text-bear");
  });

  // B3-b:`toContain("-")` 對 `-5.00%`、`2,380-` 之類的內容全都會通過 —— 缺值占位要
  // 的是**整格只有一個 `-`**,寫成全等才鎖得住
  it("p 與 ref 皆缺 → 整格只有「-」", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const el = await screen.findByTestId("group-quote-2330");
    expect(el.textContent).toBe("-");
  });
});

// review B1:mini 圖的末點延伸(design R10)靠 `quotes[code].p` 餵進去。這條接線斷掉
// 的失效樣態是「卡片上的線最久停在一分鐘前」—— 圖還在、值也對,只是不動;而群組檢視
// 存在的理由正是「現在有沒有一起動」。元件單測只驗到 `MiniIntradayChart` 收到 liveP
// 之後會延伸,驗不到 GroupGridView 有沒有真的把 quote 接上去。
describe("GroupGridView 現價延伸接線(review B1)", () => {
  function pointCount(card: HTMLElement): number {
    const el = card.querySelector('[data-testid="mini-price"]');
    return (el?.getAttribute("points") ?? "").split(" ").filter(Boolean).length;
  }

  it("盤中且 quote 有現價 → mini 圖比 snapshot 多一個延伸點", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0, 30)); // 10:00,窗內且非 09:00 那一格
    try {
      const { unmount } = wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
      const bare = await screen.findByTestId("group-card-2330");
      await waitFor(() => expect(pointCount(bare)).toBe(1)); // 基準:snapshot 只有 09:00 一格
      unmount();

      wrap(
        <GroupGridView
          groups={GROUPS}
          quotes={{ "2330": quote({ p: 2_400_000, chg_pct: 3.45 }) }}
          onPick={vi.fn()}
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
  it("整張卡片是一顆 button(有可及名稱),點了回呼該股", async () => {
    const onPick = vi.fn();
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={onPick} />);
    const card = await screen.findByTestId("group-card-2330");
    expect(card.tagName).toBe("BUTTON");
    expect(card.getAttribute("aria-label")).toBe("查看 2330 台積電");
    fireEvent.click(card);
    expect(onPick).toHaveBeenCalledWith("2330");
  });
});
