# W2 修改批(`mod/w2-daily-bars-and-screen-0800`)— verification

分支 `mod/w2-daily-bars-and-screen-0800`(worktree,自 master `de192ca3` 切出)。spec issue **#204**;tickets #205(T1)/ #206(T2)/
#207(T4)/ #208(T3)/ #209(T5)/ #210(T6)。grilling 拍板(2026-09-08):Q1 (a) 三支日 K 同吃 14:00 界、即時最後一根另開 `/feat`;
Q2 (a) 後端測試直讀前端字面;Q3 (a) 墊背不自救;Q4 (a) 前值落同一快取檔、不自動放寬;Q6 (b) 四支 hook 全修、`useIndexOverlay` 不動;
**Q7 (b) 盤前篩選改 08:00 目標交易日制**(取代原 A-3「每小時到翌日 08:00」);Q8 每 10 分鐘到 09:00 為止;Q9 目標交易日 = 今天;
Q10 處置股判今天;Q11 (a) 相對閘要。

## 1. commits(每張 ticket:test 紅先行 → fix / feat;🔴 / 🟢 / 🔵 / chore 分開)

| sha | 類 | ticket | 內容 |
|---|---|---|---|
| `674dbcea` | test | T1 #205 | 兩支開點函式(窗前 / 收盤後 / 跨週末 / 假日 / 14 天窮盡 / 與 `in*Hours` 起點同尺)+ `offHoursInterval` |
| `fed5fabe` | 🟢 feat | T1 | `msUntilFuturesTradingOpen`(08:46)/ `msUntilFuturesAllDayOpen`(08:40 / 14:55)/ `offHoursInterval`;三支共用 `msUntilNextOpen` |
| `22ccd6cc` | 🔵 refactor | T1 | `groupPollInterval` 改用 `offHoursInterval`(既有測試不改仍綠) |
| `300e3026` | test | T2 #206 | 三支日 K hook 各一條 14:00 界案;**既有 9 條事前標為該變**(期貨 4 / 加權 3 / 個股 2);後端 parity 測試 |
| `24bf6824` | 🔴 fix | T2 | `day-bars-rollover` 加第二道界(兩界取最小嚴格在後)、export `DAILY_FINAL_TIME`;三支 hook 只改註解 |
| `52318821` | chore(docs) | T2 | CLAUDE.md §4「日 K 定稿界前後端同值」契約 |
| `0c089bc1` | test | T3 #208 | 四支 hook 盤外自醒各一案;`barsPollInterval` 三案事前標為該變 + 量化案;既有「非交易時段不輪詢」只改標題 |
| `20ef3240` | 🔴 fix | T3 | 四支 hook 盤外回距開點 ms;`useIndexOverlay` 只加註解 |
| `847e0636` | test | T4 #207 | 排程判定兩案事前標為該變(08:00 / 目標交易日)+ `data_date_of`;compute 三 fetcher 日期;快取 v2 / v1 作廢;`TestTick` |
| `08d5dcae` | 🔴 feat | T4 | `RUN_TIME` 08:00;`expected_target_date` / `data_date_of`;compute 吃目標日;快取 v2;`tick()`;CLI `--date` |
| `508d8d8a` | chore(docs) | T4 | CONTEXT.md「盤前篩選」節(目標交易日 / 資料日);CLAUDE.md §0 / §1 |
| `00fa1545` | test | T5 #209 | `TestRetryWindow` 五案(注入時鐘 + fake sleep 推進時鐘) |
| `308ef4b9` | 🔴 fix | T5 | 重試時間盒 `RETRY_UNTIL` 09:00、`_MAX_ATTEMPTS` 退役、WARNING 降級 |
| `d06c1761` | test | T6 #210 | `TestDayTradeRelativeGate` 四案;`_engine` 加 `daytrade_floor` |
| `83b1d789` | 🔴 feat | T6 | 相對閘 0.8 / 絕對下限 1,000 / `daytrade_rows` 落檔 / `_read_cache` 收一份 |
| `1dd3db45` | chore(docs) | — | next-time 五條勾銷 + 2026-09-08 節三條留尾 |
| `030bd815` | test(round-1) | S-01 / F-04·S-02 / S-05·F-01 / F-06 | `_loop` 跨 08:00 立刻再 tick(紅先行)/ 402 當日放棄明講 / INFO 落檔後、compute 無欄位 / Fetch 別名 |
| `0243b33a` | 🔴 fix(round-1) | 同上 + F-03 / F-08 / S-03 | `_due()` 重算 / `_give_up` / `_compute_with_daytrade_rows` 回值 / `_RETRY_UNTIL` / `_prior_text` |
| `436f1ace` | chore(docs) | S-04 / F-05 / OBS | 契約「釘等值」/ opens 遞增 / futures 案註記 |
| `2d4c5ffe` | chore(docs) | F-02 | next-time 記知情不修(併 W3) |

