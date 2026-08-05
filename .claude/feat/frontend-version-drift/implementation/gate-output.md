# Phase 3 實作證據(frontend-version-drift)

分支 `feat/frontend-version-drift`,起點 `b9a1add`。全部改動限於 `frontend/`,零 `.py`。

> **本檔含兩輪**:§1–§6 = Phase 3 初版;**§7 起 = Phase 4 review 9 條 accepted findings
> 的修復輪(C1~C9)**。最終數字以 §8 為準。

## 1. pre-impl 紅證據(TDD 紅先行)

### 紅 1 — `b7102ab`(sha-plugin + version-drift)

紅測試檔:`frontend/src/lib/sha-plugin.test.ts`(4 條)、`frontend/src/lib/version-drift.test.ts`(9 條)

```
FAIL  src/lib/sha-plugin.test.ts [ src/lib/sha-plugin.test.ts ]
Caused by: Error: Failed to load url ../../sha-plugin (resolved id: ../../sha-plugin)
  in C:/side-project/copycat/frontend/src/lib/sha-plugin.test.ts. Does the file exist?

FAIL  src/lib/version-drift.test.ts [ src/lib/version-drift.test.ts ]
Error: Cannot find module '@/lib/version-drift' imported from
  'C:/side-project/copycat/frontend/src/lib/version-drift.test.ts'.

Test Files  2 failed (2)
     Tests  no tests
```

### 紅 2 — `2dfba3f`(useServerBuild)

紅測試檔:`frontend/src/hooks/useServerBuild.test.tsx`(7 條:60s 輪詢邊界 fake timers、
error 終態、`useFrontendSha` 四態)

```
FAIL  src/hooks/useServerBuild.test.tsx [ src/hooks/useServerBuild.test.tsx ]
Error: Failed to resolve import "@/hooks/useServerBuild" from
  "src/hooks/useServerBuild.test.tsx". Does the file exist?

Test Files  1 failed (1)
     Tests  no tests
```

### 紅 3 — `b78b9ba`(VersionDriftBadge + App 落點)

紅測試檔:`frontend/src/components/VersionDriftBadge.test.tsx`(9 條)、
`frontend/src/App.test.tsx`(新增 2 條落點測試 + 既有 fetch mock 補兩路由)

```
FAIL  src/components/VersionDriftBadge.test.tsx [ src/components/VersionDriftBadge.test.tsx ]
  (suite 載入失敗:@/components/VersionDriftBadge 尚未存在)
FAIL  src/App.test.tsx > App 版本落差膠囊落點(SC-4) > 落差態:膠囊在 nav 內,且緊鄰 IndexBar 左側
FAIL  src/App.test.tsx > App 版本落差膠囊落點(SC-4) > 健康態(兩邊同 sha):nav 內零膠囊

Test Files  2 failed (2)
     Tests  2 failed | 24 passed (26)
```

值得記一筆:健康態那條負例是**卡在 settle 點**紅的(`waitFor` 等不到 `/api/health` 被打過
→ `expected true, received false`),不是「查不到膠囊所以綠」。這正是 design R9 要的 ——
證明這條負例不會因為元件根本沒掛就恆綠。

## 2. 完工四 gate(全綠,`frontend/`)

| gate | 指令 | 結果 |
|------|------|------|
| 測試 | `npm test -- --run` | **77 files / 1100 tests passed**,exit 0(10.56s) |
| 型別 | `npx tsc -b` | exit 0,零輸出 |
| Lint | `npx eslint src` | exit 0,零輸出(含零 warning) |
| Build | `npm run build` | exit 0,166 modules,built in 923ms |

基線對照(本輪動工前 `b9a1add`):73 files / 1069 tests passed。
→ **新增 4 檔 / 31 條測試,既有 1069 條零變紅**(App.test 只補 mock 路由與新增測試,
既有斷言一字未動)。

backend 四項未跑:本輪零 `.py` 改動(`git diff b9a1add..HEAD --stat` 全在 `frontend/`)。

## 3. 附帶取得的實環境證據(Phase 6 的 R2 具名項已可勾銷)

`npm run build` 產物確認 define 有落地(SC-1):

```
$ grep -o '"[0-9a-f]\{7\}"' dist/assets/index-_NwNIetV.js | sort -u
"184dd79"      ← 等於當時 HEAD 短 sha
```

`/__build/sha` middleware 冒煙 + **每請求現算**的判別式驗證(design R2 具名必驗)。
vite dev server 起在 5199(不碰 TC4、不碰 8721 後端),**全程未重啟**:

