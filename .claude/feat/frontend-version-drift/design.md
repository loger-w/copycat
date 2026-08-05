# design:前端版本落差偵測閉環(v2)

changelog:
- v1(2026-08-05):初版。
- v2(2026-08-05):design review round 1(0 P0 / 4 P1 / 6 P2 全 accepted)整併。
  P1:R1 dev 模式 sha 改 middleware 現算(漏報動機情境 + 誤報 HMR 反向的修正,新 SC-6)/
  R2 frontendSha 延遲求值 + prop 注入縫 / R3 測試環境前提(jsdom docblock + wrap())/
  R4 膠囊 ml-auto 落點 + App 層落點測試。
  P2:R5 App.test health 路由 + retry false / R6 local fetchHealth / R7 execSync timeout+stdio /
  R8 60s 輪詢 fake timers 測試 / R9 負例 settle 點 / R10 取證配方。

對應 brainstorm.md SC-1~SC-6。純 frontend(後端 /api/health 契約現狀不動)。

## 檔案組織與資料流

```
vite.config.ts        —— gitSha()(timeout 3s 靜默降級)→ define __GIT_SHA__(SC-1)
                         + plugin buildShaPlugin:configureServer middleware /__build/sha(SC-6)
src/vite-env.d.ts     —— declare const __GIT_SHA__: string | null
src/lib/version-drift.ts      —— versionDrift 純函數(SC-3)+ frontendSha() 延遲求值(R2)
src/hooks/useServerBuild.ts   —— useQuery /api/health(SC-2)+ useFrontendSha()(SC-6 dev live)
src/components/VersionDriftBadge.tsx —— 膠囊 + console.warn once(SC-4/SC-5)
src/App.tsx           —— nav 列插入 <VersionDriftBadge>(IndexBar 之前;膠囊自帶 ml-auto)
```

資料流:前端 sha(dev = `/__build/sha` 現算 HEAD;build = `__GIT_SHA__` 常數)+ `/api/health` 的 `git_sha` → `versionDrift(fe, be)` → null(零 DOM)或 `{fe, be}`(膠囊 + warn once)。

**語意(R1 定案;`[amendment 2026-08-05: Phase 4 C3 — 缺 -- copycat/ 路徑過濾,純前端/docs commit 也亮燈,本 repo 工作流下膠囊近乎恆亮 = 雜訊化]`)**:

- **dev**:range 判別 — 前端把後端 sha 帶給 middleware(`/__build/sha?since=<be_sha>`),middleware 執行 `git log --format=%h <since>..HEAD -- copycat`(**execFileSync 陣列參數 + `/^[0-9a-f]{4,40}$/i` 驗證 since,防 shell 注入**),回 `{git_sha: <HEAD short>, behind: <boolean|null>}`(git 失敗/since 非法 → behind: null 不判定)。drift 條件 = `behind === true` — 這才是 CLAUDE.md §8 `git log <git_sha>..HEAD -- copycat/` 的**完整**自動化(含路徑過濾):只有後端 code 真的前進了才亮燈。無 since 參數(相容/冷態)→ 只回 git_sha、behind: null。
- **build(非 dev)**:維持 define 凍結 sha vs 後端 sha 的等值比對(bundle 產物語意)。
- uncommitted 改動仍不可測(Known Risks)。
- 成本記帳(C6 更正):兩 query 各 `staleTime: 5_000` — 節奏 = 每 60s + 聚焦(5s 去重),middleware 每請求一次 git 子行程(數十 ms 級,Windows);同步 execFileSync 在 5s staleTime 下無聚焦風暴。

## SC-1/SC-6:vite.config.ts

```ts
import { execSync } from "node:child_process";

/** 與後端 build_info._git 同一套降級紀律:timeout 3s、stderr 靜默、任何失敗回 null。 */
function gitSha(): string | null {
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

function buildShaPlugin(): Plugin {
  return {
    name: "copycat-build-sha",
    configureServer(server) {
      server.middlewares.use("/__build/sha", (_req, res) => {
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ git_sha: gitSha() })); // 每次現算 = 當下 HEAD(R1)
      });
    },
  };
}
// defineConfig:plugins: [react(), tailwindcss(), buildShaPlugin()]
//              define: { __GIT_SHA__: JSON.stringify(gitSha()) }
```

