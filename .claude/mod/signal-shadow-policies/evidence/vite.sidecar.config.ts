// spec #192 取證用:vite preview 把 /api、/ws proxy 到 fake_server.py(8899)而不是 prod 8721。
// 跑法(frontend/):npx vite preview --config ../.claude/mod/signal-shadow-policies/evidence/vite.sidecar.config.ts --port 4174
import { mergeConfig } from "vite";

import base from "../../../../frontend/vite.config";

const SIDECAR = "http://127.0.0.1:8899";

export default mergeConfig(base, {
  root: "C:/side-project/copycat/.claude/worktrees/mod-signal-shadow-policies/frontend",
  preview: {
    proxy: {
      "/api": SIDECAR,
      "/ws": { target: SIDECAR, ws: true },
    },
  },
});
