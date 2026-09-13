# D5 — 下單:安全閘與風控(量化系統缺口)

掃描對象:`copycat/capital/safety.py`(全 112 行讀完)、`copycat/capital/client.py`(全 1216 行讀完)、
`copycat/capital/factory.py`、`copycat/capital/close.py`、`copycat/capital/com.py`、`copycat/capital/mapping.py`、
`copycat/server/capital_api.py`(全 451 行)、`copycat/server/audit.py`(全 38 行)、
前端 `lib/flash-arm.ts` / `lib/flash-send.ts` / `components/stock/PriceLadder.tsx` / `hooks/useCapital.ts`。

實測素材:`data/audit/capital-*.jsonl` **22 個交易日 / 1,075 行**(2026-07-29 ~ 2026-09-11,prod 1,072 行)。
Benchmark 腳本落在本目錄 `bench_gate.py` / `audit_stats.py` / `audit_dup.py` / `audit_dup2.py`。

---

## 0. 一句話結論

**這套系統唯一真正在擋錢的閘,不在 copycat 裡,在群益。**
22 個交易日 1,075 筆審計中,copycat 自家安全閘(`safety.py`)的擋單次數是 **0**
(唯一 `blocked` 是 `capital_not_ready` ×3,那是「還沒登入」不是風控);
同期券商端的「網路單交易額度 249 萬」擋掉 **30 筆**。
而風控閘本身的成本實測 **< 12 µs/筆委託**,佔端到端 70 ms 的 **0.016%** ——
**「加風控會讓下單變慢」在這個系統裡是一個可以直接用數字否決的說法。**

---

## 1. 現況地圖:一張單要通過幾道閘

```
瀏覽器
 └ PriceLadder.clickPrice / marketOrder          ← 閘 ①②③(純前端,可繞)
    ① KIND_TRAITS[kind].buyLocked      無券空單不可買
    ② arm.state.armed                  未武裝 → 只顯示提示,不送
    ③ lastClick 500 ms 防抖            **同格同側**才擋(key = `${side}:${priceMilli}`)
 └ useSubmitStock → fetch POST /api/capital/order/stock   (無 AbortSignal / 無 retry)
                     │
uvicorn (127.0.0.1:8721,無 auth,CORS 只管瀏覽器跨源)
 └ capital_api.capital_order_stock                ← 閘 ④(wire 型別)
    ④ pydantic StockOrderBody          buy_sell / price_type / tif / trade_kind 值域
       (期貨路徑另有 ⑤⑥:_stkfut_gates → PRODUCT_NOT_ALLOWED / BAD_TICK)
 └ CapitalClient.submit_stock_order
    └ check_stock_order(req, self._safety)         ← 閘 ⑦⑧⑨⑩(safety.py,唯一的後端風控)
       ⑦ order_enabled 總開關          `CAPITAL_ORDER_ENABLED != "true"` → order_disabled
       ⑧ _bad_price                    NaN / inf / ≤0 顯式擋
       ⑨ daytrade_sell + buy 組合擋
       ⑩ _check_qty_amount             qty>0;max_qty;max_amount(price×qty×1000)
    └ _execute_write
       閘不過 → await to_thread(_audit blocked 行) → raise CapitalGateBlockedError → 403
       status ∉ {ok, degraded} → blocked 行 → 503
       前置審計 await to_thread(append_audit)      ← 失敗即 500,錢沒動
       _cmd_q.put((com_call, fut))                 ← **無上界、無 TTL**
       await wait_for(shield(fut), 10 s)
                     │
capital-com 執行緒 (_run)
 └ _pump_once(): pump → 3 collectors.poll → _maybe_query_balance → _poll_pending
 └ cmd = _cmd_q.get(0.05) → **result = fn() 直接執行,不檢查 fut 是否已被放棄**
 └ com.send_stock_order → SKCOM SendStockOrder(user, bAsync=0, order)   ← 98.5% 的時間在這
                     │
群益後台                                            ← 閘 ⑪(真正在擋的那道)
    ⑪ 網路單交易額度 249 萬 / 融資額度 / 集保庫存 / 沖銷股數 / 風險預告書簽署
```

### 1.1 閘逐條:擋什麼、在哪一層、繞得過嗎

| # | 閘 | 層 | 擋什麼 | 繞得過嗎 | 實測觸發次數(22 日) |
|---|---|---|---|---|---|
| ① | `KIND_TRAITS.buyLocked` | 前端元件 | 無券空單按「買」 | ✅ curl 繞過,但後端 ⑨ 補上 | — |
| ② | `arm.state.armed` | 前端 reducer | 未武裝點價不送單 | ✅ **完全前端**,curl 直打 API 無此概念 | — |
| ③ | 500 ms 同格防抖 | 前端 ref | 同一格同一側 500 ms 內第二下 | ✅ 換一格 / 換一側 / 隔 501 ms 就穿過 | 見 §3 |
| ④ | pydantic body | route | 值域外的字串 → 422 | ❌ | — |
| ⑤ | `_stkfut_gates` 產品單位 | route | ETF 期貨 / 除權息調整腿 → 400 `PRODUCT_NOT_ALLOWED` | ❌ | 0 |
| ⑥ | `_require_legal_tick` | route | 個股期限價非法檔位 → 400 `BAD_TICK` | ❌ | 0 |
| ⑦ | `check_master` | safety | `CAPITAL_ORDER_ENABLED != "true"` | ❌(但**前端零讀者**,見 F-04) | **0** |
| ⑧ | `_bad_price` | safety | NaN / inf / ≤0 | ❌ | 0 |
| ⑨ | `daytrade_sell + buy` | safety | 無券空單買進 | ❌ | 0 |
| ⑩ | `max_qty` / `max_amount` | safety | 單筆張數 / 單筆名目 | ❌,但**預設 None = 不限** | **0** |
| ⑪ | 群益額度 / 庫存 / 憑證 | 券商 | 249 萬網路單額度等 | ❌ | **52**(其中 249 萬 **30** 次) |
| ⑫ | `_close_dup_reason` | client | **只有平倉**:10 s in-flight + 同向活躍委託 | ❌,但只蓋平倉 | 0(平倉全期只有 2 筆) |

**「二次確認」(CLAUDE.md §7 閘二)的實況**:
`OrderPanel.tsx:52` 的 `confirming` state 是唯一的確認彈窗,對應 `source="panel"`。
22 日 1,075 行審計中 `source` 分布:

```
flash-locked 496   flash 345   panel 2   (cancel 不帶 source → 232)
```

**843 筆送單裡,走過二次確認的是 2 筆(0.24%)。** 其餘全部走閃電梯的「武裝 → 點價直送」路徑,
那是 `flash-arm.ts` 檔頭自己寫明的「唯一繞過二次確認的路徑」。這不是 bug —— 是刻意的 opt-in 設計,
補償手段是「解除路徑寬於進入路徑」(斷線 / 連 3 敗 / Esc / 換標的 / 閒置 5 分鐘)。
但要注意兩件事:
1. **武裝狀態完全在前端**,後端不知道這張單有沒有經過確認。
2. `source` 是**自我申報**欄位(`str`,後端不驗)。審計上「這張單是不是在鎖定態按出去的」
   只是前端誠實填的一行字。

---

## 2. 端到端延遲預算(送單寫入路徑)

量測基準:Python 3.13.13 / Windows 11 / 專案 .venv。閘與序列化以 `perf_counter_ns` 跑 200k 次取平均;
審計以 600 次取分位;端到端以 22 日審計的 pre/post 秒解析度配對回推。

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | pydantic body 驗證 + dataclass 組裝 | `capital_api.py:294-307` | ~10–30 µs | 推估(pydantic-core Rust) | 未單獨量;佔比可忽略 |
| 2 | `_stkfut_gates`(僅期貨路徑) | `capital_api.py:162-177` | **4.31 µs** | 實測 | `lookup_product` 4.10 + tick 閘 0.21 |
| 3 | `check_stock_order`(限額全開) | `safety.py:60-67` | **0.427 µs** | 實測 | 兩閘都設時 0.498 µs |
| 3' | `check_future_order`(乘數 200) | `safety.py:70-75` | **0.875 µs** | 實測 | |
| 3" | `check_master` 單獨 | `safety.py:35-37` | **0.273 µs** | 實測 | cancel / decrease 走這條 |
| 4 | `dataclasses.asdict(req)` + `json.dumps` | `client.py:335-342` + `audit.py:30` | **4.35 µs** | 實測 | asdict 1.81 + dumps 2.54 |
| 5 | **前置審計 `to_thread(append_audit)`** | `client.py:885` | **272 µs (p50) / 447 µs (p99) / 9.06 ms (max)** | 實測 | 每次 `mkdir` + `open` + `write` + `flush` + `close`;**共享 20-worker executor**,池滿時**無上界** |
| 6 | `_cmd_q.put` → COM 執行緒取件 | `client.py:887` → `:811` | < 1 ms(閒置時);**上界 = 一輪 `_pump_once`** | 推估 | `queue.get(timeout=0.05)` 被 put 立即喚醒;但 COM 執行緒若正在 `pump()` 處理成交回報 backlog 或 `get_real_balance` 就得排隊 |
| 6' | `_pump_once` 例外分支 | `client.py:793` | **+1,000 ms** | 程式碼 | `time.sleep(1.0)` 佔住唯一的送單執行緒 |
| 7 | **`SendStockOrder` + COM pump** | `com.py:154` | **≈ 69 ms (mean) / p99 ≈ 2 s** | 實測回推(見下) | 不可中斷、`bAsyncOrder=0` 同步 |
| 8 | `return_code_message(code)` | `client.py:910` → `com.py:242` | 未量(跨 apartment COM 呼叫) | unmeasurable | **在 event loop 執行緒上直呼 COM** |
| 9 | 後置審計 `to_thread(append_audit)` | `client.py:917` | **272 µs (p50)** 同 #5 | 實測 | 擋在 HTTP 回應之前 |
| 10 | `_note_price_type`(交易日曆推算) | `client.py:955-976` | ~50–200 µs(首次載入 JSON 更久) | 推估 | 回應之後才跑,不在 critical path 上 |
| 11 | **(不存在)組合層風控閘** | — | **11.35 µs** | 實測(合成) | 63 部位總曝險 + 單標的曝險 + 未實現損益 + 10 秒頻率窗 + 漲跌停帶 + 距現價 5% |

