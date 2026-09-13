# D3 — 下單:委託/成交狀態機與回報

> 掃描區塊:`copycat/capital/reply.py`(131 行)、`copycat/capital/store.py`(758 行)、
> `copycat/capital/models.py`(186 行),以及回報進入點 `copycat/capital/client.py::_handle_reply`
> 與回查鏈 `_maybe_query_balance` → `_on_balance_complete` → `_on_profit_complete` →
> `_query_open_interest` → `_finalize_positions`。
>
> 掃描日 2026-09-13。所有「實測」欄位的資料來源:
> (a) `logs/server-*.log` 64 份、3,201 則 `Capital reply` 事件、183 次回查鏈落地;
> (b) `data/audit/capital-*.jsonl` 1,075 列(order 841 / cancel 232 / close 2);
> (c) 本機 micro-benchmark(`.venv` Python 3.13.13,腳本留在本目錄)。
> 「推估」欄位一律明說。

---

## 0. 一句話結論

狀態機本身**又小又快又寫得對**(prod 實際 N = 24–63 張單,`apply_reply` p50 = 0.017–0.021 ms,
樂觀套用 189/192 筆真成交成功 = 98.4%),**效能不是這一段的問題**;
問題全部在**時間軸的邊界**:開機 backlog 重播跨越第一次快照落地 → **幽靈部位 + 平倉鈕可按**
(prod 10/64 次重啟、34 筆、窗 4.56–7.25 s,已用腳本確定性重現);
跨午夜重啟 → **昨日成交被蓋成今日日期**畫進今天的圖(prod 2026-09-11 00:36 實錄 21 筆,
而 `models.py:125` 白紙黑字寫這條「目前不可達」);
以及**整個 U / P / B / S 分支在 prod 從未跑過一次**(30 天零樣本)。

---

## 1. 現況地圖:一筆委託的完整狀態轉移

### 1.1 三條執行緒、四個資料結構

```
 event loop (uvicorn)              capital-com thread (唯一)            瀏覽器
 ───────────────────               ────────────────────────             ────────
 REST 寫入                          _run 幫浦圈(50 ms)
  _execute_write                     ├ _com.pump()      ← COM 訊息幫浦
   ├ gate                            ├ balance/profit/oi .poll()
   ├ to_thread(_audit)  ──┐          ├ _maybe_query_balance()
   ├ _cmd_q.put ─────────────────→   ├ _poll_pending()
   └ await shield(fut) ←──────────   └ _cmd_q.get(0.05) → fn() → call_soon_threadsafe

                                    OnNewData(COM 回呼)
                                     └ _handle_reply
                                        ├ parse_onnewdata   (3.2 µs)
                                        ├ logger.info        (12.5 µs,經 _Tee 同步 flush)
                                        ├ store.apply_reply  (17–21 µs @ N=16–63)
                                        │   └ [store._lock] _Agg 聚合 + _apply_fill_locked
                                        ├ _mark_balance_dirty(0.5)     (D 才做)
                                        └ _emit → call_soon_threadsafe(capital_ws.publish)
                                                                          └──→ WS {event,data}
                                                                               └ 200 ms debounce
                                                                                  → GET /api/capital/*
```

四個資料結構(全在 `CapitalStore`,同一把 `threading.Lock`):

| 結構 | 鍵 | 內容 | 誰清 |
|---|---|---|---|
| `_orders: dict[str, _Agg]`(`store.py:144`) | 13 碼委託序號 | 一張單的聚合狀態 | **只有 `clear()`,零 prod caller** |
| `_order_seq: list[str]`(`:145`) | — | 到達順序(`orders()` 同秒排序用) | 同上 |
| `_fills: list[FillRecord]`(`:166`) | — | 逐筆 D 事件 | append 時 prune + `fills()` 讀時再濾 |
| `_positions: dict[(str,str), Position]`(`:153`) | (股號/契約碼, kind) | 部位 | `set_positions` 全量替換 |
| `_price_types`(`:151`) / `_contract_ym`(`:155`) | seq | 送單意圖 / 期貨月碼 | `note_price_type` 自 prune / 只有 `clear()` |

### 1.2 狀態轉移圖

`ReplyRecord.status_raw`(回報 idx2)是唯一輸入;`_RANK`(`store.py:63-78`)是**單調棘輪**,
`_set_status`(`:173`)只在 `新 rank >= 舊 rank` 時才寫。

```
                    ┌──────────────────────────────────────────────┐
                    │  _Agg 不存在 → apply_reply 第一則即建立       │
                    │  (seq 為空 → 整筆丟棄,store.py:190)         │
                    └───────────────────┬──────────────────────────┘
                                        │
        idx3 OrderErr ∈ {Y,T} 且 idx2 ∉ {C,U,P,B}   ┌────────────────┐
        ──────────────────────────────────────────→ │ 失敗 / 逾時 (3) │ 終態
                                        │           └────────────────┘
                                        │
       ┌────────────────────────────────┴───────────────────────────┐
       │                                                            │
   idx2 = N                                                     idx2 = D 先到
   order_qty ← rec.qty                                          (亂序:N 還沒來)
   price     ← rec.price                                        filled_qty += qty
       │                                                        fill_value += price*qty
       ▼                                                        fill_date   ← 本機今日
 ┌──────────────────┐   pre_order?                              _append_fill_locked
 │ 委託成功 (rank 1) │←── 是 ──→ ┌────────────────┐                 │
 │ actionable = True │           │ 預約中 (rank 1) │                 ▼
 └────────┬─────────┘           └────────────────┘          _refresh_fill_status:
          │                                                  order_qty 未知(=0)→ **不斷言全成**
          │                                                  (store.py:177-186;斷言了就鎖死)
          │                                                        │
          ├── idx2 = P / U / B(改價 / 改量 / 改價改量,rank 1)────┤  ★ prod 30 天零樣本
          │      P: price ← rec.price                              │
          │      U: order_qty ← after_qty ?? max(order_qty-qty,0)  │
          │      B: 兩者都改                                        │
          │      U/B 之後重跑 _refresh_fill_status(減到 ≤ 已成交 = 等同全成)
          │                                                        │
          ▼                                                        ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ idx2 = D(成交);price 為 None → **整筆不採計**(store.py:228,安全方向) │
   │ filled_qty += qty ; fill_value += price×qty                         │
   │ _append_fill_locked(逐筆一列,date = **本機今日**,不是 idx23)        │
   │ _positions_seeded ? _apply_fill_locked(a) : False   ← 樂觀套用開關    │
   └──────────────────────────┬──────────────────────────────────────────┘
                              │ _refresh_fill_status
              ┌───────────────┴────────────────┐
              │                                │
   filled < order_qty                filled >= order_qty > 0
              ▼                                ▼
   ┌────────────────────┐           ┌──────────────────────┐
   │ 部分成交 (rank 2)   │           │ 全部成交 (rank 3)     │ 終態
   │ actionable = True   │           │ actionable = False    │
   └─────────┬──────────┘           └──────────────────────┘
             │
             ├── idx2 = C(刪單)──→ ┌──────────────────┐
             │                      │ 已刪單 (rank 3)   │ 終態(qty=剩量,order/filled 不動)
             │                      └──────────────────┘
             └── idx2 = S(退單)──→ ┌──────────────────┐  ★ prod 30 天零樣本
                                    │ 退單 (rank 3)     │ 終態
                                    └──────────────────┘

   例外閘(store.py:80-82 `_ACTION_TYPES = {C,U,P,B}`):
   刪 / 改事件帶 OrderErr → 只寫 error_msg,**不標終態**
   (失敗的是「那一次動作」,原單還掛在市場上;標終態會讓活單從面板消失)
```

**`actionable`** = `_RANK.get(status_label) in (1, 2)`(`store.py:588`)—— 前端刪 / 改按鈕的唯一依據。

**wire 上的量** `_to_record`(`:568`):`order_qty // div`、`filled_qty // div`,`div` 由
`_lot_unit(market)`(`:37`)決定(TS/TA/TP → 1000「張」;TF/TO/OF/OO → 1「口」;TL/TC → 1「股」)。
`avg_fill_price = fill_value / filled_qty`(round 4)。

### 1.3 部位那一半:樂觀套用 vs 券商真相(兩條路匯流)

```
  成交 D 到達
     │
     ├─ 路 A(樂觀,0.1–0.2 ms):_apply_fill_locked(store.py:332)
     │     只套「這張單尚未套過的整張增量」delta = filled_qty//unit − applied_qty
     │     增量均價 fill_avg = (fill_value − applied_value)/(filled_qty − applied_shares)
     │     沖銷兩向(:388 / :409)→ 開列 / 加碼 / 減碼 / 翻倉
     │     avg_source = "fill"(純成交價),pnl_* 一律清 None
     │     → _emit capital_position {source:"fill"}
     │
     └─ 路 B(真相,p50 1.94 s):_mark_balance_dirty(0.5)
           → 幫浦圈 _maybe_query_balance:begin_snapshot() 記**涵蓋水位**
           → GetRealBalance ─(p50 0.56 s)→ _on_balance_complete → _pending_sec
           → GetProfitLossGW ─(p50 0.58 s)→ _on_profit_complete(回填 avg_source="broker")
           → GetOpenInterestGW ─(p50 0.30 s)→ _on_oi_complete
           → _finalize_positions → store.set_positions(全量替換)
                └ 水位前的成交標「已套用」;**水位後的增量重套於快照之上**(store.py:715-723)
```

---

## 2. 端到端延遲預算

> 我負責那一段 = **「群益回報進入本行程」→「委託/部位新狀態推播出去」**,
> 外加下游到畫面的兩段(因為後端把自己優化到 0.1 ms 之後,下游還有固定 200 ms)。

