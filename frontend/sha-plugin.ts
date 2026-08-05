/// <reference types="node" />
/** build sha 的取得與 dev server 曝露(SC-1 / SC-6)。
 *
 *  抽成獨立檔而非寫在 vite.config.ts 內,是為了可測(design R2):測試 import 這裡
 *  不會連帶執行 defineConfig。vite.config.ts 只負責接線。
 */
import type { Plugin } from "vite";

import { execSync } from "node:child_process";

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

/** dev server 專屬的 `/__build/sha`:**每請求現算**當下 HEAD(design R1)。
 *
 *  現算是這條路徑存在的全部理由 —— dev 下 HMR 已把新 code 送進瀏覽器,凍結的
 *  define(啟動時求值)會讓「commit 後忘了重啟後端」變成反向誤報:前端顯示舊 sha、
 *  後端是新 sha,方向剛好相反。middleware 只存在於 dev server,build 產物打這條會
 *  404 → useFrontendSha 降級回 define 常數。
 */
export function buildShaPlugin(): Plugin {
  return {
    name: "copycat-build-sha",
    configureServer(server) {
      server.middlewares.use("/__build/sha", (_req, res) => {
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ git_sha: gitSha() }));
      });
    },
  };
}