**加總(現股限價單,健康路徑)**
純 Python 段 ≈ 0.43 + 4.35 + 272 + 272 ≈ **549 µs**,其中 **99.1% 是兩次審計檔案 IO**。
`SendStockOrder` ≈ **69 ms**。**閘的總成本 0.43 µs = 端到端的 0.0006%。**

**端到端的實測回推(22 日 536 組 pre/post 配對,秒解析度)**

```
mean = 0.090 s   p50 = 0 s   p90 = 0 s   p99 = 1 s   max = 4 s
分布:0 s ×494   1 s ×39   2 s ×1   3 s ×1   4 s ×1
```
秒解析度只能給上界。`mean 0.090 s` 是「至少有 39/536 筆跨過整秒界」的下界估計;
上一輪報的 mean ≈ 70 ms 與此一致。**max = 4 s** 出現過一次,離 10 s timeout 只差 6 秒。

**這張表最重要的一行是 #11**:整套量化風控(六道閘)加起來 11.35 µs,
是一次 `append_audit` 的 **4.2%**,是 `SendStockOrder` 的 **0.016%**。
風控缺席不是效能取捨的結果,只是還沒寫。

---

## 3. 實測:22 個交易日的審計檔說了什麼

### 3.1 送單量級 —— 「一天個位數」這個前提是錯的

```
每日新單數(前置行,action=order,未被 blocked):
20260813:19  20260814:28  20260817: 8  20260818:13  20260819:10  20260820:16
20260821:56  20260824:21  20260825:27  20260826:17  20260827:16  20260828:16
20260831:16  20260901:21  20260902:11  20260904:24  20260907:20  20260908:16
20260909:22  20260910:29  20260911:13
n=22 日   min=3   median=17   max=56   mean=19.2
每日刪單 median=3,max=21
```
**median 17 筆 / 日、最高 56 筆 / 日**。不是個位數。10 秒滑動窗最密達 **6 筆新單**。
任何「因為量很小所以不需要頻率閘」的推論,前提不成立。

### 3.2 唯一在擋錢的是券商

```
群益拒單全表(code != 0,共 52 筆):
  x30  code=999  網路單交易額度超過限定額度    249萬!
  x7   code=1068 SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO
  x4   code=999  此投資人尚未簽署創新版風險預告書,不可委託!
  x4   code=999  集保庫存剩 0 股,不得賣出或匯撥交割
  x3   code=400  DB查詢失敗 ... TMFI6無法轉換商品ID
  x1   code=999  可沖銷股數 資買 0 股; 集買 0 股
  x1   code=999  此人融資已滿!欲借 57萬;額度 90萬
  x2   code=960  此委託不可做刪改 / 查無委託資料
copycat 自家 blocked:capital_not_ready ×3。max_qty / max_amount / order_disabled = 0 次。
```

**249 萬額度拒單的時間分布**(節錄)顯示它會**連續打擊**:

```
2026-09-07 11:54:51  6488 buy @969.0
2026-09-07 11:54:56  6488 buy @971.0
2026-09-07 11:55:01  7795 buy @533.0
2026-09-07 11:55:05  7795 buy @533.0
2026-09-07 11:55:14  3055 buy @134.0
2026-09-09 09:47:18 / 09:47:23 / 09:47:30  3441 buy(三連拒)
```

這說明:**帳戶級曝險上限實際上存在,只是它在券商那裡,而且 copycat 完全不知道自己離它多遠。**
使用者的體驗是「按下去、紅字、再按、再紅字」。把 249 萬這個數字搬進 `safety.py` 當本地閘,
可以在**送出之前**就告訴使用者「這筆會爆額度」,而不是花一次往返去問券商。

送單規模(sec 名目 = price × qty × 1000,n=419):
```
min = 16,950   p50 = 176,500   p90 = 617,000   max = 1,260,000
qty 分布:1 張 ×410   3 張 ×9   5 張 ×3
```
單筆最大 126 萬,**已經是 249 萬額度的一半**。`CAPITAL_MAX_AMOUNT` 若設在 130 萬會開始 bind,
現在設的是不限。

### 3.3 84 組疑似重複新單 —— 而且在帳上不可分辨

掃描規則:同 `(stock_no, buy_sell, price, qty, trade_kind)` 的兩筆前置行間隔 ≤ 60 s。

```
合計 84 組;其中 Δ ≤ 1 s 的 44 組。
最密的實錄:
  2026-08-20 09:59:45 / :47 / :48 / :48   5608 買 @16.95 margin  (四連發,兩筆同秒)
  2026-08-21 09:18:47 / :48 / :49 / :50   5608 賣 @18.10 margin  (四連發)
  2026-08-21 09:38:20 / :28 / :35 / :35   6207 賣 @105.5 cash
  2026-08-25 10:40:31 / :32 / :33 / :36 / :37  5608 賣 @18.60 cash (五連發)
  2026-09-09 10:30:03/08/13/17/21/22      6949 市價賣 ×6,19 秒內,seq 各不相同
  2026-09-11 10:33:42(同秒兩筆)          6949 賣 @53.4
```
每一組都拿到**不同的群益委託序號** → 每一張都真的進了市場。

**關鍵是:這些到底是使用者刻意疊單,還是雙擊 / 手殘 / 重送?從審計檔上分辨不出來。**
`_record()`(`client.py:335-342`)只有 `ts / env / action / req / blocked / result`,
**沒有 request_id**,而且 `ts` 是 `timespec="seconds"` —— 同秒兩筆連先後都排不出來。
這正是 F-01 的核心:不是「會不會重複送」,是「重複送了也查不出來」。

### 3.4 順帶勘誤:`bstrPrice="0"` 已經被 prod 實證了

`mapping.py:248-253` 的註解寫「字面 "0"(非 "0.00")是**推定未實測**」。審計檔說不是:

```
2026-08-24 09:02:28 ~ 09:10:19  市價單 ×7 全數 1068 拒單(帶估價的舊版)
2026-08-25 09:02:26  5608 市價買  ok=True  SK_SUCCESS 2313207905275   ← "0" 生效
之後 12 筆市價單全部 ok=True(含 2026-09-09 六連發市價賣)
```
**"0" 字面值已通過 prod 實測 13 筆**,註解該改口。(文件層,零行為;但留著會讓下一個人重跑一次安全首單。)

---

## 4. Findings

嚴重度依「對一個要下實單的系統」判定,不是依發生頻率。

---

### F-01 【critical / risk-control】新單零冪等防護,且審計時戳只有秒 —— 重複送單在帳上不可分辨

**位置** `client.py:335-342`(`_record`)、`client.py:865-922`(`_execute_write`)、
`capital_api.py:64-73`(`StockOrderBody`)、`client.py:1122-1142`(唯一的去重,只蓋平倉)

```python
# client.py:335 —— 審計行全欄,沒有 request_id
return {
    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),   # ← 秒解析度
    "env": self._env, "action": action,
    "req": dataclasses.asdict(req), "blocked": blocked,
    "result": dataclasses.asdict(result) if result is not None else None,
}
```
```python
# client.py:884-887 —— 送單路徑上沒有任何「這張單我送過了嗎」的查詢
await asyncio.to_thread(self._audit, self._record(action, req))
fut = self._loop.create_future()
self._cmd_q.put((com_call, fut))
```

**實測**:22 日 84 組疑似重複(44 組 Δ≤1s),3 次同秒兩筆。全部拿到不同 seq_no。