| # | 區段 | 位置 | 成本 | 基礎 | 備註 |
|---|---|---|---|---|---|
| 1 | 送單結果落審計 → 群益**首則回報**到達 COM 執行緒 | `client.py:349` ↔ `client.py:402` | **p50 0.57 s / p90 0.94 s / p99 1.05 s / max 26.9 s** | 實測 n=366(audit post ts 配 log 毫秒時戳;剔除 >30 s 的預約單 / 跨場) | audit ts 只有**秒**解析度 → ±0.5 s 量化誤差。這是整條回報鏈最大的一格,而且**完全在群益端** |
| 2 | `parse_onnewdata`(48 欄 split + 取值) | `reply.py:100-131` | **3.2 µs**(p95 3.5 µs) | 實測 20,000 次 | 不是問題 |
| 3 | `logger.info("Capital reply: …")` 經 `_Tee` 同步 flush | `client.py:405-408` + `server/__main__.py:85-92` | **p50 12.5 µs / max 150 µs** | 實測 500 行 | **console 被 QuickEdit 選取時無上界**(見 FM-04) |
| 4 | `store.apply_reply`(含取鎖) | `store.py:188-258` | N=16 **17.3 µs**;N=63 **20.7 µs**;N=200 32.2 µs;N=1000 84.6 µs(p50) | 實測 400 次/檔位 | prod 實際 N = 24–63(30 天實錄) |
| 5 | └ `_apply_fill_locked` + `_with_today_qty_locked`(O(N) 掃全部委託) | `store.py:332-482` / `:300-321` | 包含在 #4;prod 自報 **0.1–0.2 ms**(含 log + `positions()`) | 實測 189 筆 prod log | 成長軸是 `_orders` 筆數,不是當日成交數 |
| 6 | `_emit` → `call_soon_threadsafe` → loop 醒來 → `capital_ws.publish` | `client.py:279-286` / `app.py:940-942` | **未量測** | — | 下界 = Windows timer 抖動地板(閒置 loop `sleep(0.05)` overshoot p50 **12.43 ms**,已知事實);上界 = loop 被 TC4 fanout 佔住的時間(**零儀器**) |
| 7 | WS 送出 → 瀏覽器收到 | `server/ws.py` | **推估 < 1 ms**(localhost) | — | per-client 各編碼一次(已知事實) |
| 8 | 前端 `capital_order` / `capital_position` **trailing debounce** | `frontend/src/hooks/useCapital.ts:129-143` | **固定 200 ms** | 讀 code | WS payload 只帶 `count`,**沒帶部位資料** → 必須再打一趟 HTTP |
| 9 | `GET /api/capital/positions`(M=5) | `capital_api.py:278-291` | **推估 < 0.1 ms**(`positions()` 0.0003 ms + `asdict` 1.9 µs/列 + `stock_code_of`/列) | 實測前兩項 | `stock_code_of` 含 `stat()`,B10 F-16 已列 |
| 10 | `GET /api/capital/orders`(全表 + asdict) | `capital_api.py:254-261` | N=16 **0.030+0.051 ms**;N=63 **0.115+0.199 ms**;N=200 0.36+0.63;N=1000 1.99+3.32 | 實測 200 次/檔位 | 前段持 `store._lock`,在 **event loop 執行緒**上 |
| **A** | **成交 → 樂觀部位出現在畫面** | #4+#6+#7+#8+#9 | **推估 ≈ 215–260 ms**(其中 200 ms 是前端 debounce,後端只佔 0.02 ms) | 混合 | 後端把自己優化到 0.1 ms,下游固定加 200 ms |
| **B** | **成交 → 券商真相落地(`set_positions`)** | `client.py:475` → `:649` | **p50 1.94 s / p75 2.19 s / p90 3.97 s / max 6.64 s** | **實測 n=183**(log「部位落地 …(自成交回報到達起 N ms)」) | CLAUDE.md §4 寫的「~2 s」= p50 準確,但**尾巴是 3.4 倍** |
| B1 | └ debounce | `client.py:475` | **固定 0.5 s** | code | |
| B2 | └ GetRealBalance → 庫存段收齊 | `client.py:520` → `:530` | p50 **1.06 s** 起算(扣 debounce ≈ 0.56 s);p90 3.25 s;max 5.57 s | 實測 n=179 | |
| B3 | └ GetProfitLossGW → 損益段收齊 | `client.py:549` → `:557` | p50 **1.64 s** 起算(增量 ≈ 0.58 s);p90 3.66 s;max 6.33 s | 實測 n=181 | |
| B4 | └ GetOpenInterestGW → 期貨段收齊 | `client.py:628` → `:645` | p50 **1.94 s** 起算(增量 ≈ 0.30 s);p90 3.97 s;max 6.64 s | 實測 n=182 | |
| B5 | └ `set_positions` 本體(持鎖,COM 執行緒) | `store.py:659-724` | N=63/M=5 **0.043 ms**;N=200/M=20 0.237 ms;N=1000/M=50 1.83 ms | 實測 100 次/檔位 | O(M×N),prod 檔位下可忽略 |
| **C** | **開機 ConnectByID backlog 重播** | `com.py:145-147` | 每則 **~100 ms** 固定節奏;prod 總長 **0.0–13.4 s**(2–145 則) | 實測 64 份 log | 盤中重啟多為 0.1–0.5 s(整批到);盤外重啟 2.6–7.5 s |
| C1 | └ 重播開始 → **第一次**部位落地 | | **1.82–10.93 s**(中位 ≈ 3.2 s) | 實測 44 份有落地紀錄的 log | 這段與 C 重疊的長度 = **幽靈部位窗**(見 F-01) |

### 2.1 把預算讀出來的三句話

1. **Python 段合計 < 0.05 ms**,而它前面是 0.57 s(群益回報)、後面是 200 ms(前端 debounce)
   + 1.94 s(回查鏈)。**這一段不需要效能優化,需要的是正確性與可觀測性。**
2. **回查鏈 p90 = 3.97 s** 才是「下單後倉位很慢」的真來源,而它三段全是**同步 COM 查詢串行**,
   跑在**唯一一條也負責送單的執行緒**上。
3. **開機重播 vs 首次落地重疊 = 幽靈部位窗**,prod 實測 4.56–7.25 s,10/64 次重啟命中。

---

## 3. 逐題回答

### Q1 完整狀態轉移圖
見 §1.2。補三點 code 層事實:

- **`_RANK` 是棘輪不是狀態機**:`_set_status` 用 `>=`,所以**同 rank 會覆寫**
  (`失敗`(3) 後來一則 `全部成交`(3) → 變全部成交)。順序敏感,但兩者都是終態、`actionable` 都是 False,
  畫面差別只在文字。
- **`D` 先於 `N` 到的亂序有守**(`_refresh_fill_status` `store.py:177-186`):`order_qty == 0` 時
  **不准**斷言「全部成交」—— 因為 rank 3 進去就退不回來,部分成交的活單會被鎖死在面板上不可刪改。
  `tests/capital/test_store.py:141` 釘住。**這條寫得對,不要動。**
- **`D` 無價整筆不採計**(`store.py:228`):量與均價分子綁定,少算成交 → `remaining_shares` 高估 →
  改價金額閘更嚴 = 安全方向。**寫得對,不要動。**

### Q2 `seq` 去重機制:**不存在**

`store.py:10-12` 自承:「聚合**非冪等** — 同一筆回報事件只能 apply 一次
(目前唯一來源 ConnectByID 啟動重播 + 即時推送,天然唯一)」。

- **沒有任何 `seen` 集合、沒有事件指紋、沒有 idempotency key。** `apply_reply` 對同一則
  `bstr_data` 呼叫兩次 = `filled_qty` 累加兩次。
- **跨重啟「有效」的方式是靠 store 是新的**,不是靠去重:每次重啟 `CapitalStore()` 全新 → 重播重建。
- **回報斷線重連沒有保護**:`_handle_reply_disconnect`(`client.py:455-462`)只降 `degraded`,
  **不重連也不 `clear()`**;`com.py:273` 註明「自動重連需先 `store.clear()` 防成交重複累計,另案處理」。
  也就是說:**只要有人把自動重連加上去而忘了 `clear()`,成交量就會靜默雙計** ——
  而 `clear()` 現在**零 prod caller**(全 repo grep 只有測試呼叫),所以它是一條沒人走過的路。
- **seq 本身是否會重用**:`note_price_type`(`store.py:496-530`)長篇說「群益 seq 是日曆日重置
  還是交易日重置**未實證**」。**本輪用 30 天 prod 資料回答了一半**:
  467 個 distinct seq、**同一個 seq 對到多個股號的筆數 = 0**;前綴分布 `{23132: 366, 23131: 94, 23156: 7}`,
  日內單調遞增、跨日不回頭(08-13 的 2313190660095 → 09-11 的 2313232942599,約 +1.4M/日)。
  → **推論(30 天實證,非證明):群益 seq 是全域單調計數器,不做日重置**,
  N075 那個「同檔同方向撞同 seq」的誤標窗在觀測期內**沒有發生過一次**。年度 rollover 未觀測。

### Q3 樂觀套用 vs 快照落地的競態:窗多長、看到什麼

**窗長 = 實測 p50 1.94 s / p75 2.19 s / p90 3.97 s / max 6.64 s(n=183)。**
CLAUDE.md §4 的「~2 s」在 p50 準確,但**尾巴是 3.4 倍**,而尾巴正是開盤連續成交時。

窗內會看到什麼(四種,依成因):

| 成因 | 窗內畫面 | 落地後 | 訊號 |
|---|---|---|---|
| 樂觀套用**成功**(prod 189/192 = 98.4%) | 部位列已在,`avg_source="fill"`(純成交價)、`pnl_base=null` | 換成 `avg_source="broker"`(含買費均價) | 打平線**跳一格**,CLAUDE.md §4 已記 |
| 樂觀套用**失敗**(prod 3/192:零股 TC ×2、無券 8358 ×1) | **部位列整個不在** | 才出現 | log 有「成交未樂觀套用…等回查鏈」,畫面零訊號 |
| **沖銷兩向**未涵蓋的組合(見 Q4) | 幽靈雙列 / kind=cash 負張數 | 修正 | 零訊號 |
| **開機重播跨越落地**(見 F-01) | **幽靈部位,平倉鈕可按** | 4.56–7.25 s 後消失 | 零訊號 |

