# C1 — TC4 無上限併發重評(實測報告)

- 日期:2026-09-13(**星期日**,台股與台期交皆休市 —— 正是 `X3-concurrency.md` §9 M4 要求的「非交易時段」)
- 環境:Windows 11 Home 10.0.26200、Python 3.13.13、pyzmq 27.2.0 / libzmq 4.3.5
- 拋棄式 venv:`…/scratchpad/venvs/C1/`(只裝 pyzmq;**專案 .venv 全程未碰**)
- 產物目錄:`…/scratchpad/verify-bakeoff/`(腳本 `probe_0*.py` / `bench_0*.py`,原始輸出 `out_*.txt`)
- **TC4 桌面 app 當時是開著的**(port 50774 LISTENING,PID 22260),prod server 也跑著
  (PID 20776,`git_sha=caca1d30`,`started_at=2026-09-11T09:05`,5 條 ESTABLISHED = 五條 session)
- repo 零改動、零 git 操作、零下單。

## 0. 一句話結論

**user 的新事實是真的,但它證明的是「TC4 的併發*許可*無上限」,不是「TC4 的併發*吞吐*無上限」。**
實測:8 條同帳號 session 全部登入成功(許可 OK),但 **TC4 桌面 app 內部把「目錄查詢 + 歷史備妥」
排在一條全域佇列上,跨 session 序列**(吞吐 NO)。因此 X3-02 的修法方案 1(多開 REQ session)
**被實測駁回**;方案 2(優先權佇列 + 在飛上限)的收益**不依賴** TC4 的併發度,實測互動延遲 p95
332 ms → 17 ms(19.5×)。

而本輪最大的意外:**目前一次冷日 K 取數的 153 ms 裡,150.5 ms 是我們自己的 `time.sleep(0.15)`**
——TC4 真正備妥只要 ~15–40 ms。這是一顆常數,不是架構問題。

---

## 1. 題目 1:`api.lock` 的真實角色(逐一用原始碼證明)

### 產生點

`spikes/TCPY/tcoreapi_mq.py:11`

```python
class TCoreZMQ():
    def __init__(self,APPID,SKey):
        self.context = zmq.Context()
        ...
        self.lock = threading.Lock()      # 就是 copycat 口中的 api.lock
```

`self.socket` 在 `Connect()` 內建立(`self.context.socket(zmq.REQ)`),**一個 `TCoreZMQ` 實例只有一顆 REQ socket**。

### (a) 保護 ZMQ REQ 的 lockstep 協定 —— **成立,且是主要理由**

wrapper 的**每一支**電文方法都是同一個形狀:

```python
self.lock.acquire(); self.socket.send_string(...); message = self.socket.recv(); self.lock.release()
```

決定性證據是 **KeepAlive 執行緒共用同一顆 socket**:

```python
# tcoreapi_mq.py:KeepAliveHelper.ThreadProcess
if findText == None: continue
objZMQ.Pong(session, "TC")      # 另一條執行緒,進去就 self.lock.acquire() + 用 self.socket
```

`Connect()` 在 LOGIN 成功後**無條件** `CreatePingPong(...)` 起這條執行緒。所以從連線建立的那一刻起,
**至少兩條執行緒共用一顆 REQ socket**。ZMQ REQ 是嚴格 send→recv 交替的狀態機,沒有這把鎖,
PONG 的 send 會插進查詢的 send/recv 之間 → EFSM 違規或回應錯配。**這把鎖是協定強制的,拿不掉。**

### (b) 保護 wrapper 的共用狀態 —— **成立,但與 (a) 是同一件事**

wrapper 唯一的共用可變狀態就是 `self.socket`(和 `self.m_objZMQKeepAlive`)。`Connect()` 也持鎖跨
「建 socket → connect → LOGIN → recv」。copycat 側 `tc4.py::_disconnect_locked` 的註解把這一點寫得最白:

> wrapper 的 KeepAlive `Pong` 取同一把鎖、用同一顆 REQ socket —— 不持鎖就 close socket
> 等於兩條執行緒同時碰 ZMQ socket(未定義行為)。

### (c) 限制對 TC4 的併發 —— **不成立**

- 這把鎖是 **per-`TCoreZMQ`-instance** 的 `threading.Lock`,在**行程內**、**每條 session 各一把**。
  它在結構上不可能限制「對 TC4 的全域併發」——prod 現在就有 5 把這種鎖各自獨立跑。
- 原始碼中**沒有任何一處**提到 TC4 端有併發配額。copycat 自己的四處註解
  (`app.py:127`、`tc4.py:833`、`tc4.py:407`、`signal_hub.py:836`)講的全是「同一條 session 上排隊」。
- 實測 P1:**8 條同帳號並發 LOGIN,8/8 成功**(見 §2)。

### (d) 以上皆是?—— **(a)+(b) 是,(c) 不是**

**結論:`api.lock` 是 ZMQ REQ 協定強制的 socket 互斥鎖,不是對 TC4 的節流閥。**
所以 user 的新事實在這一層**確實派得上用場**:協定上沒有東西阻止我們開 N 顆 REQ socket。
真正的問題出在下一層(TC4 桌面 app 自己),見 §3。

---

## 2. 題目 3:同帳號能不能並發多次 LOGIN?—— **能,實測 8/8**

腳本 `probe_01_login_fanout.py` / 原始輸出 `out_probe_01.txt`

