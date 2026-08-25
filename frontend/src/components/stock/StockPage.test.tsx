/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPage } from "@/components/stock/StockPage";
import type { StockStreamState } from "@/hooks/useStockStream";
import { emitSignal } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import type { StkfutSelection } from "@/lib/stkfut";
import type { StockAccum } from "@/lib/stock-accum";
import { wrap } from "@/test-utils";
import { FEE_DISCOUNT_KEY, STOCK_GROUP_KEY, STOCK_VIEW_KEY } from "@/lib/constants";
import type { StockView } from "@/lib/stock-view";
import { fmtPct } from "@/lib/format";
import { FEE_DISCOUNT_DEFAULT, positionEcon } from "@/lib/ladder-position";
import { pnlText } from "@/lib/pnl-format";
import type { CapitalPosition } from "@/types";

// 🔴-3:code / 資料流已上提到 App(D-3)→ 本元件改吃 props,不再自建 WS、不再讀 localStorage。
// 「TC4 斷線告警列(W-B5)」文案斷言原本掛在此檔的 WS 驅動路徑上,改以 props 直接驅動,
// 文案字串逐字不變;「選檔後渲染委託/部位」已逐條搬到 RightRail.test.tsx。

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
  book: { bids: [[2_375_000, 5]], asks: [[2_380_000, 3]] },
  meta: {
    name: "台積電",
    ref: 2_320_000,
    upper: 2_550_000,
    lower: 2_090_000,
    y_vol: 100,
  },
  noData: false,
} as unknown as StockAccum;

function stream(over: Partial<StockStreamState> = {}): StockStreamState {
  return {
    accum: ACCUM,
    watchlist: {},
    status: { tc4: "up", backfilling: null },
    stkfut: null,
    wsStatus: "open",
    ...over,
  };
}

/** header 倉位段(SC-3)的部位列。預設空 —— 既有案不該因為多了一條路由而長出內容。 */
let positions: CapitalPosition[] = [];

beforeEach(() => {
  window.localStorage.clear();
  positions = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      // 不接這條的話 useCapitalPositions 掉進 404 → data undefined → 恆無倉,SC-3
      // 的斷言會靜默 vacuous(而「沒渲染」與「查不到」在 queryBy 下長得一模一樣)
      if (String(url).includes("/api/capital/positions")) {
        return new Response(JSON.stringify({ positions }));
      }
      if (String(url).includes("/api/stock/watchlist")) {
        return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330"] }] }));
      }
      if (String(url).includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: [] }));
      }
      if (String(url).includes("/api/stock/overlay")) {
        return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
      }
      if (String(url).includes("/api/stock/signals/rules")) {
        return new Response(JSON.stringify({ rules: [] }));
      }
      // 群組檢視 batch(group-grid SC-4)。預設檢視是單檔 → 這支多半不會被打到,
      // 但 stub 少一條分支的代價是掉進 404 → query error,而群組檢視的錯誤態
      // 恰好也是「無資料」,測試會綠得毫無意義。
      if (String(url).includes("/api/stock/group-state")) {
        return new Response(JSON.stringify({ states: {} }));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StockPage", () => {
  it("未選檔時顯示提示;自選側欄仍渲染", async () => {
    wrap(<StockPage code={null} onSelect={vi.fn()} stream={stream({ accum: null })} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy()); // 側欄
    expect(screen.getByText(/從自選清單選擇/)).toBeTruthy();
  });

  // 🔴 N109:`tc4 === "down"` 有兩個來源 —— engine 在但 TC4 斷(恢復會自癒回補),
  // 以及 XR-3 後的**無 engine 模式**(server 啟動時 TC4 沒開,stock engine 只在 boot 建
  // → TC4 之後開起來也不會自癒,得重啟伺服器)。兩者的 seed 逐值相同,前端分不出來
  // (`/api/health` 刻意不含引擎健康度),所以文案要對**兩態都誠實**:改前那句
  // 「恢復後自動回補」對無 engine 模式是錯的,而使用者只會一直等。
  // 斷言字串 2026-08-24 two-axis 收修時**事前標為該變**:「server」→「伺服器」(UI 全繁中)。
  it("TC4 斷線告警列:自癒與需重啟兩態都講得到", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream({ status: { tc4: "down", backfilling: null } })}
      />,
    );
    const note = screen.getByText(/達錢 4 未連線/);
    expect(note.textContent).toContain("自動回補");
    expect(note.textContent).toContain("重啟伺服器");
  });

  it("伺服器斷線顯示重連告警列(文案不變)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ wsStatus: "closed" })} />);
    expect(screen.getByText(/伺服器連線中斷,重連中…/)).toBeTruthy();
  });

  it("選檔後中間主區 = 圖表切換 + 五檔 + 明細(SC-6/SC-7)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.getByRole("radio", { name: "江波圖" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "1分K" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "5分K" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "日K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "買1 2375" })).toBeTruthy(); // 五檔(W-16:aria-label 格式是定位鍵)
    expect(screen.getByText("時間")).toBeTruthy(); // 明細表頭
  });

  it("accum 是 tape=0 取回(tapeOmitted)→ 明細空態印「載入明細…」而非「尚無成交」(SC-4)", () => {
    const accum = { ...ACCUM, ticks: [], tapeOmitted: true } as unknown as StockAccum;
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ accum })} />);
    expect(screen.getByText("載入明細…")).toBeTruthy();
    expect(screen.queryByText("尚無成交")).toBeNull();
  });

  it("中間不再渲染閃電梯 / 委託 / 部位(已移到右欄)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
    expect(screen.queryByText("委託")).toBeNull();
    expect(screen.queryByText("部位")).toBeNull();
  });

  // 🔴 round3 SC-6:高度分配反過來 —— 圖表吃剩餘空間、下半列固定高貼底。
  // jsdom 沒有版面引擎量不到真實高度,只能鎖住產生該效果的 class 組合(真實溢出量測走
  // Phase 7 真環境 scrollHeight/clientHeight)。
  //   下半列 h-56 shrink-0 → **確定高度**。TickTape 根節點的 h-full + overflow-y-auto
  //     需要父層有確定高度才會內捲;父層若退化成「內容自然高」,30 筆明細會把該列撐成
  //     ~770px,每點一次載入更多再 +720px,圖表被擠光而 <main> 靜默裁切。
  //   圖表 wrapper flex-1 min-h-0 → 吃掉剩餘,不再是 shrink-0 的固定比例高。
  it("下半列固定高、圖表吃剩餘空間(SC-6)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    const row = screen.getByTestId("stock-lower-row");
    expect(row.className).toContain("h-56");
    expect(row.className).toContain("shrink-0");
    expect(row.className).not.toContain("flex-1");
    // 兩塊子 wrapper 都要 min-h-0(否則內層 overflow 容器算不出可捲高度)
    for (const child of [...row.children] as HTMLElement[]) {
      expect(child.className).toContain("min-h-0");
    }
    // self-start 移除:五檔卡片要撐滿列高才能與明細底邊齊平(SC-6「貼底」)
    expect((row.firstElementChild as HTMLElement).className).not.toContain("self-start");
  });

  // W-11 regression lock:捲軸逃生口不可拆。極矮視窗 / 字級放大時內容仍會超出,
  // 拆掉 overflow-y-auto 會讓「載入更多」變成不可達而不是可捲到。
  it("<main> 保留 overflow-y-auto 當逃生口(W-11)", () => {
    const { container } = wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    const main = container.querySelector("main")!;
    expect(main.className).toContain("overflow-y-auto");
    expect(main.className).toContain("min-h-0");
  });
});

