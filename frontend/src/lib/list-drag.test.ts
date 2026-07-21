import { describe, expect, it } from "vitest";

import { insertIndexFromPointer, reorder } from "@/lib/list-drag";

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
