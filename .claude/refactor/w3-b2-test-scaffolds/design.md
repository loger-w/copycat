# refactor/w3-b2-test-scaffolds — 設計記錄(handoff W3 SESSION B2 + Q18 `_listen_loop`)

## Why gate

三條全是**純測試**改動,runtime 零觸碰;動機分三段:

1. **前端三支日 K 跨日測試鷹架逐字三份**(next-time 08-31 review S-F5):`useFuturesBars.test.ts` /
   `useMarketBars.test.ts` / `useStockBars.test.tsx` 各自持有 `D1_ISO` / `D_SNAPSHOT` / `D1_SNAPSHOT` /
   `D_FINAL`(inline)/ `rerenderBurst` / 「D+1 起先失敗 n 發」計數器 / 「14:00 定稿界三段牆鐘」判定。
   08-31 後又長一對「午夜 200+空 bars」(market / futures)。W2(#206)加 14:00 界時三檔同時改了
   「途經 14:01 多一發」的計數,**三處各改一次**就是這條的成本;下一次日 K 政策再動(A-1 期貨 15:00 錨定翻頁
   若做)又是三處。
2. **`TestWsBroadcasterBackpressure` 八份 `WsBroadcaster(...) + stream() + try/finally aclose()` 骨架**
   (next-time 09-04 pr-188 收修 review F-06;實際位置 `tests/server/test_capital_api.py:1055`,handoff 寫的
   `test_ws_disconnect.py` 是筆誤):每條 8 行骨架包 3–6 行斷言,`caplog.records` 過濾「佇列滿」也五份逐字。
3. **TC4 `_listen_loop` 執行緒活過測試**(next-time 08-31 pr-160 review 實證;09-08 盤點 Q18 併本批):
   `tests/live/test_stock_source.py::test_subscribe_starts_listener_when_sub_port_known` 把 `_sub_port` 設成
   `"59999"` 後 `subscribe_symbol` 真起 listener 執行緒(連 127.0.0.1:59999 無人聽),測試結束**沒 stop 沒 join**
   → daemon 執行緒活到 process 結束,每秒 recv 逾時、30 s 後 `_check_stale` 開始 WARNING「TC4 stale」+
   重連 traceback,落進其他測試的 caplog 負向斷言與執行緒計數斷言(`test_ws_disconnect.py:1058`
   已為此把斷言收窄到單一 logger)。候選修法 = root conftest autouse fixture 測後斷言無殘留。

**為什麼是現在**:W2(PR #211)後三支日 K hook 的政策穩定;B1 剛出貨、W3 序列輪到 B2;
`_listen_loop` 洩漏是 caplog flake 的已知源,越早守門越少「偶紅歸 flake」的誤判。

## 設計(codebase-design 詞彙)

### Seam 1 — `frontend/src/hooks/__fixtures__/day-rollover.ts`(新 module)

- **Interface**(小):常數 `D1_ISO` / `D_SNAPSHOT` / `D1_SNAPSHOT` / `D_FINAL_SNAPSHOT`;判定
  `pastMidnight(now)` / `pastDailyFinal(now)`;選料 `snapshotAt(now)`(二段:D / D+1)與
  `snapshotAtWithDailyFinal(now)`(三段:D / D 14:00 定稿 / D+1)+ `partialLastAt(now)`(三段下
  `meta.partial_last` 的值,review S-03 收:那是政策不是信封);計數器 `firstCallsAfterMidnight(n)`
  (回 `() => boolean`,午夜後前 n 次呼叫為 true —— 「先失敗 n 發」與「空 bars 一發」同一顆);
  `rerenderBurst(rerender, forMs, everyMs)`。(命名依 review F-05 自 `snapshotAtThreeWay` /
  `afterMidnightBudget` 改口。)
- **Implementation 藏什麼**:D = 2026-08-05(週三)這組日期、部分 bar / 完成 bar / 定稿 bar 的數值、
  「D 14:00 起算定稿」與 `DAILY_FINAL_TIME` 鏡像的關係、`isoLocalDate` 比對方向。
- **不進 fixture**:各 hook 的 `Response` 信封(`{key, tf, bars, meta}` vs `{bars, status}`)、`urls` /
  `fetchMock` 記錄機制、`META`。三檔的 stub 各自留 5 行信封函式,只呼叫 fixture 選料 —— 信封是各 hook
  的 interface 事實,不是跨日政策的一部分。`wrapper` / `newClient` 在 19 個測試檔重複,**不在本批**
  (handoff 未列;另記 next-time)。
- **Deletion test**:刪掉 fixture,三檔各自長回 40 行常數 + 判定 → 是 pass-through 的反面,earning its keep。
- **行為不變的證據**:三檔測試名與斷言零改動、計數逐字不動;只換「料從哪來」。

### Seam 2 — `tests/server/test_capital_api.py` 模組內 async fixture `ws_stream`

- **Interface**:fixture 回 `open(maxsize=CLIENT_QUEUE_MAX, *, on=None) -> (WsBroadcaster, AsyncGenerator)`
  (`on=b` = 同一顆 broadcaster 再開一條 stream,唯一使用者 `test_slow_client_does_not_affect_fast_client`;
  review F-02 查證非 speculative generality);teardown 對每條開過的 stream `aclose()`(原 `finally` 語意)。
  另一支純函式 `_queue_full_warnings(caplog) -> list[str]` 收「佇列滿」過濾。
- **不進 conftest**:唯一使用者是這個 class(`WsBroadcaster` 其他測試在 `test_ws_disconnect.py` 走 relay
  路徑,骨架不同)。
- **pytest-asyncio 1.4 / `asyncio_mode=auto`**:async fixture 與 test 同 function loop scope。
  `stream()` **呼叫當下**就同步建 queue 並入 `_clients`(`ws.py`;review S-01 回校 —— 原寫「首次
  `__anext__` 才建」是錯的),所以 `open_stream` 由測試本體呼叫、不在 fixture 內預開;teardown 的
  `aclose()` 走同一個 loop。
- **行為不變**:八條測試的斷言、`caplog.at_level` 範圍、`monkeypatch` 時點全不動。

### Seam 3 — `tests/conftest.py` autouse `_no_leaked_tc4_threads`

- **Interface**:每條測試前後快照 `threading.enumerate()`,測後新出現且名字含 `(_listen_loop)` /
  `(_heal_loop)`(CPython 3.10+ 預設 `Thread-N (<target.__name__>)`)的執行緒先 `join(timeout=3 s)`
  (容許「`close()` 已 set `_stop` 但沒 join」的 ≤ 1 s RCVTIMEO 尾巴),仍活著 → 該測試 fail 並點名。
- **住 root conftest**:同 `_isolate_watchlist_default_path` docstring 的理由(子目錄 autouse 在交錯
  命令列參數下會靜默丟失)。
- **不做**:替漏 close 的測試代為 stop(fixture 拿不到 source 實例;代收會讓洩漏隱形)。揪出的測試各自
  補 stop + join(🔵 純測試)。
- **生效自檢**(review F-01 收):偵測邏輯抽成 `leaked_tc4_threads(before, *, join_secs)`,
  `tests/test_conftest_guards.py` 三條 —— 正向案(名字帶標記、卡在 Event 的執行緒必被點名;放行後清空)/
  負向案(測前已在的與無標記的不點名)/ 字面 parity(`tc4.py` 起兩條執行緒不帶 `name=`、target 是裸 bound
  method)。守門靠名字比對,這三條讓「名字前提」壞掉時有紅燈而不是靜默 vacuous。
  快照時點與 autouse 定義順序的前提寫進 fixture docstring(review S-05)。
- **預期一發紅**:`test_stock_source::test_subscribe_starts_listener_when_sub_port_known`;其餘由全量
  跑一次揭露。

## 步驟(每步單獨綠)

1. 🔵 前端 fixture + 三檔改吃 fixture(vitest 三檔 + 全量)。
2. 🔵 `TestWsBroadcasterBackpressure` 改吃 `ws_stream` fixture(該檔 pytest)。
3. 🔵 conftest 守門 fixture(先跑 `tests/live` 看誰紅)→ 補 stop + join 到漏的測試(全量 pytest)。
4. 收尾:two-axis review(Standards 主、Spec 對照「行為不變」)→ gate → PR;next-time 三條勾銷。
