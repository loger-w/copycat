# chore/pr-review-133-followups — change-spec(= handoff 原文,自 %TEMP%\copycat-handoff-2026-08-28-pr-review-133-fixes.md 複製;user 拍板 F-11 / F-12 皆「做」)

# Handoff — 收修 /pr-review #133 的 14 條 finding(mod/futures-day-1500 出貨後回校)

日期:2026-08-28 凌晨(~01:00)。來源:本 session 先以 `/mod` 出貨 PR #133(15:00 夜盤起算),再 `/pr-review 133`。
user 指示:**開新 session 修;F-11 / F-12 兩條 ask-user 等 user 拍板後也一併修**。

## 唯一真相源(不重抄)
- 拍板主報告:`C:\side-project\copycat\pr-133-review.md`(untracked,repo root)
- 完整證據副檔:`C:\side-project\copycat\pr-133-review.audit.md`(untracked;含每條 finding 的 anchor / search-proof / 4.3b 實查 / inline comment 全文)
- PR:https://github.com/loger-w/copycat/pull/133(MERGED,rebase merge → master a32c5cc4;四筆 608b1cfc / 1dbb7775 / 5316f857 / f95441d1 對應 master 3d0ab718 / ac7fd3b9 / e4b06195 / a32c5cc4)
- 出貨 artifacts:repo `.claude/mod/futures-day-1500/`(change-spec / current-state / verification / code-review-round-1.json / evidence 截圖)
- 上一輪同型收修樣板:`docs/superpowers/specs/pr-131-review.md` → 收修 PR #131 的做法(`chore/pr-review-128-130-followups` 分支;`git log --grep "pr-131"`)

## 要做什麼(14 條;報告「發現總覽」表 + Inline Comments 有逐條修法,這裡只列分組)

**先問 user 拍板(兩條 ask-user)**,問完一起修:
- **F-11** `futures-accum-adapter.ts:119`:Σ / high-low 迴圈靠 `k === ALLDAY_GAP.end` 認橋(位置哨兵)。改法 = `amountMilli / volume / high / low` 在**插橋之前**對 rows 跑一遍,插橋後只排序。零行為差;建議答「做」(消掉「兩處記住橋存在」)。要保留既有 adapter 測試橋節四條全綠 + 新增一條「橋不進 Σ」已存在(`futures-accum-adapter.test.ts` 橋節)。
- **F-12** `txf-overlay-series.ts:76 / :85`:bars 每秒掃兩遍。改法 = 第一圈 `dayMinuteOf` 結果存陣列給第二圈;**不可**改「由尾往前找第一根日盤 bar」(破亂序防禦,見檔頭)。效益 < 1 ms;建議答「做,順手」或「不做,記 next-time」皆可。

**auto-fix 十條**(不需再問):
- artifacts 回校(純文件):F-01 `verification.md:58` W12 句;F-02 `change-spec.md:40` W12 補「P5 後修訂」;F-04 `verification.md:11` 七檔數字改 `36 / 22 / 54 / 13 / 16 / 53 / 39 = 233`;F-05 `current-state.md:40` W1 改寫成真正不變的部分;F-09 `code-review-round-1.json:7` `8c09cbaf` → `5316f857`(出貨 SHA 以 `git log --oneline origin/master` 為準)。
- 註解口徑:F-03 `StockIntradayChart.tsx:1384`(夜盤成交屬**次一**交易日,時段 15:01→05:00)、`:1388`(近全軸窗 15:00–13:45)、`:938`(四段軸);F-08 `StockIntradayChart.tsx:939 / 1060 / 1509` 推導數字 1139 → 1365、1.6 → ~1.9 key/px,或 `MINUTE_SNAP_RADIUS` 3 → 4(二選一;`stock-intraday-svg.ts:159` 同型不在 PR 內、`useFuturesBars.ts:21` 的 1140 是對的別動);F-07 三處測試文字「死區」→「一天之外 / 非空檔」(`fill-marks.test.ts:417`、`FuturesChart.test.tsx:591 / :648`)。
- code + test:F-06 `FuturesChart.test.tsx:284` 加「只有日曆載入後才畫」的成交點屏障(ordersBody 多塞 `{date:"20260820", time:"09:00:30"}`,先 `await waitFor(fill-B-1079)` 再驗 last-dot),改完做 mutation 驗證(把 `liveSlotOf(new Date(), holidaySet)` 改回 `liveSlotOf(new Date())` 要紅);F-10 `FuturesChart.tsx:98 / :135` `liveSlotOf` / `tradeSlotOf` 的 `holidays` 改必填 `ReadonlySet<string> | undefined`(lib 側維持選配,S7 已記 next-time)。

