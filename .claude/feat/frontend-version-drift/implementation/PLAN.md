# PLAN:前端版本落差偵測閉環(v2)

依 design.md v2;`[amendment 2026-08-05: impl-spec review R1~R8 全 accepted 整併]`。
TDD 順序:sha-plugin → lib → hook → 元件 → App 接線 → vite.config 接線。

## 0. 契約定案(R1/R4/R7)

- **來源選擇(R1:live 未回前不得假造)**:`useFrontendSha()` — 非 DEV → `frontendSha()`;DEV → `/__build/sha` 的 `q.data?.git_sha`,**未 fetched 前回 `null`**(不 fallback define 舊值 — 首幀閃現假 drift + 假 warn 是 R1 修正的核心),fetched 而失敗(404/error)才降級 `frontendSha()`。
- **落點(R4:雙 ml-auto 會平分剩餘空間,膠囊會停在 nav 中段)**:`<VersionDriftBadge />` 與 `<IndexBar />` 包進 `<div className="ml-auto flex items-baseline gap-3">` 容器;膠囊**不帶** ml-auto;IndexBar 一字不動(其自身 ml-auto 在內容尺寸容器內為 no-op)。
- **warn 文案(R7,單一定案)**:`前後端版本落差:前端 ${fe} / 後端 ${be} — 舊的一邊該重啟`;warn 的 useRef/useEffect 宣告在 `if (drift === null) return null` **之前**(hooks 順序)。

## 1. `frontend/sha-plugin.ts`(🟢 新檔,R2:可測接縫)

- named exports:`gitSha()`(execSync `git rev-parse --short HEAD`,`{encoding:"utf8", timeout:3000, stdio:["ignore","pipe","ignore"]}`,catch/空 → null)與 `buildShaPlugin()`(vite `Plugin`,`configureServer` 掛 `/__build/sha` middleware,**每請求現算** `gitSha()`,回 `{"git_sha":…}` JSON)。
- 紅測試 `src/lib/sha-plugin.test.ts`(node 環境,import `../../sha-plugin`):(a) `gitSha()` 在本 repo 回 `/^[0-9a-f]{7,12}$/`;(b) plugin 以 fake server(`{middlewares:{use:vi.fn()}}`)註冊路徑 `/__build/sha`;(c) handler 餵 fake res(setHeader/end spy)→ payload JSON.parse 含 git_sha;(d) 兩次呼叫 handler 各自重新求值(spy `node:child_process` 不可行則以「handler 每次呼叫 end 皆帶現值」+ 註解記 design 依據;至少驗兩次呼叫都成功回 JSON)。

## 2. `frontend/vite.config.ts`(🟢 接線)

- `import { buildShaPlugin, gitSha } from "./sha-plugin"`;plugins 加 `buildShaPlugin()`;`define: { __GIT_SHA__: JSON.stringify(gitSha()) }`。
- 驗證:`npm run build` exit 0;Phase 6 具名必驗:`curl localhost:<vite>/__build/sha` 回現值,**commit 後不重啟 vite 再 curl 應變值**(R2)。

## 3. `frontend/src/vite-env.d.ts`(🟢 一行):`declare const __GIT_SHA__: string | null;`

## 4. `frontend/src/lib/version-drift.ts` + 測試(🟢 紅先行)

- `versionDrift(fe, be)`:皆非空字串且不等 → `{fe, be}`;否則 null。`frontendSha()`:`typeof __GIT_SHA__ === "undefined" ? null : (__GIT_SHA__ || null)`。
- 紅測試(node 環境;`afterEach(() => vi.unstubAllGlobals())` — R8):判定表 5 列 + 空字串;frontendSha 兩態 stub(stub null → null;stub "" → null;stub "aaaaaaa" → "aaaaaaa");未 stub 時 `__GIT_SHA__` global 為 string 或 null(vitest setupDefines 注入)。

## 5. `frontend/src/hooks/useServerBuild.ts` + 測試(🟢 紅先行)

- `ServerBuild` / `HEALTH_POLL_MS = 60_000` / local `getJson`(!ok throw)/ `useServerBuild`(retry: false)/ `useFrontendSha`(§0 來源選擇語意;`enabled: import.meta.env.DEV`)。
- 紅測試 `useServerBuild.test.tsx`(jsdom docblock;**renderHook + QueryClientProvider wrapper**(retry:false)— `wrap()` 是 render 包裝拿不到 hook 值,repo 慣例見 useCapital.test(R6)):
  - 輪詢(R8/fake timers):`beforeEach vi.useFakeTimers()` / `afterEach vi.useRealTimers() + vi.unstubAllGlobals()`;render 後 `await vi.advanceTimersByTimeAsync(0)` → 1 次 fetch;`+ HEALTH_POLL_MS − 1` 仍 1;`+1` → 2 次。
  - R1 loading:`/__build/sha` never-resolve → `useFrontendSha()` 回 null(非 define 值)。
  - R3 PROD:`vi.stubEnv("DEV", false)`(afterEach `vi.unstubAllEnvs()`)+ stub `__GIT_SHA__` → 回 define 值且 **未** fetch `/__build/sha`。
  - R3 降級:`/__build/sha` 回 404 → settle 後回 `frontendSha()`。
  - DEV live:`/__build/sha` 回 sha → 優先於 define。

## 6. `frontend/src/components/VersionDriftBadge.tsx` + 測試(🟢 紅先行)

- `feSha?: string | null` prop(undefined → `useFrontendSha()`);warn once per pair(§0 文案與 hooks 順序);null → 零 DOM;膠囊 `data-testid="version-drift-badge"`、warn 色系(`border-warn/40 bg-warn/15 text-warn`)、title 同 warn 文案。
- 紅測試(jsdom + `wrap()` + fetch route mock):正例(prop feSha="aaaaaaa" + health "bbbbbbb" → findByTestId + title + warn 恰一次且**參數含兩 sha 與「重啟」**(R7));負例三條(same sha / git_sha null / health 500;先 `waitFor(fetch called)` settle 再斷言無 badge 無 warn — R9);pair 變化 → 第二次 warn。

## 7. `frontend/src/App.tsx` + `App.test.tsx`(🟢)

- App:nav 列尾端改為 `<div className="ml-auto flex items-baseline gap-3"><VersionDriftBadge /><IndexBar …/></div>`(§0;IndexBar props 原樣)。
- App.test(既有檔改動):mock 補 `/api/health` 與 `/__build/sha` 路由(回 git_sha null → 無 badge 無噪音);新增落點測試(R5,不動 IndexBar):`const nav = screen.getByRole("tablist", { name: "主要分頁" })`,drift fixture(兩路由回不同 sha)→ `within(nav).findByTestId("version-drift-badge")` 且 `badge.nextElementSibling` 的 textContent 含「加權」(= IndexBar);健康態 `within(nav).queryByTestId(...)` null。註:badge 與 IndexBar 同在 wrapper 內,「nav 內」斷言以 `nav.contains(badge)` 成立即可,sibling 斷言以 wrapper 內部關係為準。

## 8. gate 與取證

- gate:frontend `npm test -- --run` / `npx tsc -b` / `npx eslint src` / `npm run build`;backend 四項照常(零 .py)。
- Phase 6(design v2 配方 + R2 具名項):(a) `curl /__build/sha` 現值 + commit 後不重啟再 curl 變值;(b) 天然 drift 截圖(prod server 8ef1346 vs HEAD);(c) 健康態:fetch override 讓 health 回 HEAD sha + blur/focus → 膠囊消失。工具 claude-in-chrome。
