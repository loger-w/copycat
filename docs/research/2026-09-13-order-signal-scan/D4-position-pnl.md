# D4 — 下單:部位、損益與稅費計算

掃描日 2026-09-13 · 對象 `C:/side-project/copycat` · 以「這是一個要下實單的系統」為準繩

量測環境:Windows 11、Python 3.13.13、專案 `.venv`(stdlib-only runtime)。
**實測**來源有三:(a) `logs/server-*.log` 79 檔 24 MB 的真實 prod 記錄;(b) `data/audit/capital-*.jsonl` 22 檔;
(c) 本輪寫的 micro-benchmark(`bench_pos.py` / `mine_chain.py`,同目錄)。**推估**一律標明。

---

## 0. 一句話結論

**這一段不是效能問題,是正確性與可觀測性問題。**
部位鏈的純 Python 算術在 prod 規模(63 張委託 × 7 列部位)實測 **0.036 ms**,
而同一條鏈的端到端實測 **p50 1.94 s / p99 6.43 s** —— 算術佔 **0.002%**,
其餘全在群益 COM 往返與一個寫死的 0.5 s debounce。
真正該修的是:**期貨部位的損益結構性恆為 null**、**期貨部位解析器零 prod 樣本卻掛著真平倉鈕**、
**`avg_source` 的兩個產生點只有一個有機驗**、以及**費率只有單一來源沒有任何對帳**。

---

## 1. 現況地圖:部位 / 損益 / 稅費怎麼流

### 1.1 三條產生路徑

部位列(`Position`)只有三個產生點,語意各不相同:

| 路徑 | 產生點 | market | kind | avg_price | avg_source | today_qty | pnl_base |
|---|---|---|---|---|---|---|---|
| 券商即時庫存 | `balance.py::parse_balance_line`(OnRealBalanceReport idx14) | `sec` | T→cash / C→margin / L→short / **T 負股數→daytrade_sell** | **恆 None**(該報告無均價欄) | None | store 補 | None |
| 券商期貨部位 | `balance.py::parse_open_interest_line`(OnOpenInterest) | `fut` | 恆 cash | idx6 平均成本 | **恆 None** | 恆 0 | **恆 None** |
| 成交樂觀套用 | `store.py::_apply_fill_locked`(D 回報當下) | sec/fut | `_FILL_KIND[idx6 資券別]` | 這張單的**純成交均價** | `"fill"` | store 補 | None |

均價 / 損益的**唯一補齊點**是 `client.py::_on_profit_complete`(OnProfitLossGWReport,未實現-彙總):
它只走 `self._pending_sec`(= 庫存段那批 **sec** 列),逐列寫入

```python
# copycat/capital/client.py:610-616
p.avg_price = r.avg_price
p.avg_source = "broker"          # ← broker 口徑的唯一產生點
p.pnl_base = r.pnl
p.pnl_base_price = r.price
p.pnl_cost = r.cost
```

### 1.2 回查鏈的形狀(COM 執行緒,串行)

```
D 成交回報 → store.apply_reply → _apply_fill_locked(樂觀套用,實測 0.20 ms p50)
                               → _emit capital_position{source:"fill"}   ← 先到
           → _mark_balance_dirty(0.5)            ← 寫死 0.5 s debounce
50 ms 幫浦圈 → _maybe_query_balance → GetRealBalanceReport(rc 同步回、結果走事件)
   ↳ OnRealBalanceReport ×N → BalanceCollector.feed → _on_balance_complete(_pending_sec)
       → GetProfitLossGWReport
   ↳ OnProfitLossGWReport ×N → _on_profit_complete(**寫 avg_source / pnl_base**)
       → GetOpenInterestGW
   ↳ OnOpenInterest ×N → _on_oi_complete → merge_fut_positions
       → _finalize_positions(sec + fut)→ store.set_positions(全量覆蓋 + 水位後增量重套)
       → _emit capital_position{count}
前端 useCapitalStream:WS capital_position → 200 ms trailing debounce → invalidate
       → GET /api/capital/positions(每列 asdict + stock_code_of 衍生欄)
       → PriceLadder / WatchlistSidebar / StockPage header / GroupGridView 四處消費
```

三段查詢是 **`_pending_sec` 串行**:`_maybe_query_balance` 見 `_pending_sec is not None` 就整輪不發,
所以鏈在飛時的成交只更新 `_balance_due`,鏈結束後補查(成交不漏,但延遲疊加)。

### 1.3 稅費與打平線:唯一一份算式在前端

**後端 `copycat/capital/` 全域零手續費、零稅、零打平線**(已 grep 驗證:
`0.001425` / `SELL_TAX` / `discount` 在 `copycat/capital/` 與 `copycat/server/capital_api.py` 均無命中)。
`safety.py::_check_qty_amount` 的金額閘是 `price × qty × multiplier`,純名目,不含費。

唯一算式在 `frontend/src/lib/ladder-position.ts::positionEcon`(L80-134),常數:

```ts
FEE_BASE = 0.001425        // 牌告手續費,買賣各一次
SELL_TAX = 0.003           // 證交稅
SELL_TAX_DAYTRADE = 0.0015 // 現股當沖減半
SHORT_BORROW = 0.0008      // 融券借券費(一次性)
FEE_DISCOUNT_DEFAULT = 1.8 // 折數
feeRate(d) = FEE_BASE * d / 10
```

多方:`cost = (avg_source==="broker") ? avg : avg*(1+f)`;`BE = cost/(1−f−t)`;
`pnl = (p−cost)·Q − p·Q·(f+t)`。
空方:`BE = avg·(1−f−t−b)/(1+f)`;`pnl = (avg−p)·Q − avg·Q·(f+t+b) − p·Q·f`。
`t` 是**按張數加權**的有效賣出稅率:`t = (T·0.0015 + (|qty|−T)·0.003)/|qty|`,
`T = clamp(today_qty, 0, |qty|)` 且只在 `kindTraits(kind).halfTaxToday`(cash / daytrade_sell)時取值。

