/** @vitest-environment jsdom */
/** 類股強弱區塊(market-overview R4 SC-3;design §9.1)。
 *
 *  三層清單的分岔點是「這個產業有沒有 subs」:有 subs 的產業列點擊 = 展開子產業,
 *  沒有的直接鑽成員 —— 少了後者,單層產業(subs 空)會變成點了沒反應的死列。
 *
 *  成員層是 lazy:未鑽取時**一次 members 請求都不該發**。這條與「展開產業」分開驗,
 *  因為兩者在畫面上都是「列展開了」,但一個是零網路、一個是每次點都打一發。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SectorSection } from "@/components/index/SectorSection";
import { SECTOR_OPEN_KEY } from "@/lib/constants";
import type { SectorMembers, SectorRotation, SectorState } from "@/lib/sector-model";

const ROTATION: SectorRotation = {
  industries: [
    {
      name: "半導體",
      members: 120,
      avg_change_rate: 2.5,
      vol_ratio: 1.8,
      subs: [
        { name: "IC設計", members: 40, avg_change_rate: 3.25, vol_ratio: 2.1 },
        { name: "封測", members: 20, avg_change_rate: -1.1, vol_ratio: null },
      ],
    },
    // subs 空 = 單層產業:點列直接鑽成員(沒有可展開的下一層)
    { name: "航運", members: 30, avg_change_rate: -0.75, vol_ratio: 0.9, subs: [] },
  ],
};

const MEMBERS: SectorMembers = {
  industry: "半導體",
  sub_industry: "IC設計",
  members: [
    {
      stock_id: "2454",
      name: "聯發科",
      change_rate: 4.12,
      vol_ratio: 2.4,
      total_amount: 3_640_000_000,
    },
    { stock_id: "3035", name: "智原", change_rate: null, vol_ratio: null, total_amount: null },
  ],
};

function mkState(over: Partial<SectorState> = {}): SectorState {
  return {
    enabled: true,
    trade_date: "2026-08-06",
    as_of: "10:31:00",
    stale: false,
    rotation: ROTATION,
    ...over,
  };
}

let fetchSpy: ReturnType<typeof vi.fn>;
let urls: string[] = [];

function stubFetch(state: SectorState, members: SectorMembers = MEMBERS): void {
  urls = [];
  fetchSpy = vi.fn(async (url: string) => {
    const u = String(url);
    urls.push(u);
    if (u.startsWith("/api/market/sector/members")) {
      return new Response(JSON.stringify(members));
    }
    return new Response(JSON.stringify(state));
  });
  vi.stubGlobal("fetch", fetchSpy);
}

function memberUrls(): string[] {
  return urls.filter((u) => u.startsWith("/api/market/sector/members")).map(decodeURIComponent);
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
      <SectorSection onOpenStock={onOpenStock} active={active} />
    </QueryClientProvider>,
  );
}

/** 直接以「已展開 + 已鑽取單層產業(航運)」開場,等成員層落定後回傳。 */
async function drillMembers(members: SectorMembers): Promise<void> {
  window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
  stubFetch(mkState(), members);
  renderSection();
  await screen.findByTestId("sector-body");
  fireEvent.click(await screen.findByTestId("sector-row-btn-航運"));
}

/** 直接以「已展開」開場(收合閘門另有專測),等資料落地後回傳。 */
async function openWith(
  state: SectorState = mkState(),
  onOpenStock?: (code: string) => void,
): Promise<void> {
  window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
  stubFetch(state);
  renderSection(onOpenStock);
  await screen.findByTestId("sector-body");
  await waitFor(() => expect(fetchSpy.mock.calls.length).toBeGreaterThan(0));
}

function header(): HTMLElement {
  return screen.getByRole("button", { name: /類股強弱/ });
}