```
$ curl -s localhost:5199/__build/sha
{"git_sha":"184dd79"}

$ git checkout --detach HEAD~1 && git rev-parse --short HEAD
b78b9ba
$ curl -s localhost:5199/__build/sha          # 同一個 vite 行程,沒重啟
{"git_sha":"b78b9ba"}                          ← 值跟著 HEAD 走 = 真的每請求現算

$ git checkout feat/frontend-version-drift && git rev-parse --short HEAD
184dd79
$ curl -s localhost:5199/__build/sha
{"git_sha":"184dd79"}                          ← 復原
```

比「commit 後再 curl」更強:凍結實作在這個判別式下必紅(啟動時求值的話三次都會是同一個值)。
驗完 vite 行程已關閉(5199 不再 LISTENING),工作樹回到 `feat/frontend-version-drift` 且乾淨。

仍留給 Phase 6:(b) 天然 drift 截圖(prod server 8ef1346 vs HEAD)、(c) 健康態 fetch override
→ 膠囊消失,兩項都要 claude-in-chrome。

## 4. commit 清單

| sha | tag | message |
|-----|-----|---------|
| `b7102ab` | [red] | 🟢 test(frontend): add failing test for SC-1/SC-3/SC-6 sha-plugin + version-drift |
| `a688a62` | [green] | 🟢 feat(frontend): implement SC-1/SC-3/SC-6 build sha 來源與落差判定 |
| `2dfba3f` | [red] | 🟢 test(frontend): add failing test for SC-2/SC-6 useServerBuild 輪詢與來源選擇 |
| `26fb208` | [green] | 🟢 feat(frontend): implement SC-2/SC-6 useServerBuild + useFrontendSha |
| `b78b9ba` | [red] | 🟢 test(frontend): add failing test for SC-4/SC-5 落差膠囊與 warn 去重 |
| `184dd79` | [green] | 🟢 feat(frontend): implement SC-4/SC-5 版本落差膠囊並掛進 nav 列 |

接線/設定類(`vite.config.ts` plugin + define、`vite-env.d.ts` 宣告、`App.tsx` 插入)無獨立紅
測試,依 Phase 3 規則併入對應 [green] commit。

## 5. 與 PLAN 的落差 / 判斷記錄

- **PLAN §6「title 同 warn 文案」 vs design 的 title 短版**:採 PLAN(較新且為契約定案),
  兩處共用 `driftMessage(fe, be)` 單一來源,避免文案漂移。膠囊本文仍是「版本落差」。
- **PLAN §1(d)「兩次呼叫各自重新求值」**:spy `node:child_process` 對這條 import 路徑不可行
  (PLAN 已預留退路),單元層退為「handler 可重入、兩次都回當下值」,真正的判別式由上面
  §3 的 detached-HEAD curl 補上(比 PLAN 原本設想的「commit 後再 curl」更強)。
- **`tsconfig` 未動**:`sha-plugin.ts` 用 `/// <reference types="node" />` 取得 node 型別,
  `tsc -b` 兩個 project 都過,不必把 `"node"` 加進 `tsconfig.app.json` 的 `types`(那會讓整個
  app project 拿到 node globals,blast radius 大得多)。
- **`warn` 色系 token 已存在**(`index.css` `--color-warn: #f0b429`),不需新增 token。

## 6. scope 外衝動(記錄,未動手)

- `VersionDriftBadge` 的 warn 去重是 per component instance(`useRef`)。App 只掛一顆所以等價於
  全域;若日後有第二個掛載點會各吵一次。現在改成 module-level 去重是為「未來可能」加抽象,
  不做。
- `useServerBuild` 回的 `git_dirty` 目前沒人用(uncommitted 改動不在偵測範圍,見 design Known
  Risks)。型別留著是照 `/api/health` 契約原樣,不裁。

---

# Phase 4 review 修復輪(C1~C9)

依 design.md 更新後的「語意(R1 定案)」C3 amendment 與新節「Phase 4 review 落地細節」。

## 7. 修復輪紅證據

### 紅 4 — `23aae13`(C3:`/__build/sha` range 判別)

紅測試檔:`frontend/src/lib/sha-plugin.test.ts`(4 → 11 條)

```
Test Files  1 failed (1)
     Tests  9 failed | 2 passed (11)

TypeError: (0 , behindSince) is not a function        ← behindSince 尚未存在(5 條)
AssertionError: expected { git_sha: '184dd79' } to deeply equal
                { git_sha: '184dd79', behind: null }  ← handler payload 還沒有 behind 欄
AssertionError: expected undefined to be true         ← ?since= 未被解析
```

