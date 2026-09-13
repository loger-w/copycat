# V2-verify-order —— 複驗:下單報告

複驗對象:`C:/side-project/copycat/docs/research/2026-09-13-order-report.md`
支撐材料:`docs/research/2026-09-13-order-signal-scan/D1-order-latency-chain.md`
日期:2026-09-13。立場:**懷疑**。這是真錢路徑,錯誤結論代價最高。

所有腳本留在本目錄,可重跑:
`reagg_audit.py` / `robust.py` / `outliers.py` / `chain.py` / `artifact.py` / `clean.py` /
`corr1019.py` / `bench_audit.py` / `proxybench.mjs`。
執行環境:系統 Python 3.13.13(`C:\Users\USER\AppData\Local\Programs\Python\Python313`)+
Node v24.13.0。**專案 `.venv` 全程唯讀**(只讀 typelib 與 node_modules,零安裝、零寫入)。
**repo 零改動、server 未啟動、零下單。**

---

## 0. 總判決

**這份報告的「事實」層可信,「推論」層有三處會誤導改造方向,「順序」層有一處證據就在自己的
log 裡卻沒讀。**

- 我用自己的配對邏輯重跑 1,075 列審計,**89.6 ms / 536 對 / delta 直方 {0:494,1:39,2:1,3:1,4:1}
  逐字重現**。回流鏈 179 條、p50 1,940 ms、max 6,639 ms 也逐字重現。**算術沒問題。**
- 但 89.6 ms 的 **95% bootstrap CI = [61.6, 119.4] ms**,而且 **0.56% 的樣本(3 筆)貢獻
  18.8% 的總質量**。報告用三位有效數字陳述一個 ±33% 的量,並在其上建立
  「拒單比成功慢一倍」「7.6% 長尾」兩條**都撐不住**的推論。
- 兩條 critical:**C2 完全成立且比報告寫的更糟**(曝險窗無時間上界);
  **C1 的「死碼 / 修綁定」是錯的診斷** —— 綁定逐位元正確,Step 1a 照著做會是 no-op。
- **最大的一條漏網**:回流鏈的整條尾巴 = `SK_ERROR_QUERY_IN_PROCESSING`(1019),
  log 裡 **310 筆**,與庫存段耗時的關係是**每一次 1019 精準加 1,060 ms**,
  庫存段 ≥ 2 s 的 25 條裡 **23 條(92%)有 1019**。報告把「三段並行」列為 Step 4 的候選方向、
  並說「要先用一天 prod 驗」—— 那一天的資料已經躺在 logs/ 裡 22 天了,而且**結論是相反的**。

**能不能拿去當改造依據?** §1(送單不要優化 Python)、§2(回流鏈是最大標的)、
C2、§6 不要動清單 —— 可以。
**§3 的 C1、§4 的「硬天花板」措辭、§5 的 Step 1a 與 Step 4 方向 —— 不可以照做,要先改。**

---

## 1. 重算 89.6 毫秒

### 1.1 逐字重現

我的配對規則(不看報告的腳本):同檔內 `blocked` 列排除,`result: null` 入 FIFO,
遇 `result` 非 null 取同 `action` 最早的 pre 配對。

```
總列數 1,075(env: prod 1,072 / test 3)
blocked 列 3(全在 capital-20260729,理由 capital_not_ready)
late 旗標列 0;檔中連 "late" 字串都 0 次
配對 536;未配對 pre 0;孤兒 post 0
delta 直方 {0:494, 1:39, 2:1, 3:1, 4:1}   Σ=48 s   mean = 89.6 ms
```

**與報告完全一致。配對數、直方、總和、平均全部重現。**

### 1.2 估計式有沒有偏?——沒有偏,但**精度是假的**

估計式本身**無偏**,我獨立推導過:`ts` 走
`datetime.now().astimezone().isoformat(timespec="seconds")`,`timespec` 是**截斷**不是四捨五入。
設 `u = frac(t) ~ U[0,1)` 與 `L` 獨立,`L = n + f`:
`E[floor(u+L)] = n + P(u ≥ 1−f) = n + f = L`。**成立。**

問題不在偏誤,在**變異**:

| 量 | 值 |
|---|---|
| `sd(delta)` | 0.345 s |
| `SE(mean)` | **14.9 ms** |
| 常態近似 95% CI | [60.3, 118.8] ms |
| **bootstrap 20,000 次 95% CI** | **[61.6, 119.4] ms** |
| 以「交易日」為叢集的 mean-of-means | 96.6 ms,跨日 sd 87.5 → CI [59.2, 134.0] |

**槓桿(刪掉 k 個最大 delta)**:

| 刪 | n | mean |
|---|---|---|
| 0 | 536 | 89.6 ms |
| 1 | 535 | 82.2 ms |
| 2 | 534 | 76.8 ms |
| **3** | 533 | **73.2 ms** |
| 10 | 526 | 60.8 ms |

**3 筆(0.56%)貢獻 9/48 s = 18.8% 的總質量。** 那三筆是:

```
3s  2026-08-21 11:07:57  order 2615  ok=True          ← 報告自己拿來當 head-of-line 證據那筆
2s  2026-09-07 11:54:49  order 6488  code=999 額度超過
4s  2026-09-07 11:54:52  order 6488  code=999 額度超過
```

**判定:mean 89.6 ms 這個點估計不該被當成三位有效數字使用。誠實的說法是
「mean 落在 60–120 ms,點估計 ~90 ms,且由兩天的兩個事件主導」。**

報告 §1 說「可以斷言的是:mean 84–89 ms」—— `84` 在 D1 與我的重算裡都找不到出處
(D1 通篇只有 89.6 / 86 / 81 / 103 / 173)。這個下界是憑空的。

### 1.3 「P(≥1 s) ≈ 7.6–7.8%」—— 上界當點估計

D1 §2.1 寫對了:`P(L ≥ 1s) ∈ [0.56%, 7.8%]`。
**主報告 §1 把它壓成「P(≥1 s) ≈ 7.6–7.8%」,等於把區間上界當成點估計。**