```
== 並發 LOGIN N=8 ==
全部同時發出 → 牆鐘 23.7 ms,成功 8/8
  L0: Success='OK' SubPort=56942 Session=ebbd397f60 login=0.7 ms
  L1: Success='OK' SubPort=56942 Session=d293e9492e login=1.3 ms
  ...(略)...
  L7: Success='OK' SubPort=56942 Session=e34647f575 login=4.2 ms
  相異 SubPort 數 = 1 → ['56942']
  相異 SessionKey 數 = 8
== 維持 20 s,看 PING/PONG 是否每條都收得到 ==
  L0..L7: pong=1(每條都收到並回了 PING)
```

- 全部用 `TC4_APPID="ZMQ"` + `TC4_SKEY=8076c98…`(`copycat/tc4common.py` 的同一組憑證)。
- **零 session token 互斥**:8 把互異 SessionKey 同時有效,20 s 內每條各自收到 PING 並 PONG 成功。
- 這其實 prod 早就在做了:`app.py` 的 `_default_source` / `_default_stock_source` / `_default_index_source`
  / `_default_futures_source` / `_default_corr_source` = **5 條並發 session**,`tc4-market-facts` skill
  也記過「Ctrl+C 後五個 `RemoveLoginInfo`」。本次只是把上界往上推到 8 並確認沒有隱藏閘。

### 附帶發現:**所有 session 共用同一個 SubPort**

8 條 session 拿到的 `SubPort` **全部是 56942**(同一個)。這逐字印證 `tc4-market-facts` 的
「推播是單一 PUB port 廣播,所有 session 都收得到所有 symbol」。
→ **多開一條 session 不等於多一條推播流,而是多一份「把同一條流再解一次」的成本。** 見 §5。

---

## 3. 題目 5 的核心風險先驗:TC4 桌面 app 自己是不是瓶頸?—— **是,而且是決定性的**

### 3.1 P2:重目錄查詢在 TC4 端**全域序列**

腳本 `probe_02_req_concurrency.py` / 輸出 `out_probe_02.txt`。
工作負載刻意選 **refcount-free** 的 `QUERYALLINSTRUMENT`(不送 SUBQUOTE,對 prod 訂閱 key 零影響)。

單發校準(一條 session、序列):

| 請求 | 中位延遲 |
|---|---|
| `QUERYALLINSTRUMENT Type=Fut` | **2458.8 ms** |
| `QUERYALLINSTRUMENT Type=Fut2`(= `list_stock_futures`) | **3318.9 ms** |
| `QUERYALLINSTRUMENT Type=Opt`(= `list_series`) | **1404.3 ms** |
| `QUERYINSTRUMENTINFO` | **0.671 ms**(p95 0.931 ms) |

固定總工作量 6 發 `Fut2`,lane 數 K 遞增:

| K | 牆鐘(s) | 加速比 | 每發 p50 | 每發 p95 |
|---|---|---|---|---|
| 1 | 19.588 | 1.00x | 3280 ms | 3302 ms |
| 2 | 19.120 | 1.02x | 6388 ms | 6407 ms |
| 3 | 19.731 | 0.99x | 9865 ms | 10264 ms |
| 4 | 18.831 | 1.04x | 12521 ms | 12529 ms |
| 6 | 18.910 | 1.04x | 12483 ms | 18908 ms |
| 8 | — | — | 撞 20 s RCVTIMEO(`zmq.error.Again`) | |

**總牆鐘幾乎不變、每發延遲隨 K 線性放大 —— 這是單伺服器佇列的教科書指紋。**
6 發不論怎麼分配 lane,總是 ~19 s。多開 lane 沒有創造任何吞吐,只是把 6 個人從
「排一列」改成「擠在門口」。

### 3.2 P3:但**輕**請求跨 session 完全不被擋

腳本 `probe_03_heavy_blocks_light.py` / 輸出 `out_probe_03.txt`

```
== 基線:沒有重請求時的輕請求延遲 ==
  QUERYINSTRUMENTINFO(閒置)p50 0.740 ms  max 1.261 ms

== 實驗:session A 發 Fut2 重查詢,同時 session B 發輕請求 ==
  第 1 輪:重請求    3298 ms | 另一 session 輕請求      1.2 ms
  第 2 輪:重請求    3334 ms | 另一 session 輕請求      1.6 ms
  第 3 輪:重請求    3573 ms | 另一 session 輕請求      1.7 ms
  第 4 輪:重請求    3572 ms | 另一 session 輕請求      1.5 ms
  第 5 輪:重請求    3336 ms | 另一 session 輕請求      1.8 ms

== 對照:同一條 session 上發輕請求(必被 api.lock 擋)==
  第 1 輪:同 session 輕請求   2901.3 ms
  第 2 輪:同 session 輕請求   3060.7 ms

  閒置輕請求          p50 =    0.740 ms
  另一 session 輕請求  p50 =      1.6 ms  (2× 閒置)
  同 session 輕請求    p50 =   2981.0 ms  (4029× 閒置)
```

**這一格是 X3-02 的 HIGH 評級第一次被量化:同 session 的 head-of-line = 2981 ms,
跨 session = 1.6 ms,差 1800×。** 所以 X3-02「api.lock 讓平行變假」這件事**本身是對的**。

但接下來的實驗把「多開 lane 就能解」這個推論打掉。

### 3.3 P10:目錄查詢**跨 session 擋住歷史備妥** —— 分 lane 救不了

