import { describe, expect, it } from "vitest";

import { CHART_FRAME, svgBox } from "@/lib/chart-frame";

/** T-10a:svgBox 換算(change-spec R-2b)。元件層的 dims regression 在 T-10b。 */

const VB_W = 800;

describe("svgBox", () => {
  it("量測為 0(首次 paint / jsdom 無 ResizeObserver)→ usable:false", () => {
    expect(svgBox({ width: 0, height: 0 }, VB_W).usable).toBe(false);
    expect(svgBox({ width: 1200, height: 0 }, VB_W).usable).toBe(false);
    expect(svgBox({ width: 0, height: 600 }, VB_W).usable).toBe(false);
  });

  it("renderPx 扣掉 figure 的 padding / border / 頂列 / 底列", () => {
    const chrome =
      CHART_FRAME.padY + CHART_FRAME.border + CHART_FRAME.topRow + CHART_FRAME.bottomRow;
    const box = svgBox({ width: 1200, height: 600 }, VB_W);
    // 安全邊 −2:誤差方向恆為「略短」而非溢出(<main> 才不會長出捲軸)
    expect(box.renderPx).toBe(600 - chrome - 2);
    expect(box.usable).toBe(true);
  });

  it("renderPx 不得超過可用高(否則 <main> 會出捲軸)", () => {
    for (const h of [200, 337, 500, 900, 1400]) {
      const box = svgBox({ width: 1200, height: h }, VB_W);
      expect(box.renderPx).toBeLessThanOrEqual(h);
    }
  });

  it("viewBoxHeight = renderPx ÷ (svg 實際寬 ÷ viewBox 寬)", () => {
    // svg 實寬 = wrapper 寬 − p-4 左右 − border 左右
    const svgW = 1200 - CHART_FRAME.padX - CHART_FRAME.border;
    const box = svgBox({ width: 1200, height: 600 }, VB_W);
    expect(box.viewBoxHeight).toBe(Math.round(box.renderPx / (svgW / VB_W)));
  });

  it("容器寬扣掉 padding/border 後為負 → usable:false(不可算出負的 viewBox 高)", () => {
    // 自選側欄很寬 / 視窗極窄時圖表區可能只剩 20px;少了這條 guard,
    // s 會是負值 → viewBox="0 0 800 -N",SVG 屬性不合法(self-review B3)
    const box = svgBox({ width: 20, height: 600 }, VB_W);
    expect(box.usable).toBe(false);
    expect(box.viewBoxHeight).toBe(0);
    expect(svgBox({ width: CHART_FRAME.padX + CHART_FRAME.border, height: 600 }, VB_W).usable).toBe(
      false,
    );
  });

  it("極矮視窗夾制到 minPx,不讓 viewBox 高度趨零", () => {
    const box = svgBox({ width: 1200, height: 60 }, VB_W, 180);
    expect(box.renderPx).toBe(180);
    expect(box.viewBoxHeight).toBeGreaterThan(0);
  });

  it("同一份 chrome 常數 → 兩張圖扣的項相同(W-12 由建構保證)", () => {
    // 兩張圖只差 viewBox 寬,可用高相同時 renderPx 必須逐像素相同
    expect(svgBox({ width: 1200, height: 600 }, 800).renderPx).toBe(
      svgBox({ width: 1200, height: 600 }, 1400).renderPx,
    );
  });
});
