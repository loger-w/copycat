/** vite plugin `buildShaPlugin`、`gitSha()` 與 `behindSince()` 的單元測試(node 環境)。
 *
 *  受測檔在 `src/` 之外(vite.config.ts 的同層),`@/` alias 涵蓋不到 → 只有這檔用相對
 *  import。之所以把 plugin 抽成獨立檔而不是寫在 vite.config.ts 裡,就是為了這個接縫
 *  (design R2):vite.config.ts 本身在測試裡 import 會連帶跑整份 defineConfig。 */
import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";

import { behindSince, buildShaPlugin, gitSha } from "../../sha-plugin";

/** 本 repo 的第一個 commit:`<root>..HEAD -- copycat/` 必定非空(backend 就住在
 *  copycat/)→ 當 `behind: true` 的確定性 fixture,不寫死任何 sha。 */
function rootSha(): string {
  return execFileSync("git", ["rev-list", "--max-parents=0", "HEAD"], { encoding: "utf8" })
    .trim()
    .split(/\s+/)[0]!;
}

/** vite dev server 的最小替身:plugin 只用到 `middlewares.use(path, handler)`。 */
interface FakeRes {
  setHeader: (key: string, value: string) => void;
  end: (body: string) => void;
}
type Handler = (req: { url?: string }, res: FakeRes) => void;

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

/** connect 對 `use(path, fn)` 會把 mount 路徑從 `req.url` 剝掉、保留 query string。 */
function callHandler(handler: Handler, query = ""): { headers: [string, string][]; body: string } {
  const headers: [string, string][] = [];
  let body = "";
  handler(
    { url: `/${query}` },
    {
      setHeader: (key, value) => headers.push([key, value]),
      end: (b) => {
        body = b;
      },
    },
  );
  return { headers, body };
}

function payload(handler: Handler, query = ""): { git_sha: string | null; behind: boolean | null } {
  return JSON.parse(callHandler(handler, query).body) as {
    git_sha: string | null;
    behind: boolean | null;
  };
}

describe("gitSha(SC-1)", () => {
  it("在本 repo 回短 sha", () => {
    expect(gitSha()).toMatch(/^[0-9a-f]{7,12}$/);
  });
});

describe("behindSince(Phase 4 C3:range 判別)", () => {
  it("since..HEAD 之間 copycat/ 有新 commit → true", () => {
    expect(behindSince(rootSha())).toBe(true);
  });

  it("since = HEAD(空 range)→ false", () => {
    expect(behindSince(gitSha())).toBe(false);
  });

  it("缺 since → null(不判定,不是 false)", () => {
    expect(behindSince(null)).toBeNull();
    expect(behindSince(undefined)).toBeNull();
    expect(behindSince("")).toBeNull();
  });

  it("git 失敗(未知 revision)→ null", () => {
    expect(behindSince("deadbeef")).toBeNull();
  });

  it("非 sha 字串一律拒收 —— shell 元字元 / git 旗標 / 路徑跳脫", () => {
    // execFile 陣列參數本來就不經 shell,這條驗的是「連 git 都不餵」的第一道閘
    expect(behindSince("abc; rm -rf /")).toBeNull();
    expect(behindSince("$(whoami)")).toBeNull();
    expect(behindSince("--all")).toBeNull();
    expect(behindSince("../../etc/passwd")).toBeNull();
    expect(behindSince("HEAD")).toBeNull(); // 只收 hex,連合法 revision 名都不放行
  });
});

describe("buildShaPlugin(SC-6)", () => {
  it("掛在 /__build/sha 路徑上", () => {
    const registered = fakeServer();
    expect(registered.length).toBe(1);
    expect(registered[0]?.[0]).toBe("/__build/sha");
  });

  it("回 JSON;無 since 時 behind 為 null,git_sha 為當下值", () => {
    const handler = fakeServer()[0]![1];
    const { headers } = callHandler(handler);
    expect(headers).toContainEqual(["content-type", "application/json"]);
    expect(payload(handler)).toEqual({ git_sha: gitSha(), behind: null });
  });

  it("?since=<舊 sha> → behind true;?since=<HEAD> → behind false", () => {
    const handler = fakeServer()[0]![1];
    expect(payload(handler, `?since=${rootSha()}`).behind).toBe(true);
    expect(payload(handler, `?since=${gitSha()}`).behind).toBe(false);
  });

  it("?since=<注入字串> → behind null(git_sha 照常回)", () => {
    const handler = fakeServer()[0]![1];
    const got = payload(handler, `?since=${encodeURIComponent("abc; rm -rf /")}`);
    expect(got.behind).toBeNull();
    expect(got.git_sha).toBe(gitSha());
  });

  it("每次請求現算(不是註冊時凍結一次)", () => {
    // 直接觀測「重新求值」需要 spy node:child_process,對這條 import 路徑不可行;
    // 退而驗「同一個 handler 連呼兩次都各自回當下值」。真正的判別式是 design R2 具名的
    // 真環境驗證(不重啟 vite、移動 HEAD 後再 curl 應變值),證據見 gate-output.md。
    const handler = fakeServer()[0]![1];
    expect(payload(handler)).toEqual({ git_sha: gitSha(), behind: null });
    expect(payload(handler)).toEqual({ git_sha: gitSha(), behind: null });
  });
});