`delta ≥ 1` 只代表**跨了秒界**,不代表 `L ≥ 1 s`。事實上若全部 `L < 1 s`,
則 `P(delta = 1) = E[L]` —— 我實測 `42/536 = 7.84%`,而 `mean = 89.6 ms`,
兩者**互相吻合到 12% 以內**。也就是說:**那 42 次跨秒,幾乎全部可以只用「平均 ~80 ms」
解釋,不需要任何長尾。**

能證明 `L ≥ 1 s` 的只有 `delta ≥ 2` 的 **3 筆 = 0.56%**。

**決策影響:** 報告 §1 結論句、§5 Step 5 的理由句都寫「那 **7.6%** 的 ≥1 s 長尾不再卡住回報」。
真實量級是 **0.6%,差一個數量級**。`bAsyncOrder=1`(Step 5)是報告自己標「第一次執行必然在
盤中真錢」的高風險改動,它的收益被高估了 10 倍。

### 1.4 「拒單比成功單慢一倍」—— 方向會反轉,而且不顯著

| 切面 | n | mean |
|---|---|---|
| 全量 ok | 484 | 80.6 ms |
| 全量 reject | 52 | 173.1 ms(比值 **2.15**) |
| **去掉那 3 筆離群後 ok** | 483 | 74.5 ms |
| **去掉那 3 筆離群後 reject** | 50 | **60.0 ms**(比值 **0.80**) |

52 筆拒單的 9 s 總量裡,**6 s 來自 2026-09-07 那兩筆(2 s + 4 s)**。
permutation test(20,000 次重排):**單尾 p = 0.069、雙尾 p = 0.138 —— 全量下就已經不顯著。**

**決策影響:** D1-08 的修法(本地累計名目金額預檢)寫「0.5 µs 取代 **173 ms** 往返」。
**那 173 ms 撐不住。** 這個改動仍該做(理由是拒單語意與風控,不是延遲),
但**不可以拿 173 ms 當優先序理由**。

### 1.5 分面:報告的「89.6 ms」其實只是「證券限價單」

我的切面(報告沒切這兩刀):

| 切面 | n | mean | ≥1 s |
|---|---|---|---|
| action=order | 419 | 85.9 ms | 7.16% |
| action=cancel | 116 | 103.4 ms | 10.34% |
| action=close | 1 | — | — |
| market=sec | 533 | 90.1 ms | 7.88% |
| **market=fut** | **3** | **0 ms** | 0% |
| **price_type=limit** | 400 | 90.0 ms | 7.50% |
| **price_type=market** | **20** | **0 ms** | **0%** |

- **期貨單只有 3 筆**,全部在 **2026-08-24 22:54 夜盤**、全部 `TC.F.TWF.TMF.HOT`、
  全部 delta = 0。**沒有任何刪單 / 平倉 / 改價的期貨樣本。**
- **市價單 20 筆全部零跨秒。** 若母體 `P(cross)=8.96%`,連 20 筆不跨的機率 ≈ 15%
  —— 不顯著,但配合期貨的 0/3,足以說:**「89.6 ms」是證券限價新單 + 刪單的數字,
  不是「下單」這個功能的數字。** 報告通篇以「端到端 mean 89.6 ms」代表整個下單功能。
- `req` 鍵集合只有三種(837 證券 / 232 刪單 / 6 期貨),**改價與減量在 22 天 prod 裡零樣本**
  —— 而 D1 §1 給它們列了「額外前置 2 × 89 µs」的成本表,那是本機 micro-bench 不是 prod。

### 1.6 「開盤不慢、11:00–13:30 反而慢 → 尾巴在券商端」—— 結論可能對,證據不足

報告:`11:00–13:30 n=70、14.3% 跨秒`。我重現了 `70 / 10 / 14.3%`。
但那 10 筆的**來源**:

```
2026-08-21 ×3   (11:07:57 / 11:07:59 / 11:41:39)
2026-09-07 ×4   (11:54:49 / 11:54:52 / 11:55:11 / 11:55:15)  ← 999 額度耗盡連發
2026-09-08 ×1   2026-09-10 ×1   2026-09-11 ×1
```

**10 筆裡 7 筆來自兩天的兩個 3 分鐘事件。** 而以交易日為單位看,mean 從 **0.0 ms(3 天)**
到 **333.3 ms(09-07)**,跨日 sd = 87.5 ms ≈ mean 本身。

**觀測值不是 iid —— 是按 session / 券商狀態叢集的。** 「時段」這個切面幾乎沒有解釋力,
真正的分層變數是「那天券商端出了什麼事」。結論(尾巴在券商端)方向上我同意,
但報告給的那個對照**不構成證據**;真正的證據是 §1.1 的 `delta` 幾乎全 0 而本地段總和只有 1.14 ms。

---

## 2. 重算回流鏈 1,940 毫秒

### 2.1 n 與分段:重現,但 p90 不對

`grep "balance 鏈" logs/*.log` → **725 行,零行無法解析**。
我的組鏈(遇「庫存段收齊」開新鏈,「部位落地」收鏈):

| 量 | 報告 | 我重算 | 判定 |
|---|---|---|---|
| 鏈數 | 179 條「完整鏈」 | 183 個 block / **178 條四段齊全** | 近似 |
| 端到端 p50 | 1,940 | **1,940** | 逐字 |
| 端到端 p90 | 4,103 | **4,057** | 分位法差異 |
| 端到端 p99 | 6,553 | **6,433** | 分位法差異 |
| 端到端 max | 6,639 | **6,639** | 逐字 |
| 成交→庫存 p50 | 1,061 | **1,061** | 逐字 |
| 庫存→損益 p50 | 576 | **566** | 近似 |
| 損益→OI p50 | 310 | **310** | 逐字 |

另外我量到報告沒列的一段:**OI→落地 p50 = 1 ms**(max 24 ms)。所以確實只有三段。
`p50 相加 = 1,938` vs `端到端 p50 = 1,940` —— 分段可加總,這點報告是對的。

### 2.2 0.5 s debounce 真的在裡面嗎?——結構上在,但 **25/178 條(14%)不在**