**為什麼平倉有、新單沒有(不對稱的成因)**
`_close_dup_reason` 的 docstring(`client.py:1123-1126`)自己寫明了動機:
> 部位快取要等成交回報→debounce→重查回來才更新,窗口內(數秒)第二次平倉仍看得到原始全量持倉、
> 照樣過量閘 → **兩張全量反向單**。

也就是說,平倉的去重是為了修**一個具體的、會造成反向超額部位的 bug**(平倉量取自 `pos.qty`,
而 `pos.qty` 有數秒的更新延遲),不是為了「防重複下單」這個一般性目標。
新單的量由使用者自己填,沒有這個放大效應 → 當時沒人覺得需要。
**這個理由在人工下單時勉強成立,在自動下單時完全不成立。**

**修法(三處)**
1. `capital_api.py:64` `StockOrderBody` / `:75` `FutureOrderBody` / `:103` `PositionCloseBody`
   各加 `client_order_id: str | None = None`(選配欄,舊前端不送 = 舊行為,不破相容)。
2. 前端 `PriceLadder.clickPrice` / `marketOrder` / `FuturesLadder` / `StkfutLadder` 六個送單點
   在 `settleFlashSend` 之前 `crypto.randomUUID()`。**收在 `lib/flash-send.ts` 一支
   `newClientOrderId()`** —— 六處各寫一次 `randomUUID()` 的失效樣態是其中一處忘了,
   而審計檔上看起來只是「少了幾筆有 id 的單」,零訊號(與 `flashSource` 同一條理由)。
3. `client.py` 新增 `self._seen_ids: dict[str, OrderResult]`(當日;`_today_ymd()` 換日清)。
   `_execute_write` 開頭:`if req.client_order_id in self._seen_ids: 審計一行
   action="order_replay" + 回上次結果`。**在 gate 之後、前置審計之前**(重放不該再過一次金額閘,
   否則「額度剛好被自己第一次送單吃掉」會讓重放拿到不一致的答案)。
4. `_record` 的 `ts` 改 `timespec="milliseconds"`。**這會動到離線讀者** —— 需確認
   `Documents\copycat-trading-review` 那批對帳腳本有沒有逐字 parse `ts` 長度(見 §7 Open questions)。

**額外**:同時加一道「無 id 時的保守窗」—— 同 `(action, req)` 在 **2 秒**內第二次出現就
回 `409 DUPLICATE_ORDER` 並要求帶 id 才放行。這會擋掉 44 組 Δ≤1s 中的絕大多數;
真要疊單的人帶 id 就能過(而且帳上分得出來)。門檻要 user 拍板 —— 實測分布顯示
2 s 會擋到一些 Δ=2s 的,1 s 只擋得到一半。

---

### F-02 【critical / risk-control】逾時的寫入命令沒有 TTL,10 秒前放棄的單會在 COM 恢復後送進市場

**位置** `client.py:886-898`(放棄端)、`client.py:808-826`(執行端)

```python
# client.py:886 —— 放棄端
fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
self._cmd_q.put((com_call, fut))
try:
    message, code = await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)
except TimeoutError:
    result = OrderResult(ok=False, code=-1, message="結果未知,勿重送", seq_no=None)
    ...
    return result          # ← 命令仍在 _cmd_q 裡,沒有任何標記
```
```python
# client.py:810-820 —— 執行端
try:
    cmd = self._cmd_q.get(timeout=0.05)
except queue.Empty:
    continue
if cmd is None: break
fn, fut = cmd
...
result = fn()              # ← 零檢查:不看 fut 狀態、不看入列時刻
```

`asyncio.shield(fut)` 的語意是「`wait_for` 取消的是 shield 外殼,不是 `fut`」——
所以逾時後 `fut` 既沒 cancel 也沒 done,**連 `if fut.done(): continue` 這種防禦都救不了**。
`_cmd_q` 是裸 `queue.Queue()`(`client.py:212`),**無上界**。

**失效劇本(結構上成立,22 日實測 0 次)**
1. 09:30:00 使用者送 6949 買 1 張 @58.7。COM 執行緒卡在前一筆 `SendStockOrder`。
2. 09:30:10 `wait_for` 逾時 → 回「結果未知,勿重送」→ 前端 `send_fail` + hint。
3. 使用者看到「結果未知」,盯了 30 秒委託列沒東西,判斷沒送出去 → 重送一張。
4. 09:30:45 COM 恢復,`_run` 從佇列取出**第 1 步那一筆**,照送。
5. 市場上有兩張。審計上兩行前置 + 一行「結果未知」+ 一行 `late=true`。

這裡有個尖銳的諷刺:`_WRITE_TIMEOUT_S` 的註解(`client.py:85-87`)說 timeout 的目的是
「不讓 HTTP 請求永久懸掛,那最容易誘發重送」—— 而放棄的命令沒 TTL,正好讓那次重送變成真的雙倍。

**修法**
```python
# client.py:168 附近
@dataclass
class _Cmd:
    fn: _ComCall
    fut: asyncio.Future[tuple[str, int]]
    deadline: float          # time.monotonic() + _WRITE_TIMEOUT_S
    action: str              # 審計用
    abandoned: bool = False  # 逾時端設 True(單一執行緒寫、單一執行緒讀,不需鎖)
```
```python
# client.py:887 —— put 時帶 deadline
cmd = _Cmd(com_call, fut, time.monotonic() + _WRITE_TIMEOUT_S, action)
if self._cmd_q.qsize() >= _CMD_Q_MAX:          # 新增上界,建議 32
    await self._audit_blocked(action, req, "cmd_queue_full")
    raise CapitalDownError("送單佇列已滿(群益端無回應)")
self._cmd_q.put(cmd)
```
```python
# client.py:816 —— 執行端 TTL 檢查
if cmd.abandoned or time.monotonic() > cmd.deadline:
    logger.warning("寫入命令逾期未執行,丟棄(action=%s,逾期 %.1f s)",
                   cmd.action, time.monotonic() - cmd.deadline)
    self._loop.call_soon_threadsafe(
        _settle, cmd.fut, None, RuntimeError("命令逾期,未送出"))
    continue
```
```python
# client.py:892 —— 逾時端標記
except TimeoutError:
    cmd.abandoned = True    # ← 關鍵
```

**丟棄後訊息要改口**:現在回「結果未知,勿重送」,TTL 落地後多出一個
**「確定未送出,可重送」**的狀態(命令在佇列裡被丟掉 = 一定沒到群益)。
這比「結果未知」好得多 —— 它把一個不可判定的狀態變成可判定的。
`OrderResult` 加一個 `dispatched: bool | None`(True=已出手 / False=確定未出手 / None=未知),
前端依它決定 hint 文案。**這是跨檔契約新增,要登記進 CLAUDE.md §4。**

---

### F-03 【critical / risk-control】沒有 runtime kill switch,而 `_safety` 是啟動時定型的 frozen 值

**位置** `factory.py:101-105`、`safety.py:16-20`、`client.py:210`

```python
# factory.py:101 —— 進程啟動時建一次
safety = SafetyConfig(
    order_enabled=(_getenv("CAPITAL_ORDER_ENABLED") or "").strip().lower() == "true",
    max_qty=..., max_amount=...,
)
```
grep `_safety` 全專案:`client.py` 內 7 處**全是讀**,零寫入路徑。

**唯一的停止手段是關 server,而關機預算是 83 秒**(`shutdown_budget.run_grace_secs()`,
CLAUDE.md §4 有這條契約)。對一個下實單的系統,「緊急停止要 83 秒」是不可接受的。
現在人工下單時這件事被「使用者的手」代償了;接上自動下單就沒有了。

**修法(最小改動,約 30 行)**
1. `client.py` 加 `self._halted: bool = False` + `halt(reason) / resume()`。
2. **關鍵細節**:`submit_stock_order` 的 gate 是在**呼叫 `_execute_write` 之前**就算好的
   (`client.py:984-986`,argument evaluation)。halt 旗標必須在 `_execute_write` **內部**再查一次:
   ```python
   # client.py:876 —— gate 檢查之前
   if self._halted and action != "cancel":     # 刪單是降風險,halt 下仍放行
       await self._audit_blocked(action, req, f"halted:{self._halt_reason}")
       raise CapitalGateBlockedError(f"已緊急停止:{self._halt_reason}")
   ```
   放在 `gate.allowed` 之前,審計 `blocked` 才記得到真原因(沿 `check_master` 的既有紀律)。
3. `capital_api.py` 加 `POST /api/capital/safety/halt` / `/resume`,
   `status_view()` 多回 `halted` / `halt_reason`。
4. **前端必須有讀者** —— 見 F-04,否則 kill switch 按下去畫面零變化。

**halt 的自動觸發源**(接自動下單前必須有至少一個):
- 單日虧損超限(資料現成,見 F-05);
- 連續 N 筆券商拒單(22 日實測有 249 萬額度連三拒的實錄);
- COM 執行緒 status 轉 `error`(現在只降 status,不擋新請求 —— `_execute_write:881` 會擋,
  但 `degraded` 放行,見 F-08)。

