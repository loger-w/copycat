/** vite plugin `buildShaPlugin` 與 `gitSha()` 的單元測試(node 環境)。
 *
 *  受測檔在 `src/` 之外(vite.config.ts 的同層),`@/` alias 涵蓋不到 → 只有這檔用相對
 *  import。之所以把 plugin 抽成獨立檔而不是寫在 vite.config.ts 裡,就是為了這個接縫
 *  (design R2):vite.config.ts 本身在測試裡 import 會連帶跑整份 defineConfig。 */
import { describe, expect, it } from "vitest";

import { buildShaPlugin, gitSha } from "../../sha-plugin";

/** vite dev server 的最小替身:plugin 只用到 `middlewares.use(path, handler)`。 */
interface FakeRes {
  setHeader: (key: string, value: string) => void;
  end: (body: string) => void;
}
type Handler = (req: unknown, res: FakeRes) => void;

function fakeServer() {
  const registered: [string, Handler][] = [];
  const server = {
    middlewares: {
      use: (path: string, handler: Handler) => {
        registered.push([path, handler]);
      },
    },
  };
  const configure = buildShaPlugin().configureServer as unknown as (s: typeof server) => void;
  configure(server);
  return registered;
}

function callHandler(handler: Handler): { headers: [string, string][]; body: string } {
  const headers: [string, string][] = [];
  let body = "";
  handler(
    {},
    {
      setHeader: (key, value) => headers.push([key, value]),
      end: (b) => {
        body = b;
      },
    },
  );
  return { headers, body };
}

describe("gitSha(SC-1)", () => {
  it("在本 repo 回短 sha", () => {
    expect(gitSha()).toMatch(/^[0-9a-f]{7,12}$/);
  });
});

describe("buildShaPlugin(SC-6)", () => {
  it("掛在 /__build/sha 路徑上", () => {
    const registered = fakeServer();
    expect(registered.length).toBe(1);
    expect(registered[0]?.[0]).toBe("/__build/sha");
  });

  it("handler 回 JSON,payload 帶當下 git_sha", () => {
    const handler = fakeServer()[0]![1];
    const { headers, body } = callHandler(handler);
    expect(headers).toContainEqual(["content-type", "application/json"]);
    expect((JSON.parse(body) as { git_sha: string | null }).git_sha).toBe(gitSha());
  });

  it("每次請求現算(不是註冊時凍結一次)", () => {
    // 直接觀測「重新求值」需要 spy node:child_process,對這條 import 路徑不可行;
    // 退而驗「同一個 handler 連呼兩次都各自回當下值」—— 凍結實作若把值存進 closure,
    // 這條測試在 sha 未變時仍會綠,真正的守門是 design R2 具名的真環境驗證
    // (commit 後不重啟 vite 再 curl 應變值)。此處守的是「handler 可重入且無副作用」。
    const handler = fakeServer()[0]![1];
    const first = callHandler(handler);
    const second = callHandler(handler);
    expect(JSON.parse(first.body)).toEqual({ git_sha: gitSha() });
    expect(JSON.parse(second.body)).toEqual({ git_sha: gitSha() });
  });
});
