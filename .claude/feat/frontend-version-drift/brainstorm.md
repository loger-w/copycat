# brainstorm:前端版本落差偵測閉環

日期:2026-08-05。分支 `feat/frontend-version-drift`。

## 分流判定

已成形方案(條件 1 中:user 指名做法 — vite define 嵌 git sha + runtime 與 /api/health 比對 + 狀態列/console 提示;條件 2 中:嵌入方式/輪詢節奏/UI 落點有決策點)→ grilling 姿態,逐題 auto-default(第 2 輪的「停下問 user」指示為該輪專屬,本輪回歸預設停等規則;無方向性抉擇)。

## 事實(自查)

- 後端已備妥:`/api/health` 回 `{git_sha, git_dirty, started_at}`(app.py:510-517);`build_info.capture()` 於 lifespan 啟動時呼叫一次,**行程級凍結**(啟動後新 commit 不會改變它的答案 — 這正是要偵測的落差);git 不可得一律 None(觀測性資訊,絕不擋啟動)。
- 前端零痕跡:無 define、無 VITE_ env、無 /api/health 呼叫。`vite.config.ts` 現況無 define 節。
- App.tsx 頂部 nav 列(:173-198)含五顆 tab + `IndexBar`(右緣指數列)— 全域常駐,是「狀態列」的自然落點。
- TanStack Query 為既有資料層慣例(useCapital 等);`ConnectionBadge` 是 per-page 連線膠囊,語意不同不混用。

## 決策(全部 auto-default)

1. **嵌入方式**:`vite.config.ts` 頂層 `execSync("git rev-parse --short HEAD")`(try/catch → null,git 不可得不炸 build/dev)+ `define: { __GIT_SHA__: JSON.stringify(sha) }`;`src/vite-env.d.ts` 補 `declare const __GIT_SHA__: string | null`。`[auto-default: define 常數而非 VITE_ env | reason: 不需 .env 檔參與,單一來源;與後端同語彙(rev-parse --short)]`
2. **取得後端 sha**:新 hook `useServerBuild()`(TanStack useQuery,GET /api/health,`refetchInterval: 60_000`、refetchOnWindowFocus 預設開 — 回來看盤的瞬間就重判)。`[auto-default: 60s 輪詢 | reason: health 是 in-memory dict,零成本;落差通常發生在重啟後,分鐘級偵測夠]`
3. **判定純函數** `versionDrift(feSha, beSha)`:兩者皆非 null 且不等 → 回 `{fe, be}`;任一 null(git 不可得/尚未取得/fetch 失敗)或相等 → null(**不誤報優先**)。
4. **UI 落點**:nav 列 IndexBar 之前插入 drift 膠囊(僅 drift 時渲染,無落差零 DOM);amber 系(`bg-warn` 語彙)。`[auto-default: nav 列 | reason: 全 tab 常駐可見,不佔版面(平時零 DOM)]`
5. **console 提示**:偵測到 drift 時 `console.warn` 一次,同一組 (fe, be) pair 不重複(useEffect + ref 記已警告 pair)。

## SC

- SC-1:build/dev 嵌入 sha:`__GIT_SHA__` 為 vite 啟動時 `git rev-parse --short HEAD` 結果;git 不可得 → `null` 且 `npm run build` 照常成功(exit 0)。驗證:vitest 斷言 `__GIT_SHA__` 型別與格式(vitest 走同一份 vite config,define 生效)+ `npm run build` exit 0。
- SC-2:`useServerBuild` 每 60s 輪詢 /api/health;fetch 失敗 → data undefined、不觸發任何提示。驗證:hook/元件測試(fetch route mock)。
- SC-3:`versionDrift` 判定表:(a1b2, a1b2)→null;(a1b2, c3d4)→drift;(null, x)→null;(x, null)→null;(null, null)→null。驗證:單元測試逐列。
- SC-4(畫面可指認):前後端 sha 不同時,**頂部 nav 列右側(指數列左邊)出現 amber 膠囊「版本落差」**,hover title 為 `前端 <sha> / 後端 <sha> — 舊的一邊該重啟`;sha 一致或任一不可得時 **nav 列無此元素**(零 DOM)。驗證:component test(兩態)+ AI 截圖:真環境健康態(無膠囊)+ fetch override 假造 health 回不同 sha(膠囊出現)雙截圖 + user 過目。驗證窗口:anytime(不依賴盤中)。
- SC-5:drift 時 `console.warn` 恰一次(含兩個 sha 與重啟提示;文案定案 `前後端版本落差:前端 <fe> / 後端 <be> — 舊的一邊該重啟`,`[amendment 2026-08-05: impl-spec R7 — 文案單一定案,驗收以此為準]`);同一 pair 在後續輪詢不重複 warn;pair 變化(如後端重啟到第三個 sha)再 warn 一次。驗證:vi.spyOn(console, "warn") 單元測試。
- SC-6:`[amendment 2026-08-05: design review R1 — dev(主要跑法)下 define 凍結於 vite 啟動,會漏報動機情境(commit 後忘重啟後端,兩邊同為舊 sha)並誤報反向(HMR 已同步仍亮燈)]` dev 模式前端 sha 改由 vite middleware `/__build/sha` **每次現算**(= 當下 HEAD),比對語意成為「後端行程是否落後 HEAD」— 即 CLAUDE.md §8 `git log <sha>..HEAD` 判法的自動化;build 模式沿 `__GIT_SHA__` 常數(bundle 凍結語意正確)。驗證:middleware 單元路徑(dev server fetch /__build/sha 回 {git_sha})+ 來源選擇函數測試(DEV → live,PROD → define)。

## Edge cases(≥3)

1. 後端 git_sha null(打包部署/git 不可得)→ 不判定不誤報(SC-3)。
2. 前端 __GIT_SHA__ null(同上)→ 不判定。
3. health fetch 失敗 / 後端未起 → data undefined → 無提示(斷線本就有各頁 ConnectionBadge 承擔,語意不混)。
4. **uncommitted 改動不觸發**(known limitation):兩個行程同一 commit 起跑、其後只有未 commit 的 .py 改動 → sha 相同無警示。與 CLAUDE.md §8「git log <sha>..HEAD」工作流同界 — 本 feature 只偵測 **committed** 落差;dirty flag 不入判定(噪音源:開發中恆 dirty)。
5. vite dev 長跑 + HMR:__GIT_SHA__ 凍結在 vite 啟動時 — 判定語意 = 「兩個**行程**起跑時的 commit 不同」,任一邊重啟到新版即出警示;HMR 造成的「前端比 sha 新」不在偵測範圍(known limitation,同上一條同源)。
6. 雙分頁:各自輪詢各自 warn 一次,可接受(無跨分頁去重需求)。

## Out of scope

- 偵測 uncommitted 改動落差(dirty 語意)。
- 自動重啟 / 阻斷操作(只提示不動作)。
- started_at 的顯示(health 已有,前端本輪不消費)。
- 後端任何改動(health 契約現狀已足)。

## S/M/L

**M**(vite.config + 新 hook + nav 膠囊 + d.ts + 測試,跨 build 設定與 runtime 兩層)→ Phase 1 design.md。