消費者恰好兩個:`PriceLadder.tsx::positionRows`(閃電梯部位條 + 梯內均價 / 打平標記)與
`position-summary.ts::secSummary`(側欄 chip / 單檔 header / 群組卡三處共用)。
**期貨完全不走它** —— `StkfutLadder.tsx:344` 明寫「不套現股稅費口徑」,只印 `pnl_base`。

---

## 2. 端到端延遲預算

### 2.1 成交 → 畫面上的部位 / 打平線

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | D 回報進 handler → 樂觀套用 + WS emit | `client.py:419-437` / `store.py:332-482` | **p50 0.20 ms / p90 0.60 / p99 4.80 / max 10.20** | **實測**(189 筆 prod log「成交樂觀套用部位 … (N ms)」) | 此時 `avg_source="fill"`,打平線偏高 ~0.5 檔 |
| 2 | WS → 前端 200 ms debounce → GET /positions | `useCapital.ts:126-142` | ~200–210 ms | **推估**(debounce 常數 + 本機 HTTP <5 ms) | |
| 3 | `_mark_balance_dirty(0.5)` debounce | `client.py:423` | **500 ms 固定** | 讀 code | 連續成交只查尾端一次;非自適應 |
| 4 | 50 ms 幫浦圈 poll 粒度 | `client.py:797-809` | 0–50 ms(平均 25) | 讀 code | |
| 5 | `GetRealBalanceReport` 往返 + N 事件 + `##` | COM | ~**560 ms p50**(= 1061 − 500 debounce) | **實測**(179 筆「庫存段收齊 … 自成交回報到達起 N ms」p50 1061 / p90 3249 / p99 5486) | p90/p99 的高值來自「鏈在飛 → 下一輪才查」 |
| 6 | 庫存段 → 損益段(`GetProfitLossGWReport`) | COM | **p50 566 / p90 702 / p99 1000 / max 2122 ms** | **實測**(178 輪配對差) | **`avg_source` 要到這裡才變 broker** |
| 7 | 損益段 → 期貨部位段(`GetOpenInterestGW`) | COM | **p50 310 / p90 321 / p99 566 / max 627 ms** | **實測**(178 輪) | prod 實測 fut 列數恆 0 |
| 8 | `merge_fut_positions` + `set_positions` + log + emit | `client.py:649-679` / `store.py:659-724` | **p50 1 ms / p99 9 / max 24 ms**(log 量測);純 `set_positions` 算術 **0.036 ms p50 / 0.054 p99** | **實測**(log 段差 + bench) | 算術只佔量到的 1 ms 的 ~4% |
| 9 | `GET /api/capital/positions` 序列化 | `capital_api.py:277-291` | **7 列 × 2.27 µs asdict = 16 µs**;fut 列另 +4.71 µs/列(含一次 `Path.stat`) | **實測**(bench) | |
| 10 | 前端 `positionEcon` × 部位列數 | `ladder-position.ts:80` | <1 µs/列 | **推估**(~20 flops,無配置) | 每 tick 重算,量級可忽略 |
| **合計** | **成交 → 樂觀部位上畫面** | | **≈ 0.2 ms + 210 ms = 0.21 s** | 實測+推估 | 均價語意 = fill |
| **合計** | **成交 → 券商口徑均價 / 打平線上畫面** | | **p50 ≈ 2.15 s / p90 ≈ 4.3 s / p99 ≈ 6.6 s** | **實測**(183 輪「部位落地」p50 1939 / p90 4057 / p99 6433 ms)+ 200 ms debounce | |

### 2.2 平時(無成交)的部位更新

| 區段 | 成本 | 依據 |
|---|---|---|
| 60 s 定時鏈(`stale = now − _balance_last_ts >= 60`) | 每 60 s 一輪,一輪 ≈ 0.9 s COM 往返 + 0.036 ms 算術 | 實測(log DEBUG 輪 + bench) |
| 前端 `useCapitalStream` 15 s positions 輪詢 | 每 15 s 一次 HTTP,伺服端 16 µs | 讀 code + bench |
| **每日量級** | 交易日 4.5 h × 60 次/h = **~270 輪回查鏈**、~1,080 次 positions HTTP | 推估 |

> **量級誠實話**:`_today_net_lots_locked` 是 O(委託數) × O(部位列數),
> prod 實測 N = 16–63 張委託、部位列 ≤ 7 →
> 單列 **0.72 µs @16 / 2.28 µs @63**,整輪 `set_positions` **0.036 ms**。
> 一天 270 次 × 0.036 ms = **9.7 ms/日**。這不是效能問題。

---

## 3. 失效模式表

**S = 零錯誤訊號**(畫面照常、log 無異常、測試不紅)

