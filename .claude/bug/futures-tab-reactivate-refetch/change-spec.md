# bug/futures-tab-reactivate-refetch — 期貨 tab 切回立即重抓 + bars fetch timeout

日期:2026-08-28。來源:08-28 拍板題 4(handoff `copycat-handoff-2026-08-28-q4-q5.md` §1.1)—— handoff 寫的根因
(`useMarketBars` 未接夜盤窗)經核**不成立**(期貨 tab 走 `useFuturesBars`,已接 `inFuturesAllDayHours`);
user 08-28 重述配方:「個股頁做單 → 切期貨 tab → 該商品(微台 / 小台)分時圖凍住、『落後 N 根(TC4 回補中)』常亮、
等多久都不動、換商品才好」。診斷全文見 memory `q4-futures-lag-diagnosis-0828`。

## 1. 診斷結果 → 兩個修法

| 事實 | 證據 | 修法 |
|---|---|---|
| 期貨 tab 藏起來時輪詢是關的(設計);切回時 TQ 只重設 60 s 計時器**不重抓** → 切回當下必亮提示、最多 60 s | 08-28 11:43–12:17 prod + preview 實測(server log 無請求;`setInterval` 儀器看到計時器準時 fire) | (A) `useFuturesBars` 改走 TQ `subscribed: active`:退訂 = 不輪詢;重訂 + `staleTime: 0` → `shouldFetchOnMount` 立即重抓 |
| 台指不卡、微台 / 小台會卡:個股頁「台指期」疊線的 `useFuturesBars("TXF")` observer 同 queryKey,在個股頁時每 60 s 養活 TXF | server log 11:58–12:02 在個股頁期間 TXF 每分鐘一發、TMF 零發 | 同 (A) |
| 「永遠不更新」**未重現**;機制上成立的候選:`fetch` 無 timeout / 無 signal,TQ 對同 query 在飛時把後續 refetch 併進同一 promise → 一趟永不回就永久凍結,換商品(新 query)才好 —— 與 user 三特徵吻合 | `query-core/query.js` dedup;08-28 切回那趟實測 14 s 才回(後端搶 `api.lock`) | (B) `lib/fetch-timeout.ts::fetchWithTimeout` 30 s + 接 TQ signal;超過 15 s 才回 `console.warn` 留證據 |

不做:後端 `/api/market/bars` 慢請求 WARNING(要重啟才生效、且前端 warn 已能定位那一趟)→ 留尾。

## 2. Caller map

- `useFuturesBars(key, mode, active, enabled)`:`FuturesChart`(intraday + day 兩個 observer,`active = tab === "futures"`)、
  `App.tsx:193` 個股頁疊線(`active = enabled = txfWanted`)。`subscribed` 對後者:`txfWanted=false` 時本來就 `enabled=false`,無差。
- `fetchFuturesBars` 只有 hook 內一個 caller。`fetchWithTimeout` 新檔,零其他 caller(`useMarketBars` / `useStockBars` 不動 —— 不順手擴 scope)。

## 3. 既有行為白名單

1. 切回 tab **不閃「載入中」**(退訂不是 `enabled: false`;cache 舊圖留著等新料)。
2. 60 s 輪詢節奏、`inFuturesAllDayHours` 窗、`FUTURES_MINUTE_DAYS = 5`、queryKey 形狀不變。
3. 日 K observer `staleTime: Infinity`:重訂不重抓。
4. `enabled=false`(疊線鈕關)→ 掛載不打、回焦不打 不變。
5. TQ `retry: 1` 不變;timeout 後走同一條 error / retry 路徑。

## 4. 行為改動(🔴 三筆)

1. `active` false→true 立即重抓(不等 60 s)。
2. **事前標該變**:`active=false` 掛載不再抓那一發(`useFuturesBars.test.ts` 「active=false」案 1 → 0;`FuturesChart.test.tsx` LF-2 案 2 → 0;
   `enabled` 案改成 active 與 enabled 同值)。App 的期貨 tab 由 `visited.futures` 閘住,第一次掛載必在 active=true 時,真實路徑上這一發本來就不存在。
3. bars 請求 30 s timeout(含 body;`TimeoutError` → TQ error / retry);> 15 s 才回 → `console.warn`。

review round 1 後追加(🔴):
4. 這幾把 query `gcTime: Infinity`(兩軸各一條 P1:退訂後 observer 歸零、TQ 預設 5 分鐘 gc → 待久切回 data undefined 閃「載入中」+ 日 K 重抓;鍵集合有界 3 商品 × 2 tf)。
5. `FuturesChart` 有舊 data 時不再整張換「K 線載入失敗」,改在提示列印「K 線更新失敗:<msg>(沿用上一份,每分鐘重試)」(Spec F-3;timeout 後整張圖抽掉 60 s 比凍住還糟)。
6. queryFn 吃 TQ signal 的副作用:切走 tab 時在飛的那趟被 TQ 主動中止(`cancel({revert:true})`),不再讓它跑完落 cache(Spec F-5;切回反正立即重抓)。

## 5. Seams

- `useFuturesBars.test.ts`:`active false→true → 立即重抓`(紅先行:改前 1 → 期望 2)、`queryFn 把 timeout signal 交給 fetch`、`慢請求 console.warn`。
- `lib/fetch-timeout.test.ts`:超時拒絕 / 外層 abort 轉發 / 成功清計時器。

## 6. 留尾

- 「永不回的那一趟」根因未證:前端 warn 落地後等 user 真事件(切回 → 記時刻 + 商品)。
- 後端 `build_minute` 慢請求 WARNING(定位卡在 hist / today 哪段)。
- `useMarketBars` / `useStockBars` 同款 timeout 未做。
