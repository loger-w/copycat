# T1 擂台:序列化 —— 真裝、真跑、真量

> 2026-09-13 · 對象 `C:/side-project/copycat` · **repo 零改動、專案 .venv 零污染**
> 全部數字皆為本機實測(p50 / p99,不是平均)。查不到的標「未量」。

---

## 0. 一頁結論

| # | 問題 | 實測答案 |
|---|---|---|
| A | 換 orjson / msgspec,系統級每秒省多少 CPU? | **峰值 ≈ 4.0 ms/牆鐘秒(0.4% 單核)、穩態 ≈ 1.1 ms/s(0.11%)。以吞吐量為理由不值得。** |
| B | 「顯式指定 `ORJSONResponse` 反而更慢」是真的嗎? | **真的,實測慢 1.9–2.2 倍。**(group-state 9 檔 861.6 → 1566.6 us) |
| C | 但「HTTP 已經是 Rust,不要動」對嗎? | **不對 —— 這是本輪最大的翻案。** route **直接回 `Response(orjson.dumps(...))`** 比現況快 **3.6–6.4 倍**(個股全量 snapshot 9.31 ms → 1.46 ms)。上一輪只比了四條路裡的兩條。 |
| D | WS per-client 重複編碼值不值得修? | 值得,但**理由是 tail latency 不是吞吐**。修法「publish 入口 orjson 編一次 + N×send_text」在 **N=1 就已經 8.7 倍**(ticks 40 筆 54.2 → 6.2 us),N=8 是 77 倍。 |
| E | `dataclasses.asdict` 呢? | **確認 9.2 倍浪費**(OrderRecord 3.03 → 0.33 us)。n=400 時 819 → 91 us,而同一份 payload 的 orjson 序列化只要 70 us —— **asdict 比真正的序列化還貴 11 倍**。 |
| F | 換 encoder 會不會改 wire? | **五份真實 payload byte-for-byte 完全相同**(stdlib == orjson == msgspec)。但有**一顆地雷**:見 §6。 |
| G | 地雷 | `copycat/live/river_state.py::snapshot` 的 `minutes` 是 **`dict[int, int]`(整數鍵)**。`orjson.dumps` 預設對它 **`TypeError: Dict key must be str`**。全域換 orjson 而不帶 `OPT_NON_STR_KEYS` = 江波圖 WS **一送就炸**。 |
| H | TC4 入站換 parser? | 只省該路徑 **12%**(前處理 5.12 → 2.03 us,但 `parse_stock_realtime` 那段 19.2 us 不動)。確認上一輪「換 parser 是白工」的判斷方向正確,但數字要修正為省 3.1 us/則(上一輪寫 2.3–5.7)。 |

**一句話**:序列化器選型在這套系統裡確實是 0.1–0.4% 單核的小事(上一輪對);
**但把 route 的 response 路徑從 pydantic-core 換成直接 `Response(orjson.dumps())`,
是一個省 3.6–6.4 倍 event-loop stall 的大事(上一輪漏了)。**

---

## 1. 環境與可重現性

```
拋棄式 venv : C:/Users/USER/AppData/Local/Temp/claude/C--side-project-copycat/
              2f320e31-68fc-4cfd-859c-b63b666e7f79/scratchpad/venvs/T1/
建法        : py -3.13 -m venv <上面那個路徑>
Python      : 3.13.13 (tags/v3.13.13:01104ce, Apr 7 2026) [MSC v.1944 64 bit (AMD64)]
CPU         : AMD Ryzen 7 7700 8-Core / 16 logical
OS          : Windows 11 Home 10.0.26200
```

`pip freeze`(全部從 PyPI wheel 裝,零編譯):

```
orjson==3.12.0
msgspec==0.21.1
pydantic==2.13.4          ← 與專案 .venv 同版
pydantic_core==2.46.4     ← 與專案 .venv 同版
fastapi==0.139.2          ← 與專案 .venv 同版
starlette==1.3.1          ← 與專案 .venv 同版
anyio==4.15.1  annotated-doc==0.0.5  annotated-types==0.8.0
idna==3.19  typing-inspection==0.4.4  typing_extensions==4.16.0
```

> **專案 `.venv` 全程唯讀**:只 `sed`/`grep` 讀 `fastapi/routing.py`、`starlette/websockets.py` 取證,
> 沒有裝任何東西進去。repo 也零改動(`git status` 前後一致,產物全在 scratchpad)。

### 腳本與原始輸出