腳本 `probe_10_confirm_global_block.py` / 輸出 `out_probe_10.txt`。
三條互異 session:CAT 發目錄查詢、HIST 發冷日 K、LITE 發輕請求。

```
== 0. 基線:沒有目錄查詢時,冷日 K(20 ms 輪詢)==
     43.6 ms / 輪詢 3 次 / 50 根
     43.3 ms / 輪詢 3 次 / 50 根
     24.2 ms / 輪詢 2 次 / 50 根

== 1. 目錄查詢在 lane CAT 上跑時,另兩條 lane 的表現 ==
  第 1 輪: 目錄    3102 ms | 日 K    3052 ms(輪詢 2 次, 50 根) | 輕請求   9.86 ms
  第 2 輪: 目錄    3099 ms | 日 K   15014 ms(輪詢 572 次, 0 根) | 輕請求   1.32 ms
  第 3 輪: 目錄    3152 ms | 日 K    3101 ms(輪詢 2 次, 50 根) | 輕請求   1.34 ms

  無目錄查詢時 冷日 K        =     43.3 ms
  目錄查詢中   冷日 K(別條 lane)=   3101.3 ms  (72× 基線)
  目錄查詢本身                 =   3102.4 ms
  目錄查詢中   輕請求(別條 lane)=     1.34 ms
```

(第 2 輪的 15 s 是 symbol 2867 在該窗沒資料,撞我設的 15 s 上界 —— 與本題無關的雜訊,
逐字對應 `_collect_history` 註解說的「TC4 對查無此檔不是快速失敗」。)

**日 K 的完成時刻 = 目錄查詢的完成時刻 + ~50 ms,而且它在另一條 session 上。**
P9(`out_probe_09.txt`)的兩種形狀更把這件事釘死 —— 同 lane 與分 lane,日 K 都恰好
比目錄查詢晚 ~105 ms 完成:

| 形狀 | 目錄查詢 | 日 K p50 | 差 |
|---|---|---|---|
| A 同一條 lane | 3171 ms | 3277 ms | +106 ms |
| B 分流到專用 lane | 2935 ms | 3040 ms | +105 ms |

**分 lane 只買到 7%,而那 7% 正好等於兩次目錄查詢本身的時間差 —— 也就是 0。**

### 3.4 TC4 內部的服務模型(由上述三支 probe 推出)

```
                     ┌──────────────────────────────────────────────┐
  REQ(任何 session)  │  TC4 桌面 app                                 │
  ───────────────────►│                                              │
                     │  (1) 輕量 metadata 路徑:真並行                │
                     │      QUERYINSTRUMENTINFO / PONG …             │
                     │      跨 session 互不擋,p50 0.7–1.6 ms         │
                     │                                              │
                     │  (2) 重量資料路徑:一條全域序列佇列             │
                     │      · QUERYALLINSTRUMENT 目錄建構             │
                     │          Opt 1.40 s / Fut 2.46 s / Fut2 3.32 s│
                     │      · 歷史備妥(SUBQUOTE DK/1K/TICKS)         │
                     │          每件 ~8–40 ms                        │
                     │      一發目錄查詢 ≈ 100 件歷史的份量            │
                     └──────────────────────────────────────────────┘
```

**一發 `list_stock_futures`(Fut2,3.3 s)= 把 TC4 的歷史佇列鎖住 3.3 秒,
不論是誰、從哪條 session 發的。**

---

## 4. 題目 4:量出這件事值多少

### 4.1 最大的意外 —— 一次冷日 K 取數的 153 ms 裡,150.5 ms 是我們自己的 sleep

腳本 `probe_05_history_breakdown.py` / 輸出 `out_probe_05.txt`

```
== 1. 逐發拆解(輪詢間隔 = 現況 150 ms)==
  1102(窗 40 日): 首頁輪詢 2 次 / 牆鐘   153.1 ms / 29 根
      REQ 明細: SUBQUOTE=1.07ms  GETHISDATA=0.72ms  GETHISDATA=0.85ms
      → REQ 總和 2.65 ms,其餘 150.5 ms 是我們自己的 sleep
  2002(窗 41 日): …  REQ 總和 1.88 ms,其餘 150.4 ms 是我們自己的 sleep
  2801(窗 42 日): …  REQ 總和 1.81 ms,其餘 150.6 ms 是我們自己的 sleep

== 2. 掃輪詢間隔:首頁真正備妥要多久?==
      輪詢間隔(ms)         平均輪詢次數         首頁備妥牆鐘 p50(ms)
           150          18.50                  152.5
            50          50.75                   52.5
            20         120.75                   22.3
            10         229.25                   23.5
             5         430.25                   37.0
             2         975.75                   17.4
             0        9171.25                   15.5
```

產生點 = `copycat/live/tc4.py:57`

```python
_POLL_BACKOFF_START = 0.15
```

`_collect_history` 第一發 `GETHISDATA` 拿到空頁 → `time.sleep(0.15)` → 第二發拿到 29–50 根。
**TC4 其實 15–40 ms 就備妥了,我們固定多睡 ~130 ms。**

重要的是這個 sleep **不持 `api.lock`**(`_req` 進出各取放一次鎖,sleep 在兩次 `_req` 之間),
所以它不是鎖競爭 —— 它是純粹的延遲浪費,外加白占一個 `to_thread` 的 executor 名額 150 ms。

