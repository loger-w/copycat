# 訊號影子政策層(`mod/signal-shadow-policies`,spec #192)— verification

分支 `mod/signal-shadow-policies`(worktree,自 master `53d8f15c` 切出)。spec #192;tickets #193–#198。
無人值守實作(2026-09-07 深夜,handoff `copycat-handoff-2026-09-07-signal-shadow-policies.md`)。

## 1. commits(每票 test 紅先行 → feat / fix 實作;🔴 / 🟢 / 🔵 三類分開)

| sha | 票 | 類 | 內容 |
|---|---|---|---|
| `c331b33d` | T1 #193 | test | 規則模型 / 遷移 v4 / 種子通知關 / 開關六鍵 / parity fixture / 「通知」文案的既有斷言改紅(hub 測試 `loud_seeds`) |
| `095b8b65` | T1 | 🟢 feat | `sweep_cluster` 第六 kind:PARAM_SPECS / INT_PARAM_KEYS / rule_config / 十二個設定鍵 / 種子卡 / 遷移 v4 append / SWITCH_KEYS 六鍵 / 規則視窗欄位表 |
| `bb51d4dd` | T1 | 🔴 fix | 種子與 v3→v4 把 cdp_cross / vol_burst 通知翻 false(逐條 log);「Discord」→「通知」 |
| `31908d26` | T2 #194 | test | 掃單簇主 seam + 研究 golden fixture(`record_sweep_cluster_golden.py` 參考碼)+ 全列 notify + 換日 / 移出自選 |
| `bb4dfd60` | T2 | 🟢 feat | `SignalDetector._eval_sweep`(同毫秒群 / 簇窗 / 回看窗 / 冷卻 / 即時判)、`SignalEvent.detail`、hub 每列 `notify`、文案「掃單簇 +x.xx%」 |
| `9e24d8d4` | T3 #195 | test | 政策層主 seam(`test_signal_policy.py`)+ engine `policy_quotes` + app 接線 |
| `6e1619be` | T3 | 🟢 feat | `signal_policy.py` 純函式、hub `_emit_policies`、Discord 四行卡、`engine.policy_quotes`、`peers_fn` 注入 |
| `7c22f7cb` | T4 #196 | test | 回填檔案 seam(`test_signal_outcome.py`) |
| `e0c3c233` | T4 | 🟢 feat | `backfill_policy_outcomes` + `_policy_outcome_worker`(`outcome_bars` = `bars_range(tf=D)`)、`fileio.atomic_write_bytes` |
| `d79e5d79` | T5 #197 | test | 前端文案 / shouldNotify / 政策組 / 提示 hook / rail 三行 |
| `00272432` | T5 | 🟢 feat | `SignalMsg` 新 kind 與欄位、toast 【標記】前綴、雙嗶、rail 政策列三行 + chip |
| `c7445b66` | T5 | 🔴 fix | 提示 hook 改讀 `notify` 欄(false 不 toast / 嗶 / 桌面通知);rail quiet 淡色 |
| `aa1818d9` | T6 #198 | docs | CLAUDE.md §4 五條契約 + §1 判準列;CONTEXT.md 十術語;tc4-market-facts 一條 |
| `8c9802b5` | review r1 | 🔵 | PeerQuote TypedDict / 旗標 helper 共用 / arrivalOrder / 折行 |
| `525c6b6a` | review r1 | 🔴 fix | chg round 2 / 壞 HH:MM:SS 建構即 raise / peers_fn 例外每日一次 / 政策卡截斷 / 翻旗集合縮回 / 回填 open ≤ 0 不位移 / 計數在 publish 後 / 起動 INFO |

**明文偏離(handoff 要求 call `implement` skill)**:該 skill `disable-model-invocation`,無法由 agent 呼叫;實作沿 `tdd`(紅先行、垂直切片、只在 spec 四條 seams 寫測試)直做,順序 T1 → T2 → T3 → T4 → T5 → T6 與 handoff 相同。

## 2. 紅 → 綠(紅態證據)

