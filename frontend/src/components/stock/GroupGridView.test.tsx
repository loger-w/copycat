/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GroupGridView } from "@/components/stock/GroupGridView";
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

describe("GroupGridView 群組下拉", () => {
  it("預設第一個群組;成員卡片全數渲染", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    const select = screen.getByLabelText("選擇群組") as HTMLSelectElement;
    expect(select.value).toBe("半導體");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.getByTestId("group-card-2317")).toBeTruthy();
    expect(screen.queryByTestId("group-card-2881")).toBeNull();
  });

  it("切換群組 → 改打新群組的 codes", async () => {
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    await waitFor(() => expect(groupCalls()).toHaveLength(1));
    expect(groupCalls()[0]).toContain("codes=2330,2317");
    fireEvent.change(screen.getByLabelText("選擇群組"), { target: { value: "金融" } });
    await waitFor(() => expect(screen.getByTestId("group-card-2881")).toBeTruthy());
    expect(groupCalls().some((u) => u.includes("codes=2881"))).toBe(true);
  });

  // edge 5(R10):群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名。
  // 不 fallback 的話畫面會停在「這個群組還沒有成員」而使用者根本沒有那一組。
  it("記住的群組已被刪 → fallback 第一個群組", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "已刪掉的組");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    expect((screen.getByLabelText("選擇群組") as HTMLSelectElement).value).toBe("半導體");
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
  });

  it("記住的群組仍在 → 沿用它(不重設回第一個)", async () => {
    window.localStorage.setItem(STOCK_GROUP_KEY, "金融");
    wrap(<GroupGridView groups={GROUPS} quotes={{}} onPick={vi.fn()} />);
    expect((screen.getByLabelText("選擇群組") as HTMLSelectElement).value).toBe("金融");
    await waitFor(() => expect(screen.getByTestId("group-card-2881")).toBeTruthy());
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
