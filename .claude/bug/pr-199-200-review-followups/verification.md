# spec #192 整體 review(PR #199 + #200)收修(`fix/pr-199-200-review-followups`)— verification

來源:`pr-199-200-review.md`(2026-09-07 /pr-review 對 range `53d8f15c..60137dae`,CC 單軸六分片 + 兩批獨立 worktree 內部複查)
findings F-01–F-47:Must 0 / Should 0 / Nice 46 / 參考用 1(校正後 MEDIUM 13 / LOW 34)。user 2026-09-07 拍板六條 ask-user:
**F-01 (b)** 研究 `combo_wlpolicy.py` 改 `late == 0` 重跑、HANDOFF §8.2 表更新 / **F-10** 啟動那趟回填只在已過 13:40 才立即跑(開盤前
起動不跑)/ **F-11** 研究 `nosig.py` 加「哪些 kind 算訊號」參數 + CLAUDE.md 契約措辭 / **F-14 (a)** 無族群 S 列第三行「無族群・…」/
**F-20 (a)** 只改文件 / **F-31 (b)** 回填順手補 `d_close` / `d_high`;auto-fix 40 條全修;F-47 no-op。**推播窗維持 12:30 不改**(user 曾提 13:20,最後拍板不改)。
分支自 master `60137dae` 切出(worktree `.claude/worktrees/fix-pr-199-200-review-followups`,前端 `npm ci` 自裝,後端用主 tree venv)。

## 1. commits(🔴 fix(+ 對應測試)→ 🔴 fix(frontend) → 🔵 refactor → chore docs,三類不混;sha = 分支上的,merge 後見 PR)

| sha(分支) | 類 | 內容 |
|---|---|---|
| `d18f4b67` | 🔴 fix(signals) | F-10 start 只在已過時點跑 / F-31 `d_close` `d_high`(emit 初值 + 回填補、舊列缺鍵一併加)/ F-03 排除組名零命中 WARNING / F-25 peers_fn 失敗計數 + 換日彙總 / F-22 群組失敗 log 點名族群 / F-24 目錄不存在 INFO / F-28 `policy_outcome_days` < 1 raise / F-29 滿載 skip_note / F-26 tick 時刻解析失敗跳過 / F-27 `policy_quotes(codes)` 必填;同 commit 含紅先行測試 21 條(F-02 / F-04 / F-05 / F-06 / F-07 / F-08 / F-09 / F-39 / F-40 / F-41 / F-42 / F-43 / F-44 / F-45 + 新行為各一案)與三條「該變」(排程案 / `_POLICY_KEYS` 多兩欄 / 滿檔案斷後果) |
| `ddb1a537` | 🔴 fix(frontend) | F-14 無族群第三行 / F-17 零值正號 `signedPct2` / F-18 `policyTitle(policies)` when 段 per-tag / F-19 `peer_touched ??` + 刪 dead 三元;紅先行:F-13 混合組不淡 / F-15 併入雙嗶 / F-16 起點錯開 / F-21 anchor 最早到 |
| `80ea7eed` | 🔵 refactor | F-32 `signal_policy` docstring 三條差異 / F-23 app.py 註解;零行為 |
| `1ee97f92` | chore docs | F-35 §0 目錄樹 / F-20 (a) + `d_*` + 零值正號 §4 政策列契約 / 回填契約跟上行為 + F-11 措辭 / 族群契約 WARNING / F-33 F-34 CONTEXT.md / F-12 skill bullet / F-36 兩份 verification merged sha / F-37 證據宣稱收斂 + curl 摘要註記 / F-38 mod round-1 json per-finding schema |

repo 外(研究目錄 `C:\Users\USER\Documents\copycat-trading-review`,不在 PR):`scripts/combo_wlpolicy.py`(`late == 0`,COLS 加 `late`,docstring 記舊口徑)、
`data/combo/wlpolicy.out` 重出(舊表備份 `wlpolicy.out.pre-0907.bak`)、`HANDOFF-2026-09-06-signal-research.md` §8.2 表更新(排除 ALL IN 36/+5,497/22% → 35/+5,784/23%;
自選 43/+4,703/23% → 42/+4,923/24%;P 相關 126/+3,132/18% → 120/+3,324/19%;S 全時段 110/+1,313/15% → 99/+1,433/17%;強勢股 102/71 → 91/67)、
`scripts/nosig.py`(`SIGNAL_KINDS`:`policy` 參數 = 只認政策列,預設 legacy 舊六種;兩模式冒煙皆跑得動)。

