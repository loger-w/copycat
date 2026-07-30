import { describe, expect, it } from "vitest";

import {
  addCode,
  addGroup,
  assignToGroup,
  deleteGroup,
  detachFromGroups,
  moveToGroup,
  removeCode,
  removeFromGroup,
  renameGroup,
  reorderUngrouped,
  setMembership,
  ungroupedCodes,
  type Watchlist,
} from "@/lib/watchlist-model";

const wl = (codes: string[], groups: { name: string; codes: string[] }[]): Watchlist => ({
  codes,
  groups,
});

describe("ungroupedCodes", () => {
  it("扣掉所有群組成員,保 codes 序", () => {
    const w = wl(
      ["2330", "5483", "3231", "2317"],
      [
        { name: "主力", codes: ["5483"] },
        { name: "觀察", codes: ["2317"] },
      ],
    );
    expect(ungroupedCodes(w)).toEqual(["2330", "3231"]);
  });

  it("零群組 → 全體都是未分組", () => {
    expect(ungroupedCodes(wl(["2330", "5483"], []))).toEqual(["2330", "5483"]);
  });
});

// W-19:5 個 case 逐條移植自 `list-drag.test.ts` 的 moveCode(那邊同輪刪除)。
// slot = 相對目標清單「移除前」的渲染索引(含被拖那一列)→ 該檔已在目標組時要補償 −1。
describe("moveToGroup 的槽位語意(往下拖的 off-by-one)", () => {
  const one = (codes: string[]) => wl(codes, [{ name: "G", codes }]);

  it("同組往下拖:[A,B,C,D] 拖 A 到槽 3 → BCAD(不是 BCDA)", () => {
    expect(moveToGroup(one(["A", "B", "C", "D"]), "A", "G", "G", 3).groups[0]!.codes).toEqual([
      "B",
      "C",
      "A",
      "D",
    ]);
  });

  it("同組往下拖到最尾:[A,B,C,D] 拖 A 到槽 4 → BCDA", () => {
    expect(moveToGroup(one(["A", "B", "C", "D"]), "A", "G", "G", 4).groups[0]!.codes).toEqual([
      "B",
      "C",
      "D",
      "A",
    ]);
  });

  it("同組往上拖不受影響:[A,B,C,D] 拖 D 到槽 0 → DABC", () => {
    expect(moveToGroup(one(["A", "B", "C", "D"]), "D", "G", "G", 0).groups[0]!.codes).toEqual([
      "D",
      "A",
      "B",
      "C",
    ]);
  });

  it("跨組但目標組已有該檔(W-1 一檔多組):[A,X,B,C] 拖 X 到槽 3 → ABXC", () => {
    const w = wl(
      ["X", "Z", "A", "B", "C"],
      [
        { name: "來源", codes: ["X", "Z"] },
        { name: "目標", codes: ["A", "X", "B", "C"] },
      ],
    );
    const out = moveToGroup(w, "X", "來源", "目標", 3);
    expect(out.groups[1]!.codes).toEqual(["A", "B", "X", "C"]);
    expect(out.groups[0]!.codes).toEqual(["Z"]);
  });

  it("跨組且目標組沒有該檔 → 槽即 index,不做補償:[A,B,C] 拖 X 到槽 2 → ABXC", () => {
    const w = wl(
      ["X", "A", "B", "C"],
      [
        { name: "來源", codes: ["X"] },
        { name: "目標", codes: ["A", "B", "C"] },
      ],
    );
    expect(moveToGroup(w, "X", "來源", "目標", 2).groups[1]!.codes).toEqual(["A", "B", "X", "C"]);
  });
});