**但不能直接把它改成固定 20 ms**:P5 的掃描顯示,對「查無此檔 / 該窗無資料」的股號,
2 ms 輪詢會在 10 s 預算內打 975 發 GETHISDATA(× 0.7 ms = **682 ms 的 `api.lock` 佔用**),
現行的倍增退避只打 ~13 發。**正解 = 起點改 20 ms、倍增與 1.0 s 上限一律不動**:
健康路徑 2–3 輪(22–44 ms)結束,壞股號的總輪數只從 ~13 增到 ~18(多 3.5 ms 鎖時間)。

### 4.2 歷史佇列的吞吐上限,以及 lane 數對它的影響

腳本 `probe_11_history_ceiling.py` / 輸出 `out_probe_11.txt`(輪詢 20 ms,只用已知有資料的股號)

| M(同時在飛) | lane 數 | 牆鐘(s) | p50 | p95 | 吞吐 | 成功 |
|---|---|---|---|---|---|---|
| 1 | 1 | 0.044 | 43 ms | 43 ms | 22.9 檔/s | 1/1 |
| 2 | 1 | 0.045 | 44 ms | 44 ms | 44.7 檔/s | 2/2 |
| 2 | 2 | 0.047 | 45 ms | 46 ms | 42.7 檔/s | 2/2 |
| 4 | 1 | 0.069 | 55 ms | 68 ms | 57.6 檔/s | 4/4 |
| 4 | 4 | 0.086 | 55 ms | 82 ms | 46.6 檔/s | 4/4 |
| 8 | 1 | 8.001(註) | 103 ms | 5247 ms | — | 7/8 |
| 8 | 8 | 8.014(註) | 76 ms | 5252 ms | — | 7/8 |
| 16 | 1 | 8.021(註) | 141 ms | 2170 ms | — | 15/16 |
| 16 | 8 | 8.003(註) | 127 ms | 2174 ms | — | 15/16 |
| 32 | 1 | 8.022(註) | 266 ms | 3848 ms | — | 30/32 |
| 32 | 8 | 8.007(註) | 230 ms | 3819 ms | — | 30/32 |

(註)牆鐘被清單裡一檔無資料股號的 8 s 預算綁死,**看 p50 才有意義**。

**判讀**:

- p50 從 M=4 起隨 M 近似線性成長(55 → 76/103 → 127/141 → 230/266 ms)→ 序列佇列,
  每件服務時間約 **8 ms**。
- **lane 數幾乎沒有差別**:M=8 是 103 vs 76 ms、M=16 是 141 vs 127 ms、M=32 是 266 vs 230 ms。
  八條 lane 相對一條只快 **10–14%**,而且那一點點正是 `api.lock` 在高在飛數下的競爭
  (每發日 K = 1 SUBQUOTE + N GETHISDATA 都要取放鎖)。**離線性加速差了一個數量級。**
- **邊際遞減點約在 M=4**:M 從 1 到 4,吞吐 22.9 → 57.6 檔/s(2.5×);M 再往上只讓 p50 線性變差。

### 4.3 排在 `api.lock` 後面的工作有哪些、各多久

以 stock session 為例(`X3-concurrency.md` §2 列了 8 類),**用本輪實測的單價重算持鎖時間**:

| 工作 | 發數 | 每發持鎖 | 合計持鎖 | 備註 |
|---|---|---|---|---|
| `list_stock_futures`(Fut2 目錄) | 1 | **3319 ms** | **3319 ms** | 實測;`tc4.py:833` 已警告 |
| `list_series`(Opt 目錄,TXO session) | 1 | **1404 ms** | 1404 ms | 實測 |
| 開機 150 檔 `SUBQUOTE` | 150 | ~0.7 ms | ~105 ms | 由 `QUERYINSTRUMENTINFO` 0.671 ms 代理推估 |
| rollover 全量 UNSUB+SUB | ~300 | ~0.7 ms | ~210 ms | 同上 |
| overlay 冷取(每檔日 K) | 3 | 0.5–1.1 ms | **~2.5 ms/檔** | 實測;**150 ms sleep 不在鎖內** |
| → 進群組 150 檔 overlay | 450 | | ~375 ms | 攤在 5.8 s 牆鐘上 → 鎖佔用率 **~6%** |
| 當日 TICKS 回補(分頁收割) | 數百 | ~0.7 ms | 100–300 ms/檔 | 沿用 2026-07-20 probe 的 3482 發 / max 1.1 ms |
| CDP 基準暖機(`_basis_worker`) | 150 檔 × 3 | ~2.5 ms/檔 | ~375 ms | `basis_gap_secs=0.2` 的 sleep 才是主體 |
| KeepAlive `Pong` | 20 s 一發 | ~0.7 ms | 可忽略 | 實測 PING 約 20 s 一則 |

**關鍵重估:`api.lock` 平常一點都不忙(overlay sweep 期間佔用率 ~6%)。
它唯一會造成傷害的時刻,是有一發「多秒級」REQ 壓在上面 —— 而那只有兩種:
`QUERYALLINSTRUMENT`(1.4–3.3 s)與撞上 RCVTIMEO 的壞連線(10 s)。**

這直接修正了 X3-02 的「所有 TC4 取數序列化」給人的印象:序列化是事實,
但**序列化本身不貴,貴的是隊伍裡那一發 3.3 秒的目錄查詢**;而 §3.3 已經證明
把它搬到別條 lane 也沒用,因為 TC4 內部照樣擋住歷史。

