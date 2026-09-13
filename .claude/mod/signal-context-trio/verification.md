# verification — mod/signal-context-trio(#224;T1 #225 / T2 #226 / T3 #227)

worktree `C:\side-project\copycat\.claude\worktrees\mod-signal-context-trio`,base = master 1a032b9b。
後端指令一律走主 tree venv 絕對路徑(worktree 無 .venv,ops-discipline);前端 `npm ci` 於 worktree。

## 1. 自動化 gate(auto-verify;§4 為最終一輪,§2–§3 為 review 收修前的中途輪)

### 1.1 紅先行(tdd)

| Ticket | 紅測試 commit | 紅時失敗數 | 綠 commit |
|---|---|---|---|
| T1 CDP 列閘 | 4dfcc039 | 5 failed(TestCdpGate 五案 + 設定預設值;「恰等門檻」案未改動前即綠 = 白名單鎖) | 44510b08 |
| T3 大單筆數格 | 3de16465 | 19 failed(TestBigLots 13 + 政策列 / Discord / hub detail 6) | d440dcb7 |
| T2 放量離開 kind | 2156bf29 | `-x` 首紅 `test_seven_switch_keys_and_kind_map`(開關鍵七鍵);全批含 TestVolBreakout 11 / 規則 / 遷移 / 前端 | 3a3964f7 |

### 1.2 中途輪(T2 綠後、review 前)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q`(全量) | 3624 passed, 3 skipped(既有 skip)in 210 s | 0 |
| `npx vitest run`(全量) | 156 files / 3074 passed | 0 |
| `ruff check copycat tests` | All checks passed | 0 |
| `pyright`(全專案) | 0 errors | 0 |
| `npx tsc -b` / `npx eslint src` | 無輸出 | 0 / 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 9 files, No issues found | 0 |
| `copycat validate --run-five <主 tree out/five_tigers> --run-four <…four_tigers>` | 42/42 PASS | 0 |

`ruff format --check` 對觸及的既有檔仍列 hunks —— 全部是 master 上本來就未 format 的區段(逐 hunk 核過:
`signal_hub.py` 1224/1434/1562、`test_signal_hub.py` 672/969/1189/2742、`test_signal_state.py` 1325/1362),
新增區段以 `--range` 格式化;依 backend-conventions 不順手重排既存格式(review F-03 抓到 formatter hook
動過 `TestSweepClusterGates` 兩段 → a897d3ae 還原)。

## 2. 真實環境(closeout §2:happy + ≥ 2 edge + 2 個未改功能;零 TC4 / 零 ZMQ,prod 8721 不碰)

側車 `evidence/sidecar_server.py`(fake source + `neutralize_external_env`;偵測器 09:00–13:30 牆鐘閘放寬,
tick 時刻照劇本 09:2x–09:4x;port 8730)+ `npx vite --config vite.sidecar.config.ts --port 5180`(臨時檔,
已刪)+ chrome-devtools MCP 截圖。2026-09-14 01:55 執行,證據在 `evidence/`:

| # | 劇本 | 預期 | 實錄(`signals_today.json` / `sidecar.log` / 截圖) | 判定 |
|---|---|---|---|---|
| happy-1 | 2330 日 K 前 5 日 +11.1% → 09:21 由下穿 NH | 一列 `cdp_cross` levels `["nh"]` | `cdp_cross 2330 09:21:00 from_below ["nh"] notify=false` | PASS |
| edge-1 | 2317 日 K 五根同收盤(+0.00%)→ 同樣穿 NH | **零** `cdp_cross`;log 一行 INFO | `signals_today` 無 2317 任何列;`sidecar.log:8` `INFO … CDP 列閘:2317 前 5 日累計 +0.00% < +5.00%,今日 CDP 不評(基準日 2026-09-14)` | PASS |
| happy-2 | 2454 09:20 + 09:30–09:39 每分鐘 10 張同價 → 09:40 離帶 +1% 40 張 | 一列 `vol_breakout` up;倍率 = 40 ÷ (101 ÷ 11 分)= 4.36 | `vol_breakout 2454 09:40:00 up 4.3564 notify=false levels=[]`;rail 印「放量向上離開 4.4 倍」紅字淡色 | PASS |
| happy-3 | 2330 09:31 暖機 30 筆 + 09:31:40 大單(10 張、外盤、價升)→ 09:33 兩個同毫秒群 | 掃單簇 `detail.big_lots_120s = 1`;2330 在「盤前篩選」→ S 政策列頂層 `big_lots_120s = 1`、`sweep` 四鍵 | `sweep_cluster … detail={n30:2, levels:2, qty:6, up_pct:0.789, big_lots_120s:1}`;`policy S … big=1`;rail 第三行「無族群・+2.2%/停 7.6%・大單 1 筆」(`rail_2026-09-14.png`) | PASS |
| edge-2 | 舊列(缺 `big_lots_120s`)第三行 | 與修改前逐字相同 | 單元測試 `SignalRail.test.tsx`「#227 … 舊列缺欄第三行不變」+ `test_policy_card_line2_without_big_lots_key_is_unchanged`(真環境無舊列可造:jsonl 由本分支寫出必帶欄) | PASS(測試層) |
| 未改-1 | `/api/health` | 200、`git_sha` = 分支 HEAD | `health.json` `git_sha: 8bc115ab`(當時 HEAD) | PASS |
| 未改-2 | `/api/stock/state/2330?tape=0` 快照 / 自選側欄三檔報價 | 形狀不變、`tape_omitted` | `state_2330.json`;截圖側欄 2330 51.1 +2.20% / 2317 50.6 / 2454 101 | PASS |
| UI-1 | 監聽規則區 | 多一列「放量離開 開」 | `rail_2026-09-14.png` 末列 | PASS |
| UI-2 | 規則視窗 | 卡「放量離開」摘要「±0.6% 帶內 600 秒 · 離帶 4 倍 · 冷卻 600 秒」;編輯表單三欄「帶寬 ±% / 最短停留(秒)/ 離帶分鐘量倍率」、種類下拉七類 | `rules_dialog_2026-09-14.png` / `rules_edit_breakout_2026-09-14.png` | PASS |

