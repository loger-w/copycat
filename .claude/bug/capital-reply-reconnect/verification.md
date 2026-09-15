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

結果:待補。
