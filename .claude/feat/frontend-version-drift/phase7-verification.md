# phase7-verification:frontend-version-drift

2026-08-05,HEAD ba31a8e。重讀 brainstorm.md 逐 SC 核對(SC-6 為 R1/C3 兩輪 amendment 後語意)。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 define 嵌入 sha(git 不可得不炸) | frontend/sha-plugin.ts(gitSha)+ vite.config.ts define | sha-plugin.test.ts(格式/降級)+ version-drift.test.ts define 注入條;`npm run build` exit 0 | dist 產物含當時 HEAD sha(gate-output.md);curl 回 git_sha 現值 | 既有 build 流程(166 modules 綠) |
| SC-2 /api/health 60s 輪詢、失敗不誤報 | hooks/useServerBuild.ts | fake timers 邊界(60_000−1/+1)+ `HEALTH_POLL_MS` 字面斷言 + 500 終態 | 真後端 health 回 8ef1346(round-1 JSON) | App 既有 26 條測試零變紅 |
| SC-3 versionDrift 判定表 | lib/version-drift.ts | 判定表 5 列 + 空字串 + frontendSha 兩態 stub | build 模式語意留待部署(Known Risks) | — |
| SC-4 膠囊兩態(nav 右側/零 DOM) | components/VersionDriftBadge.tsx + App.tsx wrapper | 元件兩態 + App 落點(wrapper ml-auto/badge 不帶/IndexBar sibling)+ 負例 settle 突變驗證 | 健康態:真後端天然情境不亮 + 截圖:evidence/SC-4_healthy-nav-no-badge.png;drift 態:DOM 全查證(title 逐字/座標)+ evidence/SC-4_drift-state-page.jpg + user 過目 | nav 既有 5 tab / IndexBar 版面 |
| SC-5 warn 恰一次 + pair 去重(含載重路徑) | VersionDriftBadge.tsx(driftMessage 單一來源) | warn 內容/一次/pair 變化/drift 消失再現仍 1 次(C2 突變會紅) | title 真環境逐字同源驗證 | — |
| SC-6 dev range 判別(-- copycat 過濾) | sha-plugin.ts(behindSince + ?since=)+ useServerBuild(useBuildDrift data-first) | middleware 三態 + 注入拒絕 + 來源選擇(暖態 error 沿用 data/僅 404 降級/500→null/PROD stubEnv) | curl 三案(behind false/true/null)+ 天然健康態不亮(10 個純前端 commit)+ detach-HEAD 判別式 | — |

- 無 FAIL;rollbacks 空。UI SC 的 user 過目為最終關卡(收尾回報列操作路徑)。
