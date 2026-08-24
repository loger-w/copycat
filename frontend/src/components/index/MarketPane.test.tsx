/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketPane, type PaneFutState, type PaneStores } from "@/components/index/MarketPane";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";
import type { MarketKey } from "@/lib/timeframe";

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: { "0901": 43_000_000, "0930": 42_039_920 },
    ...over,
  };
}

const OTC = series({
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  minutes: { "1017": 359_800 },
});
const FUTURES: Record<string, PaneFutState> = { TXF: { p: 42_142_000, ref: 42_000_000 } };
const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: false, fills: true };

const LEFT_STORES: PaneStores = {
  key: MARKET_KEY_STORE,
  mode: MARKET_MODE_STORE,
  fut: MARKET_FUT_STORE,
  overlay: INDEX_OVERLAY_STORE,
};
const RIGHT_STORES: PaneStores = {
  key: MARKET2_KEY_STORE,
  mode: MARKET2_MODE_STORE,
  fut: MARKET2_FUT_STORE,
};

function bars(n = 3) {
  return Array.from({ length: n }, (_, i) => ({
    t: `2026-07-2${7 + i}`,
    o: 100,
    h: 110,
    l: 90,
    c: 105,
    v: 10,
  }));
}

let lastUrls: string[] = [];

function stubFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      lastUrls.push(String(url));
      return new Response(JSON.stringify(body));
    }),
  );
}

const DK_BODY = {
  key: "TWSE",
  tf: "D",
  bars: bars(),
  meta: {
    source: "tc4_dk",
    coverage_from: "2026-07-27",
    coverage_to: "2026-07-29",
    partial_last: false,
    volume: true,
    refusal: null,
    synth_since: null,
  },
};