---

### F-04 【high / observability】`order_enabled` 在前端零讀者 —— 總開關關掉時畫面完全正常

**位置** `types.ts:74` 宣告了 `order_enabled?: boolean`,
grep `frontend/src` **只有 4 個測試 fixture 在用,零 production 讀者**。

```
src/components/capital/CapitalOrdersList.test.tsx:74      ← 測試
src/components/capital/CapitalPositionsList.test.tsx:64    ← 測試
src/components/OrderPanel.test.tsx:43                      ← 測試
src/components/rail/RightRail.test.tsx:112                 ← 測試
src/types.ts:74                                            ← 型別宣告
```

**症狀**:`CAPITAL_ORDER_ENABLED=false` 時,武裝鈕可按、點價可送、梯照畫,
每一下都拿 403 `ORDER_BLOCKED` + hint「order_disabled」。要按到**第 3 下**
`flash-arm.ts:88-93` 的 `FAIL_LIMIT=3` 才自動解除武裝。
使用者在盤中會以為是網路問題,而不是「總開關是關的」。

**這也是 F-03 的前置**:kill switch 如果沒有前端讀者,按下去就只是把 403 換一個 reason 字串。

**修法**:`RightRail` / `ArmRow` 讀 `useCapitalStatus().data?.order_enabled`,
false → 武裝鈕 `disabled` + title「下單總開關關閉」(沿 `armGate(wsOpen, blockedTitle)` 的
既有第二參數,零新 API)。halt 落地後同一個位置讀 `halted`。

---

### F-05 【high / quant-gap】單日虧損熔斷:資料**已經現成**,只差沒人算

任務問「需要即時損益 —— 現在拿得到嗎?」**拿得到,而且不需要新增任何外部呼叫。**

| 需要的量 | 現成來源 | 位置 |
|---|---|---|
| 未實現損益基底 | `Position.pnl_base`(群益損益試算[9],**含費稅息**) | `models.py:179` |
| 基底的報告市價 | `Position.pnl_base_price`(損益試算[5]) | `models.py:180` |
| 成本(% 分母) | `Position.pnl_cost`(損益試算[12]) | `models.py:181` |
| 當日逐筆成交 | `store.fills()` → `FillRecord(price, qty, buy_sell, unit)` | `store.py:293` |
| 當日淨進出 | `store._today_net_lots_locked(stock_no, kind)` | `store.py:300` |
| 現價 | `stock_engine.snapshot(code)` / WS 流 | `stock_engine.py:713` |

**前端已經在算了**:`lib/ladder-position.ts::positionEcon` 拿 `avg_source` / `today_qty` /
`pnl_base` / `pnl_base_price` 做平移,那是 CLAUDE.md §4 登記的契約。
**後端有全部輸入,卻沒有任何一處把它加總成「今天賺賠多少」。**

回查鏈每 60 s(或成交後 0.5 s debounce)刷新一次 `pnl_base`,精度對熔斷夠用。

**修法**:新增 `copycat/capital/risk.py`(純函式,零 IO,與 `safety.py` 同款可測性):
```python
@dataclass(frozen=True)
class PortfolioLimits:
    max_total_notional: float | None = None   # 總曝險(名目)
    max_symbol_notional: float | None = None  # 單一標的曝險
    max_daily_loss: float | None = None       # 單日虧損(未實現 + 已實現)
    max_orders_per_window: int | None = None
    order_window_secs: float = 10.0
    max_price_deviation: float | None = None  # 距現價比例

def day_pnl(positions, fills, marks) -> float: ...          # 純函式
def check_portfolio(req, *, positions, fills, marks,
                    recent_order_ts, limits) -> GateResult: ...
```
掛點 `client.py:876`(`_execute_write` 第一段,halt 之後、`gate.allowed` 之前)。
`recent_order_ts` = client 自己維護的 `collections.deque(maxlen=64)`。

**實測成本:11.35 µs/筆委託**(63 部位 + 40 筆時戳 + 漲跌停 + 距現價,全部六道)。
= 一次 `append_audit`(272 µs)的 4.2%,= `SendStockOrder`(69 ms)的 0.016%。

---

### F-06 【high / risk-control】價格合理性檢查:現股限價沒有任何「離現價多遠 / 超不超漲跌停」的閘

**位置** `safety.py:40-45`(`_bad_price` 只驗 `> 0` 且有限)、
`capital_api.py:140-149`(`_require_legal_tick` **只給個股期用**,現股路徑不經過)

現股限價單送 1000 元買一檔 100 元的股票,copycat 這邊**每一道閘都會過**:
- `_bad_price`:1000 > 0 ✅
- `max_qty`:預設不限 ✅
- `max_amount`:預設不限 ✅(設了 200 萬的話 1000×1×1000 = 100 萬,照樣過)
最後由交易所退件。這在人工下單是手滑,在自動下單是策略算錯一個小數點。

**資料同樣現成**:`live/stock_state.py:229-235` 的 `_meta_payload` 已經有
```python
"ref":   self.meta.ref_milli,     # 參考價
"upper": self.meta.upper_milli,   # 漲停
"lower": self.meta.lower_milli,   # 跌停
```
而 `copycat/market.py:49-70` 有 `limit_up_milli` / `limit_down_milli` 純函式。

**修法**
1. `stock_engine` 加一支淺存取 `price_band(code) -> tuple[int, int] | None`
   (回 `(lower_milli, upper_milli)`)。**不要用 `snapshot()`** —— 它會把當日數千筆 tick
   組成 dict 再整份丟掉,只為了兩個整數。
2. `capital_api.capital_order_stock` 取 `request.app.state.stock`,查 band,
   連同現價一起塞進 `PortfolioLimits` 的輸入。
3. **fail-open + WARNING**:非自選池的股號查不到 band,此時擋單會擋掉合法委託
   (使用者可能從別的入口下單)。留 `logger.warning("價格帶未知,跳過合理性閘: %s")`,
   自動下單模式(F-09)則改 fail-closed。

**距現價比例**的門檻要 user 拍板:鎖漲停追價時「距現價 7%」是正常的,
所以不能設 3%。建議以**漲跌停帶為硬閘**(必擋)+ **距現價比例為軟閘**(超過就要帶
`client_order_id` 或 `force=true` 才放行)。

---

### F-07 【high / risk-control】送單頻率零上限,而閃電梯是一個「按住就會連發」的介面

**位置** 全專案零 rate limit(grep `rate_limit|ratelimit|throttle` 在 `capital/` + `capital_api.py` 命中 0)。
唯一的節流是前端 `PriceLadder.tsx:281-288` 的 500 ms **同格同側**防抖。

```python
# PriceLadder.tsx:279 —— 防抖鍵只認「這一格 + 這一側」
const key = `${side}:${priceMilli}`;
if (lastClick.current?.key === key && now - lastClick.current.ts < CLICK_DEBOUNCE_MS) return;
```
換一格(價格跳一檔)、換一側、或隔 501 ms,全部穿過。

**實測**:10 秒滑動窗最密 **6 筆新單**;19 秒內 6 筆市價賣(2026-09-09 10:30:03~22)。

**修法**:`risk.py` 的 `check_portfolio` 內,以 `deque(maxlen=64)` 的 monotonic 時戳做窗:
```python
n = sum(1 for t in reversed(recent_order_ts) if now - t <= limits.order_window_secs)
if limits.max_orders_per_window is not None and n >= limits.max_orders_per_window:
    return GateResult(False, f"{limits.order_window_secs:.0f} 秒內已送 {n} 筆,超過上限")
```
成本已含在 11.35 µs 內。
**門檻建議 10 筆 / 10 秒** —— 實測歷史最密 6 筆,不會誤擋人工操作,但擋得住跑飛的迴圈。
**刪單不計入**(降風險操作),`action="cancel"` 跳過本閘。

---

### F-08 【high / risk-control】`degraded`(回報斷線)放行送單,而此時去重與金額閘同時失效

**位置** `client.py:880-883`

```python
# degraded(回報斷線)放行:送單通道獨立可用,且刪單/平倉是降風險操作
if self._status not in ("ok", "degraded") or self._loop is None:
```

上一輪(B10 F-13)已指出「單送出去但看不到」。這裡補一層**風控角度的連鎖**:
`store._orders` 只由 `OnNewData` 填(`client.py:402` `_handle_reply`),回報斷線後它**凍結**,
於是同一時刻:

| 依賴 store 的閘 | 斷線後的行為 | 訊號 |
|---|---|---|
| `_close_dup_reason` 的「同向活躍委託」掃描 | 掃不到任何新單 → **平倉防重送只剩 10 s in-flight 窗** | 無 |
| `_routing` 的 `market_of` 交叉驗證 | 回 `None` → **寬鬆放行**(`client.py:1043-1047` 明文) | 無 |
| `correct_price` 的 `remaining_shares` | 回 `None` → **金額閘整條跳過**(`safety.py:93-94`) | 無 |
| `_fut_multiplier` | 查無契約碼 → `multiplier=1` → **期貨金額閘鬆 50–200 倍** | WARNING ✅ |
| F-05 的單日虧損 / 曝險閘(未來) | 部位仍由回查鏈更新(**不依賴回報**)→ 仍有效 | — |

