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

afterEach(() => {
  vi.useRealTimers();
  performance.clearMeasures();
  performance.clearMarks();
});

/** 模擬背景分頁的 timer 節流:setInterval 永不觸發(setTimeout 保持真,observer flush 用)。
 *  靠 setInterval 的實作在這裡會紅 —— 這正是真環境抓到的失效樣態。 */
const freezeIntervals = (): void => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
};

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

test("前提自檢:React dev build 每次 props 變的 re-render 都留下 measure 條目", async () => {
  await renderTimes(20);
  expect(performance.getEntriesByType("measure").length).toBeGreaterThan(20);
});

test("SC-1 條目數達閾值後被清空(不依賴 timer,背景分頁也會跑)", async () => {
  freezeIntervals();
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  const dispose = installUserTimingGuard({ maxEntries: 10 });
  await renderTimes(20);
  await flushObservers();
  expect(performance.getEntriesByType("measure").length).toBeLessThan(10);
  expect(performance.getEntriesByType("mark").length).toBe(0);
  dispose();
});

test("SC-2 dispose 後不再清除(HMR / 測試不殘留 observer)", async () => {
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  const dispose = installUserTimingGuard({ maxEntries: 10 });
  dispose();
  await renderTimes(20);
  await flushObservers();
  expect(performance.getEntriesByType("measure").length).toBeGreaterThan(20);
});
