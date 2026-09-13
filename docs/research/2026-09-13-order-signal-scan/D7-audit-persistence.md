# D7 — 下單:審計、持久化與對帳

> 區塊:`copycat/server/audit.py`(38 行)、`copycat/capital/client.py` 的審計段
> (:320-398, :874-922)、`copycat/capital/store.py` 的持久化面(結論:**零持久化**)、
> `copycat/fileio.py`、真實資料 `data/audit/capital-*.jsonl`(22 檔 / 1,075 行 / 356 KB)
> 與 `logs/server-*.log`(79 檔)。
> 掃描日期 2026-09-13 · 唯讀,未改動 repo 任何檔案、未啟動 server、未送出任何委託。
>
> 所有帶「實測」字樣的數字都是本機跑出來的(Python 3.13 / Windows 11 / C: SSD),
> 腳本留在同目錄:`bench_fsync.py`、`bench_record.py`、`recon.py`、`recon2.py`、
> `recon3.py`、`recon_day.py`、`kill_test.py`,可重跑。
> 標「推估」的是沒量到的。

---

## 0. 一句話結論

審計檔**不是帳本,是送單意圖的收據**。它記得住「我按了什麼鈕」,記不住「市場發生了什麼」——
成交價全庫沒有任何一處落檔(audit 沒有成交列、log 行不印 price、`Position` 從不寫檔),
所以「當天成交多少、部位怎麼變」**完全無法從 repo 內的資料重建**,只能回頭問群益。
更根本的是覆蓋率:2026-09-11 當天回報流裡有 46 個委託序號,只有 **13 個(28%)** 是本 app 送出的,
其餘 33 個來自群益 APP 或昨日單 —— 一份只記錄自己送出去那一半的檔案,結構上就當不了對帳基準。

至於大家盯著的 `fsync`:它值得做,但它**不是這一區的主要風險**。實測 `taskkill /T /F`
(正是 `run.ps1:50` 的硬殺手段)之後 flush 過的行**一行不少**;沒有 fsync 的真實暴露面
只剩 OS 崩潰 / 斷電,而以每日 24 行的寫入率估,一次藍屏期望丟失 **< 0.01 行**。
真正的缺口在**沒被寫下來的東西**:request_id、毫秒時戳、實際送出的欄位、成交、部位。

---

## 1. 現況地圖

### 1.1 寫入路徑(唯一寫者 = 群益 CapitalClient)

```
event loop thread
  client._execute_write (client.py:865-922)
    ├─ gate 不過 → _audit_blocked ──┐
    ├─ 未就緒     → _audit_blocked ──┤  (client.py:344-347)
    │                                │
    ├─ 前置 (client.py:885) ─────────┤  await asyncio.to_thread(self._audit, record)
    │                                │
    │   [ COM 佇列 → SendStockOrder → 結果 ]
    │                                │
    ├─ 後置 (client.py:896/907/917) ─┤  _audit_after → to_thread(同上),例外只 log
    │                                │
    └─ 晚到 (client.py:393-398) ─────┘  ★ 不走 to_thread,**直接在 event loop 上同步寫**
                                         │
                                         ▼
                      ThreadPoolExecutor(預設池,20 workers,與 TC4 / FinMind 共用)
                                         │
                                         ▼
                      server/audit.py::append_audit (38 行,全檔)
                        line = json.dumps(record, ensure_ascii=False)
                        with _audit_lock:                    # module-level threading.Lock
                            base.mkdir(parents=True, exist_ok=True)
                            with open(path, "a", encoding="utf-8") as fh:
                                fh.write(line + "\n")
                                fh.flush()                   # ← 只到 OS,不到碟
                        except OSError → raise AuditWriteError
                                         │
                                         ▼
                      data/audit/capital-{date.today():%Y%m%d}.jsonl
                      (UTF-8 無 BOM、**CRLF**(Windows 預設 newline 翻譯)、append-only)
```

**檔案位置**:`factory.py:111` = `CAPITAL_AUDIT_DIR` → `TXO_AUDIT_DIR` → 預設 `data/audit`。
本機實際落在 repo 內的 `C:\side-project\copycat\data\audit`(非 OneDrive / 非網路磁碟)。
`data/` 在 `.gitignore` 內 → **審計檔沒有版控,也沒有任何備份機制、沒有輪替、沒有保留政策**。
成長率 ≈ 16 KB/交易日 ≈ 4 MB/年,空間不是問題。

### 1.2 執行緒歸屬(這一段全庫最容易誤解的地方)

| 寫入點 | 執行緒 | 頻率(22 天實錄) | 阻塞誰 |
|---|---|---|---|
| 前置 `client.py:885` | 預設池 worker | 536 次 | 送單 request(await 期間 loop 可跑別的) |
| 後置 `_audit_after` | 預設池 worker | 536 次 | 同上 |
| blocked `_audit_blocked` | 預設池 worker | 3 次 | 同上 |
| **晚到 `_on_late_result`** | **event loop thread** | **0 次** | **整條 loop(含 8 條 WS fanout)** |
| COM 執行緒 | — | 0 | — |

`_audit_lock` 是 **module-level `threading.Lock`**,同時被最多 20 條 worker 與 event loop
本身競爭。`_on_late_result` 那條路(client.py:396)在 loop 上 `acquire()`,若此刻某個 worker
正拿著鎖做 183 µs 的檔案操作,**event loop 就真阻塞在那裡**。22 天 0 次,是潛伏路徑不是現行問題
(見 FM-09)。

### 1.3 `store` 的持久化:沒有

`store.py:8` 檔頭逐字寫著:

> 重啟後靠 `SKReplyLib_ConnectByID` 的當日 backlog 重播重建,**無需持久化**。

grep 確認 `CapitalStore` 全檔零檔案 IO:`_orders` / `_order_seq` / `_fills` / `_positions` /
`_price_types` / `_contract_ym` / `_snapshot_watermark` 全在記憶體。委託、逐筆成交、部位、
均價、損益基底 —— **一個位元組都沒落地過**。

### 1.4 全庫的持久化原語只有兩支,都不 fsync

```
copycat/fileio.py               atomic_write_text / atomic_write_bytes / atomic_open_text
                                → tmp.write_*() + os.replace()          ← 無 fsync
copycat/server/audit.py         append + flush()                        ← 無 fsync
copycat/server/signal_hub.py    _append_jsonl: open("a") + 隱式 close   ← 連 flush 都沒明寫
```

**`grep -rn "fsync" copycat/` 全庫零命中。**

---

## 2. 端到端延遲預算(審計那一段)

全部在本機實測,`N=400`(檔案類)/ `N=3000`(純運算)/ `N=500`(to_thread)。
每一格都可加總;基準是 B10 已經量出來的「端到端 mean ≈ 70 ms、p99 ≈ 2 s」。

