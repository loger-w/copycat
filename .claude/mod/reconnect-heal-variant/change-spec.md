# mod/reconnect-heal-variant — change-spec(A6:#105 重連 × #104 自癒;收工分支 Disconnect 取鎖)

需求原文 = `docs/superpowers/specs/2026-08-25-do-batch-review.md` §3.4(P3:`index_engine._on_reconnect_threadsafe` 走
`_schedule_retry()` 預設 `clear_stale=True, variant=0`,盤後 heal 以 variant N 重試中 → 重連改以 0 號窗重抓,成功即
`stale=False`,`_heal_variant` / `_heal_interval` 不重置,下次最遠等 900 s;畫面 = 徽章健康、加權分時凍結)+ §2.6
Standards 2(P2:`tc4.py` 收工分支 `api.Disconnect()` 未取 `api.lock`;`_dispose` 明訂先 acquire;KeepAlive daemon 呼 `Pong`
取同鎖同 socket)+ §5 A6。`/auto` 鏈式第一批第 4 條。

## §0 現況 vs 目標

| 面 | 現況 | 目標 |
|---|---|---|
| reconnect 重抓的窗 | `_schedule_retry()` → variant 0、`clear_stale=True` | `_schedule_retry(variant=self._heal_variant)`;`clear_stale` **維持 True**(重連 + 重掛成功仍樂觀清 stale:那是 watchdog 的既有語意,與窗口無關) |
| 收工分支 Disconnect(`_ensure_connected` 內 `_stop` 已 set) | 直接 `api.Disconnect()`,未取 `api.lock` | 與 `_dispose` 同一支 helper `_disconnect_locked(api)`:`api.lock.acquire(timeout=lock_timeout)` → Disconnect → release;取不到鎖跳過 + WARNING(洩漏優於 crash,同 `_dispose`) |

`[auto-default: reconnect 沿用當前 variant 而非「不清 stale」 | reason: review 給兩個候選;沿用 variant 直接消掉
「回到已知毒窗」這個根因,不清 stale 只是掩蓋(重連成功後推播是否活著本來就由 watchdog 再判)。「variant 0 在新
session 是否仍毒化」未實證(review 標為假設):若新 session 的 0 號窗其實健康,沿用 N 號窗也拿得到資料
(variant 只是窗字串位移,資料相同)—— 兩種情況都對,不需要拍板]`
`[auto-default: 收工分支取鎖失敗時跳過 Disconnect 而非 raise | reason: 逐字沿用 `_dispose` 的既有判定「api.lock busy,
跳過實體 close(洩漏優於 crash)」]`

## §1 白名單

- `index_engine._on_reconnect_threadsafe` caller:`tc4.py` `_check_stale` 重連後 `on_reconnect` 回呼(source 執行緒),
  由 `start()` 掛上(`self._source.on_reconnect = ...`)。`_schedule_retry` 其他三個 caller(`start` 失敗 / rollover 失敗 /
  分時自癒)**不動**。白名單測試:`tests/server/test_index_engine.py` 全檔(`test_schedule_retry_single_flight`、
  `TestRetrySupersededSideEffects`、自癒 variant 四案、`test_lag_recovery_keeps_variant_and_swap_day_resets_it`)。
- `tc4._ensure_connected` 收工分支:唯一路徑 = `close()` 在 `Connect()` 期間發生。`_dispose` 語意不變(改成共用 helper 是
  🔵)。白名單:`tests/live/test_tc4.py::TestEnsureConnectedShutdownRace`、`TestEnsureConnectedAtomic`、`TestReqProtection`。
- 四個 source 子類都吃 `_ensure_connected`(blast radius 同 #105 §0.1),行為只在收工瞬間多取一次鎖。

## §2 backward compat

零 API / 契約改動。可觀察差異:TC4 重連後 index 的 1K 重抓用當前 variant 窗(新 log `index 重連重掛 + 重抓
(window_variant=N)`;零新鍵且 N > 0 → `index 重連重抓無進展` WARNING + variant+1);收工瞬間在途 Connect 的
Disconnect 最多多等 `lock_timeout`(12 s)—— **與 `close_worst_secs` 的毒鎖路徑互斥**(那條路要 `_api` 非 None;
收工分支 `_api` 恆 None,`close()` 拿到 `_api_lock` 即早退),該分支上界 10 + 12 = 22 s < 34 s,總上界不變;
`close_worst_secs` docstring 第 1 項已回校(round-1 修正首版「同一發、不另加」的錯誤說法)。

## §3 seams

- `IndexEngine._on_reconnect_threadsafe`(loop 內直呼)+ `FakeIndexSource.variant_minutes`:重連那一發的 `window_variants[-1]`。
- `TC4QuoteSource._ensure_connected` + `_SlowQuoteAPI.disconnect_locked`(替身在 Disconnect 當下記 `lock.locked()`)。

## §4 review round 1 逐條處置

### Standards
- **ST1 P2 [hard] 測試手刻輪詢 vs 同檔 `wait_until`** — **接受**:改 `wait_until`。
- **ST2 P3 🔴 內含 helper 抽出(🔵)** — **接受(記錄偏離)**:同 hunk,拆開留壞 commit。
- **ST3 P2 WARNING 字面「dispose」現在收工分支也用** — **接受**:改「TC4 quote Disconnect: api.lock busy …」(無測試引用)。
- **ST4 P2 `close_worst_secs` docstring 第 1 項未回校** — **接受**:補「收工分支持 `_api_lock` 內再等 `api.lock`,22 s,
  與毒鎖路徑互斥,34 s 總上界不變」。
- **ST5 P3 helper docstring 缺鎖序** — **接受**:補「`_api_lock → api.lock` 不得反轉;全檔無反向路徑」。
- 核過無問題(reviewer 列):死鎖掃描無反向路徑;`_schedule_reconnect_retry` 承重(loop 執行緒讀 variant、
  `call_soon_threadsafe` 不吃 kwargs);白名單相符。

### Spec
- **SP1 P2 `clear_stale=True` 分支不判進展 → 新 session N 號窗 stub 仍 `stale=False`、variant 不 bump(只解一半)** —
  **接受(變形)**:只在 **variant > 0 且零新鍵**(= 重連時本就在自癒中)bump `_heal_variant` + WARNING;variant 0 的
  boot / rollover 路徑不動(盤外重抓零新鍵是資料已完整,全面加進展判定會在健康路徑燒階梯)。**stale 維持樂觀清**
  —— 推播死活是 watchdog 職權,盤外 watchdog 不判、stale 留 True 會讓徽章整夜顯示異常;此取捨列「需 user 知情」。
- **SP2 P2 真環境判準無 log** — **接受**:`_schedule_reconnect_retry` 印 `index 重連重掛 + 重抓(window_variant=N)`;
  verification §4 判準改指這一行。
- **SP3 P3 「不 Disconnect 則 process 不退」錯句(本輪 hunk 照抄)** — **接受(本 hunk)+ 申報(其餘)**:收工分支註解改
  「KeepAlive 續跑、TC4 端不 LOGOUT 留到 reap」;`tc4.py` 另兩處(`_ensure_connected` 開頭 docstring、`close()` 註解)與
  `futures_engine.py` 三處是既有字面,併入鏈尾 B 類 docs chore。
- **SP4 P3 change-spec §2「同一發、不另加」事實錯** — **接受**:§2 改寫(互斥、22 < 34);docstring 同 ST4。
- 核過無問題:測試鎖得住(還原 `_schedule_retry()` → 兩條 assert 皆紅);cancel 在飛 heal 的退避不重複也不跳過。
