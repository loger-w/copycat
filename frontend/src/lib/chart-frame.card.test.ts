import { describe, expect, it } from "vitest";

import { CARD_CHROME, cardSvgBox } from "@/lib/chart-frame";

/** 群組卡片變體的尺度換算(change-spec AD-3)。
 *
 *  卡片與單檔頁的模型不同:單檔頁是「viewBox 寬固定 800、反解 viewBox 高」,
 *  卡片是**1:1**(viewBox 寬 = 量到的 px 寬),讓 svg 內的 rem 字級與單檔頁同量級 ——
 *  800 寬的 viewBox 掛進 250px 卡片,0.5625rem 的刻度會縮成 3px。 */

describe("cardSvgBox", () => {
  it("量測為 0 / 可用高 ≤ 0 → usable:false(量到之前不畫圖)", () => {
    expect(cardSvgBox({ width: 0, height: 200 }).usable).toBe(false);
    expect(cardSvgBox({ width: -1, height: 200 }).usable).toBe(false);
    // 高度只夠 readout 列 + 安全邊 → 沒有畫圖的空間
    expect(cardSvgBox({ width: 240, height: CARD_CHROME.readoutRow + 2 }).usable).toBe(false);
    expect(cardSvgBox({ width: 240, height: 0 }).usable).toBe(false);
  });

  it("width = 量到的 px 寬(1:1,四捨五入成整數)", () => {
    expect(cardSvgBox({ width: 246.4, height: 200 }).width).toBe(246);
    expect(cardSvgBox({ width: 246.6, height: 200 }).width).toBe(247);
  });

  it("主 + 副圖高相加 = 可用高(減法拆,不會因四捨五入溢出軌道)", () => {
    for (const h of [120, 173, 224, 300, 451]) {
      const box = cardSvgBox({ width: 250, height: h });
      const usable = h - CARD_CHROME.readoutRow - 2;
      expect(box.mainH + box.subH).toBe(usable);
      expect(box.usable).toBe(true);
    }
  });

  it("主 : 副 = 260 : 330(與單檔頁 MAIN/SUB 同比例)", () => {
    const usable = 330;
    const box = cardSvgBox({ width: 250, height: usable + CARD_CHROME.readoutRow + 2 });
    expect(box.mainH).toBe(260);
    expect(box.subH).toBe(70);
  });

  it("readoutRow = h-[1.375rem](22)+ mb-1(4)—— 與 CHART_FRAME.topRow 同一份口徑", () => {
    expect(CARD_CHROME.readoutRow).toBe(26);
  });

  it("usable:false 時尺寸全為 0(呼叫端拿去畫也不會生出負的 viewBox)", () => {
    const box = cardSvgBox({ width: 0, height: 0 });
    expect(box.width).toBe(0);
    expect(box.mainH).toBe(0);
    expect(box.subH).toBe(0);
  });
});
