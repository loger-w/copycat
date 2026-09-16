# verification — fix/capital-reply-reconnect(2026-09-15)

## 1. 自動化 gate(auto-verify;全在 worktree 跑,venv 用主樹絕對路徑)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行 | `PYTHONUTF8=1 …/.venv/Scripts/python -m pytest -q tests/capital/test_reply_reconnect.py`(修前,commit 83c5f827 單獨) | **5 failed**(紅在 `assert [] == ['connect_reply']`) | 1 |
| 反向驗證 | `git revert --no-commit 838a9a19` → 同上 | **4 failed**(R7 案、事件路、探針路、退避)→ `git revert --abort` → reconnect / watch / com 三檔 23 passed | 1 → 0 |
| capital 套件 | `pytest -q tests/capital/` | 445 passed | 0 |
| 全量 pytest | `pytest -q -p no:cacheprovider` | **3431 passed, 3 skipped**(212 s) | 0 |
| ruff | `ruff check copycat tests` | All checks passed | 0 |
| pyright | `pyright`(全量) | 0 errors, 0 warnings | 0 |
| validate | `copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four …/four_tigers` | 42/42 PASS | 0 |
| frontend | 未動 frontend/ → 不跑 | — | — |
| **two-axis round-1 收修後(HEAD 427f21de)** | `pytest -q tests/capital/` / 全量 `pytest -q -p no:cacheprovider` / `ruff check` / `pyright` | **450 passed** / **3436 passed, 3 skipped**(209 s)/ All checks passed / 0 errors | 0 |

既有測試改 assertion 兩條,均事前標為「該變」:`test_reply_watch::test_probe_is_throttled_and_logs_only_on_change`
(docstring 原文「status 燈不動、不重連(語意未實證…)」= 辨識批暫定;CLAUDE 舊條「看過一個交易日 … 再決定接不接
degraded(那是下一批的『修』)」)與 `test_com::test_reply_events_solace_pair_logs_only`(同一句)。

## 2. 白名單逐條核(未改功能)

| 白名單 | 證據 |
|---|---|
| 送單路徑 / OnNewData → `_handle_reply` / 回報鏈三段 / 60 s 輪詢 / 樂觀套用 | diff 未碰(`git diff 4ad1cc22...HEAD -- copycat/capital/client.py` 只在 header / 常數 / 欄位 / `_handle_reply_disconnect` 附近 / `_pump_once` 一行 / `_probe_reply`);`test_fill_latency` 4 案、`test_client` 全綠 |
| 斷線當下不 clear store | `test_client::test_reply_disconnect_degrades_and_keeps_store` 綠(只改註解) |
| `status_view()` 欄形 | 未動;`test_reply_watch` 斷 `reply_connected` 仍 int / None |
| 探針 10 s / log 字面 | `REPLY_PROBE_SECS` 未動;「群益回報線 IsConnectedByID=n(上一值 m)」逐字仍在,`_probe_lines` 前綴收緊後照抓 |
| `_init_com` 啟動序列 | `_handle_reply_connect` 只在 degraded 時動作;`test_client` 啟動序列案(RecordingCom calls 順序)綠 |

## 2.5 two-axis review round-1(`code-review-round-1.json`)

Standards 7(hard 1)/ Spec 4;accept 10、defer 1(S-07 → next-time F-18)。hard = 探針 0 在 degraded 下不排重連
(開機 ConnectByID rc≠0 那條永不重連),與 Spec-S-01 同洞;另收 Spec-S-02 恢復補武裝庫存查詢、S-05 清 last_error、
S-02 只在 degraded 排、S-03 哨兵風格、S-04 退避表兩條測試、S-06 / Spec-S-03 契約措辭。收修 commit 3366a0ae + 427f21de。

## 3. 真實環境(待 prod 重啟 + 一次可控斷線)

修前實錄 = 判準對照(`logs/server-20260914-2359.log`):05:50:57 disconnect 3033 → 05:50:59 探針 0 → 到 08:14:30 零
connection 事件、零 ConnectByID、status 仍 ok。

判準(`grep "回報線\|Solace" logs/server-<日>.log`,一次斷線要看到這四行;第 3 / 4 行順序可互換 —— STA 重入時連線事件可能先於 ConnectByID 回傳,pr-review 253 F-07):
1. `Capital Solace reply disconnect (code=…)` WARNING(或探針先翻 0)
2. `群益回報線斷線(<來源>)→ degraded,5 s 後重連` WARNING(只一行;事件與探針同時到也不重複)
3. `群益回報線重連 ConnectByID 已送出(第 n 次)` INFO(退避 5 / 10 / 20 / 40 / 60 s 內)
4. `Capital Solace reply connection (code=0)` + `群益回報線恢復(<來源>;重連 n 次)→ ok` INFO
   —— 之後 `curl 127.0.0.1:8721/api/capital/status` 的 `status == "ok"`、`reply_connected == 1`;
   `/api/capital/orders` 當日委託列數與斷線前相同(backlog 重播重建,不多不少 = R7 成立)。