也就是說,**回報斷線讓「跨筆」的防護整批失效,而其中三條零訊號。**
`_handle_reply_disconnect`(`client.py:455-462`)只把 status 降 `degraded`。

**修法(分兩段,不要一次做完)**
1. **立刻可做**:`degraded` 期間把 `max_qty` / `max_amount` 強制收到一個保守值
   (例如各自的 1/2,或一個獨立的 `DEGRADED_MAX_AMOUNT`),並在 `OrderResult.message`
   前綴「回報停更,委託列表不會更新」。四行改動,零跨檔契約。
2. **後續**:degraded 下 client 自建 `source="local"` 佔位委託列(B10 F-13 的修法),
   讓三條掃描恢復。⚠ 會碰到 `store.py:10-12` 的「聚合非冪等」註記,要走 `/feat`。

---

### F-09 【high / quant-gap】自動下單的 blocker 清單(排優先序)

現況:`signal_hub.py` / `signal_policy.py` 對 `capital` 的 import 數 = **0**。
訊號與下單完全解耦,現在沒有任何自動下單路徑。**這是好事,不要急著接。**

要接訊號自動下單,按「不接就會出事」的順序:

| 序 | Blocker | 為什麼是硬阻塞 | 對應 finding |
|---|---|---|---|
| **P0** | **kill switch**(runtime halt + 前端可見) | 程式跑飛時唯一的停止手段現在是關 server(83 秒) | F-03 + F-04 |
| **P0** | **冪等鍵 + 去重窗** | 自動路徑的重試比人手快幾個數量級;現在重複送了連查都查不出來 | F-01 |
| **P0** | **送單頻率上限** | 一個寫錯的 while 迴圈 = 每秒數百張單 | F-07 |
| **P0** | **命令 TTL + 佇列上界** | 自動路徑不會「看到結果未知就停手」,它會繼續投遞 | F-02 |
| **P1** | **單日虧損熔斷** | 人工下單有「今天不順就收手」的人類判斷,自動沒有 | F-05 |
| **P1** | **帳戶級 / 單標的曝險上限** | 249 萬券商額度是唯一的天花板,而它是**拒單**不是**阻止**(已經打到券商了) | F-05 |
| **P1** | **價格合理性(漲跌停硬閘)** | 策略算錯小數點的後果在自動路徑是立即的 | F-06 |
| **P2** | **異常行情擋單**(緩撮 / 試撮窗 / 鎖停) | 試撮窗的「成交價」不是真成交;鎖停時市價單會排到漲停 | F-10 |
| **P2** | **degraded 下的行為定義** | 自動路徑在回報斷線時該停還是該續,現在沒有答案 | F-08 |
| **P2** | **審計 fsync + 崩潰恢復對帳** | 自動路徑的單量讓「事後對帳」從可選變必須 | F-11 |
| **P3** | 訊號 → 下單的 dry-run 影子期 | 沿用 spec #192 已經建立的影子模式紀律(jsonl 真相源 + 不推播) | — |

**P0 四項合計的實作量估計:S–M**(risk.py 新檔 ~150 行 + client.py ~40 行 + route 2 支 + 前端讀者 2 處)。
**風控閘的執行成本 11.35 µs,不構成任何效能理由推遲它。**

---

### F-10 【medium / risk-control】異常行情擋單:偵測已經有了,只是「只記錄不判定」

**位置** `stock_engine.py` 的 `_observe_trade_status`(B10 / Q1 已引,自承「只記錄不判定」)、
`live/signal_state.py` 的鎖停 latch、`live/stock_models.py` 的試撮窗歸一。

四種異常行情的現況:

| 情境 | 偵測有嗎 | 擋單嗎 | 後果 |
|---|---|---|---|
| 鎖漲停 / 鎖跌停 | ✅ `signal_state` 有 lock latch;TC4 第一檔會推「市價單佇列」價格 0 | ❌ | 鎖停時送市價 = 排進漲停佇列,成交價 = 漲停 |
| 緩撮(TradeStatus) | ✅ `_observe_trade_status` 有,UI 印「(緩)」 | ❌ | 緩撮期間的簿價不是連續競價的價 |
| 試撮窗(08:30–09:00 / 13:25–13:30) | ✅ `stock_models` 有試撮窗歸一 | ❌ | 試撮的「成交價」是模擬撮合價,拿它當市價單估價是錯的 |
| 跳空 | ❌ 沒有集中判定 | ❌ | — |

**修法**:`risk.py` 吃一個 `MarketCondition` 值物件(`locked_up / locked_down / slow_match /
pre_match / last_updated_ago_secs`),由 route 從 `stock_engine` 取。
**這是新的跨檔契約,要登記進 CLAUDE.md §4** —— 因為它會讓「引擎的市況判定」變成
「擋不擋單」的輸入,漂掉的症狀是擋單規則靜默失效。

**優先序放 P2 的理由**:這四項的門檻都需要交易語意的拍板(鎖停時要不要能追價?
user 的策略核心正是「跟鎖」,一律擋掉會把主要用例擋死),不是工程判斷。

---

### F-11 【medium-high / correctness】下單審計沒有 `fsync`,而 fsync 的邊際成本實測只有 65 µs

**位置** `server/audit.py:34-37`

```python
with open(path, "a", encoding="utf-8") as fh:
    fh.write(line + "\n")
    fh.flush()              # ← 只 flush 到 OS page cache,沒有 fsync
```

`flush()` 把資料交給 OS,**不保證落盤**。Windows 藍屏 / 斷電 / 強制關機時,
最後幾筆審計行會消失 —— 而這是「錢動了、事後必須查得到帳」且**不可重建**的唯一一份
(群益 `ConnectByID` 只重播**當日** backlog,跨日就沒了)。

**實測(600 / 300 次取分位,同一台機器)**

| 寫法 | p50 | p90 | max | 每筆委託(×2 次)|
|---|---|---|---|---|
| 現行:每次 mkdir+open+write+flush+close | **272.4 µs** | 352.9 µs | 9,059 µs | 545 µs |
| 現行 + `os.fsync` | 617.3 µs | 717.6 µs | 1,685 µs | 1,235 µs |
| **持久 handle + flush + fsync** | **337.2 µs** | 376.0 µs | 687.5 µs | **674 µs** |
| 持久 handle + flush(無 fsync) | **9.5 µs** | 10.3 µs | 84.5 µs | 19 µs |

**結論**:改成持久 handle 之後,**連 fsync 一起做也只比現在貴 65 µs**(337 vs 272),
而且 **max 從 9.06 ms 降到 0.69 ms**(開檔關檔的長尾消失)。
「加 fsync 會變慢」在這裡是假的 —— 真正貴的是每筆重開檔。

**修法**
1. `audit.py` 改成 module 級的 `dict[Path, TextIO]` handle 快取(跨日換檔時關舊開新)。
   `_audit_lock` 已經在,序列化語意不變。
2. 加 `os.fsync(fh.fileno())`。
3. **關機要關 handle** —— 掛進 `app.py` lifespan 的 capital 段(已經是最後一段)。
4. ⚠ `logs/` 的 tee 也開著同名目錄的檔,不要共用同一個快取。

**取捨**:持久 handle 讓「有沒有寫進去」的失敗時機從「每次 open」變成「第一次 open」。
open 失敗 → `AuditWriteError` → 拒單的既有語意要保住(第一筆就拒,而不是靜默降級)。

---

### F-12 【medium】`_on_late_result` 在 event loop 上同步跑 COM 呼叫 + 檔案 IO,而那正是 COM 生病的時候

**位置** `client.py:357-398`

```python
def _on_late_result(self, action, req, fut) -> None:
    ...
    message, code = fut.result()
    text = f"{self._com.return_code_message(code)} {message}".strip()   # ← 跨 apartment COM 呼叫
    ...
    self._note_price_type(...)      # ← 交易日曆推算(可能觸發 JSON 讀檔)
    record = self._record(action, req, result=result)
    record["late"] = True
    try:
        self._audit(record)          # ← 同步 append_audit,不走 to_thread
```
docstring 自承「done_callback 在 loop 上跑,同步 append_audit 可接受(罕見路徑)」。

三個問題疊在一起:
1. `return_code_message` 是 `SKCenterLib_GetReturnCodeMessage` —— **從 event loop 執行緒
   跨 apartment 呼叫 COM 物件**(B10 F-02 已列)。COM marshalling 在 apartment 擁有者
   (capital-com 執行緒)忙碌時會排隊,**而 late 路徑成立的前提就是它剛剛忙了 10 秒以上**。
2. `self._audit(record)` 同步,p50 272 µs / max 9 ms 全記在 event loop 上。
3. `_note_price_type` 可能觸發 `load_trading_calendar()`(lazy 單例首次)。

