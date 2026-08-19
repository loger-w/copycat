// @vitest-environment jsdom
/** dev-only User Timing guard(2026-08-19 /bug react-dev-measure-leak)。
 *
 *  React 19.2 development build 的 Component Performance Track 對每個「props identity 變了」的
 *  re-render 打一筆 `performance.measure`;Chrome 的 User Timing buffer 沒上限、不在 V8 heap、
 *  不自動回收 → 看盤 632 筆/秒 ≈ 1.1 MB/s,數小時後 renderer Aw Snap。guard 定期清掉。
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

async function renderTimes(n: number): Promise<void> {
  const { act, render } = await import("@testing-library/react");
  const { rerender } = render(<Leaf rows={[0]} />);
  for (let i = 1; i <= n; i++) {
    act(() => {
      rerender(<Leaf rows={[i]} />);
    });
  }
}

test("前提自檢:React dev build 每次 props 變的 re-render 都留下 measure 條目", async () => {
  await renderTimes(20);
  expect(performance.getEntriesByType("measure").length).toBeGreaterThan(0);
});

test("SC-1 guard 安裝後,React 留下的 measure / mark 條目被定期清空", async () => {
  vi.useFakeTimers();
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  const dispose = installUserTimingGuard({ intervalMs: 10_000 });
  await renderTimes(20);
  expect(performance.getEntriesByType("measure").length).toBeGreaterThan(0);
  vi.advanceTimersByTime(10_000);
  expect(performance.getEntriesByType("measure").length).toBe(0);
  expect(performance.getEntriesByType("mark").length).toBe(0);
  dispose();
});

test("SC-2 dispose 後不再清除(HMR / unmount 不殘留 timer)", async () => {
  vi.useFakeTimers();
  const { installUserTimingGuard } = await import("@/lib/dev-perf-guard");
  const dispose = installUserTimingGuard({ intervalMs: 10_000 });
  dispose();
  await renderTimes(20);
  const n = performance.getEntriesByType("measure").length;
  expect(n).toBeGreaterThan(0);
  vi.advanceTimersByTime(30_000);
  expect(performance.getEntriesByType("measure").length).toBe(n);
});