窗內**平倉鈕是活的**:`close_position`(`client.py:1178`)只查 `store.position_for`,
`_close_dup_reason`(`:1122`)只擋「in-flight 10 s」與「同標的同向**活躍**委託」——
重播出來的單全是終態(`actionable=False`),**擋不住**。

### Q4 同股號沖銷兩向的實作正確性

**正向(現股買先沖 daytrade_sell)** `store.py:388-407`:
```python
if market == "sec" and kind == "cash" and signed > 0:
    ds = self._positions.get((key_no, "daytrade_sell"))
    if ds is not None and ds.qty < 0:
        offset = min(signed, -ds.qty)
        ... signed -= offset
        if signed == 0: return True
```
**反向(無券賣先沖現股多單)** `store.py:409-430`:對稱寫法,`offset = min(-signed, long_row.qty)`。

逐條查核結果:

| 面向 | 結論 |
|---|---|
| 沖銷段均價處理 | **正確**:走 `dataclasses.replace(qty=…)`,`avg_price` 不動(減碼語意),`pnl_*` 清 None |
| 歸零刪列 | **正確**:`if ds.qty + offset == 0: del` |
| 餘量接續 | **正確**:`signed -= offset` 之後才走一般開列 / 加碼路徑,測試 `:892` / `:914` 釘住 |
| `fill_avg` 除以零 | **不可能**:`delta > 0` ⇒ `applied_shares = applied_qty×unit ≤ (total−1)×unit < filled_qty`,分母 ≥ unit。**驗證過,不要為此加防禦** |
| 殘量(不足 1 張)價金 | **正確**:`applied_value += fill_avg × delta × unit` 只消化整張的價金,殘股留給下一張(測試 `:699`) |
| 翻倉均價 | **正確**:用「換號」判(`(new_qty>0) != (prev.qty>0)`)不用幅度判,測試 `:736` 釘住(修過 review F-03) |
| **缺口 1**:`無券賣` 回報若帶 `00`(現股)而賣量 **> 現有多單** | 兩個沖銷分支**都不成立**(分支 a 要 `signed>0`、分支 b 要 `kind=="daytrade_sell"`)→ 落到一般路徑 → 產生 **`(股號, "cash")` 且 `qty < 0`** 的列。`_CLOSE_MAP` 沒有 `(cash, False)` 鍵 → **平倉直接 403**,而畫面看不出差別。CLAUDE.md §4 把 `(cash, qty<0)` 定義成「資料矛盾,該拒絕」——但那條講的是 **wire 上 kind 被單邊改回 cash**;這裡是 **store 自己算出來的**。窗長 = 回查鏈(1.9–6.6 s)。**觸發條件我沒有 prod 實錄(推測):需要無券賣量超過持股且群益回 `00`** |
| **缺口 2**:融資買 / 融券賣**不參與**任何沖銷 | 設計如此(不同交易別不自動沖銷),**正確** |
| **缺口 3**:`_today_net_lots_locked`(`:300`)以 **`a.fill_date`(整張單最後一筆成交的到達日)** 判「今天」 | 對證券 ROD 單不可達跨日,**目前正確**;但這是**每張單一個日期、不是每筆成交一個日期**——若未來接 GTC / 預約單跨日部分成交,整張單的量會被算成今天的,前端當沖稅減半 → **少收稅、打平線偏低,零訊號** |

### Q5 `_orders` / `_fills` 成長:所有 O(N) 路徑與實際 N

**實際 N(30 天 prod 實錄,per session)**:distinct 委託序號 **24 / 27 / 30 / 63**,
事件總數 47 / 50 / 58 / 145。session 長度數小時,**每天都重啟**(64 份 log / 30 天)。
→ **prod N ∈ [24, 63]**。長跑一週不重啟的推估 N ≈ 280。

| O(N) 路徑 | 位置 | 觸發頻率 | N=63 實測 | N=1000 實測 | 判定 |
|---|---|---|---|---|---|
| `_today_net_lots_locked` 掃全部委託 | `store.py:300-321` | **每次部位變更**(每筆成交 + 每列快照) | 含在 20.7 µs 內 | 含在 84.6 µs 內 | **不是問題** |
| `set_positions` 的 `_with_today_qty_locked` × M 列 | `store.py:704` | 每 60 s + 每筆成交後 | 0.043 ms (M=5) | 1.83 ms (M=50) | **不是問題**(但持鎖,見 Q7) |
| `set_positions` 的水位重套迴圈掃全部委託 | `store.py:715-723` | 同上 | 同上 | 同上 | 同上 |
| `orders()` 排序 + `_to_record` × N | `store.py:594-603` | `/api/capital/orders`(30 s 輪詢 + 每筆回報 debounce invalidate)、`_close_dup_reason`(每次平倉)、`_correct_price_tick_gate`(每次改價) | **0.115 ms 持鎖** | 1.99 ms 持鎖 | **不是問題**,但在 event loop 上取鎖(Q7) |
| route 的 `asdict` × N(鎖外) | `capital_api.py:258` | 同上 | 0.199 ms | 3.32 ms | 不是問題 |
| `_append_fill_locked` 的 prune(重建整個 list) | `store.py:262-264` | **每筆成交** | `fills()` 全表 0.0093 ms | — | 不是問題 |
| `fills()` 讀時再濾 | `store.py:293-298` | `/api/capital/fills` | 0.0093 ms | — | 不是問題 |
| `note_price_type` 的 stale prune 掃全表 | `store.py:538-542` | 每次送單成功 | — | — | 不是問題 |
| `_price_types` / `_contract_ym` / `_close_inflight` / `_avg_logged` 的成長 | `store.py:151,155` / `client.py:236,238` | — | — | — | `_contract_ym` **只有 `clear()` 會清**(零 caller)→ 每筆期貨單留一項永不釋放;其餘三個都小。**記憶體不是問題,但「零 caller 的清理路徑」是個氣味** |

**結論:`_orders` 的成長軸是 process uptime 而非當日筆數(上一輪已指出),但在 prod 實際檔位下
所有 O(N) 路徑都在 0.2 ms 以內。這一節不需要動。** 真正的成長風險是 `clear()` 的零 caller ——
它讓「回報重連」這條路永遠沒被走過(見 Q2 / FM-02)。

### Q6 重啟恢復:哪些回得來、哪些回不來

| 資產 | 恢復方式 | 洞 |
|---|---|---|
| **未成交委託** | ConnectByID backlog 重播 N 事件(prod 實錄每次 2–145 則,~100 ms/則) | 回得來 |
| **當日成交** | 重播 D 事件 → `_Agg.filled_qty` / `_fills` 重建 | **`FillRecord.date` 被蓋成「重播當下的本機日」**(`store.py:262,278`),見 F-02 |
| **部位** | 不靠重播:`_positions_seeded=False` 擋住樂觀套用,靠券商快照落地(1.8–10.9 s)| **重播跨越落地 → 幽靈部位**,見 F-01 |
| **`price_type`(市價 / 限價標籤)** | **回不來**:`_price_types` 是送單意圖、純記憶體,重播不會重建 | 重啟後本 app 送出的市價單全體失標。已知、可接受(`clear()` 刻意不清它,但重啟時 store 是新的) |
| **`_snapshot_watermark`** | `None` 開機 = 「快照即真相」 | 寫得對(`store.py:648-657`,pr-163 F-01 修過),但只涵蓋「重播**早於**落地」,不涵蓋「重播**晚於**落地」→ F-01 |
| **審計** | `data/audit/capital-*.jsonl` append-only | 回得來,但 `server/audit.py:34-37` **只 flush 沒 fsync**(上一輪已列) |
| **訊號/委託關聯** | 無 | 無 `request_id` / client order id(上一輪 F-09) |

**最大的洞**:重啟恢復把「重播」與「即時」當成同一種事件餵進同一個狀態機,
而**狀態機沒有任何方式分辨它們**——`ReplyRecord` 裡沒有「這是重播」的欄位,
`_handle_reply` 也沒有把 `_positions_seeded` 以外的任何閘接上去。

### Q7 鎖的粒度

`CapitalStore._lock = threading.Lock()`(`store.py:143`),**一把鎖護全部四個結構**。

**持有者與時長(實測)**:

| 呼叫者 | 執行緒 | 持鎖時長 | 鎖內有沒有 IO |
|---|---|---|---|
| `apply_reply` | COM | 17–21 µs (N=63) | **有**:`_apply_fill_locked` 的 `logger.info`(`:365`)/ `logger.warning`(`:372`) |
| `set_positions` | COM | 0.043 ms (N=63,M=5) | **有**:重複列 `logger.warning`(`:697`)+ 水位重套 `logger.info`(`:717`) |
| `begin_snapshot` | COM | < 0.01 ms | 無 |
| `orders()` | **event loop** | 0.115 ms (N=63) | 無 |
| `fills()` | **event loop** | 0.009 ms | **可能有**:`_fill_live` → `self._calendar()` → `_calendar()`(`client.py:121`)**首次呼叫會讀檔**(lazy singleton),一次性 |
| `positions()` / `position_for()` / `remaining_shares()` / `market_of()` | **event loop** | 0.0003 ms | 無 |
| `note_price_type` / `forget_price_type` | **event loop** | < 0.01 ms | 無 |

**判定**:
- **時長本身完全沒問題**(prod 檔位全部 < 0.2 ms)。
- **但「鎖內 log」是真的**,而 log 走 `_Tee`(`server/__main__.py:85-92`)**每筆 write 同步 flush 到檔
  + 寫 console**。平常 12.5 µs;**console 被 Windows QuickEdit 選取時 `WriteConsole` 會阻塞到使用者
  按 Esc 為止**(推測觸發,機制是 Windows 已知行為)。那一刻 COM 執行緒握著 `store._lock` 不放 →
  event loop 上每一支 capital route **同步** `lock.acquire()` → **整個 event loop 凍住** →
  所有 TC4 推播、所有 WS、所有 route 一起停。見 FM-04。