**event loop 上跑的所有東西 = 8 條 WS 的 fanout + 全部 route。**
在最需要系統活著的那一刻(COM 剛從 10 秒卡死恢復),這條路徑會把整台 server 凍住。

**實測 late 行數:0**(22 日)。所以這是一條**從未在 prod 執行過的路徑**,
也就是說它的正確性只有測試背書。

**修法**:`_on_late_result` 改成 `loop.create_task(...)`,裡面
`await asyncio.to_thread(self._audit, record)`;`return_code_message` 的結果改由
**COM 執行緒在 `_run` 裡先算好**塞進 future 的 result tuple(`(message, code, code_text)`),
event loop 端就不必再碰 COM。第二點是根治 B10 F-02 的同一手。

---

### F-13 【medium】`_close_inflight` 只在「同鍵被再讀一次」時清理,沒有掃除

**位置** `client.py:235`、`client.py:1133-1137`、`client.py:1159`

```python
self._close_inflight: dict[str, float] = {}   # key → monotonic 解鎖時刻
...
deadline = self._close_inflight.get(inflight_key)
if deadline is not None:
    if time.monotonic() < deadline:
        return f"..."
    del self._close_inflight[inflight_key]     # ← 唯一的刪除點,要「再平一次同一檔」才觸發
```
`_submit_close_locked` 只在**前置閘擋下**時 `pop`(`client.py:1163`);
成功送出的鍵留著,直到下一次平同一檔才被清。

**量級誠實說**:key 是 `"股號:種類"` 或契約碼,一天最多幾十個,每個 ~60 bytes。
**這不是記憶體問題**(prod 22 日平倉總共 2 筆)。列出來的理由是**語意**:
`_close_inflight` 的大小 = 「這個 process 生命週期內平過倉的不同標的數」,
成長軸是 uptime 而不是當日筆數 —— 與 B10 指出的 `store._orders` 同一個形狀。
接自動下單後平倉筆數會上一個數量級,屆時它會變成一個**帶著陳舊 deadline 的字典**,
而每一個陳舊項都是一次「第一次平這檔時多跑一次 dict 查找」。

**修法**:`_poll_pending` 那個 watchdog(每 50 ms 跑一次)順手掃一次:
```python
now = time.monotonic()
if self._close_inflight:
    self._close_inflight = {k: v for k, v in self._close_inflight.items() if v > now}
```
兩行。或者更省:每 60 秒掃一次(用 `_balance_last_ts` 同款的節流)。
**但注意** `_close_inflight` 的 docstring 寫「只在 loop 上碰」,而 `_poll_pending`
跑在 **COM 執行緒**上 —— 直接加會破掉那條不變量。要嘛改成 loop 上的 `call_later`,
要嘛把不變量改成「兩條執行緒 + 鎖」。**前者正確,後者是退步。**

---

### F-14 【medium / risk-control】`_audit_blocked` 走共享 executor,且寫檔失敗會把 403 蓋成 500

**位置** `client.py:344-347`、`client.py:876-883`

```python
async def _audit_blocked(self, action, req, reason) -> None:
    await asyncio.to_thread(self._audit, self._record(action, req, blocked=reason))
```
```python
if not gate.allowed:
    reason = gate.reason or "blocked"
    await self._audit_blocked(action, req, reason)      # ← 這裡拋 AuditWriteError 就蓋掉下一行
    raise CapitalGateBlockedError(reason)
```

兩個後果:
1. **被擋下的單也要等共享 executor**。那個池的鄰居是最壞 20 秒、不可中斷的 TC4 歷史取數
   (任務前提已查證)。也就是說「這筆超過金額上限」這個**純記憶體 0.5 µs 就能算出來的判斷**,
   回覆使用者可能要 20 秒。閘擋得越嚴,誤擋時的體驗越差 —— 這會直接壓低使用者設上限的意願。
2. `AuditWriteError` 走 `app.py` 的既有 handler → **500 `AUDIT_WRITE_FAILED`**,
   而真正的原因是 403 `ORDER_BLOCKED` + reason。磁碟滿的時候,使用者看到的是
   「審計寫入失敗」而不是「你超過上限了」。

**修法**:F-11 的持久 handle 落地後,`append_audit` 從 272 µs 降到 9.5 µs(無 fsync)/
337 µs(有 fsync,但無長尾)。**此時 blocked 路徑可以直接同步寫,不走 to_thread** ——
9.5 µs 在 event loop 上完全可接受,而且順便消掉共享池依賴。
第 2 點:`_audit_blocked` 內 catch `AuditWriteError` → `logger.exception` 後仍 raise
`CapitalGateBlockedError`(**閘的結論比審計行重要;錢沒動,審計缺一行是可接受的降級**)。
⚠ 這與「前置審計失敗 = 拒單」的紀律方向相反,但語意不同:
前置審計是「錢要動了,先留帳」;blocked 審計是「錢不會動,留帳只為事後分析」。
**要 user 拍板。**

---

### F-15 【medium / risk-control】`source` 是自我申報字串,後端零驗證

**位置** `capital_api.py:82`(`source: str = "panel"`)、`models.py:60`(`source: str = "panel"  # 稽核分流:panel/flash`)

`flash-send.ts:51-62` 花了 12 行 docstring 說明為什麼六個送單點要共用 `flashSource()`
(「其中一處漂成別的字串,而審計檔上看起來只是少了幾筆 flash-locked —— 沒有訊號」),
但後端這一欄是**任意字串**,沒有 Literal、沒有白名單。

實測值域:`{flash-locked, flash, panel}` 三種,乾淨。
**但接自動下單後這一欄會變成「這張單是誰下的」的唯一線索**(人工 vs 策略 A vs 策略 B),
那時候它就不能是自由字串了。

**修法**:`capital_api.py` 的三個 body 把 `source` 收斂成
`Literal["panel", "flash", "flash-locked"]`(+ 未來的 `auto:*`)。
**這是 wire 值域收窄 = 跨檔契約異動**,前端送 `flashSource()` 的三個值都在集合內,零改動;
但 CLAUDE.md §4 要登記,否則哪天前端加一個 `source` 值會吃 422 且訊息難懂。

---

### F-16 【low-medium / correctness】`mapping.py` 註解與 prod 實證脫節:`bstrPrice="0"` 已驗證

**位置** `mapping.py:248-253`

```python
# 「必須為 0」已實證(SKCOM 回文原文);**字面 "0"(非 "0.00")是推定未實測**
# ... 安全首單若仍 1068 → 改試 "0.00"
```

審計檔說它已經實測過了:2026-08-24 七筆 1068 全拒(修前),2026-08-25 起
**13 筆市價單全部 `ok=True`**(含 2026-09-09 六連發市價賣)。

**修法**:改註解一行,附 2026-08-25 那筆 seq(`2313207905275`)當證據。
零行為改動。留著的代價是下一個人會為此再排一次「安全首單」的儀式。

---

### F-17 【low】`_env_limit` 把 `0` 當「不限」,而 `0` 的自然語意是「一張都不准下」

**位置** `factory.py:71-84`

```python
if value <= 0:
    return None      # ← 0 = 不限
```
docstring 寫明是 user 拍板的(與 treading-king 的 fail-closed 相反)。

列出來不是要推翻拍板,是要標記**它與 kill switch 的互動**:
如果有人想用 `CAPITAL_MAX_QTY=0` 當「停止下單」,結果是**完全相反**的全開。
F-03 的 halt 落地後,文件要明說「停止下單請用 `CAPITAL_ORDER_ENABLED=false` 或 halt API,
不要用 `MAX_*=0`」。`factory.py:73` 的 docstring 已經寫了,但它在後端檔案裡,
而設 env 的人看的是 CLAUDE.md §1 的表。

---

## 5. 失效模式表

「零錯誤訊號」= 這條路徑發生時,log、UI、審計檔**三者都不會出現任何異常跡象**。

