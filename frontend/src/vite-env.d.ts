/// <reference types="vite/client" />

/** vite.config.ts `define` 注入的 build sha(git 不可得時為 null)。
 *  讀取一律經 `lib/version-drift.ts` 的 `frontendSha()`,別直接用。 */
declare const __GIT_SHA__: string | null;