- `positions()` 回傳的是**物件參考**(`store.py:726-736` 自己寫了長註)。目前唯一在
  **已發布**物件上就地寫的路徑是 `_finalize_positions(self._stale_fut_positions())` →
  `set_positions` 的 carry-over 五行,而那五行在 `p is prev` 時全是自我賦值 → 沒有撕裂讀。
  **這是一個靠「恰好」成立的不變量**,不是靠型別或鎖保證。見 FM-09。

---

## 4. Findings

### F-01 【critical】開機 backlog 重播跨越第一次快照落地 → 幽靈部位,平倉鈕可按

**位置** `copycat/capital/store.py:236`(`return self._apply_fill_locked(a) if self._positions_seeded else False`)
+ `:724`(`self._positions_seeded = True`)

```python
# store.py:229-237(apply_reply 的 D 分支)
if rec.price is not None:
    a.filled_qty += rec.qty
    a.fill_value += rec.price * rec.qty
    a.fill_date = self._today()
    self._append_fill_locked(a, rec)
self._refresh_fill_status(a)
# 快照未落地(開機 / 重連重播中)只累計不套
return self._apply_fill_locked(a) if self._positions_seeded else False
```

`_positions_seeded` 是**一個全域布林**,不是「這一則事件是不是重播」的判斷。
`set_positions` 一落地它就翻 True(`:724`),**而 backlog 還在以 ~100 ms/則的節奏流進來**。
從那一刻起,**重播出來的歷史成交被當成新成交,樂觀套用到剛落地的券商快照之上**。

**prod 實證**(`logs/server-20260901-1515.log`):
```
15:16:16,270  balance 鏈: 部位落地 2 列(自成交回報到達起 862 ms)   ← _positions_seeded = True
15:16:16,276  WARNING GetRealBalanceReport rc=1019: SK_ERROR_QUERY_IN_PROCESSING
15:16:17,294  WARNING GetRealBalanceReport rc=1019: SK_ERROR_QUERY_IN_PROCESSING
15:16:17,481  成交樂觀套用部位: seq=2313218142671 stock=6182 (0.2 ms)   ← 重播列
15:16:17,730  成交樂觀套用部位: seq=2313218233192 stock=6182 (0.1 ms)   ← 重播列
15:16:17,981  成交樂觀套用部位: seq=2313218320363 stock=2243 (0.1 ms)   ← 重播列
15:16:18,542  WARNING GetRealBalanceReport rc=1019
15:16:19,602  WARNING GetRealBalanceReport rc=1019
15:16:22,038  balance 鏈: 部位落地 2 列(自成交回報到達起 4057 ms)   ← 自癒,窗 = 4.56 s
```
(15:16 已收盤三小時,這些不可能是真成交。)

**全樣本掃描(64 份 log)**:**10 份**出現 seed 後的重播樂觀套用,共 **34 筆**,窗長
**4.56 / 4.79 / 4.92 / 5.48 / 5.96 / 6.13 / 6.41 / 6.80 / 6.99 / 7.25 秒**。
最壞一次 `server-20260911-0036.log` **9 筆**。

**確定性重現**(腳本 `repro_phantom.py`,本目錄):
```
落地當下(= 券商真相): [('2330', 1), ('6182', 1)]
重播後半段之後       : [('2243', 1), ('2330', 1), ('6182', 3)]
```

**為什麼零訊號**:幽靈列與真部位在 `/api/capital/positions` 上**逐欄相同**
(`avg_source:"fill"` 是唯一差異,而前端 `useCapitalStream` 對 `capital_position` 一律 invalidate、
**不看 `source`** —— `client.py:429-433` 自己寫了「讀者目前 = 無」)。
`close_position` 只查 `position_for`;`_close_dup_reason` 只擋「in-flight 10 s」與
「同標的同向**活躍**委託」,而重播的單全是終態 → **擋不住**。
**按下平倉 = 一張真單進市場,平掉一個不存在的部位 = 反向開倉。**

**測試盲區**:`tests/capital/test_store.py:987`
`test_boot_watermark_before_backlog_does_not_reapply_replayed_fills` 只蓋
「重播**整批早於**落地」;**「重播跨越落地」沒有任何一條測試**。

**修法(三選一,由小到大)**
1. 最小:`_positions_seeded` 改成「**首次落地 + 重播靜默期**」——
   `set_positions` 落地時記 `_seed_at = monotonic()`,`apply_reply` 的 D 分支在
   `now - _seed_at < REPLAY_QUIET_S`(建議 2 s,= 觀測到的最大重播間隔 ~0.25 s 的 8 倍)且
   該 `_Agg` 的**第一則事件早於 `_seed_at`** 時不套。
2. 中:讓 `client._init_com` 在 `connect_reply` 之後、幫浦圈開始之前**先完成一輪回查鏈**,
   並在重播結束(連續 `REPLAY_QUIET_S` 無事件)之前一律不開樂觀套用。
3. 正解:**去重**——`_Agg` 記下已見過的事件指紋(`(seq, idx2, idx20, idx24)` 或整列 hash),
   重播與即時自動變成冪等。同時把 Q2 的「回報重連不可加」限制一併解除。

---

### F-02 【high】跨午夜重啟:昨日成交被蓋成今日日期,畫進今天的分時圖(且 `models.py` 白紙黑字說這條不可達)

**位置** `copycat/capital/store.py:260-282`

```python
def _append_fill_locked(self, a: _Agg, rec: ReplyRecord) -> None:
    today = self._today()          # ← 本機「現在」的日曆日
    ...
    self._fills.append(FillRecord(
        ...,
        date=today,                # ← 不是 rec.date(idx23)
        time=rec.time or a.time,   # ← 卻是**原始成交時刻**
    ))
```

`FillRecord.date` 的語意是「成交**到達**本機日」。對即時推播正確;**對 ConnectByID 重播就是謊報**。

**`models.py:124-128` 明確主張這條不可達**:
> 已知殘餘限制:重播蓋日(跨錨定日重連時 `store.clear()` 後重播昨日 D 事件會以到達日重建)
> 目前**不可達** —— `clear()` 零 prod caller(ConnectByID 只在開機重播,屆時 store 是新的)

**這個推論錯了**:store 是不是新的與 `date` 蓋不蓋無關。新 store 在 00:36 重播昨日 D 事件,
一樣把 `date` 寫成今天。

**prod 實證**:
```
logs/server-20260910-0905.log  2026-09-10 09:06:14,012  seq=2313231157711 stock=6949 status=成交
logs/server-20260911-0036.log  2026-09-11 00:36:13,241  seq=2313231157711 stock=6949 status=成交   ← 同一筆,重播
```
2026-09-11 00:36 那次重啟共重播 **21 則成交**,全部被記成 `date="20260911"`、
`time` 保留 09-10 的原始成交時刻。

**下游**:`fills()` 的保留窗 `_fill_live`(`:283`)先比 `f.date == today` → **通過**;
前端 `fill-marks.ts:104`(`if (b.date !== todayYmd) return null`)與 `:193`
(`anchorDateOf(stamp) !== anchorDate`)兩道守門**也通過**(後端已經把日期改成今天了)。
→ **昨天的成交三角畫在今天的分時圖上,時刻照舊。**

**不受影響的是閃電梯**:`ladder-lots.ts:119` 以**委託**的 `o.date`(= idx23 原單日)判
`filledDates.has(o.date)`,重播的舊單被排除。所以只有圖上的成交點壞掉 —— **一半壞一半對,
更難察覺**。

**觸發頻率**:64 份 log 中跨午夜重啟 **≥ 6 次**(08-21 01:35、08-22 00:48、08-22 02:58、
08-28 00:44、09-01 00:23、09-01 01:14、09-11 00:36)。實務上這些 process 多半在開盤前又被重啟一次
(所以沒人看到),但**只要有一次活到隔天開盤,整天的成交點圖就是錯的**。

**修法**:`_append_fill_locked` 的 `date` 改取 `rec.date`(idx23)、缺值才退回 `self._today()`。
代價 = 期貨夜盤跨午夜的 `date` 語意要重新對 `_anchor_trade_date`(`:114`)。
**或者**更保守:`_handle_reply` 傳一個 `replayed: bool` 進來,重播列直接用 `rec.date`。
不論哪種,`models.py:124-128` 那段「不可達」的敘述**必須刪掉**——它現在在誤導下一個人。

---

### F-03 【high / quant-gap】`U` / `P` / `B` / `S` 四條狀態轉移在 prod 從未執行過一次

**證據**(30 天、3,201 則 `Capital reply`):
```
1602  status=委託 (N)
1037  status=成交 (D)
 440  status=刪單 (C)
   0  改量 (U) / 改價 (P) / 改價改量 (B) / 退單 (S)
```
**審計側同源**(1,075 列):`order 841 / cancel 232 / close 2`,
**`correct-price` 與 `decrease` 各 0 次**。

也就是說 `store.py:240-256` 的 U / P / B / S 分支、`_ACTION_TYPES`(`:82`)的
「刪改失敗不標終態」邏輯、`remaining_shares`(`:605`)的改價金額閘、
`_correct_price_tick_gate`(`capital_api.py:180`)—— **全部只在測試裡跑過**。

**為什麼這對量化系統重要**:改價(chase)是自動化執行最基本的一招。
現在這條路徑的第一次真實執行會發生在**真錢盤中**,而它牽涉:
- `_set_status("改價")` rank 1 **低於**「部分成交」rank 2 → 部分成交後改價,`status_label`
  **不會**變成「改價」(棘輪擋住),但 `a.price` 會變 → 畫面顯示「部分成交 @ 新價」,
  看不出改價成功與否。**要靠 `remaining_shares` 反推,零直接訊號。**
