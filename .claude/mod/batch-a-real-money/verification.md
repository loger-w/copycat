# verification — mod/batch-a-real-money(spec #232;tickets #233–#237)

分支 commits(merge-base 285c4b11):360de8cc(#233)→ dc8ea638(#234)→ 2dfd7036(#235)→ 8187d5b0(#236)
→ eb6a0454(#237)→ 085eb880(two-axis round-1 收修)→ 4a17ab89(next-time)。
worktree `.claude/worktrees/mod-batch-a-real-money`;venv 用主樹 `.venv`(pytest 走 pyproject pythonpath,直跑腳本自加 sys.path)。

## 1. 自動化 gate(auto-verify;全在 worktree 跑)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest 全量(收修前) | `.venv\Scripts\python -m pytest -q` | 3384 passed, 3 skipped(既有 skip)in 220.78 s | 0 |
| pytest 全量(收修後) | 同上 | 見 §1.1 | — |
| pytest 觸及檔(收修後) | `pytest -q tests/server/test_signal_policy.py tests/server/test_signal_hub.py tests/capital tests/server/test_clock_monitor.py` | 641 passed | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| validate(golden) | `python -m copycat validate --run-five <主樹 out/five_tigers> --run-four <主樹 out/four_tigers>` | 42/42 PASS | 0 |
| vitest 全量 | `npx vitest run` | 157 files / 3077 passed in 24.5 s | 0 |
| vitest 觸及檔(收修後) | `npx vitest run src/lib/signal-model.test.ts src/lib/query-client.test.tsx` | 57 passed | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found! | 0 |
| build | `npm run build` | ✓ built in 1.32 s | 0 |

### 1.1 收修後全量 pytest

`pytest -q -p no:cacheprovider` → **3385 passed, 3 skipped, 1 warning in 208.44 s**,exit 0(含 085eb880 收修;之後只加
一條測試 75084bd6 `TestAppWiring`,單檔 21 passed、ruff / pyright 0)。3 個 skip 為既有(與 merge-base 同數)。

### 1.2 spec / ticket 驗收逐條(verification-before-completion)

| ticket | 條目 | 實作位置 | 測試 | 證據 |
|---|---|---|---|---|
| #233 | raw 列 `policy_ctx` 十鍵 + `skip` 值域 | `signal_hub._policy_context` / `_policy_ctx_payload` | `TestPolicyCtxOnRawRow` 四案 + error 案 | 641 passed |
| #233 | 政策列 34 鍵 / `_policy_touch` / `notify` 不變 | 未動 | `TestPolicyHits` / `TestDailyCounting` 既有全綠、`_POLICY_KEYS` 未動 | 同上 |
| #233 | WS 與 jsonl 同一份 | `_emit` 同 payload | `test_hit_raw_row_carries_ctx_with_hits` 斷 `rows[0].policy_ctx == ctx` | 同上 |
| #233 | 前端型別 optional 不讀 | `signal-model.ts::policy_ctx?` | tsc / eslint 0 | §1 |
| #233 | 真環境 grep 判準 | — | — | §2.2 重啟後 |
| #234 | 起點只在空時設 / 只涵蓋輪印 INFO / 落地才清 + 「涵蓋 n 筆」 | `client._handle_reply` / `_chain_covers_fill` / `_finalize_positions` | `test_fill_in_flight_keeps_chain_timer_origin` / `test_fill_during_stale_poll_chain_is_measured_by_the_next_chain` | 同上 |
| #234 | 查詢節奏不變 | 未動 | 新案斷「落地前恰一次庫存查詢、fill B 重查在落地後」+ 既有 4 案 | 同上 |
| #234 | CLI `chain-stats` 三種壞樣本 / p50 p90 p99 / 1019 | `capital/chain_stats.py` + `cli.py` | `test_chain_stats.py`(含 log 格式 parity) | 同上 |
| #234 | 基線 | — | — | `evidence/pre-restart-baseline.md` |
| #235 | Solace 兩 sink 只 log、不接 on_disconnect | `com.py::_ReplyEvents` | `test_reply_events_solace_pair_logs_only` | 同上 |
| #235 | `is_reply_connected` 回原始 int;FakeCom 序列 | `com.py` / `fake_com.py` / `_StubCom` | `test_protocol_methods_complete_on_stub_and_real_impl` | 同上 |
| #235 | 10 s 節流 / 值變化才印 / ≠1 WARNING / 不翻 status | `client._probe_reply` | `test_probe_is_throttled_and_logs_only_on_change` / `test_probe_skipped_when_not_logged_in` | 同上 |
| #235 | `status_view.reply_connected`;前端 optional | `client.status_view` / `types.ts` | 同上;tsc | 同上 |
| #236 | 純函式 / 閾值三案 / 三台全失敗 / loop | `server/clock_monitor.py` | `test_clock_monitor.py` 21 案 | 同上 |
| #236 | lifespan task + app.state + prod 接線 | `app.py` lifespan / `__main__` | `TestAppWiring` + `test_main_wiring` prod kwargs | 同上 |
| #236 | 文案 / 閾值不進 config / 不加 API | 常數 | `test_thresholds_documented_in_claude_md` | 同上 |
| #236 | user 校時四行 | — | — | §2.3(user 手動) |
| #237 | 工廠 + main / test-utils 同形 | `lib/query-client.ts` | `query-client.test.tsx` 三案 | 57 passed |
| #237 | queries 層無 networkMode、refetchOnReconnect true | 同上 | 同上 + 真環境 reqid 58–74 | §2.1 |
| #237 | 真環境 Offline → 立即失敗 → 恢復切回零 PUT | — | — | §2.1(a)完成;(c)擇日 |

## 2. 真實環境(prod 8721 仍跑舊版 6cbf7cdd,15:07 起;五件裡四件要重啟後才看得到)

### 2.1 已在本 session 驗到的

- **T2 #237 networkMode(happy + focus 半邊)**:worktree `npm run build` → `vite preview --port 4174`(proxy 到 prod 8721)
  → Chrome DevTools MCP 隔離 context:個股頁看 2330(非自選)→ **Emulate Offline**(`navigator.onLine=false`)→
  「加入自選」→「加入 2330 到 ALL IN」→ 畫面立刻「儲存失敗」;Network 出現
  `PUT /api/stock/watchlist [net::ERR_INTERNET_DISCONNECTED]`(= mutation **沒暫停**,立即送出並失敗)。
  → 解除 Offline → 派 blur / visibilitychange(hidden→visible)/ online / focus 事件 → Network 只有 GET 重抓
  (reqid 58–74:`refetchOnReconnect` / `refetchOnWindowFocus` 照常 = 白名單 queries 層未動)、**零新 PUT**;
  `curl /api/stock/watchlist` 2330 不在自選、總數 80 不變。截圖 `evidence/t2-offline-save-failed.jpeg`。
  盤後 `CAPITAL_ORDER_ENABLED=false` 的送單 (c) 半邊未做(user 拍板 (a) 為主,(c) 雙保險擇日)。
- **T4 #234 chain-stats 基線**:`evidence/pre-restart-baseline.md` —— 全部 log 198 條 / 乾淨 150 / p50 1952 / p90 2993 / p99 6433 ms /
  1019 × 342;與 V2 §2.3 手算(178 條、乾淨 150、盤中 p90 3,027)同量級。
- **T1 #236 SNTP 直跑**:`+2861 ms(time.google.com,RTT 9 ms)` + ERROR 行「本機鐘超前,校時服務可能沒在跑」;17:32 手寫腳本
  三台一致 +2.62 s(spec 正文符號讀反,#232 已留言勘誤)。
- **未改功能抽驗 2 個**:(1) 台股綜合頁加權 / 櫃買分時、漲跌家數、連板表在新 dist 下正常渲染(截圖同上 session);
  (2) 個股頁切 2330 後 `GET /api/stock/state/2330` / `overlay/2330` / `stkfut/contracts/2330` 200,閃電 / 委託 / 部位 tab 照常。
- **手機下單三筆在委託列表**(回報線帳號層級證實;3008 十股是零股,閃電梯排除零股是設計)。

### 2.2 重啟後判準(user 明早 build + 重啟 + 校時四行後,下一交易日盤後核)

| # | 判準 | 指令 |
|---|---|---|
| T1 | 首行 \|offset\| < 250 ms、一天約 144 行、零 ERROR | `grep 時鐘偏差 logs/server-<日>.log` |
| T2 | (c) 半邊:`CAPITAL_ORDER_ENABLED=false` 下 Offline 送單 → 恢復切回 → 審計檔零新列 | `data/audit/capital-<日>.jsonl` |
| T3 | `reply_connected` 有值;首次值一行;Solace 有無命中各記一種結論;`IsConnectedByID 耗時` 零命中;手機小單的 `Capital reply:` 有該序號 | `curl /api/capital/status`;`grep "回報線\|Solace" logs/` |
| T4 | 當日 `non_monotonic` = 0;1019 次數記錄 | `python -m copycat chain-stats --log logs/server-<日>.log` |
| T5 | 每顆掃單簇 raw 列都有 `policy_ctx`;`skip=error` 零筆 | `grep -c '"policy_ctx"' data/signals/<日>.jsonl` = `grep -c '"kind": "sweep_cluster"'` |

### 2.3 user 動作(管理員 PowerShell,盤後)

```powershell
Set-Service W32Time -StartupType Automatic
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpClient" SpecialPollInterval 3600
Start-Service W32Time
w32tm /resync
```
然後 `frontend/` 下 `npm run build`,重啟 server。

## 3. 白名單逐條核(/mod)

| 白名單 | 證據 |
|---|---|
| 時鐘:gate / cooldown / 回填時點不改 | `clock_monitor` 只 log + `app.state.clock_skew`;signal_state / signal_hub 零改動(diff) |
| queries 層零改動、refetchOnReconnect 不變 | `query-client.test.tsx` 斷 `refetchOnReconnect === true`;真環境 reqid 58–74 重抓 |
| OnNewData / 既有 OnDisconnect→degraded / 送單路徑不動、不重連 | `test_com.py` 既有案綠;Solace 兩方法只 logger;`_probe_reply` 不碰 `_status` 也不重連(`test_reply_watch` 以 `RecordingCom` 斷值翻 0 後 status == ok **且** `com.calls` 零新增 —— 09-14 出貨版只斷 status,「不重連」那半零覆蓋,pr-238 review F-02 補) |
| 回報鏈 debounce / 60 s / 1019 退避 / begin_snapshot / 樂觀套用 / _pending_deadline 不動 | `test_fill_latency` 既有 4 案綠 + 新案斷「落地前恰一次庫存查詢、fill B 重查在落地後」 |
| 政策列 34 鍵、_policy_touch、notify、Discord 卡不變;raw 列只加欄 | `TestPolicyHits` / `TestDailyCounting` / `TestPolicyDiscord` 全綠零 assertion 改;`_POLICY_KEYS` 未動 |

## 4. two-axis review

`code-review-round-1.json`:Standards 7 條 / Spec 5 條,全 judgement 零 hard;接受 8(S-01 / S-03 / S-04 / S-05 / S-06 / P-01 / P-03 /
P-04 說明)、反駁 3(S-02 部分→next-time / S-07 / P-02)、知情 1(P-05)。收修 commit 085eb880。

### 2.4 09-15 第一個交易日實錄(§2.2 判準逐條;數字皆為 13:47 當場指令輸出)

環境:當日三段 server —— `1e0720be`(09-14 23:59:44 → 08:14:30)/ `f5ba99ac` = 批 B Tier 0 merge 後(08:14:33 → 12:32:31)/
`e05a964f` = pr-251 收修(12:32:34 →)。三段都含本批五件;log 三檔 `server-20260914-2359.log` / `server-20260915-0814.log` /
`server-20260915-1232.log`,判準跨三檔合併算(chain-stats 多檔語法 = `--log A B C` 一個旗標接多值;**重複 `--log` 只吃最後一個**、
靜默 0 條 —— 併 F-17 的「可多檔」測試一起釘)。

| # | 結果 | 證據 |
|---|---|---|
| T1 時鐘 | **PASS**。忽略 23:59:44 校時前那行(+3163 ms ERROR),之後 83 行全 time.google.com,\|offset\| 13–129 ms、RTT ≤ 19 ms、≥ 250 ms 零筆、零 ERROR / WARNING。每段開機起算,行數 83 ≠ 144 是三次重啟 + 從 23:59 起算的結果,不是漏量 | `grep 時鐘偏差:` 三檔 → awk max/min |
| T2 (c) | 未做(擇日;(a) 半邊 09-14 已 PASS) | — |
| T3 回報線 | **PASS(辨識目標達成,且抓到一次真實斷線)**。首值:23:59:56 `IsConnectedByID=2(上一值 None)` WARNING → 00:00:06 翻 1;08:14 / 12:32 兩次開機首值直接 1。**Solace 那對真的會響**:23:59:53 / 08:14:40 / 12:32:53 三次 `Solace reply connection code=0`;**05:50:57 `Solace reply disconnect code=3033` WARNING,1.4 s 後探針 `IsConnectedByID=0(上一值 1)`** —— 同一分鐘 DNS 失敗(MIS getaddrinfo 11001)、Discord gateway 斷、TC4 海外八腿靜默 123 s、群益 OI 查詢 12007,是一次本機網路中斷;Discord 05:52:58 自動重連、TC4 05:52 自癒重掛,**群益回報線到 08:14 重啟前都沒有再連上(零 connection 事件、探針值停在 0)**。若 user 沒為批 B 重啟,09:00 的成交回報會全數收不到。`IsConnectedByID 耗時` 零命中;Traceback 12 則全是 discord.client 05:51 重連自帶(非本批)。`curl /api/capital/status` 盤中 09:27 / 11:37 皆 `reply_connected: 1`;手機小單 3008 十股 09:22:38 `Capital reply: seq=2313237721744 status=委託` 即時到,09:39 刪單、10:37 重掛、10:40 成交三則回報皆到 | `grep "回報線\|Solace\|耗時"` 三檔;`awk '$2>="05:45"&&$2<="05:56"'` 2359 檔 |
| T4 回報鏈 | **PASS**。三檔合併:回報鏈 6 條、乾淨 5 條(排除 off_session 1 = 23:59 夜間 2305 兩筆)、`non_monotonic` 0、`partial_chain` 0;乾淨子集 **p50 1731 / p90 1889 / p99 1889 ms**;1019 × 3(全在 23:59:58–00:00:00 開機三秒內,盤中零)。五筆盤中落地行:1744 / 1631 / 1889 / 1731 / 1573 ms。母體只有 5 筆(user 當日成交數),p90 / p99 = 同一筆;**寫回 CLAUDE §1 當新基線**,標明 n=5、與舊尺 149 / 198 不相減 | `python -m copycat chain-stats --log logs/server-20260914-2359.log logs/server-20260915-0814.log logs/server-20260915-1232.log` |
| T5 快照 | **PASS**。`"kind": "sweep_cluster"` 55 = `"policy_ctx"` 55;`skip=error` 0;skip 分布 null 46 / no_group 9;政策列 51;13:40:16 「T+1/T+2 回填完成:共回填 105 列(掃 5 個日檔)」 | `grep -c` 三式 + `grep 回填` 1232 檔 |
| 佇列滿 | 0(三檔) | `grep -c 佇列滿` |
| 關機 | 兩次 lifespan 收尾 **0.22 s / 0.20 s**(txo 段 0.21 s 最長;上限 89 s)。run.ps1 Ctrl+C 到 process 退的牆鐘秒數 user 端未記 | `grep 關機收尾` |

**非本批、當日觀察到的環境事件(已告知 user)**:(1) FinMind 帳號 08:14 起被降回 register(API 原文「Your level is register」),
breadth / 盤前篩選 / day_trading 全 400,盤前篩選群組維持前日 29 檔、連板欄 null,user 續 Sponsor 後不需重啟;(2) 08:14 開機十分鐘
TC4 歷史慢,11 檔 1K 回補兩次逾時「當日不再重排」,開盤後全部靠首筆 tick 入列自癒(09:27 每檔 25–28 根);(3) 13:30 index 分時自癒、
13:45 期貨三腿零推播自癒,昨日同時刻同樣式,是收盤節奏噪音不是新症狀。