## 2. 紅 → 綠(每張 ticket 都先看到紅)

- T1:13 條 ImportError 紅(函式不存在)→ 44 passed(含 `groupPollInterval` 既有 6 案不改)。
- T2:三支 hook 新案 + 9 條事前標為該變的既有案紅 → 實作第一版只看 14:00 界時 **3 條「slack 窗內」案仍紅**(00:00:10 求值把午夜界推到 14:01,
  正是 pr-151 F-01 那條測試守的洞)→ 改「兩界各算第一個嚴格在後、取最小」→ 68 passed。後端 parity 測試 5 passed。
- T3:10 條紅 → 實作後 3 條 09:01 案仍紅 → 臨時 debug 測試印出時戳 `08:00:00,09:01:00,09:01:10,…` 證明**實作對、測試算術錯**
  (08:00 + 60 分 59 秒 = 09:00:59 不是 08:59:59;08:46 / 08:40 / 14:55 三條算對)→ 改 59 分 → 84 passed。臨時測試已刪。
- T4:ImportError 紅(`data_date_of` 不存在)→ 37 passed。
- T5:4 紅 / 1 綠(「第 3 次成功」在舊三次盒下剛好過)→ 實作後 2 條測試側算錯(放棄行與第 6 次失敗合成同一行 = 6 行 WARNING 不是 7;
  `calls` 記每個 EOD 日的 fetch、成功那趟走 21 天)→ 修斷言 → 37 passed。
- T6:整檔 17 紅(`_DAYTRADE_MIN_ROWS` 不存在)→ 41 passed。