| # | 區段 | 位置 | p50 | p95 | max | 基礎 |
|---|---|---|---:|---:|---:|---|
| 1 | `_record()` 建 dict | `client.py:327-342` | **4.1 µs** | 4.6 | 26.5 | 實測 |
| 1a | └ `datetime.now().astimezone().isoformat(seconds)` | `client.py:336` | 2.5 µs | 2.5 | 6.3 | 實測 |
| 1b | └ `dataclasses.asdict(req)` | `client.py:339` | 1.4 µs | 1.5 | 41.6 | 實測 |
| 1c | └(對照)手寫 dict | — | 0.2 µs | 0.2 | 1.4 | 實測 |
| 2 | `asyncio.to_thread` 往返(**池空**) | `client.py:885` | **32.4 µs** | 94.0 | 295.9 | 實測 |
| 3 | `_audit_lock.acquire()`(無爭用) | `audit.py:32` | < 1 µs | — | — | 推估 |
| 4 | `base.mkdir(parents, exist_ok)` | `audit.py:33` | **40.3 µs** | 61.3 | 107.1 | 實測 |
| 5 | `json.dumps(record)` | `audit.py:30` | **2.9 µs** | 3.1 | 27.5 | 實測 |
| 6 | `open("a") + write + flush + close`(含 #4#5) | `audit.py:34-36` | **183.5 µs** | 268.0 | 516.8 | 實測 |
| 7 | **前置審計合計(#1+#2+#6)** | — | **≈ 220 µs** | ≈ 367 | ≈ 839 | 實測合成 |
| 8 | **後置審計合計** | — | ≈ 220 µs | ≈ 367 | ≈ 839 | 同 #7 |
| 9 | **每筆委託的審計總成本(#7+#8)** | — | **≈ 0.44 ms** | ≈ 0.73 | ≈ 1.7 | 實測合成 |
| 10 | (對照)端到端一筆委託 | B10 §H3 | ≈ 70 ms | — | ≈ 2 s | B10 實測 |
| 11 | **審計佔端到端比例** | — | **0.63%** | — | — | 推算 |
| 12 | 預設池滿時的排隊 | `client.py:885` | — | — | **無上界** | **不可量**(見 FM-10) |
| 13 | 改法 A:常開 handle + fsync/筆 | 建議修法 | 308.1 µs | 392.5 | 1496.5 | 實測 |
| 14 | 改法 B:常開 handle 不 fsync | 建議修法 | **2.8 µs** | 3.8 | 254.4 | 實測 |
| 15 | 全日審計總工作量(24 行/交易日) | — | **5.3 ms/天** | — | — | 推算 |

**讀法**:第 9 格 0.44 ms 對上第 10 格 70 ms —— 審計在延遲上**不是問題**,連前 20 名都排不進去。
第 13 格說改成真 durable 只多 0.18 ms/筆(+0.25%),第 14 格說單純去掉 open/close 可以省 99%。
唯一真正危險的是第 12 格,而它是排隊問題不是 IO 問題(B10 F-01 已立案)。

### 2.1 對 B10 F-05 的一處校正

B10 §F-05 寫「persistent handle + fsync 的成本(0.34 ms)跟現在(0.25 ms)幾乎一樣……
可以**免費**把稽核升級成真的落盤」。我這一輪重量的結果是 **308 µs vs 184 µs = 1.68 倍**,
不是「幾乎一樣」。結論(值得做)不變,措辭要改:代價是每筆委託 **+0.25 ms**,
佔端到端 70 ms 的 0.35% —— 是**便宜**,不是**免費**。兩次量測差異推測來自目錄內既有檔案數
與當下 page cache 狀態,不是方法分歧。

---

## 3. 逐題回答

### Q1 — 沒有 `fsync` 的實際風險量化

**(a) 什麼情況下會掉?**

`fh.flush()` 只把 Python 的 buffer 推進 OS page cache。因此:

| 情境 | 會不會丟 | 證據 |
|---|---|---|
| 未捕捉例外 / `sys.exit` / 正常關機 | **不會** | `close()` 前已 flush |
| `Ctrl+C` → uvicorn graceful | **不會** | 同上 |
| **`taskkill /PID … /T /F`**(`run.ps1:50` 的硬殺) | **不會** | **本輪實測**:子行程寫 5 行 flush 後被 `/F` 殺,檔案 5 行完好(`kill_test.py`) |
| OS 藍屏 / 斷電 / 拔電源 | **會**,丟 page cache 內尚未由 lazy writer 刷出的部分 | Windows NTFS 行為,未實測 |
| 磁碟本身故障 | 會 | — |

也就是說,**這個系統最常用的那種殺法(run.ps1 的 taskkill /T /F)完全不受影響**。
B10 F-05 講「斷電 / 藍屏會丟掉最後幾筆」是對的,但沒把 taskkill 這個高頻情境排除掉,
讀起來嚴重性被放大了。

**(b) 量級**:22 天 1,075 行 → 每交易日 ≈ 24 行 ≈ 48.9 行/日(含 blocked)……實際
536 次寫入動作 / 22 天 = **24.4 次/天**,集中在 09:00–12:00(09 時 654 行、10 時 268 行)。
以最忙的 09 時計 = 654/22/3600 ≈ 0.0083 行/秒。NTFS lazy writer 的視窗以秒計,
取悲觀的 5 秒窗 → 一次藍屏期望丟失 **0.04 行**;以全日平均計 **< 0.01 行**。
換句話說:**要靠斷電丟掉一行審計,大約要在盤中恰好藍屏一百次**。

**(c) 掉了怎麼知道?**
**不知道。** 這是零錯誤訊號路徑:JSONL 沒有行號、沒有序號、沒有 checksum、
沒有「本日共 N 行」的收尾行。少了一行就是少了一行,任何讀者都看不出來。
唯一的間接線索是 pre/post 配對變成奇數 —— 但配對本身就已經有 1.5% 不可辨識率(Q4)。

**(d) 修法成本**:實測 **+0.18 ms / 行**(常開 handle + fsync 308 µs vs 現況 184 µs),
或 **+0.37 ms / 行**(不改結構、原地加 `os.fsync` = 556 µs)。
每筆委託兩行 → 分別是 **+0.25 ms** 與 **+0.74 ms**,對 70 ms 的端到端都可忽略。
**⚠ 一個必須先確認的前提**:量測是在 `scratchpad`(同一顆 C: SSD)做的,不是在
`data/audit` 本身(不動 repo)。兩者同磁碟,但 `data/audit` 在 repo 內,若 Defender
即時保護對 repo 目錄有不同的掃描規則,fsync 的尾巴會不一樣 —— 落地前要在真目錄量一次 p99。

---

### Q2 — 審計行的 schema:有什麼、缺什麼

**現況(`client.py:327-342`,唯一產生點)**,22 天 1,075 行逐行驗證後的實際鍵集:

```json
{"ts": "2026-09-11T09:07:25+08:00", "env": "prod", "action": "order",
 "req": {"stock_no":"6949","buy_sell":"sell","price":58.8,"qty":1,
         "price_type":"limit","time_in_force":"ROD","trade_kind":"margin",
         "source":"flash-locked"},
 "blocked": null,
 "result": {"ok":true,"code":0,"message":"SK_SUCCESS 2313232659083","seq_no":"2313232659083"}}
```

頂層鍵恆為 6 個(`ts/env/action/req/blocked/result`);第 7 個 `late` 只在
`_on_late_result` 加(`client.py:394`),**22 天實錄 0 次**。
`action` ∈ {order 841, cancel 232, close 2};`env` ∈ {prod 1072, test 3}。

**對照 CLAUDE.md §7 閘三的要求**(「每筆 order req/res 寫 append-only JSONL
(request_id / timestamp / 帳戶遮罩 / 結果)」)以及最初的設計稿
(`.claude/feat/dq4-order-phase1/brainstorm.md:33` 同款要求):

| 契約要求 | 現況 | 判定 |
|---|---|---|
| append-only JSONL | ✔ | 過 |
| timestamp | ⚠ 只有**秒** | 半過 |
| result | ✔ | 過 |
| **request_id** | **✘ 完全沒有** | **不過** |
| **帳戶遮罩** | **✘ 完全沒有**(連遮罩過的末 4 碼都沒有) | **不過** |

舊 TC4 trade 路是有 `request_id` 的(`phase-7-goal-check.md:11` 記載「preview→submit→result
共用 request_id + report exec/fill,帳號全遮罩」),群益這條鏈**把它弄丟了**。
這不是「還沒做」,是**既有能力的退化**。

**還缺的(量化系統角度,詳見 Q7)**:各階段時戳、觸發原因、報價快照、參數版本、
最終狀態、成交。

**缺的還有一類:「實際送出去的東西」。** `req` 是 route 組出來的**意圖層 dataclass**,
不是 SKCOM 真正收到的欄位。三個實錄反例:

1. **期貨的月份契約不在審計裡。** `capital_api.py:330-332` 在 route 內
   `futures.resolved_contract(product)` → `to_exchange_symbol(...)` 把 `TC.F.TWF.TMF.HOT`
   解成具體月份,再**當 kwarg** 傳進 `submit_future_order(req, contract=..., multiplier=...)`。
   `req` 裡只有 `tc4_symbol: "TC.F.TWF.TMF.HOT"`。實錄(2026-08-24 22:54)三筆期貨單,
   審計 req 全是 `.HOT`,實際送的是哪一個月份**只能從券商回傳的錯誤訊息裡讀到**
   (`"TMFI6無法轉換商品ID"`)—— 成功的那些單就無從得知。
2. **市價單的價格是假的。** `price_type: "market"` 時 `bstrPrice="M"`,`req.price` 那個
   數字根本不參與送單(`_stkfut_gates` 的註解逐字寫著「market 單跳過:bstrPrice="M",
   body 的 price 欄不參與送單」)。實錄 2026-08-27 的 close 行 `price_type:"market", price:77.5`
   —— 77.5 只是閘用估價。
3. **ROD → IOC 的升級不在 `req`。** `client.py:1012-1016`:期權市價 + ROD 會被 mapping
   強制改成 IOC,而審計的 `req.time_in_force` 仍然是 `"ROD"`。這件事只以
   `"市價單已升級 IOC;"` 前綴出現在 `result.message` 裡。

**還有一個 schema 級的語意錯誤:`result.seq_no` 在非 order 動作上裝的不是委託序號。**
`client.py:915`:

```python
seq_no=(message.strip() or None) if ok else None,
```

`SendStockOrder` 的 `message` 是委託序號沒錯,但 `CancelOrderBySeqNo` 的 `message` 是狀態文字。
實錄:**114 筆 cancel 的 `result.seq_no` 全都是字串 `"委託資料傳送交易所中!"`。**
任何離線對帳程式只要 join `result.seq_no`,就會靜默把 114 筆刪單接到一個不存在的委託上。

**改毫秒要動哪裡、會不會破壞既有讀者?**

- 動一行:`client.py:336` 的 `timespec="seconds"` → `"milliseconds"`。
- **成本為零**:實測 `isoformat(timespec="milliseconds")` = **2.5 µs**,與 `"seconds"` 的
  2.5 µs **完全一樣**(兩者都是 `datetime.now()` 主導)。
- **破壞讀者?沒有讀者可破壞。** 全 repo grep(py / ts / tsx / md / ps1)confirm:
  `data/audit/*.jsonl` **零程式讀者** —— 沒有 CLI、沒有 endpoint、沒有前端、沒有分析腳本。
  命中的全是文件引用與兩支測試(`tests/capital/test_client.py:107, 1768-1777`,
  兩支都只 `glob("*.jsonl")` 數檔名,不解析 `ts`)。
  ISO-8601 的毫秒是既有格式的**超集**,任何 `datetime.fromisoformat` 讀者也照樣吃。
- **同一件事也適用 `request_id` / `lat_us` / `account_masked` 等新欄**:JSONL 加欄零風險。

---

### Q3 — 審計與 `store` 的關係:兩份記錄一致嗎?能不能互相對帳?

**答:兩者記的是不相交的東西,原理上就對不起來。**

| 維度 | `data/audit/capital-*.jsonl` | `CapitalStore`(RAM) |
|---|---|---|
| 資料來源 | **本 app 的送單意圖 + 群益的同步回應碼** | **群益 OnNewData 主動回報** |
| 涵蓋範圍 | 只有本 app 送的 | 當日**全部**委託(含群益 APP 下的) |
| 生命週期 | 永久(檔案) | process 生命週期 |
| 有沒有成交 | **沒有** | 有(`_fills` / `_Agg.fill_value`) |
| 有沒有部位 | 沒有 | 有(`_positions`) |
| 日界 | **本機日曆日**(`date.today()`,`client.py:325`) | **錨定交易日**(`store._anchor_trade_date`,:115-125) |
| 唯一鍵 | 無(`result.seq_no` 對 cancel 是錯的) | `seq_no`(13 碼 KeyNo) |

**唯一可用的接縫是 `seq_no`,而且只對 `action=="order"` 成立**:
audit 的 `result.seq_no` ↔ store 的 `_Agg.seq_no`。實測 22 天 369 筆成功送單全部拿得到 seq。
反向也可用:刪改單的 `req.seq_no` 可以 join 回同日 audit 的送單行 —— 實測
**115/116 命中(99%)**,唯一的孤兒是 2026-09-11 09:02:14 刪一張前一交易日的單
(`2313231433470`,群益回 `960 查無委託資料`)。

**但兩件事讓對帳在實務上不成立**:

1. **日界不同軸。** audit 的檔名由 `date.today()` 決定,而且是在 **worker 執行緒真正寫檔那一刻**
   算的 —— `_record()` 的 `ts` 卻是更早在 loop 上算的。夜盤跨午夜時,同一個交易日的委託
   會被切到兩個 audit 檔;而 store 的 `_fills` 保留窗走的是錨定交易日(週五夜盤錨到週一)。
   要對一個「交易日」的帳,得自己拼兩個 audit 檔,而檔案本身沒有任何欄位告訴你這件事
   (`req` 裡沒有 trade_date,只有 `ts`)。實錄已有 22:54 的期貨單(2026-08-24),
   離午夜只差 66 分鐘。
2. **覆蓋率只有三成。** 見 Q4。

---

### Q4 — 對帳能力:實際試一次

拿 2026-09-11(`recon_day.py`)。

**[A] 只讀 `data/audit/capital-20260911.jsonl`(32 行)**

- 重建出:**13 筆**送出且被群益收下的委託。每筆知道送出時刻(秒解析度)、股號、方向、
  委託價、量、價格別、交易別、來源(`flash-locked` / `panel`)、委託序號。
- 另外重建出:2 筆刪單(其中 1 筆是跨日單,群益回 960)。
- **重建不出**:成不成交、成交價、成交量、成交時刻、最終狀態、實際送出的欄位。

**[B] 加上 `logs/server-20260911-*.log`**

- `_handle_reply`(`client.py:405-408`)每則回報印一行 INFO,格式固定為
  `Capital reply: seq=%s stock=%s status=%s qty=%s` —— **沒有 price、沒有資券別、沒有 raw**。
- 當日 **90 則**回報,涵蓋 **46 個委託序號**;狀態分布 `{委託:46, 成交:35, 刪單:9}`。
- audit 的 13 筆**全部**在 log 裡找得到回報(13/13)。
- **log 有而 audit 沒有的 seq:33 個(72%)** —— 群益 APP 下的單 + 昨日單。

**[C] 判定表**

| 要重建的東西 | 可不可以 | 缺什麼 |
|---|---|---|
| 當天(本 app)下了哪些單、意圖是什麼 | ✔ 可 | — |
| 哪些單被收下 / 拒絕 / 結果未知 | ✔ 可 | `result.code`(實錄碼:0 / 999 / 960 / 1068 / 400) |
| 為什麼被本方擋下 | ✔ 可 | `blocked`(22 天只有 3 筆 `capital_not_ready`) |
| 哪些單成交、成交幾張 | ~ 勉強 | 要 log 還在且格式沒變;audit 完全沒有 |
| **成交價** | **✘ 不可** | 全庫唯一存放處是 RAM 的 `store._fills` 與 `_Agg.fill_value` |
| **當日整體委託流**(含群益 APP) | **✘ 不可** | 72% 的單不在 audit 裡;log 有 seq 但沒價 |
| **部位怎麼變** | **✘ 不可** | `Position` 從不落檔;只有 `損益列回填 … avg=…` 這種零星 INFO 行 |
| 當日已實現損益 / 手續費 / 稅 | ✘ 不可 | 完全沒有 |
| 送單延遲分布 | ✘ 不可 | 秒解析度;92.2% 的 pre/post 落在同一秒(見下) |

**[D] 秒解析度實際毀掉多少資訊**(`recon3.py`,全 22 天 536 對)

| 觀察 | 數字 |
|---|---|
| pre→post 落在**同一秒**(延遲只知道 0–999 ms) | **494 / 536 = 92.2%** |
| 1 秒 | 39 |
| 2 / 3 / 4 秒 | 1 / 1 / 1 |
| **同秒 + 同 `req`,原理上不可配對的 pre 行** | **8 行(1.5%)**,4 組各 2 行 |
| post 行**不緊跟**自己 pre(交錯,adjacency 配對會錯) | **24 次(4.5%)** |

具體例子:2026-09-11 10:33:42 有兩筆 `6949 sell 1 @53.4 limit cash` 的 pre 行、時戳逐字相同、
`req` 逐字相同 —— 它們的兩個 post 行誰配誰,**沒有任何欄位能決定**。這正是 request_id 要解的問題,
而不是「反正只差幾毫秒」。

---

### Q5 — 委託/成交的持久化:重啟後恢復得了嗎?

**答:靠群益,而且只恢復一部分。**

`store.py:8` 的設計就是「不持久化,靠 `SKReplyLib_ConnectByID` 重播當日 backlog」
(`com.py:145-147`、`client.py:755`)。實際恢復能力:

| 狀態 | 重啟(同一交易日)恢復? | 機制 / 缺口 |
|---|---|---|
| 委託聚合 `_orders` | ✔ | ConnectByID 重播當日 backlog |
| 逐筆成交 `_fills` | ✔ | 同上(D 事件重播) |
| 部位 `_positions` | ✔ | 60 s 輪詢的 balance→profit→OI 回查鏈,約 2 s 後落地 |
| `_contract_ym` | ✔ | 重播帶 idx33 |
| **價格別 `_price_types`** | **✘ 永久失去** | 它是**送單意圖**不是回報事件,重播不重建它 —— `store.clear()` 的 docstring 逐字寫「清掉等於本 app 送出的市價單在重連後全體失標」。重啟等同 clear。 |
| `_snapshot_watermark` | ✔(重建) | 首刷記 None,快照即真相 |
| **跨交易日的任何東西** | **✘** | ConnectByID 只重播「當日」 |

**三個沒被 backlog 救到的洞**:

1. **價格別失標**:重啟後,今天送過的市價單在委託面板上一律顯示不出「市價」標籤。
   **而審計檔裡明明有 `price_type`** —— 只要開機讀一次當日 audit 就能把
   `note_price_type` 餵回去,現在沒有人做這件事。這是「資料有、但沒接起來」的典型。
2. **夜盤跨午夜**:群益的「當日」是哪一種日界未實證。05:00 重啟能不能重播 22:00 的單,
   repo 內沒有樣本。
3. **回報主機斷線後不自動重連**(`client.py:455-462` 逐字:「不自動重連、不 clear store」)。
   斷線後 store 停更到收盤,而 audit 本來就不記成交 —— 這段期間的成交**兩邊都沒有**。
   前端只看得到 `degraded` 徽章,徽章不會告訴你「你的成交記錄從這一刻起是空的」。

---

### Q6 — 檔案 IO 的執行緒歸屬與成本

見 §1.2 與 §2 的延遲預算。摘要:

- **成本**:`append_audit` 實測 p50 **183.5 µs**(其中 `mkdir(exist_ok)` 佔 **40.3 µs = 22%**、
  `json.dumps` 佔 2.9 µs = 1.6%,其餘 ~140 µs 全在 `open`/`close` 這兩個 syscall)。
  加上 `to_thread` 往返 32.4 µs 與 `_record` 4.1 µs → 每次 **≈ 220 µs**。
- 上一輪對 `signal_hub._append_jsonl` 量到的 200 µs/列與這個數字同數量級,合理 —— 兩者是
  同一個 pattern(每列重開檔)。
- **歸屬**:536/539 次在預設池 worker(與不可中斷的 TC4 取數同池,B10 F-01);
  3 次(blocked)同上;**0 次**走 `_on_late_result` 的 loop 直寫路徑。
- **全日總工作量 5.3 ms**(24 行 × 220 µs)。以「一天」為單位看,這個區塊的 IO 成本
  **不存在**。任何以「省 CPU」為理由改它的提案都應該被駁回;要改是為了**耐久性**與**可觀測性**。

---

### Q7 — 量化系統標準:一筆交易的完整生命週期記錄

下面這張表是「要下實單的系統該有什麼」對上「現在有什麼」。判定只看 `data/audit/*.jsonl`
(因為那是唯一永久的一份)。

| # | 應有欄位 | 現況 | 位置 / 缺口 |
|---|---|---|---|
| 1 | **`request_id`**(本方冪等鍵,貫穿 pre/post/late/reply) | **✘** | grep 零命中;CLAUDE.md §7 明文要求 |
| 2 | 事件類型(intent / sent / ack / reject / fill / cancel / timeout) | ~ | 只有 `action` + `blocked`/`result` 三態,**沒有 fill / 沒有終態** |
| 3 | **毫秒(或更細)時戳** | **✘** | `client.py:336` `timespec="seconds"`;92.2% 不可分辨 |
| 4 | **各階段時戳**(gate / audit / enqueue / COM in / COM out / ack) | **✘** | 零分段;B10 F-10 已立案 |
| 5 | **實際送出的欄位快照**(解析後的契約碼、`bstrPrice`、真正的 TIF) | **✘** | 只有意圖層 `req`;三個實錄反例見 Q2 |
| 6 | 委託序號 | ✔(order)/ **✘✘**(cancel 裝的是訊息字串) | `client.py:915` |
| 7 | 券商回應碼 + 原文 | ✔ | `result.code` / `result.message` |
| 8 | **帳號(遮罩)/ 市場 / 環境** | ~ 只有 `env` | `factory.py` 有 `帳號 ****0270` 的 log,審計沒有;cancel 走哪個帳號(sec/fut)不記 |
| 9 | **觸發原因 / 訊號來源** | ~ 只有 `source` 字串(`panel`/`flash`/`flash-locked`) | 沒有訊號 id、沒有規則 id、沒有政策標記 —— 訊號側 `data/signals/*.jsonl` 與下單側**零關聯欄** |
| 10 | **下單當下的報價快照**(bid/ask/last/五檔) | **✘** | 完全沒有。事後無法回答「當時盤面長什麼樣、這個價合不合理」 |
| 11 | **參數版本**(安全閘設定、規則版本、git sha) | **✘** | `/api/health` 有 `git_sha`,審計沒有 |
| 12 | **風控判定過程**(哪些閘、各自結果) | ~ 只有被擋時的 `blocked` 字串 | 過了的閘不留痕;22 天只有 3 筆 blocked |
| 13 | **成交記錄**(價、量、時刻、費用) | **✘** | 全庫零落檔 |
| 14 | **部位變化前後** | **✘** | 全庫零落檔 |
| 15 | 完整性保證(序號 / checksum / 日終收尾行) | **✘** | 丟行零訊號 |
| 16 | 耐久保證(fsync) | **✘** | 全庫零 `fsync` |

**計分:16 項裡完整具備 2 項(#7、#6 的一半),部分具備 4 項,完全沒有 10 項。**

值得特別點出 #9:專案剛上線了影子政策層(spec #192),`data/signals/*.jsonl` 一天寫幾千列、
欄位設計得非常仔細(`kind` / `policy` / `t1_open` / `d_close` 一路到 T+2 回填)。
**但訊號列與下單審計之間沒有任何共同鍵。** 要回答「這筆掃單簇政策 P 之後我有沒有進場、
進在哪」,現在得靠人眼比對時刻。對一個要走到「訊號→下單」自動化的系統,這是最該先補的一條線,
而它只需要在審計 `req` 裡多一個 `signal_id`(前端送 `source` 時一併帶)。

---

## 4. Findings

依嚴重度排。全部標明 on_hot_path(這一區幾乎都不在熱路徑 —— 這正是重點)。

### D7-01 【high / quant-gap】成交價在全庫零落檔,當日成交無法離線重建
**位置** `capital/store.py:166`(`_fills` 只在 RAM)、`client.py:405-408`(reply log 不印 price)、
`server/audit.py` 全檔(無成交列)
**證據** `recon_day.py` 對 2026-09-11 的重建:log 有 35 個成交事件、audit 有 0 個;
`logger.info("Capital reply: seq=%s stock=%s status=%s qty=%s", …)` 格式字串裡沒有 `price`。
**影響** 「當天成交多少」只能問群益。process 一關,當日成交價全部消失。
對帳、滑價分析、策略績效歸因全部做不了。
**修法** `_handle_reply` 的 D 事件(`client.py:421`)多寫一行 JSONL 到
`data/audit/fills-YYYYMMDD.jsonl`(seq / stock / price / qty / flag / time / raw)。
在 COM 執行緒上寫,**必須非阻塞**(見 D7-06 的常開 handle 修法,2.8 µs)。
**風險** 新增 COM 執行緒上的檔案 IO —— 這條執行緒同時是唯一的送單通道(B10 F-04),
所以只能用常開 handle 寫法,不能用現況的 open/close(183 µs × 每則回報)。
**effort** M

### D7-02 【high / quant-gap】零 `request_id` / 冪等鍵,pre/post 配對有 1.5% 原理上不可解
**位置** `client.py:327-342`
**證據** `recon3.py`:536 個 pre 行裡 **8 行(1.5%)**「同秒 + 同 `req`」無法配對;
**24 次(4.5%)** post 不緊跟自己 pre。實例 2026-09-11 10:33:42 兩筆 `6949 sell 1 @53.4`。
CLAUDE.md §7 與 `.claude/feat/dq4-order-phase1/brainstorm.md:33` 都明文要求 request_id;
舊 TC4 trade 路曾經有(`phase-7-goal-check.md:11`),群益路**退化掉了**。
**影響** timeout 之後無法回答「我那張單在不在市場上」(B10 F-09 已立案);
離線對帳無法建立 1:1 關係;未來加自動下單時無法做 exactly-once。
**修法** `_execute_write` 進場 `rid = uuid4().hex[:16]`,寫進 pre / post / late / blocked 四種行;
順手用 `contextvars` 讓 `_note_price_type` 等下游也拿得到。零跨檔契約影響(無讀者)。
**effort** S

### D7-03 【high】`result.seq_no` 對 cancel 裝的是券商訊息字串,任何 join 都會靜默錯接
**位置** `client.py:915` `seq_no=(message.strip() or None) if ok else None`
**證據** 22 天實錄:**114 筆** cancel 的 `result.seq_no` 值為字串 `"委託資料傳送交易所中!"`;
1 筆 close 的值才是真序號 `2313212411813`。
**影響** 欄位名稱與內容不符。離線對帳程式 join `result.seq_no` 會把 114 筆刪單接到不存在的
委託上,而且**不會報錯**(它是合法字串)。
**修法** 依 `action` 分流:只有 `order` / `close` 才把 `message` 當序號;其餘留 `None`,
把原文放進既有的 `result.message`(它已經有了:`"委託資料傳送交易所中!"`)。
**風險** `_note_price_type`(`client.py:955`)也吃 `result.seq_no`,但它被
`if not (price_type and …)` 擋住(cancel 的 req 沒有 `price_type`)→ 改動不影響它。
`tests/capital/test_client.py` 有相關斷言要一併看。
**effort** S

### D7-04 【high / quant-gap】審計記的是意圖,不是實際送出去的欄位
**位置** `capital_api.py:323-334`(期貨 contract/multiplier 走 kwarg 不進 req)、
`client.py:1012-1016`(ROD→IOC 升級不進 req)、`_stkfut_gates` docstring(market 單 price 不參與送單)
**證據** 2026-08-24 三筆期貨審計行 `req.tc4_symbol` 全是 `TC.F.TWF.TMF.HOT`;
實際送出的月份只能從券商錯誤訊息 `"TMFI6無法轉換商品ID"` 反推。
2026-08-27 close 行 `price_type:"market", price:77.5` —— 77.5 從未送出。
**影響** 「我到底送了什麼」在成功路徑上無法回答。期貨換月當天最危險:
審計說 `.HOT`,實際送了哪一個月份完全不可考。
**修法** `_record()` 多一個 `sent` 區塊,由 `com_call` 閉包把最終欄位 dict 回傳
(`to_stockorder_fields` / `to_futureorder_fields` 的產物,敏感欄如帳號遮罩)。
**風險** `to_*_fields` 的產物含帳號 → 必須遮罩(只留末 4 碼),這正好順手補上 §7 的「帳戶遮罩」。
**effort** M

### D7-05 【medium-high】`date.today()` 在 worker 執行緒、`ts` 在 loop —— 跨午夜會分岔,且日界是日曆日不是交易日
**位置** `client.py:325` `when=date.today()` vs `client.py:336` `ts=datetime.now()`
**證據** 兩個時刻點之間隔著一次 `to_thread`(實測 p50 32 µs,池滿時無上界)。
22 天 1,075 行實測**檔名日 vs ts 日不符 = 0**(還沒發生過),但 22:54 的期貨單已經實錄
(2026-08-24),離午夜 66 分鐘。
**影響** (a) 罕見但可能:23:59:59.9 的單被寫進隔天的檔;(b) 必然:夜盤交易日被切成兩個檔,
而檔案裡沒有任何欄位告訴讀者這件事(`req` 無 trade_date)。store 那邊用的是錨定交易日
(`store.py:115-125`),**兩份記錄的日界不同軸**。
**修法** 檔名改用「錨定交易日」(沿用 `store._anchor_trade_date` 的同一條式子,不要另寫一份),
並在 record 內加 `trade_date` 欄。`client._trade_ymd()`(`client.py:141-156`)已經有這個推算,
只是目前只給價格別標籤用。
**風險** 改檔名 = 改既有檔案的命名語意。因為**零程式讀者**,風險只在人的習慣;
建議只加 `trade_date` 欄、檔名先不動(見 fix_plan 排序)。
**effort** S

### D7-06 【medium-high】每筆重開檔(183 µs,22% 花在 `mkdir`)且無 `fsync`
**位置** `server/audit.py:33-36`
**證據** 實測:現況 183.5 µs / 常開 handle 2.8 µs(**66×**)/ 常開 + fsync 308.1 µs /
現況 + fsync 555.5 µs;`mkdir(exist_ok)` 單獨 40.3 µs;`json.dumps` 2.9 µs。
全庫 `grep fsync` 零命中。
**影響** 兩件事:(a) 耐久性缺口(但見下方「風險」的量化 —— 沒有想像中嚴重);
(b) 若要加 D7-01 的成交列(頻率提高 ~4×)或在 COM 執行緒上寫,183 µs 就變成問題了。
**修法** client 持有 per-day 的 append handle(`open(path, "ab", buffering=0)`),
日界換檔時 close 舊開新,`close()` 時 shutdown。`_audit()` 直接
`fh.write(line); os.fsync(fh.fileno())`。
**風險** ① 常開 handle 在關機路徑必須 close,否則反而比現在更容易丟(現況每筆 close 是
天然的耐久點)—— 這會進 `shutdown_budget` 的預算(CLAUDE.md §4 三方同源契約)。
② fsync 尾巴受磁碟 / 防毒影響,量測是在 scratchpad 做的,落地前要在 `data/audit` 真目錄量 p99。
**effort** M

### D7-07 【medium】fsync 缺口的實際嚴重度被高估 —— `taskkill /F` 不丟資料(實測)
**位置** `server/audit.py:36` / `run.ps1:50`
**證據** `kill_test.py`:子行程 `write + flush` 五行後被 `taskkill /PID … /T /F` 硬殺,
檔案**五行完好**。寫入率實測 24.4 行/交易日、最忙的 09 時 0.0083 行/秒 →
一次藍屏(取 5 秒 page cache 窗)期望丟失 **0.04 行**。
**影響** 這是一條**反向 finding**:它說 D7-06 的優先序應該排在 D7-01/02/03 之後,
理由是耐久性而不是「現在正在掉資料」。也校正 B10 F-05 的措辭(見 §2.1)。
**修法** 無(這是判定,不是缺陷)。
**effort** S(僅文件)

### D7-08 【medium / quant-gap】訊號側與下單側零共同鍵
**位置** `client.py:339`(`req.source` 只有 `panel`/`flash`/`flash-locked`)vs
`server/signal_hub.py` 的 `data/signals/*.jsonl`(每列有 `id` / `rule_id` / `policy`)
**證據** 兩份 JSONL 的鍵集完全不相交;grep `signal_id` 在 `capital/` 下零命中。
**影響** 「這筆政策 P 之後我有沒有進場、進在哪、賺賠多少」只能靠人眼比對時刻。
影子期(2026-09-08 起四週)結束後要拿兩本帳對決,現在沒有機器可讀的連結。
**修法** 前端下單時把當下觸發的訊號 `id` 放進 `source`(或新增 `signal_id` 欄),
後端 `StockOrderRequest` 加一個 optional 欄 → 自動進 `req`。
**風險** `StockOrderRequest` 是 frozen dataclass,加 optional 欄不破壞既有 caller;
但 wire 層 `StockOrderBody` 要同步(pydantic),屬跨檔契約(前端 `useCapital.ts`)。
**effort** M

### D7-09 【medium】`_on_late_result` 在 event loop 上同步持 module lock 寫檔
**位置** `client.py:396` `self._audit(record)`(docstring 自承「done_callback 在 loop 上跑,
同步 append_audit 可接受(罕見路徑)」)
**證據** 22 天實錄 `late` 行 **0 筆** —— 從未觸發。但 `_audit_lock` 是 module-level
`threading.Lock`,最多 20 條 worker 同時競爭;loop 上 `acquire()` 是**真阻塞**。
**影響** 潛伏路徑:TC4 半死導致池排隊 + 同時發生一次 timeout 晚到 → event loop 被
audit 鎖住(183 µs ~ 排隊時間)。8 條 WS fanout 一起停。
**判定** 目前**不要動**(罕見 + 沒有實錄)。但如果做了 D7-06(常開 handle,2.8 µs),
這條路自然也變成 3 µs,問題自解 —— 列出來是為了說明 D7-06 的附帶收益。
**effort** S

### D7-10 【medium】審計後置寫入失敗只 log,委託已送出而帳上沒有結果
**位置** `client.py:349-355`
```python
except Exception:
    logger.exception("審計後置寫入失敗(action=%s)— 委託已送出,結果未入帳: %s", action, result)
```
**證據** 設計是刻意的(不可把已送進群益的單回報成失敗,誘發重送)—— 這個取捨是對的。
**影響** 但結果是:pre 行有、post 行沒有,而**沒有任何欄位標記這件事**。
離線讀者看到的是「一個沒有結果的 pre 行」,與「timeout 還在跑」「process 當掉」同形。
**修法** 失敗時降級到一條**極簡**的 fallback 行(只有 `rid` + `code`,寫進另一個檔或
stderr 的結構化行),讓「審計自己壞了」與「還沒寫」分得開。或至少在
`/api/health` 曝一個 `audit_write_failures` 計數。
**effort** S

### D7-11 【medium】重啟後價格別失標,而審計檔裡明明有 `price_type`
**位置** `store.py:623-627`(`clear()` 不清 `_price_types` 的理由)+ `client.py:955-976`
**證據** `_price_types` 只由送單結果產生,ConnectByID 重播不重建它。
而 `data/audit/capital-*.jsonl` 每一筆 order 的 `req.price_type` 都在(843/843 有此欄)。
**影響** 盤中重啟後,今天送過的市價單在委託面板永久失標。零錯誤訊號(標籤只是少,不是錯)。
**修法** 開機時讀當日 audit,把成功送出且有 `seq_no` 的 order 行餵回 `store.note_price_type`。
十幾行。這是「審計檔第一個真正的程式讀者」——順帶也逼出 D7-02/03 的價值。
**風險** 要小心 `note_price_type` 的 prune 規則(候選日集合不相交就刪)與綁定欄位語意;
餵入順序必須依 `ts` 升冪,否則 prune 會互相清掉。
**effort** M

### D7-12 【medium】`fileio.atomic_write_*` 的 `os.replace` 前不 fsync tmp —— 斷電可讓整日訊號檔歸零
**位置** `copycat/fileio.py:21-31`
```python
def atomic_write_bytes(path, content):
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)      # ← 資料可能還在 page cache
    os.replace(tmp, path)         # ← 只有 metadata 是 atomic
```
**證據** 全庫零 `fsync`。`signal_hub.backfill_policy_outcomes`(每日 13:40)用
`atomic_write_bytes` **整檔覆寫**當日與前幾日的 `data/signals/*.jsonl`(單檔 200–300 KB)。
**影響** 這是典型的 rename-without-fsync 危險:斷電後檔名指向一個資料區塊尚未落盤的檔,
最壞是**零長度或半截**,而**原檔已經被 replace 掉了**。audit 每筆只丟一行,這裡一次丟一整天。
零錯誤訊號(下次讀到的是一個合法的短檔)。
**判定** 這一條嚴格說在 B06 的地盤,但 `fileio.py` 是我這一區的必讀檔、也是唯一的持久化原語,
所以在這裡立案。
**修法** `atomic_write_*` 三支在 `os.replace` 前加
`fh.flush(); os.fsync(fh.fileno())`(需要改成用 `open` 而非 `Path.write_bytes`)。
成本:每次一個 fsync(實測 ~120–300 µs),而這三支的呼叫頻率是「每天幾次」到「回測每輪一次」。
**風險** `atomic_write_text` 有 30+ 個 caller(回測輸出),加 fsync 會讓大批小檔寫入變慢 ——
但那些是離線批次,不在任何熱路徑上。
**effort** S

### D7-13 【medium】`signal_hub._append_jsonl` 的 OSError 被吞成 `logger.error`
**位置** `server/signal_hub.py:1412-1419`
**證據**
```python
except OSError as e:
    logger.error("訊號 jsonl 寫入失敗(%s):%s", path, e)
```
對照 `audit.append_audit` 是 `raise AuditWriteError`。
**影響** 兩份「真相源」JSONL 的失敗語意不一致:一份會擋下交易,另一份靜默少一列。
CLAUDE.md 的宣告是「jsonl 是真相源」,而真相源可以靜默缺列。
**判定** 這一條是刻意設計(訊號寫失敗不該打斷行情處理),但至少要有計數器
(`/api/health` 或一個節流 WARNING 的累計)讓「今天掉了幾列」看得出來。
**effort** S

### D7-14 【low-medium】審計檔無完整性標記(無序號 / 無 checksum / 無日終收尾)
**位置** `server/audit.py` 全檔
**影響** 少一行、檔案被截斷、被編輯過 —— 全都零訊號。對「唯一一份錢動了的記錄」來說,
這是最基本的缺口。
**修法** 最小版:每行加一個**日內單調遞增序號** `n`(同一個 `_audit_lock` 內遞增,零額外成本)。
讀者只要檢查 `n` 連續就知道有沒有掉行。日終再寫一行 `{"kind":"eod","n":N,"count":N}`。
**effort** S

### D7-15 【low-medium】審計沒有帳號欄(連遮罩版都沒有),刪改單走哪個帳號不可考
**位置** `client.py:327-342`;`_routing`(`client.py:1031-1051`)決定 sec/fut 帳號但不記
**證據** CLAUDE.md §7 要求「帳戶遮罩」;`factory.py` 開機有 `群益正式環境 | 帳號 ****0270`
的 WARNING,但那是 log 不是審計。
**影響** 多帳號(證券 + 期貨)情境下,「這筆刪單打到哪個帳號」只能靠 `req.market` 推。
**修法** `_record` 加 `"account": mask(account)`(末 4 碼),`_execute_write` 收一個
account 參數(`_routing` 已經算出來了)。
**effort** S

### D7-16 【low】審計檔無輪替 / 無保留政策 / 不在版控 / 無備份
**位置** `factory.py:111` + `.gitignore`
**證據** 22 天 356 KB,≈ 4 MB/年。`data/` 被 gitignore。
**判定** **空間不是問題,不要做輪替。** 但「唯一一份錢的記錄只存在一台本機的一顆碟上、
沒有任何複本」是事實。最低成本的補法是每日收盤後把當日檔複製到另一個位置(或直接
`git add -f` 到一個 private 分支)。不是效能問題,是營運問題。
**effort** S

### D7-17 【low】`json.dumps` 用預設 separators,每行多幾十 bytes
**位置** `audit.py:30`
**證據** 實測 `json.dumps` 2.9 µs,佔 183 µs 的 1.6%。
**判定** **不要動。** 空白讓 `grep` / 人眼閱讀舒服,而這個檔就是給人看的;
省下的 bytes 對 4 MB/年無意義。列出來是為了先把這個常見的「優化」提案駁回。
**effort** S

### D7-18 【low】審計檔是 CRLF
**位置** `audit.py:34` `open(path, "a", encoding="utf-8")`(預設 newline 翻譯)
**證據** 實測 `capital-20260911.jsonl`:32 個 `\r\n` / 32 個 `\n`,無 BOM。
**判定** `json.loads` 容忍尾端空白,現況無害。但若未來做 D7-14 的 checksum 或跨平台工具,
行尾語意要先釘死(對照 `fileio.py` 檔頭已經把三種 newline 語意分清楚了)。
**effort** S

### D7-19 【medium / quant-gap】下單當下沒有報價快照,滑價與「這個價合不合理」事後不可查
**位置** `client.py:327-342`;`_execute_write` 完全不碰行情
**證據** `req.price` 是使用者/前端給的;系統手上明明有 `stock_engine` 的即時 tick
(`live/stock_state.py`)與五檔,但送單路徑完全不取。
**影響** 「我這張 58.8 的賣單,當下的 bid/ask 是多少」事後無解。
滑價分析、成交品質評估、以及**異常行情擋單**(B10 F-12 要的那種風控)全都缺這一份輸入。
**修法** `_execute_write` 進場時從 `app.state.stock` 取一個 O(1) 的快照
(last / bid1 / ask1 / 累計量),寫進 pre 行的 `quote` 欄。
**風險** 引入 capital → stock_engine 的相依(目前是乾淨的零相依)。
建議走注入(一個 `Callable[[str], dict | None]`),保住 `capital/` 的可測性。
這是新功能,要走 `/feat`。
**effort** L

### D7-20 【low】審計覆蓋率 28%,結構上當不了帳本
**位置** 設計層面
**證據** 2026-09-11:回報流 46 個 seq,audit 只有 13 個(28%);其餘 33 個來自群益 APP / 昨日單。
**影響** 任何以 audit 為基準的對帳都會少七成。
**判定** 這不是 bug,是**定位問題**:audit 是「我方送單意圖的收據」,不是「帳本」。
帳本必須由回報流(OnNewData)餵養 —— 也就是 D7-01。
把這兩件事在文件上分清楚,比把 audit 硬撐成帳本更重要。
**effort** S(文件)

---

## 5. 失效模式表

**重點在第 3 欄「零錯誤訊號」。** 這一區 15 條裡有 **11 條**是零訊號的。

| # | 失效模式 | 觸發 | 症狀 | 零訊號 | 位置 | 嚴重度 | 現在怎麼發現 / 要加什麼 |
|---|---|---|---|:--:|---|---|---|
| FM-01 | 審計行永久遺失 | OS 藍屏 / 斷電 | 少一行,pre 或 post 缺一半 | **是** | `audit.py:36` | medium | **沒辦法**。要加行內單調序號 `n`(D7-14),讀者檢查連續性 |
| FM-02 | 成交價永久不可考 | process 結束(每天必然發生) | 當日成交價只剩群益那邊有 | **是** | `store.py:166` RAM only | **high** | 沒辦法。要加 `fills-*.jsonl`(D7-01) |
| FM-03 | cancel 的 `result.seq_no` 錯接 | 任何離線 join | 114 筆刪單接到不存在的委託 | **是** | `client.py:915` | high | 沒辦法(值是合法字串)。要 D7-03 分流 + D7-02 的 rid |
| FM-04 | 同秒同 req 的 pre/post 配不起來 | 連點閃電梯(實錄 4 組) | 延遲統計 / 結果歸屬錯 1.5% | **是** | `client.py:336` 秒解析度 | medium | 沒辦法。要毫秒時戳 + `request_id` |
| FM-05 | 期貨審計不知道送了哪個月份 | 每一筆期貨單(換月當天最痛) | 事後無法確認送出的契約 | **是** | `capital_api.py:330-332` | high | 只有失敗時才從券商錯誤訊息看得到。要 D7-04 的 `sent` 區塊 |
| FM-06 | 夜盤交易日被切成兩個審計檔 | 跨午夜(實錄已到 22:54) | 對一個交易日的帳要拼兩檔,而檔案不說 | **是** | `client.py:325` `date.today()` | medium | 沒辦法。要加 `trade_date` 欄 |
| FM-07 | `ts` 與檔名日分岔 | 23:59:xx 送單 + to_thread 延遲 | 行落在隔天的檔 | **是** | `client.py:325` vs `:336` | low | 可用 `ts[:10] vs 檔名` 掃(本輪掃過:22 天 0 次) |
| FM-08 | 後置審計失敗 → 有 pre 無 post | 磁碟滿 / 權限 / 防毒鎖檔 | 帳上看起來像「還在跑」 | 半(有 `logger.exception`) | `client.py:352-355` | medium | `grep 審計後置寫入失敗 logs/` (22 天 0 次)。要加健康度計數(D7-10) |
| FM-09 | event loop 被 audit 鎖住 | timeout 晚到 + 池排隊同時發生 | 全站(含 8 條 WS)卡住 | **是** | `client.py:396` loop 直寫 | medium | 沒辦法(沒有 loop lag probe)。D7-06 落地後自解 |
| FM-10 | 送單前置審計無上界排隊 | 預設池被 20 條 TC4 半死執行緒佔滿 | 按鈕一直轉,沒有任何 log | **是** | `client.py:885` to_thread | **critical**(B10 F-01) | 沒辦法。要專用 executor + queue depth 指標 |
| FM-11 | 回報斷線後成交記錄整段空白 | `OnDisconnect`(不自動重連) | store 停更 + audit 本來就沒成交 = 雙盲 | 半(`degraded` 徽章) | `client.py:455-462` | high | 徽章看得到「斷線」,看不到「你的成交記錄從此是空的」。要在斷線時寫一行審計標記 |
| FM-12 | 重啟後市價單全體失標 | 盤中重啟(常態) | 委託面板少了「市價」標籤 | **是** | `store._price_types` 不持久 | low | 沒辦法(少標不是錯標)。D7-11 可修 |
| FM-13 | `atomic_write_bytes` 斷電留下零長/半截檔 | 13:40 訊號回填時斷電 | 整天的訊號 jsonl 變成短檔,原檔已被 replace | **是** | `fileio.py:27-31` | medium | 沒辦法(短檔是合法 JSONL)。要 replace 前 fsync(D7-12) |
| FM-14 | 訊號 jsonl 靜默少列 | 磁碟/權限瞬斷 | 「真相源」缺列 | 半(`logger.error`) | `signal_hub.py:1417-1418` | medium | `grep 訊號 jsonl 寫入失敗`。要累計計數 |
| FM-15 | 審計檔整份遺失 | 磁碟故障 / 誤刪 `data/` | 22 天的唯一一份記錄消失 | **是**(事後才知道) | `.gitignore` + 無備份 | medium | 沒辦法。要每日收盤後複製到第二個位置(D7-16) |

---

## 6. 改造順序 + 每一步的量測判準

原則:**先把「記不下來的東西」補上,再談「記得牢不牢」。** 耐久性(fsync)排在中段,
理由是 D7-07 的實測 —— 現在並沒有在掉資料。

| # | 做什麼 | 為什麼排這裡 | effort | 量測判準(怎麼量才算改對) | 改壞了怎麼退 |
|---|---|---|---|---|---|
| 1 | **毫秒時戳 + `request_id` + 日內序號 `n` + `trade_date`**(D7-02 / D7-05 / D7-14 + Q2) | 一行改動就把秒解析度、配對歧義、丟行偵測、夜盤日界四個問題一起解;而且零讀者 = 零風險。**後面每一步的驗證都要靠它** | S | ① `PYTHONUTF8=1 python -c` 掃當日檔:`n` 連續無缺口;② pre/post 以 `rid` 配對率 = 100%(現況 98.5%);③ 秒內配對的 `lat_ms` 出得來 p50/p95/p99;④ 實測確認 `_record()` 仍 ≤ 6 µs(現 4.1) | `git revert` 單一 commit;新欄是 additive,舊行照樣讀得動 |
| 2 | **`result.seq_no` 依 action 分流**(D7-03) | 在任何人寫對帳程式之前修掉,否則錯誤會被複製進工具 | S | 隔日 audit 檔:`action=="cancel"` 的行 `result.seq_no` 恆 `null`、`result.message` 仍含原文;`pytest tests/capital/test_client.py -q` 全綠 | 單 commit revert |
| 3 | **成交列落檔 `fills-YYYYMMDD.jsonl`**(D7-01) | 這是「能不能對帳」的唯一關鍵。必須排在 #4 常開 handle **之前完成設計、之後才啟用**(它跑在 COM 執行緒上,不能用 183 µs 的寫法) | M | ① 隔日收盤:`wc -l data/audit/fills-*.jsonl` ≈ log 裡 `status=成交` 的行數(2026-09-11 基準:35);② 逐筆 price 非 null;③ **COM 執行緒不變慢**:`grep "balance 鏈" logs/` 的「自成交回報到達起 N ms」p95 不比前一日增加 > 2 ms | 一個 env 旗標關掉寫入(預設開),回到只寫 log |
| 4 | **常開 handle + `os.fsync` + 關機 close**(D7-06) | 把 #3 的每則回報成本從 183 µs 壓到 3 µs,順手拿到真 durable | M | ① 在**真目錄** `data/audit` 重跑 `bench_fsync.py`,確認 p99 < 1 ms(scratchpad 基準 572 µs);② `tests/server/test_shutdown_budget.py` 全綠(關機預算契約);③ 關機後 `lsof`-等價確認無殘留 handle;④ 送單端到端 p50(#1 的 `lat_ms`)增幅 < 0.5 ms | handle 改回 per-call open(兩行) |
| 5 | **`sent` 區塊(實際送出欄位,帳號遮罩)**(D7-04 + D7-15) | 有了 #1 的 rid 才好把 COM 側的東西接回來 | M | 隔日 audit:期貨 order 行的 `sent.contract` 是具體月份(如 `TMFI6`)不是 `.HOT`;市價單 `sent.bstrPrice == "M"`;`sent.account` 形如 `****0270` | 移除 `sent` 欄(additive) |
| 6 | **`atomic_write_*` replace 前 fsync**(D7-12) | 獨立於下單鏈,但它保護的是整日訊號檔,單次損失量級最大 | S | ① `pytest -q` 全綠;② 量一次 `atomic_write_bytes` 對 300 KB 的成本(預期 +0.3–2 ms),確認 13:40 回填 worker 的總時間增幅 < 50 ms;③ `copycat validate` PASS | 拿掉兩行 |
| 7 | **開機讀當日 audit 回灌價格別**(D7-11) | 審計檔的第一個程式讀者,順便驗證 #1–#5 的 schema 真的可用 | M | 盤中重啟後 `curl /api/capital/orders \| jq '[.orders[].price_type] \| map(select(.!=null)) \| length'` > 0(現況重啟後恆 0) | 啟動旗標關掉回灌 |
| 8 | **`signal_id` 打通訊號↔下單**(D7-08) | 影子期結束前要有,否則兩本帳對不起來 | M | 從 `data/signals/*.jsonl` 取一個政策列 `id`,在 audit 找得到同 `signal_id` 的 order 行;前端 `useCapital` 送得出去(`npm test` + `npx tsc -b`) | wire 欄是 optional,兩邊各自可退 |
| 9 | **審計健康度上 `/api/health`**(D7-10 / D7-13 / FM-08) | 把「審計自己壞了」變成看得見 | S | `curl /api/health \| jq '.audit'` 有 `{lines_today, write_failures, last_ts}`;人為讓目錄唯讀 → `write_failures` 遞增且送單回 500 `AUDIT_WRITE_FAILED` | 移除該區塊 |
| 10 | **收盤後審計異地複本**(D7-16 / FM-15) | 純營運,最後做 | S | 每交易日 13:40 後 `data/audit/capital-YYYYMMDD.jsonl` 在第二個位置有 byte-identical 複本(`fc /b` 或 sha256 比對) | 停掉排程 |

**刻意不排進去的**:D7-19(報價快照)—— 它是新功能,要走 `/feat` + grilling,
而且它會引入 `capital/` → `stock_engine` 的相依,不該夾在這批裡順手做。

---

## 7. 工具選型

| 工具 | 用在哪 | 為什麼 | 取捨 | 結論 |
|---|---|---|---|---|
| `uuid.uuid4().hex[:16]` + `contextvars` | `request_id` 貫穿各階段 | stdlib、零相依;`contextvars` 讓 rid 不必穿參數 | 無 | **建議導入** |
| `os.fsync` + 常開 append handle | `audit.py` | 實測 308 µs vs 現況 184 µs;真 durable | 關機要 close(進 `shutdown_budget` 契約);fsync 尾巴受磁碟影響 | **建議導入**(排第 4) |
| `time.perf_counter_ns()` 分段時戳 | `_execute_write` | 實測 0.1 µs;是後面一切優化的前提 | 審計行變大 ~100 bytes | **建議導入**(與 B10 F-10 同案) |
| `datetime.isoformat(timespec="milliseconds")` | `client.py:336` | **實測與 seconds 同價(2.5 µs)** | 無 | **建議導入(零成本)** |
| 日內單調序號 `n` | `audit.py` 鎖內遞增 | 讓「掉行」從零訊號變成可偵測 | 需要跨日 reset(與檔名同源) | **建議導入** |
| `orjson` / `msgspec` | 審計序列化 | — | 實測 `json.dumps` 只佔 183 µs 的 1.6%;且審計檔是給人讀的,orjson 的 compact 輸出更難 grep | **不建議** |
| `sqlite3`(stdlib)當交易帳本 | 取代 / 補強 JSONL | 有 WAL、有 index、有交易語意、可以查詢;stdlib 零相依 | 失去「用 `grep`/`tail` 直接看」的特性;需要 schema migration 紀律;**且 append-only JSONL 正是 §7 閘三的字面要求** | **有條件導入**:JSONL 留作 append-only 真相源,**另**建一個由 JSONL 重建的 sqlite 作為查詢/對帳視圖(單向、可丟棄、可重建)。不要拿 sqlite 取代 JSONL |
| `aiofiles` | 審計 async 寫 | 內部也是丟 thread pool,不解 FM-10 | 多一層抽象 + 新相依 | **不建議** |
| `logging.handlers.QueueHandler` | 把 reply log 移出 COM 執行緒 | 若做 D7-01(成交列)後 COM 執行緒 IO 變重,這是 stdlib 的標準解 | 弱化 `_Tee` 的「crash 當下已落盤」設計意圖 | **有條件**:等 D7-01 的量測(判準 #3)顯示 COM 執行緒真的變慢再說 |
| `hashlib` 行級 checksum | 審計完整性 | 偵測人為編輯 | 對「防自己手滑」有用,對「防丟行」序號就夠了;每行多 ~20 µs | **不建議(現階段)**:先做序號,真的需要防竄改再說 |
| `watchdog` / 檔案監控 | 審計異地複本 | — | 每日一次的複製用 Windows 排程 / `run.ps1` 收尾就夠 | **不建議** |
| `numpy` / `polars` / `pyarrow` | — | 這一區零數值批次運算,全是 dict/字串/檔案 syscall | — | **明確不建議** |

---

## 8. 這裡不要動(反向結論)

| 位置 | 為什麼不要動 |
|---|---|
| `audit.py` 的 `_audit_lock` 序列化 | 它解的是「Windows 並發 append 撕裂行」這個正確性問題(design R2-4),不是效能結構。實測 183 µs 的成本裡它佔 < 1%。拿掉 = 換一個零訊號的資料損壞模式 |
| `audit.py` 的「前置寫不進去 = 拒單(500 `AUDIT_WRITE_FAILED`)」 | 這是 §7 閘三的核心不變量:**錢沒動,寧可整筆失敗**。任何「加個 try/except 讓它別擋交易」的提案都是在拆安全閘。前端 `trade-text.ts:18` 有對應文案,是完整的錯誤契約 |
| `client.py:349-355` 後置失敗只 log 不 raise | 反向的不變量,同樣是對的:單已經送進群益,回報成失敗會誘發重送。要補的是**可觀測性**(D7-10),不是改行為 |
| `client.py:889-902` 的 `shield` + `_on_late_result` | 「timeout 不可 cancel 底層 fut、晚到結果要能落審計」是 review B1 打磨出來的。22 天 0 次觸發不代表它沒用 —— 它是保險絲 |
| `json.dumps` 的預設 separators / `ensure_ascii=False` | 實測佔 1.6%。這個檔的**唯一讀者是人**,可讀性 > 幾十 bytes(D7-17) |
| `store` 完全不持久化這個決定 | ConnectByID 重播是對的設計 —— 自己存一份委託狀態等於多一個會跟券商分岔的真相源,而分岔是零訊號的。要補的是**成交流水**(append-only 事實),不是**狀態快照** |
| `store.clear()` 不清 `_price_types` | docstring 已經解釋過了:它是送單意圖不是回報事件。動它 = 市價標籤在重連後全滅 |
| `_lot_unit` / `_FILL_KIND` / `_CLOSE_MAP` 三張表 | CLAUDE.md §4 的跨語言契約。任何持久化重寫要逐字保留這些字面值(「張/口/股」/「無券」/ 回補單種) |
| `fileio.py` 三支 helper 的 newline 語意分工 | 檔頭已經寫明「不可互換」。加 fsync 時只加 fsync,不要順手統一 newline |
| `factory.py:111` 的 `CAPITAL_AUDIT_DIR` → `TXO_AUDIT_DIR` → `data/audit` 三段 fallback | env 語意契約(CLAUDE.md §1),`server/verify.py:47-48` 有讀者 |

---

## 9. Open questions

1. **群益的「當日 backlog」是哪一種日界?** 夜盤 22:00 下的單,隔日 05:00 重啟時
   `SKReplyLib_ConnectByID` 會不會重播?repo 內無樣本。決定 D7-05 的檔名到底該用哪一種日。
2. **`data/audit` 這個目錄有沒有被 Defender 即時保護 / 任何同步工具盯著?**
   決定 D7-06 的 fsync p99 能不能接受(scratchpad 量到的 572 µs 不一定可移植)。
3. **user 對「對帳」的實際期待是什麼?** 三種很不一樣:(a) 盤後自己核一下有沒有下錯單;
   (b) 每月與群益對帳單逐筆核;(c) 餵給策略績效歸因。(a) 現況勉強夠,(b)(c) 差得遠。
4. **成交列要記多細?** 只記 parse 後的欄位,還是連 48 欄的 `raw` 原文一起?
   raw 每則 ~200 bytes × 90 則/天 = 18 KB/天,完全負擔得起,而且它是**唯一**能在
   parser 改版後重新解讀的東西。傾向全記,但要 user 拍板(它含帳號)。
5. **`request_id` 有沒有辦法送進群益、讓回報帶回來?** `STOCKORDER` / `FUTUREORDER`
   有沒有 user-defined 欄位(B10 open question #3,`docs/research/2026-07-28-skcom-typelib.md`
   有 typelib 全表)。有的話對帳可以做到閉環;沒有的話只能本地 heuristic。
6. **影子期(2026-09-08 起四週)結束時要用什麼對決兩本帳?** 如果答案是「訊號 × 實際下單」,
   D7-08 必須在那之前落地,否則對決要靠人眼比對時刻。
7. **審計檔要不要離開這台機器?** 這牽涉帳號資訊外流(即使遮罩),需要 user 拍板。