beforeEach(() => {
  window.localStorage.clear();
  lastUrls = [];
  stubFetch(DK_BODY);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

interface RenderOver {
  paneId?: "left" | "right";
  stores?: PaneStores;
  defaultKey?: MarketKey;
  futures?: Record<string, PaneFutState> | null;
  onToggle?: (key: keyof ChartToggles, value: boolean) => void;
  /** 兩條指數流。預設 = 既有 fixture;`null` 是「流還沒回來」的合法值,故用
   *  `undefined` 才代表「不覆寫」(不可寫成 `over.twse ?? series()`)。 */
  twse?: IndexSeries | null;
  otc?: IndexSeries | null;
}

function renderPane(over: RenderOver = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketPane
        paneId={over.paneId ?? "left"}
        twse={over.twse === undefined ? series() : over.twse}
        otc={over.otc === undefined ? OTC : over.otc}
        futures={over.futures === undefined ? FUTURES : over.futures}
        stores={over.stores ?? LEFT_STORES}
        defaultKey={over.defaultKey ?? "TWSE"}
        toggles={TOGGLES}
        onToggle={over.onToggle ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

/** 真開關(只剩「重疊」)。標的 / 期貨商品 / 週期三組已改 radiogroup → 用 `pill()`。 */
function btn(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

/** a11y 批:三組單選 pill 改 RadioPills(sr-only `<input type=radio>` + 帶原 class 的
 *  `<label>`)。選中態 = `checked`;class / `aria-disabled` 掛在 label(= `parentElement`)。 */
function pill(name: string): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

// 🔴 SC-3:17 顆週期鈕在 ~350px 的 pane(1536 兩欄態)折成 3 行、吃掉 50px 圖高。
// 修法 = pane 自掛 `@container` + 窄容器下把 Btn 的 px-2 收成 px-1、列 gap-1 收成
// gap-0.5(估算 ≈ 561px / 346px = 1.6 行 → 2 行)。
//
// **只能鎖 class 字串**:jsdom 不套 Tailwind CSS,`getComputedStyle` 對 container query
// 一無所知 —— 真正「折幾行」由 SC-3 的真環境量測(getBoundingClientRect().height ≤ 48)
// 把關,這裡防的是「漏寫 / 被 twMerge 吃掉」。
//
// ⚠ 門檻用 **rem 不用 px**:鈕的文字與 padding 全是 rem,rem 門檻讓「塞不塞得下」這個
// 條件對 root font-size 不變(frontend-conventions 的 px 案例反過來 —— 那裡量的是固定
// px 面板寬)。**本專案 root 目前恆 16px(無縮放 media query),26.5rem = 424px /
// 41rem = 656px**;真環境量測(2026-08-21):1536 pane 350 → 降級(右欄 473 亦降級);
// 1920 pane 466 → 不 compact 但週期列仍 2 行(48px)、右欄 627 → 七欄;2560 pane 658、
// 右欄 883 → 九欄。
describe("MarketPane 窄容器週期列(SC-3)", () => {
  it("pane root 自掛 @container(週期列的門檻要量 pane 寬,不是左欄寬)", () => {
    renderPane();
    // 最近的 container 祖先若還是左欄(兩欄態 630–930px),26.5rem 的門檻永不成立
    expect(screen.getByTestId("market-pane-left").className).toContain("@container");
  });

  it("週期鈕:窄容器 px-1,寬容器仍是既有 px-2(W-6:兩個 token 都要在)", () => {
    renderPane();
    // W3:compact class 逐字保留 —— 只是從 `<button>` 搬到包住 radio 的 `<label>`
    const cls = pill("日K").parentElement!.className;
    expect(cls).toContain("@max-[26.5rem]:px-1");
    // twMerge 不會把兩者判成衝突(不同 variant),被吃掉的話寬 pane 的 padding 也變了
    expect(cls).toContain("px-2");
  });

  // TC-8:「重疊」是唯一還是 `<button>` 的那顆,class 與 pill 同源(`pillClass`)——
  // 同源這件事沒有斷言的話,哪天有人把 Btn 的 class 抄成自己一份,窄 pane 下它不縮 padding
  // 而旁邊的週期鈕縮了,折行行為與版面就與 SC-3 的量測脫節。
  it("「重疊」toggle 與週期鈕吃同一份 class(窄容器 px-1 / 寬容器 px-2)", () => {
    renderPane();
    const overlay = btn("重疊");
    expect(overlay.className).toContain("@max-[26.5rem]:px-1");
    expect(overlay.className).toContain("px-2");
  });

  it("週期列容器:窄容器 gap-0.5,寬容器仍是既有 gap-1", () => {
    renderPane();
    // 週期列 = radiogroup 容器本身(label 的父層);容器 class 逐字沿用
    const row = screen.getByRole("radiogroup", { name: "週期" });
    expect(pill("日K").parentElement!.parentElement).toBe(row);
    expect(row.className).toContain("@max-[26.5rem]:gap-0.5");
    expect(row.className).toContain("gap-1");
  });
});

// a11y 批 SC-1' / D2':三列 pill 各自是**單選**,改成三個 radiogroup。
// 標的列拆兩群(標的 / 期貨商品)而不是一群:兩者語意不同,「恰一顆 checked」在合成的
// 單一群裡不成立(台指期 + 大台會同時亮)。「重疊」是真開關,留在週期列 DOM 位置。
describe("MarketPane radiogroup 語意(a11y SC-1')", () => {
  it("標的列 = radiogroup「標的」三顆;期貨商品列僅期貨態出現且各自獨立 name", () => {
    renderPane();
    const keyGroup = within(screen.getByRole("radiogroup", { name: "標的" }));
    const keyRadios = keyGroup.getAllByRole("radio") as HTMLInputElement[];
    expect(keyRadios.map((r) => r.parentElement!.textContent)).toEqual(["加權", "櫃買", "台指期"]);
    expect(keyRadios.filter((r) => r.checked).length).toBe(1);
    expect(screen.queryByRole("radiogroup", { name: "期貨商品" })).toBeNull();

    fireEvent.click(pill("台指期"));
    const futGroup = screen.getByRole("radiogroup", { name: "期貨商品" });
    const futRadios = [...futGroup.querySelectorAll("input")] as HTMLInputElement[];
    expect(futRadios.map((r) => r.parentElement!.textContent)).toEqual(["大台", "小台", "微台"]);
    expect(futRadios.filter((r) => r.checked).length).toBe(1);
    // edge case 2:同頁多組必須各自 `name`,否則原生 radio 互相搶選
    expect(new Set(futRadios.map((r) => r.name)).size).toBe(1);
    expect(futRadios[0]!.name).not.toBe(pill("加權").name);
  });

  // 🔴 A11Y-p2-1:第三顆「台指期」的 value 改前直接是 `futKey` —— 換期貨商品
  // (大台 → 小台)連帶換掉 `key={item.value}`,React 於是把整顆 label + input 卸載重建。
  // 症狀:焦點掉回 body(鍵盤使用者每換一次商品就得從頭 Tab 回來),而畫面完全一樣。
  // value 固定 `"FUT"`,futKey 的映射留在呼叫端。
  it("切換期貨商品時「台指期」radio 不重掛(DOM node 恆等)", () => {
    renderPane();
    fireEvent.click(pill("台指期"));
    const before = pill("台指期");
    expect(before.checked).toBe(true);
    fireEvent.click(pill("小台"));
    expect(pill("台指期")).toBe(before);
    expect(before.checked).toBe(true);
    // 映射仍生效:選的是小台(標的與商品兩群各自恰一顆 checked)
    expect(pill("小台").checked).toBe(true);
    expect(screen.getByText("台指期(小台)")).toBeTruthy();
  });

  it("週期列 = radiogroup「週期」,「重疊」toggle 仍在同一列且保留 aria-pressed", () => {
    renderPane();
    const modeGroup = screen.getByRole("radiogroup", { name: "週期" });
    expect((modeGroup.querySelectorAll("input") as NodeListOf<HTMLInputElement>).length).toBe(17);
    // W2:重疊是真開關 —— 不進 radiogroup 的 radio 集合,但 DOM 位置不變(留在週期列內)
    const overlay = btn("重疊");
    expect(overlay.getAttribute("aria-pressed")).toBe("false");
    expect(modeGroup.contains(overlay)).toBe(true);
  });
});

describe("MarketPane 參數化(SC-2)", () => {
  it("(a) 無 storage 時尊重 defaultKey:右 pane 預設櫃買", () => {
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "OTC" });
    expect(pill("櫃買").checked).toBe(true);
    expect(pill("加權").checked).toBe(false);
    expect(screen.getByText("櫃買指數")).toBeTruthy();
  });

  it("(a2) 根節點 data-testid 依 paneId", () => {
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "OTC" });
    const pane = screen.getByTestId("market-pane-right");
    expect(pane).toBeTruthy();
    expect(within(pane).getByText("櫃買指數")).toBeTruthy();
    expect(screen.queryByTestId("market-pane-left")).toBeNull();
  });

  it("(b) storage keys 注入生效:寫入指定 key,舊 key 不動", () => {
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "OTC" });
    fireEvent.click(pill("台指期"));
    fireEvent.click(pill("小台"));
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBe("MXF");
    expect(window.localStorage.getItem(MARKET2_FUT_STORE)).toBe("MXF");
    expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBe("m1");
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET_FUT_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBeNull();
  });

  it("(b2) 讀取也走注入的 key:market2 殘值生效、舊 key 殘值被忽略", () => {
    window.localStorage.setItem(MARKET2_KEY_STORE, "OTC");
    window.localStorage.setItem(MARKET_KEY_STORE, "TWSE");
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "TWSE" });
    expect(pill("櫃買").checked).toBe(true);
  });

  it("(c) OTC 時日/週/月 disabled,分 K 仍可點", () => {
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "OTC" });
    for (const label of ["日K", "週K", "月K"]) {
      expect(pill(label).parentElement!.getAttribute("aria-disabled")).toBe("true");
      expect(pill(label).disabled).toBe(true);
    }
    expect(pill("30分").disabled).toBe(false);
  });

  it("(d) 殘值「日K + 櫃買」重載後經 coerce 落回分時", () => {
    window.localStorage.setItem(MARKET2_KEY_STORE, "OTC");
    window.localStorage.setItem(MARKET2_MODE_STORE, "day");
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "TWSE" });
    expect(pill("櫃買").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
  });

  it("(e) 期指子鈕切換:點台指期才出現三選一,選微台後標題換料", () => {
    renderPane();
    // TC-3:pill 已改 radio,查 `button` 恆為 null = 恆真斷言(「期貨商品列一直都在」
    // 這個 bug 照樣全綠)。查的角色必須跟實作同一個。
    expect(screen.queryByRole("radio", { name: "小台" })).toBeNull();
    fireEvent.click(pill("台指期"));
    expect(pill("大台").checked).toBe(true);
    fireEvent.click(pill("微台"));
    expect(screen.getByText("台指期(微台)")).toBeTruthy();
    expect(pill("微台").checked).toBe(true);
  });

  it("(f) 只寫 mode=day 不寫 key → defaultKey=OTC 落分時,無 disabled 模式被選中", () => {
    window.localStorage.setItem(MARKET2_MODE_STORE, "day");
    renderPane({ paneId: "right", stores: RIGHT_STORES, defaultKey: "OTC" });
    expect(pill("櫃買").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
    expect(pill("日K").checked).toBe(false);
    // 沒有任何 disabled 鈕處於選中狀態(a11y 批:改數 checked 的 radio;`aria-disabled`
    // 掛在 label 上)
    const checked = (screen.getAllByRole("radio") as HTMLInputElement[]).filter((r) => r.checked);
    expect(checked.length).toBeGreaterThan(0);
    for (const r of checked) expect(r.parentElement!.getAttribute("aria-disabled")).toBeNull();
  });

  it("(g) stores.overlay undefined → 無「重疊」鈕;有 overlay key 才有", () => {
    const { unmount } = renderPane({
      paneId: "right",
      stores: RIGHT_STORES,
      defaultKey: "TWSE",
    });
    expect(screen.queryByRole("button", { name: "重疊" })).toBeNull();
    unmount();
    cleanup();
    renderPane();
    expect(screen.getByRole("button", { name: "重疊" })).toBeTruthy();
  });
});

