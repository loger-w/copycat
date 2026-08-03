# 後端去重盤點(Explore agent,2026-08-03)

## P1 — 明顯值得做

### B-D1 | P1 | stock_source.py 同檔兩份 `_taipei_minute_key`
`_taipei_minute_key`(:161-182)與 `fetch_day_minutes` 內嵌版(:407-420)逐字同義
(docstring :169 自稱「同一把尺」)。修法:迴圈內改呼叫 `_taipei_minute_key(str(r["Time"]))`,
None → continue;dict last-write-wins 收斂政策保留。
Blast radius:`_taipei_minute_key` caller = parse_1k_bars(:250);fetch_day_minutes caller =
index_engine.py:216/:381(IX0001,與個股同域 — 必須維持 0901-1330 不可套 FUTURES 域)。
測試 test_stock_source.py:296/314/326、test_index_engine.py:31、test_index_routes.py:46、
test_market_routes.py:74。

### B-D2 | P1 | `_listen_loop` 三份逐字複製(stock_source:504-529 / futures_source:151-176 / corr_source:103-128;基底 tc4.py:453-491)
generation-following ZMQ SUB 迴圈,2026-07-20 實證修正現要四處同步改。
修法:tc4.py 基底 `_listen_loop` 把 :477-488 訊息處理段拆成 `handle_raw(self, raw)`
(內容 = 現有 TXO tick 解析),三子類刪整個 `_listen_loop` 只留 handle_raw 覆寫。
風險:基底改動碰 TXO 實盤路徑,逐字搬移。
測試直呼 handle_raw:test_stock_source.py:341/348/378、test_futures_source.py:145/152/153、
test_corr_source.py:129/138/147/148。

### B-D3 | P1 | `handle_raw` futures/corr 兩檔逐字相同(futures_source:137-149 / corr_source:90-101)
個股版(stock_source:485-502)多 `_seen` bookkeeping,覆寫時必須維持
「`_seen.add` 早於 `_on_message`」順序。接 B-D2 一起做:基底放四步版,兩檔刪除。

### B-D4 | P1 | UNSUB→SUB 冪等訂閱核心四份(stock_source:331-349 / futures_source:54-64、:72-85 / corr_source:60-69)
連註解都抄三遍。修法:tc4.py 基底 `_resub(sym)` / `_unsub(sym)`;
外圍(stock 的 _seen.discard、F: 跳過健檢、Timer;futures leaf symbol 組字)留原地。
**失敗語意是契約**:stock_engine._acquire(:118-122)靠 ConnectionError 回滾 refcount,
不可改回傳 bool。unsubscribe 三份同理。
caller:stock_engine:117/:247、futures_engine:131/:239(to_thread)、index_engine:215/:374、
corr_engine:128。測試 test_stock_source.py:63、test_futures_source.py:44、test_corr_source.py:60。

### B-D5 | P1 | per-client 有界 queue fanout 三份;共用類 `WsBroadcaster` 已存在(capital_api.py:48-80 / stock_engine.py:478-514 / index_engine.py:488-513)
修法:WsBroadcaster 搬 `server/ws.py`(住 capital_api 會逆向依賴),
`__init__(maxsize=...)` 參數化(500/32/1000);stock/index engine 各持實例。
⚠ stock stream() 種子必須 per-client(:485-486 明寫不可借 _publish)→
stream() 要能吃 seed 或回 queue 讓 caller 塞。
Blast radius:stock_engine._publish 內部 10 個 call site;app.py:200-203 建四個既有實例;
/ws/stock=app.py:724、/ws/index=:711。測試 test_stock_engine.py:211、test_index_engine、
test_capital_api。

## P2 — 可做