- T1:`test_signal_rules / test_signals_config / test_signal_state / test_signal_hub` 先紅(hub 全批 v4 載入失敗 + 種子旗標 + 鍵集);實作後四檔綠,再補 `test_signal_routes._SEEDED_KINDS`(全量抓到)。前端 parity + Dialog 5 條紅 → 綠。
- T2:`TestSweepCluster` 8 案 + `TestSweepClusterGolden` 3 案 + `TestSweepClusterState` 2 案先紅 → 實作後 **golden 三個股票日事件集合 == 研究 prefix 參考**(6715 08-17 4 則 / 1727 08-05 5 則 / 8103 08-19 2 則;研究定義事件時刻 ⊆ 線上)。兩條 hub 案例的情境寫錯(第三簇落在簇窗外)由紅態抓到、改測試情境不改實作。
- T3:`test_signal_policy.py` 35 案先紅(`_state(ref=)` / `peers_calls` 不存在)→ 實作後 32 綠 + 3 條測試期望修正(harness 不經 ingest 需手動 `high_milli`;rollover 日別不換;爆拉 +0.60% 在第二筆就達標)。
- T4:`test_signal_outcome.py` 15 案先紅 → 實作後 byte 比對抓到 `atomic_write_text` 換行翻譯(Windows CRLF → CRCRLF)→ 改 `splitlines(keepends)` + `atomic_write_bytes` 綠。
- T5:15 條前端紅(3 檔)→ 實作後 127 passed。
- review r1:`test_bad_hhmmss_config_raises_at_construction` 先紅(`time.fromisoformat("13:40")` 合法)→ 改 `strptime("%H:%M:%S")` 綠;`test_zero_open_bar_not_used_and_not_shifted` 加 T+2 不位移斷言。

## 3. 完成前 gate(全綠;工作樹 = `525c6b6a`,gate 跑在 review 收修套用後、artifact commit 前)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree root) | **3480 passed, 3 skipped**(206.20 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four …/four_tigers`(worktree code,主 tree replay 產物) | **42/42 PASS** | 0 |
| `npx vitest run`(frontend/) | **154 files / 3002 tests passed** | 0 |
| `npx tsc -b`(frontend/) | PASS | 0 |
| `npx eslint src`(frontend/) | PASS | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | 1 條 `no-high-complexity-react-function` `SignalRulesDialog.tsx:160` —— **master 基準已有**(主 tree `--scope all` 掃描同函式 `:156`,本輪只動 JSX 文字與元件外的 `ruleSummary`),零新增 | 0 |
| `npm run build`(frontend/) | ✓ built in 1.17s | 0 |

ruff format:新檔(`signal_policy.py` / `record_sweep_cluster_golden.py` / `test_signal_policy.py` / `test_signal_outcome.py`)已 format;
`signal_hub.py` 有一段 master 本來就未 format 的 hunk(`_enqueue` 的 warning 折行)、`test_signal_rules.py` / `test_signal_hub.py` master 版本
本來就未 format,依 backend-conventions 不整檔重排(新增段落乾淨)。

## 4. 真實環境(盤後可驗;spec「真環境驗收」第一段)— 全部 PASS

| 項目 | 證據 | 結果 |
|---|---|---|
| 規則清單含「掃單簇」且 CDP 穿越 / 爆量通知關(遷移 log 逐條) | `evidence/migration-dry-run.txt`(對 prod `data/signal_rules.json` v1 唯讀 dry-run:七條、`CDP 穿越 notify=False`、`爆量 notify=False`、`掃單簇 enabled=True notify=False cooldown=60`,**檔案未回寫 True**)+ `evidence/sidecar-rules-curl.txt`(側車 `GET /api/stock/signals/rules` 同七條)+ `evidence/sidecar-startup-log.txt`(v1→v2 / v2→v3 ×2 / v3→v4 翻旗 ×2 / v3→v4 append 種子卡,逐條) | PASS |
| server 啟動 log 有回填 task 起動一行 | `evidence/sidecar-startup-log.txt`:`T+1/T+2 回填 worker 起動:start 後跑一次,之後每日 13:40:00(最近 5 個日檔)` | PASS |
| 前端規則視窗顯示新 kind 與「通知」文案 | `evidence/rules-dialog-list.png`(七條;通知開的印「通知」徽章、CDP 穿越 / 爆量 / 掃單簇無徽章;掃單簇摘要「30 秒內 2 掃 · 2 層 · 60 秒漲 0.3% · 冷卻 60 秒」)+ `evidence/rules-dialog-sweep-edit.png`(種類 select 六類、五欄預設 30 / 2 / 2 / 0.3 / 60 且 min/max 帶值域、「通知」checkbox 未勾) | PASS |
| 前端 build 成功 | `npm run build` ✓(上表) | PASS |

側車:`evidence/fake_server.py`(neutralize + FakeStockSource + prod 規則檔副本落 tmp,port 8899,零 TC4 / ZMQ)+ `evidence/vite.sidecar.config.ts`
(preview proxy → 8899)。取證當時是把設定檔複製到 `frontend/`、順手把 import 改成 `./vite.config` + `root: __dirname` 跑的
(與檔頭寫的 `--config ../.claude/...` 跑法互斥,review F-06);兩檔已改為自我定位(review F-05),下次直接在
`frontend/` 以 `--config` 指定、不複製。截圖以 chrome-devtools MCP 拍,拍完關 tab、殺 8899 / 4174 兩個 process。