機制確認:`_handle_reply` 收到 `status_raw == "D"` → `_fill_seen_at = t0` +
`_mark_balance_dirty()`(`delay_s=0.5`)→ `_maybe_query_balance` 要等 `now >= _balance_due`
才發查詢。**所以健康路徑的庫存段 ≥ 500 ms + 幫浦粒度(≤50 ms)+ COM 往返。CONFIRMED。**

但實測:**庫存段 < 500 ms 的鏈有 25 條,最小值 0 ms。** 結構上不可能。

### 2.3 量測器自己被污染 ——(報告完全沒提)

根因在 `client.py:421`:`self._fill_seen_at = t0` **每收到一筆成交就覆寫**,
而 `_log_chain_stage` 印的是 `now - _fill_seen_at`。鏈進行中來了新成交 → **計時器中途歸零**。

三個可觀測的污染指紋,我全部抓到了:

| 指紋 | 條數 | 意義 |
|---|---|---|
| **累積值非單調遞增** | **8 條** | 同一把計時器不可能倒退。例:`庫存 1,097 → 損益 311` |
| **缺「庫存段」起點**(60 s DEBUG 輪中途被成交點亮) | 4 條 | `部位落地` 183 > `庫存段` 179 的來源 |
| 庫存段 < 500 ms | 25 條 | debounce 不可能被跳過 |

**而且它們高度集中在 server 剛啟動時**(= 開機 backlog 重播):

| 子集 | n | 距 server 啟動 < 2 分鐘 | 中位距啟動 |
|---|---|---|---|
| 乾淨(單調且庫存段 ≥ 500 ms) | 150 | 14 (9%) | **70.5 分** |
| **被剔除** | **28** | **22 (79%)** | **1.0 分** |

清洗後:

| 子集 | n | p50 | p90 | p99 |
|---|---|---|---|---|
| 報告的全部 178 | 178 | 1,940 | 4,057 | 6,433 |
| 乾淨 | 150 | 1,994 | 4,877 | 6,553 |
| 被剔除的 28 | 28 | **641** | 935 | 1,043 |
| **盤中(09:00–13:30)且乾淨** | **139** | **1,979** | **3,027** | 6,433 |

**判定:p50 1,940 ms 是穩的(清洗後 1,979,+2%),Step 4 的優先序站得住。
但 p90 4,103 是混合產物** —— 使用者真正經歷的盤中 p90 是 **3,027 ms**,
而報告那個 4,103 有一半是盤外重啟重播。

**而且這把尺是 Step 4 的驗收判準**(報告 §5:「`grep 'balance 鏈' logs/` 的 p50 從 1,940 ms 下降」)。
**用一把會自我污染、且污染量與「開機次數」正相關的尺去驗「回流變快了」——
多重啟幾次就能讓數字變好看,零錯誤訊號。** 這是順序層的實質缺陷。

### 2.4 【最大漏網】整條尾巴 = 1019,而且證據已經在 logs/ 裡

`grep "GetRealBalanceReport rc" logs/*.log` → **310 筆,100% 是 `rc=1019
SK_ERROR_QUERY_IN_PROCESSING`**。每一筆的代價是 `client.py` 的
`self._mark_balance_dirty(1.0)` —— **固定退避 1 秒**。

我把每條鏈的庫存段時窗與落在窗內的 1019 對齊:

| 該段窗內 1019 次數 | n | 庫存段 p50 | p90 | max |
|---|---|---|---|---|
| **0** | **156** | **1,022** | 1,249 | 2,628 |
| 1 | 2 | 2,122 | 2,198 | 2,198 |
| 2 | 5 | 3,249 | 3,296 | 3,296 |
| 3 | 7 | 4,183 | 4,281 | 4,451 |
| 4+ | 9 | 5,301 | 5,495 | 5,572 |

**每多一次 1019,庫存段精準多 ~1,060 ms。**
**庫存段 ≥ 2,000 ms 的 25 條裡,23 條(92%)窗內有 1019。**

這改寫 Step 4 的全部三個候選方向:

1. **「0.5 s debounce 是否可縮短」** —— 天花板是 −500 ms(p50 1,940 → 1,440,**−26%**)。
   而且縮短 debounce **會增加** 1019 碰撞機率(查詢更密),可能淨負。
2. **「三段能否並行(庫存與 OI 不互相依賴?)」** —— 報告自己註「⚠ 可能撞 1019,要先用一天
   prod 驗」。**不必驗:1019 已經是常態(310 次),而且是尾巴的唯一來源。**
   並行 = 同時對群益發兩個查詢 = **直接製造 1019**。**這個方向的證據是反向的。**
3. **「六類不樂觀套用能否縮小」** —— 與延遲無關,是覆蓋率問題,方向獨立成立。

**真正的 Step 4 應該是第四個方向(報告沒有):消除 1019 碰撞來源
(成交觸發查詢 vs 60 s stale 輪詢撞在一起),以及把固定 1 s 退避改成短退避。**
量級:p50 −0 ms(p50 本來就沒有 1019),**p90 3,027 → ~1,250 ms(−59%)、p99 6,433 → ~2,600(−60%)**。
使用者抱怨的「下單後倉位很慢」是尾巴不是中位數,**所以這才是那條槓桿。**

其他訊號:`部位合併逾時` 8 次、`GetOpenInterestGW` 5 次、`審計後置寫入失敗` 0 次、
`COM 幫浦圈例外` **0 次**(見 §5 靜默旗標稽核)。

---

## 3. 驗兩條 critical

### 3.1 C1 「回報斷線偵測是死碼」——**診斷錯誤**

報告 §3:「**回報連線斷線偵測是死碼** | 65 次 session、3,531 則 `OnNewData`,而
`OnConnect` / `OnDisconnect` **零觸發**」,Step 1a:「**修 `OnConnect` / `OnDisconnect` 綁定**」。

我逐層查證:

