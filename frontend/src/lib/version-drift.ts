/** 前後端版本落差判定(SC-3)。 */

export interface Drift {
  fe: string;
  be: string;
}

/** 兩邊 sha 皆可得且不等 → 落差;任一不可得(null / undefined / 空字串)→ null。
 *
 *  「不可得就不判定」是刻意的:沒有 sha 代表不知道,不是代表不同。誤報一次就會讓
 *  這顆膠囊被當雜訊無視,之後真的落差也不會有人看。 */
export function versionDrift(
  fe: string | null | undefined,
  be: string | null | undefined,
): Drift | null {
  if (!fe || !be) return null;
  return fe === be ? null : { fe, be };
}

/** vite `define` 注入的 bundle sha;缺席或空值回 null。
 *
 *  **延遲求值**(design R2):寫成 module 頂層 const 會在 import 當下凍結,測試就
 *  無法用 `vi.stubGlobal("__GIT_SHA__", …)` 換值(vitest 把 define 當 globalThis 屬性
 *  注入)。`typeof` 守衛是為了 define 完全缺席時不拋 ReferenceError。 */
export function frontendSha(): string | null {
  return typeof __GIT_SHA__ === "undefined" ? null : __GIT_SHA__ || null;
}