| 檔 | 用途 |
|---|---|
| `…/scratchpad/verify-bakeoff/gen_payloads.py` | 從 repo 真實資料生 payload(見 §2) |
| `…/scratchpad/verify-bakeoff/payloads.pkl` / `payloads_meta.json` | 生出來的 payload 與尺寸清單 |
| `…/scratchpad/verify-bakeoff/bench_t1.py` | 主擂台(六節,183 列結果) |
| `…/scratchpad/verify-bakeoff/bench_t1_raw.txt` | 主擂台原始輸出 |
| `…/scratchpad/verify-bakeoff/bench_t1_results.json` | 主擂台結構化結果 |
| `…/scratchpad/verify-bakeoff/bench_t1b.py` / `bench_t1b_raw.txt` | 追加 1:HTTP 第四條路、相容性紅線、單價彙整 |
| `…/scratchpad/verify-bakeoff/bench_t1c.py` / `bench_t1c_raw.txt` | 追加 2:WS text-frame 變體、river int 鍵、wire byte 對照 |

計時法:每個樣本跑 inner loop 到 ~5 ms,取 7–400 個樣本,回報 **p50 / p99**(不是 mean、不是 min)。
**跨次執行變異約 ±40%**(例:`ws_ticks_40` 的 stdlib dumps 在主擂台量到 33.6 us、追加 2 量到 54.2 us)
—— 這台機器有其他負載,所以**倍率比絕對值可信**,下面所有結論都以倍率立論。

---

## 2. 真實輸入(不是合成 toy)

`gen_payloads.py` 把 repo 真資料灌進真的狀態機:

| 來源 | 用法 |
|---|---|
| `data/stock_watchlist.json` | 取真實自選碼,湊 150 檔(= CLAUDE.md §4 的 `WATCHLIST_LIMIT` 上限) |
| `data/1k/<code>/<最新日>.json`(1,715 檔 × 真實 1K bar) | 每根 bar 的真實 `(o,h,l,c,v,up,down,unch)` 驅動 `copycat.live.stock_state.StockDayState.ingest` —— minutes / VP / ticks 三者的分佈都由真實成交決定 |
| `data/signals/20260911.jsonl`(**686 列,真的**) | 單列 + 整檔 loads |
| `copycat.live.stock_state` / `stock_engine._quote_payload` / `_flush_ticks` / `stock_models.parse_stock_realtime` | payload 形狀逐欄照抄產生點,不是我猜的 |

生出來的尺寸(`payloads_meta.json`,UTF-8 bytes):

| payload | 大小 | 備註 |
|---|---|---|
| `group_state_150`(150 檔 light_snapshot) | **3,413,777 B** | 上一輪量到 3.26 MB — 同量級,獨立對上 |
| `group_state_50` | 1,168,944 B | |
| `group_state_9`(prod log 實測的 codes 數) | 207,376 B | |
| `stock_snapshot_full`(20,000 ticks + 270 分鐘 + 88 VP 檔位) | **1,703,150 B** | deque 上限打滿 |
| `stock_snapshot_tape0`(`?tape=0`) | 23,144 B | |
| `ws_ticks_200 / 50 / 40 / 10` | 27,120 / 6,769 / 5,419 / 1,369 B | |
| `ws_watchlist_quote` | 189 B | |
| `ws_book` | 192 B | |
| `ws_ping` | 16 B | |
| signals 單列 / 整檔 686 列 | 413 B / 329,887 B | |
| TC4 REALTIME 電文 body | 1,184 B | ⚠ 見下 |

> **TC4 電文的誠實標註**:repo 裡**沒有存**原始擷取樣本(2026-07-21 probe 的
> `stock_realtime_sample.json` 在當時的 session scratchpad,已不存在)。
> 我依 `parse_stock_realtime` 實際消費的欄位 + `docs/research/2026-07-21-stock-spot-quote-order-probe.md`
> §1 記載的欄位重建了一則 **25 欄 + 五檔 ×4 欄 = 45 欄、1,184 B** 的電文。
> 題目給的「876 byte」與上一輪的「869 B」比我的短 —— 差在我多帶了幾個 probe 記載但
> parse 不吃的欄位(`OpeningPrice` / `HighPrice` / `Change` …)。**這則是重建,不是原始擷取**,
> 所以第 §7 節的絕對值請當上界;倍率不受影響。

---

## 3. 對決 1:dumps(stdlib vs orjson vs msgspec)

單位 us,`stdlib` = starlette `send_json` 的實際參數 `separators=(",",":"), ensure_ascii=False`。