// 🔴 M8:明細的「載入更多」筆數是 TickTape 內部 state,切股時必須跟著歸零 ——
// 換一檔股票卻沿用上一檔展開到一半的筆數,與 pickerOpen 的換股歸零不一致
describe("StockPage 切股時明細展開筆數歸零(M8)", () => {
  function accumWithTicks(code: string): StockAccum {
    return {
      ...ACCUM,
      code,
      ticks: [...Array(70).keys()].map((i) => ({
        t: `09:0${Math.floor(i / 10)}:0${i % 10}.000`,
        p: 2_380_000,
        q: 1,
        side: "outer",
      })),
      // 這份 fixture 只餵明細表(tape),VP 不是它要驗的東西 —— 但 `vp` 是必填欄,
      // 每個 `as unknown as StockAccum` 站點都自己列全,不倚賴 spread 幫忙補
      vp: new Map(),
    } as unknown as StockAccum;
  }

  function rows(container: HTMLElement): number {
    return container.querySelectorAll("tbody tr").length;
  }

  it("展開後切股 → 顯示筆數回初始值", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const page = (code: string) => (
      <QueryClientProvider client={client}>
        <StockPage
          code={code}
          onSelect={vi.fn()}
          stream={stream({ accum: accumWithTicks(code) })}
        />
      </QueryClientProvider>
    );
    const { container, rerender } = render(page("2330"));
    expect(rows(container)).toBe(30);
    fireEvent.click(screen.getByRole("button", { name: "載入更多" }));
    expect(rows(container)).toBe(60);

    // 切股(元件不 unmount,只是 props 換了)
    rerender(page("2317"));
    expect(rows(container)).toBe(30);
  });

  // 🔴 F-4:同一檔股票的現貨與各月合約是**不同標的**,而 `code` 在換月與現貨↔合約時
  // 恆不變 → `key={code}` 不重掛,展開到一半的筆數跟著跨標的存活(同頁的 pickerOpen、
  // useStockStream deps、RightRail centerRequest 都已改吃 instrumentKey,獨漏此處)。
  it("同股切合約 → 顯示筆數回初始值(重掛鍵是 instrumentKey 不是 code)", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const page = (contract: StkfutSelection | null) => (
      <QueryClientProvider client={client}>
        <StockPage
          code="2330"
          onSelect={vi.fn()}
          stream={stream({ accum: accumWithTicks("2330") })}
          contract={contract}
          onContract={vi.fn()}
        />
      </QueryClientProvider>
    );
    const { container, rerender } = render(page(null));
    expect(rows(container)).toBe(30);
    fireEvent.click(screen.getByRole("button", { name: "載入更多" }));
    expect(rows(container)).toBe(60);

    // 現貨 → 合約(股號不變)
    rerender(page({ prod: "CDF", ym: "202609", mini: false, unit: 2000 }));
    expect(rows(container)).toBe(30);

    // 換月(股號仍不變)
    fireEvent.click(screen.getByRole("button", { name: "載入更多" }));
    expect(rows(container)).toBe(60);
    rerender(page({ prod: "CDF", ym: "202610", mini: false, unit: 2000 }));
    expect(rows(container)).toBe(30);
  });
});

// 🟢 round4 項 4:搜尋改預覽後,「加入自選」的入口移到分時圖上方的報價 header
describe("StockPage 漲跌停亮燈(round6 項 3)", () => {
  const atLimit = (p: number) =>
    stream({ accum: { ...ACCUM, last: { p, t: "09:00:01.000", cum_vol: 1 } } as StockAccum });

  it("漲停 → header 的價格 + %數整塊紅底白字", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atLimit(2_550_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).toContain("bg-bull");
    expect(cls).toContain("text-white");
  });

  it("跌停 → 綠底白字", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atLimit(2_090_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).toContain("bg-bear");
    expect(cls).toContain("text-white");
  });

  it("未漲跌停 → 不亮燈,維持漲跌文字色(SC-3.4)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atLimit(2_380_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).not.toContain("bg-bull");
    expect(cls).not.toContain("bg-bear");
    expect(cls).toContain("text-bull"); // 2380 > ref 2320
  });
});