middleware 只存在於 dev server;build 產物無此路徑(fetch 404 → 降級走 define,見下)。

## SC-2/SC-6:hooks/useServerBuild.ts

```ts
export interface ServerBuild { git_sha: string | null; git_dirty: boolean | null; started_at: string; }
export const HEALTH_POLL_MS = 60_000;

/** 本檔自寫 local fetch(R6:useCapital.fetchJson 是模組私有且帶錯誤碼解析,health 無此契約)。 */
async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as T;
}

export function useServerBuild() {
  return useQuery({
    queryKey: ["server-build"],
    queryFn: () => getJson<ServerBuild>("/api/health"),
    refetchInterval: HEALTH_POLL_MS,
    retry: false, // R5:60s 下一輪就是重試;retry 會在測試 teardown 後打真 fetch(flake 源)
  });
}

/** 前端 sha 來源:dev 走 /__build/sha 現算(60s 輪詢,與 health 同節奏);
 *  非 dev 或該路徑不可得(404/失敗)→ frontendSha()(define 常數)。 */
export function useFrontendSha(): string | null {
  const q = useQuery({
    queryKey: ["frontend-sha"],
    queryFn: () => getJson<{ git_sha: string | null }>("/__build/sha"),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
    enabled: import.meta.env.DEV,
  });
  return q.data?.git_sha ?? frontendSha();
}
```

## SC-3:lib/version-drift.ts(R2:延遲求值)

```ts
export interface Drift { fe: string; be: string; }
export function versionDrift(fe: string | null | undefined, be: string | null | undefined): Drift | null;
// 兩者皆為非空字串且不等 → {fe, be};否則 null。空字串視同 null。

export function frontendSha(): string | null {
  return typeof __GIT_SHA__ === "undefined" ? null : (__GIT_SHA__ || null);
}
// 延遲求值:vitest 以 globalThis 注入 define(deleteDefineConfig → setupDefines),
// vi.stubGlobal("__GIT_SHA__", …) 才有效;module 頂層 const 會在 import 時凍結(R2)。
```

## SC-4/SC-5:VersionDriftBadge

```tsx
export function VersionDriftBadge({ feSha }: { feSha?: string | null }) {
  const live = useFrontendSha();
  const fe = feSha !== undefined ? feSha : live; // 注入縫(R2:測試不依賴機器 git 狀態)
  const { data } = useServerBuild();
  const drift = versionDrift(fe, data?.git_sha);
  // warn once per pair(useRef;drift 消失不清 — pair 級去重)
  if (drift === null) return null;
  return (
    <span data-testid="version-drift-badge"
          title={`前端 ${drift.fe} / 後端 ${drift.be} — 舊的一邊該重啟`}
          className="ml-auto inline-flex items-center gap-1.5 rounded-sm border border-warn/40 bg-warn/15 px-2.5 py-1 font-mono text-xs text-warn">
      版本落差
    </span>
  );
}
```

- **落點(R4)**:App.tsx nav 列 `<VersionDriftBadge />` 插在 `<IndexBar />` 之前;膠囊自帶 `ml-auto` — 有膠囊時它吃掉自由空間、IndexBar 緊隨其右(IndexBar 自己的 ml-auto 成為 no-op);無膠囊(null)時 IndexBar 的 ml-auto 照舊。膠囊樣式沿 ConnectionBadge 語彙(rounded-sm border px-2.5 py-1 font-mono text-xs)。
- warn 文案:`前後端版本落差:前端 ${fe} / 後端 ${be} — 舊的一邊該重啟`。

## 測試設計

**環境前提(R3)**:元件/hook 測試檔頭 `/** @vitest-environment jsdom */`;render 走 `@/test-utils` 的 `wrap()`;fetch mock 依 App.test.tsx 形態(`vi.stubGlobal("fetch", vi.fn(...))` + afterEach `vi.unstubAllGlobals()`)。

