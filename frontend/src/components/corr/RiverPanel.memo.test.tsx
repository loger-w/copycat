/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RiverPanel } from "@/components/corr/RiverPanel";
import type { RiverLeg, RiverState } from "@/types";

/** S3 memo 邊界的 regression lock:江波圖的兩道重算邊界有沒有真的擋住。
 *
 *  這兩件事**在畫面上完全看不出來** —— 失效只是多算幾何:
 *  (1) 重疊圖每次 mousemove(游標在圖上滑一下 = 數十則事件)重算七腿全窗幾何;
 *  (2) 任一腿有新 tick(每秒)時六張並排卡片全部重算,而 delta 通常只動一兩腿。
 *  線照畫、值照對,只有 CPU 知道。
 *
 *  量法(refactor-plan R11):`importOriginal` partial mock `@/lib/river-chart-svg`,
 *  **只包住** `buildOverlayGeometry` / `buildLegGeometry` 兩支計次,其餘 export
 *  (`offsetAtX` / `spreadLabelYs` / `timeTicks` / `PAD_Y` …)一律保留真身 ——
 *  漏了 `offsetAtX` 游標換算就變 NaN、漏了 `timeTicks` 時間軸整條不見,
 *  測試會以為自己在量 memo,其實在量壞掉的圖。
 *  跨腿案採「同輪對照組」:未變的腿(台指)與變了的腿(富台)在同一次 rerender 內比較。
 *
 *  **獨立檔**:`vi.mock` 是檔案級 + hoisted,與同目錄那份要看到真幾何數字的
 *  `RiverPanel.test.tsx` 不能共存。 */

const hoisted = vi.hoisted(() => ({
  /** buildOverlayGeometry 被呼叫幾次(= 重疊圖七腿全窗幾何重算次數) */
  overlay: 0,
  /** buildLegGeometry 每次呼叫的腿名(= 哪一張並排卡片重算了幾何) */
  legs: [] as string[],
  /** timeTicks 呼叫次數。**並排模式下只有 `RiverCard` 會呼叫它**(RiverPanel 自己不叫、
   *  RiverOverlay 沒 mount),而它在卡片 render body 內、不在任何 useMemo 裡
   *  → 這個數字就是「卡片實際 render 了幾次」。
   *  非有它不可:卡內的 `useMemo([leg, win])` 會把幾何擋住,所以光看 buildLegGeometry
   *  量不出 `memo(RiverCard)` 在不在 —— 拔掉 memo 卡片照樣每輪重跑整個 render body
   *  (七腿 × 全窗刻度 + polyline 字串),而 buildLegGeometry 計次紋風不動。 */
  ticks: 0,
}));

vi.mock("@/lib/river-chart-svg", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/river-chart-svg")>();
  return {
    ...actual,
    buildOverlayGeometry: (...args: Parameters<typeof actual.buildOverlayGeometry>) => {
      hoisted.overlay += 1;
      return actual.buildOverlayGeometry(...args);
    },
    buildLegGeometry: (...args: Parameters<typeof actual.buildLegGeometry>) => {
      hoisted.legs.push(args[0].label);
      return actual.buildLegGeometry(...args);
    },
    timeTicks: (...args: Parameters<typeof actual.timeTicks>) => {
      hoisted.ticks += 1;
      return actual.timeTicks(...args);
    },
  };
});

const DAY = { start_min: 525, end_min: 825 };

function state(): RiverState {
  return {
    type: "river",
    seq: 3,
    session: "day",
    base: "TXF",
    window: DAY,
    legs: {
      TXF: {
        label: "台指",
        minutes: { "10": 40_000_000, "20": 40_400_000 },
        last: 40_400_000,
        last_minute: 20,
      },
      TWN: {
        label: "富台",
        minutes: { "10": 3_400_000, "20": 3_366_000 },
        last: 3_366_000,
        last_minute: 20,
      },
      YM: { label: "道瓊", minutes: {}, last: null, last_minute: null },
    },
  };
}

/** 模擬 `useRiver.applyDelta` 的產物:只有收到點的腿換 identity,其餘腿與 `window` 保持同參照。 */
function withTick(prev: RiverState, key: string, minute: number, price: number): RiverState {
  const leg = prev.legs[key] as RiverLeg;
  const minutes = { ...leg.minutes, [String(minute)]: price };
  return {
    ...prev,
    seq: prev.seq + 1,
    legs: { ...prev.legs, [key]: { ...leg, minutes, last: price, last_minute: minute } },
  };
}

/** viewBox 寬 = 960(RiverOverlay.SIZE);jsdom 的 rect 恆 0 會讓 handleMouseMove 早退。 */
function mockRect(): void {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    right: 960,
    bottom: 340,
    width: 960,
    height: 340,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

function xAt(offset: number): number {
  return (offset / (DAY.end_min - DAY.start_min)) * 960;
}

beforeEach(() => {
  hoisted.overlay = 0;
  hoisted.legs.length = 0;
  hoisted.ticks = 0;
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("江波圖 memo 邊界計次(S3)", () => {
  it("重疊圖:游標滑過三個分鐘 → 七腿幾何零重算(cursor 只動讀值列)", () => {
    mockRect();
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));
    const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
    // 自檢:圖真的畫出來了(幾何至少算過一次),否則下面量的 +0 與 memo 無關
    expect(hoisted.overlay).toBeGreaterThan(0);
    const before = hoisted.overlay;

    // 三個**相異**的 offset:同一 offset 連發會被 setState 的相同值 bail out,量不到東西
    fireEvent.mouseMove(svg, { clientX: xAt(20), clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: xAt(10), clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: xAt(15), clientY: 100 });

    // 自檢:讀值列真的跟著游標動了(hover 沒生效的話 +0 是假綠)
    expect(screen.getByText("台指 —")).toBeTruthy();
    expect(hoisted.overlay - before).toBe(0);
  });

  it("並排卡片:一腿有新 tick → 只有那張卡重算幾何(同輪對照組:沒動的腿)", () => {
    const s1 = state();
    const { rerender } = render(<RiverPanel state={s1} />);
    // 自檢:三張卡都畫過(道瓊無點也照畫「無資料」卡)
    expect(hoisted.legs.filter((l) => l === "台指").length).toBeGreaterThan(0);
    const count = (label: string): number => hoisted.legs.filter((l) => l === label).length;
    const [b台指, b富台, b渲染] = [count("台指"), count("富台"), hoisted.ticks];
    // 自檢:掛載時三張卡都 render 過(台指 / 富台 / 道瓊)
    expect(b渲染).toBe(3);

    // 只有富台收到新 tick(= applyDelta 的樣態:台指腿與 window 保持同參照)
    rerender(<RiverPanel state={withTick(s1, "TWN", 30, 3_400_000)} />);

    expect(count("富台") - b富台).toBe(1); // 值真的變了,這張非重算不可(卡內 useMemo 邊界)
    expect(count("台指") - b台指).toBe(0); // 對照組:沒動的腿不該被拖著重算幾何
    expect(hoisted.ticks - b渲染).toBe(1); // 三張卡只有富台那張重繪(memo(RiverCard) 邊界)
  });
});