// 🔴 mod/stock-price-prominence:header 現價要成為整列唯一視覺焦點。
// jsdom 量不到字級,只能鎖住產生該效果的 class 組合(真實版面走截圖對照)。
describe("StockPage 現價醒目化", () => {
  const atPrice = (p: number) =>
    stream({ accum: { ...ACCUM, last: { p, t: "09:00:01.000", cum_vol: 1 } } as StockAccum });

  // SC-1:絕對字級 + **相對於股名**。只斷言 text-3xl 會在「股名也一起放大」時仍綠 = vacuous;
  // 正向鎖住股名維持 text-lg 才真的鎖到「現價 > 股名」這個相對關係(反向 not 斷言在
  // 股名被改成 text-2xl 之類時同樣抓不到)。
  it("未觸價 → 現價 text-3xl + font-semibold,且字級大於股名(SC-1)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atPrice(2_380_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).toContain("text-3xl");
    expect(cls).toContain("font-semibold");
    expect(cls).toContain("font-mono"); // 數字字體不可因放大被換掉(白名單 4)
    const heading = screen.getByRole("heading", { name: /台積電/ });
    expect(heading.className).toContain("text-lg");
    expect(heading.className).not.toContain("text-3xl");
  });

  // SC-2:% 同步放大一級(text-xs → text-sm),但刻意不與主數字等比;
  // font-normal 抵銷父層繼承的 semibold;顏色一律繼承父層(自帶顏色會在反白時脫鉤)
  it("漲跌 % 放大為 text-sm、字重還原、顏色純繼承(SC-2)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atPrice(2_380_000)} />);
    const cls = screen.getByTestId("page-quote-pct").className;
    expect(cls).toContain("text-sm");
    expect(cls).toContain("ml-1"); // 緊貼主數字右側的間距
    expect(cls).toContain("font-normal");
    expect(cls).not.toMatch(/text-(bull|bear|ink|white)/);
  });

  // SC-3:字級與反白是兩組獨立 class,twMerge 不可把任一方吃掉;
  // px-1.5 / rounded 是反白塊的形狀,放大後仍須原樣保留(白名單 8)
  it("漲停 → text-3xl 與反白底色白字並存(SC-3)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atPrice(2_550_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).toContain("text-3xl");
    expect(cls).toContain("bg-bull");
    expect(cls).toContain("text-white");
    expect(cls).toContain("px-1.5");
    expect(cls).toContain("rounded");
  });

  it("跌停 → text-3xl 與反白底色白字並存(SC-3)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={atPrice(2_090_000)} />);
    const cls = screen.getByTestId("page-quote").className;
    expect(cls).toContain("text-3xl");
    expect(cls).toContain("bg-bear");
    expect(cls).toContain("text-white");
    expect(cls).toContain("px-1.5");
    expect(cls).toContain("rounded");
  });

  // 白名單 5:chg 算不出來(無參考價)時只是不渲染 %,主數字照放大照顯示 ——
  // 新加的 testid 讓「% 恆存在」變成很容易寫進去的錯誤假設
  it("無參考價 → 不渲染 %,主數字仍放大顯示(白名單 5)", () => {
    const noRef = stream({
      accum: { ...ACCUM, meta: { ...ACCUM.meta!, ref: null } } as StockAccum,
    });
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={noRef} />);
    expect(screen.queryByTestId("page-quote-pct")).toBeNull();
    expect(screen.getByTestId("page-quote").className).toContain("text-3xl");
  });
});

describe("StockPage 加入自選(round4 項 4)", () => {
  let putBodies: unknown[];

  function mockApi(codes: string[], groups: { name: string; codes: string[] }[]): void {
    putBodies = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body)) as unknown;
          putBodies.push(body);
          return new Response(JSON.stringify(body));
        }
        if (String(url).includes("/api/stock/names")) {
          return new Response(JSON.stringify({ names: [], count: 0 }));
        }
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify({ codes, groups }));
        }
        if (String(url).includes("/api/stock/bars")) return new Response(JSON.stringify({ bars: [] }));
        if (String(url).includes("/api/stock/overlay")) {
          return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
        }
        if (String(url).includes("/api/stock/signals/rules")) {
          return new Response(JSON.stringify({ rules: [] }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
  }

  const GROUPS = [{ name: "主力", codes: ["2330"] }];

  it("看非自選股 → header 出現「加入自選」;已在自選 → 不出現", async () => {
    mockApi(["2330"], GROUPS);
    const { rerender } = wrap(
      <StockPage code="2317" onSelect={vi.fn()} stream={stream()} />,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    cleanup();
    mockApi(["2330"], GROUPS);
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.queryByText("台積電")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "加入自選" })).toBeNull();
    expect(rerender).toBeTruthy();
  });

  it("點按鈕 → 展開群組清單 + 未分組", async () => {
    mockApi(["2330"], GROUPS);
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    expect(screen.getByLabelText("加入 2317 到 主力")).toBeTruthy();
    expect(screen.getByLabelText("加入 2317 到未分組")).toBeTruthy();
  });

  it("選群組 → **PUT 恰一筆**,codes 與該組同時含該檔", async () => {
    mockApi(["2330"], GROUPS);
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    fireEvent.click(screen.getByLabelText("加入 2317 到 主力"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    const body = putBodies[0] as { codes: string[]; groups: { name: string; codes: string[] }[] };
    expect(body.codes).toEqual(["2330", "2317"]);
    expect(body.groups[0]!.codes).toEqual(["2330", "2317"]);
  });

  it("選「未分組」→ 只加進 codes,群組零改動", async () => {
    mockApi(["2330"], GROUPS);
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    fireEvent.click(screen.getByLabelText("加入 2317 到未分組"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    const body = putBodies[0] as { codes: string[]; groups: { name: string; codes: string[] }[] };
    expect(body.codes).toEqual(["2330", "2317"]);
    expect(body.groups).toEqual(GROUPS);
  });

  // review F5:R16 指名的「連點兩下」場景 —— 第一次 PUT 未回前 wl 仍是舊值、gate 仍 true。
  // 沒有這支測試的話,把 commit() 的深度比對拿掉不會有任何測試紅。
  it("PUT pending 期間重複選同一組 → 仍只送一筆 PUT(W-9 零 PUT 早退)", async () => {
    const bodies: unknown[] = [];
    const gate: { release?: () => void } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          bodies.push(JSON.parse(String(init.body)));
          // 卡住第一筆:wl 不會被更新 → gate 仍為 true,重現連點兩下
          await new Promise<void>((r) => { gate.release = r; });
          return new Response(String(init.body));
        }
        if (String(url).includes("/api/stock/names")) {
          return new Response(JSON.stringify({ names: [], count: 0 }));
        }
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify({ codes: ["2330"], groups: GROUPS }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    fireEvent.click(screen.getByLabelText("加入 2317 到 主力"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    // pending 期間「加入自選」本身就停用 → 面板連開都開不了,第二筆 PUT 無從發生
    const trigger = screen.getByRole("button", { name: "加入自選" }) as HTMLButtonElement;
    expect(trigger.disabled).toBe(true);
    fireEvent.click(trigger);
    expect(screen.queryByLabelText("加入 2317 到 主力")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(bodies).toHaveLength(1);
    gate.release?.();
  });

  // review F3:App 渲染 StockPage 沒帶 key,同一 instance 活過切檔 → 面板留在展開狀態
  // 而按鈕已綁到新 code,誤觸就把錯的股票靜默加進群組
  it("切換股票 → 展開中的群組面板自動收起", async () => {
    mockApi(["2330"], GROUPS);
    const { rerender } = wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    expect(screen.getByLabelText("加入 2317 到 主力")).toBeTruthy();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <StockPage code="2331" onSelect={vi.fn()} stream={stream()} />
      </QueryClientProvider>,
    );
    expect(screen.queryByLabelText(/加入 .* 到 主力/)).toBeNull();
  });

  it("自選尚未載入 → 按鈕不渲染(EMPTY_WL fallback 上按加入會把整份自選清空)", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Promise<Response>(() => {})), // 永不 resolve
    );
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.queryByRole("button", { name: "加入自選" })).toBeNull();
  });

  it("PUT 失敗 → header 顯示中文文案(上限 / 壞碼看得到)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return new Response(JSON.stringify({ detail: { error: "WATCHLIST_FULL" } }), {
            status: 400,
          });
        }
        if (String(url).includes("/api/stock/names")) {
          return new Response(JSON.stringify({ names: [], count: 0 }));
        }
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify({ codes: ["2330"], groups: GROUPS }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
    wrap(<StockPage code="2317" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "加入自選" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "加入自選" }));
    fireEvent.click(screen.getByLabelText("加入 2317 到未分組"));
    await waitFor(() => expect(screen.getByText("自選已達 50 檔上限")).toBeTruthy());
  });
});

