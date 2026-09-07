// spec #192 取證用:vite preview 把 /api、/ws proxy 到 fake_server.py(8899)而不是 prod 8721。
// 跑法(frontend/):npx vite preview --config ../.claude/mod/signal-shadow-policies/evidence/vite.sidecar.config.ts --port 4174
// `root` 自本檔位置自我定位(review F-05 / F-06:原本寫死已收掉的 worktree 路徑,且與「複製到 frontend/ 跑」互斥)
import { fileURLToPath } from "node:url";

import { mergeConfig } from "vite";

import base from "../../../../frontend/vite.config";

const SIDECAR = "http://127.0.0.1:8899";

export default mergeConfig(base, {
  root: fileURLToPath(new URL("../../../../frontend", import.meta.url)),
  preview: {
    proxy: {
      "/api": SIDECAR,
      "/ws": { target: SIDECAR, ws: true },
    },
  },
});
