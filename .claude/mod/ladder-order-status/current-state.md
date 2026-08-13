# current-state — 閃電梯掛單顯示 + 庫存刷新提速

日期:2026-08-13。/mod L 級(前端 ~9 檔 + 後端 2 檔)。branch `mod/ladder-order-status`。

## 需求(user 拍板,方案已成形)

1. **掛單顯示**:閃電梯每個價位列顯示自己的委託狀態,格式「未成交(已成交)」,買賣兩側分開。
   例:掛買 1 口未成交 →「1(0)」;全部成交 →「(1)」。
2. **庫存刷新提速**:成交後 balance 重查 debounce 2.0s → 0.5s;合併語意(連續成交只查一次)
   保留;前端 useCapital 200ms invalidate debounce 不動;**送單路徑不動**(user 已確認延遲
   純屬顯示層,送單為同步直送群益)。

## 現況地圖(逐檔)

### 前端 — 三座梯的「我的單」路徑**不是一條**(user 敘述的修正)

user 說「渲染位置在共用畫面層 LadderView.tsx…三座梯一體受益」— **實況只有兩座**走 LadderView:

| 梯 | container | 聚合函式 | 畫面層 |
|---|---|---|---|
| 現股 | `stock/PriceLadder.tsx` | 檔內 `aggregateLots(orders, code)`(138-155 行) | `stock/LadderView.tsx` |
| 個股期 | `stock/StkfutLadder.tsx` | 檔內 `aggregateLots(orders, contract)`(54-72 行) | 同上 |
| 期貨 | `futures/FuturesLadder.tsx` | `lib/futures-ladder.ts::splitMyLots`(44-65 行) | **自畫列**(397-454 行),lot 烘進 `FutLadderRow.myQty/mySeqNos` |

- 兩份 `aggregateLots` **逐字相同**(除參數名/null 早退):過濾
  `!actionable || stock_no !== key || price === null`,聚合 `qty += max(0, order_qty - filled_qty)`
  + `seqs`,產出 `Map<priceMilli, LadderLot>` buy/sell 兩張。歷史:stkfut-contracts R2-4 抽
  LadderView 時 container 各留一份(當時註明行為零變更)。
- `splitMyLots` 差異:單一 map(期貨紅方格不分買賣側)、skip `remaining <= 0`、輸出 sorted
  array `MyFutLot{priceMilli,qty,seqNos}`,由 `buildFuturesLadder` 烘進 rows。
- **共同點:三者都只聚合 actionable 活單,已成交量(filled)零痕跡**。

### 畫面層現況

- `LadderView.tsx` 234-346 行價位列:`buyLot`/`sellLot` 存在 → 渲染**刪單紅方格 button**
  (`aria-label="刪 {價} 買單/賣單"`,textContent = 殘量),onClick → `onCancelLot(lot)`
  逐 seq 直刪。`LadderLot = { qty, seqs }`(LadderView.tsx 26-29 行)。
- `FuturesLadder.tsx` 410-419 行:`r.myQty > 0` → 同款紅方格(`aria-label="刪 {價} 掛單"`),
  onClick → `cancelLot(r.mySeqNos)`。
- 版面鐵律(LadderView 檔頭 + footer 註):**武裝中的點擊目標不得位移**;紅方格在買/賣欄
  內緣 inline,寬度隨字數增長會壓縮 flex-1 點價鈕(既有行為,多位數殘量已如此)。

### 資料鏈

- `GET /api/capital/orders` → `OrderRecord`(capital/models.py 110-132):有
  `price / order_qty / filled_qty / actionable / buy_sell / stock_no / seq_no`。
  `actionable = _RANK in (1,2)`(store.py 184);rank 3 = 全部成交/已刪單/失敗/逾時/退單。
  **已刪單可能帶 filled_qty > 0(部分成交後刪)**;失敗/退單 filled_qty 恆 0。
  store 生命週期 = 當日 session(委託清單 = 今日單)。
- 更新即時性:`/ws/capital` 推 `capital_order` 事件(client.py 294,成交當下即推)→
  `useCapital.ts::useCapitalStream` 200ms trailing debounce invalidate `capital-orders`
  → TQ refetch。輪詢兜底 30s。**此鏈零改動即可支撐需求 1**。
- 市價單 `price === null` 不上階梯(既有語意,已成交的市價單也不會顯示)。

### 後端 — balance 鏈(需求 2)

- `capital/client.py:291-292`:成交回報(status_raw=="D")→ `_mark_balance_dirty()`。
- `client.py:323-324`:`_mark_balance_dirty(self, delay_s: float = 2.0)` →
  `_balance_due = monotonic() + delay_s`。**唯一 caller 用預設值**;merge 語意 = 後到的
  成交直接推遲 due(重設),幫浦圈只在 due 到時查一次。
- `client.py:326-341`:`_maybe_query_balance` 由 `_pump_once`(513 行)每輪呼叫,
  幫浦圈週期 ~0.05s(cmd_q timeout)→ 0.5s debounce 解析度足夠。
- 查詢鏈:GetRealBalance → profit → open interest 串行合併後 set_positions → 廣播
  `capital_position` → 前端 200ms debounce invalidate。**改 delay 只縮排程,不碰鏈**。

## Caller map(動態用法已 grep)

- `aggregateLots`:兩檔各自檔內私有,無外部 caller;測試經渲染間接驗
  (PriceLadder.test.tsx SC-7 節 444-473、StkfutLadder.test.tsx 273-292)。
- `LadderLot`:LadderView(型別 + 渲染)、PriceLadder、StkfutLadder(cancelLot 參數)。
  無其他 import(grep 全 repo 含 .claude 歷史 diff,無動態用法)。
- `splitMyLots` / `FutLadderRow.myQty/mySeqNos`:FuturesLadder.tsx + futures-ladder.test.ts
  (118-160 行 3 案)+ buildFuturesLadder 自身。
- `_mark_balance_dirty` / `_balance_due`:client.py 內部 + tests/capital/test_client.py
  1156/1161(只 assert None/not None,**無測試釘 2.0 值**)。

## 既有測試(該紅 / 不該紅預判)

| 測試 | 現 assert | 判定 |
|---|---|---|
| PriceLadder.test.tsx 465-466(SC-7)| 紅方格 textContent `"4"` / `"1"` | **該紅**(格式變 `"4(1)"` 等)|
| StkfutLadder.test.tsx 287-288 | 同上 `"4"` / `"1"` | **該紅** |
| FuturesLadder.test.tsx 329(SC-8)| `"4"` | **該紅** |
| futures-ladder.test.ts 118-160 splitMyLots 3 案 | 輸出 shape `{priceMilli,qty,seqNos}` | **該紅**(shape 加 filled 欄)或不紅(視實作,加欄不驗舊案可不紅)|
| test_client.py 1146-1161 | `_balance_due` None/not None | **不該紅**(不釘值)|
| 其餘(點刪 seq 清單、他契約過濾、部位條、武裝)| — | **不該紅** |

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 紅方格內容 | 殘量單一數字 | `未成交(已成交)`;全成交後轉不可點徽章 `(N)` |
| 聚合輸入 | 只吃 actionable | actionable 出殘量+seqs;**全部單**出 filled 量 |
| 聚合實作 | 兩份重複 + splitMyLots 一份 | 重複兩份抽共用 lib(🔵)後擴充(🔴) |
| balance debounce | 2.0s | 0.5s(僅預設值,語意不變) |
| backward compat | — | 純 UI + 內部 debounce,無對外 API / 無資料格式 / 無 migration |