// 🟢 stock-signals T11(SC-9):訊號欄進版面最左。
// 訊號不用 mock hook 餵 —— 直接發 bus 事件走 useSignalFeed 的 live 路徑,
// 測到的是「WS 收到訊號 → 列表出現 → 點了切主檔」整條真實接線(mock 掉 feed
// 只會鎖住 props 傳遞,rail 沒接上 hook 也照樣綠)。
describe("StockPage 訊號欄(SC-9)", () => {
  function sig(over: Partial<SignalMsg> = {}): SignalMsg {
    return {
      type: "signal",
      id: "sig-1",
      kind: "surge",
      code: "2317",
      name: "鴻海",
      price: 2_000_000,
      time: "09:15:03",
      levels: [],
      direction: null,
      pct: 2.5,
      touch_count: 1,
      ...over,
    };
  }

  it("SignalRail 渲染在自選側欄「之前」(最左欄)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    const rail = screen.getByTestId("signal-rail");
    const sidebar = screen.getByLabelText("自選清單");
    // 位置關係要正向鎖:只斷言「rail 存在」會在它被塞到最右邊時照樣綠
    expect(
      rail.compareDocumentPosition(sidebar) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("WS 訊號進來 → 列出;點該列切換主檔(onSelect)", async () => {
    const onSelect = vi.fn();
    wrap(<StockPage code="2330" onSelect={onSelect} stream={stream()} />);
    act(() => emitSignal(sig()));
    const label = await screen.findByText("爆拉 +2.50%");
    fireEvent.click(label.closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("2317");
  });

});

// 🟢 signal-rules SC-7:四鍵開關退場 → 規則列 + 規則 Dialog。
// 接線在本層(SignalRail / SignalRulesDialog 都不自己抓 rules)。
describe("StockPage 訊號規則(signal-rules SC-7)", () => {
  const RULE = {
    id: "r-1-000",
    name: "我的爆量",
    kind: "vol_burst",
    enabled: true,
    notify_discord: true,
    cooldown_secs: 300,
    params: { ratio: 3, window_secs: 60, min_elapsed_min: 5, min_window_lots: 100, min_day_lots: 500 },
    cdp_levels: [],
  };

  let writes: { url: string; init: RequestInit }[];

  function mockRules(): void {
    writes = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method !== undefined) {
          writes.push({ url: String(url), init });
          return new Response(String(init.body ?? "{}"));
        }
        if (String(url).includes("/api/stock/signals/rules")) {
          return new Response(JSON.stringify({ rules: [RULE] }));
        }
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify({ codes: ["2330"], groups: [] }));
        }
        if (String(url).includes("/api/stock/names")) {
          return new Response(JSON.stringify({ names: [], count: 0 }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
  }

  it("規則列顯示規則名;點開關 → PUT 該規則、enabled 反轉", async () => {
    mockRules();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    const rules = screen.getByTestId("signal-rail-rules");
    await waitFor(() => expect(within(rules).getByRole("switch", { name: /我的爆量/ })).toBeTruthy());
    fireEvent.click(within(rules).getByRole("switch", { name: /我的爆量/ }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]?.url).toBe("/api/stock/signals/rules/r-1-000");
    expect(writes[0]?.init.method).toBe("PUT");
    expect((JSON.parse(String(writes[0]?.init.body)) as { enabled: boolean }).enabled).toBe(false);
  });

  it("點「規則」鈕 → 規則 Dialog 開啟(列出該規則)", async () => {
    mockRules();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "管理訊號規則" })).toBeTruthy());
    // 逐 token 比對:`flex-col` 恆在 class 上,子字串斷言鎖不到 display 的切換
    const cls = () => (screen.getByTestId("signal-rules-dialog").className ?? "").split(/\s+/);
    expect(cls()).toContain("hidden");
    fireEvent.click(screen.getByRole("button", { name: "管理訊號規則" }));
    expect(cls()).toContain("flex");
    expect(within(screen.getByTestId("signal-rules-dialog")).getByText("我的爆量")).toBeTruthy();
  });
});

