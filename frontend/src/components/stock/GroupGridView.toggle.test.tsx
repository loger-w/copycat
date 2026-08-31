/** @vitest-environment jsdom */
/** SC-2:圖牆頂那一列 toggle → **每一張卡**同步顯示 / 隱藏該層。
 *
 *  **獨立檔**:vp 直方圖的資料來自 group-state 的 `vp` 鍵(包 B,尚未落地),
 *  `useGroupSnapshots` 現在還不解析它 —— 走真 fetch 的話 `snap.vp` 恆空,
 *  「開了 toggle 有沒有出現長條」永遠測不到(全綠但 vacuous)。改 mock hook 直接餵一份
 *  含 vp 的 Map:這裡要鎖的是「圖牆頂的 toggle 狀態有沒有傳到每一張卡」這條線,
 *  不是 vp 的折法(那是包 B 的 parity fixture 在管)。
 *  `vi.mock` 是檔案級 + hoisted,與同目錄走真 hook 的測試不能共存。 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type React from "react";
import { GroupGridView } from "@/components/stock/GroupGridView";
import { useStockGroup } from "@/hooks/useStockGroup";
import { CHART_TOGGLES_KEY } from "@/lib/constants";
import { ymdOf } from "@/lib/ladder-lots";
import type { MinuteAgg, VpCell } from "@/lib/stock-accum";
import type { Group } from "@/lib/watchlist-model";
import type { CapitalFill } from "@/types";
import { wrap } from "@/test-utils";


/** 測試用外殼:圖牆自 F2 起受控(「現在看哪一組」唯一持有者是 StockPage 的 `useStockGroup`),
 *  這裡以同一支 hook 扮演 StockPage,既有「記住的群組」語意(localStorage)一字不改。 */
function Grid(props: Omit<React.ComponentProps<typeof GroupGridView>, "selectedGroup" | "onSelectGroup">) {
  const { picked, select } = useStockGroup();
  return <GroupGridView {...props} selectedGroup={picked} onSelectGroup={select} />;
}
const GROUPS: Group[] = [{ name: "半導體", codes: ["2330", "2317"] }];

function snap() {
  return {
    minutes: new Map<number, MinuteAgg>([
      [540, { c: 2_380_000, v: 10, i: 3, o: 7, u: 0, h: 2_385_000, l: 2_375_000 }],
      [541, { c: 2_390_000, v: 6, i: 2, o: 4, u: 0, h: 2_392_000, l: 2_386_000 }],
    ]),
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    noData: false,
    backfilling: false,
    vwap: 2_385_000,
    high: 2_392_000,
    low: 2_375_000,
    vp: new Map<number, VpCell>([
      [2_380_000, { t: 10, o: 7, i: 3 }],
      [2_390_000, { t: 6, o: 4, i: 2 }],
    ]),
  };
}

vi.mock("@/hooks/useGroupSnapshots", () => ({
  useGroupSnapshots: () => ({ data: { "2330": snap(), "2317": snap() }, isPending: false }),
}));

/** 同 GroupGridView.test.tsx:量到尺寸卡片才畫圖(AD-3),jsdom 沒有 RO。 */
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

/** SC-5 的委託 fixture:2330 / 2317 各一筆當日成交(minute 540,價 2380 元落在
 *  `snap()` 的 y 域 [2090000, 2550000] 內)。`date` 動態算 —— 寫死會在隔天靜默轉紅。 */