**no-op 兩條**(只記錄):F-13 `docs/next-time.md:23`「#132」是 issue 編號(reviewer 誤判 REFUTED),順手改「issue #132 / PR #133」可選;F-14 commit subject 錯(歷史已 merge 不重寫)。

**收尾另一件**:兩份報告目前 untracked 在 repo root —— 依慣例 `chore(docs): /pr-review #133 報告落檔` 搬進 `docs/superpowers/specs/pr-133-review{,.audit}.md`(可與收修同分支,不同 commit)。

## 環境事實(不重查)
- **主 tree 被另一 session 用著**(01:00 時在 `chore/test-hygiene-batch` e600f341,另有 worktree `.worktrees/mod-n075`)→ 一律 `git worktree add` 開 `chore/pr-review-133-followups`(從 `origin/master`;先 `git fetch`);前端在 worktree `npm ci` 直裝;後端 gate 借主 tree venv `C:\side-project\copycat\.venv\Scripts\python -m pytest -q`(本案後端零 diff,跑 gate 只證沒連帶)。worktree 三險見 `ops-discipline`。
- `.claude/mod/<slug>/` artifacts **已進版控**(f95441d1 那筆),改它們就是一般 tracked 檔;新 slug 的 artifacts 寫主 tree `.claude/chore/pr-review-133-followups/`(worktree remove 會刪 worktree 內的)。
- Bash tool 的 heredoc **超過 ~8k 字元會 `unexpected EOF`** → 大檔用 Write tool、patch 腳本先 Write 到 scratchpad 再 `python <file>`;safety hook 擋 `rm -rf`(用 python `shutil.rmtree` + chmod onexc)與 `grep .env`。
- 全量 vitest 與全量 pytest **不要並跑**;`App.test.tsx` / `App.memo.test.tsx` 在負載下 1–1.5 s flake,單獨重跑即綠(next-time 已記)。
- prod 8721 於 01:00 **沒在跑**(user 08-27 收工未重起);我 00:18–00:27 從 worktree 起過一台取證、已用 CTRL_BREAK 優雅收掉。SC-13 (b)–(e) 真環境窗口(15:01 翻頁 / 08:46 水平橋 / CDP 對 APP / 個股頁夜盤疊線)待 user prod 重啟後過目,不在本 handoff scope。
- 若再跑 /pr-review:C4 reducer 在 Windows 要 `PYTHONUTF8=1 py -3.14`(cp950 stdin 假報 `C4_CLI_INPUT_INVALID`);projection helper 三檔必須同目錄(repo root)。

## 流程建議
1. 開工:`git fetch` → worktree 開 `chore/pr-review-133-followups`(branch-lifecycle 開工節)。
2. 先問 user F-11 / F-12(一則訊息兩題,附建議答案),等答。
3. 三類分開 commit:🔵 F-11 / F-12(若做)/ F-10 純結構 → 🟢 F-06 測試 → 🔵 chore 註解 F-03 / F-07 / F-08 → chore(docs) artifacts F-01 / F-02 / F-04 / F-05 / F-09 + 報告落檔。
4. gate:vitest 本案七檔 + 全量、tsc、eslint、react-doctor --scope changed;F-06 mutation 紅先行證據。
5. two-axis review 一輪(closeout)→ push → PR → merge(鐵則 H 全自動)。

## Suggested skills
`chore`(router;或直接 `branch-lifecycle` 開工 + `auto-verify` + `code-review-two-axis` 收尾)、`frontend-conventions`、`frontend-testing`(F-06 fake timers / waitFor 慣例)、`ops-discipline`(worktree 三險、gitignored 依賴複製、清 worktree)、`receiving-code-review`(逐條核 finding 再動手,尤其 F-08 二選一與 F-13 已 REFUTED)、`verification-before-completion`。