### 紅 5 — `da1ea7a`(C1/C2/C4~C9:來源選擇、warn 載重路徑、落點斷言)

紅測試檔:`useServerBuild.test.tsx`(7 → 13 條)、`VersionDriftBadge.test.tsx`(9 → 11 條)、
`App.test.tsx`(落點兩條升級)

```
Test Files  2 failed | 1 passed (3)
     Tests  15 failed | 35 passed (50)

TypeError: (0 , useBuildDrift) is not a function                ← 9 條(hook 尚未改形)
AssertionError: expected <span …(3)></span> to be null          ← behind=false / behind=null /
                                                                  /__build/sha 500 三條仍亮膠囊
                                                                  (舊實作走 sha 等值)
AssertionError: expected 1 to be +0                             ← be=null 時仍去問 middleware
AssertionError: expected "warn" to be called 2 times, but got 1 ← C2 載重路徑
```

App.test 的 C8(wrapper / ml-auto 歸屬)與 C9(restoreAllMocks 上移)屬**測試強化**,對當時的
實作即綠 —— 這兩條本來就不是行為修正,紅不起來,如實記錄。

## 8. 修復輪四 gate(全綠,`frontend/`)

| gate | 指令 | 結果 |
|------|------|------|
| 測試 | `npm test -- --run` | **77 files / 1115 tests passed**,exit 0(9.66s) |
| 型別 | `npx tsc -b` | exit 0,零輸出 |
| Lint | `npx eslint src` | exit 0,零輸出(含零 warning) |
| Build | `npm run build` | exit 0,built in 893ms |

對照:Phase 3 收工 1100 條 → 修復輪 **1115 條**(+15:sha-plugin +7、useServerBuild +6、
VersionDriftBadge +2)。基線 1069 條既有測試仍**零變紅**。backend 仍零 `.py` 改動。

## 9. 真實環境重驗(改用 `?since=` 驗 behind)

vite dev 起在 5199(不碰 TC4、不碰 8721),六案對照:

```
1) 無 since                              -> {"git_sha":"ba31a8e","behind":null}
2) since=ba31a8e(= HEAD,空 range)       -> {"git_sha":"ba31a8e","behind":false}
3) since=<root commit>                   -> {"git_sha":"ba31a8e","behind":true}
4) since=b9a1add(本輪起點,其後 10 個
   commit 全是純前端)                    -> {"git_sha":"ba31a8e","behind":false}   ← C3 的核心
5) since=4625d91(其後有 copycat/ commit) -> {"git_sha":"ba31a8e","behind":true}
6) since=「abc; <shell 元字元注入串>」    -> {"git_sha":"ba31a8e","behind":null}
```

第 4 案就是 C3 要修的東西:HEAD 比 `b9a1add` 前進 10 個 commit,但沒有一個動到 `copycat/`
→ **behind false,膠囊不亮**。修復前的等值比對在這個情境下會亮燈(sha 明明不同),正是
「本 repo 工作流下近乎恆亮 = 雜訊化」的來源。

同行程 liveness(不重啟 vite,只移動 HEAD;兩個 commit 的 `vite.config.ts` 與 `sha-plugin.ts`
逐位元組相同 → 不觸發 vite 的 config 熱重啟):

```
at HEAD=ba31a8e: {"git_sha":"ba31a8e","behind":true}
at HEAD=da1ea7a: {"git_sha":"da1ea7a","behind":true}   ← 同一行程,值跟著 HEAD 走
at HEAD=ba31a8e: {"git_sha":"ba31a8e","behind":true}   ← 復原
```

**踩到並記下(Phase 6 取證時會再遇到)**:`git checkout` 若跨過「`vite.config.ts` 有改動」的
commit,**vite 會偵測 config 變更自動重啟整個 dev server** —— 期間 `/__build/sha` 會退化成
SPA fallback(回 index.html 而不是 JSON),而且重啟後的行程是新讀一次 config 的,
「同一行程現算」的判別式在那種取法下**是被污染的**。本輪第一次嘗試 detach 到 `4625d91`
(該 commit 還沒有 plugin)就是這樣拿到 HTML 的;改用同 config 的相鄰 commit 後才成立。
Phase 6 若要重現,只在「config 未變」的 commit 之間移動 HEAD。

驗完 vite 行程已關閉(5199 不再 LISTENING),工作樹回到 `feat/frontend-version-drift` 且乾淨。