function fillOf(code: string, seqNo: string): CapitalFill {
  return {
    seq_no: seqNo,
    stock_no: code,
    buy_sell: "B",
    flag_label: null,
    price: 2380,
    qty: 1,
    unit: "張",
    date: ymdOf(new Date()),
    time: "09:00:30",
    code,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      // 圖牆層掛一份 `useCapitalOrders`(SC-6);不分 URL 回 overlay 的話它會拿 overlay
      // 的殼當委託列表用 → `orders` undefined → 恆零標記,SC-5 的成交點案靜默 vacuous。
      String(url).includes("/api/capital/fills")
        ? new Response(JSON.stringify({ fills: [fillOf("2330", "s1"), fillOf("2317", "s2")] }))
        : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function vpBarCount(): number {
  return document.querySelectorAll('[data-testid="vp-bar"]').length;
}

describe("GroupGridView toggle 列同步每張卡(SC-2)", () => {
  it("localStorage 預種 vp:false → 掛載即無長條;按「量分佈」→ 兩張卡同時出現、再按同時消失", async () => {
    window.localStorage.setItem(
      CHART_TOGGLES_KEY,
      JSON.stringify({ vwap: true, cdp: false, ma: false, bb: true, vp: false, v: 2 }),
    );
    wrap(<Grid groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await screen.findByTestId("group-card-2330");
    // 存檔優先於預設(vp 預設是開的)—— 這條同時鎖住「重整後狀態保留」
    expect(vpBarCount()).toBe(0);

    fireEvent.click(screen.getByTestId("grid-toggle-vp"));
    // 兩張卡各兩根:同步是**每一張**卡都吃到,不是只有第一張(卡片各持一份 toggles
    // 的話點一次只會亮一張,而那正是把 useChartToggles 留在卡片內的失效樣態)
    await waitFor(() => expect(vpBarCount()).toBe(4));
    expect(screen.getByTestId("grid-toggle-vp").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByTestId("grid-toggle-vp"));
    await waitFor(() => expect(vpBarCount()).toBe(0));
    expect(
      JSON.parse(window.localStorage.getItem(CHART_TOGGLES_KEY) ?? "{}") as { vp?: boolean },
    ).toMatchObject({ vp: false });
  });

  /** 🟢 R2 SC-5:成交點 toggle 同樣是圖牆頂一顆管所有卡。
   *  量法一律 **per-card** `polygon[data-testid^="fill-"]` —— 兩張卡同一分鐘同一側時
   *  testid 會撞,document 級的 getByTestId 直接拋 multiple-elements。
   *  `fills-layer` 群組不入計數(它恆存,數進去就永遠 > 0)。 */
  it("localStorage 預種 fills:false → 掛載即無三角;按「成交點」→ 兩張卡同時出現", async () => {
    window.localStorage.setItem(
      CHART_TOGGLES_KEY,
      JSON.stringify({ vwap: true, cdp: false, ma: false, bb: true, vp: false, fills: false, v: 2 }),
    );
    wrap(<Grid groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    const cards = [
      await screen.findByTestId("group-card-2330"),
      screen.getByTestId("group-card-2317"),
    ];
    const marks = (el: HTMLElement) =>
      el.querySelectorAll('polygon[data-testid^="fill-"]').length;
    // 存檔優先於預設(fills 預設是開的)—— 這條同時鎖住「重整後狀態保留」
    for (const c of cards) expect(marks(c)).toBe(0);

    fireEvent.click(screen.getByTestId("grid-toggle-fills"));
    // **每一張**卡都要吃到(卡片各持一份 toggles 的話點一次只會亮一張)
    await waitFor(() => expect(marks(cards[0]!)).toBeGreaterThan(0));
    expect(marks(cards[1]!)).toBeGreaterThan(0);
    expect(screen.getByTestId("grid-toggle-fills").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByTestId("grid-toggle-fills"));
    await waitFor(() => expect(marks(cards[0]!)).toBe(0));
    expect(marks(cards[1]!)).toBe(0);
  });

  it("均價 toggle 同樣傳到每張卡(VWAP 白線 + 右緣價位標)", async () => {
    window.localStorage.setItem(
      CHART_TOGGLES_KEY,
      JSON.stringify({ vwap: false, cdp: false, ma: false, bb: true, vp: false, v: 2 }),
    );
    wrap(<Grid groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    await screen.findByTestId("group-card-2330");
    expect(document.querySelectorAll('[data-testid="edge-price-vwap"]').length).toBe(0);

    fireEvent.click(screen.getByTestId("grid-toggle-vwap"));
    await waitFor(() =>
      expect(document.querySelectorAll('[data-testid="edge-price-vwap"]').length).toBe(2),
    );
  });
});