beforeEach(() => {
  window.localStorage.clear();
  stubFetch(mkState());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("SectorSection 收合閘門", () => {
  it("預設收合:body 不 mount、零 fetch", async () => {
    renderSection();
    await waitFor(() => expect(header().getAttribute("aria-expanded")).toBe("false"));
    expect(screen.queryByTestId("sector-body")).toBeNull();
    expect(fetchSpy.mock.calls.length).toBe(0);
  });

  it("展開寫入 localStorage,重新 mount 仍展開", async () => {
    renderSection();
    fireEvent.click(header());
    await screen.findByTestId("sector-body");
    expect(window.localStorage.getItem(SECTOR_OPEN_KEY)).toBe("1");
    expect(header().getAttribute("aria-expanded")).toBe("true");

    cleanup();
    renderSection();
    expect(await screen.findByTestId("sector-body")).toBeTruthy();
  });

  it("收合把 body unmount 並寫回 0(query 隨之消失)", async () => {
    await openWith();
    expect(screen.queryByTestId("sector-list")).toBeTruthy();

    fireEvent.click(header());

    expect(screen.queryByTestId("sector-body")).toBeNull();
    expect(screen.queryByTestId("sector-list")).toBeNull();
    expect(window.localStorage.getItem(SECTOR_OPEN_KEY)).toBe("0");
    expect(header().getAttribute("aria-expanded")).toBe("false");
  });
});

describe("SectorSection 產業列", () => {
  it("每列印名稱 / 成員數 / 著色漲跌 / 量比,預設全部收合", async () => {
    await openWith();
    const row = screen.getByTestId("sector-row-btn-半導體");
    expect(row.textContent).toContain("半導體");
    expect(row.textContent).toContain("(120)");
    expect(row.getAttribute("aria-expanded")).toBe("false");

    const up = screen.getByTestId("sector-change-半導體");
    expect(up.textContent).toBe("+2.50%");
    expect(up.getAttribute("class")).toContain("text-bull");
    expect(screen.getByTestId("sector-ratio-半導體").textContent).toBe("1.80");

    const down = screen.getByTestId("sector-change-航運");
    expect(down.textContent).toBe("-0.75%");
    expect(down.getAttribute("class")).toContain("text-bear");

    // 子產業未展開 → 不在 DOM
    expect(screen.queryByTestId("sector-sub-btn-半導體-IC設計")).toBeNull();
  });

  it("產業排序照後端給的順序(前端不重排)", async () => {
    await openWith();
    expect(
      screen
        .getAllByTestId(/^sector-row-btn-/)
        .map((el) => el.getAttribute("data-testid")!.replace("sector-row-btn-", "")),
    ).toEqual(["半導體", "航運"]);
  });

  it("點有子產業的產業列 → 展開 subs(同欄位),再點收合", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));

    expect(screen.getByTestId("sector-row-btn-半導體").getAttribute("aria-expanded")).toBe("true");
    const sub = screen.getByTestId("sector-sub-btn-半導體-IC設計");
    expect(sub.textContent).toContain("IC設計");
    expect(sub.textContent).toContain("(40)");
    expect(screen.getByTestId("sector-change-半導體-IC設計").textContent).toBe("+3.25%");
    expect(screen.getByTestId("sector-ratio-半導體-IC設計").textContent).toBe("2.10");
    // vol_ratio 缺值 → 破折號(不是 0.00)
    expect(screen.getByTestId("sector-ratio-半導體-封測").textContent).toBe("—");
    expect(screen.getByTestId("sector-change-半導體-封測").getAttribute("class")).toContain(
      "text-bear",
    );

    // 展開子產業本身**不觸發**成員請求(lazy)
    expect(memberUrls()).toEqual([]);

    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));
    expect(screen.queryByTestId("sector-sub-btn-半導體-IC設計")).toBeNull();
  });
});