### 4.4 進群組 150 檔 overlay 的系統級換算

| 設定 | 每檔 | 在飛上限 | 150 檔牆鐘 | 相對現況 |
|---|---|---|---|---|
| 現況(150 ms 輪詢 + `Semaphore(4)`) | 153 ms | 4 | **~5.8 s**(由 P9 §5 M=4 實測 25.7 檔/s 外推) | 1.0× |
| 20 ms 輪詢起點 + `Semaphore(4)` | 55 ms | 4 | **~2.6 s**(P11 M=4 實測 57.6 檔/s) | **2.2×** |
| 20 ms 輪詢起點 + 在飛上限 16 | 127 ms | 16 | **~1.2 s**(P11 M=16 p50 外推 126 檔/s) | **4.8×**(推估) |
| 多開 N 條 REQ lane(任何 N) | — | — | **無改善**(P10/P11 實證) | 1.0× |

prod 端側面佐證(`bench_04_prod_overlay.py` / `out_bench_04.txt`):跑著的 server 因為
兩天 uptime 已把 80 檔的 overlay cache 全灌熱,**量不到冷取**;但量到了 cache hit 基線
p50 13.4 ms、以及「背景 20 檔灌入中,互動 K 線請求 181 ms vs 閒置 14 ms(13×)」。
**這一列是 cache-warm 條件下的數字,不能當冷取代表。** 冷取要在 prod 重啟後第一次進群組才量得到。

### 4.5 `basis_gap_secs = 0.2` 是為了保護一把其實不忙的鎖

`copycat/signals_config.py:64` `basis_gap_secs: float = 0.2`,`_basis_worker` 逐檔付一次。
150 檔 = **30 s 純睡眠** + 150 × 153 ms = 23 s → 一輪約 **53 s**。
以實測重算:歷史佇列在 M=4 時 57.6 檔/s,150 檔只要 **2.6 s**。
0.2 s 的逐檔 gap 是在「鎖很稀缺」的假設下訂的;實測顯示那個假設不成立(§4.3 的 6% 佔用率)。
**換成「在飛上限 4、無 gap」約 20×;代價是把 TC4 歷史佇列的深度從 1 拉到 4,
互動型 overlay 的 p50 從 43 ms 變 55 ms(P11 實測),很小。**

---

## 5. 題目 2:REQ 與 SUB 在 wrapper 裡耦合嗎?

### 5.1 耦合是硬耦合,但可以壓到近乎免費

```python
# tcoreapi_mq.py:Connect
if data["Success"] == "OK":
    self.CreatePingPong(data["SessionKey"], data["SubPort"])   # 無條件
# CreatePingPong → KeepAliveHelper.__init__ → 起執行緒 →
#     socket_sub = ctx.socket(zmq.SUB); connect(SubPort); setsockopt_string(SUBSCRIBE, "")
```

- **不能完全不帶 SUB**:沒有 PONG,TC4 的 `ExecuteCheckPingTime` 約 60 s 後 reap 掉這條 session
  (`tc4-market-facts` (c))。所以「純 REQ 通道」必須至少維持 PING/PONG。
- 現況每條 session 有 **2 顆 SUB socket、兩顆都 `SUBSCRIBE ""`**:
  wrapper 的 KeepAlive 一顆 + `tc4.py::_listen_loop` 一顆。prod 5 條 session = **10 顆全收 SUB**。
- **但 PING 有固定 topic**。P6(`probe_06_sub_topics.py` / `out_probe_06.txt`)實地抓下來:

```
SubPort = 56942(所有 session 共用同一個,見 P1)
== 45 s 內收到 4 則,topic 分布 ==
       2  topic='PING'
          樣本: PING:{"DataType":"PING"}
       2  topic='TC.F.CFE.VX.HOT'
          樣本: TC.F.CFE.VX.HOT:{"DataType":"REALTIME","Quote":{"Symbol":"TC.F.CFE.VX.HOT",…
```

→ **`SUBSCRIBE "PING"` 就能讓 libzmq 在訂閱側丟掉其餘全部。**

### 5.2 量:多開一條通道的 SUB 代價

腳本 `bench_08_sub_fanout.py` / 輸出 `out_bench_08.txt`。真實輸入 = P7 從 TC4 PUB 抓下來的
**1742 bytes** 電文(`captured_realtime.json`,`TC.F.CME.CL.HOT`,含五檔 × 10 層)。

```
== 1. 單則電文的 CPU 成本(輸入 = 真實 TC4 電文 1742 bytes)==
  KeepAlive 的 regex 找 PING(未命中)  :    1.235 µs/則
  bytes.decode('utf-8')                 :    0.481 µs/則
  _realtime_msg(find + json.loads + get):   10.622 µs/則

  → 每則電文,現行 5 條 session 的固定重複成本 =
     KeepAlive 5 × (decode 0.48 + regex 1.24) =    8.58 µs
     listener  5 × (decode 0.48 + parse 10.62) =   55.52 µs
     合計 64.10 µs/則;再加一條純 REQ 通道 → +1.72 µs/則(SUBSCRIBE "")

== 2. ZMQ 扇出實測(20000 則,每 500 則一個 PING)==
  A 現況:5 KeepAlive,SUBSCRIBE ""            牆鐘    867.2 ms  各 SUB 實收  20000/20000 則
  B 提案:5 KeepAlive,SUBSCRIBE "PING"        牆鐘     34.9 ms  各 SUB 實收     40/20000 則
  A+ 再加一條純 REQ 通道(6 條,SUBSCRIBE "") 牆鐘   1160.5 ms  各 SUB 實收  20000/20000 則
  B+ 再加一條純 REQ 通道(6 條,SUBSCRIBE "PING") 牆鐘  36.9 ms  各 SUB 實收     40/20000 則

  A → B 加速 24.9x;SUB 實收則數 20000 → 40(libzmq 在訂閱側就丟掉)
  多開第 6 條通道的邊際代價:現況 +293.3 ms / 提案 +2.1 ms(同樣 20000 則)
```

