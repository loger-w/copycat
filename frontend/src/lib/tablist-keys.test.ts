/** `tablistKeyAction` 的行為表(TC-6)。
 *
 *  兩處 tablist(App 主分頁 / RightRail)共用這一份判斷,而「其中一處漏了 Home/End」
 *  這種漂移不會有畫面訊號、也不會有測試紅 —— 所以判斷本身必須有自己的表。
 *
 *  🔴 A11Y-4:改前只吃 `key` 字串 → **Alt+←/→(瀏覽器上一頁 / 下一頁)、Ctrl+Home/End
 *  (捲到頁首 / 頁尾)被 tablist 整個吃掉**(呼叫端拿到非 null 就 `preventDefault`)。
 *  修飾鍵組合一律早退回 null,把按鍵還給瀏覽器。 */
import { describe, expect, it } from "vitest";

import { tablistKeyAction } from "@/lib/tablist-keys";

type Ev = { key: string; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean };

const CASES: [name: string, ev: Ev, index: number, count: number, want: number | "select" | null][] =
  [
    // 方向鍵:環狀移動(APG 要求首尾相接)
    ["ArrowRight 一般", { key: "ArrowRight" }, 0, 3, 1],
    ["ArrowRight 尾端環回首", { key: "ArrowRight" }, 2, 3, 0],
    ["ArrowLeft 一般", { key: "ArrowLeft" }, 2, 3, 1],
    ["ArrowLeft 首端環回尾", { key: "ArrowLeft" }, 0, 3, 2],
    ["Home 到首", { key: "Home" }, 2, 3, 0],
    ["End 到尾", { key: "End" }, 0, 3, 2],
    // manual activation:Enter / Space 才是「切換到這顆」
    ["Enter → select", { key: "Enter" }, 1, 3, "select"],
    ['" " → select', { key: " " }, 1, 3, "select"],
    // 非本組按鍵 → null(呼叫端據此**不** preventDefault)
    ["ArrowUp 不吃", { key: "ArrowUp" }, 1, 3, null],
    ["Tab 不吃", { key: "Tab" }, 1, 3, null],
    ["一般字元不吃", { key: "a" }, 1, 3, null],
    // 單顆 tab:方向鍵原地不動(不拋、不越界)
    ["count=1 ArrowRight 原地", { key: "ArrowRight" }, 0, 1, 0],
    ["count=1 ArrowLeft 原地", { key: "ArrowLeft" }, 0, 1, 0],
    // 空 tablist(渲染中 / 條件全關):不得回 -1 或 NaN 當索引用
    ["count=0 ArrowRight → null", { key: "ArrowRight" }, 0, 0, null],
    ["count=0 ArrowLeft → null", { key: "ArrowLeft" }, 0, 0, null],
    ["count=0 Home → null", { key: "Home" }, 0, 0, null],
    ["count=0 End → null", { key: "End" }, 0, 0, null],
    // 🔴 A11Y-4:修飾鍵是瀏覽器 / OS 的快捷鍵,不是 tablist 的
    ["Alt+ArrowLeft(上一頁)→ null", { key: "ArrowLeft", altKey: true }, 1, 3, null],
    ["Alt+ArrowRight(下一頁)→ null", { key: "ArrowRight", altKey: true }, 1, 3, null],
    ["Ctrl+Home(捲到頁首)→ null", { key: "Home", ctrlKey: true }, 1, 3, null],
    ["Ctrl+End(捲到頁尾)→ null", { key: "End", ctrlKey: true }, 1, 3, null],
    ["Meta+ArrowRight → null", { key: "ArrowRight", metaKey: true }, 1, 3, null],
    ["Ctrl+Enter → null", { key: "Enter", ctrlKey: true }, 1, 3, null],
  ];

describe("tablistKeyAction", () => {
  for (const [name, ev, index, count, want] of CASES) {
    it(name, () => {
      expect(tablistKeyAction(ev, index, count)).toBe(want);
    });
  }
});