| # | 失效模式 | 觸發 | 症狀 | 零訊號 | 位置 | 現在怎麼發現 |
|---|---|---|---|---|---|---|
| M-01 | **重複送單在帳上不可分辨** | 雙擊 / 換一格點 / 隔 501 ms 再點 | 兩張單都成立;審計兩行看起來像刻意疊單 | **是** | `client.py:335` 無 request_id + `ts` 秒解析度 | **發現不了**。要加 `client_order_id` + 毫秒時戳(F-01) |
| M-02 | **逾時放棄的單在 COM 恢復後才送出** | COM 卡 >10 s | 使用者看到「結果未知」,30 秒後市場上多一張 | 否(有 `late=true` 審計 + WARNING) | `client.py:810-820` 無 TTL | `grep '"late": true' data/audit/capital-*.jsonl`(22 日 = 0) |
| M-03 | **總開關關閉時 UI 完全正常** | `CAPITAL_ORDER_ENABLED != true` | 武裝可按、點價可送,連按三下才自動解除武裝 | **是**(UI 層面) | `types.ts:74` 零 production 讀者 | 只能看 403 的 response body。修:前端讀 `order_enabled`(F-04) |
| M-04 | **degraded 下跨筆防護整批失效** | 群益回報主機斷線 | 平倉可重送、改價金額閘跳過、market 交叉驗證放行 | **是**(三條無 log) | `client.py:1043 / safety.py:93 / client.py:1139` | 只有 status badge 變 degraded。要加「degraded 下收緊上限」(F-08) |
| M-05 | **價格打錯一個位數照送** | 限價欄多一個 0 | 交易所退件(或極端行情下真的成交) | 否(券商拒單訊息) | `safety.py:43` 只驗 >0 | 券商退件。修:漲跌停帶硬閘(F-06) |
| M-06 | **帳戶曝險超標只有券商知道** | 累積委託 > 249 萬 | 第 N 筆拒單「額度超過 249 萬」,前 N-1 筆已成立 | 否(拒單訊息明確) | 全專案無帳戶級閘 | `grep 249萬 data/audit/*.jsonl`(22 日 = **30 次**) |
| M-07 | **單日虧損無上限** | 連續虧損 | 沒有任何自動停止 | **是** | 無熔斷 | **發現不了**。資料現成(F-05),只是沒人加總 |
| M-08 | **程式跑飛時無法在 83 秒內停止** | 迴圈寫錯 / 策略異常 | 只能 Ctrl+C,graceful 上限 83 s | 否(會看到單一直冒) | `factory.py:101` frozen SafetyConfig | 肉眼。修:halt API(F-03) |
| M-09 | **審計行在斷電時遺失** | 藍屏 / 強制關機 | 最後幾筆下單記錄消失,且跨日後群益不重播 | **是** | `audit.py:36` 只 flush 不 fsync | **發現不了**(要出事後才知道)。修:持久 handle + fsync(F-11) |
| M-10 | **後置審計失敗 → 單送出了但結果沒入帳** | 磁碟滿 / 權限 | 審計只有前置行,像「送了沒結果」 | 否(`logger.exception`) | `client.py:353-355` | `grep "審計後置寫入失敗" logs/server-*.log`(22 日審計檔顯示 = 0) |
| M-11 | **`_on_late_result` 凍住整台 server** | COM 從長時間卡死恢復 | 8 條 WS + 全部 route 同時停頓 | 否(會很明顯) | `client.py:373` 跨 apartment COM + `:396` 同步 IO | 22 日從未執行過。修:轉 task + to_thread(F-12) |
| M-12 | **blocked 被審計寫入失敗蓋成 500** | 磁碟滿時擋單 | 使用者看到 `AUDIT_WRITE_FAILED` 而不是 `ORDER_BLOCKED` | 否(有 500) | `client.py:878-879` | 靠 response code 分辨。修:F-14 |
| M-13 | **關瀏覽器分頁後單仍送出且無人看見結果** | 送單途中關頁 | 單照送、審計照記,使用者端零回饋 | 否(審計完整) | copycat **無 disconnect watcher**(grep `is_disconnected` = 0),uvicorn 不 cancel route task | 委託列表下次刷新會看到。**設計上是對的**(單不會被半路取消) |
| M-14 | **鎖停 / 緩撮 / 試撮窗照送市價單** | 該市況下按市價鈕 | 鎖停時排進漲停佇列;試撮價當估價 | **是**(閘用估價來自試撮價,看起來合理) | `capital_api.py` 無市況閘 | **發現不了**。修:`MarketCondition` 輸入(F-10) |
| M-15 | **`_cmd_q` 無上界,COM 卡死時無限堆積** | COM 長時間無回應 + 使用者持續送 | 記憶體成長 + 恢復時一次全送 | **是**(無任何計數 / log) | `client.py:212` 裸 `queue.Queue()` | **發現不了**。修:上界 + `qsize()` 進 `/api/capital/status`(F-02) |

---

## 6. 改造順序 + 每一步的量測判準

排序原則:**先讓失效可見,再讓失效不發生**;每一步都要能在不重啟 prod 的情況下驗到。

| 序 | 做什麼 | 為什麼排這裡 | 工作量 | 量測判準(怎麼量才算改對) | 改壞了怎麼退 |
|---|---|---|---|---|---|
| **1** | **審計加 `client_order_id`(選配欄)+ `ts` 升毫秒 + 前端六個送單點共用 `newClientOrderId()`** | 沒有 id 之前,後面每一步的效果都量不出來(84 組重複至今無法判定是不是真重複) | S | ① `pytest -q` + `npm test` 全綠;② 盤後 `python - <<'PY'` 讀當日 `capital-*.jsonl`,`sum(1 for r in rows if r["req"].get("client_order_id"))` **== 新單前置行數**(漏一筆 = 有送單點沒接上);③ 同秒兩筆的 `ts` 毫秒不同 | 欄位是選配,後端忽略未知 key;revert 前端即回舊行為 |
| **2** | **`audit.py` 改持久 handle + `fsync`;lifespan 關 handle** | F-11 實測 max 從 9.06 ms → 0.69 ms,且 F-14 的「blocked 也要等 20 秒」要靠它才敢改成同步 | S | ① 重跑本目錄 `bench_gate.py`,持久 handle+fsync **p50 ≤ 400 µs、max ≤ 1 ms**;② `pytest tests/server/test_audit*.py` 綠;③ prod 跨日當天 `ls -la data/audit/` 看到新舊兩檔、舊檔大小不再變;④ 盤後 `grep "審計" logs/server-*.log` 無新增 ERROR | `audit.py` 單檔 revert,無跨檔契約 |
| **3** | **`_cmd_q` 加 `_Cmd` dataclass:deadline + abandoned + 上界 32;逾時端標記;執行端丟棄 + 回「確定未送出,可重送」** | M-02 / M-15 是**結構上已經成立、只是還沒發生**的兩條;而自動下單會讓它必然發生 | M | ① 新增測試:put 一個 deadline 已過的 cmd,斷言 `fn` **未被呼叫**且 fut 拿到 `RuntimeError("命令逾期,未送出")`;② 突變體:把 TTL 檢查刪掉 → 該測試必紅;③ prod 盤後 `grep "寫入命令逾期" logs/server-*.log`(預期 0,有命中就是真的發生過);④ `/api/capital/status` 新欄 `cmd_queue_depth` 盤中恆 0 | `_Cmd` 是內部型別,無 wire 影響;`OrderResult.dispatched` 是 additive |
| **4** | **kill switch:`client.halt/resume` + `POST /api/capital/safety/halt|resume` + `status_view` 加 `halted` + 前端 `ArmRow` 讀 `order_enabled` / `halted`** | P0 第一名。前端讀者與 API 必須同一批做,否則按下去畫面零變化(M-03) | M | ① `curl -XPOST localhost:8721/api/capital/safety/halt -d '{"reason":"test"}'` → `GET /api/capital/status` 回 `halted:true`;② 立刻送一筆 → **403 `ORDER_BLOCKED` + reason `halted:test`**,審計有 blocked 行;③ 送 `cancel` → **仍成功**(刪單降風險不擋);④ 畫面:武裝鈕 disabled + title「已緊急停止」;⑤ resume 後 ①–④ 反向 | halt 預設 false,不呼叫 = 舊行為;前端讀者 revert 即回舊 UI |
| **5** | **`copycat/capital/risk.py` 純函式 + `PortfolioLimits`;先只掛「頻率窗」與「漲跌停硬閘」兩道,其餘門檻留 None** | 先上**不需要交易語意拍板**的兩道(頻率、漲跌停是客觀的),曝險 / 虧損門檻另外談 | M | ① `pytest tests/capital/test_risk.py` 含突變體:把窗長改 0 / 把漲停界改成 `<` → 各有測試紅;② benchmark:`check_portfolio` **≤ 20 µs**(基準 11.35 µs,留一倍餘裕);③ prod 盤後 `grep "秒內已送" logs/server-*.log` = 0(門檻設 10 筆/10 秒,歷史最密 6 筆,不該誤擋);④ 故意送一筆超漲停價 → 403 且審計 blocked reason 含「超出漲跌停」 | `PortfolioLimits` 全 None = 全閘跳過 = 舊行為 |
| **6** | **`stock_engine.price_band(code)` 淺存取 + route 串接** | 第 5 步的漲跌停閘需要它;獨立一步是因為它碰 stock_engine(另一個區塊的檔案) | S | ① `price_band("2330")` 回 `(lower_milli, upper_milli)` 且與 `snapshot()["meta"]` 的 `lower`/`upper` **逐字相等**(parity 測試,兩處取值不得各自為政);② benchmark:`price_band` **≤ 5 µs**(對照 `snapshot()` 的數百 µs);③ 非自選股號回 `None` 且 route 印 WARNING 後放行 | 新增方法,零既有 caller |
| **7** | **單日虧損熔盤 + 曝險上限(門檻要 user 拍板)** | 需要交易語意決策:249 萬要不要搬進來當本地閘?單日虧損設多少?**先量再定** | M | ① 先做**影子模式**:算出來只寫 log 不擋單,跑兩週;② 盤後 `grep "風控影子" logs/server-*.log`,統計「若門檻設 X 會擋掉幾筆」,拿這張表給 user 拍板;③ 正式啟用後,`day_pnl()` 與前端 `positionEcon` 加總的差 **< 100 元**(同一組 `pnl_base` 算出來的兩個數不該不同) | 門檻 None = 不啟用;影子期零行為 |
| **8** | **`degraded` 下收緊上限 + message 前綴** | 第 5 步的 `PortfolioLimits` 在場之後才有「收緊」的載體 | S | ① 測試:status=degraded 時同一筆單,`max_amount` 生效值 = 設定值 / 2;② prod 真實斷線時(`grep "回報連線中斷"`)送一筆 → message 前綴含「回報停更」 | 收緊係數設 1.0 = 舊行為 |
| **9** | **`_on_late_result` 轉 task + `code_text` 由 COM 執行緒預算** | 排後面因為 22 日 0 次觸發;但接自動下單前必須做(M-11 會凍整台) | M | ① 測試:觸發 late 路徑,斷言 `com.return_code_message` **在 COM 執行緒上被呼叫**(用 `threading.get_ident()` 記錄);② loop lag probe(B10 §6.3)在 late 路徑期間 **p99 < 50 ms** | future result tuple 從 2 元組變 3 元組 = 內部型別,revert 即可 |
| **10** | **`source` 收斂成 Literal + CLAUDE.md §4 登記 + `mapping.py` 註解勘誤(F-16)** | 純文件 / 型別收窄,放最後 | S | ① `pytest` + `npx tsc -b` 綠;② 前端三個 `flashSource()` 值都在 Literal 內(parity 測試直讀前端字面,沿 §4 既有慣例);③ 送一個未知 source → 422 | 型別放寬即回舊行為 |