執行方式(盤後,user 親做或授權):prod 重啟到本分支 → 手機 / 網卡斷網 60 s(達錢 4 與群益 SKCOM 同一台,斷網
會同時觸發 TC4 自癒,那是既有行為)→ 看 log 四行 → 復網 → 判準 4。**盤中不做**(真錢面板)。

結果:**2026-09-16 05:50 每日自然實驗 PASS**(`logs/server-20260916-0039.log`,跨夜台含 #253 / #254;user 沒做可控斷線,
直接吃天然的那次;09-16 08:11 user 依舊習慣重啟,但重啟前回報線早已自己回來):
- 05:50:53.414 `Solace reply disconnect code=3033` → 同毫秒「斷線(斷線事件 code=3033)→ degraded,5 s 後重連」**只一行**(判準 1 / 2);
  05:50:58.429 又一顆 disconnect code=3002(去重成立,沒第二行)。
- 第 1 次 ConnectByID 05:50:58 出手、**阻塞 11 s** 到 05:51:09.508 才回 rc=1108 `SK_EEROR_TELNET_SERVER_FAIL`;探針 05:51:09.558 才翻 0
  (被同一次阻塞壓後);第 2 次 05:51:09.560(見下方偏差)、第 3 次 05:51:29.597(+20 s)、第 4 次 05:52:09.637(+40 s)全 rc=1108
  —— 網路真的還沒回(同窗 MIS `getaddrinfo failed` 連續 19 次到 05:52:41、Discord DNS 失敗 7 輪、TC4 海外八腿 05:52:26 自癒)。
- 第 5 次 05:53:09.846「ConnectByID 已送出(第 5 次)」+ 05:53:09.897 `Solace reply connection code=0` + 「恢復(連線事件 code=0;
  重連 5 次)→ ok」(判準 3 / 4);探針 05:53:09.897 翻 2(連線中)→ 05:53:19 翻 1,之後到 08:11 收機零再斷。**斷到回 2 m 16 s**,
  由網路決定、退避格 60 s 上限成立。
- 重播:恢復後 0.5 s 內重播 09-15 當日 backlog(6706 / 3532 ×2 / 6715 / 3008 ×2 / 3441 / 3141 共 6 筆成交、含刪單),
  `_mark_balance_dirty` 起的鏈 05:53:16「部位落地 2 列(累計 6 筆成交)」= 恢復後重 seed 那半成立;`store.clear()` 在 ConnectByID 前
  → 沒雙計(fills 只出現一份)。
- traceback 14 則全 `discord.client` DNS 重連(7 輪 × 2),capital 0;斷線期間 `balance collector 忽略放棄輪遲到的終止符(尚欠 0)`
  ×2 = 60 s 定時庫存查詢在斷網下逾時放棄、終止符遲到,既有行為零副作用。F-01 專屬判準(斷線瞬間有鏈在飛)沒撞到 —— 跨夜台 05:50 前
  零成交、零 `部位落地`,以紅先行測試為證。
- 09-16 08:59 `curl /api/capital/status`:`status ok`、`reply_connected 1`(判準「09:00 前」成立;台已是 08:11 那台)。
- 09-16 09:03:33 當日第一筆單(3441)`Capital reply: 委託` → 0.2 s `成交` → 樂觀套用 0.2 ms → 鏈 1378 ms 落地,**即時到**;
  到 11:00 共 8 筆委託(3 刪單)/ 5 筆成交,`/api/capital/orders` 8 列、`/api/capital/fills` 5 列與 log 逐筆對得上(判準「09:00 後
  第一筆單」成立)。10:45:45 `rc=1019` ×3 = 2426 兩筆成交相隔 2 s、第二筆撞上第一筆在飛的鏈,既有語意(CLAUDE §1 chain-stats 尺)。

**偏差(記 next-time,不是紅燈)**:`ReplyLink.begin_attempt(now)` 的下一格從出手**前**的 `now` 起算,而 `ConnectByID` 在斷網下同步阻塞
11 s > 第 1 格 10 s → 回傳時已到期,第 2 次在第 1 次失敗後 **52 ms** 就發(log 印「10 s 後再試」是假陳述)。副作用只有多打一次
ConnectByID;更值得記的是那 11 s 幫浦圈整段阻塞(下單命令排在其後),盤中網路抖才會撞到、且斷網時本來也送不了單。

