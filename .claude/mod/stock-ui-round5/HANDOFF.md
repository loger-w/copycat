# stock-ui-round5 交接(2026-07-30)

**規格 source of truth = `change-spec.md`**(含兩輪 review 的 28 條 amendment)。
本檔只講「進度 + 環境陷阱」。

## 工作區

- worktree:`C:\side-project\copycat\.claude\worktrees\mod-stock-ui-round5`
- 分支:`mod/stock-ui-round5`(base = master `f1677bc`)
- **這個 repo 沒有任何 remote** → branch-lifecycle 收尾走離線 `--ff-only` fallback,不是 PR

## 流程狀態

**已收尾:2026-07-30 rebase 到 master 後 `--ff-only` merge 完成(master = `235f70f`,本輪 20 個
commit;repo 無 remote → 離線 fallback,不是 PR)。分支與 worktree **刻意保留** —— 後端 server
與 vite dev server 都從這個 worktree 跑,砍掉會斷線。**

`/auto` + `/mod`,Phase 0-4 全過;**Phase 5 的畫面驗收未做**(見「還沒做的事」)。

**退出條件**:量化 gate 全綠(已達成,見下)+ change-spec 白名單 W-1~W-24 逐條保留
+ 四大項成功條件 SC-1~SC-22 交 user 過目(**未做,需要畫面**)。

## 進度:7 個工作單元全部完成(13 個 commit)

| # | 內容 | commit |
|---|---|---|
| 1 | 後端 tick 買賣價 + `StockDayState` 當日高低 running max/min | `1d6e7c6` + `1cf85f7` |
| 2 | 江波圖右緣帶 / 量 bar 置中 / 總量堆疊 / 左軸漲跌配色 | `781b071` + `d4791ab` |
| 3 | 後端自選 schema v3 + API `codes` + 訂閱池(§🔴-4 / §🔴-5) | `abcd573` + `b2ec3fb` |
| 4 | `watchlist-model.ts` 12 支純函數(§🟢-7) | `d2bad66` + `13735a8` |
| 5a | hook 上 v3 契約 + `errText` 抽出(§🔴-6);側欄機械適配 | `aed7f61` + `7ca7c54` |
| 5b | 管理群組與股票 Dialog(§🟢-10) | `f6c0316` + `4688e83` |
| 5c | list-drag 未分組 zone + 側欄改版(§🔴-8 / §🔴-9) | `76b173f` + `7857fbf` |
| 6 | 明細五欄 + 當日高低進 accum(§🔴-11) | `0b1cdb5` + `5a9981b` |
| 7 | 江波圖高低線與現價圈 + K 線視窗高低標(§🟢-12 / §🟢-13) | `b8dbf01` + `d5d7913` |
| — | 收尾:Dialog「無變化」不再誤報 BAD_GROUP | `f401af7` |

**與原計畫的兩處刻意偏離**(理由已寫進 commit message):

1. 原「commit 5 側欄 + commit 6 Dialog」拆成 5a/5b/5c —— 側欄改版要刪掉群組增刪 /
   ⊞ 多組勾選的測試,而等價測試住在 Dialog 測試檔。照原順序做會出現「測試已刪、
   等價測試還沒生出來」的覆蓋空窗。改成先上 hook 契約、再長 Dialog、最後拆側欄。
2. Dialog 群組列**沒做** spec 草圖裡的 `⋮⋮` 排序握把:SC-14 沒有「群組排序」這條,
   不長沒有行為的 UI(鐵則 B)。

## 量化 gate(全綠,2026-07-30 21:4x 實跑)

| 指令 | 結果 |
|---|---|
| `pytest -q` | **1390 passed, 1 skipped**(改動前 1379 passed) |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors, 0 warnings |
| `copycat validate`(帶主 repo 的 out/) | **42/42 PASS** |
| `npm test`(frontend/) | **63 files / 716 tests passed**(改動前 61 / 648) |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |

## 還沒做的事(Phase 5)

1. **重起後端才看得到新欄位** —— port 8721 目前跑的是**主 repo master 的 build**
   (PID 15012,`C:\side-project\copycat\.venv\Scripts\python.exe -m copycat.server`,
   16:54 起跑,parent 是另一個 claude session)。它有 round 4(`/api/stock/names` 回 200)
   但沒有 round 5 的 `codes` / `high` / `low` / tick `b`/`a`。
   ⚠ **不要另開 port 並存**:CLAUDE.md §8「TC4 同 symbol 跨 session 只推一邊」,
   兩個 server 同時訂個股會有一邊靜默零推播。要驗就是砍掉 15012 再從本 worktree 起。
2. **`data/stock_watchlist.json` 已備妥**(本 worktree,gitignored):
   主力 [2330, 4989] / 觀察 [3231] / **未分組 2317** —— 未分組桶與 SC-9/10/12 的素材。
3. **SC-1~SC-22 的畫面對照**:本 session 全程開不了瀏覽器
   (chrome-devtools MCP 的 profile 被並行 session 佔住、claude-in-chrome 擴充未連線),
   畫面類一律要 user 截圖。

## 環境陷阱(全部真踩過)

| 事項 | 處置 |
|---|---|
| worktree 沒有 `.venv` | 用主 repo 的 `C:/side-project/copycat/.venv/Scripts/python` |
| worktree 沒有 `out/` | `copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four C:/side-project/copycat/out/four_tigers` |
| Bash tool 每次呼叫都會把 cwd 重設回 round4 worktree | 每個指令自己 `cd <round5 worktree> && …` |
| `spikes/TCPY` / `frontend/node_modules` | 已就位,不用再處理 |
| `.claude/` 是 gitignored | mod artifacts 不進版控,只活在這個 worktree |
| `git add -A` / `.` | 被 safety hook 擋 → 一律列明確檔案路徑 |
| LSP 診斷 | 改完型別後會有一段時間報舊快取的錯,以 `tsc -b` / `pytest` 為準 |

## 已鎖定的決策(不要重新討論)

1. 未分組桶語意:`codes`(全體)+ `groups`(成員關係),**未分組 = codes − ∪groups 衍生不另存**
2. Enter 後股票**持久化**進未分組;未分組列的 `+` 指派群組,零群組時 `disabled`
3. 管理 Dialog **取代**側欄的 `⊞` 面板(一檔多組改在 Dialog 做)
4. 跨群組拖曳 = **移動**;拖進未分組 = 從**所有**群組移除
5. 現價小圈**只做江波圖**;K 線圖只加視窗高低標
6. 明細漲跌基準 = `meta.ref`;量的顏色依內外盤
7. `<dialog>` 開關**只由 effect 驅動 + feature-detect**,`open` 不進 JSX
8. 當日高低資料源 = 後端 running max/min(**不是** TC4 `HighPrice`/`LowPrice`)

## 一條教訓(已寫進 spec §項 2)

user 回報「交易量對應不到十字軸」時,我用選項題讓他勾症狀,他勾了「垂直線沒穿進量區」,
我就去查 **K 線圖**的幾何,量了很久全部對得上 —— 因為症狀根本在**江波圖的副圖**。
**畫面類問題先要截圖,不要拿選項讓 user 猜我的用詞。**