describe("MarketPane review 修復", () => {
  it("(SI-1) 標的切換一律沖掉 mode 殘值,重載不會跳到沒選過的週期", () => {
    // 殘值 = 「櫃買 + 日K」,畫面已 coerce 成分時,但 storage 的 mode 還留著 day
    window.localStorage.setItem(MARKET_KEY_STORE, "OTC");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    renderPane();
    expect(pill("分時").checked).toBe(true);
    // 點加權 = 一次 no-op coerce(intraday 對 TWSE 合法)→ 舊寫法只寫 key 不寫 mode,
    // storage 變成 TWSE+day 這組「合法但使用者沒選過」的組合,下次重載就跳日K
    fireEvent.click(pill("加權"));
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBe("intraday");
  });

  it("(F3) 根節點是具名 group,兩 pane 在 a11y 樹可區分", () => {
    renderPane({ paneId: "left" });
    expect(screen.getByRole("group", { name: "左圖" })).toBeTruthy();
  });
});

describe("MarketPane 標的列(自 IndexPage 搬遷)", () => {
  it("三顆標的鈕;預設選加權,現值/漲跌/高低昨收顯示於標題列", () => {
    renderPane();
    expect(pill("加權").checked).toBe(true);
    expect(pill("櫃買")).toBeTruthy();
    expect(pill("台指期")).toBeTruthy();
    expect(screen.getByText("加權指數")).toBeTruthy();
    expect(screen.getByText(/-1594\.27/)).toBeTruthy();
    // 昨收改斷言在**同一個標題列元素**上:分時圖右緣現在也有一顆「昨收 <值>」標籤
    // (SC-6),裸 getByText 會撞兩個元素。本條要驗的是「標題列印得出昨收」,不是
    // 「全畫面只有一處昨收」—— 收斂 scope,不放寬語意。
    const quote = screen.getByText(/高 43221\.93/);
    expect(quote.textContent).toContain("昨收 43634.19");
    // 現值同理收斂到標題列:分時圖換 `IntradayChartCore` 後 readout 也印「該分鐘點位」,
    // 而最新分鐘的收盤恰等於現值 —— 裸 getByText 撞兩個元素。
    expect(within(quote.closest("figcaption")!).getByText("42039.92")).toBeTruthy();
  });

  it("Quote 漲跌整串:跌用負號(characterization)", () => {
    renderPane();
    expect(screen.getByText("-1594.27 (-3.65%)")).toBeTruthy();
  });

  it("Quote 漲跌整串:漲帶 + 前綴(characterization;台指期)", () => {
    renderPane();
    fireEvent.click(pill("台指期"));
    expect(screen.getByText("+142.00 (+0.34%)")).toBeTruthy();
  });

  it("期指商品用獨立 localStorage key,不碰期貨 tab 的 copycat-fut-product(W-13)", () => {
    renderPane();
    fireEvent.click(pill("台指期"));
    fireEvent.click(pill("小台"));
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBe("MXF");
    expect(window.localStorage.getItem(MARKET_FUT_STORE)).toBe("MXF");
    expect(window.localStorage.getItem("copycat-fut-product")).toBeNull();
  });

  it("basis 列不屬 pane(留在 IndexPage)", () => {
    renderPane();
    expect(screen.queryByTestId("basis-row")).toBeNull();
  });
});

