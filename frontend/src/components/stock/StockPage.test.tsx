/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPage } from "@/components/stock/StockPage";
import type { StockStreamState } from "@/hooks/useStockStream";
import type { StockAccum } from "@/lib/stock-accum";

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

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/watchlist")) {
        return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330"] }] }));
      }
      if (String(url).includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: [] }));
      }
      if (String(url).includes("/api/stock/overlay")) {
        return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("StockPage", () => {
  it("未選檔時顯示提示;自選側欄仍渲染", async () => {
    wrap(<StockPage code={null} onSelect={vi.fn()} stream={stream({ accum: null })} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy()); // 側欄
    expect(screen.getByText(/從自選清單選擇/)).toBeTruthy();
  });

  it("TC4 斷線顯示告警列(文案不變)", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream({ status: { tc4: "down", backfilling: null } })}
      />,
    );
    expect(screen.getByText(/達錢 4 連線中斷,恢復後自動回補/)).toBeTruthy();
  });

  it("伺服器斷線顯示重連告警列(文案不變)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ wsStatus: "closed" })} />);
    expect(screen.getByText(/伺服器連線中斷,重連中…/)).toBeTruthy();
  });

  it("選檔後中間主區 = 圖表切換 + 五檔 + 明細(SC-6/SC-7)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.getByRole("button", { name: "江波圖" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "1分K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "5分K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "日K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "買1 2375" })).toBeTruthy(); // 五檔(W-16:aria-label 格式是定位鍵)
    expect(screen.getByText("時間")).toBeTruthy(); // 明細表頭
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
    await waitFor(() => expect(screen.getByText("自選已達 30 檔上限")).toBeTruthy());
  });
});