## 3. 完成前 gate(worktree tip `2d4c5ffe`,round-1 收修後全套重跑)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree root,先清 `__pycache__`;跑在 `0243b33a`+docs,後端零再改) | **3548 passed, 3 skipped**(213 s;基準 3531 → +17;round-1 前 3547) | 0 |
| `… -m ruff check copycat tests`(tip) | All checks passed | 0 |
| `… -m pyright`(round-1 收修後;中途抓到 `_counting` 回型 `tuple[object, object]` 一處,已改 `tuple[Fetch, Fetch]`) | 0 errors, 0 warnings, 0 informations | 0 |
| `… -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four …/four_tigers`(tip) | 42/42 PASS | 0 |
| `npx vitest run`(worktree frontend/,tip) | **154 files / 3046 tests passed**(基準 3022 → +24;round-1 前同數,收修只改前端註解) | 0 |
| `npx tsc -b`(frontend/,round-1 後) | PASS | 0 |
| `npx eslint src`(frontend/,round-1 前全 src;round-1 後三個改註解檔單跑) | PASS | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry`(frontend/,tip) | **Scanned 13 files · No issues found**(基準那條 `WatchlistManagerDialog.tsx:42` 不在本批 changed scope) | 0 |

ruff format:`copycat/server/screen_engine.py` 兩個「would reformat」hunk(`_DAILY_MIN_ROWS` raise 的字串拆行、`logger.info` 引數排版)是
merge-base 版本本來就未 format(`git show de192ca3:… > tmp && ruff format --check tmp` 同樣 would reformat),依 backend-conventions 不整檔重排;
`tests/server/test_screen_engine.py` 我新增的 hunk 已 `ruff format` 整檔(該檔在 T4 手修後為 0 hunk,整檔 format 只碰我的段落)。

## 4. 突變體(scratchpad `mutcheck.py`:逐個套用 → 跑對應測試 → 記憶體原文還原(不 `git checkout`)→ 刪該檔 pyc;**10/10 KILLED**)

| 突變體 | 紅的測試 |
|---|---|
| M1 `DAY_ROLLOVER_SLACK_MS` 60_000 → 0 | 三支日 K hook 18 failed |
| M2 拿掉 14:00 界(只看午夜) | 12 failed(三支新案 + 9 條事前標為該變) |
| M3 只看 14:00 界不取 min(pr-151 F-01 那個洞) | 3 failed(三支「slack 窗內」案 —— 實作第一版就是被它們抓到) |
| M4 前端 `DAILY_FINAL_TIME` [14,0] → [14,30] | `test_daily_final_time_parity_with_frontend` |
| M5 `offHoursInterval` 拿掉 1 s 下限 | 1 failed(`barsPollInterval` 量化案) |
| M6 `useBreadthRows` 盤外回 false(修前) | 1 failed(09:01 自醒案) |
| M7 `_DAYTRADE_SHRINK_RATIO` 0.8 → 0(全放行) | `TestDayTradeRelativeGate` 2 failed |
| M8 `_RETRY_UNTIL` 09:00 → 13:30(盒變寬) | `TestRetryWindow` 3 failed |
| M9 `RUN_TIME` 08:00 → 21:00(舊制) | 10 failed(排程判定 + TestTick + TestRetryWindow) |
| M10 當沖名單改抓資料日(舊制) | `test_compute_fetches_eod_from_previous_trading_day_and_daytrade_disposition_on_target` |

兩個迴圈事故(記帳,均無殘留:`git status` 乾淨):(1) 第一輪子行程輸出用 cp950 解碼炸掉 → 加 `encoding="utf-8", errors="replace"` + `PYTHONUTF8=1`;
(2) 第二輪 M10 讓 compute 在**沒裝 fake sleep** 的 TestTick 案失敗 → `_run_attempts` 真的 `asyncio.sleep(600)` → 900 s 超時,且我用 `tail` 吃掉前九隻結果
→ 後端四隻改指向直接呼叫 compute / 裝了 fake sleep 的測試(`-k`),分兩批重跑。教訓:突變體命令要選「失敗路徑不會真睡」的測試。

## 5. two-axis review(`code-review-round-1.json`;fixed point `de192ca3`,兩個 opus sub-agent 並行)

Standards 8 條 + 1 觀察(零硬違規;白名單逐條核過):修 F-01 / F-03 / F-04 / F-05 / F-06 / F-08 / OBS,知情不修 F-02(next-time 併 W3)/ F-07(歷史不重寫)。
Spec 5 條:全修 —— **S-01 MED 真洞**(`_loop` 為昨天補跑拖過 08:00 後睡到明天、今天整天不跑;紅先行 → `_due()` 重算立刻再 tick)、
S-02(= F-04)、S-03 / S-04 doc、S-05 log 移位。Spec 軸另逐條驗過兩界算術 / 三支開點同尺 / `barsPollInterval` 次序 / `active=false` / 快取 v1 作廢 / 閘邊界 / Out of Scope 五項零碰。

## 5b. spec #204 acceptance 逐條對(verification-before-completion)

| ticket / AC | 實作 | 測試 | 證據 |
|---|---|---|---|
| #205 兩支開點函式 + parity 同尺 + 量化 helper + groupPollInterval 改用 | `lib/trading-hours.ts` | `trading-hours.test.ts` 三個新 describe(13 案)+ `useGroupSnapshots.test.tsx` 既有 6 案不改 | §3 vitest;M5 |
| #206 三支 hook 14:01 案 / 9 條事前標為該變 / parity / 突變體 / §4 契約 / bars.py 零 diff | `lib/day-bars-rollover.ts` | 三支 hook 各 +1 案;`test_daily_final_time_parity_with_frontend` | M1–M4;`git diff --stat` 無 bars.py |
| #208 四支 hook 自醒 / `barsPollInterval` 該變 / `active=false` 不變 / `useIndexOverlay` 零行為 | 四支 hook | 四支各 +1–2 案;`barsPollInterval` 四案 | M6;Spec 軸驗 `active=false` |
| #207 目標交易日制 / compute 三 fetcher 日期 / 快取 v2 / 非交易日不跑 / 白名單 / CLI / 文件 | `screening.py` / `screen_engine.py` / `cli.py` | `test_screening` 3 案;`test_screen_engine` compute + cache + `TestTick` 3 案 | M9 / M10;CLI `--date` help 改口(未實跑 CLI:`tests/test_cli.py` 在全量內) |
| #209 重試序列 / 09:00 後放棄 / 重武裝 / 402 / WARNING 零 ERROR | `_run_attempts` / `_next_attempt_at` / `_give_up` | `TestRetryWindow` 5 案 + `TestTick` S-01 案 | M8;**AC 字面「402 走長退避不越界」→ 實作「402 當日放棄」**(round-1 拍板,ticket 留言校正) |
| #210 相對閘 / 無前值 1,000 / 落檔 / 突變體 / log / 既有閘不變 | `_require_daytrade_complete` | `TestDayTradeRelativeGate` 4 案 | M7 |
| #204 US6–US13 盤前篩選 08:00 制 | 同上 | 同上 | 真環境待下一交易日(§6) |
| #204 US14–US17 輪詢自醒 | 同上 | 同上 | 真環境待下一交易日(§6) |
| #204 US20 舊快取自動作廢 / US21 CLI / US23 CONTEXT.md / US24 CLAUDE.md | `_read_cache` 版本守門;CLI;CONTEXT.md 兩詞;CLAUDE.md §0 §1 §4 | `test_cache_v2_records_target_and_data_date_and_old_version_is_void` | commits 508d8d8a / 52318821 |

未做(明列):真環境節(§6)全部待下一交易日 —— 本批改的是「時間到了會不會自己醒」,無法在盤後 / 非該時刻重現;前端 dist 由主樹 `npm run build` 在 merge 後產出。

## 6. 真環境判準(prod 重啟 + `npm run build` 後;寫給下一交易日)

- **日 K 14:01**:交易日 14:0x 常開的期貨 / 加權 / 個股頁 Network 各恰一發 `tf=D`(13:59 / 14:00:30 不打);加權頁「· 最後一根未收盤」14:01 消失;
  期貨 15:0x 錨定翻頁後 CDP / MA 基準 = 今日完整 D bar;00:01 照舊再一發。分頁必須 visible(ops-discipline:hidden 分頁 TQ tick 全停)。
- **盤前篩選 08:00 制**:交易日 08:00:3x log「盤前篩選 <今天>(資料日 <昨天>):硬條件 … → 資格後 …」+「當沖名單 n 列(前值 m)」+
  「盤前篩選群組「盤前篩選」已更新:k 檔」;群組 08:0x 換新。**第一天前值 = None(舊 v1 快取作廢)→ 走絕對下限 1,000**,log 印「當沖名單 n 列(前值 無(用絕對下限))」(pr-211 F-01 校正:`_prior_text(None)` 印的是「無(用絕對下限)」,不是「None」)。
  FinMind 08:00 名單沒出 → 每 10 分鐘一行 WARNING「第 n 次取數失敗…;HH:MM:SS 再試」,09:00 前全敗 → 一行「今日放棄」、零 ERROR。
  **待實錄**:FinMind 當沖名單 08:00 整是否已出(09-08 13:15 實測今天名單已在、成交量全 0)。
- **輪詢頁自醒**:開盤前(08:5x)開著台股綜合 tab 不動,09:01:00 漲跌停列表 Network 自己出現第一發、之後 10 s;
  期貨 tab 08:39 → 08:40 分 K 一發、13:51–14:54 停、14:55 一發;個股頁 / 加權頁分 K 09:01 一發。
- **白名單抽查**:午夜 00:01 三張日 K 各一發照舊;`active=false`(切走 tab)盤中零輪詢照舊;群組檢視 60 s 節奏照舊。

## 7. 部署備註

- 前端 dist 要 `npm run build` 才吃到日 K / 輪詢改動(runtime 契約無變,舊 dist 照舊可用)。
- 換制第一個早上:server 若 08:00 前已在跑 → 08:00:30 起跑今天;08:00 後才啟動 → 啟動即補跑;前一晚 21:00 那次不再發生。
- 舊快取 `data/market/premarket_screen.json`(v1)自動作廢,不必手刪。
