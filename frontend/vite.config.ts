/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

import { buildShaPlugin, gitSha } from "./sha-plugin";

const BACKEND = "http://127.0.0.1:8721";

export default defineConfig({
  plugins: [react(), tailwindcss(), buildShaPlugin()],
  // build 時凍結的 bundle sha(SC-1);dev 下前端 sha 改走 plugin 的 /__build/sha 現算,
  // 這裡的值只在非 dev(build 產物)或該路徑不可得時當降級來源。
  define: { __GIT_SHA__: JSON.stringify(gitSha()) },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    proxy: {
      "/api": BACKEND,
      "/ws": { target: BACKEND, ws: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
