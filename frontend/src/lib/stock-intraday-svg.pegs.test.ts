import { describe, expect, it } from "vitest";

import { EDGE_LABEL_H, pegLabels, type PegInput } from "@/lib/stock-intraday-svg";

/** 域外疊線掛牌的定位(change-spec R4 §3.1)。
 *
 *  掛牌是「CDP 落在對稱域外」時的**唯一**訊號(KR-1)—— 線體不畫,只剩右緣這行字。
 *  定位純函式獨立測:元件層只驗「有沒有掛出來、與 MA 讓位」,堆疊次序 / 界的夾制
 *  在那裡看不出來(y 是 svg 屬性字串,矮圖疊印與正常堆疊在 DOM 上長得一樣)。
 *
 *  刻意不寫進 `stock-intraday-svg.test.ts`:那一檔是 SC-5 的「個股零變化」白名單,
 *  本輪一字不動才證明得了 core 的 stock 路徑沒被碰過。 */
describe("pegLabels", () => {
  const BOUNDS = { top: 9, bottom: 241 };

  const up = (level: PegInput["level"], priceMilli: number): PegInput => ({
    level,
    priceMilli,
    dir: "up",
  });
  const down = (level: PegInput["level"], priceMilli: number): PegInput => ({
    level,
    priceMilli,
    dir: "down",
  });

  it("空輸入 → 空陣列", () => {
    expect(pegLabels([], BOUNDS)).toEqual([]);
  });

  it("up 由 top 往下、down 由 bottom 往上,各自每 EDGE_LABEL_H 疊一層;**槽位次序與價位一致**", () => {
    const out = pegLabels(
      [up("ah", 24_100_000), up("nh", 23_500_000), down("nl", 22_700_000), down("al", 22_500_000)],
      BOUNDS,
    );
    expect(out.map((p) => p.level)).toEqual(["ah", "nh", "nl", "al"]);
    // 輸入序 = `outOfDomainLevels` 的固定次序(價位由高到低)。up 側第一顆(最高)貼上緣;
    // down 側**最後一顆(最低)貼下緣**,較高的 NL 排在 AL 之上 —— 兩顆以上域下掛牌時
    // 「較低的價位畫在較高的上面」是 code review C-1 抓到的倒序,這裡鎖住語意。
    expect(out.map((p) => p.y)).toEqual([
      BOUNDS.top,
      BOUNDS.top + EDGE_LABEL_H,
      BOUNDS.bottom - EDGE_LABEL_H,
      BOUNDS.bottom,
    ]);
    const nl = out.find((p) => p.level === "nl")!;
    const al = out.find((p) => p.level === "al")!;
    expect(nl.y).toBeLessThan(al.y);
  });

  it("兩個方向各自計數,不互相推擠(up 只看 up、down 只看 down)", () => {
    const out = pegLabels([down("al", 1), up("ah", 2), down("nl", 3), up("nh", 4)], BOUNDS);
    // 輸入次序保留(文字與配色靠 level,次序只決定同向的第幾層):down 側依輸入序
    // 「最後一顆貼下緣」→ al(第一顆 down)在上、nl(第二顆 down)貼下緣
    expect(out.map((p) => p.level)).toEqual(["al", "ah", "nl", "nh"]);
    expect(out.map((p) => p.y)).toEqual([
      BOUNDS.bottom - EDGE_LABEL_H,
      BOUNDS.top,
      BOUNDS.bottom,
      BOUNDS.top + EDGE_LABEL_H,
    ]);
  });

  it("priceMilli / level / dir 原樣帶出(文字組法留在元件端)", () => {
    const [first] = pegLabels([up("ma5", 23_018_000)], BOUNDS);
    expect(first).toEqual({ level: "ma5", priceMilli: 23_018_000, dir: "up", y: BOUNDS.top });
  });

  it("矮圖:堆疊超出界一律 clamp 進界內(疊印可接受,飛出畫布 = 靜默不見)", () => {
    const out = pegLabels(
      [up("ah", 1), up("nh", 2), up("cdp", 3)],
      { top: 0, bottom: 15 },
    );
    expect(out.map((p) => p.y)).toEqual([0, 10, 15]);
    for (const p of out) {
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(15);
    }
  });

  it("界退化(top > bottom)→ 一顆都不畫(同 edgePriceLabels 的紀律)", () => {
    expect(pegLabels([up("ah", 1), down("al", 2)], { top: 30, bottom: 10 })).toEqual([]);
  });
});
