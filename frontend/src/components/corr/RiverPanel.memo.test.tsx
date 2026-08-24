/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RiverPanel } from "@/components/corr/RiverPanel";
// 共檔 fixture(`river-test-fixtures.ts`):與 `RiverPanel.test.tsx` 同一組數字 —— 本檔的
// 「台指 —」自檢與 `xAt` 換算就是行為檔拍下來的那組,分兩份會各自漂。
import { mockRect, riverState as state, xAt } from "@/components/corr/river-test-fixtures";
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
  /** timeTicks 呼叫次數 = **render body 實際跑了幾次**(它在 render body 內、不在任何
   *  useMemo 裡)。呼叫者依模式而異,兩種模式各取其一,別混讀:
   *  - 並排:只有 `RiverCard` 叫它(RiverPanel 自己不叫、RiverOverlay 沒 mount)
   *    → 數字 = 卡片 render 次數;
   *  - 重疊:只有 `RiverOverlay` 叫它(卡片沒 mount)→ 數字 = 重疊圖 render 次數。
   *  並排案非有它不可:卡內的 `useMemo([leg, win])` 會把幾何擋住,所以光看 buildLegGeometry
   *  量不出 `memo(RiverCard)` 在不在 —— 拔掉 memo 卡片照樣每輪重跑整個 render body
   *  (七腿 × 全窗刻度 + polyline 字串),而 buildLegGeometry 計次紋風不動。 */
  ticks: 0,
  /** `RiverOverlay` 的 **render body 執行次數**(N030 起的重疊圖探針)。
   *
   *  舊探針是 `timeTicks`:它當時落在 RiverOverlay 的 render body 上,計次剛好等於
   *  render 次數。N030 把 `timeTicks` 與七條 polyline 字串一起收進幾何 useMemo 之後,
   *  那個位置就沒有東西可數了 —— 沿用它會讓「重疊圖 render 次數」的斷言變成恆 0 的
   *  假綠(mousemove 照樣重跑 render body,只是探針看不到)。
   *  改成直接包住元件本體:與「哪個 lib 函式恰好留在 render body」解耦。 */
  overlayRenders: 0,
  /** `pts()` 呼叫次數 = **polyline 座標字串重組**次數(N030 的收斂目標)。
   *  滿窗夜盤是 840 分鐘 × 七腿,每則 mousemove 重組一次是純浪費。 */
  pts: 0,
}));

vi.mock("@/lib/svg-points", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/svg-points")>();
  return {
    ...actual,
    pts: (...args: Parameters<typeof actual.pts>) => {
      hoisted.pts += 1;
      return actual.pts(...args);
    },
  };
});

vi.mock("@/components/corr/RiverOverlay", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/corr/RiverOverlay")>();
  const Wrapped = (props: Parameters<typeof actual.RiverOverlay>[0]) => {
    hoisted.overlayRenders += 1;
    return actual.RiverOverlay(props);
  };
  return { ...actual, RiverOverlay: Wrapped, default: Wrapped };
});

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

/** 重疊圖上某一腿的腿名標籤 x(= 該腿末點 x + 4;`RiverOverlay` 的右緣標籤)。
 *  取 svg 內的 `<text>` 而非勾選列的按鈕 —— 兩處文字相同,按鈕不隨資料動。 */
function legLabelX(label: string): number {
  const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
  const el = Array.from(svg.querySelectorAll("text")).find((t) => t.textContent === label);
  if (el === undefined) throw new Error(`重疊圖上沒有 ${label} 這一腿的標籤`);
  return Number(el.getAttribute("x"));
}

beforeEach(() => {
  hoisted.overlay = 0;
  hoisted.legs.length = 0;
  hoisted.ticks = 0;
  hoisted.overlayRenders = 0;
  hoisted.pts = 0;
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
    const beforeRender = hoisted.overlayRenders;
    const beforeTicks = hoisted.ticks;
    const beforePts = hoisted.pts;
    // 自檢:兩個探針在**掛載時**確實被叫過(掛載都是 0 的話,下面的「+0」與 memo 無關,
    // 而是探針根本沒接上 —— 那條斷言會靜默變成恆真)
    expect(beforeTicks).toBeGreaterThan(0);
    expect(beforePts).toBeGreaterThan(0);

    // 三個**相異**的 offset:同一 offset 連發會被 setState 的相同值 bail out,量不到東西
    fireEvent.mouseMove(svg, { clientX: xAt(20), clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: xAt(10), clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: xAt(15), clientY: 100 });

    // 自檢:讀值列真的跟著游標動了(hover 沒生效的話 +0 是假綠)
    expect(screen.getByText("台指 —")).toBeTruthy();
    expect(hoisted.overlay - before).toBe(0);
    // **現況拍照,不是收斂目標**:cursor 住在 RiverOverlay 內,每則 mousemove 仍重跑一次
    // 它的 render body(讀值列 + 十字線)。這條在意的是這個數字別在無人察覺下往上長
    // (例如把 cursor 提到 RiverPanel 層 → 連 RiverCards / 勾選列一起重繪);要往下收
    // 得換手法(cursor 下沉到子元件 / 十字線獨立成一層),那是另一個題目。
    expect(hoisted.overlayRenders - beforeRender).toBe(3);
    // 🔵 N030 的收斂:render body 重跑,但**全窗刻度與七條 polyline 字串一次都不重組**
    // (兩者已隨幾何進 useMemo)。把它們搬回 render body 的話這兩個數字會變成 3 / 21。
    expect(hoisted.ticks - beforeTicks).toBe(0);
    expect(hoisted.pts - beforePts).toBe(0);
  });

  it("重疊圖:一腿有新 tick → 幾何恰重算一次,且該腿末點跟著換(entries deps 反向守門)", () => {
    const s1 = state();
    const { rerender } = render(<RiverPanel state={s1} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));
    // 自檢:重疊圖真的畫出來了(沒畫的話下面的 +1 與 +0 都無從談起)
    expect(hoisted.overlay).toBeGreaterThan(0);
    const before = hoisted.overlay;
    // 富台末點在 offset 20 → x = (20/300)*960 = 64,腿名標籤畫在 x+4
    expect(legLabelX("富台")).toBe(68);

    // 只有富台收到新 tick(applyDelta 樣態:台指腿與 window 保持同參照)
    rerender(<RiverPanel state={withTick(s1, "TWN", 30, 3_400_000)} />);

    // 上面那條案例鎖的是「別多算」,這條鎖的是**反向**:`entries` 的 deps 掉了 `legs`
    // (只剩 `off`)→ identity 永不換 → 幾何 +0、富台的線凍在 offset 20,而畫面上
    // 「線照畫、值照對」,只有那一腿悄悄停在過去。
    expect(hoisted.overlay - before).toBe(1);
    expect(legLabelX("富台")).toBe(100); // offset 30 → x = 96
    expect(legLabelX("台指")).toBe(68); // 同輪對照組:沒收到 tick 的腿末點不動
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