- `U` 減量到 0:`order_qty = after_qty = 0` → `_refresh_fill_status` 在 `filled_qty <= 0` 時
  **直接 return**(`:180`)→ 狀態停在「改量」(rank 1)→ **`actionable` 仍為 True**,
  一張已經沒有剩量的單在面板上還有刪 / 改鈕。(推測:是否允許減到 0 取決於群益,未實證。)
- `S`(退單)`prod` 零樣本 → `_TYPE["S"]="退單"` 的欄位索引假定沒被驗過。

**建議**:在開自動改價之前,先用**一筆最小量、遠離市價的限價單**跑一次
「送出 → 改價 → 改量 → 刪單」全鏈,把四則回報的原始字串收進 fixture。
這是 `tc4-market-facts` 那種「實錄校準」的標準做法,repo 已有先例。

---

### F-04 【high】回報處理與所有 log 都在**唯一一條也負責送單的執行緒**上,且 log 走同步 console 寫入

**位置** `client.py:795-836`(`_run`)、`client.py:405-408`、`server/__main__.py:83-92`(`_Tee.write`)

COM 執行緒的一輪:`pump()` → 3× `collector.poll()` → `_maybe_query_balance()` → `_poll_pending()`
→ `_cmd_q.get(timeout=0.05)` → 執行寫入命令。**回報回呼(`OnNewData`)也在這條執行緒上被 COM 幫浦驅動。**

每則回報至少 1 行 `logger.info`(`:405`),成交多 1–2 行。每行都經 `_Tee.write`:
```python
def write(self, s: str) -> int:
    if self._sink is not None:
        self._sink.write(s); self._sink.flush()   # 檔案,每筆 flush
    return self._stream.write(s)                   # ← 真正的 console
```
實測 12.5 µs p50 / 150 µs max(檔案 sink + devnull console)。
**但 `run.ps1` 把 server 跑在使用者的 PowerShell console 裡**,而 Windows console 的
QuickEdit 模式在使用者用滑鼠選取文字時會**阻塞 `WriteConsole` 直到按 Esc**(推測觸發,
機制是 Windows 已知行為;我無法在此環境驗證)。

**複合後果**:COM 執行緒停住 → `_cmd_q` 沒人取 →
`_execute_write` 的 `wait_for(shield(fut), timeout=_WRITE_TIMEOUT_S)` 逾時 →
回「結果未知,勿重送」→ **而上一輪已確認「逾時的命令沒有 TTL、仍留在 `_cmd_q`,恢復後照送」**
→ 使用者放開選取的那一刻,10 秒前放棄的單進市場。
開盤重播期(~100 ms/則 × 145 則)正是 console 滾得最快、使用者最可能去選取 log 的時刻。

**修法**:log 移出熱路徑 —— `QueueHandler` + `QueueListener`(stdlib,零新依賴),
COM 執行緒只 `put` 到無界 queue,listener 執行緒負責寫檔與 console。
順帶把 F-06 的「鎖內 log」一併解掉。

---

### F-05 【high】`store._lock` 內呼叫 `logger`(檔案 flush + console 寫)

**位置** `store.py:365`、`:372`、`:697`、`:717`

```python
# store.py:715-723,set_positions,持 self._lock
if delta > 0:
    if self._apply_fill_locked(a):
        logger.info("快照落地重套水位後增量: %s %s %s %d 張/口(水位 %d 股)", ...)
```
```python
# store.py:363-366,_apply_fill_locked,持 self._lock(由 apply_reply 取得)
if k is None:
    logger.info("成交種類 %r 不在樂觀套用表,等回查鏈: %s", a.flag_label, a.stock_no)
```

而 event loop 上的 `orders()` / `fills()` / `positions()` / `position_for()` 都是**同步**
`lock.acquire()`。鎖內的 log = **event loop 的阻塞時間直接綁在 console 的寫入延遲上**。

**量級誠實說**:平常 12.5 µs,一天觸發次數 = 「重套水位」prod 30 天共 **9 次**、
「成交種類不在表」共 **1 次**。**在健康路徑上這完全不是效能問題。**
列出來是因為它是 F-04 的放大器:console 一卡,連帶把 event loop 也卡住,
而不只是卡住 COM 執行緒。

**修法**:把 log 搬到鎖外(收集要印的東西,`with` 區塊結束後再印)。
`set_positions` 的重套 log 可以先 append 到 local list,離開 `with` 再迴圈印。**三行的事。**

---

### F-06 【medium-high】`clear()` 零 prod caller ⇒「回報斷線重連」這條路永遠是死的

**位置** `store.py:623-637`、`client.py:455-462`、`com.py:270-275`

```python
# client.py:455-462
def _handle_reply_disconnect(self, error_code: int) -> None:
    """OnDisconnect:回報主機斷線 → degraded(送單通道獨立可用),
    不自動重連、不 clear store(重播 backlog 前必須先 clear,另案;review R7)。"""
```

現況:回報主機斷線 → 狀態降 `degraded` → **委託 / 成交回報永久停更,直到重啟整個 server**。
而 `_execute_write` **明確放行 degraded**(`client.py:879-880`:「送單通道獨立可用」)。

**也就是說:回報斷線之後,系統可以繼續下單,但看不到任何委託回報、任何成交回報,
部位只靠 60 s 輪詢的回查鏈更新。** 對一個「要下實單」的系統,這是**盲送**。
(上一輪的 F-13 已列「degraded 放行 = 盲送」;本輪補的是**為什麼沒人修**:
因為修它需要 `store.clear()` + 重播,而重播路徑沒有去重 —— 回到 F-01 / Q2 的同一個根。)

**prod 頻率**:30 天 log 中 `grep "回報連線中斷"` = **0 次**(從沒發生過)。
所以這是「沒發生過所以沒人知道會怎樣」的路徑,不是「常常發生」的路徑。

**修法**:與 F-01 的正解同一個 —— **事件指紋去重**。一旦 `apply_reply` 冪等,
重連 + 重播就不需要 `clear()`,`_handle_reply_disconnect` 可以直接接 `connect_reply` 重試。

---

### F-07 【medium】`_to_record` 的 `filled_qty // div` 會把未滿張的部分成交顯示成 0

**位置** `store.py:583-584`

```python
order_qty=a.order_qty // div,
filled_qty=a.filled_qty // div,
```
`div = 1000`(TS/TA/TP)。500 股的部分成交 → wire 上 `filled_qty = 0`、`order_qty = 1`。
`avg_fill_price` 卻有值(`fill_value / filled_qty` 用的是**股**)。
`actionable` 為 True(rank 2「部分成交」)。
→ 面板顯示「部分成交,已成交 0 張,均價 1050.00」。

`_lot_unit` 的 docstring(`store.py:38-43`)說「理論上整股撮合除得盡,分岔不可達」。
**這對整股市場成立**(撮合以張為單位)。列在這裡是因為:
- 盤中零股(TC)不走這條(`div=1`、`unit="股"`),**正確**;
- 但**整股與零股混在同一支 `/api/capital/orders`**,前端 `ladder-lots.ts` 以 `unit === "股"` 排零股
  —— 若群益未來對某市場回不同單位,這裡靜默捨位。
**低優先,但「除不盡就退回原始股數」的處理在 `_append_fill_locked`(`:271`)有做、
在 `_to_record` 沒做 —— 同一個檔案裡兩種處置。**

---

### F-08 【medium】`error_msg` 只進不退:一次刪單失敗之後,那張活單永遠掛著錯誤訊息

**位置** `store.py:215-219`

```python
if rec.order_err in ("Y", "T"):
    a.error_msg = rec.error_msg or a.error_msg
    if t not in _ACTION_TYPES:
        self._set_status(a, "失敗" if rec.order_err == "Y" else "逾時")
```
`_ACTION_TYPES` 的設計很對(刪 / 改失敗不標整張單終態)。但 `error_msg` **沒有對應的清除**:
一張活單刪單失敗一次 → `error_msg` 寫上 → 之後成交、改價、全部成交,那行錯誤訊息**一直在**。
前端會把它顯示在委託列上。

**prod 佐證**:`data/audit/capital-20260911.jsonl` 有 `cancel` → `code 960 [960] 查無委託資料`,
可見刪單失敗**是會發生的**。(不過 960 是送單端拒絕,不一定產生帶 err 的 C 回報。)

**修法**:成功事件(N / D / 非 err 的 C/U/P/B)時 `a.error_msg = None`。一行。

---

### F-09 【medium】`positions()` 回傳已發布物件的**參考**,安全性靠一個「恰好」成立的不變量

**位置** `store.py:726-736`(docstring 自己寫了長註)+ `client.py:638-643`(`_stale_fut_positions`)
+ `store.py:668-674`(carry-over 五行)

```python
# store.py:668-674,set_positions 的 carry-over
if p.avg_price is None and prev is not None:
    p.avg_price = prev.avg_price        # ← 就地寫
    p.avg_source = prev.avg_source
    p.pnl_base = prev.pnl_base
    p.pnl_base_price = prev.pnl_base_price
    p.pnl_cost = prev.pnl_cost
```
一般路徑寫的是尚未發布的新列。**唯一例外**:`_stale_fut_positions()` 回傳的是
`self.store.positions()` 過濾出來的**已發布** `Position` 物件,
它們進 `merged` → `set_positions` → 這五行時 `p is prev` → 五行全是自我賦值 → 沒有可觀測變化。

route 在**鎖外** `dataclasses.asdict(p)`(`capital_api.py:288`)。如果那五行哪天變成
「補一個新欄」或「換來源」,就會在 event loop 正在 asdict 的同時就地改欄 →
**撕裂讀(新 `pnl_base` 配舊 `pnl_base_price`)**,而測試不會紅(單執行緒)。