| # | 失效模式 | 觸發 | 症狀 | S | 位置 | 嚴重度 |
|---|---|---|---|---|---|---|
| F-01 | **期貨部位損益結構性恆 null** | 只要持有任何期貨 / 個股期部位 | `StkfutLadder` 部位條損益永遠 `—`;chip / header / 群組卡的「期 N口」永遠不帶損益 | **是**(`—` 與「資料還沒到」同形) | `client.py:613` 只寫 `_pending_sec`(sec);fut 列無任何 `pnl_base` writer | **critical** |
| F-02 | **OI 欄序猜的,零 prod 樣本,卻掛著真平倉鈕** | 首次持有期貨部位 | 契約碼 / 口數 / 方向任一欄猜錯 → 部位列是錯的 → `build_future_close_order` 依 `pos.qty>0` 定反向、依 `abs(pos.qty)` 定口數 → **送出方向或口數錯誤的真實期貨單** | 部分(錯口數靜默;錯方向會被交易所退) | `balance.py:106-112` 自承「欄序 prod 未實測」;`tests/capital/test_balance.py:407-441` 全為手編 fixture | **critical** |
| F-03 | **`avg_source` 的 broker 半邊無機驗** | 損益段標籤亂碼 / 種類不符 / 該輪逾時 | 該列 `avg_source` 停在 null → 前端走「當純價再加一次買費」→ 打平線偏高 25.7 毫元(0.5 檔 @100 元)、損益少 51 元/2 張 | **是**(數字看起來完全正常) | `client.py:612`;parity 測試 `test_avg_source_parity_with_frontend` 只比**值域**不比**產生** | high |
| F-04 | **損益段種類標籤亂碼 → 整列略過** | SKCOM 中文欄 Big5→CP1252 不可逆壓縮(2026-08-20 prod 實錄 **303 次**) | `kind=None` → `avg_price` / `avg_source` / `pnl_base` 全不回填 → 打平 `—`、損益 `—` | 否(有 WARNING) | `balance.py:227-234`;備援 `_PNL_KIND_CODE` **只有 1→cash / 2→margin**,**融券(疑 3)刻意不對映** | high |
| F-05 | **`today_qty` 缺席 / 為 0** | 後端未重啟(舊 payload)、`flag_label` 不在 `_FILL_KIND`、跨 `_orders` 未清的隔夜聚合 | 當沖稅減半靜默消失 → 打平線偏高 **150.8 毫元 = 3 檔 @100 元**、損益少 300 元/2 張 | **是** | `store.py:300-330`;前端 `ladder-position.ts:98` 的 `Number.isFinite` 缺欄退 0 | high |
| F-06 | **13:30 後 `today_qty` 仍非零** | 每個交易日收盤到午夜 | 打平線仍套 0.15% 當沖稅,但那批張數已不可能當沖 → 顯示比實際**樂觀 3 檔** | **是** | `store.py::_today` = `time.strftime("%Y%m%d")` 日曆日,無收盤界 | medium |
| F-07 | **`_stale_fut_positions()` 無限沿用** | OI 查詢連續失敗(prod log 13 次;2026-08-18 09:46–09:56 連續 7 輪) | 已平掉的期貨部位持續顯示,平倉鈕可按 → 送出一張「平不存在部位」的單 | 否(每輪 WARNING) | `client.py:638-643`,無次數 / 時間上限 | medium |
| F-08 | **平倉以最多 60 s 舊的 `pos.qty` 當上限** | 群益 APP 端平掉部位而 D 回報未到 / `_positions_seeded` 為假 | `daytrade_sell` 的回補單是**現股買**;超量的部分不是被退單,而是**開了一筆新的現股多單** | **是**(單子成功、審計顯示 ok) | `close.py:218-241` 的 `holding = abs(pos.qty)` | high |
| F-09 | **平倉審計不記「平的是哪一列」** | 每筆平倉 | `data/audit/capital-*.jsonl` 只有 `trade_kind`(= 回補單種),`daytrade_sell` 平倉記成 `trade_kind:"cash"` → 事後對帳分不出「平無券空單」與「賣現股多單」 | **是** | `client.close_position` → `submit_stock_order(order, action="close")`,`PositionCloseRequest.kind` 不進審計 | medium |
| F-10 | **手續費折數是使用者手打的 localStorage,與券商真值零對帳** | 使用者改折數 / 券商調折數 | 賣出側費率與打平線分母偏差;**買進側是對的**(來自 broker 均價)→ 同一條線兩個口徑 | **是** | `fee-discount.ts` + `constants.ts::FEE_DISCOUNT_KEY` | low(量級見 §4.3) |
| F-11 | **`pnl_cost` / `pnl_base_price` 是死線** | 恆真 | 兩個欄位跨 wire、進 `types.ts`,前端**零讀者**;`models.py:180` 仍寫「前端『券商基底+即時平移』的平移基準」= 假述 | **是** | `types.ts:130-131`;grep 全前端無非測試讀者 | low |
| F-12 | **融資部位的報酬率分母是全額成本** | 持有融資部位 | `pct = pnl / (avg×|qty|×1000)`,不是自有資金報酬率 → 槓桿部位的 % 被稀釋約 2.5 倍;融資利息也不計 | **是**(標成「成本基準報酬率」) | `position-summary.ts:77-81` | low |
| F-13 | **回測與實盤的手續費折數用相反慣例、不同數值** | 拿回測期望值決定實單 | 回測 `fee_rate × (1 − fee_discount)`,configs 全帶 `0.84` → 等效 **1.6 折**;前端 `FEE_BASE × discount / 10`,預設 **1.8 折**。兩者無共用常數、無 parity 測試 | **是** | `backtest/simulate.py:82` / `fade_simulate.py:82` vs `ladder-position.ts:31` | medium |
| F-14 | **最低手續費 NT$20 不套** | 名目 < 77,973 元的部位 | 打平線偏低 | **是**(明寫「已知簡化」) | `ladder-position.ts:77` | **low —— 實測只有 2/58 筆(3%)命中,偏差 0.02%,不要修** |
| F-15 | **`_fill_code` 以 `unit == "口"` 當期貨判準代理** | 改 `_lot_unit` 的「口」字面值 | 個股期股號反查靜默失效 → 圖牆個股期三角全滅 | **是** | `capital_api.py:240-250`(自承);`tests/capital/test_store.py` 有 lock | low |

---

## 4. 逐題回答

### 4.1 `avg_source` 的兩個產生點與漂移

| | `"broker"` | `"fill"` |
|---|---|---|
| 產生點 | `client.py:612`(`_on_profit_complete`,**唯一**) | `store.py:446`(新倉)/ `store.py:468`(反手翻倉) |
| 語意 | 群益損益試算「平均買進成本」= 純成交價 **+ 買進手續費(含折數)** | 這張單的純成交均價 |
| 前端處置 | `cost = avg`(不再加買費) | `cost = avg × (1+f)` |
| 加碼時 | `store.py:454` **沿用舊來源** —— broker 含費均價與純價加權,誤差只在新增那幾張的買費,~2 s 後鏈落地即消 | 同 |
| 減碼時 | 均價不動、來源沿用 | 同 |
| `avg` 為 None 時 | `source = None`(`store.py:469-470`) | 同 |