**盤中判準(影子期第一個交易日起,留給 user;CLAUDE.md §1 已列)**:
- [ ] `grep '"kind": "policy"' data/signals/<YYYYMMDD>.jsonl` 有列,且 `first_of_day` / `late` / `notify` 對得上時刻(12:30 後只記)
- [ ] Discord 收到四行卡且同 tick 合併(【P・B-a】並列)
- [ ] rail 政策列三行(chip + 掃單簇文案 + 「同伴≥3% n・鎖過 有/無・+x.x%/停 y.y%」)、toast 帶【標記】、雙嗶
- [ ] CDP 穿越 / 爆量 jsonl 有列但無 Discord / 無 toast(rail 淡色)
- [ ] `grep 佇列滿 logs/server-*.log` 為 0
- [ ] 13:40 log「T+1/T+2 回填 <日>:回填 n 列」;次日 `t1_open` 已補、再次日 `t2_open` 已補

## 5. Review(two-axis,fixed point `53d8f15c`,reviewed head `aa1818d9`;兩 sub-agent 皆 opus)

- 標準軸 14 條(HIGH 1 / MED 5 / LOW 8;**W1–W12 未破**):修 11、否決 2(F-02 rail 3% 字面 = spec 字面且影子期參數凍結;F-11 三種百分比格式各屬版面)、記錄 1(F-12 既有 Shotgun 形狀)。
- spec 軸 5 條(全 LOW;32 user stories / 六票 AC / W1–W12 逐條對過):全修(政策卡截斷 / 翻旗集合縮回 / 回填不位移 / 計數在 publish 後 / docstring)。
- 處置全文 `code-review-round-1.json`;收修 commit `8c9802b5`(🔵)+ `525c6b6a`(🔴)。收修後重跑全部 gate(§3 數字即收修後)。

## 6. 逐條核 spec acceptance(verification-before-completion;每條:實作 / 測試 / 證據)

### #193 T1(7 條)
1. 既有斷言先紅 → `c331b33d`(test_signal_rules / test_signals_config / test_signal_state / test_signal_hub / parity / Dialog)。
2. v1 / v2 / v3 載入含掃單簇種子、cdp / vol 通知 false、逐條 log、撞名 / 滿 30 跳過、不回寫 → `TestMigrationV3ToV4` 8 案 + `TestMigrationFromV1` / `V2ToV3` 改寫;prod 檔 dry-run `evidence/migration-dry-run.txt`。
3. 全新安裝預設通知口徑 → `test_seed_notify_flags_quiet_for_negative_kinds` + hub `test_migration_defaults`。
4. 新 kind params 精確鍵集 / 值域 / 整數鍵 INVALID_RULE、cdp_levels 必空 → `TestNormalizeParams`(parametrize 自動涵蓋六 kind)+ `test_integer_keys_reject_fractional` 加兩鍵 + `test_non_cdp_kind_must_have_empty_levels`。
5. `configs/signals.json` 十二鍵覆寫、tuple、未知鍵 raise → `test_load_policy_keys_and_exclude_groups_as_tuple` + 既有 `test_unknown_key_raises`。
6. 規則視窗六類、五欄預設落值域、「通知」文案、parity 兩邊綠 → `SignalRulesDialog.test.tsx` 三案 + `signal-param-parity.test.ts` + `test_param_specs_parity_with_frontend`;截圖 §4。
7. 回退手順進 docstring → `signal_rules.load_rules` docstring(退 v3 / v2 / v1 三段)。

### #194 T2(5 條)
1. 主 seam(合成 tick → raw 列 / detail / notify=false / 不進 Discord;單掃 / 漲幅不足 / 非外盤 / 賣一 0 不發;冷卻)→ `TestSweepCluster` 8 案。
2. 首筆達標即發、同群不重計 → `test_first_qualifying_tick_fires_and_group_counts_once`。
3. 對照 seam golden fixture(三個股票日、參考碼、已知差異列表)→ `tests/fixtures/sweep_cluster_golden.json` + `record_sweep_cluster_golden.py` + `TestSweepClusterGolden`(含 `test_fixture_self_check` 斷言每案至少一則「發訊早於群末」)。
4. 換日 / 移出自選清空 → `TestSweepClusterState` 2 案。
5. 既有五 kind 列多 `notify` 其餘逐字不變 → `_SIGNAL_KEYS` 加 notify、`test_ws_and_jsonl_key_contract` 斷言 `notify is True` 且無 `detail`;`test_quiet_and_loud_rules_stamp_notify_per_rule`。