| payload | 大小 | stdlib p50 | orjson p50 | msgspec p50 | **orjson 倍率** | stdlib p99 | orjson p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ping` | 16 B | 1.38 | **0.08** | 0.06 | **17.3x** | 2.33 | 0.15 |
| `watchlist_quote` | 189 B | 2.45 | **0.17** | 0.28 | **14.4x** | 3.96 | 0.32 |
| `book` | 192 B | 3.20 | **0.21** | 0.34 | **15.2x** | 5.50 | 0.41 |
| signals 單列 | 359 B | 2.97 | **0.30** | 0.36 | **9.9x** | 5.03 | 0.54 |
| `ticks` items=10 | 1.4 KB | 9.83 | **1.13** | 1.54 | **8.7x** | 16.88 | 1.93 |
| `ticks` items=40 | 5.4 KB | 33.58 | **3.57** | 5.49 | **9.4x** | 39.14 | 5.57 |
| `ticks` items=200 | 27 KB | 158.87 | **17.25** | 24.82 | **9.2x** | 282.86 | 30.72 |
| `stock_snapshot`(tape=0) | 23 KB | 170.62 | **17.72** | 26.96 | **9.6x** | 275.04 | 31.89 |
| signals 整檔 686 列 | 289 KB | 1,326.87 | **134.36** | 212.91 | **9.9x** | 2,345.93 | 215.99 |
| `group_state_9` | 207 KB | 1,674.87 | **171.07** | 239.23 | **9.8x** | 2,760.17 | 304.13 |
| `group_state_50` | 1.17 MB | 10,536.05 | **1,005.93** | 1,572.12 | **10.5x** | 16,879.40 | 1,728.17 |
| `group_state_150` | 3.41 MB | 30,531.60 | **3,990.90** | 5,320.20 | **7.7x** | 40,536.50 | 6,346.30 |
| `stock_snapshot` 全量 | 1.7 MB | 12,188.70 | **1,484.93** | 2,369.45 | **8.2x** | 19,457.00 | 2,351.40 |

**結論**:orjson 在**每一種真實 payload** 上都贏,倍率穩定落在 **7.7–17.3x**,越小的訊息倍率越大。
msgspec 全面第二(約 orjson 的 1.3–1.6 倍時間),**唯一例外**是極小訊息(`ping` 16 B)與 int 鍵 payload(§6)。

> 上一輪的表把 `watchlist_quote` 寫成「3.40 → 1.09 us,3.13x」—— 那是拿
> **pydantic-core 的 `to_json`** 當對照。換成真正的 orjson 是 **14.4x**。上一輪的倍率被低估了 4.6 倍。

---

## 4. 對決 2:loads

| 輸入 | stdlib(str) | stdlib(bytes) | orjson(bytes) | msgspec(bytes) | orjson 倍率 |
|---|---:|---:|---:|---:|---:|
| TC4 REALTIME body 1,184 B | 4.43 | 5.12 | **1.86** | 2.18 | **2.4x** |
| signals jsonl 單列 413 B | 2.44 | 3.17 | **0.72** | 0.86 | **3.4x** |
| signals 整檔 686 列(逐列) | 2,636.35 | — | **639.76** | 791.85 | **4.1x** |
| `group_state_9` 207 KB | 1,740.90 | — | 998.37 | **914.92** | 1.7x(msgspec 1.9x) |

兩個違反直覺的點:

1. **stdlib `json.loads(bytes)` 比 `json.loads(str)` 慢**(5.12 vs 4.43;jsonl 列 3.17 vs 2.44)。
   CPython 的 bytes 路徑會先做一次 detect-encoding + decode。所以「改吃 bytes 就會變快」對 stdlib **不成立**,
   只有換 Rust parser 才成立。
2. **大 payload 的 loads,orjson / msgspec 只贏 1.7–1.9 倍**(不是 dumps 的 10 倍)。而且
   `group_state_9` 的 **p99 是 p50 的 5 倍**(1,740 → 8,824 us)—— 那是 GC:一次 parse 生出 20 萬個小物件。
   **這條路真正的成本是「生 Python 物件」不是「parse」**,換 parser 救不到。

---

## 5. 對決 3(關鍵對照):FastAPI response 的四條路

### 5.1 先確認現況走哪條

`.venv/Lib/site-packages/fastapi/routing.py:709-711`:
```python
use_dump_json = response_field is not None and isinstance(response_class, DefaultPlaceholder)
```
`routing.py:322`:
```python
serializer = field.serialize_json if dump_json else field.serialize
```
`fastapi/_compat/v2.py:231`:`serialize_json` → `self._type_adapter.dump_json(...)` = **pydantic-core Rust**。

repo 的 39 支路由全部 `-> dict` 且未指定 `response_class` ⇒ `DefaultPlaceholder` ⇒ **走 Rust `dump_json`**。
**上一輪這段考證我複驗過,正確。**

還有第四條路,`routing.py:695`:
```python
if isinstance(raw_response, Response):
    ...
    response = raw_response       # ← 完全跳過 field.validate / serialize_response