| 查核點 | 結果 |
|---|---|
| sink 有沒有實作? | **有。** `com.py:264 OnConnect` / `com.py:271 OnDisconnect` |
| 有沒有 advise? | **有。** `com.py:129 comtypes_client.GetEvents(self._reply, self._reply_sink)` |
| advise 的是不是對的介面? | **是。** typelib `SKReplyLib._outgoing_interfaces_ = [_ISKReplyLibEvents]` |
| 方法名對得上嗎? | **對。** `_ISKReplyLibEvents` 宣告 `'OnConnect'` dispid 1、`'OnDisconnect'` dispid 2 |
| **引數個數 / 型別對得上嗎?** | **對。** typelib:`(['in'], BSTR, 'bstrUserID'), (['in'], c_int, 'nErrorCode')`;sink:`(self, bstrUserID: str, nErrorCode: int)` —— **逐位元相符** |
| 有沒有測試? | **有。** `tests/capital/test_com.py:134-145` |
| log level 擋得住嗎? | **擋不住。** `__main__.py:143 basicConfig(level=INFO)`;`OnConnect` 印 INFO、`OnDisconnect` 印 **ERROR** |
| `copycat.capital.com` 這個 logger 出得來嗎? | **出得來。** logs 裡有 22 行(全 WARNING);**INFO 行 0** |

**結論:綁定沒有壞。Step 1a 照字面做(「修綁定」)會是 no-op,而且會消耗一次「修好了」的
信心,把真正的洞留在原地 —— 這在真錢路徑上比不修更糟。**

**零觸發是真的**(我獨立確認:`Capital reply connected` 0 / `Capital reply disconnected` 0 /
`Capital reply connect error` 0 / `回報連線中斷` 0),但正確的陳述是
**「這條路徑 22 天零觀測、根因未知」**,不是「死碼 / 綁定壞了」。

**頭號候選根因(報告完全沒看到):** 同一個 `_ISKReplyLibEvents` 還宣告

```
dispid(9)   OnSolaceReplyConnection(bstrUserID: BSTR, nErrorCode: c_int)
dispid(10)  OnSolaceReplyDisconnect(bstrUserID: BSTR, nErrorCode: c_int)
```

**`grep -n "Solace" copycat/capital/*.py` → 零命中。sink 完全沒實作這一對。**
Solace 是群益回報基礎設施的訊息匯流排。**若現行回報主機走 Solace 通道,連線 / 斷線通知就是
從 dispid 9/10 出來,而 comtypes 對 sink 未實作的事件是靜默忽略** ——
這一個假說**同時解釋** 3,201 則 `OnNewData` 正常與 `OnConnect` 零觸發,
而報告的「綁定壞了」假說**解釋不了 OnNewData 為什麼是好的**(同一個 sink、同一次 advise)。

**Step 1a 必須改寫成:先掛上 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect` 兩個 sink
方法(各一行 log),下一個交易日看哪一對會響。** 在知道哪一對會響之前,
「手動拔網 → log 出現斷線行」這個判準是無效的(拔網也可能兩對都不響)。

**順帶:`3,531 則 OnNewData` 是錯的。** `_handle_reply` 無條件印
`Capital reply: seq=%s ...`(`client.py:405`,在任何 early return 之前),
`grep` → **3,201**。差 330(+10.3%)。`65 次 session` 則**正確**
(`grep "群益正式環境" = 65`)。

### 3.2 C2 「TanStack networkMode 會自動補送真錢單」——**成立,而且比報告寫的更糟**

版本:`@tanstack/react-query` + `query-core` **5.101.2**(讀 `node_modules`,非記憶)。
`main.tsx:16` = `new QueryClient()`,零 defaultOptions。**CONFIRMED。**

逐條查證(全部出自 `node_modules/@tanstack/query-core/build/modern/`):

| 查核點 | 原始碼 | 結果 |
|---|---|---|
| mutation `networkMode` 預設 | `retryer.js:11` `(networkMode ?? "online") === "online" ? onlineManager.isOnline() : true` | **預設 "online"。CONFIRMED** |
| 離線時會怎樣 | `mutation.js:89-94` `const isPaused = !this.#retryer.canStart(); ... dispatch({type:"pending", variables, isPaused})` | **`mutationFn` 根本不被呼叫**,狀態是 pending+isPaused → UI 轉圈。**CONFIRMED** |
| 會不會重複送 | `mutation.js:83` `retry: this.options.retry ?? 0` | **不會。** mutation 預設零重試 → C2 是「延遲首送」不是「重複送」。報告寫「自動補送」**準確** |
| 恢復時放行幾筆 | `mutationCache.js:113-118` `getAll().filter(isPaused)` + `Promise.all(map(m => m.continue()))` | **一次全數放行。CONFIRMED** |
| **誰觸發放行** | `queryClient.js:36-41` **`focusManager.subscribe` 與 `onlineManager.subscribe` 各掛一條** | **報告只寫了 online 那條** |
| 放行的條件 | `retryer.js:42` `canContinue = focusManager.isFocused() && (networkMode==="always" \|\| onlineManager.isOnline()) && canRun()` | **online 與 focus 必須同時成立** |

**報告漏掉的那一半,是嚴重的那一半:**

放行需要 **online 恢復** 與 **視窗聚焦** 同時成立,由**較晚發生的那一個**觸發。
所以:網路在分頁處於背景時恢復 → 單**不會**立刻送;**等使用者下次切回分頁那一刻才送出**。

**→ 曝險窗沒有時間上界。** 報告寫「網路恢復時一次全數放行」會讓人以為窗 = 斷線時長;
實際上窗 = 斷線時長 **+ 使用者下次回到這個分頁的時間**,可以是幾小時後、完全不同的價位。
真錢限價單在幾小時後以當時已經失效的價格送進市場 —— 這是 C2 真正的形狀。

**還有一層報告沒說,而它讓 C2 在這台機器上是純誤判:**
`onlineManager.js:10-19` 用的是 `window.addEventListener("online"/"offline")`,
也就是 `navigator.onLine` —— **瀏覽器對「這台機器有沒有對外網路」的判斷。**
而本系統**全部跑在同一台 Windows 11 上、前端經 loopback 打 `127.0.0.1:8721`**。