describe("MarketPane 週期列(自 IndexPage 搬遷)", () => {
  it("十七顆週期鈕,順序 = 分時 / 1-10分 / 30 / 60 / 90 / 日 / 週 / 月", () => {
    renderPane();
    const labels = [
      "分時", "1分", "2分", "3分", "4分", "5分", "6分", "7分", "8分", "9分", "10分",
      "30分", "60分", "90分", "日K", "週K", "月K",
    ];
    const nodes = labels.map((l) => pill(l));
    for (let i = 1; i < nodes.length; i += 1) {
      // DOM 順序 = 畫面由左至右
      expect(nodes[i - 1]!.compareDocumentPosition(nodes[i]!) & Node.DOCUMENT_POSITION_FOLLOWING)
        .toBeTruthy();
    }
  });

  it("預設分時;切日K 後打 /api/market/bars 並持久化", async () => {
    renderPane();
    expect(pill("分時").checked).toBe(true);
    fireEvent.click(pill("日K"));
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBe("day");
    await waitFor(() =>
      expect(lastUrls.some((u) => u.includes("/api/market/bars/TWSE?tf=D"))).toBe(true),
    );
  });

  it("分 K 走 tf=1 共用原料(30/60/90 由前端聚合)", async () => {
    renderPane();
    fireEvent.click(pill("90分"));
    await waitFor(() =>
      expect(lastUrls.some((u) => u.includes("/api/market/bars/TWSE?tf=1&days=30"))).toBe(true),
    );
  });
});