- **多開一條 naive 通道的邊際代價 = 14.7 µs/則**(293.3 ms ÷ 20000);
  改 `SUBSCRIBE "PING"` 後 = **0.105 µs/則**,便宜 **140×**。
- 更有價值的是:**現存 5 條 KeepAlive 全改 `SUBSCRIBE "PING"`,keepalive 路徑的扇出成本
  867 ms → 34.9 ms(24.9×),而且這與多不多開通道完全無關。**
- 量測用 `inproc://`,不是 loopback TCP。TCP 的每 socket 複製成本更高,所以上面的
  「多一條 SUB 的代價」是**低估**;方向不變。

**回答題目 2:能開純 REQ 通道,SUB 拿不掉但可以用 topic 前綴壓到近乎免費。
只是 —— §3 已經證明開了也沒用。**

---

## 6. 題目 5:風險清單

| # | 風險 | 實證狀態 | 說明 |
|---|---|---|---|
| R1 | **TC4 桌面 app 自己是瓶頸** | **已實證成立** | P2 / P10 / P11。目錄查詢 + 歷史備妥是一條全域序列佇列。這條不是「可能」,是「已經是」。 |
| R2 | **額外 lane 死掉會帶走 prod 的 symbol feed** | 已實證機制(skill),本輪未觸發 | `_req` 失敗 → `_dispose` → `api.Disconnect()`,而 `Disconnect()` **不送 LOGOUT**(skill 2026-08-26 實證)→ 該 session 約 60 s 後被 `ExecuteCheckPingTime` reap → 它獨持的 refcount key 歸 0 → **上游退訂整個 symbol** → 同 symbol 其他 key(count 仍 >0)一起斷、之後再 SUBQUOTE 也不重掛。每多一條**會持有任何 key** 的 lane,就多一個獨立的 feed-killer。**唯一安全的多 lane 形狀 = 純 REQ 且只發 `QUERYALLINSTRUMENT`/`QUERYINSTRUMENTINFO`(零 key)** —— 而那正是 P10 證明零收益的那一條。 |
| R3 | 回應配對 / 現有不變式 | 靜態分析 | `_dispose(api)` 比 `self._api is api`、`_connection()` 回單一 `(api, session)`、`_check_stale` 假設一條連線、`_heal_resub` 持 `self._lock`。這些不變式在 `tc4.py` 的四段 docstring 裡被明文寫死(含鎖序 `self._lock → _api_lock → api.lock` 不得反轉)。改成 N lane 要重寫這整組不變式 —— 這是 L 級改動,不是 M。 |
| R4 | **關機預算三方同源**(CLAUDE.md §4) | 靜態分析 | `shutdown_budget.py::TC4_LANE_DEPTH = 2`,`run_grace_secs() = WS_DRAIN + 2 × close_worst_secs() + COM_JOIN + slack = 83 s`;`close_worst_secs()` = 10 + max(20, 24) = **34 s**。每多一條進入既有 lane **串鏈**的 session,就要 +34 s 並同步改 `TC4_LANE_DEPTH`(`tests/server/test_shutdown_budget.py` 含 run.ps1 字面 parity,會機械擋下漏改)。 |
| R5 | `SUBSCRIBE "PING"` 的 topic 假設 | **證據薄弱** | 只觀察到 2 則 PING,topic 皆為字面 `PING`。若 TC4 某版把 PING 的 topic 改掉 → KeepAlive 永不 PONG → 60 s 後全部 session 被 reap → **全站零推播**。這是最高 blast radius 的一條。導入前必須:(a) 連續一個交易日的長窗觀察確認 topic 恆定;(b) 加「N 秒沒收到 PING 就退回 `SUBSCRIBE ""`」的保險絲。 |
| R6 | 本輪所有數字量在**週日閒置 TC4** | 已知侷限 | 盤中 TC4 正在處理 150+ 檔 feed,歷史佇列的服務時間(週日 ~8 ms/件)可能完全不同。已備妥複驗腳本 `RUNME_intraday_recheck.py`,三條判準見該檔檔頭。 |
| R7 | 我用 `QUERYALLINSTRUMENT` 當重請求代表 | 已知侷限,但 P10 已補 | P2 只證明目錄查詢序列;P10 補上「目錄查詢也擋歷史」,P11 補上「歷史彼此也序列」。三者合起來才構成 §3.4 的模型。**未測**:`SUBQUOTE REALTIME` / `UNSUBQUOTE` 落在哪一條路徑(推測是輕路徑,未量)。 |
| R8 | 我完全沒測 trade session(`TradeAPI`) | 未量 | 下單走群益 Capital,TC4 的 `TradeAPI` 在 prod 未用。本報告的結論不涵蓋它。 |

---