describe("moveToGroup", () => {
  const base = () =>
    wl(
      ["2330", "5483", "3231"],
      [
        { name: "主力", codes: ["2330", "5483"] },
        { name: "觀察", codes: ["3231"] },
      ],
    );

  it("移動語意:來源組移除、目標組插入(不是複製)", () => {
    const out = moveToGroup(base(), "2330", "主力", "觀察", 0);
    expect(out.groups[0]!.codes).toEqual(["5483"]);
    expect(out.groups[1]!.codes).toEqual(["2330", "3231"]);
  });

  it("codes 全體不變 —— 換組不影響訂閱池", () => {
    expect(moveToGroup(base(), "2330", "主力", "觀察", 0).codes).toEqual(["2330", "5483", "3231"]);
  });

  it("slot 溢出 → clamp 到尾端", () => {
    expect(moveToGroup(base(), "2330", "主力", "觀察", 99).groups[1]!.codes).toEqual([
      "3231",
      "2330",
    ]);
  });

  it("slot 為負 → clamp 到頭", () => {
    expect(moveToGroup(base(), "2330", "主力", "觀察", -5).groups[1]!.codes).toEqual([
      "2330",
      "3231",
    ]);
  });

  it("不影響第三組(一檔多組的其他歸屬保留,W-1)", () => {
    const w = wl(
      ["2330", "3231"],
      [
        { name: "主力", codes: ["2330"] },
        { name: "觀察", codes: ["3231"] },
        { name: "旁觀", codes: ["2330"] },
      ],
    );
    expect(moveToGroup(w, "2330", "主力", "觀察", 0).groups[2]).toEqual({
      name: "旁觀",
      codes: ["2330"],
    });
  });

  it("來源組不存在該 code → 其他組不被破壞", () => {
    expect(moveToGroup(base(), "9999", "主力", "觀察", 0).groups[0]!.codes).toEqual([
      "2330",
      "5483",
    ]);
  });
});

describe("assignToGroup", () => {
  const base = () =>
    wl(["2330", "5483", "3231"], [{ name: "主力", codes: ["5483", "3231"] }]);

  it("指派後該檔離開未分組並進該組指定槽", () => {
    const out = assignToGroup(base(), "2330", "主力", 1);
    expect(out.groups[0]!.codes).toEqual(["5483", "2330", "3231"]);
    expect(ungroupedCodes(out)).toEqual([]);
  });

  it("codes 全體與順序不變(未分組是衍生集合)", () => {
    expect(assignToGroup(base(), "2330", "主力", 1).codes).toEqual(["2330", "5483", "3231"]);
  });

  it("空群組 → 落在第一列", () => {
    const out = assignToGroup(wl(["2330"], [{ name: "空組", codes: [] }]), "2330", "空組", 0);
    expect(out.groups[0]!.codes).toEqual(["2330"]);
  });
});

describe("detachFromGroups", () => {
  it("從所有群組移除(一檔多組拖進未分組不會只掉來源組)", () => {
    const w = wl(
      ["2330", "5483"],
      [
        { name: "主力", codes: ["2330", "5483"] },
        { name: "觀察", codes: ["2330"] },
      ],
    );
    const out = detachFromGroups(w, "2330", 0);
    expect(out.groups[0]!.codes).toEqual(["5483"]);
    expect(out.groups[1]!.codes).toEqual([]);
    expect(ungroupedCodes(out)).toEqual(["2330"]);
  });

  it("落點位置換算到 codes 的絕對 index:[X,C,Y] 的 C 拖到未分組槽 1 → 仍是 [X,C,Y]", () => {
    const w = wl(["X", "C", "Y"], [{ name: "G", codes: ["C"] }]);
    expect(detachFromGroups(w, "C", 1).codes).toEqual(["X", "C", "Y"]);
  });

  it("拖到未分組尾端 → 落在 codes 尾端", () => {
    const w = wl(["X", "C", "Y"], [{ name: "G", codes: ["C"] }]);
    expect(detachFromGroups(w, "C", 2).codes).toEqual(["X", "Y", "C"]);
  });
});

describe("reorderUngrouped", () => {
  it("未分組內排序套同一組 off-by-one 補償:[A,B,C,D] 拖 A 到槽 3 → BCAD", () => {
    expect(reorderUngrouped(wl(["A", "B", "C", "D"], []), "A", 3).codes).toEqual([
      "B",
      "C",
      "A",
      "D",
    ]);
  });

  it("群組成員在 codes 的相對位置不動", () => {
    const w = wl(["X", "C", "Y"], [{ name: "G", codes: ["C"] }]);
    const out = reorderUngrouped(w, "X", 2);
    expect(out.codes).toEqual(["C", "Y", "X"]);
    expect(out.groups[0]!.codes).toEqual(["C"]);
  });
});