**拔掉 WiFi / 網路線 → 瀏覽器發 `offline` → 每一筆送單 mutation 被暫停,
但 loopback 這條路從頭到尾好好的、uvicorn 好好的、群益那條是 Python 進程自己的 socket 也好好的。**
`#online` 初值是 `true`,只有明確的 `offline` 事件才翻。

**→ 在「撇除網路 / 全部同機」這個部署前提下,`networkMode: "online"` 這個預設的判準
與真實可達性完全無關。改成 `"always"` 不只是修 C2,是移除一個**結構性不相干**的閘。
報告說「修法是一行」—— 同意,而且理由比報告給的更強。**

**Step 0a 的 blast radius(我逐一查了全部 5 個 mutation 點):**

| 位置 | 用途 | 改 `always` 的後果 |
|---|---|---|
| `useCapital.ts:223` `useCapitalMutation` | **送單 / 平倉 / 改價 / 刪單全部走這一支**(`useSubmitStock` / `useSubmitFuture` / `useCancelOrder` / `useCorrectPrice` …) | 離線立即失敗而非排隊。**正是要的** |
| `useStockWatchlist.ts:46` | 自選 PUT | 排隊的 PUT 在數小時後放行會用**舊快照覆蓋**新狀態。改 always **也是改善** |
| `useSignalRules.ts:74 / 98` | 規則 upsert / delete | 同上 |
| `useSeries.ts:19` | TXO series 快照(讀形 POST) | 失敗即失敗,無副作用 |

**五個都是「立即失敗優於延遲放行」。全域設在 `mutations:` 安全。**

**但有一個一定要說的坑:`queryClient.js:271-273`**

```js
if (defaultedOptions.refetchOnReconnect === void 0) {
  defaultedOptions.refetchOnReconnect = defaultedOptions.networkMode !== "always";
}
```

這在 **`defaultQueryOptions`(queries)** 裡。**若實作時把 `networkMode: "always"` 放錯層
(放進 `queries:` 或共用 default),全站每一支輪詢 hook 的 `refetchOnReconnect` 會被
靜默關掉**,零錯誤訊號。報告給的那一行放在 `mutations:` 是對的 —— 但**這個坑必須寫進 ticket**,
因為它正是「一行改動」最容易被寫歪的一行。

---

## 4. 驗硬天花板:自訂單號

### 4.1 證券:CONFIRMED(但「typelib 封死」這個措辭過頭)

`.venv/Lib/site-packages/comtypes/gen/_75AAD71C_*.py`(唯讀):

```
STOCKORDER._fields_ (14 欄):
  bstrFullAccount bstrStockNo sPrime sPeriod sFlag sBuySell bstrPrice
  bstrOrderType bstrSeqNo bstrBookNo nQty nTradeType nSpecialTradeType nUnitQty
```
**零自訂欄位。`bstrSeqNo` / `bstrBookNo` 是券商配發。CONFIRMED。**
全 typelib 只有一個 `Send*StockOrder*` 家族方法:`SendStockOrder`(+ 海外的
`SendForeignStockOrder` / `SendForeignStockOrderOLID`)。**`SendStockOrderOLID` 不存在。CONFIRMED。**
OLID 家族 11 個方法我全列了,**全部是海外 / 複委託**。CONFIRMED。

**但**:全 typelib 搜尋「疑似自訂識別」欄位 → `bstrOrderLinkedID`(海外)、`bstrCIDTandem`、
`bstrOrderSign`、**`bstrUserDef`**。
`bstrUserDef` 在 **`STOCKSTRATEGYORDER`**(智慧單 / 策略單)裡,不在 `STOCKORDER` 裡。

所以正確措辭是 **「`SendStockOrder` 這條路徑封死」**,不是「SKCOM typelib 封死了這個設計空間」。
另有 `STOCKSTRATEGYORDER` / `...MIOC` / `...MIT` / `...OCO` / `...OUT` 五個策略單 struct,
其中至少 `STOCKSTRATEGYORDER` 帶 `bstrUserDef`。**我沒有證據說它可用**
(智慧單有不同的委託語意、可能要另外開通),但報告把設計空間宣告為「硬天花板」時
**沒有提到這個存在**,而 grilling 階段若 user 問「真的一個欄位都沒有嗎」,
答案會被現場推翻 —— 那正是報告 §4 說要避免的「白做一輪」。

### 4.2 期貨:報告只說「國內單」,我補上

```
FUTUREORDER._fields_ (36 欄):
  bstrFullAccount bstrStockNo bstrStockNo2 bstrPrice bstrPrice2 bstrTrigger bstrTrigger2
  bstrMovingPoint bstrDealPrice sTradeType sBuySell sBuySell2 sDayTrade sNewClose nQty
  sReserved nTimeFlag nOrderPriceType bstrCIDTandem bstrOrderSign bstrSettlementMonth
  bstrStrikePrice bstrOrderType bstrSeqNo bstrBookNo nCallPut nCurrency nTriggerDirection
  nResultFormat nFlag nFunType bstrLongEndDate nLongActionFlag nLAType nMarketNo
  bstrSettlementMonth2
```

- **無自由文字欄位。`bstrCIDTandem`(組合單腿關聯)/ `bstrOrderSign`(停損單標記)語意受限,
  報告的判斷正確。**
- `sReserved` 存在但語意未定義,**未量**,不建議當冪等鍵。
- **結論:期貨與證券同樣封死。報告的「國內單」措辭涵蓋了期貨,只是沒明說 —— 我補證,CONFIRMED。**

### 4.3 同一次查核撿到的:額度預檢可能不必只靠本地累加

`_ISKOrderLibEvents` 宣告 **`OnMarginPurchaseAmountLimit`**,且有對應方法
**`GetMarginPurchaseAmountLimit`**。

報告 D1-08 的修法是「把今日已送出名目金額累加在 client 本地」。
**至少「融資額度」這一類有官方查詢 API,不必用本地累加去猜。** 見 §5 的拒單語意分解。

---

## 5. 靜默旗標與失效模式稽核

### 5.1 「999 ×40 全是額度超過」——REFUTED

D1-08 白紙黑字:「拒單碼分布:`999` ×40(**全是** `網路單交易額度超過限定額度 249萬`)」。
我逐列聚合 `result.ok == false`:

| code | 次數 | 訊息 |
|---|---|---|
| 999 | **30** | 網路單交易額度超過限定額度 249萬 |
| 1068 | 7 | 市價單委託價須為 0 |
| **999** | **4** | **此投資人尚未簽署創新版風險預告書,不可委託!** |
| **999** | **4** | **集保庫存剩 0 股,不得賣出或匯撥交割** |
| 400 | 3 | DB查詢失敗 TMFI6無法轉換商品ID |
| **999** | **1** | **目前此投資人可沖銷股數,資買 0 股;集買 0 股** |
| **999** | **1** | **此人融資已滿!欲借 57萬;額度 90萬;整戶可借 0張** |
| 960 | 1 | 此委託不可做刪改! |
| 960 | 1 | 查無委託資料 |

**999 是 40 次沒錯,但它是 5 種語意共用一個碼,只有 30 次是 249 萬額度。**
(主報告 §3 寫「30 次實證」是對的;**D1-08 的「全是」是錯的**,兩份文件互相矛盾。)

**決策影響兩條:**
1. D1-08 的本地名目累加**只蓋得住 40 筆裡的 30 筆**。另外 10 筆
   (未簽風險預告書 / 集保庫存 0 / 可沖銷 0 / 融資額度)**本地累加原理上算不出來**。
2. **這反過來強化「`err_msg` 前端零讀者」的嚴重性** ——「未簽風險預告書」是一次性開戶動作、
   「集保庫存剩 0 股」是資料狀態 bug、「額度 249 萬」是等明天,
   **三種處置完全不同的事全部顯示成「券商拒單(999)」。**
   我獨立確認:`grep -rn "err_msg" frontend/src` **零命中**。CONFIRMED。

### 5.2 靜默旗標:一條**誤標**、一條**漏標**(漏標的那條更危險)

報告 §3 稱「236 條中 175 條標為靜默(74%)」。我抽查了下單線裡旗標最關鍵的幾條:

| 失效 | 報告旗標 | 我的判定 |
|---|---|---|
| 前置審計卡在共用 executor | ★ 零訊號 | **正確**。無 qsize 指標、`_WRITE_TIMEOUT_S` 管不到 ③ |
| `OrderResult.ok===false` 無讀者 | ★ | **正確(部分)**。`OrderPanel.tsx:114` 有讀 `result.ok`;`PriceLadder.tsx:294/345` 走 `mutateAsync` + `settleFlashSend` **不讀**。報告寫「四個入口中三個」與我查到的一致 |
| `/api/health` 不含 capital | — | **CONFIRMED**,grep 零命中 |
| `notify_discord` 在 capital 零 caller | — | **CONFIRMED**,`copycat/capital/*.py` 零呼叫 |
| **`_pump_once` 例外 → 每圈 sleep 1 s** | **★ 零訊號** | **誤標。** `client.py:792` 有 `logger.exception("COM 幫浦圈例外(本輪略過)")`,報告自己的「現在怎麼發現」欄也寫了 `grep`。**有訊號,不該標 ★。**(我實測 22 天 log 命中 **0** 次 → 這條路徑 prod 零發生,優先序應再降) |
| **回流鏈 1019 碰撞** | **完全沒列** | **漏標,而且它是尾巴的唯一來源。** 有 WARNING(310 行)所以**不是**靜默 —— 但報告沒列它,等於「有訊號卻沒人讀」,實務後果與靜默相同 |
| **回流鏈量測器自我污染** | **完全沒列** | **漏標,★ 真・零訊號。** 見 §2.3:8 條非單調、28 條啟動污染,而它正是 Step 4 的驗收判準 |
| **`_on_late_result` 在 event loop 上同步寫審計** | 沒列 | `client.py:396` `self._audit(record)` **未經 `to_thread`**,而它由 `fut.add_done_callback` 在 loop 上跑 → 阻塞 loop ~211 µs 且會搶 `_audit_lock`。報告說這條路徑 prod 零執行(我確認 `late` 字串 0 命中),**所以是潛伏不是現行**,但該列 |

**方向判定:誤標(把有 log 的標成 ★)是保守方向,無害。漏標兩條 —— 其中
「量測器自我污染」直接讓 Step 4 的驗收判準失效,是這份報告在靜默旗標上最實質的缺口。**

---

## 6. 查改造順序

### 6.1 Step 0a(networkMode)—— 可以先做,但 ticket 要加一句

見 §3.2。五個 mutation 全部受益;**唯一風險是寫錯層**(`queries:` 會靜默關掉
`refetchOnReconnect`)。判準「斷網後按送單 → 應立即失敗」**不完整**,應補一條:
**「斷網 → 按送單 → 立即失敗 → 恢復網路 → 切到別的分頁再切回來 → 不得有任何單被送出」**
(補的是 focus 那條放行路徑)。

### 6.2 Step 0c 是 0a/0b 之外每一步的前提 —— 同意,而且比報告說的更必要

報告說「0c 是後面每一步的前提」。我的 §1.2 把理由加強了:
**不只 p50 量不出來,連 mean 都只有 ±33% 的精度,且被 3 個樣本主導。**
0c 之前的任何延遲數字都不該被引用到小數點。

**一個內部矛盾**:§5 Step 0c 寫「現有 **499** 對配對受限於秒解析度」,
而 §1 與 D1 通篇都是 **536** 對(我重算 = 536)。**499 無出處。**

### 6.3 Step 1a —— **必須改寫**(見 §3.1)

「修綁定」沒有東西可修。正確的第一步是掛 `OnSolaceReplyConnection` /
`OnSolaceReplyDisconnect`,先做**辨識**再談修。
報告自己也註明「1a 單獨做收益比想像小,要 1a + 1d 一起做」—— 這個判斷對,
但前提是 1a 真的有東西可修;現況是 1a **連目標都還沒找到**。

**替代的低風險保底(報告沒提):回報停更是**可以不靠事件偵測的** ——
`_handle_reply` 每則都留痕,做一個「最後一則回報距今 N 秒」的 watchdog 就能覆蓋
「真掉線時 status 恆 ok」這個 blast radius,而且**不依賴任何 SKCOM 事件是否會響**。
在根因未知的情況下,這比修一個沒壞的綁定務實得多。