describe("SectorSection 成員層(lazy drill-down)", () => {
  it("點子產業 → 帶 industry + sub 取成員,表頭四欄", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));
    expect(memberUrls()).toEqual([]);

    fireEvent.click(screen.getByTestId("sector-sub-btn-半導體-IC設計"));
    await screen.findByTestId("sector-members-table");

    expect(memberUrls()).toEqual(["/api/market/sector/members?industry=半導體&sub=IC設計"]);
    expect(screen.getAllByRole("columnheader").map((el) => el.textContent)).toEqual([
      "名稱",
      "漲跌",
      "量比",
      "成交額",
    ]);
    expect(screen.getByTestId("sector-member-2454").textContent).toContain("聯發科");
    expect(screen.getByTestId("sector-member-change-2454").textContent).toBe("+4.12%");
    expect(screen.getByTestId("sector-member-ratio-2454").textContent).toBe("2.40");
    expect(screen.getByTestId("sector-member-amount-2454").textContent).toBe("36.4");
    // 缺值一律破折號
    expect(screen.getByTestId("sector-member-change-3035").textContent).toBe("—");
    expect(screen.getByTestId("sector-member-ratio-3035").textContent).toBe("—");
    expect(screen.getByTestId("sector-member-amount-3035").textContent).toBe("—");
  });

  it("點無子產業的產業列 → 直接取成員,URL 不帶 sub", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await screen.findByTestId("sector-members-table");

    expect(memberUrls()).toEqual(["/api/market/sector/members?industry=航運"]);
  });

  it("成員列點擊 → onOpenStock(SC-3 廣度→深度銜接)", async () => {
    const onOpenStock = vi.fn();
    await openWith(mkState(), onOpenStock);
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await screen.findByTestId("sector-members-table");

    fireEvent.click(screen.getByTestId("sector-member-2454"));
    expect(onOpenStock.mock.calls).toEqual([["2454"]]);
  });

  // 成員鑽取是 404(查無 industry / sub)/ 500(後端全 universe 掃描炸掉)都到得了的路。
  // 少了這條分流,失敗會永遠停在「載入中…」—— 看起來像還在等,其實已經放棄了。
  it("成員請求 500 → 成員載入失敗(清單其餘部分照常)", async () => {
    window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
    urls = [];
    fetchSpy = vi.fn(async (url: string) => {
      const u = String(url);
      urls.push(u);
      if (u.startsWith("/api/market/sector/members")) return new Response("boom", { status: 500 });
      return new Response(JSON.stringify(mkState()));
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderSection();
    await screen.findByTestId("sector-body");
    fireEvent.click(await screen.findByTestId("sector-row-btn-航運"));

    // MembersPanel 自帶 `retry: 1` → 要等一次重試(exponential backoff 初次 1s)
    await waitFor(
      () => expect(screen.getByTestId("sector-members-msg").textContent).toBe("成員載入失敗"),
      { timeout: 5000 },
    );
    expect(screen.queryByTestId("sector-members-table")).toBeNull();
    // 失敗只吃掉成員層:輪動清單本身是另一支 query,不該一起消失
    expect(screen.queryByTestId("sector-list")).toBeTruthy();
  });

  // 「該群組今天一檔成員都沒有」與「還在抓」是兩句話。少了這條,空成員會渲染成一張
  // 只有表頭的空表格 —— 看起來像資料掉了。
  it("成員回空陣列 → 無成員資料(不是空表格)", async () => {
    await drillMembers({ ...MEMBERS, members: [] });
    await waitFor(() =>
      expect(screen.getByTestId("sector-members-msg").textContent).toBe("無成員資料"),
    );
    expect(screen.queryByTestId("sector-members-table")).toBeNull();
  });

  it("再點同一個鑽取目標 → 收起成員層", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await screen.findByTestId("sector-members-table");

    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    expect(screen.queryByTestId("sector-members-table")).toBeNull();
  });
});