**這不是 bug,是一顆已經上膛的地雷。** docstring 已經標了(pr-119 F-06),
但保護只有註解。**建議把 `Position` 改成 `frozen=True`**,
所有寫入強制走 `dataclasses.replace` —— 型別檢查會把那五行直接變紅,
而它們本來就是自我賦值,刪掉即可。

---

### F-10 【medium / quant-gap】成交 → 畫面的 200 ms 是後端那段的 **10,000 倍**,而 WS 上根本沒帶資料

**位置** `frontend/src/hooks/useCapital.ts:120-143`、`client.py:429-440`

後端為了「部位早點出現」寫了整套樂觀套用(`_apply_fill_locked`,150 行 + 大量 review 修正),
把延遲壓到 **0.1–0.2 ms**。然後:
```js
// useCapital.ts:129-143  module-level 單一 timer per queryKey
const invalidateTimers = new Map<string, number>();
... window.setTimeout(() => { ...invalidateQueries(...) }, 200)   // trailing debounce
```
WS payload 只有 `{"count": n, "source": "fill"}`(`client.py:430-433`),
**沒有部位本體** → 前端必須再打一趟 `GET /api/capital/positions`。

端到端 ≈ 0.02 ms(store) + loop hop(≥ 12.4 ms 抖動地板) + **200 ms debounce** + HTTP RTT。
**後端的 0.2 ms 在這個預算裡是 0.1%。**

而且 `client.py:429-433` 自己承認:
> `source: fill` 讓讀者分得出這是先到的還是券商確認的。**讀者目前 = 無**

**判定**:樂觀套用**不是白做**(它決定了部位列出不出現,不只是早 200 ms),但
「把延遲從 2 s 壓到 0.2 ms」的收益被前端 debounce 吃掉了 99.9%。
若要真的做到「成交即見」,正解是**在 WS payload 裡直接帶部位快照**(M ≤ 50 列 × ~1.9 µs asdict),
砍掉 200 ms debounce 與那趟 HTTP。

---

### F-11 【medium】`seq` 在 30 天 prod 資料中**沒有重用**——N075 那個誤標窗可以收掉一半

**證據**:467 個 distinct seq、**同 seq 對到多個股號 = 0 筆**;
前綴 `{23132: 366, 23131: 94, 23156: 7}`;跨日單調遞增(08-13 → 09-11 約 +1.4M/日)。

`store.note_price_type`(`:496-530`)為了防「seq 日重置導致誤標」寫了 35 行 docstring、
兩個候選日、綁 `stock_no` + `buy_sell`,並在 `tests/capital/test_store.py:458` 釘了
「同一組輸入 store 分不出兩張單」的窗。

**這一輪的 prod 資料是把那個未實證前提往「seq 全域單調」方向推的第一份證據**
(30 天,不是證明;年度 rollover 未觀測)。
若 user 願意接受這份證據,`note_price_type` 可以退回「只記單一候選日」,
把整個綁定邏輯與 `_price_type_of` 的三道比對刪掉 —— **淨減約 60 行 + 一個永遠測不出來的窗**。

**這是 user 決策,不是我能拍板的**。但 08-25 review 當時的「候選處置 = 送單時刻 ± 窗或 seq 單調性檢查」
現在有資料了:**seq 單調性成立**。

---

### F-12 【low-medium】`_close_inflight` / `_contract_ym` / `_avg_logged` 三個 dict 沒有 prune

**位置** `client.py:236`(`_close_inflight`)、`store.py:155`(`_contract_ym`)、`client.py:238`(`_avg_logged`)

- `_close_inflight[key] = monotonic() + 10`,**只有下一次對同 key 檢查且已過期才 `del`**
  (`client.py:1130-1132`)。平倉 100 個不同標的 → 100 項永遠留著。
- `_contract_ym[seq] = ym` 每筆期貨回報寫一項,**只有 `clear()` 會清**(零 caller)。
- `_avg_logged[(stock, kind)]` 每個曾持有過的部位一項,永不清。

**量級誠實說**:prod 30 天 close 只有 **2 次**、期貨單極少。三個 dict 加起來遠不到 1 KB。
**不是效能問題,也不急著修**。列出來只是為了說清楚:`_orders` 的「成長軸是 uptime」
這個性質不只一處,而是這個模組的通用模式。

---

### F-13 【low】`_fill_live` 首次呼叫在鎖內做檔案 IO(交易日曆 lazy load)

**位置** `store.py:283-291` → `client.py:121-135` → `trading_calendar.load_trading_calendar`

```python
def _fill_live(self, f: FillRecord, today: str) -> bool:
    if f.date == today:
        return True
    cal = self._calendar()        # ← client._calendar,lazy singleton,**首次會讀檔**
```
只有在有「日期不是今天」的 fill 時才走到,且只發生一次(module-level 全域快取)。
成本推估 < 1 ms(JSON 假日表)。**不用修**,列出來是因為 §Q7 問「鎖內有沒有 IO」——答案是「有,一次」。

---

## 5. 失效模式表

| ID | 失效模式 | 觸發 | 使用者/系統看到什麼 | 零訊號? | 位置 | 嚴重度 | 現在怎麼發現 / 要加什麼 |
|---|---|---|---|---|---|---|---|
| FM-01 | **重播跨落地 → 幽靈部位,平倉鈕可按** | 開機 backlog > 首次落地耗時(prod 10/64 次) | 部位面板多出不存在的列 / 張數膨脹;按平倉 = 真單進市場反向開倉 | **是**(與真列逐欄相同) | `store.py:236,724` | **critical** | 現在只有 `grep 成交樂觀套用部位` 落在首次「部位落地」之後。**要加**:重播期旗標 + 落地後 N 秒內樂觀套用一律記 WARNING;或直接修 F-01 |
| FM-02 | **回報斷線後永久盲送** | `OnDisconnect`(prod 30 天 0 次) | 委託 / 成交回報全停,部位只剩 60 s 輪詢;**下單照樣放行** | 半(狀態徽章變 degraded,但下單鈕不變) | `client.py:455-462`, `:879` | high | 徽章已有。**要加**:degraded 時下單前二次確認,或直接擋新倉只放降風險操作 |
| FM-03 | **跨午夜重啟 → 昨日成交點畫到今天的圖** | 00:00–09:00 之間重啟且 process 活到開盤 | 分時圖上出現昨天的買賣三角,時刻照舊;閃電梯正常 | **是**(前端兩道日期守門都被騙過) | `store.py:262,278` | high | **現在無法發現**。要加:`FillRecord` 多一個 `event_date`(= idx23)並在 `fills()` 比它 |
| FM-04 | **console 被選取 → COM 執行緒凍住 → 送單逾時 → 放開後遲送** | Windows QuickEdit 滑鼠選取(**推測**) | 下單轉 10 s 後回「結果未知,勿重送」;放開選取後單才進市場 | **是** | `__main__.py:85-92` + `client.py:405` + 無 TTL 的 `_cmd_q` | high | **現在無法發現**。要加:`QueueHandler`/`QueueListener`;`_cmd_q` 命令加 TTL |
| FM-05 | **鎖內 log 卡住 → event loop 全凍** | FM-04 的放大路徑 | 所有 WS 停、所有 route 停、TC4 推播停 | **是**(看起來像 TC4 斷線) | `store.py:365,372,697,717` | high | 要加:loop lag 探針(上一輪已建議);log 搬出鎖 |
| FM-06 | **改價 / 改量第一次真實執行在真錢盤中** | 首次用 `/api/capital/order/correct-price` | 未知 —— prod 30 天零樣本 | — | `store.py:240-256` | high | **要先做**:小量遠價單跑一次全鏈、收 fixture |
| FM-07 | **減量到 0 的單仍 `actionable`** | `U` after_qty=0(**未實證是否允許**) | 已無剩量的單還有刪 / 改鈕;按下去券商拒絕 | 半(有 broker 錯誤) | `store.py:177-180, 240-245` | medium | 要加:`_refresh_fill_status` 在 `order_qty == 0 且曾 > 0` 時標終態 |
| FM-08 | **無券賣量 > 持股且回報帶 `00` → `(cash, qty<0)` 資料矛盾** | 推測(無 prod 實錄) | 部位列看起來正常,按平倉 **403** | **是** | `store.py:388,409`(兩個分支都不成立) | medium | 要加:`_apply_fill_locked` 收尾檢查 `kind=="cash" and new_qty<0` → WARNING |
| FM-09 | **`_stale_fut_positions` 那條路未來被改 → 撕裂讀** | 有人給那五行加一個新欄 | 前端拿到新 `pnl_base` 配舊 `pnl_base_price`,損益數字錯一拍 | **是**(測試單執行緒不會紅) | `store.py:668-674` + `client.py:638-643` | medium | 要加:`Position` 改 `frozen=True`,讓那五行編譯期變紅 |
| FM-10 | **`error_msg` 只進不退** | 刪 / 改失敗一次 | 那張單此後永遠顯示舊錯誤訊息,即使已全部成交 | **是** | `store.py:216` | low | 要加:成功事件清 `error_msg` |
| FM-11 | **`seq` 為空的回報整筆丟棄且無記錄** | `rec.seq_no` falsy | 該則回報消失,無 log | **是** | `store.py:189-190` | low | 要加:一行 WARNING(`client.py:405` 的 INFO 印得出 `seq=None`,但 store 這邊靜默 return) |
| FM-12 | **`apply_reply` 非冪等 + 任何未來的重連/重放** | 加自動重連而忘了 `clear()` | 成交量雙計 → 部位翻倍 → 平倉送兩倍量 | **是** | `store.py:10-12`(靠註解防守) | high(潛在) | 要加:事件指紋去重(F-01 正解同一件事) |
| FM-13 | **`_price_types` 在重啟後全失** | 每次重啟 | 本 app 送出的市價單標籤消失 | 半(標籤不見得注意得到) | `store.py:151` | low | 已知、接受 |
| FM-14 | **`_snapshot_watermark` 的到達序 vs 券商入帳序偏差** | 成交已入快照但推播晚於查詢出手 | 該筆多計一次,下一輪鏈(~2 s)自癒 | **是** | `store.py:711-714`(pr-163 F-02 已記) | low | 已知、接受;`grep 快照落地重套水位後增量`(30 天 9 次) |
| FM-15 | **`_RANK` 同 rank 覆寫** | `失敗`(3) 之後來 `全部成交`(3) | 狀態文字取決於到達序 | 是 | `store.py:173-175` | low | 兩者都是終態、`actionable` 都 False,實務無害 |

