# change-spec:閃電梯市價單成交後以成交價落格(mod/ladder-market-fill-marker)

> 2026-09-05。來源 = user 回報「市價買跟市價賣時 閃電下單不會出現下單的點位」。
> grilling 拍板:Q1 兩格各一張(逐筆成交價,不取均價);Q2 user 不在意單的種類,
> 只要徽章出現 → 採「委託價缺(null / 0)或 `price_type === "market"` 的單改用 fills 表落格」
> (涵蓋群益 APP 手機下的市價單;它們 `price_type` 恆 null,唯一線索是委託價 0 / 空)。
> 規模:S(前端 1 lib + 1 container + 測試 2 檔;無後端、無 API、無 migration)→ 跳 tickets,
> spec 只留本檔。seams(user 已知情):`lib/ladder-lots.ts::aggregateLots` 純函式 +
> `PriceLadder` 元件渲染。

## 0. 目標一句話

現股閃電梯上,市價買 / 賣成交後,在**實際成交的價位列**出現 `(n)` 成交徽章(n = 該價位成交張數),
與限價單全成交徽章同一個外觀;送單那段一個字不動。

## 1. 根因(讀 code 確認)

`aggregateLots` 以 `OrderRecord.price`(委託價)當梯列鍵。現股市價單送群益 `bstrPrice="0"`
(PR #94 避 1068),回報委託價 0 / 空 → `price === null` 被跳過、`price === 0` 對不到任何列。
fills 表(`/api/capital/fills`,每筆帶 seq_no + 真實成交價 + 側 + 量)同頁 `StockChart` 已在拉,
TanStack Query 共用 cache;`capital_order` WS 事件同時 invalidate orders 與 fills。

## 2. 成功條件(SC)

| # | 條件 | 驗證 |
|---|---|---|
| SC-1 | `aggregateLots(orders, key, dates, excludeUnit, fills)`:委託價缺(`price === null` 或 `price === 0`)或 `price_type === "market"` 的單,**已成交量改由 fills 表同 seq 的逐筆決定**:每筆成交在 `round(fill.price × 1000)` 那格累加 `filled += fill.qty`,`qty` 0、`seqs` 空;側取 fill 的 `buy_sell` | `ladder-lots.test.ts` 新案:市價單 2 張成交 100 / 100.5 各 1 → buy map 兩格各 `{qty:0,filled:1,seqs:[]}` |
| SC-2 | 這類單**未成交殘量不上梯**(沒有價位可掛;現況相同),fills 未給或無同 seq 成交 → 零 entry(現況相同) | 既有案「市價(price=null)全排除」改述為「無 fills 時不上梯」+ 新案 fills 給了但 seq 不符 |
| SC-3 | 日期界與零股閘沿用單的判準:`countFilled`(活單恆計 / 終態看 `date`)與 `excludeUnit` 先在單上過,過了才看 fills | 新案:終態市價單 date 昨日 → 零 entry;零股市價單(unit 股)→ 零 entry |
| SC-4 | `PriceLadder` 接 `useCapitalFills()` 餵進 `aggregateLots`;市價買單 2 張成交 100 / 100.5 各 1 → 兩列各一顆 `(1)` 徽章(`data-testid="ladder-filled-lot"`),不可點、無刪單 aria | `PriceLadder.test.tsx` 新案 |
| SC-5(UI 可指認) | 真環境:下一筆閃電梯市價單成交後,梯上成交價那列出現 muted 邊框 `(n)` 徽章(與限價全成交徽章同款);委託列表「市價」標籤照舊 | prod 重啟 + 重 build 後 user 過目;09-04 已無 server 可回放,無法本輪親驗 |

## 3. 不能破壞的既有行為白名單(W)

| # | 行為 | 守門 |
|---|---|---|
| W1 | 限價單(price 有效且 price_type ≠ market)的聚合算式:殘量 / 已成交 / seqs 刪單入口 / 同價混合 —— 一字不改,**不看 fills** | `ladder-lots.test.ts` 既有 12 案全綠 |
| W2 | 零股排除 `excludeUnit="股"`、終態單嚴格今日日期界、活單成交恆計 | 既有案 + SC-3 |
| W3 | `StkfutLadder` 共用同函式、不傳 fills → 行為零差(其市價鈕實為限價貼漲跌停 + IOC,委託價有效) | `StkfutLadder.test.tsx` 全綠 |
| W4 | `FuturesLadder` 走 `splitMyLots`,不動 | 不改檔 |
| W5 | 分時圖成交點 `fill-marks.ts` 不動(只改 docstring 分工敘述) | `fill-marks.test.ts` 全綠 |
| W6 | 市價買 / 賣鈕送單路徑(`marketOrder`、`price_type:"market"`、防抖、hint)不動 | `PriceLadder.test.tsx` 既有市價鈕案全綠 |
| W7 | LadderView 渲染:徽章分支 `lot.filled > 0` 守門、`lotText` 不動 | `LadderView.test.tsx` 全綠 |
| W8 | 失敗 / 退單零痕跡;市價單失敗(filled 0、無 fills)同樣零痕跡 | 既有案 |

## 4. Backward compat

- `aggregateLots` 第五參數 optional,兩個既有 caller 中只有 `PriceLadder` 傳;舊後端(無
  `/api/capital/fills`,404 → `[]`)= 現況(不畫)。無 API / 資料格式改動。
- 已知殘餘:市價單**成交前**那段(實測 124 ms)梯上仍無標記;`price` 解析失敗的異常單會走 fills
  路徑,畫的仍是真實成交價,不是假資訊。

## 5. 實作順序

🔴 `ladder-lots.ts` + 既有案改述 → 🟢 新案 → 🟢 `PriceLadder.tsx` 接 fills + 元件案 → 🔵 docstring(fill-marks 分工)。