// 🟢 group-grid SC-3:個股頁新增「單檔｜群組」檢視切換。
// pill 掛在 main 頂層、`code === null` 與 `accum === null` 兩個條件分支**之外**(design R6)
// —— 未選股 / 主圖 snapshot 還沒回來時,群組檢視仍要可達。
describe("StockPage 群組檢視(group-grid SC-3)", () => {
  const GROUP_WL = {
    codes: ["2330", "2317"],
    groups: [{ name: "半導體", codes: ["2330", "2317"] }],
  };

  function mockGroupApi(): void {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify(GROUP_WL));
        }
        if (String(url).includes("/api/stock/group-state")) {
          return new Response(
            JSON.stringify({
              states: {
                "2330": {
                  minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
                  meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 1 },
                  no_data: false,
                  backfilling: false,
                },
                "2317": {
                  minutes: {},
                  meta: { name: "鴻海", ref: 2_000_000, upper: null, lower: null, y_vol: 1 },
                  no_data: true,
                  backfilling: false,
                },
              },
            }),
          );
        }
        if (String(url).includes("/api/stock/names")) {
          return new Response(JSON.stringify({ names: [], count: 0 }));
        }
        if (String(url).includes("/api/stock/bars")) {
          return new Response(JSON.stringify({ bars: [] }));
        }
        if (String(url).includes("/api/stock/overlay")) {
          return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
        }
        if (String(url).includes("/api/stock/signals/rules")) {
          return new Response(JSON.stringify({ rules: [] }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
  }

  it("預設單檔檢視:pill 在、群組 grid 不在", () => {
    mockGroupApi();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    // a11y 批:檢視 pill 改 RadioPills(sr-only radio),單選態由 checked 表達
    const single = screen.getByRole("radio", { name: "單檔" }) as HTMLInputElement;
    const grid = screen.getByRole("radio", { name: "群組" }) as HTMLInputElement;
    expect(single.checked).toBe(true);
    expect(grid.checked).toBe(false);
    expect(screen.getByRole("radiogroup", { name: "檢視" })).toBeTruthy();
    expect(screen.queryByLabelText("選擇群組")).toBeNull();
    expect(screen.getByTestId("stock-lower-row")).toBeTruthy();
  });

  it("切到群組 → header / 圖表 / 下半列讓位給卡片 grid;訊號欄與自選欄不動", async () => {
    mockGroupApi();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.queryByTestId("stock-lower-row")).toBeNull();
    expect(screen.queryByTestId("page-quote")).toBeNull();
    expect(screen.getByTestId("signal-rail")).toBeTruthy();
    expect(screen.getByLabelText("自選清單")).toBeTruthy();
  });

  // R6 鎖:pill 若掛在 `code === null` 分支內,未選股時就永遠切不到群組檢視
  it("未選股(code=null)仍切得到群組檢視", async () => {
    mockGroupApi();
    wrap(<StockPage code={null} onSelect={vi.fn()} stream={stream({ accum: null })} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.queryByText(/從自選清單選擇/)).toBeNull();
  });

  // R6 鎖的另一半:主圖 snapshot 還沒回來(accum === null)時也不可把群組檢視關在門外
  it("主圖 snapshot 未到(accum=null)仍切得到群組檢視", async () => {
    mockGroupApi();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ accum: null })} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    await waitFor(() => expect(screen.getByTestId("group-card-2330")).toBeTruthy());
    expect(screen.queryByText("載入中…")).toBeNull();
  });

  // 🔴 group-grid-full-chart SC-3:點卡片的意圖改了。卡片上現在是**單檔同款**的完整
  // 分時圖 —— 要看的細節就在圖牆上,點下去是「把右欄閃電梯的標的換成這一檔」,不是
  // 「離開圖牆去看單檔頁」。自動切走的舊行為會讓每次換標的都得再點一次「群組」回來,
  // 而盯盤時圖牆本身就是主畫面。進單檔的路徑只剩檢視 pill(D3)。
  // 🟢 F2(chart-ux-batch-0826):群組檢視下點側欄「某群組區段」的列 → 圖牆切到那一組;
  // 點未分組列不切;單檔檢視下側欄行為不變(只換主檔)。
  it("群組檢視下點側欄群組列 → 圖牆切到該組;未分組列不切;單檔檢視不動群組", async () => {
    const TWO = {
      codes: ["2330", "2317", "2881", "3231"],
      groups: [
        { name: "半導體", codes: ["2330", "2317"] },
        { name: "金融", codes: ["2881"] },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stock/watchlist")) return new Response(JSON.stringify(TWO));
        if (String(url).includes("/api/stock/group-state")) {
          return new Response(JSON.stringify({ states: {} }));
        }
        if (String(url).includes("/api/stock/signals/rules")) {
          return new Response(JSON.stringify({ rules: [] }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
    const onSelect = vi.fn();
    wrap(<StockPage code="2330" onSelect={onSelect} stream={stream()} />);
    await waitFor(() => expect(screen.getByTestId("wl-group-金融")).toBeTruthy());
    // 單檔檢視:點金融區段的 2881 → 只換主檔
    fireEvent.click(within(screen.getByTestId("wl-group-金融")).getByTestId("wl-select-2881"));
    expect(onSelect).toHaveBeenLastCalledWith("2881");
    expect(window.localStorage.getItem(STOCK_GROUP_KEY)).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    const rail = await screen.findByLabelText("選擇群組");
    expect((within(rail).getByRole("radio", { name: "半導體" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(screen.getByTestId("wl-group-金融")).getByTestId("wl-select-2881"));
    expect((within(rail).getByRole("radio", { name: "金融" }) as HTMLInputElement).checked).toBe(true);
    expect(window.localStorage.getItem(STOCK_GROUP_KEY)).toBe("金融");
    expect(onSelect).toHaveBeenLastCalledWith("2881");
    // 未分組列(3231 不屬任何組)→ 群組不動
    fireEvent.click(screen.getByTestId("wl-select-3231"));
    expect((within(rail).getByRole("radio", { name: "金融" }) as HTMLInputElement).checked).toBe(true);
    expect(onSelect).toHaveBeenLastCalledWith("3231");
  });

  it("點卡片 → onSelect 該股,檢視仍停在群組", async () => {
    mockGroupApi();
    const onSelect = vi.fn();
    wrap(<StockPage code="2330" onSelect={onSelect} stream={stream()} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    const card = await screen.findByTestId("group-card-2317");
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith("2317");
    // 兩側都要釘:群組列還在(沒被切走)+ 單檔的下半列沒有回來(不是兩個檢視同時掛)
    expect(screen.getByLabelText("選擇群組")).toBeTruthy();
    expect(screen.queryByTestId("stock-lower-row")).toBeNull();
  });

  // review A4 的接線半:三態要分得出來,`wl` 的 isPending / isError 就得真的傳下去。
  // 只在 GroupGridView 那一側測 props 是 vacuous —— StockPage 忘了傳照樣全綠,而畫面
  // 會在自選讀不到時說「尚無群組 — 到自選欄建立群組」,把「後端出事」講成「你沒建群組」。
  it("自選載入失敗 → 群組檢視說「自選載入失敗」,不冒充零群組", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stock/watchlist")) {
          return new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 });
        }
        if (String(url).includes("/api/stock/signals/rules")) {
          return new Response(JSON.stringify({ rules: [] }));
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }),
    );
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    // `useStockWatchlist` 是 retry: 1 + 指數退避 → 錯誤終態要等第二次失敗(skill:
    // TanStack Query error path 的 waitFor 必須放寬 timeout)
    await waitFor(() => expect(screen.getByText("自選載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("尚無群組 — 到自選欄建立群組")).toBeNull();
    // it 自己的 timeout 也要放寬:預設 5s 與 waitFor 的 5s 撞在一起,失敗訊息會變成
    // 「Test timed out」而看不出是哪一條斷言沒過
  }, 10_000);

  // 🔴 review F1:`view` 有**兩份初值**(本元件與 App 各自 `readStockView()`)。同一個
  // 分頁內兩者相等,但另一個視窗改過 localStorage 之後,App 讀到的是它自己掛載當下那
  // 一份 —— 本元件掛在「群組」而 App 以為「單檔」,那趟 `/api/stock/state` 照樣拖回整份
  // tape(MB 級),而畫面上完全看不出來(B15 省流量整條失效)。掛載通知一則就對齊。
  it("掛載時把實際檢視通知上層一次(localStorage=group)", async () => {
    mockGroupApi();
    window.localStorage.setItem(STOCK_VIEW_KEY, "group");
    const onViewChange = vi.fn();
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream()}
        onViewChange={onViewChange}
      />,
    );
    await waitFor(() => expect(onViewChange).toHaveBeenCalledWith("group"));
    expect(onViewChange).toHaveBeenCalledTimes(1);
  });

  it("掛載通知也涵蓋單檔(壞值 / 未設 → 兩邊都得知道是 single)", async () => {
    mockGroupApi();
    window.localStorage.setItem(STOCK_VIEW_KEY, "亂寫");
    const onViewChange = vi.fn();
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream()}
        onViewChange={onViewChange}
      />,
    );
    await waitFor(() => expect(onViewChange).toHaveBeenCalledWith("single"));
    expect(onViewChange).toHaveBeenCalledTimes(1);
  });

  // 掛載通知會讓 App setState → 本元件重繪。沒有「只發一次」的守門就是 render 迴圈,
  // 而 App 傳下來的 `onViewChange` 每次重繪都是新的函式(setState 的 setter 其實穩定,
  // 但這裡不倚賴那個巧合)。
  it("上層重繪(換 props / 換 onViewChange 身分)不重發掛載通知", async () => {
    mockGroupApi();
    window.localStorage.setItem(STOCK_VIEW_KEY, "group");
    // 同一個 client 重繪(不能用 `wrap` 的 rerender:那會換掉 QueryClient)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tree = (cb: (next: StockView) => void) => (
      <QueryClientProvider client={client}>
        <StockPage code="2330" onSelect={vi.fn()} stream={stream()} onViewChange={cb} />
      </QueryClientProvider>
    );
    const first = vi.fn();
    const { rerender } = render(tree(first));
    await waitFor(() => expect(first).toHaveBeenCalledTimes(1));
    const second = vi.fn();
    rerender(tree(second));
    expect(second).not.toHaveBeenCalled();
    expect(first).toHaveBeenCalledTimes(1);
  });

  it("檢視選擇存進 localStorage,重掛後還原", async () => {
    mockGroupApi();
    const { unmount } = wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    fireEvent.click(screen.getByRole("radio", { name: "群組" }));
    await waitFor(() => expect(screen.getByLabelText("選擇群組")).toBeTruthy());
    unmount();
    mockGroupApi();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByLabelText("選擇群組")).toBeTruthy());
  });
});