---

## 7. 這裡不要動(反向結論)

1. **`safety.py` 的五支純函式** —— 0.27~0.88 µs,零配置、零 IO、NaN 顯式擋、
   `remaining <= 0` 顯式擋、`daytrade_sell + buy` 顯式擋。
   **這是全專案寫得最乾淨的一個模組。** 新風控要「加一個新檔」而不是「改這個檔」,
   理由是 `safety.py` 是**無狀態單筆閘**,而組合風控必然有狀態(部位 / 時戳 deque)——
   混進來會毀掉它現在的可測性。

2. **`shield(fut)` + 「結果未知,勿重送」的設計** —— 這是正確的。
   真錢命令一旦送進佇列就不該被 cancel,晚到結果要能落審計。
   `_settle` 的 `if fut.done(): return`(`client.py:186`)也是對的
   (逾時側可能已 cancel,重複 set 會炸進 loop exception handler)。
   **F-02 要加的是 TTL,不是拿掉 shield。** 兩者正交:
   TTL 管「還沒出手的就別出手了」,shield 管「已經出手的結果要收得到」。

3. **`_close_dup_reason` 的兩把鍵顯式分離**(`inflight_key` = 股號:種類 / `scan_key` = 股號)——
   docstring 把「為什麼不能共用一把」寫得很清楚。新的新單去重要**另立一把鍵**
   (`client_order_id`),不要去擴充這兩把。

4. **TanStack mutation 沒有 `retry`** —— `useCapitalMutation`(`useCapital.ts:221-230`)
   刻意沒設 retry(TanStack mutation 預設 0 次)。**不要為了「網路不穩」加 retry。**
   POST 下單不是冪等的,自動重試會把 F-01 從「使用者雙擊」升級成「框架替你雙擊」。
   F-01 的 `client_order_id` 落地**之後**才可以談 retry,而且要 `retry: 1` + 同 id。

5. **`factory.py` 的環境隔離** —— `CAPITAL_ENV` 未知值不默認正式(回 None + `logger.error`)、
   prod banner 印末 4 碼、`_getenv` 對 CAPITAL_* 刻意不 fallback 空值。
   三條都是 fail-safe 方向,且註解寫明理由。不要碰。

6. **`_execute_write` 的審計三段(blocked / 前置 / 後置 / late)結構** ——
   四種路徑各有各的失敗語意,而且都寫對了:blocked 寫不進去 = 拒單、前置寫不進去 = 拒單、
   後置寫不進去 = 只 log(不可回報失敗誘發重送)、late 補行。
   **要改的是 IO 實作(F-11 / F-14),不是這個狀態機。**

7. **server 綁 `127.0.0.1`**(`__main__.py:193`)—— 不要為了「手機也能看盤」改成 `0.0.0.0`。
   下單 API 零 auth,綁 localhost 是現在唯一的存取控制。

8. **`_stkfut_gates` / `_correct_price_tick_gate` / `_close_tick_gate` 三處共用
   `_is_tickable_stkfut` + `_require_legal_tick`** —— docstring 把「三處各寫一份會怎麼漂」
   寫得很清楚(`capital_api.py:144-149 / 186-189 / 210-219`)。新的價格閘要沿用同一個模式:
   **規則寫一份,三個掛點吃同一支。**

---

## 8. 量測方法補充(給下一輪)

**本輪已建立的兩條離線通道**(零 prod 風險,可隨時重跑):

```bash
# 1) 審計統計:閘觸發次數 / 拒單全表 / 名目分布 / source 分流
.venv/Scripts/python scratchpad/order-signal-scan/audit_stats.py

# 2) 重複送單掃描 + pre/post 配對延遲 + 送單密度窗
.venv/Scripts/python scratchpad/order-signal-scan/audit_dup.py
.venv/Scripts/python scratchpad/order-signal-scan/audit_dup2.py   # UTF-8 輸出檔

# 3) 閘與審計 micro-benchmark(純函式 + 檔案 IO 四種寫法對照)
.venv/Scripts/python scratchpad/order-signal-scan/bench_gate.py
```

**還缺的兩條**:
- **`SendStockOrder` 那一段的真實分布**。現在只有秒解析度的 pre/post 配對(mean 0.090 s)。
  F-01 的毫秒時戳落地後,同一支 `audit_dup.py` 就能直接量出 p50/p99,不需要新工具。
- **COM 執行緒的佔用率**。`_pump_once` 每輪的耗時、`_cmd_q` 的等待時間都沒有量。
  最小侵入的做法:`_run` 裡記 `t_get = time.monotonic()`,`fn()` 前後各一次,
  把 `(等待 ms, 執行 ms)` 塞進 `OrderResult` 之外的一個 ring buffer,`/api/capital/status` 回最近 20 筆。
  **這比任何 profiler 都準,因為它量的正是「這張單在我們這邊花了多久」。**

---

## 9. Open questions(需要 user 或 prod 才能答)

1. **84 組重複新單裡,有多少是刻意疊單?** 這決定 F-01 的去重窗要設 1 s 還是 2 s,
   以及要不要在「無 id 時」直接 409。**只有 user 自己知道。**
2. **249 萬要不要搬進 `safety.py` 當本地閘?** 好處:送出前就知道會爆,省一次往返;
   壞處:券商調額度時本地值會過期,而過期的方向是**誤擋**(比誤放好,但仍是誤)。
   建議做成「軟閘 + 警示」:超過就在 hint 上標紅但仍放行,由券商做最終判定。
3. **單日虧損門檻設多少?** 需要先跑兩週影子期拿分布(fix_plan 第 7 步)。
   八月復盤的數字(+15.6 萬 / 月,鎖板單抱到鎖板 +16.4 萬 vs 實拿 +1.7 萬)可以當起點,
   但日內分布沒人算過。
4. **鎖停時要不要擋單?** user 的策略核心是「跟鎖」(memory:`combo-backtest-0906`
   「T+1 開盤出即最優」「只打族群最強那支」),一律擋掉會把主要用例擋死。
   需要的是「鎖停時**市價單**擋、限價貼漲停放行」這種細分,而不是一刀切。
5. **`ts` 升毫秒會不會打壞離線對帳腳本?** `Documents\copycat-trading-review` 那批
   (7,306 行、無版控、repo 外)如果有逐字 parse `ts` 長度或 `strptime` 固定格式就會壞。
   **改之前要 grep 那個目錄。**
6. **`_close_inflight` 的掃除要放 loop 還是 COM 執行緒?** F-13 指出 `_poll_pending`
   在 COM 執行緒上,而該欄位的不變量是「只在 loop 上碰」。
   正確解是 loop 上的 `call_later`,但那需要 client 持有一個週期 task —— 現在沒有。
   要不要為了這件事開一個?或者接受「陳舊項自然堆積」直到自動下單上線?
7. **自動下單的 `source` 值域怎麼設計?** `auto:policy-P` 這種帶策略 id 的形式,
   還是 `auto` + 另一個 `strategy` 欄?這會決定審計檔的分析維度,而審計檔是不可重寫的。