describe("MarketPane 櫃買降級(自 IndexPage 搬遷)", () => {
  it("日/週/月 K 鈕 disabled,分 K 仍可點", () => {
    renderPane();
    fireEvent.click(pill("櫃買"));
    for (const label of ["日K", "週K", "月K"]) {
      expect(pill(label).parentElement!.getAttribute("aria-disabled")).toBe("true");
      expect(pill(label).disabled).toBe(true);
    }
    expect(pill("30分").disabled).toBe(false);
  });

  it("從加權(日K)切到櫃買 → 自動落回分時,不停在 disabled 模式", () => {
    renderPane();
    fireEvent.click(pill("日K"));
    fireEvent.click(pill("櫃買"));
    expect(pill("分時").checked).toBe(true);
  });

  it("後端回 refusal → 圖區顯示明確理由,不畫假圖", async () => {
    stubFetch({
      key: "OTC",
      tf: "D",
      bars: [],
      meta: {
        source: "none",
        coverage_from: null,
        coverage_to: null,
        partial_last: false,
        volume: false,
        refusal: "NO_HISTORICAL_SOURCE",
        synth_since: null,
      },
    });
    renderPane();
    fireEvent.click(pill("日K"));
    await waitFor(() =>
      expect(screen.getByText("達錢 4 未提供櫃買指數,無歷史 K 線資料源")).toBeTruthy(),
    );
  });

  it("localStorage 存著非法組合(櫃買 + 日K)重載後落回分時", () => {
    window.localStorage.setItem(MARKET_KEY_STORE, "OTC");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    renderPane();
    expect(pill("櫃買").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
  });

  it("期指沒有分時 → 分時鈕 disabled,由加權切過去自動落到 1分", () => {
    renderPane();
    fireEvent.click(pill("台指期"));
    expect(pill("分時").disabled).toBe(true);
    expect(pill("1分").checked).toBe(true);
  });
});

describe("MarketPane 重疊(自 IndexPage 搬遷;左 pane 形態)", () => {
  it("分時下有重疊 toggle,開啟後顯示加權 vs 櫃買疊線並持久化", () => {
    renderPane();
    fireEvent.click(btn("重疊"));
    expect(screen.getByText("加權 vs 櫃買(相對昨收 %)")).toBeTruthy();
    expect(screen.getByLabelText("指數重疊走勢")).toBeTruthy();
    expect(window.localStorage.getItem(INDEX_OVERLAY_STORE)).toBe("overlay");
  });

  it("舊 localStorage 值 overlay 讀時遷移(backward compat)", () => {
    window.localStorage.setItem(INDEX_OVERLAY_STORE, "overlay");
    renderPane();
    expect(screen.getByText("加權 vs 櫃買(相對昨收 %)")).toBeTruthy();
  });

  it("切到 K 線週期後不再顯示重疊圖", () => {
    window.localStorage.setItem(INDEX_OVERLAY_STORE, "overlay");
    renderPane();
    fireEvent.click(pill("日K"));
    expect(screen.queryByLabelText("指數重疊走勢")).toBeNull();
  });
});

describe("MarketPane meta 行(自 IndexPage 搬遷)", () => {
  it("顯示資料源中文與涵蓋期間", async () => {
    renderPane();
    fireEvent.click(pill("日K"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("達錢 4 日K");
    expect(meta.textContent).toContain("2026-07-27 ~ 2026-07-29");
  });

  it("fallback 分支要說實話(tc4_dk_1k_agg),partial_last 標未收盤", async () => {
    stubFetch({
      ...DK_BODY,
      meta: { ...DK_BODY.meta, source: "tc4_dk_1k_agg", partial_last: true },
    });
    renderPane();
    fireEvent.click(pill("週K"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("達錢 4 1分K 聚合(日K 無資料)");
    expect(meta.textContent).toContain("最後一根未收盤");
  });

  it("本機合成標明來源與起始時刻;無量資料不畫 0 柱、量欄顯示「—」", async () => {
    stubFetch({
      key: "OTC",
      tf: "1",
      bars: [{ t: "2026-07-30 10:17", o: 359_800, h: 359_900, l: 359_700, c: 359_800, v: 0 }],
      meta: {
        source: "mis_poll_synth",
        coverage_from: "2026-07-30",
        coverage_to: "2026-07-30",
        partial_last: false,
        volume: false,
        refusal: null,
        synth_since: "10:17",
      },
    });
    renderPane();
    fireEvent.click(pill("櫃買"));
    fireEvent.click(pill("1分"));
    const meta = await screen.findByTestId("market-meta");
    expect(meta.textContent).toContain("本機合成(MIS 5秒取樣)");
    expect(meta.textContent).toContain("自 10:17 起");
    expect(screen.getByText("無量資料")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy(); // 資訊列的量欄
  });
});

// 🔴 N262:`buildOverlayGeometry` 濾掉 ref 缺值的 series,而 OverlayCard 以陣列位置查
// `OVERLAY_LINES` → twse.ref 缺時僅剩的**櫃買**線被畫成加權色、標成「加權」。
// 兩腿都在的正常態逐值不變(白名單 W4)。
describe("MarketPane 重疊單邊 ref 缺值(N262)", () => {
  function openOverlay() {
    fireEvent.click(btn("重疊"));
    return screen.getByLabelText("指數重疊走勢");
  }

  it("加權 ref 缺值 → 僅存的櫃買線用櫃買色與「櫃買」標籤", () => {
    renderPane({ twse: series({ ref: null }) });
    const svg = openOverlay();
    const lines = [...svg.querySelectorAll("polyline")];
    expect(lines).toHaveLength(1);
    expect(lines[0]!.getAttribute("class")).toContain("stroke-idx-otc");
    // 線末端的標籤同樣不可錯位
    const labels = [...svg.querySelectorAll("text")].map((t) => t.textContent);
    expect(labels).toContain("櫃買");
    expect(labels).not.toContain("加權");
  });

  it("兩腿都在 → 顏色 / 標籤逐值不變(既有行為)", () => {
    renderPane();
    const svg = openOverlay();
    const lines = [...svg.querySelectorAll("polyline")];
    expect(lines).toHaveLength(2);
    expect(lines[0]!.getAttribute("class")).toContain("stroke-profit");
    expect(lines[1]!.getAttribute("class")).toContain("stroke-idx-otc");
  });
});

// 🔴 N108:MIS(櫃買快照源)從開盤即死透的日子 —— otc 的 p/ref 恆 null、minutes 恆空,
// 而 otc **不吃 `stale`**(watchdog 只看加權)→ 畫面是一條靜默的空線。加權有分鐘格
// 而櫃買一格都沒有 = 唯一自足的判別子(盤前兩者皆空 → 不誤報)。
describe("MarketPane 櫃買快照源中斷(N108)", () => {
  const DEAD = series({ p: null, ref: null, high: null, low: null, minutes: {} });

  it("加權有分鐘格、櫃買整片空 → 櫃買 pane 印「櫃買快照源中斷」", () => {
    renderPane({ defaultKey: "OTC", otc: DEAD });
    expect(screen.getByText("櫃買快照源中斷")).toBeTruthy();
  });

  it("加權 pane 不受影響(不是它的問題)", () => {
    renderPane({ defaultKey: "TWSE", otc: DEAD });
    expect(screen.queryByText("櫃買快照源中斷")).toBeNull();
  });

  it("盤前(加權也還沒有分鐘格)不誤報", () => {
    renderPane({ defaultKey: "OTC", twse: series({ p: null, ref: null, minutes: {} }), otc: DEAD });
    expect(screen.queryByText("櫃買快照源中斷")).toBeNull();
  });

  it("開盤頭兩分鐘給 MIS poll 寬限(加權只有一格時不報)", () => {
    renderPane({
      defaultKey: "OTC",
      twse: series({ minutes: { "0901": 43_000_000 } }),
      otc: DEAD,
    });
    expect(screen.queryByText("櫃買快照源中斷")).toBeNull();
  });

  it("櫃買有值 → 不報(既有行為)", () => {
    renderPane({ defaultKey: "OTC" });
    expect(screen.queryByText("櫃買快照源中斷")).toBeNull();
  });
});