## 7. 題目 6:與「單 reader 重構」的關係

### 7.1 正交嗎?—— 資料面正交,控制面不正交

| | REQ 側(本區 C1) | SUB 側(單 reader) |
|---|---|---|
| socket | `api.socket`(REQ),每 session 一顆 | `_listen_loop` 的 SUB + KeepAlive 的 SUB |
| 執行緒 | `to_thread` 的 executor worker | listener 執行緒 × 5 + KeepAlive 執行緒 × 5 |
| 鎖 | `api.lock` / `_api_lock` / `_lock` | 無(listener 是單執行緒迴圈) |

**不正交的那一條線**:`_listen_loop` 是**偵測斷線並驅動重連的那條執行緒**:

```python
except zmq.ZMQError:          # RCVTIMEO 1 s 到期
    self._check_stale(); continue
# _check_stale → self._lock → _rt_request → _req → _ensure_connected(REQ 側)
```

而 `_ensure_connected` 更新的 `self._sub_port` 又反過來讓 listener 重建 SUB socket
(2026-07-20 盤中實證過:不跟隨就是 30 秒無限重連)。
**單 reader 重構把 5 條 listener 收成 1 條時,這 5 條各自的「stale 偵測 + 重連觸發」
必須有新歸屬 —— 這是該重構最容易漏掉、而且漏了零錯誤訊號的一點。**

### 7.2 先後順序 —— 單 reader 在先,而且本區建議不做 REQ lane

- 單 reader 的收益是**實測且確定**的:每則 REALTIME 電文的重複解碼 **64.10 → 11.10 µs(5.8×)**
  (1 條 listener + 5 條 `SUBSCRIBE "PING"` 的 KeepAlive),再加上 ZMQ 從 10 顆 SUB socket
  收成 2 顆的傳輸成本。
- 本區建議的 REQ lane 收益是**實測且為零**。
- 另一個順序理由:P1 證明所有 session 共用同一個 SubPort,**多開通道會讓 SUB 扇出更糟**
  (+14.7 µs/則)。所以萬一日後真要多開通道,也該先做完單 reader + `SUBSCRIBE "PING"`,
  讓「多開一條」的邊際成本從 14.7 µs 降到 0.105 µs 再說。

---

## 8. 對 X3-02 原文的逐條回應

> X3-02:「所有 TC4 取數序列化在一 session 一顆 REQ socket + 一把 `api.lock` 上,
> `Semaphore(4)` 與 20 個 executor worker 都是假平行」—— 評 critical

- **「序列化」= 事實**(原始碼證明,§1)。
- **「假平行」= 事實,而且本輪第一次量化**:同 session head-of-line 2981 ms vs 跨 session 1.6 ms(§3.2)。
- **「這條是第一個要先解的:在它之上做的任何平行化都是假的」= 需要修正。**
  真正的序列化點在 TC4 桌面 app 裡,不在 `api.lock`。解掉 `api.lock` 之後平行化**還是假的**(§3.3 / §4.2)。
- **修法方案 1(多開一條歷史專用 session)= 實測駁回。**
  原文寫「這是假說,不是事實 —— 必須先跑一次受控 probe(§8 M4)」。**M4 已經跑了**(P4/P9/P10/P11):
  假說為偽。順帶:M4 原本擔心的「歷史 session 會不會搶走 realtime feed」,在 P1 的
  「單一 PUB port 廣播」之下不是推播被搶,而是 R2 的 refcount reap 風險。
- **修法方案 2(優先級佇列)= 實測支持,而且收益不依賴 TC4 的併發度。**
  `bench_03_headofline.py` / `out_bench_03.txt`(服務時間 8 ms = P11 實測的歷史佇列服務時間、
  背景 150 發、互動 20 發、N=4):

```
### 情境 1:TC4 端序列(= 本輪實測成立的那個)
client 形狀                        總牆鐘(s)  互動 p50  互動 p95  互動 max
A 現況:1 lane + FIFO 鎖              1.45     247ms    332ms    342ms
B 方案2:1 lane + 優先權佇列            1.46      13ms     17ms     17ms
C 方案1:4 lanes + FIFO               1.44     243ms    328ms    338ms

### 情境 2:TC4 端可平行(假設)
A 現況:1 lane + FIFO 鎖              1.46     247ms    333ms    343ms
B 方案2:1 lane + 優先權佇列            1.46      14ms     17ms     17ms
C 方案1:4 lanes + FIFO               0.48       9ms     76ms     86ms
```

**情境 1(= 現實)下:優先權佇列把互動 p95 從 332 ms 壓到 17 ms(19.5×),
多 lane 一點用都沒有(328 ms)。**

但有一個前提:**優先權佇列只有搭配「在飛上限」才有效**。若 client 把 150 發一次全倒進
TC4,排序權就落到 TC4 的 FIFO 手上,client 的優先權佇列被架空。
現行的 `overlay_sem = asyncio.Semaphore(4)` 正好就是那個上限 —— **要做的是保留這個上限、
把它後面的等待隊伍從 FIFO 換成優先權序,而不是把上限拆掉。**

---

## 9. 建議(依「收益 ÷ 風險」排序)

