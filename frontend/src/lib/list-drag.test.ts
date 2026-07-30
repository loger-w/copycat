import { describe, expect, it } from "vitest";

import {
  dropTargetFromPointer,
  insertIndexFromPointer,
  moveCode,
  reorder,
  type DropZone,
} from "@/lib/list-drag";

describe("reorder", () => {
  it("moves item forward and backward", () => {
    expect(reorder(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
    expect(reorder(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
  });

  it("same index is identity", () => {
    expect(reorder(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });

  it("out of range clamps", () => {
    expect(reorder(["a", "b"], 0, 99)).toEqual(["b", "a"]);
  });
});

describe("insertIndexFromPointer", () => {
  it("maps pointer y to row index by row height", () => {
    expect(insertIndexFromPointer(0, 40, 5)).toBe(0);
    expect(insertIndexFromPointer(59, 40, 5)).toBe(1); // 過半行高 → 下一格
    expect(insertIndexFromPointer(199, 40, 5)).toBe(4);
  });

  it("clamps to list bounds", () => {
    expect(insertIndexFromPointer(-10, 40, 5)).toBe(0);
    expect(insertIndexFromPointer(9999, 40, 5)).toBe(4);
  });
});

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
});

describe("moveCode", () => {
  const GROUPS = [
    { name: "主力", codes: ["2330", "5483"] },
    { name: "觀察", codes: ["3231"] },
    { name: "旁觀", codes: ["1101"] },
  ];

  it("跨組 = 移動:來源移除、目標依 index 插入", () => {
    expect(moveCode(GROUPS, "2330", "主力", "觀察", 0)).toEqual([
      { name: "主力", codes: ["5483"] },
      { name: "觀察", codes: ["2330", "3231"] },
      { name: "旁觀", codes: ["1101"] },
    ]);
  });

  it("跨組 append(index === count)", () => {
    expect(moveCode(GROUPS, "2330", "主力", "觀察", 1)[1]).toEqual({
      name: "觀察",
      codes: ["3231", "2330"],
    });
  });

  it("同組 = 重排(不重複、不消失)", () => {
    expect(moveCode(GROUPS, "2330", "主力", "主力", 2)[0]).toEqual({
      name: "主力",
      codes: ["5483", "2330"],
    });
  });

  it("目標組已含該 code → 不重複(移動到已存在的組等於只從來源移除)", () => {
    const groups = [
      { name: "主力", codes: ["2330", "5483"] },
      { name: "觀察", codes: ["2330"] },
    ];
    expect(moveCode(groups, "2330", "主力", "觀察", 0)).toEqual([
      { name: "主力", codes: ["5483"] },
      { name: "觀察", codes: ["2330"] },
    ]);
  });

  it("index 溢出 → 夾制", () => {
    expect(moveCode(GROUPS, "2330", "主力", "觀察", 99)[1]!.codes).toEqual(["3231", "2330"]);
    expect(moveCode(GROUPS, "2330", "主力", "觀察", -5)[1]!.codes).toEqual(["2330", "3231"]);
  });

  it("不影響第三組(一檔多組的其他歸屬保留)", () => {
    const groups = [
      { name: "主力", codes: ["2330"] },
      { name: "觀察", codes: ["3231"] },
      { name: "旁觀", codes: ["2330"] },
    ];
    expect(moveCode(groups, "2330", "主力", "觀察", 0)[2]).toEqual({
      name: "旁觀",
      codes: ["2330"],
    });
  });

  it("來源組不存在該 code → 其他組不被破壞", () => {
    expect(moveCode(GROUPS, "9999", "主力", "觀察", 0)[0]).toEqual({
      name: "主力",
      codes: ["2330", "5483"],
    });
  });
});