### 6.4 Step 2(具名 executor)與關機預算 —— 我自己算了一次

不等式(`shutdown_budget.py`,全部常數我逐一查過):

```
_REQ_TIMEOUT_MS = 10_000            → req_secs = 10
DEFAULT_LOCK_TIMEOUT_SECS = 12.0
close_worst_secs() = 10 + max(2×10, 2×12) = 10 + 24 = 34
COM_JOIN_TIMEOUT_SECS = 5.0 ; TC4_LANE_DEPTH = 2 ; LIFESPAN_SLACK_SECS = 5.0
lifespan_close_worst = 2×34 + 5 + 5 = 78
run_grace_secs() = ceil(5 + 78) = 83        ← 與 CLAUDE.md §4 的 83 s 逐字相符
```

**答案:具名 audit executor 與這個不等式相容,不需要改任何常數。** 理由:
- 它的工作是一次 `append_audit`(我實測 p50 211 µs),**有界且亞毫秒**;
- `LIFESPAN_SLACK_SECS = 5.0` 的 docstring 明寫涵蓋「TC4 之外的段 + **執行緒排程**」,
  這正是它該落的格。

**但報告的警告寫得不精確,而且錯過了一個更大的洞。**

報告寫:「`ThreadPoolExecutor` 的 worker 是 non-daemon;直譯器退出時會 join 全部」。
機制對(我實測 `[t.daemon for t in loop._default_executor._threads] == [False]`,
`max_workers = 20`,cpu_count 16 → `min(32, 16+4)`,與報告一致),但**排序錯了**:

```
uvicorn/server.py:74  asyncio_run(...)  →  uvicorn/_compat.py:29  asyncio.Runner
asyncio/runners.py    Runner.close():
    loop.run_until_complete(loop.shutdown_default_executor(constants.THREAD_JOIN_TIMEOUT))
asyncio.constants.THREAD_JOIN_TIMEOUT = 300        ← 我實測
```

**`asyncio.run` 在 lifespan 結束後、直譯器退出前,會先 join 預設 executor 最多 300 秒。**
**這 300 秒完全不在 83 秒的預算裡,而且是今天就存在的洞** ——
預設 executor 現在同池住著 TC4 ZMQ REQ(10 s)與 FinMind EOD(60 s),
只要有一條卡住,`run.ps1` 必定在 83 s 到期時 `taskkill /T /F`,
而 `tests/server/test_shutdown_budget.py` 的不等式根本沒有這一項。

**所以 Step 2 的正確結論是相反的:它不是「要小心會不會撐破預算」,
它是「把審計搬出預設池會**降低**關機風險」。** 但有一個必做的附帶條件:
**新 executor 必須在 lifespan 裡顯式 `shutdown()`(進一條 lane),否則它會落到
`concurrent.futures.thread._python_exit` 的 atexit join —— 那條路徑連 300 s 的
timeout 都沒有,是真正的無上界。**

### 6.5 Step 2 的 fsync 取捨 —— 我重量過,報告樂觀了

`bench_audit.py`,N=3,000,同一顆 SSD(scratchpad):

| 寫法 | 報告 p50 | **我量 p50** | 報告 p99 | **我量 p99** | **我量 max** |
|---|---|---|---|---|---|
| 現況 `mkdir+open(a)+write+flush+close` | 224.5 µs | **211.5** | 353.1 | **317.5** | 558.5 |
| **同上但不含 `mkdir`** | (未量) | **139.5** | — | 229.8 | 642.1 |
| persistent handle 只 write | 3.5 µs | **2.8** | 15.7 | **5.6** | 120.6 |
| persistent handle + `fsync` | 295.5 µs | **325.7** | 491.5 | **459.2** | **7,146.5** |
| `json.dumps` 本身 | 2.3 µs | **2.7** | 4.0 | 4.6 | 24.3 |
| `await to_thread(noop)` 池空 | 40.6 µs | **59.3** | — | 118.3 | 1,925.8 |
| `await to_thread(append)` 池空 | 351.8 µs | **291.8** | 545.9 | **392.8** | 890.3 |

**全部在 ±30% 內重現 —— 報告的 benchmark 是真的。** 兩處修正:

1. **fsync 不是「只多 70 µs」,是 +114 µs(211.5 → 325.7)**,而且 **max 7.1 ms vs 558 µs,
   尾巴差 13 倍**。報告的表裡 fsync max = 591 µs 比現況的 622.9 µs 還小 —— 那組數字的
   跑數應該不夠長。報告 §5 Step 2 自己說「驗收判準要看 p99 不是 p50」,**方向對,
   但應該看 max**:送單路徑會付兩次,最壞 +14 ms。仍遠小於 88 ms 的券商段,
   **所以「該做」這個結論我同意,只是「白撿的」這個形容不成立。**

2. **報告完全沒提 `mkdir`。** `audit.py:33` 的 `base.mkdir(parents=True, exist_ok=True)`
   在**每一次 append 都跑一遍,而且在 `_audit_lock` 裡面**。
   **它佔 211.5 µs 裡的 72 µs(34%)。** 拿掉它(啟動時建一次)是零風險、零取捨、
   一行改動,送單路徑省 **0.14 ms(×2)** —— 比整個 §6「不要動」清單裡任何一項都大。
   報告說「225 µs 有 98% 在 open/close」—— **不對,是 34% mkdir + 約 64% open/close,
   write 本身只有 2.8 µs。**

### 6.6 Step 4 —— 方向要換(見 §2.4),判準要換(見 §2.3)

- 方向:「三段並行」有反向證據,不該排進去。
- 判準:`grep 'balance 鏈' 的 p50 下降` 用的是一把會被開機次數污染的尺。
  應改成「**盤中(09:00–13:30)、單調、庫存段 ≥ 500 ms 的子集**的 p90」,
  並同時追 `grep -c "GetRealBalanceReport rc=1019"`。

### 6.7 Step 5(`bAsyncOrder=1`)—— 收益被高估一個數量級