**獨立實證(本輪新做)**:用 prod log 的 `損益列回填 … avg=… cost=…` 反推隱含費率
(`cost` = idx12 成交價金 = 純價 × 股數;`avg` = 券商均價,2 位小數):

| 股號 | kind | cost | 股數 | 純價 | 券商 avg | 1.8 折理論 avg | 四捨五入後 |
|---|---|---|---|---|---|---|---|
| 6949 | cash | 125,500 | 2,000 | 62.750 | 62.77 | 62.7661 | 62.77 ✓ |
| 6949 | margin | 117,000 | 2,000 | 58.500 | 58.52 | 58.5150 | 58.52 ✓ |
| 6667 | margin | 250,500 | 1,000 | 250.500 | 250.56 | 250.5642 | 250.56 ✓ |
| 6715 | margin | 364,500 | 1,000 | 364.500 | 364.59 | 364.5935 | 364.59 ✓ |
| 2243 | cash | 95,250 | 2,000 | 47.625 | 47.64 | 47.6372 | 47.64 ✓ |
| 2426 | cash | 99,800 | 1,000 | 99.800 | 99.83 | 99.8256 | 99.83 ✓ |
| 2426 | cash | 199,100 | 2,000 | 99.550 | 99.58 | 99.5755 | 99.58 ✓ |
| 4908 | cash | 242,000 | 1,000 | 242.000 | 242.06 | 242.0621 | 242.06 ✓ |

**8/8 全中**。這是三件事的第一手證據:(a)「券商均價含買進手續費」是真的;
(b) 使用者的真實折數確實是 **1.8**,`FEE_DISCOUNT_DEFAULT` 對;
(c) **這個對帳可以自動化**(見 §6 修法 4),而且它同時驗 `avg_source` 有沒有真的落地。

**哪裡會漂**:
- broker 半邊靠**一行賦值**,沒有任何測試釘「走過 `_on_profit_complete` 的列 `avg_source` 必為 broker」
  —— 2026-08-26 那版正是把它寫在一條零 caller 的 store 方法上,測試綠、prod 全 null(CLAUDE.md §4 已記)。
  現在的 parity 測試(`test_avg_source_parity_with_frontend`)只比 `AVG_SOURCES` 字面 ⊇ `get_args(AvgSource)`,
  **不驗產生**。同一個洞還開著,只是搬了位置。
- 損益段沒回來(逾時 8 次 / 種類不符 303 次 / 標籤亂碼 28 次)→ 停在 null。
- **fut 列恆 null 是設計**(OI 不經損益回填),CLAUDE.md 已明記「不要替 OI 列硬填來源」。
- **漂了看不看得出來**:`curl /api/capital/positions` 看 `market=="sec"` 列的 `avg_source` 非 null,
  是 CLAUDE.md 既有的紅燈判準 —— 但那是**人工**的,沒有任何自動探針。
  畫面上完全正常:打平線只差 25.7 毫元(0.5 檔 @100 元)、損益只差 51 元 / 2 張。

### 4.2 當沖段 `today_qty` 與賣出稅減半

**計算**(`store.py:300-330`):
```python
# _today_net_lots_locked(stock_no, kind):掃全部 _orders
#   市場 ∈ {TS,TA,TP}、filled_qty>0、fill_date == 今天(本機日曆日)、
#   _FILL_KIND[flag_label] == kind、且 (kind==daytrade_sell 時排除買向)
#   net += (filled_qty//1000) if buy_sell=="B" else -(...)
# _with_today_qty_locked:多方取 net、空方取 −net,clamp 到 [0, |qty|];fut 恆 0
```
**分段加權**在前端(`ladder-position.ts:101-102`):
`t = (T·0.0015 + (|qty|−T)·0.003) / |qty|`,`T` 再 clamp 一次(刻意雙側防禦)。
只有 `kindTraits(kind).halfTaxToday` 為真(cash / daytrade_sell)才取 T;
margin / short / 未知字串一律 T=0 全稅(`UNKNOWN_KIND_TRAITS`)。

**量級**(本輪實算,2 張 @100.00 broker 均價、1.8 折):

| 情境 | pnl(現價 100.00) | 打平線(毫元) |
|---|---|---|
| 基準(broker + today=2) | −351 | 100,175.96 |
| **少送 `today_qty`** | −651 | 100,326.71(**+150.8 = 3 檔**) |
| **少送 `avg_source`** | −403 | 100,201.65(+25.7 = 0.5 檔) |
| 兩者都少 | −703 | 100,352.45 |

→ **`today_qty` 的漂移量是 `avg_source` 的 6 倍**,而 CLAUDE.md 的紅燈判準只釘 `avg_source`。

**兩個已知殘餘**:
1. `_FILL_KIND` 對不上就靜默算 0(`"零股"` / 未知資券別)。零股本來就不該算(市場 TL/TC 已先排除),
   但**未知資券別**(`_SEC_FLAG` 表外的代碼)會讓整檔的當沖段消失,零訊號。
2. **13:30–24:00 仍算當沖**(F-06)。`_today()` 是日曆日,沒有收盤界。

### 4.3 無券空單(`daytrade_sell`)完整鏈 —— 所有讀者

**產生**
1. `balance.py:79-92` — 現股 T 列**負股數** → `pos_kind = "daytrade_sell"`(prod 8358 實錄校準);
   融資列負股數則保留 `margin` + WARNING、平倉鍵鎖住(`_CLOSE_MAP` 無 `(margin, False)`)。
2. `store.py:52-60` `_FILL_KIND["無券"] = "daytrade_sell"`(回報 idx6 = `08`,`reply.py:33`)。
   `_apply_fill_locked` 對**無券買向**(`08` + `B`)一律 WARNING 不套(無部位語意)。