### #195 T3(7 條)
1. P / B-a / B-b / S 命中與不命中逐條 → `TestPolicyHits` 10 案(同伴已動 / 有人鎖過 / ≥6% / 非最強 / 零組 / 無同伴報價 / 無參考價 / 盤前篩選 + 族群 → S 與 P 各自)。
2. 多組聯集 + 一則 WARNING、排除組名走設定、盤前篩選恆不算族群 → `TestGroupResolution` 3 案。
3. 第二次命中 first_of_day=false / notify=false 仍寫 jsonl;12:30 後 late;換日;移出自選 → `TestDailyCounting` 5 案(含 tod 五桶 + 12:30 邊界 10 組參數)。
4. 政策列全欄位齊、id 決定性且與 raw 不同 → `test_p_hit_full_row_schema`(`_POLICY_KEYS` 精確集合)。
5. Discord 單政策四行逐字 / 兩政策並列 / 爆拉接首行尾 / 不掛同群摘要 / 非政策批次既有測試不動 → `TestPolicyDiscord` 6 案 + 既有 `TestGroupSuffix` / `TestDiscordMerge` 零改動綠。
6. 熱路徑零 IO(peers_fn 只在掃單簇事件被叫)→ `test_peers_fn_not_called_for_other_kinds` + `test_missing_ref_evaluates_nothing…`(`peers_calls == 0`)。
7. engine 快照 no_data / 缺 meta / 未成交回 None 鍵仍在 → `TestPolicyQuotes` 4 案;接線 `TestSignalHubGroupWiring` 斷言 `hub._peers_fn`。

### #196 T4(6 條)
1. 檔案 seam byte 比對 → `test_fills_t1_t2_and_leaves_other_lines_byte_identical`(含空行 / 壞行 / 檔尾換行 / 鍵序)。
2. 只補 null / 兩者皆有不取日 K / 同檔一次 → `test_only_null_fields_filled…` + `bars.calls` 斷言。
3. 只碰過去日 / days 窗 → `test_only_past_files_within_days_window` + `test_hub_date_ahead_of_wall_clock…`。
4. 只有 T+1 → 下輪補 T+2;逾時 / 空 / 例外續行 + log → `test_only_t1_available_then_t2_next_round` + `test_failure_leaves_null_and_continues_other_codes`(三種例外)+ `test_empty_bars…` + `test_log_reports_filled_rows`。
5. 排程:start 立即一次、13:40 一次、同日不重跑、隔日再跑、close 不吊死 → `TestSchedule` 3 案(輪詢常數 monkeypatch 0.01 s、注入時鐘)。
6. 無日 K 來源不啟動 + INFO → `test_no_source_not_started_with_info`;側車 log 有起動行(§4)。

### #197 T5(6 條)
1. 提示 hook:notify=false 不 toast / 嗶 / 通知;缺欄照舊;政策雙嗶;既有案不動 → `useSignalAlerts.test.tsx`「notify 閘與政策列」5 案 + 既有 40 案零改動。
2. rail:三行 / chip 文字與色 class / hover 全文 / 政策 + 掃單簇合一列 / quiet 淡色 / 既有列不變 → `SignalRail.test.tsx`「政策列」5 案。
3. 文案純函式:兩新 kind label;未知 kind 原字串 → `signal-model.test.ts`「kindLabel — spec #192」3 案(tone 由 rail 案的 `text-bull` class 斷言)。
4. toast 文案政策組帶標記、價取組錨 → `signal-model.test.ts`「政策組」toast 案(字面量)。
5. 舊後端訊息照舊、不 NaN → `舊後端訊息…` 案 + `舊後端 / 缺欄的政策列不印 NaN` 案。
6. tsc / eslint / react-doctor 只算新增 → §3。

### #198 T6(6 條)
1. CLAUDE.md §4 五條 + §1 判準列;CONTEXT.md 十術語 → `aa1818d9`。
2. 專案 skill 沉澱 → tc4-market-facts「同毫秒群 = 掃單」一條(含 PreciseTime 同源、`ask > 0` 判準、即時判 0.7% 量測)。
3. two-axis findings 逐條處置落 json;auto-verify gate + exit code 落本檔 → `code-review-round-1.json` + §3。
4. 盤後可驗證據(curl / 遷移 log / 截圖 / 起動 log / build)→ §4。
5. 收尾回報列早上要做的事與盤中判準 → 收尾訊息。
6. merge 後自動 pr-review、報告產出即停等 → 收尾鏈執行。

## 7. 已知 / 刻意
- 即時判 vs 研究群結束判:多發 0.7%、零漏發(user 拍板);fixture 三案皆含「發訊早於群末」差異案例。
- 回填日 K 走 `engine.bars_range(tf="D")`(`daily_bars` 的 `DailyBar` 沒有 open)。
- rail 第三行「同伴≥3%」是 spec 字面(門檻不進列;影子期參數凍結);Discord 第三行走 cfg。
- 多組聯集 WARNING 一檔一天一次;peers_fn 例外 traceback 一天一次。
- `implement` skill 不可由 agent 呼叫(§1 明文偏離)。
