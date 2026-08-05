/// <reference types="node" />
/** build sha 的取得與 dev server 曝露(SC-1 / SC-6)。
 *
 *  抽成獨立檔而非寫在 vite.config.ts 內,是為了可測(design R2):測試 import 這裡
 *  不會連帶執行 defineConfig。vite.config.ts 只負責接線。
 */
import type { Plugin } from "vite";

import { execFileSync, execSync } from "node:child_process";

/** 與後端 `build_info._git` 同一套降級紀律:timeout 3s、stderr 靜默、任何失敗回 null。
 *  非 git checkout / 沒裝 git / repo 損毀都不該讓 dev server 或 build 掛掉。 */
export function gitSha(): string | null {
  try {
    return (
      execSync("git rev-parse --short HEAD", {
        encoding: "utf8",
        timeout: 3000,
        stdio: ["ignore", "pipe", "ignore"],
      }).trim() || null
    );
  } catch {
    return null;
  }
}

/** since 白名單:只收 hex(短 sha 到完整 sha)。連 `HEAD` 這種合法 revision 名都不放行 ——
 *  這個參數來自 HTTP query,值域窄到只剩「後端回報的 sha」才是它該有的樣子。 */
const SHA_RE = /^[0-9a-f]{4,40}$/i;

/** `since..HEAD` 之間 **`copycat/` 底下**是否還有 commit(design C3)。
 *
 *  = CLAUDE.md §8「跑著的 server 是哪一版」那條 `git log <git_sha>..HEAD -- copycat/`
 *  的完整自動化。**路徑過濾是重點**:少了它,純前端 / docs 的 commit 也會亮燈,在本
 *  repo 的工作流下膠囊近乎恆亮 = 雜訊化。
 *
 *  三態:true(後端落後,該重啟)/ false(同步)/ **null = 不判定**(since 缺席或非法、
 *  git 失敗)。null 不是 false —— 不知道就別下結論。
 *
 *  `execFileSync` 陣列參數不經 shell;`:/copycat` 是 git 的 top-level magic pathspec,
 *  **不可寫成 `copycat`** —— vite 的 cwd 是 `frontend/`,相對 pathspec 會解成
 *  `frontend/copycat`(不存在)→ git 正常結束、輸出為空 → 恆回 false 的靜默失效。 */
export function behindSince(since: string | null | undefined): boolean | null {
  if (!since || !SHA_RE.test(since)) return null;
  try {
    const out = execFileSync("git", ["log", "--format=%h", `${since}..HEAD`, "--", ":/copycat"], {
      encoding: "utf8",
      timeout: 3000,
      stdio: ["ignore", "pipe", "ignore"],
    });
    return out.trim().length > 0;
  } catch {
    return null;
  }
}

/** dev server 專屬的 `/__build/sha`:**每請求現算**當下 HEAD 與 range 判別(design R1/C3)。
 *
 *  現算是這條路徑存在的全部理由 —— dev 下 HMR 已把新 code 送進瀏覽器,凍結的
 *  define(啟動時求值)會讓「commit 後忘了重啟後端」變成反向誤報:前端顯示舊 sha、
 *  後端是新 sha,方向剛好相反。middleware 只存在於 dev server,build 產物打這條會
 *  404 → 前端降級回 define 常數的等值比對。
 */
export function buildShaPlugin(): Plugin {
  return {
    name: "copycat-build-sha",
    configureServer(server) {
      server.middlewares.use("/__build/sha", (req, res) => {
        // connect 會把 mount 路徑從 req.url 剝掉、留下 query;base 只為了讓 URL 可解析
        const since = new URL(req.url ?? "/", "http://localhost").searchParams.get("since");
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ git_sha: gitSha(), behind: behindSince(since) }));
      });
    },
  };
}