| 排名 | 動作 | 位置 | 實測收益 | 風險 |
|---|---|---|---|---|
| 1 | `_POLL_BACKOFF_START` 0.15 → 0.02,**倍增與 1.0 s 上限不動** | `copycat/live/tc4.py:57` | 冷歷史取數 153 → 43 ms(3.5×);進群組 150 檔 5.8 → 2.6 s(2.2×) | 極低。壞股號的輪詢從 ~13 發增到 ~18 發(+3.5 ms 鎖時間)。零契約、零跨檔。 |
| 2 | 單 reader 重構 + 5 條 KeepAlive 改 `SUBSCRIBE "PING"` | `tc4.py::_listen_loop` + `spikes/TCPY/tcoreapi_mq.py` | 每則電文 64.10 → 11.10 µs(5.8×);keepalive 扇出 24.9× | **中**:R5(PING topic 假設)要先長窗驗證 + 保險絲;§7.1 的重連觸發歸屬必須處理。 |
| 3 | `overlay_sem` 後面換優先權序(互動 > 背景 sweep),**保留在飛上限** | `app.py:547` + `_req` 入口 | 互動 p95 332 → 17 ms(19.5×,模型) | 中:要改 `_req` 所有 caller 的 await 形狀(它們現在是 `to_thread` 裡的同步阻塞形)。 |
| 4 | 在飛上限 4 → 8~16(搭配 #1) | `app.py:547` | 150 檔 2.6 → 1.2 s(推估) | 低,但會把互動 overlay p50 從 43 推到 127 ms。**與 #3 同時做才安全。** |
| 5 | `basis_gap_secs` 0.2 s 逐檔 gap → 在飛上限制 | `signals_config.py:64` | 一輪 53 s → ~3 s(推估,~20×) | 低。原本的 gap 是為了保護一把其實只有 6% 佔用率的鎖。 |
| — | **多開 REQ lane(X3-02 方案 1)** | — | **0(實測)** | 高(R2/R3/R4)。**不建議。** |

---

## 10. 腳本與原始輸出索引

全部在 `C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\verify-bakeoff\`

| 檔 | 用途 | 輸出 |
|---|---|---|
| `tc4lane.py` | 共用最小 TC4 lane client(refcount-free 電文專用) | — |
| `probe_01_login_fanout.py` | 8 條並發 LOGIN / SubPort 共用 | `out_probe_01.txt` |
| `probe_02_req_concurrency.py` | 目錄查詢的 K-lane 併發對決 | `out_probe_02.txt` |
| `probe_03_heavy_blocks_light.py` | 重請求擋不擋輕請求(跨 / 同 session) | `out_probe_03.txt` |
| `probe_04_history_lanes.py` | 歷史取數的多 lane 初探 | `out_probe_04.txt` |
| `probe_05_history_breakdown.py` | 153 ms 的逐發拆解 + 輪詢間隔掃描 | `out_probe_05.txt` |
| `probe_06_sub_topics.py` | PUB topic 形狀(PING / REALTIME) | `out_probe_06.txt` |
| `probe_07_capture_full.py` | 抓完整 1742 bytes 真實電文 | `captured_realtime.json` |
| `probe_09_lane_split.py` | 目錄查詢分流 lane 的收益 | `out_probe_09.txt` |
| `probe_10_confirm_global_block.py` | **樞紐**:目錄查詢跨 session 擋歷史 | `out_probe_10.txt` |
| `probe_11_history_ceiling.py` | 歷史佇列吞吐上限 × lane 數 | `out_probe_11.txt` |
| `bench_03_headofline.py` | 優先權佇列 vs N lane(本機 ZMQ 模型) | `out_bench_03.txt` / `.json` |
| `bench_04_prod_overlay.py` | prod HTTP 熱路徑(cache-warm) | `out_bench_04.txt` |
| `bench_08_sub_fanout.py` | SUB 扇出重複解碼成本 | `out_bench_08.txt` |
| **`RUNME_intraday_recheck.py`** | **交給 user 盤中/盤後自己跑的複驗**(三條判準) | — |

### 安全性聲明

所有 probe 對 prod 的 TC4 訂閱 refcount **零影響或影響已隔離**:

- P1/P2/P3/P6/P7/P10 的輕路徑:只送 `LOGIN` / `PONG` / `QUERYALLINSTRUMENT` /
  `QUERYINSTRUMENTINFO` / `LOGOUT` —— **零 SUBQUOTE**。
- P4/P5/P9/P10/P11 的歷史路徑:只對 **prod 自選 80 檔以外**的股號建 `DK` key
  (corr 11 腿全是期貨,零交集),且窗刻意用 200–900 日(prod `fetch_daily_bars` 是 40 日)
  → key `symbol|DataType|StartTime|EndTime` 必為互異。
- **完全沒有送過 `SUBQUOTE REALTIME` / `UNSUBQUOTE`。**
- 每支腳本收工 `LOGOUT` → `close socket` → `term context`。
- 執行時段 = 星期日(台股 / 台期交日盤皆休市)。

### 未量(不要當成量過)

- 盤中(TC4 忙碌)條件下的所有數字 → `RUNME_intraday_recheck.py`。
- `SUBQUOTE REALTIME` / `UNSUBQUOTE` 落在 TC4 的輕路徑還是重路徑。
- `TradeAPI`(TC4 下單通道)—— prod 不用,本報告不涵蓋。
- 進群組 150 檔**冷** overlay 的 prod 端到端數字(cache 已被 2 天 uptime 灌熱;
  要在 prod 重啟後第一次進群組才量得到)。
- PING topic 是否恆為字面 `PING`(只觀察到 2 則)。