**後端讀者**
- `store.py:388-410` 現股買(`cash` + `signed>0`)**先沖** `(股號, daytrade_sell)` 空單列,餘量才開現股多單。
- `store.py:411-435` 對稱向:無券賣(`daytrade_sell` + `signed<0`)**先減** `(股號, cash)` 多單,餘量才開空單列。
- `store.py:315-318` `_today_net_lots_locked` 對 `daytrade_sell` 桶**排除買向**(與上一條同一把尺)。
- `close.py:214` `_CLOSE_MAP[("daytrade_sell", False)] = ("buy", "cash")` — **唯一「部位種類 ≠ 送出交易別」的組合**。
- `safety.py:65-66` `trade_kind=="daytrade_sell" && buy_sell=="buy"` → 直接擋(`daytrade_sell 不可買進`)。
- `capital_api.py:114` `PositionCloseBody.kind: TradeKind | None` — wire 值域含 `daytrade_sell`。
- `client.py:597-604` 損益段**唯一的跨 kind 例外**:報告 `kind=="cash"` 而 pending 只有 `daytrade_sell` 負向列 → 配對成功。
- `client.py:~545` 每 (股號, 交易日) 一次 INFO「庫存段 … 現股負股數 → 無券空單」。

**前端讀者**
- `trade-kinds.ts:293` `TRADE_KINDS` → 標籤「無券」。
- `trade-kinds.ts:327` `KIND_TRAITS.daytrade_sell = { buyLocked: true, halfTaxToday: true, borrowFee: false, order: 3 }`
  —— 買側鎖(閃電梯 disabled)+ 當沖稅減半 + 無借券費 + 部位列殿後。
- `ladder-position.ts:100-103` `positionEcon` 經 `kindTraits` 取 `halfTaxToday` / `borrowFee`(不逐點比字串)。
- `close-order.ts:373` `KIND_TEXT.daytrade_sell = {short:"無", full:"無券"}`(部位面板 / 確認窗)。
- `close-order.ts:393` `CLOSE_KIND.daytrade_sell = "cash"` → `closeKindLabel` 印「買回 n 張(現股)」。
- `close-order.ts:382` `kindOf` —— 「標得出來就送得出去」的守門(`Object.hasOwn`,不用 `in`)。
- `position-summary.ts:16` `kindLabel`;`ladder-position.ts:165` `secPositionsOf` 排序。

**機驗**(跨語言)
- `tests/capital/test_models.py::test_position_kind_subset_of_trade_kind`(前端 `PositionKind` ⊆ 後端 `TradeKind`)
- `tests/capital/test_close.py::test_close_kind_label_parity_with_frontend`(回補單種 parity)
- `trade-kinds.ts:335` `_KindDomainsMatch` 型別層雙向相等斷言(tsc 紅)
- `tests/capital/test_store.py -k borrowless`、`test_capital_api.py::test_close_body_kind_daytrade_sell_sends_cash_buy`
- `frontend/src/lib/ladder-position.test.ts`「無券空單」/ `close-order.test.ts`

**prod 實錄**:本輪 grep 79 個 log 檔,`無券空單` / `現股負股數` / `無券買向成交無部位語意` 命中數皆為 **0**
→ 這整條鏈**在 2026-08-28 那一筆校準之後,從未在現存 log 裡再跑過**。全鏈靠測試護著,沒有第二次真實樣本。

### 4.4 手續費折數:後端與前端是否一致?

**下單這條路徑沒有這個問題,因為後端根本不算費。**
`copycat/capital/` 與 `copycat/server/capital_api.py` 零費率常數(已 grep);
安全閘只比名目 `price × qty × multiplier`。折數的唯一存在處是前端 localStorage + `feeRate()`。
所以**不存在回測那種「兩邊算同一個數卻用相反慣例」的即時漂移**。

**但跨模組的慣例分岔是真的,而且數值也不同**(F-13):

| | 慣例 | 預設 / 實配 | 等效費率 |
|---|---|---|---|
| 前端實盤 `ladder-position.ts:31` | `FEE_BASE × discount / 10`(**折數**) | 1.8 折 | 0.0002565 |
| 回測 `backtest/simulate.py:82` | `fee_rate × (1 − fee_discount)`(**折讓比例**) | `config.py:38` 預設 0.0;`configs/fade_uc_round*.json` 全帶 **0.84** | 預設 0.001425(= 10 折);實配 0.000228(= **1.6 折**) |

兩邊**無共用常數、無 parity 測試、語意互為倒數**。後果不是即時算錯,而是
**策略期望值與實盤成本不同尺**:回測預設值把成本高估 5.6 倍(保守方向,會誤殺真正有 edge 的策略),
實配的 1.6 折又比實盤的 1.8 折低 11%(樂觀方向)。§6 給了最小修法。

### 4.5 期貨部位:OI 快照、`_stale_fut_positions()`、個股期反查

**OI 快照來源**:`GetOpenInterestGW(nFormat=1)` → `OnOpenInterest` 事件 → `parse_open_interest_line`。
欄序 **假定**為 `[0]市場 [1]帳號 [2]商品 [3]買賣別 [4]口數 [5]當沖口數 [6]平均成本`,
`balance.py:106-112` 自承「欄序 prod 未實測」。防禦做得不錯(`S` → 負口數、成本壞掉不丟整筆、
`#` / 含「無資料」→ None),但**防禦擋不了欄位錯位**:如果真實報告在商品碼前多一欄,
`parts[2]` 拿到的是帳號、`parts[3]` 不是 B/S → 整列回 None → **期貨部位整段靜默消失**(這是安全方向);
如果剛好錯位成合法形狀,就是**錯誤的契約 / 口數 / 方向**(這是危險方向)。
prod log 全域 `期貨部位段收齊 0 列`(182 輪,max=0)→ 這條路**從未跑過真資料**,
而 `build_future_close_order` 直接吃 `pos.qty` 的符號決定買賣、吃 `abs(pos.qty)` 決定口數,
再 `new_close=1` 送出。**這是本區塊唯一「錯了會直接送錯單」的路徑。**

`merge_fut_positions`(`balance.py:88-104`):同契約多列 B/S → 淨額合併 + WARNING;
淨額 0 不佔一列;`avg_price` 保留首列(混合成本無單一正解)。合理。