// 🟢 stkfut-contracts SC-4:header 合約下拉。契約選擇的**狀態持有者是 App**(D5),
// 本元件只負責「畫得出來 + 選了要通知上層」—— 所以這裡測的是渲染與回呼,
// 換股重置與資料流在 App.test.tsx。
describe("StockPage 合約下拉(SC-4)", () => {
  const CONTRACTS = {
    code: "2330",
    name: "台積電",
    std: { prod: "CDF", contracts: ["202608", "202609"], unit: 2000 },
    mini: { prod: "QFF", contracts: ["202608", "202609"], unit: 100 },
  };

  /** 在 beforeEach 的預設 stub 之上補合約端點(其餘路由行為逐字不變) */
  function withContracts(body: unknown = CONTRACTS, status = 200) {
    const base = globalThis.fetch as ReturnType<typeof vi.fn>;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stock/stkfut/contracts/")) {
          return new Response(JSON.stringify(body), { status });
        }
        return base(url);
      }),
    );
  }

  it("無期貨(404)→ 不渲染下拉", async () => {
    // 預設 stub 對未知路由就是 404 = NO_STKFUT
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() => expect(screen.getByTestId("stock-lower-row")).toBeTruthy());
    expect(screen.queryByLabelText("合約")).toBeNull();
  });

  it("有期貨 → 現貨 + 標準月 + 小型月三類選項皆可指認", async () => {
    withContracts();
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    const select = await screen.findByLabelText("合約");
    const labels = [...select.querySelectorAll("option")].map((o) => o.textContent);
    expect(labels).toEqual(["現貨", "2026/08", "2026/09", "小型 2026/08", "小型 2026/09"]);
    expect((select as HTMLSelectElement).value).toBe(""); // 預設現貨
  });

  it("選標準月 → 上層收到 {prod, ym, mini:false}", async () => {
    withContracts();
    const onContract = vi.fn();
    wrap(
      <StockPage code="2330" onSelect={vi.fn()} stream={stream()} contract={null} onContract={onContract} />,
    );
    const select = await screen.findByLabelText("合約");
    fireEvent.change(select, { target: { value: "CDF:202609" } });
    expect(onContract).toHaveBeenCalledWith({ prod: "CDF", ym: "202609", mini: false, unit: 2000 });
  });

  it("選小型月 → mini:true(乘數與口數標籤靠它分岔)", async () => {
    withContracts();
    const onContract = vi.fn();
    wrap(
      <StockPage code="2330" onSelect={vi.fn()} stream={stream()} contract={null} onContract={onContract} />,
    );
    fireEvent.change(await screen.findByLabelText("合約"), { target: { value: "QFF:202608" } });
    expect(onContract).toHaveBeenCalledWith({ prod: "QFF", ym: "202608", mini: true, unit: 100 });
  });

  it("選回現貨 → 上層收到 null", async () => {
    withContracts();
    const onContract = vi.fn();
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream()}
        contract={{ prod: "CDF", ym: "202609", mini: false, unit: 2000 }}
        onContract={onContract}
      />,
    );
    const select = await screen.findByLabelText("合約");
    expect((select as HTMLSelectElement).value).toBe("CDF:202609"); // 受控於 contract prop
    fireEvent.change(select, { target: { value: "" } });
    expect(onContract).toHaveBeenCalledWith(null);
  });

  // 期現價差列的兩條腿是「現貨主圖 vs 期貨」;主圖已經是期貨時它比的是自己,
  // 留著會顯示一個恆為 0 或與畫面無關的價差(D15 前端側)。
  it("期貨態不顯示期現價差列", async () => {
    withContracts();
    const s = stream({ stkfut: { prod: "CDF", p: 2_398_000, basis: 18_000 } });
    // 兩次獨立 render(不用 rerender:`wrap` 的 QueryClientProvider 會被 rerender 換掉)
    const { unmount } = wrap(<StockPage code="2330" onSelect={vi.fn()} stream={s} />);
    await waitFor(() => expect(screen.getByText(/價差/)).toBeTruthy());
    unmount();
    withContracts();
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={s}
        contract={{ prod: "CDF", ym: "202609", mini: false, unit: 2000 }}
        onContract={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByLabelText("合約")).toBeTruthy());
    expect(screen.queryByText(/價差/)).toBeNull();
  });

  // contract 有沒有真的傳到圖表:忘了傳照樣全綠,而畫面會掛一張現貨 K 線在期貨合約上
  it("contract 傳進 StockChart(期貨態 K 線模式鈕停用)", async () => {
    withContracts();
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream()}
        contract={{ prod: "CDF", ym: "202609", mini: false, unit: 2000 }}
        onContract={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("stock-lower-row")).toBeTruthy());
    expect(screen.getByRole("radio", { name: "日K" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("radio", { name: "江波圖" }).hasAttribute("disabled")).toBe(false);
  });
});