## 2. 紅 → 綠(紅先行證據)

補丁分兩段套:先只套測試(六檔)跑 → **11 failed / 666 passed**;紅的恰是新行為(排除組名 WARNING / 快照失敗彙總 / 排程不在 start 跑 ×2 /
目錄不存在 INFO / days 驗證 / `d_close` `d_high` / 滿載 skip_note / `_POLICY_KEYS` 該變 / 逐檔 gap)+ 兩條我寫錯前提的案(stale 案 ctx 與 tick 同日不會被擋、
bogus 案回看基準也被毒掉)—— 改序列後與實作一起綠。守門型案(6.00 恰等 / leader 平手 / round / 鎖死賣側空 / 簇窗回看界 / 群內重複達標 / session gate /
hub 落後守門 / 零補不重寫 / 例外傘)在紅段就綠是**正確的**:它們釘現行正確行為,對應突變體在 review 內部複查已序列實跑(V2:17 發 16 存活 1 被 golden 殺)。
前端同法:先套測試 → **9 failed**(零值正號 / 無族群第三行 ×2 / peer_touched null / policyTitle 簽名 ×3 + per-tag ×2);套實作 → 149 passed。
兩條 hook 測試(併入雙嗶 / 起點錯開)紅段即綠 = 守門型。

## 3. 完成前 gate(全綠;`1ee97f92` 工作樹)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q` | **3516 passed, 3 skipped**(209.03 s;master 3494 → +22) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five …/out/five_tigers --run-four …/out/four_tigers` | **42/42 PASS** | 0 |
| `npx vitest run`(frontend/) | **154 files / 3024 passed**(master 3006 → +18) | 0 |
| `tsc -b` / `eslint src` | 零輸出 | 0 |
| `react-doctor --scope changed --base 60137dae --json` | newCount 0 / fixedCount 0 / baseTotalCount 0(中途曾抓到我新寫的 `.filter().map()` 一條 `js-combine-iterations`,改單迴圈後歸零) | 0 |

## 4. 真實環境判準(留給 user;prod 尚未重啟)

- 重啟後啟動 log:「T+1/T+2 回填 worker 起動:每日 13:40:00 跑一次(已過時點起動則立即跑;最近 5 個日檔)」;**開盤前起動不會有回填 DK**(`grep "T+1/T+2 回填" logs/server-*.log` 在 13:40 前只有起動那一行)。
- 13:40 後 log「T+1/T+2 回填 2026-09-07:回填 n 列」;`data/signals/20260907.jsonl` 政策列多出 `d_close` / `d_high`(舊列缺鍵一併加)與 `t1_open` / `t1_date`。
- `grep "排除組名" logs/server-*.log` = 0(自選有「ALL IN」組);把該組改名再重載自選 → 恰一行 WARNING。
- rail:S 政策列(無族群)第三行印「無族群・+x.x%/停 y.y%」;hover 仍「盤前篩選名單・無族群濾網」;政策 + raw 掃單簇混合列不淡色。
- `frontend/dist` 落後,preview 前 `npm run build`(畫面「版本落差」膠囊會提示)。

## 5. two-axis review 處置(fixed point `60137dae`,兩軸皆 opus;細節 `code-review-round-1.json`)

標準軸 8 條:**修 5**(F-01 / F-02 重複貼上去重、F-03 hover 無族群略同伴段、F-04 刪 `groupPolicyAnchor`、F-07 兩行 format)/ 否決 1(F-05 `fmtPct` 加參數)/
知情 2(F-06 🔴 commit 含紅先行測試 —— 與 #200 同形;F-08 `asyncio.sleep` monkeypatch 範圍)。spec 軸 3 條全修(S-01 = 重複貼上含 CLAUDE.md 族群段、
S-02 補 F-46 route 往返案、S-03 = F-04)。白名單 W1–W12 破壞:無。

**教訓(進 next-time)**:補丁腳本的冪等判斷 `if old not in t and new in t: continue` 在「new 包含 old」時失效 → 第二次跑會再貼一份;測試全綠掩蓋(vitest 同名 it 照跑、
Python 重複 if 區塊無害)。兩軸各自獨立抓到同一根因是這輪 review 的價值。

**round-1 收修後最終重跑(`HEAD` 工作樹)**:後端五檔 440 passed / ruff All checks passed / pyright 0 errors;vitest **154 files / 3015 passed**(去重 −9)/ tsc 0 / eslint 0 /
react-doctor newCount 0;全量 pytest 3516(round-1 前)+ 1(F-46)—— 見 PR body 最終數字。