報告的理由是「消除 head-of-line blocking → 那 7.6% 的 ≥1 s 長尾不再卡住回報」。
**真實的 `P(L ≥ 1 s)` 下界只有 0.56%(3/536),7.84% 是上界**(§1.3)。
而 D1 §3.2 自己算出改非同步**若不先做 `MsgWaitForMultipleObjects` 會 +25 ms**。

**建議:Step 5 降到「先不做」,理由改成「收益量級未知且下界只有 0.6%,
而代價是新 code 第一次執行必然在盤中真錢」。** 要重估必須等 Step 0c 的分段時戳。

---

## 7. 以「撇除網路」重評 ①,以及一個會反轉的結論

### 7.1 ① 我量了,而且 preview 真的會走這一跳

**先確認前提**(報告與 CLAUDE.md §1 都假設看盤日常經 4173 preview):
`vite.config.ts` 只設了 `server.proxy`,沒設 `preview.proxy`。
我查 vite **6.4.3** 原始碼 `dist/node/chunks/dep-Dm0c1Wj2.js`:

```js
resolvePreviewOptions(preview2, server) { ... proxy: preview2?.proxy ?? server.proxy, ... }
```

**preview 確實繼承 `server.proxy`。前提成立 —— 這一跳真的在。**

**然後我量了它**(`proxybench.mjs`,Node v24.13.0,同機 loopback,keep-alive,
3,000 次 POST,同樣的 order body):

| | p50 | p90 | p99 | max |
|---|---|---|---|---|
| 直打上游(1 跳 loopback) | 68.6 µs | 112.0 | 212.7 | 972.5 |
| 經 Node proxy(2 跳 loopback) | 139.8 µs | 212.4 | 340.6 | 570.4 |
| **多一跳的增量** | **71.2 µs = 0.071 ms** | 100 | 128 | — |

**報告的「0.2–1 ms 推估」高估了 3–14 倍。** D1-19 說「量到 > 2 ms 才談掛 `StaticFiles`」
—— 以 0.071 ms 論,**這格永久結案,不要再回頭看。**
(合成基準:Node 內建 `http` 反向代理,非 vite 實際用的 `http-proxy`;
量的是**多一跳的相對增量**,這個量對實作差異不敏感。)

### 7.2 撇除網路之後,「不要優化送單路徑的 Python」這個結論會反轉

報告 §1 的結論句:「把 ①–⑬ 全部優化到零,端到端只從 89.6 ms 變成 88.5 ms。」
**算術對,但分母選錯了 —— 而且錯在 user 明確排除的那一項上。**

那 88.5 ms 的實體是 `SendStockOrder` **同步等群益伺服器回應**。
那是**對外網路往返**,不是 loopback,更不是這個 codebase。
User 的規則是「**撇除網路因素 —— 不要把網路延遲算進任何預算**」。
**照這條規則,88.5 ms 就不在預算裡。** 而報告正是拿它當分母,得出
「本地 1.3%,所以不要動」。

**以「in-scope(本機可控)預算」重算:**

| 段 | 成本(p50) | 我的依據 |
|---|---|---|
| ① vite preview proxy 多一跳 | 0.071 ms | **本輪實測** |
| ② uvicorn + routing + pydantic | 0.305 ms | 報告實測(未複驗) |
| ③ safety gate | 0.0005 ms | 報告實測 |
| ④ `_record()` | 0.0041 ms | 報告實測 |
| **⑤ 前置審計** | **0.29–0.35 ms** | **本輪實測 291.8 µs** |
| ⑥⑦⑩ 佇列 + 取件 + 回跳 | 0.130 ms | 報告實測 |
| **⑫ 後置審計** | **0.29–0.35 ms** | **本輪實測** |
| ⑬ `_note_price_type` | 0.004 ms | 報告實測 |
| **in-scope 合計** | **≈ 1.22 ms** | |

**其中兩次審計 = 0.70 ms = in-scope 預算的 57%。**
換成 persistent handle(我實測 2.8 µs)後 in-scope 降到 **≈ 0.52 ms —— 砍掉 57%**。
連「不做 fsync 只拿掉 `mkdir`」都是 **−0.14 ms = −11%**,零取捨。

**→ 「不要優化送單路徑的 Python」在「分母 = 89.6 ms」時成立;
在 user 自己訂的「撇除網路」規則下,對**審計那兩段**是相反的結論。**
報告 §6「不要動」清單裡的「送單路徑的任何 Python 微優化 —— 全部加起來只有 1.14 ms / 89.6 ms」
這一條,**在這份 user 目標下不該原樣採用**。

**但要說清楚兩件事,免得矯枉過正:**
1. 這 0.7 ms **對交易結果沒有意義**(對手是 88 ms 的券商往返 + 秒級的市場)。
   它的價值是「這是本機唯一一段可控且尚未壓縮的成本」,屬於**量化系統的衛生**,不是 alpha。
2. `safety.py` / `mapping.py` / `stkfut_map` 的 `stat()` cache / COM 執行緒模型 /
   `shield` + 「結果未知」—— **這五條不要動的判斷我完全同意**,而且理由與延遲無關。
   我特別複驗了 `_cmd_q.get(timeout=0.05)` 不是輪詢週期這條:
   `queue.Queue.get` 阻塞在 `threading.Condition`,`put()` 會 `notify()`。
   **機制正確,不要為那個 50 ms 去改它。**

---

## 8. 給下一步的三句話

1. **先改三處措辭再開 ticket:** C1 不是死碼(是「零觀測、根因未知」,頭號候選是 Solace 那一對);
   「999 全是額度」是 30/40;「7.6% 長尾」是 0.6%–7.8% 的區間上界。
2. **Step 4 換方向也換判準:** 尾巴 100% 是 1019(310 筆、每次 +1,060 ms、
   庫存段 ≥2 s 的 92% 命中),而「三段並行」會製造更多 1019;
   驗收尺要先去掉開機重播污染。
3. **Step 0a / 0b / 0c 照做,並把 `mkdir` 那一行順手拿掉** ——
   它是整條送單鏈上最便宜、零取捨、報告完全沒看到的一格。
