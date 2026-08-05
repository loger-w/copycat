/** 版本落差判定純函數(SC-3)+ 前端 sha 延遲求值接縫(design R2)。 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { frontendSha, versionDrift } from "@/lib/version-drift";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("versionDrift(SC-3 判定表)", () => {
  it("兩者皆非空且不等 → 落差物件", () => {
    expect(versionDrift("aaaaaaa", "bbbbbbb")).toEqual({ fe: "aaaaaaa", be: "bbbbbbb" });
  });

  it("兩者相等 → null(健康態零 DOM)", () => {
    expect(versionDrift("aaaaaaa", "aaaaaaa")).toBeNull();
  });

  it("前端 sha 不可得 → null(不誤報)", () => {
    expect(versionDrift(null, "bbbbbbb")).toBeNull();
    expect(versionDrift(undefined, "bbbbbbb")).toBeNull();
  });

  it("後端 sha 不可得 → null(不誤報)", () => {
    expect(versionDrift("aaaaaaa", null)).toBeNull();
    expect(versionDrift("aaaaaaa", undefined)).toBeNull();
  });

  it("空字串視同不可得(git 失敗時後端回空字串也不該亮燈)", () => {
    expect(versionDrift("", "bbbbbbb")).toBeNull();
    expect(versionDrift("aaaaaaa", "")).toBeNull();
    expect(versionDrift("", "")).toBeNull();
  });
});

describe("frontendSha(R2:延遲求值,不在 module 頂層凍結)", () => {
  it("讀當下的 __GIT_SHA__ 全域值", () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    expect(frontendSha()).toBe("aaaaaaa");
  });

  it("define 為 null(git 不可得)→ null", () => {
    vi.stubGlobal("__GIT_SHA__", null);
    expect(frontendSha()).toBeNull();
  });

  it("define 為空字串 → null(與 null 同語意)", () => {
    vi.stubGlobal("__GIT_SHA__", "");
    expect(frontendSha()).toBeNull();
  });

  it("未 stub 時取 vite define 注入值:null 或短 sha,且不拋(define 缺席也要活)", () => {
    const sha = frontendSha();
    if (sha !== null) expect(sha).toMatch(/^[0-9a-f]{7,12}$/);
  });
});
