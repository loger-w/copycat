// @vitest-environment jsdom
/** dev-only User Timing guard(2026-08-19 /bug react-dev-measure-leak)。
 *
 *  React 19.2 development build 的 Component Performance Track 對每個「props identity 變了」的
 *  re-render 打一筆 `performance.measure`;Chrome 的 User Timing buffer 沒上限、不在 V8 heap、
 *  不自動回收 → 看盤 632 筆/秒 ≈ 1.1 MB/s,數小時後 renderer Aw Snap。
 *
 *  guard 走 PerformanceObserver「條目數 ≥ 閾值就清」,**不用 setInterval**:背景分頁的 timer 被
 *  Chrome 節流到每分鐘一次(真環境實測 20 s 只跑 7 次),observer 回呼不受節流(同 20 s 256 次)。
 *
 *  vitest 的 console 沒有 `timeStamp`,React 據此判定 `supportsUserTiming=false` 整段不發 →
 *  必須在 react-dom 載入前補 stub 才重現得出來(hoisted + 動態 import)。 */
import { afterEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  (console as unknown as { timeStamp: () => void }).timeStamp = () => {};
});

function Leaf({ rows }: { rows: number[] }) {
  return <div>{rows.length}</div>;
}

/** 每個 test 的 dispose 交給 afterEach:斷言一紅,observer 不會外洩到下一個 test(review C-5/T-5)。 */
let dispose: (() => void) | undefined;

afterEach(async () => {
  dispose?.();
  dispose = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  const { cleanup } = await import("@testing-library/react");
  cleanup();
  performance.clearMeasures();
  performance.clearMarks();
});

const RENDERS = 20;

/** React dev 每次 re-render 至少留 1 筆(實測約 2 筆);斷言只依賴較弱的「≥ 1 筆/render」。 */
async function renderTimes(n: number): Promise<void> {
  const { act, render } = await import("@testing-library/react");
  const { rerender } = render(<Leaf rows={[0]} />);
  for (let i = 1; i <= n; i++) {
    act(() => {
      rerender(<Leaf rows={[i]} />);
    });
  }
}

/** observer 回呼是獨立 task,要讓出主執行緒才會跑。 */
const flushObservers = (): Promise<void> => new Promise((r) => setTimeout(r, 20));

/** 模擬背景分頁的 timer 節流:setInterval 永不觸發(setTimeout 保持真,observer flush 用)。
 *  靠 setInterval 的實作在這裡會紅 —— 這正是真環境抓到的失效樣態。 */
const freezeIntervals = (): void => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
};

const measures = (): number => performance.getEntriesByType("measure").length;

async function install(maxEntries: number) {
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  dispose = installUserTimingGuard({ maxEntries });
  return dispose;
}

test("前提自檢:React dev build 每次 props 變的 re-render 都留下 measure 條目", async () => {
  await renderTimes(RENDERS);
  expect(measures()).toBeGreaterThanOrEqual(RENDERS);
});

test("SC-1 條目數達閾值後被清空(不依賴 timer,背景分頁也會跑)", async () => {
  freezeIntervals();
  await install(10);
  await renderTimes(RENDERS);
  expect(measures()).toBeGreaterThanOrEqual(10); // 自證前提:清之前真的到了閾值
  await flushObservers();
  expect(measures()).toBeLessThan(10);
});

test("SC-2 dispose 後不再清除(HMR / 測試不殘留 observer)", async () => {
  const d = await install(10);
  d();
  await renderTimes(RENDERS);
  await flushObservers();
  expect(measures()).toBeGreaterThanOrEqual(RENDERS);
});

test("SC-1 邊界:剛好 N 筆清、N-1 筆不清(閾值是 >=,不是「一有就清」)", async () => {
  await install(5);
  for (let i = 0; i < 4; i++) performance.measure(`m${i}`);
  await flushObservers();
  expect(measures()).toBe(4); // 閾值以下原封不動(review T-1)
  performance.measure("m4");
  await flushObservers();
  expect(measures()).toBe(0); // 第 5 筆觸發(review T-3:>= 不是 >)
});

test("SC-1 marks 一併清(測試內自己製造 mark,不靠環境)", async () => {
  await install(3);
  performance.mark("a");
  performance.mark("b");
  for (let i = 0; i < 3; i++) performance.measure(`m${i}`);
  await flushObservers();
  expect(performance.getEntriesByType("mark").length).toBe(0);
});

test("降級:缺 PerformanceObserver 時 install 不拋、dispose 可呼叫", async () => {
  vi.stubGlobal("PerformanceObserver", undefined);
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  let d: (() => void) | undefined;
  expect(() => {
    d = installUserTimingGuard({ maxEntries: 10 });
  }).not.toThrow();
  expect(() => d?.()).not.toThrow();
});

test("降級:observe({type}) 拋 TypeError(Level-1 實作)時 install 不拋、回 no-op", async () => {
  class ThrowingPO {
    observe(): void {
      throw new TypeError("entryTypes required");
    }
    disconnect(): void {}
  }
  vi.stubGlobal("PerformanceObserver", ThrowingPO);
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  let d: (() => void) | undefined;
  expect(() => {
    d = installUserTimingGuard({ maxEntries: 10 });
  }).not.toThrow();
  expect(() => d?.()).not.toThrow();
});

test("冪等:重複 install 不疊加 observer —— 任一 dispose 即解除", async () => {
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  const d1 = installUserTimingGuard({ maxEntries: 5 });
  const d2 = installUserTimingGuard({ maxEntries: 5 });
  dispose = d2;
  d1();
  for (let i = 0; i < 8; i++) performance.measure(`m${i}`);
  await flushObservers();
  expect(measures()).toBe(8); // 疊加版會被第二個 observer 清成 0
});