## 10. 修復輪 commit 清單

| sha | tag | message |
|-----|-----|---------|
| `23aae13` | [red] | 🟢 test(frontend): add failing test for C3 /__build/sha range 判別 |
| `a703e50` | [green] | 🔴 fix(frontend): /__build/sha 升級 range 判別,帶 copycat/ 路徑過濾 |
| `da1ea7a` | [red] | 🟢 test(frontend): add failing test for C1/C2/C4~C9 range 判定與來源選擇 |
| `ba31a8e` | [green] | 🔴 fix(frontend): dev 判定改吃 middleware 的 behind,只有 404 才降級 define |

兩個 green commit 的 body 都註了 `Phase 4 review fix: <ids>` 與 `red→green for <red-sha>`。
修復輪的 green 用 🔴(行為改動)而非 🟢 —— 這輪改的是既有判定行為,不是新功能。

## 11. 修復輪的判斷記錄(與清單的落差)

- **`:/copycat` 而不是 `copycat`(C3 實作細節,實測過)**:vite 的 cwd 是 `frontend/`,
  git pathspec 相對 cwd 解析 → `-- copycat` 會被解成 `frontend/copycat`(不存在),
  git **正常結束、輸出為空** → `behind` 恆 false 的靜默失效。實測:在 `frontend/` 下
  `git log <root>..HEAD -- copycat` 回 0 列,`-- :/copycat` 回 3+ 列。改用 top-level magic
  pathspec `:/copycat` 才等價於 CLAUDE.md §8 的 `-- copycat/`。
- **`useBuildDrift` 回 `{mode, fe, behind}` 而不是 design 字面的 `{fe, behind}`**:design 有兩處
  對 `behind === null` 的處置不一致 —— §語意 說「git 失敗 / since 非法 → 不判定」,
  §落地細節 說「build → versionDrift 等值比對」。若只有 `{fe, behind}`,「dev 問到了但
  middleware 說不知道」與「build 產物語意」兩種 `behind: null` **無法區分**,前者會掉進
  等值比對 → 正好是 C3 要消滅的誤報。加一個 `mode` 標籤把 design 的四個分支 1:1 標記
  (`equal` / `range` / `equal` / `unknown`),兩節就都成立。
- **`VersionDriftBadge` 拿掉 `feSha` prop**:C3 之後 dev 的判定來源是 `behind`,不是 fe/be 等值,
  「只注入 fe」的縫**表達不了 dev fixture**(注入了 fe 仍得 mock `/__build/sha` 才有 behind)。
  R2 當初要這個縫是為了「測試不依賴機器 git 狀態」,而現在 dev 路徑的 fe/behind 都來自
  被 mock 的 route、build 路徑來自 `vi.stubGlobal("__GIT_SHA__")`,機器 git 狀態已完全不在
  元件測試的依賴裡 —— 縫的目的達成,縫本身可以拆。
- **fake timers 下 `advanceTimersByTimeAsync(0)` 推不動兩段式**:health → `/__build/sha`
  的第二段(since 來自第一段回應)在 0ms 步進下**五輪都不落地**(實測),改 1ms 第一輪就
  到位。C2 的兩條載重路徑測試因此用 `[ms, 1, 1]` 三段推進,不是 `0`。單段的 query 用 0ms
  照樣落地(hook 測試那幾條沒改)。
- **C6 的 `staleTime` 有測試守**:「同 client 卸載後短時間內重掛 → 兩條 query 都不重打」,
  否則這個常數是啞的(改成 0 也不會有測試變紅)。

## 12. 修復輪 scope 外衝動(記錄,未動手)

- `behindSince` 每次請求 fork 一個 git 子行程(Windows 上數十 ms)。想加 memo(以
  `since|HEAD` 為鍵)但那會跟「每請求現算」的核心語意打架 —— staleTime 5s 已經把
  聚焦 / 重掛風暴壓掉,不再多做。
- `driftOf()` 是純函數但留在元件檔內(未搬進 `lib/version-drift.ts`)。搬過去要連帶把
  `BuildDrift` 型別也搬,而它現在住在 hook 檔 —— 為了「更好放」而動兩個檔的邊界,
  不在本輪 scope。
- `versionDrift()` 現在只剩 `equal` 模式在用(dev 走 behind)。它仍是 build 產物語意的唯一
  判定,不動;但若日後確定不會有 build 部署形態,這個函式與 `frontendSha()` 可一併收掉。