**`_stale_fut_positions()`**(`client.py:638-643`):
```python
stale = [p for p in self.store.positions() if p.market == "fut"]
logger.warning("期貨部位查詢未完成 — 沿用上一輪 fut 部位(%d 列)", len(stale))
```
三個呼叫點:`_query_open_interest` 的 `rc != 0`、`_query_open_interest` 無期貨帳號時(改走 `[]`)、
`_poll_pending` 的 pending 逾時。**沒有次數上限、沒有時間上限、沒有「已沿用 N 輪」的標記**。
prod log 13 次,其中 2026-08-18 09:46–09:56 **連續 7 輪**(每 60 s 一次)。
沿用回去的是**已發布的物件參考**(`positions()` 的 docstring 明寫這條是唯一例外,
靠 `p is prev` + 五行自我賦值才沒撕裂)—— 這個不變量脆弱且只有註解護著。

**個股期契約碼反查**:
- `capital_api.py:288` positions 路徑用 `stock_code_of(p.market, p.stock_no)`(以 `p.market` 為尺,正確)。
- `capital_api.py:240-250` orders / fills 路徑用 `_fill_code(unit, stock_no)`,
  **以 `unit == "口"` 當期貨判準的代理** —— `OrderRecord` / `FillRecord` 沒帶 market。
  自承:改 `_lot_unit` 的「口」字面值 = 反查靜默死。
- 實測成本:`stock_code_of("fut", "CDFI6")` = **4.71 µs**(其中 `lookup_product` 3.89 µs,
  每次做一個 `Path.stat` 檢查 mtime 快取)。`stock_code_of("sec", …)` = **0.053 µs**。
  這是 async route 上的同步 syscall,但 prod fut 列數 = 0 → 目前零成本;
  即使 20 列也只有 94 µs。**不是問題,不要動。**

### 4.6 打平線 / 損益的算式在哪幾份?

**一份半。**
- **證券**:`frontend/src/lib/ladder-position.ts::positionEcon`(L80-134)—— 唯一一份。
  兩個呼叫點(`PriceLadder.tsx:147`、`position-summary.ts:147`)傳的參數逐字相同,
  排序 / 過濾也共用 `secPositionsOf`。這是這個區塊做得最好的部分。
- **期貨**:沒有算式,直接印 `pnl_base`(`StkfutLadder.tsx:372`、`position-summary.ts:180-182`)。
  設計上刻意(期交稅 + 每口手續費是另一套規則),但**`pnl_base` 在 fut 列上恆為 null**(F-01)
  → 實際上這半份算式印的永遠是 `—`。
- **成本基準報酬率** `pctOf`(`position-summary.ts:77-81`)另算一份分母
  (`avg × |qty| × 1000`),**不用** wire 上的 `pnl_cost`(= idx12 成交價金)。
  兩者差一筆買進手續費(實測 6949:125,540 vs 125,500)。差異 0.03%,不影響判斷,
  但代表 `pnl_cost` 是死線(F-11)。

### 4.7 哪些欄位缺席會讓前端靜默算錯

| 缺席欄位 | 前端行為 | 打平線偏差(2 張 @100,1.8 折) | 訊號 |
|---|---|---|---|
| `avg_source`(undefined / 值域外字串) | `isAvgSource` 白名單 → null → 走「fill」口徑加一次買費 | +25.7 毫元(0.5 檔) | 零 |
| `today_qty`(undefined / NaN) | `Number.isFinite` → 退 0 → 全稅 0.3% | +150.8 毫元(**3 檔**) | 零 |
| `avg_price`(null / ≤0) | `px()` → null → `{pnl:null, breakEvenMilli:null}` | 整列 `—` | 半(畫面有破折號) |
| `kind`(值域外字串) | `kindTraits` → `UNKNOWN_KIND_TRAITS`(全稅、無借券費、不鎖買側、殿後) | 現股列 +150.8;融券列**少收 0.08% 借券費** | 零 |
| `pnl_base`(fut) | `futSummary` 回 `pnl: null` | 期貨損益整段 `—` | 零 |
| `code`(fut 反查失敗) | `positionsByCode` 跳過該列;`unmappedFutCount` 另計一行提示 | 該部位在 chip / header / 卡片上完全不出現 | **有**(側欄印「n 筆個股期倉位無法對映」)—— 這是本區塊唯一做對的缺欄提示 |

前端的防禦姿態一致且正確:**缺欄一律退回「修前口徑」,不退成假數字**
(`?? null` 擋不住值域外字串 → 改用白名單 + `Number.isFinite`,`ladder-position.ts:96-111` 有完整說明)。
問題不在防禦,而在**退回去之後沒有任何人知道退了**。

---

## 5. 反向清單:量過、夠快 / 已寫對,不要動

| 對象 | 實測 | 為什麼不要動 |
|---|---|---|
| `_today_net_lots_locked` 的 O(M×N) | 0.72 µs @16 orders / 2.28 µs @63;整輪 `set_positions` **0.036 ms p50** | 成長軸是 `_orders` 長度,而 prod 實測 16–63。要到 5,000 張委託才 140 µs/列。一天總成本 9.7 ms。改成增量維護只會引入「當沖段對不上」這種零訊號 bug |
| `dataclasses.asdict` 在 positions route | 2.27 µs/列 × ≤7 列 = **16 µs** | B10 提過的 msgspec / 手寫 `to_dict()` 在這支完全不划算,而且會碰 `unit` / `avg_source` / `today_qty` 三條跨檔契約 |
| `stock_code_of` / `lookup_product` 的 `Path.stat` | 4.71 µs/列,prod fut 列數 = 0 | mtime 快取是為了「另一個 process 跑 refresh-stkfut-map」而設計的,拿掉會讓新上市個股期送單被拒而對映檔明明已更新 |
| `positionEcon` 每 tick 重算 | <1 µs/列,部位列個位數 | `PriceLadder.tsx:246` 已註明「kinds 量級是個位數的純算術,不值得 memo」。正確 |
| 最低手續費 NT$20 不套 | 臨界名目 77,973 元;實測 58 筆 distinct 成交價金只有 **2 筆(3%)** 在臨界下,偏差 0.02% | 要套就得知道筆數(聚合部位還原不出來)。成本遠大於收益 |
| 打平線 snap 方向(多 `snapUp` / 空 `snapDown`) | — | 刻意往「還沒打平」那側取,不讓標記騙人。正確的保守方向 |
| 前端缺欄退「修前口徑」的白名單姿態 | — | `isAvgSource` + `Number.isFinite` + `kindTraits` 三處同姿態,是被 #118 prod 事故逼出來的。不要簡化回 `?? null` |
| `_apply_fill_locked` 的雙向沖銷(現股買先沖無券空單 / 無券賣先沖現股多單) | 樂觀套用實測 0.20 ms p50 | 這兩段是 pr-152 F-02 用真實「幽靈雙列 + 平倉鈕可按」的事故換來的。少任一向就回到 ~2 s 的可按錯鈕窗 |
| `positions()` 回傳參考 + `dataclasses.replace` 發布新物件 | — | 撕裂讀(新 pnl 配舊基準價)的唯一防線 |