---

## 6. 這裡**不要動**(反向結論)

| 對象 | 位置 | 理由 |
|---|---|---|
| `_refresh_fill_status` 的「`order_qty==0` 不斷言全成」 | `store.py:177-186` | 修過的 bug(部分成交活單被鎖死不可刪改)。`tests/capital/test_store.py:141` 釘住。**動它 = 重新引入已修的 bug** |
| `D` 無價整筆不採計 | `store.py:228` | 少算成交 → `remaining_shares` 高估 → 改價金額閘更嚴 = 安全方向。刻意的 |
| `_ACTION_TYPES`(刪 / 改失敗不標整張單終態) | `store.py:80-82, 217-219` | 標終態會讓活單從面板消失(刪 / 改鈕跟著沒了)。這是對的 |
| 沖銷兩向的 `offset` 算術與增量均價 | `store.py:378-430` | 逐條驗過:除以零不可達、殘量處理正確、翻倉用換號判不用幅度判。**`fill_avg` 不需要加除零防禦** |
| `_apply_fill_locked` 的整體效能 | `store.py:332-482` | prod N=24–63 時 17–21 µs/tick。換 numpy / 換資料結構只會更慢,形狀不對 |
| `parse_onnewdata` | `reply.py:100-131` | 3.2 µs。48 欄 split + 十幾個 `_at`。沒有優化空間也沒有優化必要 |
| `_lot_unit` 的三個字面值(張 / 口 / 股) | `store.py:37-48` | CLAUDE.md §4 跨語言契約,五個讀者(前端 ×2、後端 `_fill_code`)。改字面 = 圖牆個股期三角全滅 |
| `orders()` 的排序鍵與 `arrival` dict | `store.py:594-603` | N=63 時 0.115 ms。B10 F-06 建議加索引,**在 prod 檔位下不值得**(多一個索引 = 多一個要同步的狀態) |
| `_snapshot_watermark` 記 `None` 而不是 `{}` | `store.py:648-657` | pr-163 F-01 修過的 bug(今買 1 顯示 2)。`tests:987` 釘住 |
| `BalanceCollector` 的逐筆 deadline 欠帳機制 | `balance.py:265-402` | N017 修過、寫得極細、docstring 把所有取捨列清楚。**這是全 repo 最不該亂動的一段** |
| `positions()` 回傳參考 + route 鎖外 asdict | `store.py:726-736` | 目前正確(GIL 下 dict 讀是原子)。要改就改成 `frozen=True`(F-09),不要改鎖 |

---

## 7. 改造順序 + 每一步的量測判準

> 原則:**先讓它可觀測、再修真錢路徑、最後才碰形狀**。
> 每一步的 rollback 都必須是「revert 單一 commit」。

### 步驟 1 —— 給重播加旗標與 log(不改行為,只加訊號)
**做什麼**:`client._handle_reply` 判斷「本 session 是否還在 backlog 重播期」
(首則回報起、連續 `REPLAY_QUIET_S=2.0` 無事件為止),把旗標印進既有的
`Capital reply: …` 行;`store.apply_reply` 多收一個 `replayed: bool = False` 參數(目前只 log 不用)。
**為什麼排第一**:F-01 的修法需要這個旗標;而且加上去之後,**現有 64 份 log 的問題可以逐日對帳**。
**量測判準**:
- 重啟 server,`grep "replay=1" logs/server-*.log | wc -l` ≈ 該次 backlog 則數(prod 2–145);
- `grep "replay=1" | tail -1` 的時戳 − 第一則 `Capital reply` 時戳 ∈ [0, 14] s(對得上本輪實測 0.0–13.4 s);
- **關鍵判準**:若 `grep "成交樂觀套用部位"` 有任何一行的時戳落在 `replay=1` 區間內 →
  F-01 命中,數量應與本輪掃到的 34 筆同量級。
**Rollback**:revert;純加欄位與 log。
**工作量**:S

### 步驟 2 —— 修 F-01:重播期不開樂觀套用
**做什麼**:`store` 多一個 `_replay_quiet_until: float | None`;
`set_positions` 落地時不再無條件 `_positions_seeded = True`,
而是 `_positions_seeded = True` 且記 `_seed_at`;
`apply_reply` 的 D 分支在 `replayed=True` **或**
(`monotonic() − _seed_at < REPLAY_QUIET_S` 且該 `_Agg` 首則事件早於 `_seed_at`)時**不套**。
**為什麼排這裡**:這是唯一一條「按下去會送出真單」的零訊號路徑,而步驟 1 給了它判準。
**量測判準**:
- 紅先行:新增 `test_backlog_replay_crossing_first_snapshot_does_not_apply`,
  照 `repro_phantom.py` 的順序,斷言落地後重播列**不改變** `positions()`;
  修前應紅(6182 = 3 張)、修後綠(6182 = 1 張)。
- prod:重啟 5 次(至少 2 次在盤外,backlog 較長),
  `grep "成交樂觀套用部位"` **不得有任何一行落在 `replay=1` 區間** —— 目標 **0 筆**(修前 34/64 次重啟)。
- 回歸:`tests/capital/test_store.py:987`(重播早於落地)仍綠。
**Rollback**:revert 單一 commit;旗標預設關閉即回舊行為。
**工作量**:M

### 步驟 3 —— 修 F-02:`FillRecord` 的日期改用回報日
**做什麼**:`FillRecord` 加 `event_date: str | None`(= `rec.date` / idx23),
`_fill_live` 改成「`event_date` 有值就比 `event_date`,缺值退回既有 `date` 邏輯」;
刪掉 `models.py:124-128` 那段「不可達」的錯誤敘述。
**為什麼排這裡**:比步驟 2 簡單,但影響的是「畫面上的事實」而非「會不會送單」,所以排第二。
**量測判準**:
- 新測:模擬 00:36 重播昨日 D 事件,斷言 `fills()` 回**空**(昨日成交不屬於今日錨定日);
  修前應紅(回 21 列)。
- prod:下一次跨午夜重啟後,`curl -s localhost:8721/api/capital/fills | python -m json.tool`
  在**當日尚無成交**時應回 `{"fills": []}`;修前會回上一交易日的整批。
- 回歸:`test_fills_keep_futures_night_session_across_midnight`(`:1002`)、
  `test_fills_friday_night_survive_weekend_to_monday`(`:1020`)仍綠 —— 這兩條是夜盤錨定的守門。
**Rollback**:revert;`event_date` 為 optional,舊資料不受影響。
**工作量**:M

### 步驟 4 —— log 搬出 `store._lock`(F-05)
**做什麼**:`_apply_fill_locked` / `set_positions` 的四處 `logger.*` 改成
「鎖內收集 → 鎖外印」。
**為什麼排這裡**:三行的事,而且它是步驟 5 的前置(縮小 event loop 被卡住的面)。
**量測判準**:
- `pytest tests/capital -q` 全綠(現有 caplog 測試 `:372` / `:394` 仍能抓到那些 log);
- micro-bench:`set_positions`(N=63,M=5,含一筆重套)持鎖時間 ≤ 0.05 ms(修前含 log ≈ 0.056 ms);
- 靜態判準:`grep -n "logger\." copycat/capital/store.py` 的每一行,
  往上找最近的 `with self._lock` 應為 0 行命中。
**Rollback**:revert。
**工作量**:S

### 步驟 5 —— log 移出熱路徑:`QueueHandler` + `QueueListener`(F-04)
**做什麼**:`server/__main__.py` 的 `basicConfig` 改成
root logger 只掛 `QueueHandler(queue.SimpleQueue())`,
`QueueListener` 執行緒掛既有的 `StreamHandler(_Tee(...))`。
stdlib,**零新依賴**。
**為什麼排這裡**:它同時解掉 FM-04 與 FM-05 的放大路徑,但它動的是全 server 的 logging,
所以排在 capital 內部的修正之後。
**量測判準**:
- micro-bench:`logger.info` 一行 p50 由 **12.5 µs** 降到 **< 2 µs**(QueueHandler 只做 `put`);
- 真環境:啟動後在 console **滑鼠選取一段文字 30 秒**,期間
  `curl -s -w "%{time_total}\n" localhost:8721/api/capital/positions` 應仍 < 50 ms,
  且 `grep "Capital reply"` 在放開後**一次補齊**(修前:整條 COM 執行緒停)。
  **這是唯一能驗 FM-04 的判準,必須在非交易時段做。**
- 回歸:log 檔內容與 console 內容逐行相同(`diff <(tail -200 logs/…) …`);
  crash 時最後幾行仍落盤(`QueueListener` 要在 atexit 前 `stop()`)。
**Rollback**:revert(logging 設定單點)。
**工作量**:M

### 步驟 6 —— `_cmd_q` 命令加 TTL(補 FM-04 的另一半)
**做什麼**:`_Cmd` 加 `deadline: float`;`_run` 取出時 `if monotonic() > cmd.deadline: _settle(fut, exc=TimeoutError)` 直接丟棄不送 COM。
**為什麼排這裡**:上一輪已列(無 TTL 的逾時命令會遲送),步驟 5 之後這條路變罕見但不會消失。
**量測判準**:
- 新測:FakeCom 的寫入 fn 阻塞 12 s,斷言 `_execute_write` 逾時後
  **`FakeCom.send_stock_order` 的呼叫次數維持 0**;修前為 1。
