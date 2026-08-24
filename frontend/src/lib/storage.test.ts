/** @vitest-environment jsdom */
/** `lib/storage.ts` — 全站 localStorage 的唯一出口(N022)。
 *
 *  這裡守的是**兩個失效面**,兩者都會讓整頁白屏(全 frontend 零 ErrorBoundary):
 *  (a) Safari 私密視窗 / 企業政策鎖 storage 時,**光是存取**就拋(讀取端住在
 *      `useState` 的 lazy initializer 裡 = render 路徑上);
 *  (b) 配額滿時 `setItem` 拋 `QuotaExceededError`(使用者操作中途炸掉)。
 *
 *  另外釘住「警告只發一次」:讀取端一秒可以被呼叫幾十次,每次一則 warn 會把
 *  console 洗到沒人看 —— 但完全靜默又違反「不吞錯誤」的鐵則,故 module 級旗標。 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type StorageMod = typeof import("@/lib/storage");

const KEY = "copycat-test-key";

/** 每個 it 重新載入模組。**警告旗標是 module 級**(「只警告一次」正是被測的行為),
 *  沿用同一份 module 的話第二個 it 起恆不警告,`toHaveBeenCalledTimes(1)` 會靜默
 *  變成 vacuous(量到的是上一個 it 的殘留而不是本次)。 */
async function fresh(): Promise<StorageMod> {
  vi.resetModules();
  return await import("@/lib/storage");
}

function throwOnAccess(method: "getItem" | "setItem" | "removeItem"): void {
  vi.spyOn(Storage.prototype, method).mockImplementation(() => {
    throw new DOMException("The operation is insecure.", "SecurityError");
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  // spy 還原放 afterEach:斷言先炸時主體末尾的 restore 永遠不會執行,
  // Storage.prototype 的 spy 會漏到後續測試(LimitListSection.test.tsx review A-2)。
  vi.restoreAllMocks();
});

describe("readLocal", () => {
  it("讀得到寫進去的字面值;未設回 null(getItem 的契約逐字沿用)", async () => {
    const { readLocal } = await fresh();
    expect(readLocal(KEY)).toBeNull();
    window.localStorage.setItem(KEY, "hello");
    expect(readLocal(KEY)).toBe("hello");
  });

  it("存取即拋 → 回 null,不往外拋(白屏的根因)", async () => {
    const { readLocal } = await fresh();
    throwOnAccess("getItem");
    expect(() => readLocal(KEY)).not.toThrow();
    expect(readLocal(KEY)).toBeNull();
  });

  it("連續讀取失敗只 console.warn 一次(不吞成靜默,也不洗版)", async () => {
    const { readLocal } = await fresh();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    throwOnAccess("getItem");
    readLocal(KEY);
    readLocal(KEY);
    readLocal("copycat-another");
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.[0])).toContain("storage");
  });
});

describe("writeLocal", () => {
  it("成功 → 回 true 且值逐字進得去", async () => {
    const { writeLocal } = await fresh();
    expect(writeLocal(KEY, "v1")).toBe(true);
    expect(window.localStorage.getItem(KEY)).toBe("v1");
  });

  it("QuotaExceededError → 回 false,不往外拋", async () => {
    const { writeLocal } = await fresh();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    let ok: boolean | null = null;
    expect(() => {
      ok = writeLocal(KEY, "v1");
    }).not.toThrow();
    expect(ok).toBe(false);
  });

  it("連續寫入失敗只 console.warn 一次,且與讀取的旗標各自獨立", async () => {
    const { readLocal, writeLocal } = await fresh();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    throwOnAccess("getItem");
    readLocal(KEY);
    expect(warn).toHaveBeenCalledTimes(1);

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    writeLocal(KEY, "v1");
    writeLocal(KEY, "v2");
    // 讀 1 + 寫 1;共用同一個旗標的話這裡會是 1
    expect(warn).toHaveBeenCalledTimes(2);
  });
});

describe("removeLocal", () => {
  it("成功 → 回 true 且鍵消失", async () => {
    const { removeLocal } = await fresh();
    window.localStorage.setItem(KEY, "v1");
    expect(removeLocal(KEY)).toBe(true);
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("存取即拋 → 回 false,不往外拋", async () => {
    const { removeLocal } = await fresh();
    throwOnAccess("removeItem");
    let ok: boolean | null = null;
    expect(() => {
      ok = removeLocal(KEY);
    }).not.toThrow();
    expect(ok).toBe(false);
  });
});

describe("readLocalJson", () => {
  it("合法 JSON → 解出來的值", async () => {
    const { readLocalJson } = await fresh();
    window.localStorage.setItem(KEY, JSON.stringify(["TWN", "SPX"]));
    expect(readLocalJson(KEY)).toEqual(["TWN", "SPX"]);
  });

  it("未設 / 空字串 / 壞 JSON / 字面 `null` 一律回 null(呼叫端只有一條退預設路徑)", async () => {
    const { readLocalJson } = await fresh();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(readLocalJson(KEY)).toBeNull();
    for (const raw of ["", "{not json", "null"]) {
      window.localStorage.setItem(KEY, raw);
      expect(readLocalJson(KEY)).toBeNull();
    }
  });

  it("存取即拋 → null,不往外拋", async () => {
    const { readLocalJson } = await fresh();
    throwOnAccess("getItem");
    expect(() => readLocalJson(KEY)).not.toThrow();
    expect(readLocalJson(KEY)).toBeNull();
  });
});