---

## 6. 改造順序 + 量測判準

> 全部以「不改前端算式、不改跨檔契約字面值」為前提。每一步都給可 grep / 可 curl 的判準。

### 1. 期貨部位損益的真相對齊(F-01)—— 先決定要不要顯示,不要先寫 code
**做什麼**:先確認 `OnProfitLossGWReport` 到底回不回期貨列(群益手冊 + 一次 prod probe)。
- 回:把 `_on_profit_complete` 的母體從 `_pending_sec` 擴成 `_pending_sec + fut_rows`(需把 OI 段移到損益段之前,或改成兩段各自回填);
- 不回:把 `StkfutLadder` / `futSummary` 的期貨損益改成**明確的空態文案**(「群益未提供期貨損益」),
  並把 `models.py:179` 那句「前端平移基底」的假述改掉。

**量測判準**:持一口期貨部位,`curl -s localhost:8721/api/capital/positions | python -c "..."`
→ `market=="fut"` 列的 `pnl_base` 非 null(方案 A),或畫面出現空態文案而非 `—`(方案 B)。
加一條 `tests/capital/test_client.py::test_fut_row_pnl_base_is_populated_or_explicitly_absent`。
**effort S(方案 B)/ M(方案 A)**。**rollback**:純顯示層,revert 該 commit。

### 2. OI 欄序 prod 校正 + 未校正前鎖住期貨平倉(F-02)
**做什麼**:在 `parse_open_interest_line` 加一個 `oi_layout_verified` 旗標(讀 env 或常數,預設 False);
False 時 `capital_api.py::capital_position_close` 的 `market=="fut"` 分支直接 403 `OI_LAYOUT_UNVERIFIED`,
並在啟動 banner 印一行。同時把 `OnOpenInterest` 的**整列原文**以 INFO 記一次(每 (帳號, 日) 一次),
讓第一次真有部位時就有樣本可校。
**為什麼排第二**:這是唯一「錯了會直接送出錯誤真實期貨單」的路徑,而且成本極低。
**量測判準**:(a) `grep "OnOpenInterest 整列" logs/server-*.log` 在首次持倉當日有列;
(b) 校正前 `POST /api/capital/position/close {"market":"fut"}` 回 403;
(c) 校正後翻旗標,該 403 消失、`tests/capital/test_balance.py` 換成真樣本 fixture。
**effort S**。**rollback**:旗標翻回 True 即回到現況(但不建議)。

### 3. `avg_source` / `today_qty` 的落地探針(F-03 / F-05)
**做什麼**:在 `_finalize_positions` 落地後加一行(每 (股號, kind, 日) 節流一次):
```
WARNING 部位缺語意欄:2330/cash avg_source=None today_qty=0 avg=None(打平線走修前口徑)
```
判準 = `market=="sec"` 且 `avg_price is not None` 且 `avg_source is None`。
**不改任何算式**,只把「零訊號」變成「一行訊號」。
**量測判準**:盤後 `grep "部位缺語意欄" logs/server-*.log` 應為 0;
若非 0,每一行都對得上一筆 `profit row 種類不符略過` 或 `部位合併逾時`。
再加後端測試:走過 `_on_profit_complete` 的列 `avg_source == "broker"`(補上目前缺的那一條)。
**effort S**。**rollback**:刪 log 行。

### 4. 隱含費率對帳(F-10 / F-03 的交叉驗證)
**做什麼**:`_on_profit_complete` 已同時握有 `r.avg_price`(含費)與 `r.cost`(純價金);
再取 `store` 同股號的 `filled_qty` 即可反推隱含折數
`d = 10 × ((avg×股數/cost) − 1) / 0.001425`。每 (股號, 日) 印一次 INFO,
偏離前端 `FEE_DISCOUNT_DEFAULT` 超過 20% 時升 WARNING。
**注意 2 位小數量化**:低價股(<30 元)的量化誤差 ≈ 整個費率,這些列要跳過(或只在 avg ≥ 50 時判)。
本輪已用 8 筆 prod 樣本驗證這個反推法 8/8 全中(§4.1)。
**量測判準**:交易日盤後 `grep "隱含折數" logs/server-*.log`,值落在 1.7–1.9;
人為把 `FEE_DISCOUNT_DEFAULT` 改成 5 折跑一次 → WARNING 出現。
**effort S**。**rollback**:刪 log 行。

### 5. `today_qty` 加收盤界(F-06)
**做什麼**:`_today_net_lots_locked` 的「今天」判定不變(`fill_date == today` 是對的),
但在 `_with_today_qty_locked` 加一道:牆鐘 ≥ 13:30(或非交易日)→ `today = 0`。
**注意**:這會讓收盤後的打平線往上跳 3 檔 —— 那是**正確**的(那批張數已不可能當沖)。
要先跟 user 拍板(是行為改動,🔴)。
**量測判準**:13:29 與 13:31 各 `curl /api/capital/positions`,同一列的 `today_qty` 由 n → 0;
`tests/capital/test_store.py` 加兩個注入時鐘的案子。
**effort S**。**rollback**:單一條件式,revert。