describe("SectorSection 降級", () => {
  it("rotation null → 類股資料未就緒(不是「載入中」也不是空清單)", async () => {
    await openWith(mkState({ rotation: null }));
    expect(screen.getByTestId("sector-msg").textContent).toBe("類股資料未就緒");
    expect(screen.queryByTestId("sector-list")).toBeNull();
  });

  // `rotation: null` 與 `industries: []` 不同義:前者「產業鏈快取還沒好,等一下就有」,
  // 後者「今天所有產業都沒成員」。共用一句文案會把前者說成後者(或反過來),而使用者
  // 對這兩句的反應完全不同(等 vs 去查為什麼)。
  it("industries 空陣列 → 暫無類股資料(與 rotation null 分流)", async () => {
    await openWith(mkState({ rotation: { industries: [] } }));
    expect(screen.getByTestId("sector-msg").textContent).toBe("暫無類股資料");
    expect(screen.queryByTestId("sector-list")).toBeNull();
  });

  it("enabled=false → FinMind 未設定", async () => {
    await openWith(mkState({ enabled: false, as_of: null, rotation: null, stale: true }));
    expect(screen.getByTestId("sector-msg").textContent).toBe("FinMind 未設定");
  });

  it("stale=true → 延遲標記,清單照常渲染", async () => {
    await openWith(mkState({ stale: true }));
    expect(screen.getByTestId("sector-stale").textContent).toBe("資料延遲");
    expect(screen.queryByTestId("sector-list")).toBeTruthy();
    expect(screen.queryByTestId("sector-msg")).toBeNull();
  });

  it("stale=false → 無標記", async () => {
    await openWith();
    expect(screen.queryByTestId("sector-stale")).toBeNull();
  });

  // TQ v5 的 `isError` 對 **refetch** 失敗同樣為 true(`LimitListSection` 同款)。單看它
  // 分流會讓「已經有一整份輪動、只是這一輪 10 秒輪詢沒抓到」整塊消失換成「載入失敗」
  // —— 盤中最需要看的那份資料因為一次網路抖動就被清掉。有 data 就保清單,失敗改用膠囊說。
  it("已有資料後 refetch 失敗 → 清單保留,改以「更新失敗」膠囊示警", async () => {
    await openWith();
    expect(screen.getAllByTestId(/^sector-row-btn-/).length).toBe(2);

    fetchSpy.mockImplementation(async () => new Response("boom", { status: 500 }));
    await act(async () => {
      await client.refetchQueries({ queryKey: ["sector-state"] });
    });
    // TQ 的 observer 通知走 notifyManager(macrotask 排程),act 只吃得到 microtask
    await waitFor(() => expect(screen.getByTestId("sector-refetch-error")).toBeTruthy());

    expect(screen.getByTestId("sector-refetch-error").textContent).toContain("更新失敗");
    expect(screen.queryByTestId("sector-list")).toBeTruthy();
    expect(screen.getAllByTestId(/^sector-row-btn-/).length).toBe(2);
    expect(screen.queryByTestId("sector-msg")).toBeNull();
  });

  it("HTTP 失敗 → 載入失敗(不可永遠停在「載入中…」)", async () => {
    window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
    fetchSpy = vi.fn(async () => new Response("boom", { status: 500 }));
    vi.stubGlobal("fetch", fetchSpy);
    renderSection();
    await screen.findByTestId("sector-body");
    await waitFor(() => expect(screen.getByTestId("sector-msg").textContent).toBe("載入失敗"), {
      timeout: 5000,
    });
  });
});

// (FE-7 拍板 2026-08-12)產業列每 10 秒依後端 avg 重排,展開/鑽取中的列會在游標下
// 位移 —— 誤點成員 = setStockCode + set_main,代價不只看錯。拍板解:任何展開/鑽取
// 期間**凍結排序**(數字照更新、位置不動)+ 顯示「排序已凍結」標籤,全收合才恢復。
describe("SectorSection 排序凍結(FE-7)", () => {
  /** 後端下一輪把航運排到最前(avg 反轉)—— 凍結時位置不得跟著跳。 */
  const REORDERED: SectorRotation = {
    industries: [
      { name: "航運", members: 30, avg_change_rate: 5.0, vol_ratio: 2.2, subs: [] },
      {
        name: "半導體",
        members: 120,
        avg_change_rate: 2.5,
        vol_ratio: 1.8,
        subs: [
          { name: "IC設計", members: 40, avg_change_rate: 3.25, vol_ratio: 2.1 },
          { name: "封測", members: 20, avg_change_rate: -1.1, vol_ratio: null },
        ],
      },
    ],
  };

  function rowOrder(): string[] {
    return screen
      .getAllByTestId(/^sector-row-btn-/)
      .map((el) => el.getAttribute("data-testid")!.replace("sector-row-btn-", ""));
  }

  /** 下一輪 sector-state 改回傳重排後的清單,並主動觸發 refetch。 */
  async function refetchReordered(): Promise<void> {
    fetchSpy.mockImplementation(
      async () => new Response(JSON.stringify(mkState({ rotation: REORDERED }))),
    );
    await act(async () => {
      await client.refetchQueries({ queryKey: ["sector-state"] });
    });
    // 數字要照常更新(凍的是位置不是資料)—— 也是等 TQ macrotask 通知落地的錨點
    await waitFor(() => expect(screen.getByTestId("sector-change-航運").textContent).toBe("+5.00%"));
  }

  it("展開子產業層中輪詢順序改變 → 列位置凍結、數字照更新、顯示凍結標籤", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));
    expect(screen.getByTestId("sector-frozen").textContent).toBe("排序已凍結");

    await refetchReordered();
    expect(rowOrder()).toEqual(["半導體", "航運"]);
  });

  it("全收合 → 恢復後端最新排序、凍結標籤消失", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));
    await refetchReordered();

    fireEvent.click(screen.getByTestId("sector-row-btn-半導體"));
    expect(screen.queryByTestId("sector-frozen")).toBeNull();
    expect(rowOrder()).toEqual(["航運", "半導體"]);
  });

  it("鑽取成員表中(無子產業直鑽)同樣凍結 + 標籤", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await screen.findByTestId("sector-members-table");
    expect(screen.getByTestId("sector-frozen").textContent).toBe("排序已凍結");

    await refetchReordered();
    expect(rowOrder()).toEqual(["半導體", "航運"]);
  });

  it("未展開任何列 → 不凍結(照後端新順序重排、無標籤)", async () => {
    await openWith();
    expect(screen.queryByTestId("sector-frozen")).toBeNull();
    await refetchReordered();
    expect(rowOrder()).toEqual(["航運", "半導體"]);
  });

  // 成員表是誤點代價最高的一層(點下去就換主圖)—— 鑽取中成員列同樣不得位移。
  it("成員表輪詢順序改變 → 成員列位置凍結、數字照更新", async () => {
    await openWith();
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await screen.findByTestId("sector-members-table");

    const reordered: SectorMembers = {
      ...MEMBERS,
      members: [
        { stock_id: "3035", name: "智原", change_rate: 9.9, vol_ratio: 3.1, total_amount: 1e9 },
        MEMBERS.members[0]!,
      ],
    };
    fetchSpy.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.startsWith("/api/market/sector/members")) {
        return new Response(JSON.stringify(reordered));
      }
      return new Response(JSON.stringify(mkState()));
    });
    await act(async () => {
      await client.refetchQueries({ queryKey: ["sector-members"] });
    });
    await waitFor(() =>
      expect(screen.getByTestId("sector-member-change-3035").textContent).toBe("+9.90%"),
    );
    expect(
      screen
        .getAllByTestId(/^sector-member-\d+$/)
        .map((el) => el.getAttribute("data-testid")!.replace("sector-member-", "")),
    ).toEqual(["2454", "3035"]);
  });
});

