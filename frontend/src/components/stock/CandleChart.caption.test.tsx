/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CandleChart } from "@/components/stock/CandleChart";
import type { Bar } from "@/lib/candle";

/** 🔴 N026(mod/chart-label-batch):底列 figcaption 在窄容器折行溢出。
 *
 *  `h-4`(16px)是**固定高**且不可動 —— 兩個 figure(K 線 / 江波圖)的框外 chrome 逐項
 *  對稱,「切模式不跳高」(SC-6.7)靠的就是這個高度。而四段內容(`N 根 / 高 / 低 / 期間`)
 *  在 < ~320px 寬會折成兩行,第二行直接溢出壓到下方元素。
 *
 *  修法取「截字」不取「放行高」:恆一行 + 逐段省略號,四段一顆都不消失。
 *  **jsdom 不套 CSS,量不到折行**(getBoundingClientRect 恆 0)→ 這裡只鎖 class 字串,
 *  防的是漏寫;真實折行由 headless 截圖層看(frontend-conventions「class 鎖只防漏寫」)。
 *
 *  獨立檔的理由:`CandleChart.test.tsx` 內含一個歷史遺留的 NUL 位元組,git 把整檔判成
 *  binary —— 往那裡追加會讓 diff 變成「Binary files differ」而 review 看不到內容。 */
afterEach(cleanup);

const BARS: Bar[] = [
  { t: "2026-07-24", o: 100_000, h: 110_000, l: 95_000, c: 108_000, v: 10 },
  { t: "2026-07-25", o: 108_000, h: 112_000, l: 104_000, c: 105_000, v: 10 },
];

describe("CandleChart 底列 figcaption 不折行(N026)", () => {
  it("figcaption 恆一行且不外溢(whitespace-nowrap + overflow-hidden),高度仍是 h-4", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const cap = container.querySelector("figcaption")!;
    expect(cap.className).toContain("h-4"); // 對稱高度不可動
    expect(cap.className).toContain("whitespace-nowrap");
    expect(cap.className).toContain("overflow-hidden");
  });

  it("四段各自可截字(min-w-0 + truncate)—— 窄容器時省略號而不是整段擠掉", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const spans = [...container.querySelector("figcaption")!.querySelectorAll("span")];
    expect(spans.length).toBe(4);
    for (const s of spans) {
      expect(s.className).toContain("min-w-0");
      expect(s.className).toContain("truncate");
    }
  });
});