### B-D6 | P2 | `_on_*_threadsafe` 守衛 8 份 × 4 行(loop=None close 閘)
四引擎各私有。抽 LoopBridge mixin 或 `_to_loop(fn,*args)`。
注意 on_reconnect 是 hasattr + 動態賦值(# type: ignore[attr-defined] 三處),grep 要含
`hasattr(self._source, "on_reconnect")`。

### B-D7 | P2 | app.py lifespan 引擎起停樣板五份(:228-255/:257-284/:287-307/:311-331/:335-372;收尾 :378-403)
檔內 `_boot(name, build)` + `_shutdown(name, closer)`。
⚠ 建構順序是語意(corr 在 futures 後);關機反序;capital close 是 to_thread → closer 吃 callable。
create_app caller:__main__ + 測試 8 檔;降級路徑(None→503)有測試。

### B-D8 | P2 | `"50774"` 硬編 9 處;`os.environ.get("TC4_PORT","50774")` app.py 重複 5 次
抽 tc4common `TC4_DEFAULT_PORT` + app.py `_tc4_port()`。
🚨 `_default_stock_source`(:157-160)與 `_default_index_source`(:163-166)函式體逐字相同
但**不可合併呼叫**(獨立 session 註解載重:同 symbol 跨 session 只推一邊)→ 只抽 port,不併函式。

### B-D9 | P2 | Decimal `to_milli` ≡ `to_millipts`(stock_models:25-32 / models:30-37)
只合併 Decimal 對到 tc4common,兩邊留薄別名。
🚨 不跨 Decimal/float 家族合併(截斷 vs banker's rounding 在 tick 邊界分岔);
不統一吞例外行為(stock_source._milli 的 ValueError 被 _parse_dk_rows 轉 skipped 計數)。
注意 stock_engine.py:395 對 to_milli 是函式內 late import,grep 易漏。

### B-D10 | P2 | HTML 刮取 regex + `_text()` 兩份(stock_names.py:51-54,71-72 / stkfut_map.py:25-31)
抽 `copycat/htmltable.py`(ROW_RE/TD_RE/strip_tags(cell, *, nbsp=False))。
⚠ &nbsp; 處理 per-caller 保留:stkfut_map._contract_unit 靠 isdigit() 找欄,改動會靜默退回
小型契約(:46-47 docstring 記載的踩坑)。write_names/write_map 可加 fileio.write_versioned_json。

### B-D11 | P2 | route 層小重複:BAD_CODE 檢查三份(app.py:525/:540/:561);index 就緒閘內嵌四份(:571/:601/:620/:627,stock 已有 _stock)
補 `_index(request)` + `_valid_code` dependency。
⚠ 錯誤碼不可統一(CORR_NOT_READY/RIVER_NOT_READY 前端分流)。

### B-D12 | P2(測試)| `_JsonSocket`+`_FakeApi`+`_ok` 六份逐字複製(tests/live/ 六檔)
抽 tests/live/conftest.py 或 tests/helpers/tc4_fakes.py。
test_backfill_tc4.py:35 變體(不走 zmq extras)不收。

### B-D13 | P2(測試)| `FakeTxoSource` 六份(tests/server/ 六檔,唯一差異 docstring)
抽 tests/server/conftest.py。make_client 形狀相近但 kwargs 各異,不泛型化。

## P3 — 不建議動

- B-D14 🚨 分鐘鍵家族五份:三種分桶約定(+1 / 不+1 / floor)× 三種回傳型別,合併會整線位移
  一分鐘且零 assertion 紅。all_day_window 三行重複是刻意(避免逆依賴)。
  `_taipei_time` zfill(12) 只對台期交成立,不可泛化。維持現狀。
- B-D15 river_backfill.collect_1k_minutes ↔ tc4._collect_history:docs/next-time.md 已記錄
  為已接受的債 + 收斂條件(第三個回補路徑出現時)。本輪不動。
- B-D16 🚨 rollover 兩段式 stock vs index:觸發證據不同(首筆新日 tick vs 1K 回補+牆鐘閘)、
  reset 範圍相反(stock 保 book/meta)。合併會改假日行為且無測試會紅。backfill worker
  三種併發模型同理不併。
- B-D17 OverlayCache ↔ BarsCache.daily_get/put:「空」判準領域專屬 + bars 有負向快取,
  抽 predicate 殼淨負值。

## 掃過無重複
market.py(與個股頁零交集;stock-tick.ts 鏡像是有註解背書的刻意)、stock_state.py(除 :142
minute_key 一行屬 B-D14)、overlay.py compute_*、stock_watchlist.py、stock_models.py
制度專屬函式(parse_futures_realtime=parse_stock_realtime 是做對的別名)、bars.py
(build_daily/build_period 分開有 review P2-1 理由)、fileio.py/tc4common.py(前輪抽取成果)。

## 建議執行順序
B-D1(零風險同檔)→ B-D5(搬家+參數化)→ B-D4 → B-D2/B-D3(綁一起,唯一碰 TXO 實盤路徑,
單獨 commit)→ B-D12/B-D13(測試層)。B-D6~B-D11 視精力。B-D14~B-D17 標不動。