// 展開狀態存在 localStorage、tab 又是 `hidden` 保留而非 unmount(App 慣例)→
// 「展開著被切走」是常態。這一組鎖的是「`active` 有真的接到 query 的 refetchInterval 上」。
describe("SectorSection 背景輪詢 gate", () => {
  function openWithTimers(active?: boolean): void {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
    stubFetch(mkState());
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

  // (review round-2 FE-3)成員表原本沒有 `refetchInterval`,全 repo 也沒人 invalidate
  // `["sector-members"]` → 鑽開的成員表**從打開那一刻起就凍結**,而它正上方的產業列
  // 每 10 秒在更新。畫面上兩層數字並排,一層是即時的、一層是幾分鐘前的,沒有任何
  // 標示能區分 —— 使用者只會以為這幾檔今天很穩。
  /** 展開 + 鑽取單層產業(航運)的成員表,全程 fake timers。 */
  async function drillWithTimers(active?: boolean): Promise<void> {
    openWithTimers(active);
    await vi.advanceTimersByTimeAsync(0);
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await vi.advanceTimersByTimeAsync(0);
  }

  it("成員表跟著產業列一起輪詢(盤中 + active)", async () => {
    await drillWithTimers(true);
    expect(memberUrls().length).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(memberUrls().length).toBe(2);
  });

  it("active=false → 成員表也不背景輪詢(鑽取當下仍抓一次)", async () => {
    await drillWithTimers(false);
    expect(memberUrls().length).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(memberUrls().length).toBe(1);
  });

  it("盤外(週六)→ 成員表不輪詢", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 8, 10, 0)); // 週六
    window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
    stubFetch(mkState());
    renderSection(undefined, true);
    await vi.advanceTimersByTimeAsync(0);
    fireEvent.click(screen.getByTestId("sector-row-btn-航運"));
    await vi.advanceTimersByTimeAsync(0);
    expect(memberUrls().length).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(memberUrls().length).toBe(1);
  });

  it("盤外(週六)→ 展開且 active 也不輪詢", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 8, 10, 0)); // 週六
    window.localStorage.setItem(SECTOR_OPEN_KEY, "1");
    stubFetch(mkState());
    renderSection(undefined, true);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchSpy.mock.calls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchSpy.mock.calls.length).toBe(1);
  });
});
