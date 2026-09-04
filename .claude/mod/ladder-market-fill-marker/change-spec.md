# change-spec:閃電梯市價單成交後以成交價落格(mod/ladder-market-fill-marker)

> 2026-09-05。來源 = user 回報「市價買跟市價賣時 閃電下單不會出現下單的點位」。
> grilling 拍板:Q1 兩格各一張(逐筆成交價,不取均價);Q2 user 不在意單的種類,
> 只要徽章出現 → 採「委託價缺(null / 0)或 `price_type === "market"` 的單改用 fills 表落格」
> (涵蓋群益 APP 手機下的市價單;它們 `price_type` 恆 null,唯一線索是委託價 0 / 空)。
> 規模:S(前端 1 lib + 1 container + 測試 2 檔;無後端、無 API、無 migration)→ 跳 tickets,
> spec 只留本檔。seams(user 已知情):`lib/ladder-lots.ts::aggregateLots` 純函式 +
> `PriceLadder` 元件渲染。

> **2026-09-05 追加拍板(user)**:限價單也統一 —— user 實際遇過「掛 98.5 買、成交 98.3,梯上徽章在 98.5、
> 成本線在 98.3」兩條線說的不是同一件事。本輪**所有單的已成交量一律以 fills 表逐筆成交價落格**;
> 未成交殘量(與 seqs 刪單入口)留在委託價列。成本 / 損益平衡線本就吃部位均價(成交價),不動。

## 0. 目標一句話

現股閃電梯上,**任何單**(市價 / 限價)成交後,已成交張數標在**實際成交的價位列**(`(n)` 徽章,或
與同列活單合併成 `殘量(n)` 紅方格);未成交殘量留在委託價列;送單那段一個字不動。

## 1. 根因(讀 code 確認)

`aggregateLots` 以 `OrderRecord.price`(委託價)當梯列鍵。現股市價單送群益 `bstrPrice="0"`
(PR #94 避 1068),回報委託價 0 / 空 → `price === null` 被跳過、`price === 0` 對不到任何列。
fills 表(`/api/capital/fills`,每筆帶 seq_no + 真實成交價 + 側 + 量)同頁 `StockChart` 已在拉,
TanStack Query 共用 cache;`capital_order` WS 事件同時 invalidate orders 與 fills。

## 2. 成功條件(SC)

| # | 條件 | 驗證 |
|---|---|---|
| SC-1 | `aggregateLots(orders, key, dates, excludeUnit, fills)`:**任何單**只要 fills 表有同 seq 的成交,已成交量改由逐筆決定:每筆成交在 `round(fill.price × 1000)` 那格累加 `filled += fill.qty`(側取 fill 的 `buy_sell`);該單的 `filled_qty` 不再落委託價列。市價單(委託價缺:`price === null` / `0`,或 `price_type === "market"`)沒有委託價列,只有這條路 | `ladder-lots.test.ts`:市價單 2 張成交 100 / 100.5 各 1 → 兩格各 `{qty:0,filled:1,seqs:[]}`;限價 98.5 買成交 98.3 → 98.3 列 `(1)`、98.5 列無 entry |
| SC-1b | 未成交殘量與 `seqs`(刪單入口)**留在委託價列**:活單部分成交於較優價 → 委託價列 `{qty:殘, filled:0, seqs:[seq]}` + 成交價列 `{qty:0, filled:n, seqs:[]}`;市價單殘量沒有價位可掛,不上梯(現況相同) | 新案:活單 98.5 買 2 張、成交 98.3 × 1 |
| SC-2 | **成交價不明時退回委託價**:該 seq 在 fills 表找不到成交(fills 未傳 = 個股期梯;舊後端 404 → `[]`;或 query 尚未載入)→ `filled_qty` 照舊落委託價列(= 現況);市價單此時零 entry(現況相同) | 既有 12 案(不傳 fills)全綠 = 這條;新案:fills 給了但 seq 不符 → 限價單退回委託價、市價單零 entry |
| SC-3 | 日期界與零股閘沿用單的判準:`countFilled`(活單恆計 / 終態看 `date`)與 `excludeUnit` 先在單上過,過了才看 fills | 新案:終態市價單 date 昨日 → 零 entry;零股市價單(unit 股)→ 零 entry |
| SC-4 | `PriceLadder` 接 `useCapitalFills()` 餵進 `aggregateLots`;市價買單 2 張成交 100 / 100.5 各 1 → 兩列各一顆 `(1)` 徽章(`data-testid="ladder-filled-lot"`),不可點、無刪單 aria | `PriceLadder.test.tsx` 新案 |
| SC-5(UI 可指認) | 真環境:下一筆閃電梯市價單成交後,梯上成交價那列出現 muted 邊框 `(n)` 徽章(與限價全成交徽章同款);委託列表「市價」標籤照舊 | prod 重啟 + 重 build 後 user 過目;09-04 已無 server 可回放,無法本輪親驗 |

## 3. 不能破壞的既有行為白名單(W)

| # | 行為 | 守門 |
|---|---|---|
| W1 | 限價單的**殘量 / seqs 刪單入口 / 同價混合**算式不變且恆在委託價列;已成交量在「成交價 = 委託價」(絕大多數限價成交)時畫面零差;**不傳 fills 時(個股期梯 / 舊後端)整套算式一字不改** | `ladder-lots.test.ts` 既有 12 案(不傳 fills)全綠;新案「成交價 = 委託價 → 同一格」 |
| W2 | 零股排除 `excludeUnit="股"`、終態單嚴格今日日期界、活單成交恆計 | 既有案 + SC-3 |
| W3 | `StkfutLadder` 共用同函式、不傳 fills → 行為零差(其市價鈕實為限價貼漲跌停 + IOC,委託價有效;個股期成交價與委託價可能不同,但本輪不接 fills,留待另案) | `StkfutLadder.test.tsx` 全綠 |
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
- fills query 載入前的一拍(`fillsData` undefined)= 退回委託價路徑,載入後徽章移到成交價 —— 只在
  「成交價 ≠ 委託價」時可見一次位移,同 orders query 本身的載入拍。
- 成本 / 損益平衡線(`positionRows` 吃部位 `avg_price`)本就是成交均價,不在本輪範圍、不動。

## 5. 實作順序

🔴 `ladder-lots.ts` + 既有案改述 → 🟢 新案 → 🟢 `PriceLadder.tsx` 接 fills + 元件案 → 🔵 docstring(fill-marks 分工)。
