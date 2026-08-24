import { describe, expect, it } from "vitest";

import { dropTargetFromPointer, type DropZone } from "@/lib/list-drag";

// 🟢 round4 項 2:群組全列出後可跨群組拖曳(user 拍板「移動」語意 — 來源移除)
const ROW = 44;
const BOUNDS = { left: 0, right: 240 };

/** 主力(2 檔,展開)/ 觀察(1 檔,折疊)/ 空組(0 檔,展開) */
const ZONES: DropZone[] = [
  { group: "主力", top: 0, bottom: 120, listTop: 32, count: 2, collapsed: false },
  { group: "觀察", top: 130, bottom: 160, listTop: 160, count: 1, collapsed: true },
  { group: "空組", top: 170, bottom: 220, listTop: 202, count: 0, collapsed: false },
];

describe("dropTargetFromPointer", () => {
  it("命中所在群組,index 依列高換算(上界是 count 不是 count−1,跨組要能 append)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 32 }, ZONES, ROW, BOUNDS)).toEqual({
      group: "主力",
      index: 0,
    });
    expect(dropTargetFromPointer({ x: 100, y: 32 + ROW }, ZONES, ROW, BOUNDS)).toEqual({
      group: "主力",
      index: 1,
    });
    // 落在最後一列下半 → append 到尾(index === count)
    expect(dropTargetFromPointer({ x: 100, y: 119 }, ZONES, ROW, BOUNDS)).toEqual({
      group: "主力",
      index: 2,
    });
  });

  it("折疊的群組仍是落點,index 恆為 count(append 到尾)", () => {
    // ⚠ 這條是 review R4:若沿用 listTop = bottom 的算式,y − listTop 為負 → clamp 成 0
    // (prepend),與語意相反。折疊必須是明確分支。
    expect(dropTargetFromPointer({ x: 100, y: 140 }, ZONES, ROW, BOUNDS)).toEqual({
      group: "觀察",
      index: 1,
    });
  });

  it("展開的空群組 → index 0", () => {
    expect(dropTargetFromPointer({ x: 100, y: 200 }, ZONES, ROW, BOUNDS)).toEqual({
      group: "空組",
      index: 0,
    });
  });

  it("落在群組之間的縫隙 → 取最近的群組(拖到標題列間不失敗)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 122 }, ZONES, ROW, BOUNDS)?.group).toBe("主力");
    expect(dropTargetFromPointer({ x: 100, y: 129 }, ZONES, ROW, BOUNDS)?.group).toBe("觀察");
  });

  it("x 落在側欄水平範圍外 → null(不可逆的搬組不能因為 y 剛好同高就發生)", () => {
    expect(dropTargetFromPointer({ x: 900, y: 32 }, ZONES, ROW, BOUNDS)).toBeNull();
    expect(dropTargetFromPointer({ x: -100, y: 32 }, ZONES, ROW, BOUNDS)).toBeNull();
    // ±16px 寬容:貼著側欄邊緣放開仍算有效
    expect(dropTargetFromPointer({ x: 250, y: 32 }, ZONES, ROW, BOUNDS)?.group).toBe("主力");
  });

  it("沒有任何 zone → null", () => {
    expect(dropTargetFromPointer({ x: 100, y: 32 }, [], ROW, BOUNDS)).toBeNull();
  });

  // 🔴 B10(SC-1):sticky 搜尋區下緣以上 = 作廢帶。舊行為是「在所有 zone 上方 → 取最上
  // 的 zone」,所以游標停在搜尋框上放開會靜默把股票搬到第一組 index 0(不可逆的移動語意)。
  it("y 在作廢帶內(< voidBelowY)→ null(拖到 sticky 搜尋區放開 = 整個作廢)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 39 }, ZONES, ROW, BOUNDS, 40)).toBeNull();
    // 作廢帶向上無界:側欄上方(負座標)照樣作廢
    expect(dropTargetFromPointer({ x: 100, y: -5 }, ZONES, ROW, BOUNDS, 40)).toBeNull();
  });

  it("y 恰等於 voidBelowY → 照舊取最近 zone(邊界是 `<` 不是 `<=`)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 40 }, ZONES, ROW, BOUNDS, 40)).toEqual({
      group: "主力",
      index: 0,
    });
  });

  it("未傳 voidBelowY → 四參數行為位元不變(W1)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 39 }, ZONES, ROW, BOUNDS)).toEqual({
      group: "主力",
      index: 0,
    });
  });

  // 🔴 N097(作廢帶下緣鏡像):側欄最後一組**下方的空白區**放開,舊行為是「在所有 zone
  // 下方 → 取最近的 zone」= 靜默 append 到最後一組(不可逆的移動語意),與 sticky 區
  // 那頭同一個 bug 的鏡像。`voidAboveY` = 最後一個 section 的 bottom + 一列高度容差。
  it("y 在最後一組下方的空白區(> voidAboveY)→ null", () => {
    // ZONES 最後一組 bottom = 220 → voidAboveY = 220 + ROW = 264
    expect(dropTargetFromPointer({ x: 100, y: 300 }, ZONES, ROW, BOUNDS, undefined, 264)).toBeNull();
  });

  it("y 恰等於 voidAboveY → 照舊取最近 zone(邊界是 `>` 不是 `>=`)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 264 }, ZONES, ROW, BOUNDS, undefined, 264)).toEqual({
      group: "空組",
      index: 0,
    });
  });

  it("未傳 voidAboveY → 五參數行為位元不變(W1;下方空白仍落最後一組)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 300 }, ZONES, ROW, BOUNDS, 40)).toEqual({
      group: "空組",
      index: 0,
    });
  });

  it("兩條作廢帶並存 → 各自生效(上緣 sticky / 下緣空白區)", () => {
    expect(dropTargetFromPointer({ x: 100, y: 10 }, ZONES, ROW, BOUNDS, 40, 264)).toBeNull();
    expect(dropTargetFromPointer({ x: 100, y: 300 }, ZONES, ROW, BOUNDS, 40, 264)).toBeNull();
    expect(dropTargetFromPointer({ x: 100, y: 200 }, ZONES, ROW, BOUNDS, 40, 264)?.group).toBe(
      "空組",
    );
  });

  // 未分組區塊也是一個 drop zone,用 `group: null` 表示(round5 §🔴-8)
  it("group 為 null 的 zone(未分組)→ 回 { group: null, index }", () => {
    const zones: DropZone[] = [
      { group: null, top: 0, bottom: 120, listTop: 24, count: 2, collapsed: false },
    ];
    expect(dropTargetFromPointer({ x: 100, y: 68 }, zones, ROW, BOUNDS)).toEqual({
      group: null,
      index: 1,
    });
  });
});