```
**route 只要直接回一個 `Response`,整條 response_field 鏈都不執行。**

### 5.2 四條路實測(p50 us)

| payload | ① 現況 Rust dump_json | ② `ORJSONResponse` | ③ `JSONResponse` | ④ **直接回 `Response(orjson.dumps())`** |
|---|---:|---:|---:|---:|
| `group_state_9` 207 KB | 861.60 | 1,566.62 | 3,127.15 | **178.68** |
| `group_state_50` 1.17 MB | 5,319.90 | 10,064.30 | 20,152.80 | **1,657.75** |
| `group_state_150` 3.41 MB | 22,387.40 | 34,084.20 | 59,957.50 | **6,237.80** |
| `stock_snapshot` 全量 1.7 MB | 9,310.85 | 12,782.90 | 28,447.55 | **1,462.22** |
| `stock_snapshot` tape=0 23 KB | 87.12 | 152.30 | 306.85 | — |
| positions 風 60 列小 payload | 8.16 | — | — | **2.26** |

**② vs ①:確認 `ORJSONResponse` 慢 1.4–2.2 倍。上一輪這個「反向發現」是對的,我複驗通過。**
分段可以看出為什麼:

| 分段(`group_state_50`) | p50 |
|---|---:|
| `field.validate(dict)` | **0.34 us**(對裸 `dict` 幾乎 no-op,沒有「pydantic 驗證稅」) |
| `field.serialize_json`(Rust,現況) | 5,026 us |
| `field.serialize`(② / ③ 走的,Python dict 重建) | **7,699 us** ← 兇手 |
| 裸 `orjson.dumps(原 dict)` | **1,028 us** |
| `TypeAdapter(dict).dump_json(原 dict)` | 4,998 us |

② 之所以慢,是因為 `ORJSONResponse` 讓 `use_dump_json` 變 False,於是多跑一次 `field.serialize`
(7.7 ms 的 Python dict 重建),orjson 省下的那 4 ms 不夠賠。

### 5.3 ④ 才是真正的答案 —— 這是上一輪漏掉的

`TypeAdapter(dict).dump_json` 與 `field.serialize_json` 完全同價(4,998 vs 5,026 us),
所以**慢的不是 FastAPI,是 pydantic-core 對「裸 `dict`」只能走 any-serializer**
(每個值都要在 Rust 裡回 Python 問型別)。orjson 是純 C 的直接編碼器,沒有這層。

| payload | ① 現況 | ④ `Response(orjson.dumps())` | 倍率 | 省下的 event-loop stall |
|---|---:|---:|---:|---:|
| `group_state_9`(prod 現況 7–9 檔) | 861.6 us | **178.7 us** | **4.8x** | −0.68 ms |
| `group_state_50` | 5.32 ms | **1.66 ms** | **3.2x** | −3.7 ms |
| `group_state_150`(上限) | 22.39 ms | **6.24 ms** | **3.6x** | **−16.1 ms** |
| `stock_snapshot` 全量(20k ticks) | 9.31 ms | **1.46 ms** | **6.4x** | **−7.8 ms** |
| positions 小 payload | 8.16 us | **2.26 us** | 3.6x | −6 us |

`Response(msgspec.json.encode())` 是穩定的第二名(group_state_9 330 us、150 檔 8,332 us)。

**這條的意義**:這些 stall 期間 event loop 完全停擺,**8 條 WS 全部停推**。對一套要下實單的系統,
把最壞一發從 9.3 ms 壓到 1.5 ms,比省 0.4% 單核有意義得多。

---

## 6. 相容性紅線(換 encoder 會不會改 wire / 直接炸)

### 6.1 wire byte 對照 —— 五份真實 payload 全部逐 byte 相同

```
group_state_9        stdlib==orjson? True   stdlib==msgspec? True   (168930/168930/168930 B)
ws_ticks_40          stdlib==orjson? True   stdlib==msgspec? True   (4617/4617/4617 B)
stock_snap_tape0     stdlib==orjson? True   stdlib==msgspec? True   (19041/19041/19041 B)
ws_book              stdlib==orjson? True   stdlib==msgspec? True   (167/167/167 B)
signal_line          stdlib==orjson? True   stdlib==msgspec? True   (330/330/330 B)
```
含中文(`"台積電"`)、含 tuple(`book.bids` 是 `list[tuple[int,int]]`)、含 `null`、含 float —— 全部 byte-for-byte 相同。
**golden 對帳 / log diff 不會紅。** 這一點上一輪只推理沒實測,我實測確認。

### 6.2 差異矩陣(這才是要小心的)

| 情境 | stdlib | orjson | msgspec | 判讀 |
|---|---|---|---|---|
| `float("nan")` | `{"x":NaN}` | `{"x":null}` | `{"x":null}` | **stdlib 現在吐的是非法 JSON,瀏覽器 `JSON.parse` 會 throw。換 orjson 其實是修 bug**,但屬行為改動 |
| `float("inf")` | `{"x":Infinity}` | `{"x":null}` | `{"x":null}` | 同上 |
| **int dict key** | `{"1":"a"}` | **RAISE TypeError** | `{"1":"a"}` | 🔴 **見 6.3** |
| tuple 值 | `[1,2]` | `[1,2]` | `[1,2]` | 相同 |
| set 值 | RAISE | RAISE | `[1,2]` | msgspec 更寬鬆(= 少一個早期報錯點) |
| dataclass 值 | RAISE | 自動展開 | 自動展開 | 🟡 現在會大聲炸的忘記轉 dict,換了之後會**靜默通過** |
| 2**63 | 一致 | 一致 | 一致 | 相同 |
| 中文 | 一致 | 一致 | 一致 | 相同(三者都等同 `ensure_ascii=False`) |

### 6.3 🔴 地雷:`river_state.snapshot()` 的整數鍵

`copycat/live/river_state.py:46,160-164`:
```python
self._minutes: dict[str, dict[int, int]] = {k: {} for k in self._keys}
...
legs[key] = {"label": ..., "minutes": dict(minutes), ...}   # ← int 鍵直接上 wire
```

實測(11 腿 × 270 格,30,115 B):

```
stdlib json.dumps                  OK
orjson.dumps(預設)                  RAISE TypeError: Dict key must be str      ← 🔴
orjson.dumps(OPT_NON_STR_KEYS)     OK  30115 bytes,與 stdlib byte-for-byte 相同
msgspec.json.encode                OK  30115 bytes,與 stdlib byte-for-byte 相同
```

**在 `WsBroadcaster.publish` 入口無條件換 orjson,江波圖 WS 第一則 snapshot 就 TypeError。**
`stock_state` 的 `minutes` / `vp` 有 `str(k)`(產生點寫死了),`oi_levels` 的 `by_strike` 轉成 list —— 唯獨 river 沒有。

`OPT_NON_STR_KEYS` 的代價(同一份 payload,鍵已是 str):39.81 → 64.03 us,**+61%**。
而 river 這份 payload 本身:

| | p50 |
|---|---:|
| stdlib | 466.40 us |
| orjson + `OPT_NON_STR_KEYS` | 101.66 us |
| **msgspec**(免旗標) | **63.09 us** ← 這個 payload msgspec 贏 orjson 1.6 倍 |

**處置建議**:不要靠全域旗標。要嘛 (a) 先把 `river_state.snapshot` 的 `minutes` 鍵改成 `str(k)`
(那是一行,而且與 `stock_state._minutes_payload` 的既有慣例一致),然後用不帶旗標的 orjson;
要嘛 (b) 用 msgspec 當統一 encoder。(a) 比較好 —— 統一慣例 > 靠 encoder 寬容。

---

## 7. TC4 入站:換 parser 到底省多少

現況 `copycat/live/tc4.py:1193-1200` + `:1247`:
```python
raw = (sock.recv()[:-1]).decode("utf-8")     # 整則 decode
idx = raw.find(":")
msg = json.loads(raw[idx + 1:])              # 再 slice 出第二份 str,才 loads
if msg.get("DataType") != "REALTIME": return # ← 過濾在 loads 之後
```

| 段 | p50 |
|---|---:|
| 現況 `decode + find + str slice + json.loads` | **5.12 us** |
| `bytes find + slice + orjson.loads` | **2.03 us** |
| `bytes` 預篩 `b'"REALTIME"' in raw` | 0.17 us |
| `parse_stock_realtime(dict)` | **19.18 us** |
| **全鏈(現況)** | **25.78 us** |
| **全鏈(bytes + orjson)** | 25.66 us(p99 42.00 → 39.80) |

**換 parser 省 3.1 us,佔全鏈 12%。**(上一輪寫「省 2.3–5.7 us = 8–10%」,方向一致,數字微修。)

> 全鏈那兩列 p50 幾乎相同(25.78 vs 25.66)是量測噪音吃掉了 3 us —— 分段量才看得出來。
> 這是「量全鏈看不到、量分段才看得到」的典型,兩種都要量。

**順帶排除一個假說**:我懷疑過 orjson 產的 dict 因為 key 沒被 intern,會讓後面的
`msg.get("SecurityName")` 變慢,把省下的 parse 時間吐回去。實測**不成立**:

| `parse_stock_realtime` 吃的 dict 來自 | p50 |
|---|---:|
| stdlib `json.loads` | 19.02 us |
| orjson `loads` | 19.59 us |
| msgspec `decode` | 19.69 us |
| 原始碼字面 dict(interned key) | 20.71 us |

四者在噪音內相同(連 interned key 都沒比較快),**`parse_stock_realtime` 對 dict 的產生者不敏感**。
所以那 3.1 us 是真的省得到。

**但**:全鏈 80% 在 `parse_stock_realtime`(19.18 / 25.78)。**這條的主戰場不在序列化。**

---

## 8. WS per-client 重複編碼

`starlette/websockets.py:174` 逐字:
```python
text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
```
`copycat/server/ws.py:281-284` 的 `relay._send` 對**每個 client** 各呼叫一次 `send_json`
(`WsBroadcaster.publish` 放的是同一個 dict 物件,零複製 —— 序列化才是 N 倍的地方)。

四個變體實測(p50 us;A/B 保留 **text frame**,C 改 **binary frame**):

### `watchlist_quote` 189 B

| N | 現況 N×`send_json` | A 1×stdlib + N×`send_text` | **B 1×orjson+decode + N×`send_text`** | C 1×orjson + N×`send_bytes` |
|---:|---:|---:|---:|---:|
| 1 | 2.31 | 2.32 | **0.31**(7.5x) | 0.26 |
| 2 | 4.57 | 2.33 | **0.44**(10.4x) | 0.30 |
| 4 | 9.60 | 3.21 | **0.62**(15.5x) | 0.50 |
| 8 | 26.90 | 4.02 | **0.66**(40.8x) | 0.56 |

### `ticks` items=40(5.4 KB,峰值形狀)

| N | 現況 | A | **B** | C |
|---:|---:|---:|---:|---:|
| 1 | 54.17 | 50.85 | **6.24**(8.7x) | 5.38 |
| 2 | 99.03 | 52.49 | **6.82**(14.5x) | 5.09 |
| 4 | 209.08 | 44.13 | **5.79**(36.1x) | 6.09 |
| 8 | 337.59 | 54.12 | **4.36**(77.4x) | 4.25 |

### `ticks` items=200(27 KB,開盤爆量)

| N | 現況 | A | **B** | C |
|---:|---:|---:|---:|---:|
| 1 | 250.81 | 255.94 | **27.58**(9.1x) | 26.43 |
| 4 | 820.06 | 174.57 | **20.37**(40.3x) | 29.62 |
| 8 | 2,039.82 | 255.76 | **20.97**(97.3x) | 18.55 |

**三個判讀**:

1. **變體 B 在 N=1 就已經贏 7.5–9.1 倍** —— 也就是說「現在只有 1–2 個分頁所以不急」是錯的推論。
   N 倍那部分是 bonus,**encoder 那部分立刻就有**。
2. **變體 C(binary frame)相對 B 幾乎沒有額外好處**(省下的 `.decode()` 在噪音內),
   卻要動前端:`ws-reconnect.ts:205` 是 `JSON.parse(ev.data)`,binary frame 下 `ev.data` 是 `Blob`
   → 得設 `binaryType='arraybuffer'` + `TextDecoder`,而且是**前後端同版部署**才不會靜默死。
   **不值得。選 B。**
3. 變體 A(只去掉 N 倍、不換 encoder)在 N=1 是零收益,N=8 才 8 倍。**不如直接做 B。**

`PING` 可以做成模組級常數 `PING_BYTES = b'{"type":"ping"}'`(現況每 10 s × 每連線各 1.38 us)——
零風險、零 wire 變動,可以當 `WsConnection` Protocol 加 `send_text` 這件事的試驗田。

---

## 9. `dataclasses.asdict`

全庫呼叫點(`grep -rn asdict copycat/`,16 處):

```
copycat/server/capital_api.py:258   orders    ← HTTP 熱端點
copycat/server/capital_api.py:271   fills     ← prod log 第四名 1,210 次
copycat/server/capital_api.py:288   positions ← prod log 第一名 4,329 次
copycat/server/capital_api.py:307/337/344/355/364/381  單物件(量可忽略)
copycat/capital/client.py:339,341   審計 _record(每筆下單 ×2,可忽略)
copycat/replay/runner.py:132,149    離線
copycat/backtest/fade_optimize.py:125  離線
```

單列(p50 us):

| dataclass | `asdict` | `dict(o.__dict__)` | `{n: getattr(o,n) …}` | 倍率 |
|---|---:|---:|---:|---:|
| `OrderRecord`(21 欄) | 3.03 | **0.33** | 0.76 | **9.2x** |
| `FillRecord`(9 欄) | 1.55 | **0.19** | 0.34 | **8.2x** |
| `Position`(11 欄) | 1.86 | **0.20** | 0.47 | **9.3x** |

整支 route 規模(`{**asdict(p), "code": …}` 推導式):

| n | 現況 | `__dict__` 版 | 倍率 | 對照:該 payload 的 `orjson.dumps` |
|---:|---:|---:|---:|---:|
| 50 | 101.69 | **11.27** | 9.0x | 8.91 |
| 100 | 207.43 | **23.01** | 9.0x | 17.62 |
| 400 | 819.25 | **91.43** | 9.0x | 70.27 |
| 1200 | 2,468.50 | **279.73** | 8.8x | 207.70 |

**`asdict` 比真正的序列化貴 11.7 倍**(n=400:819 us vs 70 us)。上一輪說「貴 3.3 倍」——
那是拿 pydantic-core 當對照,拿 orjson 當對照差距更懸殊。

`msgspec.Struct` 直出對照(5 欄 × 400 列):`msgspec.encode(list[Struct])` 37.90 us vs
`orjson.dumps(list[dict])` 26.15 us —— **Struct 沒有比較快**,它的價值是型別安全與記憶體,不是速度。
**把 `capital/models.py` 從 dataclass 改成 msgspec.Struct 沒有效能理由**(而且會炸掉
CLAUDE.md §4 的 `avg_source` / `PositionKind ⊆ TradeKind` 那幾條 parity 測試的 `dataclasses.fields` 反射)。

修法是三行:`{**p.__dict__, "code": ...}`。前提是那三個 dataclass 沒有 `slots=True`
(有的話 `__dict__` AttributeError —— **會炸不會靜默錯**,可接受);穩妥版用 `{n: getattr(o,n) for n in _NAMES}`
(模組級預算好的 tuple),仍快 4x 且對 slots 免疫。

---

## 10. 換算到系統級

單價(`bench_t1b` §(d),同一次執行,p50 us):

| 訊息 | stdlib | orjson | 省/則 |
|---|---:|---:|---:|
| `watchlist_quote` | 2.207 | 0.173 | 2.034 |
| `book` | 3.077 | 0.215 | 2.862 |
| `ticks`(40 items) | 35.177 | 3.758 | 31.419 |
| `ping` | 2.234 | 0.142 | 2.092 |

### 峰值一秒(09:00–09:05,80 檔自選,N=1 client)

| 路徑 | 量(來源:上一輪 prod log + 本題給定) | 現況 | orjson 後 | 省 |
|---|---|---:|---:|---:|
| 出站 `watchlist_quote` | 150 則/s(最壞) | 331 us | 26 us | **305 us/s** |
| 出站 `book`(零節流) | 100 則/s | 308 us | 22 us | **286 us/s** |
| 出站 `ticks` | 10 則/s × 40 items | 352 us | 38 us | **314 us/s** |
| 出站 futures 0.1 s flush | 40 則/s 小訊息 | ~120 us | ~10 us | ~110 us/s |
| 出站 `ping` | 0.8 則/s | 1.8 us | 0.1 us | 1.7 us/s |
| 入站 TC4 五 session | 800 則/s(粗估) | 4,096 us | 1,624 us | **2,472 us/s** |
| HTTP `group-state` | 0.077/s(prod 實測) | 66 us | 14 us | 53 us/s |
| HTTP `stock/state` 全量 | 0.056/s(prod 實測) | 521 us | 82 us | 440 us/s |
| HTTP `positions` asdict | 0.27/s × ~60 列 | 33 us | 4 us | 29 us/s |
| **合計** | | **≈ 5.8 ms/s** | **≈ 1.8 ms/s** | **≈ 4.0 ms/s** |

**峰值省 4.0 ms / 牆鐘秒 = 0.4% 單核。**
穩態(入站 200 則/s、出站量減半)≈ **1.1 ms/s = 0.11% 單核**。

> **這印證了上一輪「換序列化器省 0.3% 單核」的結論。以吞吐量為理由,這整塊不值得做。**
> 我量到的是 0.4%(峰值)/ 0.11%(穩態),與上一輪同量級。

`N` 不是 1 時(雙螢幕 / 多分頁 / 之後掛自動化 consumer):出站那 1.1 ms/s 線性乘 N,
而修法 B 之後恆定 0.1 ms/s。N=4 時省的是 4.3 ms/s 而不是 1.0 ms/s。

### 但真正的理由是尾巴,不是總和

| 單發 event-loop stall(期間 8 條 WS 全停) | 現況 | 修後 | 省 |
|---|---:|---:|---:|
| `GET /api/stock/state/{code}` 全量 20k ticks | **9.31 ms** | 1.46 ms | **−7.85 ms** |
| `GET /api/stock/group-state` 150 檔(上限) | **22.39 ms** | 6.24 ms | **−16.15 ms** |
| `GET /api/stock/group-state` 9 檔(prod 現況) | 0.86 ms | 0.18 ms | −0.68 ms |
| WS `ticks` 200 items × N=4 | 0.82 ms | 0.02 ms | −0.80 ms |

對照題目給的地板:**Windows timer 精度 15.6 ms、閒置 loop `asyncio.sleep(0.05)` overshoot p50 = 12.43 ms**。
`group-state` 150 檔的 22 ms stall **已經超過那個地板**,`stock/state` 的 9.3 ms 是同量級。
其餘每一條都遠在地板之下 —— **那些改了也量不出來**。

---

## 11. 建議(依 收益/風險 排序)

| 排序 | 做什麼 | 在哪 | 實測收益 | 風險 |
|---|---|---|---|---|
| **1** | route 直接回 `Response(orjson.dumps(payload), media_type="application/json")`,**只做三支大 payload 端點** | `server/app.py` 的 `stock_state` / `stock_group_state` / `market_breadth_rows` | stall −7.85 / −16.15 ms(單發) | 低。wire byte 相同(實測);失去的只有 `-> dict` 那個空 OpenAPI schema。⚠ NaN 語意變了(見 6.2) |
| **2** | `WsBroadcaster.publish` 入口編一次(orjson → `.decode()`)、`relay` 改 `send_text`;`WsConnection` Protocol 加 `send_text` | `server/ws.py` | N=1 就 7.5–9.1x;N=8 是 40–97x | 中。8 條 WS 的 fake 全要補 `send_text`;**先修 river int 鍵**(6.3)否則炸 |
| **3** | `{**p.__dict__, "code": …}` 取代 `asdict` | `server/capital_api.py:258/271/288` | 9.0x(n=400:819→91 us) | 低。三行。`slots=True` 會炸不會靜默錯 |
| **4** | `river_state.snapshot` 的 `minutes` 鍵改 `str(k)` | `live/river_state.py:162` | 本身零收益,是 #2 的前置 | 中。**改 wire**(`{540: 3}` → `{"540": 3}`)—— 但 JSON 本來就只有字串鍵,前端 `JSON.parse` 拿到的一直都是字串鍵,**前端零改動**。要確認前端沒有依賴 `Number(k)` 之外的東西 |
| **5** | `PING_TEXT = '{"type":"ping"}'` 模組級常數 | `server/ws.py:41` | 0.8 us/s(可忽略) | 零。當 #2 的試驗田 |
| **6** | TC4 入站走 bytes + orjson + `b'"REALTIME"' in raw` 預篩 | `live/tc4.py:1193-1200,1247` | 全鏈 −12%(25.8 → 22.7 us/則) | 中。`handle_raw(raw: str)` 是四個子類的覆寫點,簽名改 str→bytes 要同動四處 + 全部 fake + 測試 |
| **不做** | 加 `ORJSONResponse` / `JSONResponse` | — | **負收益 1.4–2.2x** | — |
| **不做** | `capital/models.py` 改 msgspec.Struct | — | **零收益**(37.9 vs 26.2 us,還輸給 orjson+dict) | 高(炸 parity 測試) |
| **不做** | 為 loads 換 parser(除了 TC4 入站) | — | 大 payload 只 1.7x,且成本在 GC | — |

**如果只做一件事**:做 #1。三個 route 各改一行,省的是 7.8–16 ms 的 WS 全停。
**如果要做整套**:#4 → #5 → #2 → #3 → #1 → #6,但先承認 **總 CPU 只省 0.4%**,
說服力全在「event-loop stall 從 9.3 ms 變 1.5 ms」這件事上,不在吞吐量。

---

## 12. 量測的侷限(什麼情況下結論會反轉)

1. **跨次執行變異 ±40%**(同一組 `ws_ticks_40` stdlib 在三次執行中量到 33.6 / 54.2 / 35.2 us)。
   這台機器不是隔離的 benchmark 環境。**倍率可信,絕對值當量級看。**
2. **訊息率是繼承的,不是我量的**:800 則/s 入站、150 則/s `watchlist_quote`、100 則/s `book`
   來自上一輪的 prod log 推估與本題給定。**盤中沒有跑 server 實測過**(硬紀律禁止)。
   若真實入站只有 200 則/s,§10 的入站那 2.47 ms/s 要打四折,總省變 2.1 ms/s。
3. **TC4 電文是重建的**(§2 末),不是原始擷取。§7 的絕對值是上界。
4. **`group_state_150` / `stock_snapshot` 全量是理論最壞**:prod log 實測 `group-state` 的
   `codes=` 只有 7–9 個、tape 多半走 `?tape=0`。所以 #1 的「省 16 ms」是**上限值**,
   現況日常那一發只省 0.68 ms。要讓 #1 的收益兌現,得先確認有人真的會開到 50/150 檔群組。
5. **前端那半完全沒量**(`JSON.parse` + `minutesFromRecord` 重建):那是 F 區的事。
   後端序列化變快不會讓前端變快 —— 上一輪量到 150 檔時前端主執行緒 block 25.5 ms,
   **比後端的 22.4 ms 還大**。只修後端 = 只解掉一半。
6. **沒有量 `asyncio` / uvicorn / ASGI 那一層的開銷**:§8 的數字只是純序列化,
   `websocket.send({"type":"websocket.send","text":…})` 的 ASGI 往返沒算。
   若那層本身要 20 us,把序列化從 54 us 壓到 6 us 的實際收益會被稀釋。**未量。**
7. **GC 沒有控制**:`group_state_9` loads 的 p99 是 p50 的 5 倍就是 GC。
   真實 server 裡這些 payload 的存活期不同,GC 壓力也不同。