- `lib/version-drift.test.ts`(node 環境可):SC-3 判定表逐列 + 空字串;`frontendSha()` 非 null 時符合 `/^[0-9a-f]{7,12}$/`;`vi.stubGlobal("__GIT_SHA__", "aaaaaaa")` 後 `frontendSha() === "aaaaaaa"`(延遲求值縫的守門)。
- `components/VersionDriftBadge.test.tsx`(jsdom):
  - 正例:`feSha="aaaaaaa"` prop + health 回 `bbbbbbb` → `await screen.findByTestId("version-drift-badge")`、title 含兩 sha;console.warn 恰一次(rerender 不重複)。
  - 負例三條(R9:先 `await waitFor(() => expect(fetchMock).toHaveBeenCalled())` settle 再斷言無 badge/無 warn):same sha / health git_sha null / health 500。
  - pair 變化 → 第二次 warn。
  - dev live 路徑:mock `/__build/sha` 回 sha → 斷言優先於 define 常數(`import.meta.env.DEV` 在 vitest 為 true)。
- `hooks/useServerBuild.test.tsx`(jsdom + fake timers,R8):render 後 1 次 fetch;`advanceTimersByTimeAsync(HEALTH_POLL_MS − 1)` 仍 1 次;補 1ms → 2 次。
- `App.test.tsx`(既有檔改動,PLAN 明列):mock 補 `/api/health` 與 `/__build/sha` 路由(回 git_sha null → 無 badge 無噪音);新增 App 層落點測試:drift fixture(兩路由回不同 sha)→ badge 出現且為 nav 內 IndexBar 的前一個 sibling;健康態 nav 無該 testid(R4)。
- `npm run build` exit 0(SC-1 gate)。

## 接點與風險

- App 層新增兩條 60s 輪詢(health + dev 的 /__build/sha);皆零成本(in-memory dict / execSync 10ms 級)。
- `/__build/sha` 走 vite middleware **不經** proxy(路徑非 /api、/ws)— 與後端零耦合;build 部署下 404 → useFrontendSha 降級 define 常數。
- vitest 對 `import.meta.env.DEV` 為 true → dev live 路徑在測試可達;App.test 必須 mock `/__build/sha`(否則 404 fallback,仍安全)。
- execSync 每 60s 一次(middleware),10ms 級,dev 機負擔可忽略。

## Known Risks

- uncommitted 改動(sha 不變)與「vite dev 也需重啟的 config/依賴級變更」不在偵測範圍(brainstorm edge 4/5)。
- build 模式(非 dev)語意回到「bundle 凍結 sha vs 後端行程」— 本專案目前無 build 部署形態,語意留待真的部署時再驗。

## Phase 4 review 落地細節(C1/C4/C5 — useFrontendSha 來源選擇最終版)

```ts
// dev 路徑(query key 含 beSha;enabled: DEV && beSha 非 null):
// GET /__build/sha?since=<beSha> → { git_sha, behind }
// 來源選擇(data-first,不假造):
if (!import.meta.env.DEV) return { fe: frontendSha(), behind: null };   // build:等值比對
if (q.data !== undefined) return { fe: q.data.git_sha, behind: q.data.behind }; // 有問到過 → 最後現算值(暖態 error 沿用 data)
if (q.status === "error" && status === 404) return { fe: frontendSha(), behind: null }; // 路徑不存在(build 產物)才降級 define
return { fe: null, behind: null };  // 冷態 / transient error:不知道就不判定
```

badge 判定:dev(behind 可得)→ `behind === true` 才 drift(title/warn 用 fe=HEAD short、be=後端 sha);build → `versionDrift(fe, be)` 等值比對。`getJson` 的 Error 帶 `status` 欄位(`Object.assign(new Error(...), {status})`)。warn 去重補載重路徑測試(C2:drift → 消失 → 同 pair 再現仍 1 次)。

## 真實環境取證(R10 配方)

當下天然可拍:prod server(8ef1346,今晨起)vs 本輪 HEAD(晚 20+ commits)→ dev 模式開 vite 即應亮「版本落差」膠囊(drift 態截圖);健康態:claude-in-chrome fetch override 讓 `/api/health` 回當下 HEAD sha → blur/focus 觸發 refetch → 膠囊消失(零 DOM 查證 + 截圖)。兩態都不需重啟任何東西。