// 🟢 試撮/緩撮標示(SC-2)。`accum.trial` 來自 snapshot 種子 + 主圖 watchlist_quote 補寫;
// 期貨鍵的試撮窗是空的(後端恆 False),合約態刻意不標 —— 標了就是憑空編一個狀態。
describe("StockPage 緩撮標示(SC-2)", () => {
  const CONTRACT: StkfutSelection = { prod: "CDF", ym: "202609", mini: false, unit: 2000 };

  function trialStream(trial: boolean): StockStreamState {
    return stream({ accum: { ...ACCUM, trial } });
  }

  it("accum.trial=true + 現貨態 → h2 內代號右側出現「(緩)」", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={trialStream(true)} contract={null} />);
    const badge = screen.getByTestId("page-trial");
    expect(badge.textContent).toBe("(緩)");
    // 落點是 header 的 h2(與名稱 / 代號同一條 baseline),不是漂到報價塊旁邊
    expect(badge.closest("h2")).toBeTruthy();
    const cls = badge.getAttribute("class") ?? "";
    expect(cls).toContain("amber");
    expect(cls).not.toContain("bull");
    expect(cls).not.toContain("bear");
  });

  it("accum.trial=false → 不出現", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={trialStream(false)} contract={null} />);
    expect(screen.queryByTestId("page-trial")).toBeNull();
    expect(screen.queryByText("(緩)")).toBeNull();
  });

  it("期貨合約態 → 即使 trial=true 也不標(合約無試撮窗)", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={trialStream(true)}
        contract={CONTRACT}
        onContract={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("page-trial")).toBeNull();
  });

  it("期貨合約態 + trial=false → 不標(四格的第四格)", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={trialStream(false)}
        contract={CONTRACT}
        onContract={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("page-trial")).toBeNull();
  });

  // 🔴 code review IC-4:窗內的 payload 對 no_data 檔照算 trial=true,而側欄那一列
  // (`q?.trial && !q?.no_data`)不標 —— header 標的話兩個視圖對同一狀態給相反答案,
  // 而且是對一檔**沒有任何報價**的標的講撮合狀態。口徑統一到側欄那一邊。
  it("no_data 檔不標(IC-4:與側欄同口徑)", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream({ accum: { ...ACCUM, trial: true, noData: true } })}
        contract={null}
      />,
    );
    expect(screen.queryByTestId("page-trial")).toBeNull();
    expect(screen.queryByText("(緩)")).toBeNull();
  });
});