### 6. `_stale_fut_positions` 加沿用上限 + 標記(F-07)
**做什麼**:記 `_fut_stale_rounds`;`_on_oi_complete` 歸零。
連續 ≥ 5 輪(約 5 分鐘)→ WARNING 升級並在 `capital_status` 的 `status_view()` 帶
`fut_positions_stale_rounds`,前端部位列加一個「期貨部位可能已過期」的視覺標記。
**不要**直接清空(A7 的原始理由仍在:閃斷不可把面板期貨部位清光)。
**量測判準**:注入連續 OI 失敗的 fake,第 5 輪 `status_view()["fut_positions_stale_rounds"] >= 5`;
prod 盤後 `grep "沿用上一輪 fut 部位" | wc -l` 與升級行數對得上。
**effort S**。**rollback**:純觀測欄,無行為改動。

### 7. 平倉的「部位快照新鮮度」閘(F-08)
**做什麼**:`Position` 加一個**不進 wire** 的 `snapshot_ts`(store 內部);
`close_position` 在 `pos` 的來源是 `_stale_fut_positions` 或快照年齡 > N 秒時,
對 `daytrade_sell` / `short` 這兩種**反向部位**要求 `req.qty <= pos.qty` 之外再加一次即時重查
(或直接降級成 403 `POSITION_STALE`,要 user 重按)。
**為什麼只鎖反向**:超賣現股會被券商退單,但超買回無券空單會**靜默變成新的現股多單**。
**量測判準**:構造「store 顯示 −3 張、實際已回補」的場景 → 平倉回 403 而非送單;
`data/audit/capital-*.jsonl` 出現對應的 `blocked` 列。
**effort M**。**rollback**:閘可用 env 關掉。**風險**:誤擋合法平倉 → 必須留逃生門。

### 8. 平倉審計記錄部位種類(F-09)
**做什麼**:`submit_stock_order(order, action="close")` 多帶 `close_kind=pos.kind`,寫進審計列。
**量測判準**:平一筆無券空單後,`grep '"action": "close"' data/audit/capital-*.jsonl | tail -1`
含 `"close_kind": "daytrade_sell"`。
**effort S**。**rollback**:審計是 append-only,新增欄位向後相容。**風險**:碰審計 schema,讀者要能吃缺欄。

### 9. 回測 / 實盤費率慣例統一(F-13)
**做什麼**:**不合併兩份實作**(回測是 float 純函式、實盤是 TS,強行共用是假共用)。
改成:回測 config 增加 `fee_discount_tenths`(折數,與前端同慣例)並在
`simulate.py::_cost` 以 `fee_rate * fee_discount_tenths / 10` 計;舊 `fee_discount` 標 deprecated 但保留讀取。
加一條測試釘「兩種慣例在同一折數下算出同一個數」。
**量測判準**:`configs/fade_uc_round5.json` 的 0.84 換算成 `fee_discount_tenths: 1.6`,
重跑 `tday-search` 的成本行輸出逐字不變;把它改成 1.8,報告成本行差 0.0000285。
**effort M**。**rollback**:新欄位可選,不帶就走舊路徑。

### 10. 清掉死線(F-11)
**做什麼**:`pnl_cost` / `pnl_base_price` —— 要嘛讓 `position-summary.ts::pctOf` 真的吃 `pnl_cost`
(口徑與群益 APP 對齊),要嘛把 `models.py:180` 的假述改成「目前無讀者,保留供對帳」。
**量測判準**:改文件版 = `grep -n "平移基準" copycat/capital/models.py` 無命中;
改行為版 = 同一筆部位的 `pct` 與群益 APP 的報酬率逐字相同。
**effort S**。**rollback**:文件層。

---

## 7. 待確認 / 推翻上一輪

- **沒有推翻上一輪任何結論。** B10 的 `_orders` 永不裁剪、風控只有單筆閘、審計無 fsync 等,
  在本區塊得到獨立佐證:`_today_net_lots_locked` 的成長軸確實是 `_orders` 長度(= process uptime),
  但實測量級(63 張 → 2.28 µs)證明**它在成為效能問題之前,會先成為 `today_qty` 正確性問題**
  —— 隔夜庫存若被算成今天進來的,前端稅減半 = 少收稅、打平線偏低,零訊號(`store.py:300-305` 的註解
  已經預見這一點,並用 `fill_date == today` 擋住了)。
- **`app.user_middleware == []`、零 request timing** 在本區塊的具體代價:
  `GET /api/capital/positions` 的 p99 完全不可知;但本輪從 log 的「balance 鏈」行
  拿到了整條回查鏈的完整分位數,**這是全 codebase 唯一有端到端分位數的路徑**,
  應該當成其他區塊補儀器時的樣板。

## 8. 開放問題

1. `OnProfitLossGWReport`(全部商品)到底回不回期貨列?決定 F-01 走 A 還是 B 方案。
2. `OnOpenInterest` 的真實欄序 —— 需要一次持倉 probe。在此之前期貨平倉是否該鎖?(建議鎖)
3. 融券的損益報告 `[25]` 種類代碼是不是 `3`?目前刻意不對映 → 持融券時若標籤又亂碼,整列略過。
4. 群益「無券空單」的損益列均價是純賣價還是扣費稅淨收?`client.py:606-608` 的蒐證 log 已埋,
   但 2026-08-28 之後 prod log 零命中 —— 需要第二筆實錄。
5. 13:30 之後 `today_qty` 歸零是否要做?(是行為改動,打平線會往上跳 3 檔,要 user 拍板)
6. 期貨的成本模型(期交稅 + 每口手續費)要不要補?補了才有真正的期貨打平線;
   不補就要把「期貨無打平線」寫成畫面上看得懂的話,而不是一個 `—`。
