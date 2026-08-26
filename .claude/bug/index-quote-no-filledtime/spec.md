# /bug index-quote-no-filledtime — spec(originating bug description)

## 症狀(user)
「加權分時線中間又卡住」。08-26 12:21 `/api/index/state`:`twse.p` 在跳(45811910,stale=False),`twse.minutes` 只到 1059
(119 鍵),11:00 起 82 分鐘全空;櫃買(MIS 輪詢)完整到 12:21。log `index 分時自癒` 08-20 起每個交易日 67–133 行,
形狀 = 每 7 分一發「落後 >3 分」,換窗口那發有進展、同窗口那發「零新分鐘鍵」,階梯封頂後全「無進展」。

## 根因(2026-08-26 12:23 只聽不訂 probe 實證)
TC4 推的 IX0001 REALTIME quote:`FilledTime='0'`、`PreciseTime='0'`(只有 TradeDate / TradingPrice / Reference / High / Low)。
`index_engine._handle_quote` 用 `minute_key(FilledTime, utc=True)` → `'000000'` → +8 → `0801` → 域外 → None →
分鐘不寫、只更新 `p`。分鐘全靠 1K 自癒補;窗口階梯封頂後 1K 回同一份 → 停在那一分鐘。

## 要求
1. `FilledTime` 去零為空(`'0'` / `''` / `'000000'`)→ 以注入的 `_now_fn()`(台北牆鐘)算分鐘鍵(`minute_key(utc=False)`,
   終點標記 floor+1 語意與 FilledTime 路徑同一把尺)。
2. `FilledTime` 有值 → 照舊 UTC+8(白名單:期貨 / 個股 / 既有測試 `_quote(filled="13015")` → 0931 不變)。
3. 牆鐘落在 0901–1330 域外(試撮前 / 收盤後快照)→ 不寫分鐘、現價照更新、不炸。
4. 不動:1K 自癒判準與階梯、`_pending_date` 換日路徑、MIS 路徑、`minute_key` 本身。
5. 沉澱:tc4-market-facts 事實(IX0001 無時間欄位 + 只聽不訂 probe 寫法);river_models docstring 更正。

## 驗證 seam
`tests/server/test_index_engine.py::TestQuoteWithoutFilledTime`(FakeIndexSource.on_message → engine.state())。
真環境:prod 收盤後重啟(user 拍板不在盤中重啟),次一交易日 09:10 打 `/api/index/state` 看 `twse.minutes` 最大鍵貼著牆鐘、
log `index 分時自癒` 盤中應近零。

## 非目標
- 自癒階梯封頂後仍每 15 分空打到午夜(推播修好後 lag 條件不成立,自然不發)。
- 期貨 K 棒落後量測 log(next-time 08-26 另條)。