// batch3 R3 SC-3:header 的倉位段。**逐 kind / 逐契約各一段**(不聚合)——
// 右欄閃電梯的部位列就在旁邊,一對一才能並排核對數字。
describe("StockPage header 倉位(SC-3)", () => {
  const LAST = 2_380_000; // ACCUM.last.p(毫元)
  const AVG = 2350;

  function pos(over: Partial<CapitalPosition> = {}): CapitalPosition {
    return {
      market: "sec",
      stock_no: "2330",
      qty: 3,
      name: "台積電",
      avg_price: AVG,
      kind: "cash",
      pnl_base: null,
      pnl_base_price: null,
      pnl_cost: null,
      code: "2330",
      ...over,
    };
  }

  async function segments(): Promise<HTMLElement[]> {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} contract={null} />);
    const bar = await screen.findByTestId("page-position");
    return [...bar.children] as HTMLElement[];
  }

  it("現股段 = 交易別 + 張數 + 均價 + 含費稅損益(與 positionEcon 同折數)", async () => {
    positions = [pos()];
    const segs = await segments();
    const econ = positionEcon(3, AVG, LAST, FEE_DISCOUNT_DEFAULT, "cash");
    const pct = ((econ.pnl ?? 0) / (AVG * 3 * 1000)) * 100;
    expect(segs).toHaveLength(1);
    expect(segs[0]?.textContent).toBe(`現股 3張 · 均價 2350 · 損益 ${pnlText(econ.pnl)} (${fmtPct(pct)})`);
    expect(segs[0]?.className).toContain(econ.pnl !== null && econ.pnl > 0 ? "text-bull" : "text-bear");
  });

  // 現貨態也要看得到個股期倉:右欄梯一次只顯示一個合約,header 不列全就看不到
  // 「我這檔還有期倉」。期貨用群益名目損益(pnl_base),不套現股稅費口徑。
  it("個股期段逐契約列出(含合約碼),與現股段並存", async () => {
    positions = [pos(), pos({ market: "fut", stock_no: "CDFI6", qty: 2, avg_price: 2360, pnl_base: 500 })];
    const segs = await segments();
    expect(segs).toHaveLength(2);
    expect(segs[1]?.textContent).toBe("期 CDFI6 多 2口 · 均價 2360 · 損益 +500");
    expect(segs[1]?.className).toContain("text-bull");
  });

  it("均價缺 → 均價與損益皆破折號、不印百分比(張數照顯示)", async () => {
    positions = [pos({ avg_price: null })];
    const segs = await segments();
    expect(segs[0]?.textContent).toBe("現股 3張 · 均價 — · 損益 —");
    expect(segs[0]?.className).toContain("text-ink-dim");
  });

  it("折數改成 3 折 → 損益跟著換(SC-5 元件級)", async () => {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, "3");
    positions = [pos()];
    const segs = await segments();
    const at3 = positionEcon(3, AVG, LAST, 3, "cash");
    const at18 = positionEcon(3, AVG, LAST, FEE_DISCOUNT_DEFAULT, "cash");
    expect(segs[0]?.textContent).toContain(`損益 ${pnlText(at3.pnl)}`);
    expect(segs[0]?.textContent).not.toContain(`損益 ${pnlText(at18.pnl)}`);
  });

  // 🔴 code review C-1(P1):個股期態下主圖 accum 是**合約簿**的價 —— 拿它算現股損益
  // 就是「用期貨價算的現股部位」,一個看起來很正常的錯數字。現股段一律吃側欄現貨報價。
  it("期貨態現股段吃側欄現貨價、不用合約簿價(C-1)", async () => {
    const SEC_LAST = 1_190_000; // 側欄現貨報價(毫元)
    const FUT_LAST = 1_150_000; // 主圖 = 合約簿成交價(毫元)
    const AVG_SEC = 1180;
    const CONTRACT: StkfutSelection = { prod: "CDF", ym: "202609", mini: false, unit: 2000 };
    positions = [pos({ avg_price: AVG_SEC })];
    const both = stream({
      accum: { ...ACCUM, last: { p: FUT_LAST, t: "09:00:01.000", cum_vol: 1 } } as StockAccum,
      watchlist: {
        "2330": {
          p: SEC_LAST,
          chg_pct: null,
          vol: null,
          ref: null,
          upper: null,
          lower: null,
          no_data: false,
          trial: false,
        },
      },
    });
    const pnlAt = (lastMilli: number) =>
      pnlText(positionEcon(3, AVG_SEC, lastMilli, FEE_DISCOUNT_DEFAULT, "cash").pnl);
    async function secText(contract: StkfutSelection | null): Promise<string> {
      wrap(
        <StockPage
          code="2330"
          onSelect={vi.fn()}
          stream={both}
          contract={contract}
          onContract={vi.fn()}
        />,
      );
      const text = (await screen.findByTestId("page-position")).textContent ?? "";
      cleanup(); // 兩次 render 在同一個 it 內,不清會撞 getMultipleElementsFound
      return text;
    }
    // 現貨態:accum 本來就是現貨簿 → 期望值取主圖那口價(現況已對,不該因修改而變)
    expect(await secText(null)).toContain(`損益 ${pnlAt(FUT_LAST)}`);
    // 期貨態:accum 已換成合約簿 → 現股段必須改吃側欄現貨價
    expect(await secText(CONTRACT)).toContain(`損益 ${pnlAt(SEC_LAST)}`);
  });

  // review C-2:等 `page-quote` 是 props 驅動的節點,對「倉位查詢還沒回來」與「真的沒倉」
  // 給同一個答案 = vacuous。改成先以有倉的檔自檢節點真的長得出來(同一份已落地的 positions),
  // 再切到沒倉的檔斷言消失 —— 兩次斷言吃同一次查詢結果,無倉是資料判定不是時序。
  it("無倉 → 整段不渲染(零佔位)", async () => {
    positions = [pos()]; // 只有 2330 有倉
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const page = (code: string) => (
      <QueryClientProvider client={client}>
        <StockPage code={code} onSelect={vi.fn()} stream={stream()} contract={null} />
      </QueryClientProvider>
    );
    const { rerender } = render(page("2330"));
    await screen.findByTestId("page-position"); // 自檢:有倉時真的渲染
    rerender(page("2317")); // 切到沒倉的檔(查詢已落地,同一份 data)
    expect(screen.queryByTestId("page-position")).toBeNull();
  });
});

// 🔴 SC-2(D3'):資料日 ≠ 後端今日(假日 / 盤前開站)時,rail 標題帶日期。
// 接線正向鎖:`useSignalFeed` 的兩欄要真的走到 rail —— 只測 rail 自己會在
// StockPage 忘了傳 props 時照樣綠。
describe("StockPage 訊號欄標題資料日(SC-2)", () => {
  it("signals/today 回 trade_date ≠ today → rail 標題「08-20 訊號」", async () => {
    const base = globalThis.fetch as ReturnType<typeof vi.fn>;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/stock/signals/today")) {
          return new Response(
            JSON.stringify({ signals: [], trade_date: "2026-08-20", today: "2026-08-21" }),
          );
        }
        return base(url);
      }),
    );
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    await waitFor(() =>
      expect(screen.getByTestId("signal-rail").getAttribute("aria-label")).toBe("08-20 訊號"),
    );
    expect(screen.getByRole("heading", { name: "08-20 訊號" })).toBeTruthy();
  });
});

// 🔵 N121 的前提鎖:`StockChart` 的 `spotMode`(進合約前的現貨模式)在 prod 之所以沒有
// 讀者,是因為主圖被 `{accum ? …}` 關著 —— 換合約時 `useStockStream` 先 `setAccum(null)`,
// StockChart 因此**卸載重掛**,待還原偏好歸零(還原實際由 localStorage 兌現)。
// 這條測試把那個前提釘住:哪天圖表脫離 accum gate(常駐掛載),這裡會紅,
// 提醒去看 StockChart 的 spotMode 是不是該重新驗 A6 或刪掉。
describe("StockPage 主圖 accum gate(N121 前提)", () => {
  it("accum === null(切標的中)→ 圖表整棵不掛,模式列也不在", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ accum: null })} />);
    expect(screen.getByText("載入中…")).toBeTruthy();
    expect(screen.queryByRole("radiogroup", { name: "圖表模式" })).toBeNull();
    expect(screen.queryByTestId("stock-lower-row")).toBeNull();
  });
});
