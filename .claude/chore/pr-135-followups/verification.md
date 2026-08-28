# chore/pr-135-followups — verification

主 tree 直做;branch 自 master 第 0 筆「chore(skills): backend-conventions 記 ruff format stdin --check 誤判教訓 …」開。
來源 = `/pr-review 135` 三條 Nice(見同目錄 `change-spec.md`);依拍板 (b) commit 以「第 n 筆 + subject」指認。

## 0. 白名單

| # | 項目 | 證據 | 結果 |
|---|---|---|---|
| 1 | `copycat/` 零 diff | `git diff master --stat -- copycat/` → 空 | PASS |
| 2 | 斷言語意不變(除 F-01 新增 deadline assert) | F-02 / F-03 只動 docstring;F-01 diff 的既有 assert 三條全在(`type == "index"` / `seen[-1] == 42_039_920` / `seen and …`),新增一條 `time.monotonic() < deadline` | PASS |

## 1. F-01(第 1 筆 `fix(tests): test_ws_streams_index_payload 加 3 s 牆鐘預算 + 心跳調快 0.2 s …`)

- **紅先行(hang 重現)**:plugin `evidence/dead_quote.py`(`IndexEngine._handle_quote = no-op`,模擬「quote 進來但推播鏈不撥 dirty」的迴歸)
  對修前測試跑 `PYTHONPATH=evidence timeout 25 pytest -q <nodeid> -p dead_quote` → **exit 124、26 s 被 timeout 殺**(= hang,不是紅;報告 F-01 的機制推論實證)。
- **修**:`_WS_QUOTE_DEADLINE_SECS = 3.0` 牆鐘預算,迴圈頂 `assert time.monotonic() < deadline`(訊息印已收 `seen`);
  測試內 `monkeypatch.setattr(ws_mod, "WS_HEARTBEAT_SECS", 0.2)` 讓 ping 每 0.2 s 把阻塞的 `receive_json` 叫醒(relay 在連線建立當下讀模組常數,
  per-test monkeypatch 生效;`test_app.py:170` / `test_signal_routes.py:882` 同手法)。ping 也停 = relay 死,那是 `test_ws_disconnect` 的範圍,註解明寫。
- **修後同 plugin**:**`1 failed` in 4.09 s**,`AssertionError` 於 :110、訊息「3.0 s 內沒等到含 p 的 index payload;已收 […]」。
- 裸跑整檔 **`11 passed`**;test-hygiene-batch 的 `race_index_ws.py` plugin 3/3 `1 passed`;ruff / pyright 0。
- 常態路徑代價:quote 在首則或前兩則就到(毫秒級),3 s 預算只在迴歸時觸發;0.2 s 心跳只影響本測試(monkeypatch per-test)。

## 2. F-02(第 2 筆 `chore(tests): balance_rows docstring …`)

- docstring 末段補「例外(比照 `profit_rows`)」:`test_client` 兩列一次性合成列 —— `3357,T,…,2000,…`(配 `RAW_C_MARGIN` 驗兩種類並存,:1078)
  與 `2330,T,…,500,…`(驗 balance 側丟零股,:1103)—— 各只該處用得到、不收常數;群益改欄形時一起改。純文件。

## 3. F-03(第 3 筆 `chore(tests): TestModuleClock 第二條哨兵 docstring …`)

- 刪「別的測試把 `_now_time` 改回真牆鐘」子句,改寫為「這一條擋 `_DAYTIME` 被凍到窗內(外部洩漏 autouse 每條測試 setup 都會蓋掉,兩條都偵測不到、也不需要)」。純文件;
  `tests/server/test_bars.py` + `tests/capital/test_balance.py` **`98 passed`**。

## 4. 報告落檔(第 4 筆 `chore(docs): /pr-review #135 報告落檔 …`)

- root 的 `pr-135-review.md` / `pr-135-review.audit.md` `mv` 進 `docs/superpowers/specs/`(比照 #131),內容未改;兩檔 `Report generation` 同 hash `b148dcbc…`。

## 5. 自動化 gate

- 第 4 筆後:`pytest -q` **`3140 passed`**(206 s;含 master 上 mod/n075 與本分支)exit 0;`pyright` 0;`ruff check copycat tests` PASS;時段 10:54–10:57。
- 收修第 5 筆後:主 agent 快篩 `tests/server/test_bars.py` **`53 passed`** + ruff;純 docstring 改動。
- `copycat validate` 不需(未動 replay);frontend 未動,vitest 不跑。

## 6. Two-axis review(round 1,fixed point = merge-base 第 0 筆;兩軸 opus)

- **Standards 3 條(全 P3 judgement)**:S-1 `import copycat.server.ws as ws_mod` 與 `test_app.py` 的 `from copycat.server import ws as ws_mod` 兩形並存(倉庫皆有先例,**declined**)/ S-2 F-03「兩條都偵測不到」措辭(**fixed**,第 5 筆)/ S-3 deadline 在 `receive_json` 之前檢查、ping 也停仍會 hang —— 註解已誠實指向 `test_ws_disconnect`(**accepted**)。四個特別核(relay 呼叫當下讀常數 / 3 s vs 0.2 s 千倍邊際 / 註解全 WHY / monkeypatch per-test)全 ✓;鐵則 E「不是 sleep + retry,是 fail-fast 上界」✓。
- **Spec 3 條全 PASS**:F-01 reviewer 自跑迴歸 plugin `1 failed in 3.31s` + 對照組注入 `deadline=1e9` → `timeout 25` 砍(exit 124),證實由 hang 變紅;race plugin ×3 綠;F-02 `grep A123456789 test_client.py` 恰 2 筆與 docstring 逐字相符;F-03 新句無不成立宣稱;報告 hash 相同。零 scope creep(刪「10 s 一發」是 F-01 必要連動)。新 finding P-1 LOW = 與 S-2 同一句的分工歸屬(直擋「凍到窗內」的是第一條 `_DAYTIME >= MIDNIGHT_BUFFER_END`,**fixed** 第 5 筆);P-2 INFO 無需處置。
- 收修 commit:第 5 筆 `chore(tests)`(F-03 docstring 歸屬校正)。JSON:`code-review-round-1.json`。

## 7. 需 user 知情

- 本分支不動生產碼、不需重啟 prod。