- 審計判準:`data/audit/capital-*.jsonl` 出現 `result.message == "結果未知,勿重送"` 的列之後,
  **不得**再出現同 req 的 late 行。
**Rollback**:revert;TTL 設成 `inf` 即回舊行為。
**工作量**:S

### 步驟 7 —— `Position` 改 `frozen=True`(F-09)
**做什麼**:`models.Position` 加 `frozen=True`;把 `_on_profit_complete` 的六處就地寫改成
`dataclasses.replace` 重建 pending 列;`set_positions` 的 carry-over 五行改成 replace(或直接刪 —— 它們在唯一例外路徑上是自我賦值)。
**為什麼排這裡**:它是預防性的,而且會讓 pyright 一次把所有就地寫點抓出來 —— **順序上必須在行為修正之後**,否則兩種改動混在一起 review 不動。
**量測判準**:
- `pyright` 零新錯;`pytest -q` 全綠;
- 靜態判準:`grep -n "p\.\(avg_price\|avg_source\|pnl_base\|pnl_cost\)\s*=" copycat/capital/*.py` 應為 0 行;
- prod:重啟後 `curl /api/capital/positions` 的**證券**列 `avg_source` 非 null(CLAUDE.md §4 的紅燈判準)。
**Rollback**:revert。
**工作量**:M

### 步驟 8 —— 改價 / 改量 / 退單的真實回報實錄(F-03 / FM-06)
**做什麼**:非交易時段或盤中以**最小量 + 遠離市價的限價單**,跑
「送出 → 改價 → 改量 → 刪單」全鏈,把四則 `OnNewData` 原始字串收進
`tests/capital/rows.py` 當 fixture,並補 `test_reply.py` 的逐欄斷言。
**為什麼排這裡**:它需要 user 親自在 prod 操作(我不能下單),且不擋前面任何一步。
**量測判準**:
- `grep -h "Capital reply: seq" logs/server-*.log | grep -o "status=[^ ]*" | sort | uniq -c`
  出現 `改價` / `改量` / `改價改量` 各 ≥ 1(現為 0);
- 新 fixture 餵進 `parse_onnewdata` 後,`after_qty`(idx22)、`price`(idx11)、`qty`(idx20)
  三欄的值與畫面 / 群益 APP 逐字相符。
**Rollback**:純新增測試,無 rollback 需求。
**工作量**:S(操作)+ M(fixture 與測試)

### 步驟 9 —— 事件指紋去重(F-01 正解 / F-06 / FM-12)
**做什麼**:`_Agg` 加 `seen: set[tuple]`(指紋 = `(idx2, idx20, idx22, idx24, idx11)` 或整列 hash),
`apply_reply` 在指紋重複時直接 return;`clear()` 隨之變成可選而非必要。
之後 `_handle_reply_disconnect` 才能安全接 `connect_reply` 重試。
**為什麼排最後**:它改變的是狀態機的**核心不變量**(非冪等 → 冪等),
需要步驟 1–2 的旗標與測試先在位。做完它,步驟 2 的 quiet 窗可以退役。
**量測判準**:
- 新測:同一則 `bstr_data` 連餵 3 次,`filled_qty` / `positions()` 與餵 1 次相同;
- 突變體:把去重那一行拿掉,至少 3 條測試轉紅;
- prod:重啟後 `grep "重複回報事件已忽略"` 的筆數 ≈ backlog 與即時的重疊量(理想 0;
  若非 0 表示群益真的會重送,那本身就是一個新發現);
- 回歸:`copycat validate` 不受影響(它不碰 capital)。
**Rollback**:revert;去重開關可用 env 關掉。
**工作量**:L

### 步驟 10 —— WS payload 直接帶部位(F-10)
**做什麼**:`capital_position` 事件的 `data` 改成帶完整 `positions` 陣列
(M ≤ 50 列 × 1.9 µs asdict ≈ 0.1 ms);前端 `useCapital` 對該事件直接
`queryClient.setQueryData` 而非 `invalidateQueries`,砍掉 200 ms debounce 與那趟 HTTP。
**為什麼排最後**:它是純效能,而且動的是 CLAUDE.md §4 沒有但實質上是跨檔契約的東西(wire 形狀)。
**量測判準**:
- 前端:DevTools Network 在一筆成交後,`/api/capital/positions` 的請求數由 1 降到 0;
- 端到端:在 `_handle_reply` 的 `_emit` 前打一個 `performance.now()` 對照的時戳進 payload,
  前端收到時算差 —— 目標 **p50 < 30 ms**(現況推估 215–260 ms);
- 回歸:`tests/capital/test_fill_latency.py` 的兩種推播仍分得出來(它讀 `source`)。
**Rollback**:revert 兩邊(**這是前後端同版部署**,參照 CLAUDE.md §4 的規則)。
**工作量**:M

---

## 8. 工具選型

| 工具 | 用在哪 | 為什麼 | 取捨 | 結論 |
|---|---|---|---|---|
| `logging.handlers.QueueHandler` / `QueueListener`(stdlib) | `server/__main__.py` | 步驟 5;把 log 從 COM 執行緒與 `store._lock` 熱路徑移走,同時解掉 console 阻塞的傳導 | 崩潰時 queue 內未寫的行會丟 → `atexit` 要 `stop()`;`_Tee` 的 per-write flush 語意搬到 listener 上 | **建議導入** |
| `dataclasses(frozen=True)` + pyright | `capital/models.py::Position` | 步驟 7;把 F-09 的「靠恰好成立的不變量」變成型別檢查得出來 | `_on_profit_complete` 六處就地寫要改 replace(pending 列,無效能顧慮) | **建議導入** |
| `queue.SimpleQueue` 取代 `queue.Queue`(`_cmd_q`) | `client.py:210` | `SimpleQueue` 無條件變數、`put` 更快且 reentrant-safe | `Queue` 的 `task_done` / `join` 沒被用到;但 `SimpleQueue` 的 `get(timeout=)` 語意相同 | **有條件導入**(收益 < 1 µs/次,只在順手做步驟 6 時一起) |
| `time.perf_counter_ns` + 一個 ring buffer 的內建 latency 直方圖 | `client._handle_reply` / `_execute_write` | 上一輪 F-10 已提;本輪把**要量什麼**釘死了:①送單→首則回報 ②成交→部位落地 ③loop hop | 需要一支 `/api/capital/metrics`;`/api/health` 刻意不含(比照 `window_dropped` 慣例) | **建議導入**(步驟 1 順手) |
| `orjson` / `msgspec` | 序列化 | `asdict(Position)` = 1.9 µs、`parse_onnewdata` = 3.2 µs、prod M ≤ 50 | 純 CSV split 與 dataclass,不是 JSON 瓶頸;且 FastAPI 已走 pydantic-core Rust 路徑 | **不建議**(形狀不對,與上一輪駁回的結論一致) |
| `numpy` / `polars` | 狀態機 | `apply_reply` 17–21 µs、增量式、穩態零配置 | 同上一輪駁回 | **不建議** |
| SQLite(WAL)當委託 / 成交的持久層 | 取代 `_orders` 記憶體聚合 | 能解「重啟恢復」與「跨日成長」兩題 | 違反 CLAUDE.md §5「沒有 DB」的既定架構決策;而 prod N=24–63、重啟每天一次,問題不在儲存而在**重播與即時不可分辨** | **不建議**(先做步驟 9 的去重,那才是根因) |
| `py-spy`(已裝) | prod 取樣 | 驗步驟 5 之後 COM 執行緒不再卡在 `write` | 盤中 attach 有風險,盤後做 | **有條件導入** |

---

## 9. Open questions(需要 prod 或 user 回答)

1. **群益 seq 會不會年度 rollover?** 30 天實測單調遞增、零重用(F-11),但觀測窗不含跨年。
   若 user 能問到群益,`note_price_type` 那 60 行綁定邏輯可以整段刪掉。
2. **`U`(改量)可以減到 0 嗎?** 決定 FM-07 是否可達。群益文件或一次實驗即可。
3. **無券賣量 > 持股時,群益回報 idx6 給 `08` 還是 `00`?** 決定 FM-08 是否可達。
   CLAUDE.md §4 自承「有庫存時回 08 還是 00 沒有實錄」。
4. **`OnDisconnect` 在 prod 從沒發生過(30 天 0 次)——是真的不會斷,還是回呼沒接上?**
   `com.py:273` 的註解說「只做偵測+通知降級」,但零樣本讓人分不出「沒斷」與「偵測壞了」。
   建議:在非交易時段把群益 APP 關掉一次,看 `grep "回報連線中斷"` 有沒有那一行。
5. **`OnOpenInterest` 的欄序至今 prod 未實測**(`balance.py:114-119` 自承「依群益手冊慣例假定」)。
   期貨部位的 `qty` / `avg_price` 全靠這個假定。有期貨部位時應先對一次。
6. **Windows console QuickEdit 是否真的會阻塞這個 server?** FM-04 的機制我沒能在此環境驗證。
   步驟 5 的判準就是實驗本身(非交易時段做)。
7. **樂觀套用的「200 ms debounce 吃掉 99.9% 收益」user 在意嗎?**
   若「成交即見」不是需求(現況 p50 2 s 的券商真相已經夠用),步驟 10 可以整個不做。

---

## 附錄:本輪產生的量測腳本(留在本目錄)

| 檔 | 用途 |
|---|---|
| `bench_d3.py` | `apply_reply` / `orders()` / `set_positions` / `positions()` / `logger.info` 的檔位對照 |
| `analyze_replay.py` | 64 份 log 的 backlog 重播窗 × 幽靈套用筆數 × 自癒時間 |
| `analyze2.py` | 未樂觀套用事件的 seed 前 / 後分帳 |
| `reply_latency.py` | 審計 post → 首則回報到達的分布(n=366) |
| `repro_phantom.py` | F-01 的確定性重現 |