順帶觀察(非本案):2454 離帶那筆同時由下穿 NH(日 K 100.00 ±0.5 → NH 100.50)→ rail 同 tick 合併列
「突破 CDP NH・放量向上離開 4.4 倍」,合併列 SC-5 既有語意。

**prod 判準(user 重啟 + build 後,影子期內)**:
- 盤前 basis sweep 後 `grep "CDP 列閘" logs/server-*.log` = 前 5 日未漲 ≥5% 的自選檔各一行 INFO;整批全「日 K 不足」= 抓取根數被改小(不是資料源壞)。
- rail 的 CDP 穿越列只出現在 log 沒被列閘擋的檔;圖上 CDP 五線照舊。
- 掃單簇 / 政策列第三行尾有「大單 n 筆」(0 也印);`grep '"big_lots_120s"' data/signals/<日>.jsonl` 每列政策列都有。
- 監聽規則區多「放量離開」(通知關);有事件時 rail 淡色列「放量向上/向下離開 x.x 倍」,無 toast / 嗶 / Discord。
- 規則檔:首次 upsert 後 `data/signal_rules.json` `_cache_version` = 5、末張「放量離開」。

## 3. Two-axis review(closeout §1)→ `code-review-round-1.json`

（見該檔;Standards 7 條全收修:F-01 型別 / F-02 壞資料 WARNING 分講 + 紅先行 / F-03 還原重排 / F-04 改名 /
F-05 收成 `_quiet_seed_rule` / F-06 bool 守門 / F-07 判斷題不動;Spec 軸見該檔。）

## 4. 最終輪(review 收修後,推送前;HEAD = f06b9c08 + docs / artifacts commit)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q`(全量) | **3626 passed**, 3 skipped(既有)in 207 s(比中途輪 +2:F-02 壞資料案 + S-01 續跑案) | 0 |
| `npx vitest run`(全量) | 156 files / **3074 passed** | 0 |
| `ruff check copycat tests` | All checks passed | 0 |
| `pyright`(全專案) | 0 errors | 0 |
| `npx tsc -b` / `npx eslint src` | 無輸出 | 0 / 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 9 files, No issues found | 0 |
| `copycat validate --run-five … --run-four …` | 42/42 PASS | 0 |

真實環境節(§2)在 S-01 收修**之前**取證;S-01 只影響「離帶筆之後同分鐘續跑出新錨的帶」這一支(劇本 happy-2 的
離帶筆 40 張一筆即達標,不經那一支),故不重跑側車,由紅先行測試
`test_follow_up_tick_leaving_the_new_anchor_band_keeps_the_break_minute_accumulating` 釘住。

`[auto-default]` 全清單見 change-spec §3(Q1–Q17)+ 本次流程層:worktree 開工時主 tree 兩個既有髒檔
(`.claude/feat/live-last-bar/verification.md`、`.claude/mod/w2-daily-bars-and-screen-0800/verification.md`,前次觀察
session 實錄)不 commit 不 stash、留在主 tree(worktree 自 origin/master 切,不受影響)。
