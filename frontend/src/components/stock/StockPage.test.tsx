/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPage } from "@/components/stock/StockPage";
import type { StockStreamState } from "@/hooks/useStockStream";
import { emitSignal } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import type { StockAccum } from "@/lib/stock-accum";
import { wrap } from "@/test-utils";

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
      if (String(url).includes("/api/stock/signals/rules")) {
        return new Response(JSON.stringify({ rules: [] }));
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
    await waitFor(() => expect(screen.getByText("自選已達 30 檔上限")).toBeTruthy());
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
    expect(screen.getByTestId("signal-rules-dialog").className).toContain("hidden");
    fireEvent.click(screen.getByRole("button", { name: "管理訊號規則" }));
    expect(screen.getByTestId("signal-rules-dialog").className).toContain("flex");
    expect(within(screen.getByTestId("signal-rules-dialog")).getByText("我的爆量")).toBeTruthy();
  });
});