describe("removeFromGroup", () => {
  it("只從該組移除,code 留在自選 → 回到未分組", () => {
    const w = wl(["2330", "5483"], [{ name: "主力", codes: ["2330", "5483"] }]);
    const out = removeFromGroup(w, "2330", "主力");
    expect(out.groups[0]!.codes).toEqual(["5483"]);
    expect(out.codes).toEqual(["2330", "5483"]);
    expect(ungroupedCodes(out)).toEqual(["2330"]);
  });

  it("一檔多組時只掉指定那組,仍不在未分組(W-1)", () => {
    const w = wl(
      ["2330"],
      [
        { name: "主力", codes: ["2330"] },
        { name: "觀察", codes: ["2330"] },
      ],
    );
    const out = removeFromGroup(w, "2330", "主力");
    expect(out.groups[1]!.codes).toEqual(["2330"]);
    expect(ungroupedCodes(out)).toEqual([]);
  });
});

describe("removeCode", () => {
  it("從 codes 與所有群組移除", () => {
    const w = wl(
      ["2330", "5483"],
      [
        { name: "主力", codes: ["2330"] },
        { name: "觀察", codes: ["2330", "5483"] },
      ],
    );
    const out = removeCode(w, "2330");
    expect(out.codes).toEqual(["5483"]);
    expect(out.groups[0]!.codes).toEqual([]);
    expect(out.groups[1]!.codes).toEqual(["5483"]);
  });
});

describe("addCode", () => {
  it("加到 codes 尾端,不進任何群組", () => {
    const out = addCode(wl(["2330"], [{ name: "主力", codes: ["2330"] }]), "5483");
    expect(out.codes).toEqual(["2330", "5483"]);
    expect(out.groups[0]!.codes).toEqual(["2330"]);
    expect(ungroupedCodes(out)).toEqual(["5483"]);
  });

  it("已在自選 → 原物件不動(呼叫端據此零 PUT,W-21)", () => {
    const w = wl(["2330"], []);
    expect(addCode(w, "2330")).toBe(w);
  });
});

describe("setMembership", () => {
  it("勾選 → 進該組尾端;可同時屬兩組(W-1)", () => {
    const w = wl(
      ["2330"],
      [
        { name: "主力", codes: ["2330"] },
        { name: "觀察", codes: [] },
      ],
    );
    const out = setMembership(w, "2330", "觀察", true);
    expect(out.groups[0]!.codes).toEqual(["2330"]);
    expect(out.groups[1]!.codes).toEqual(["2330"]);
  });

  it("取消勾選 → 離開該組,code 留在自選", () => {
    const w = wl(["2330"], [{ name: "主力", codes: ["2330"] }]);
    const out = setMembership(w, "2330", "主力", false);
    expect(out.groups[0]!.codes).toEqual([]);
    expect(out.codes).toEqual(["2330"]);
  });

  it("勾選已在該組的檔 → 原物件不動", () => {
    const w = wl(["2330"], [{ name: "主力", codes: ["2330"] }]);
    expect(setMembership(w, "2330", "主力", true)).toBe(w);
  });
});

describe("addGroup", () => {
  it("附加一個空群組", () => {
    expect(addGroup(wl([], []), "主力").groups).toEqual([{ name: "主力", codes: [] }]);
  });

  it("名稱空白或重名 → 原物件不動(呼叫端零 PUT)", () => {
    const w = wl([], [{ name: "主力", codes: [] }]);
    expect(addGroup(w, "  ")).toBe(w);
    expect(addGroup(w, "主力")).toBe(w);
  });
});

describe("renameGroup", () => {
  it("改名保序,成員不動", () => {
    const w = wl(["2330"], [{ name: "主力", codes: ["2330"] }, { name: "觀察", codes: [] }]);
    expect(renameGroup(w, "主力", "強勢").groups).toEqual([
      { name: "強勢", codes: ["2330"] },
      { name: "觀察", codes: [] },
    ]);
  });

  it("撞既有名或空白 → 原物件不動", () => {
    const w = wl([], [{ name: "主力", codes: [] }, { name: "觀察", codes: [] }]);
    expect(renameGroup(w, "主力", "觀察")).toBe(w);
    expect(renameGroup(w, "主力", "   ")).toBe(w);
  });
});

describe("deleteGroup", () => {
  it("只刪群組,成員留在 codes → 掉回未分組", () => {
    const w = wl(["2330", "5483"], [{ name: "主力", codes: ["2330"] }]);
    const out = deleteGroup(w, "主力");
    expect(out.groups).toEqual([]);
    expect(ungroupedCodes(out)).toEqual(["2330", "5483"]);
  });
});
