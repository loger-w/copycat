# C2 — 交叉一致性與完整性批判(第四輪:10 區複驗 + 實測擂台)

2026-09-13。輸入 = 三份功能報告 + 全域綜整 + 44 份分區長篇 + 本輪 10 區(3 份對抗式複驗、6 場真的裝了套件跑的擂台、1 份 TC4 併發重評)。

**本輪與前三輪的性質差異必須先講清楚**:前三輪是 56 個 agent 的離線 micro-benchmark 與投票,綜整報告自己在 §0 寫了「上面 457 條的每一個量級,全部是離線 micro-benchmark + 推估」。本輪是**真的裝了 numpy / orjson / msgspec / polars / duckdb / pyarrow / winloop / zustand / uPlot / lightweight-charts,真的開了 free-threading build,真的用 CDP 對真 Chrome 抓 trace,真的對開著的達錢 4 發電文**。所以本輪的職責不是再投一次票,是把票推翻。

---

## §0 一句話

**前三輪的方向大致對、排序大致錯,而排序錯的根因是同一個:它們量的是「這個函式跑多久」,沒量「換掉它以後系統少停多久」。** 本輪實測推翻了 13 條被寫進改造路線的結論,其中最貴的三條是:(a) 綜整報告 Layer 0 的「一行 `timeBeginPeriod(1)` 壓到 0.7 ms」在 Windows 11 上**單獨呼叫三秒後失效**,而它寫的驗收判準會在那三秒內回報 PASS;(b) 「TC4 無上限 → 回補開專用 session」這條被 user 新事實解鎖的最大機會,實測**收益為 0**,真正的第一刀是一顆 `0.15` 的常數(3.5x、改一行);(c) 「最大收益全部來自刪掉重複工作、零新相依」不成立 —— WS 出站換 orjson 實測 8.7–77x、HTTP 大 payload 繞過 FastAPI response chain 實測 3.6–6.4x,但**同一句話的反面也不成立**:CorrState 換 numpy 只有 10x,而純 Python 增量是 208x 且 numpy 增量版比純 Python **還慢**。工具換不換,要一格一格量,不能整批表態。

---

## §1 矛盾清單

### 1.1 同一個數字在不同地方不一樣

| 量 | 各處的值 | 判定 |
|---|---|---|
| `CorrState.correlations()` 單次 | 綜整 11.6–13.7 ms ‖ X4 13.60 ms ‖ V1 8.955 ms ‖ **T2 9.153 ms(sparse 25%,對齊 `configs/correlation.json`)/ 12.240 ms(全 dense 上界)** | **可調和**:兩端分別是 sparse 與 dense 上界;11.6–13.7 那個區間其實是 dense 側,被當成常態值寫進「每秒固定停頓」表。常態應取 ~9 ms。 |
| 送單端到端 mean | 綜整 §4 Layer 0「**70 ms**、511 筆」‖ 下單報告 §1「**89.6 ms**、536 對」‖ 同報告 §5 Step 0c「現有 **499** 對」‖ **V2 獨立重跑 89.6 ms / 536 對 / bootstrap 95% CI [61.6, 119.4] ms** | **真矛盾,三個數字**。V2 用自己的配對規則重現了 536 與 89.6(逐字),所以 70 ms / 511 筆 與 499 對 都錯。更要緊:89.6 的 CI 是 ±33%,且 0.56% 的樣本貢獻 18.8% 總質量 —— 三個數字誰對其實不重要,重要的是**這個量根本沒有三位有效數字的精度**。 |
| 1K bar 全掃 21,254 檔 | 綜整「**18 s**」‖ **T3 同一台機器三支腳本 10.415 / 12.299 / 14.162 s(±35% 漂移)** | **18 s 應撤回**。T3 明確指出機器負載漂移 ±35%,並因此把所有倍數限定在同一次執行內比。18 s 很可能是一次高負載取樣。 |
| `/api/stock/group-state` 150 檔 | 綜整 ~33 ms ‖ B04「上限 150 檔 = 103 ms」(查核降為 54 ms)‖ **T1 現況 FastAPI 路徑 22.39 ms(3.41 MB)/ pydantic dump_json 19.38 ms(4.09 MB)** | **可調和但要收斂**:103 → 54 → 33 → 22.4,四輪各降一次。T1 是唯一一次走真實 FastAPI response chain 量的,應以 22.4 ms 為準;33 ms 與「19 ms 序列化 + 14 ms dict 建構」相符,也可接受。103 ms 必須從所有引用處撤掉。 |
| `applyTick` 成本歸因 | 綜整 Layer 3「**82% 在 `new Map(acc.minutes)`**」‖ V1「vp=124 時 73.9%,**vp=900 時 minutes 只剩 21.4%、vp 佔 68.5%**」‖ **T6「vp=200 時 minutes 60.0% / vp 38.4% / ticks 5.0%;vp=60 時 minutes ~78%」** | **82% 只在 vp 小的一種形狀成立**。V1 與 T6 兩個獨立量測都指向「vp 一多就變 6:4 甚至反轉」。`stock-accum.ts:451` 的註解自己寫著 vp「autofit 的低價股可以近千檔」。**只修 minutes 最多拿到六成,在最貴的形狀只拿到兩成。** |
| Windows timer drift | 三份報告一致寫 12.43 ms 並標「**這是地板**」‖ **T4 重現 base 12.571 ms,但 EcoQoS 豁免 + tbp 後 0.556 ms(22.4x);且 1000 則/s 推播下自然降到 0.626 ms** | **「地板」是錯的**。它既可以用兩行 API 消掉,也會被自家推播流量自然消掉。詳見 §2.1。 |
| full GC 停頓 | 綜整「71–108 ms,一天 2–3 次」(被 V1 引為閃電梯最壞延遲的組成)‖ **T4 `gc.collect()` 全量 53.86 ms;擬真盤中(30 萬長活 tick + 150 萬配置)自動 GC 最壞單次 25.53 ms** | **71–108 ms 是 `gc.collect()` 的數字,不是盤中會發生的事**。盤中真正的 stop-the-world 上界是 25.5 ms。V1 的「book 最壞 ≥100 ms」用了這個偏高的組件。 |
| ProcessPool 回測加速 | 綜整「8–12x 推估…可能 4–8x」‖ **T4 用真的 `simulate_sample` 實測:熱池 4.45x、含 spawn 3.10x;天真切法 0.03x(慢 30 倍)** | **連被 hedge 過的 4–8x 都偏高**。8 physical core、SMT 對吃記憶體的工作幾乎無加成。 |
| WS `send_json` 打包單價 | V1「300 筆 375.69 µs」= 1.25 µs/筆 ‖ **T1「200 筆(27,120 B)158.87 µs」= 0.79 µs/筆** | **未解,差 58%**。兩邊都標實測、都用 starlette 逐字同參數。差異來源應是 item 欄位形狀不同(V1 未列 payload bytes)。**倍率一致(8.4x vs 9.2x),絕對值不可互換引用。** |
| 訊號 tick 路每則成本 | 訊號報告 78.5 µs(7 slot)‖ S8 L6 **94.6 µs**(同窗長)‖ on_book 26.4 vs S8 23.9 µs ‖ 記憶體 100→14 MB vs S1 §5 **39→5.6 MB(差 2.5 倍)** | **真矛盾,兩邊都標實測**。V3 指出報告挑了其中一份且未註明另一份存在。**後果:Step 3 的驗收判準「從 78.5 降到 ~10 µs」在基準有 2.5 倍歧異時無法判定達標。** |
| jsdom vs 真瀏覽器 | repo `StockIntradayChart.tsx` N047 註解「真瀏覽器的 diff **快一個量級**」(綜整 §5 Layer 4 據此推 1.5 ms/卡並結論「不值得換寫法」)‖ **T5 同一份元件碼實測:1140 rect jsdom 13.09 / Chrome 4.0 ms = 3.3x;1140 path 兩邊一樣快(0.96x)** | **高估 3 倍,且倍率不是常數**(節點多時 6.8–9.2x,path 化後降到 0.96–2.6x)。 |
| 政策 P 放到尾盤 | 訊號報告「**−2,822** vs 研究 +5,784」‖ **V3:−2,822 的單位是「元/張」,+5,784 的單位是「每筆 50 萬名目」(`combo_wlpolicy.py:4` 逐字);同一批 23 筆換成 50 萬名目 = +4,003,符號相反** | **單位錯配,必須改掉才能用**。而且支撐材料 S8-09 用的就是 50 萬名目並算出 +4,003 —— 報告挑了嚇人的那份且未提另一份。 |
| 影子期起算日 | CLAUDE.md + 訊號報告「2026-09-08 起四週」‖ **V3:`20260907.jsonl` 有 29 列政策列,sweep rule_id epoch = 09-07 08:03:18,對應 `logs/server-20260907-0803.log`** | **repo 自身不一致**。四週結束日、「第一週」是 4 天還 5 天,現在都是混的(報告所有 n 建立在 5 天上而敘述說 4 天)。 |
| `_TICKS_MAXLEN` 母體 | 看盤報告 median **2,247** / 合計 381,107 / 90 檔 ‖ **V1 重跑同一份 log:median 2,834(每檔取首筆)或 131(全 167 列),合計 380,606,89 檔;max 30,598 兩邊逐字相同** | max 一致,median 來源不明。更關鍵的是**報告沒給頻率:89 檔裡只有 2 檔(2.2%)超過 20,000**。 |
| signals jsonl 母體 | S8 §0「26 個交易日 / **8,003** 列」‖ **V3 全量數到 8,789 列(差 786)** | 任何以 8,003 算比例的支撐段落要重算。 |

### 1.2 結論相反(本輪內部的對決)

| 題目 | 一邊 | 另一邊 | 誰對、證據 |
|---|---|---|---|
| **CorrState 該換什麼** | **V1**:換 numpy,實測 8.955 → 0.909 ms(10x),逐值差 1.388e-16,可寫 golden 釘死;並批評「報告把 numpy 的否定寫在 RiverState 上,沒分辨密集浮點時間序列」 | **T2**:同一顆函式跑了 7 個變體 —— numpy 整批 5.7x、numpy ring 22.6x、**純 Python 增量 running sums 208x**、**numpy 增量 183x(比純 Python 慢 14%)**;另有逐位元相同的保守版 G(3.1x) | **T2 勝**,理由是它做了頭對頭而 V1 只比了兩點。V1 的「該分辨 CorrState 與 RiverState」這個批評成立且重要,但它推出的答案(numpy)只是次佳解的次佳解。**在 10 腿 × 3 窗這種小陣列上,ndarray 的 dispatch 開銷已經超過 30 次 Python float 加法。** |
| **REST 側要不要動** | **V1**:CONFIRMED「FastAPI 已走 pydantic-core Rust 快路徑,orjson 只有 2.6x,**不必換**」,並誠實記「我一開始也猜錯」 | **T1**:比了四條路 —— ① 現況 dump_json、② ORJSONResponse(**慢 1.4–2.2x**)、③ JSONResponse(慢 2.7–3.6x)、**④ route 直接回 `Response(orjson.dumps())`(快 3.6–6.4x)**,因為 `fastapi/routing.py:695` 的 `isinstance(raw_response, Response)` 會整條短路 | **T1 勝**。V1 與綜整報告都只比了 ①②,結論「不必換」對 ②③ 成立、對 ④ 不成立。個股全量 snapshot 9.31 → 1.46 ms,是本輪能把單發 event-loop stall 砍掉一個量級的唯一一條。 |
| **TC4 無上限解鎖了什麼** | **V1 missed #5**:「回補走專用 session,把開盤回補與看盤取數分流 —— 這是新事實解鎖的最大機會,報告完全沒有這條」 | **C1 對開著的達錢 4 實測**:6 發目錄查詢分 1–6 條 lane,牆鐘恆 ~19 s(最佳 1.04x);跨 session 的目錄查詢照樣把冷日 K 從 43 → 3101 ms(72x);分流 lane 只救回 7%,而那 7% 恰好等於兩次目錄查詢本身的時間差 | **C1 勝,而且是決定性的**。阻塞點在 TC4 桌面 app 裡,不在 client 的 `api.lock`。user 的新事實講的是**併發許可**(8 條並發 LOGIN 全過),不是**併發吞吐**。V1 自己有警告「方向別走反:SUB 要收斂、REQ 才是要放開的」—— 那個警告對,但 REQ 放開也沒用。 |
| **前端最大的單一遺漏是什麼** | **V1**:`applyTicks` 批次化(effort S、零契約、實測 N=20 15.9x / N=50 53.3x),「照報告做會直接跳到 effort M 的容器重構,而這個被跳過」 | **T6**:整條 accum 路徑在真實 200 tick/s 下 = **主執行緒 0.29%**,最壞單筆 330 µs;換成最快的定長陣列是 119x,但只值 **0.28 個百分點** ‖ **T5**:同一時間圖牆的 SVG 渲染是 **56.83 ms/拍**(50 卡全動)或 5.10 ms/拍(2/50 動) | **兩邊數字都對,V1 的 verdict 錯**。V1 的 N=20 省 257 µs/則 × 10 則/s = 2.57 ms/s ≈ 0.26% —— 與 T6 的 0.29% 完全一致。**倍數 5–53x,絕對值 0.3 個百分點。** 前端真正的大頭在 T5 那一格,差兩個量級。 |
| **EnergySub 怎麼修** | **綜整 §5 Layer 4 + F2-02 + _MISSED-143**:「卡片變體其實是退化重疊繪製…**降採樣比 path 化更便宜**」 | **T5 真 Chrome CDP 實測**:降採樣到 170 根 = **1.44x**(該層 44.99 → 31.20 ms)且**資料失真**(桶內取 max,副圖 maxTotal 與資訊列的「量」不再同源);單一 `<path>` = **3.12x**(→14.42 ms)逐像素相同;canvas = **6.58x**(→6.84 ms) | **T5 勝,降採樣應撤回**。成本在「元素個數 × (React reconcile + DOM 屬性寫 + Blink 樣式重算)」這條線性項上,271→170 只是沿線滑一格。 |
| **1K bar 該換什麼格式** | **綜整 Layer 4**:「21,254 個小檔…55% 花在建 Bar1K…**parquet / 記憶體 cache 在這裡明確勝出**」 | **T3**:55% 複驗成立(53.5%);但 **per-file parquet 全量 0.85x、要建 Bar1K 0.58x、單檔隨機讀也更慢** —— parquet 的 177x 完全來自「整併成一個檔」不是「格式」;而且**整併之後 stdlib `array.array` 0.195 s 追平 numpy 0.228 s** | **T3 勝**。「parquet 勝出」這個措辭會讓人做出一個更慢、又多一個相依的版本。真正的變數是「整併 + 不建物件」。 |
| **stock_state 為什麼不該換 numpy** | **綜整**:「n 太小 / 已經是增量、換 numpy 只會變慢」 | **T2**:結論成立但**理由錯** —— 30,598 筆對 numpy 綽綽有餘,而且 numpy `aggregate()` 的輸出與現況**逐欄全等**(做得到);真因是「這裡已經是增量了,任何批次化都是把 O(1)/tick 換成 O(n)/snapshot」,系統級 **差 52x**。另加對照組拆穿:numpy 逐 tick 的「快 3x」全來自延後聚合,純 Python 延後(list.append)**比 numpy 寫陣列還快 1.69x** | 結論一致、理由必須改寫。**理由錯會讓下一個人用「n 夠大了」推翻一個正確的決定。** |
| **前端狀態要不要外移 / 換 store** | **_REFUTED 清單**:zustand 全票否決,理由「前端的問題是 memo 邊界與節流,不是計算量」 | **T6 真 Chrome prod build 六變體對照**:結論一致(不要換),但理由要改 —— **memo 邊界現況已經正確**(每則更新只重畫 1 張卡,六種架構的 card 渲染數一模一樣都是 1000),所以這些套件**連「修 memo 邊界」這件事都沒得做**;它們拿到的 20–30 µs/則全來自「App 不再重繪」,而那件事 uSES / 既有 EventTarget **用零新依賴就拿得到**(bus 65.0 ms vs zustand 62.8 ms,差 3% 在雜訊內) | 結論一致、理由要改寫。 |
| **`bAsyncOrder=1` 的優先序** | **綜整 Q8**:「配合 98.5% 延遲在 SendStockOrder + pump,**這是下單延遲的最大單一標的**」 | **V2**:唯一理由「7.6% 的 ≥1 s 長尾」是區間**上界**,可證實的下界只有 **0.56%**(42 次跨秒幾乎全可用「平均 80 ms」解釋);而 D1 §3.2 自算不先做 `MsgWaitForMultipleObjects` 會 **+25 ms 淨負**;且它是報告自標「新 code 第一次執行必然在盤中真錢」的最高風險項 | **V2 勝,應降級**。收益被高估一個數量級。 |
| **`_distribute` 補 `enabled` 檢查的收益** | **綜整 Layer 1**:「停用的 CDP 規則仍付全額狀態推進,純死工」(訊號報告標「實測 2.1 µs/tick」) | **V3**:`data/signals_enabled.json` 只有四鍵且全 true,surge_pullback / sweep_cluster 缺鍵 fail-open → **prod 七條規則全部 enabled,現值 = 0 µs**;支撐材料 S3 誠實標過「這條今天沒有損失」,報告把那句拿掉了 | **V3 勝**。程式面問題真實,但它是「使用者按了停用之後反而沒省到」的陷阱,不是今天在燒的錢。同一步裡真有收益的是 `evaluate_book` latch 短路。 |
| **X3-02「第一個要先解的」** | **_DIGEST**:「若目標是改造成高效能量化系統,這條是第一個要先解的:**在它之上做的任何平行化都是假的**」 | **C1**:問題描述成立且首次量化(同 session head-of-line **1800x**:2981 ms vs 1.6 ms),但修法方案 B 收益 0、方案 A 只有模型支撐;而**真正的第一刀是 `_POLL_BACKOFF_START = 0.15`** —— 一次冷日 K 的 153 ms 裡有 **150.5 ms 是我們自己的 `time.sleep(0.15)`**,TC4 真正備妥只要 15–40 ms | **問題對、排序錯**。四輪掃描把它歸類成「TC4 取數慢」,其實是一顆常數。 |

### 1.3 單一份材料內部自相矛盾

| 位置 | 矛盾 |
|---|---|
| 看盤報告 §3 第 9 列 | 同一列的「位置」欄寫「`tests/test_corr_config.py` **有釘**」,「靜默」欄寫「**是**」。 |
| 看盤報告 §4 Step 3 vs Step 9 | Step 3 的風險欄逐字寫「改它要先解決 **Step 9** 的供應鏈問題」,卻把 Step 3 排在 Step 9 **前面六步**;而 Step 9 的收益欄寫「五條 KeepAlive 執行緒與其 ZMQ Context **直接不起**」→ Step 3 的 KeepAlive 半邊在 Step 9 之後 100% 白工。 |
| 下單報告 §3 vs D1-08 | §3「被查核修正的兩條」寫 999 是「**30 次**實證」,D1-08 寫「999 ×40 **全是** 249 萬」。V2 逐列聚合:30 筆是 249 萬,另 10 筆是四種不同原因(未簽風險預告書 ×4 / 集保庫存 0 ×4 / 可沖銷 0 ×1 / 融資額度 ×1)。 |
| 下單報告 §1 vs §5 Step 0c | 536 對 vs 499 對。 |
| 下單報告 D1 失效表 #4 | `_pump_once` 例外標 ★ 零錯誤訊號,而**同一列的「現在怎麼發現」欄就寫了 `grep "COM 幫浦圈例外"`** —— `client.py:792` 確實有 `logger.exception`。 |
| 訊號報告 §0 表格第 2 列 | 同一格內「83 列」是去重版、「−2,822」的 n=23 來自 92 列未去重版(83 列版是 −2,950);「5.2/日」取去重版而「2.7 倍」的分子取未去重版(5.4)。 |
| T4 內部 | 硬否決 free-threading 的理由是 pywin32 沒有 cp313t wheel;但在建議不導入 msgspec 時,又把「會把 free-threading 那條長期路線的門關死」列為代價。**門已經被 pywin32 關死了**,這個代價論證自我抵銷。 |
| 綜整 §3 vs §4 Layer 1 | §3 結論「最大的收益**全部**來自刪掉重複的工作與加閘,零新相依」;§3 同節又寫「orjson 真正該指的地方是 WS 出站」—— 那是一個新相依。本輪實測 WS 出站 orjson 是全後端收益最大的單一改動之一(N=1 已 8.7x),所以「全部」這個字要拿掉。 |

---

## §2 被本輪實測推翻的先前結論(最有價值的產出)

依「推翻的貴重程度」排序。

### 2.1 ★★★「Windows timer 12.43 ms 是地板」+「一行 `timeBeginPeriod(1)` 壓到 0.7 ms」

三份報告(綜整 R2 / 看盤 §2.3 第 97 行 / Layer 0 第 2 項)一致把 12.43 ms 寫成「**這是地板,所有 ms 級量測都要先扣掉它**」,並開了一行處方。

**T4 用 6 支腳本、8 種配方追這個雙峰,結論全部相反:**
- `timeBeginPeriod(1)` 單獨呼叫**只有效約 3 秒**就被作業系統收回(p50 退回 12.602 ms,0% 落在 2 ms 內)。重複呼叫、End+Begin 循環、`NtSetTimerResolution` 直呼、HIGH_PRIORITY_CLASS、常駐 armed 的 high-resolution waitable timer、每 1 ms 的 `call_later` —— **全部無效**。
- 真兇是 Windows 11 的 **Power Throttling(EcoQoS)**:預設對背景 process 忽略 timer resolution 請求。決定性對照 = 同腳本 `-WindowStyle Normal`(有可見 console)全程 0.544 ms、`-WindowStyle Hidden` 三秒後退回 12.6 ms。而 `run.ps1` 現行就是 `-NoNewWindow`。
- 正解是**兩行**:`SetProcessInformation(GetCurrentProcess(), ProcessPowerThrottling, {ControlMask: EXECUTION_SPEED|IGNORE_TIMER_RESOLUTION, StateMask: 0})` + `timeBeginPeriod(1)` → p50 **0.556 ms**、p99 1.98 ms、98.8% 落在 2 ms 內、全程穩住。
- **而且它不是地板**:一條限速 producer 敲門就能把 drift 自然壓下來 —— 10 則/s 時 12.24 ms、100 則/s 時 3.42 ms、300 則/s 時 2.89 ms、**1000 則/s 時 0.626 ms 且 100% 在 2 ms 內**。盤中 TC4 推播密集時 drift 本來就只剩 2–3 ms。

**最貴的一點:看盤報告 §4 為這一步寫的驗收判準是「重測閒置 `sleep(0.05)` 超出量:p50 從 12.43 ms 降到 < 1 ms」。照這個判準,一個只寫了 `timeBeginPeriod(1)` 的錯誤實作會在前三秒回報 PASS。** 判準本身會產生假綠燈,而且零錯誤訊號。

副作用:R1 的收益要誠實拆成「盤外 ~12 ms、盤中 ~2 ms」,而且 `queue.get(timeout=)` 這一族完全不受影響 —— **下單路徑 `capital/client.py` 的 `_cmd_q.get(timeout=0.05)` 不在受益範圍**,不能算進去。

### 2.2 ★★★「TC4 無上限 → 多開 lane / 回補專用 session」

C1 在週日對**開著的達錢 4**(PID 22260、5 條 prod session ESTABLISHED)發了 refcount-free 電文,全程零 `SUBQUOTE REALTIME`、零 `UNSUBQUOTE`:

- **並發 LOGIN 可行**(8 條全過、相異 SessionKey 8),user 的新事實為真。
- **但併發吞吐 = 1**:6 發目錄查詢分 K=1..6 條 lane,牆鐘恆 ~19 s(最佳 1.04x),每發延遲隨 K 線性放大 —— 單伺服器佇列的教科書指紋。
- **跨 session 也擋**:目錄查詢在飛時,別條 session 的冷日 K 從 43.3 → **3101 ms(72x)**;分流 lane 只救回 7%,而那 7% 恰好等於兩次目錄查詢本身的時間差(同 lane +106 ms、分流 lane +105 ms,**逐字相同**)。
- **8 條 lane 相對 1 條只快 10–14%**,離線性加速差一個量級。
- 附帶決定性發現:**8 條 session 全部拿到同一個 SubPort(56942)** → 多開 session 在 SUB 側是純負(多一條 naive 通道 = +14.7 µs/則)。

**所以 X3-02 的方案 B 應直接刪除,V1 的 missed #5 應撤回,而 X3-02「第一個要先解的」這個排序要讓位給 §2.3。**

同時被推翻的還有**問題的量級描述**:C1 首次量化了 head-of-line —— 重查詢在飛時,**同一條 session** 的輕請求 p50 **2981 ms**(4029× 閒置),**另一條 session** 的輕請求只要 1.6 ms(2× 閒置)。所以「api.lock 讓平行變假」成立,但「鎖飽和」不成立:用本輪單價重算,overlay sweep 期間 `api.lock` 佔用率只有 **~6%**。`basis_gap_secs = 0.2` 這顆節流常數,是為了保護一把 6% 佔用率的鎖而存在的。

### 2.3 ★★★ 一次冷歷史取數的 153 ms 裡,150.5 ms 是我們自己的 `sleep`

C1 逐發拆解:`SUBQUOTE` 0.61–1.07 ms + `GETHISDATA` 0.46–0.85 ms ×2 → **REQ 總和只有 1.81–2.65 ms**,其餘 150.4–150.6 ms 是 `_POLL_BACKOFF_START = 0.15` 的 `time.sleep`。輪詢間隔掃描:150 ms→152.5 / 50→52.5 / **20→22.3** / 10→23.5 / 2→17.4 / 0→15.5 ms。

**四輪掃描都沒發現,因為那個均勻度(標準差 < 0.3 ms)看起來太像「穩定的服務時間」—— 而真正穩定的東西正是我們自己的常數。** 改一行(起點 0.15 → 0.02,倍增與 1.0 s 上限不動),冷歷史取數 3.5x,150 檔進群組冷 overlay 由 5.8 s → 2.6 s。

### 2.4 ★★「最大收益全部來自刪掉重複工作、零新相依」

綜整 §3 的「真正的結論」。本輪三處實測反例:

1. **WS 出站**:`starlette/websockets.py:174` 逐字 `json.dumps(data, separators=…)`,stdlib、在 loop 上、**每個 client 各一次**。T1 量的三種修法:A(只去 N 倍)N=1 零收益;**B(1×orjson + N×send_text)ticks 40 items N=1 已 8.7x、N=4 36.1x、N=8 77.4x**;C(binary frame)幾乎無額外收益卻要改前端 —— 不值得。**關鍵判讀:N=1 就已經贏 7.5–9.1x,所以「現在只有 1–2 個分頁所以不急」是錯的推論。**
2. **HTTP 大 payload**:`Response(orjson.dumps(payload))` 繞過 response_field 鏈,個股全量 snapshot 9.31 → **1.46 ms(6.4x)**、group-state 150 檔 22.39 → 6.24 ms(3.6x)。
3. 反向:**CorrState 換 numpy 只有 10x,純 Python 增量 208x**;**1K bar 整併後 stdlib `array.array` 追平 numpy**;**breadth 換 numpy 是 0.79x(倒退),純 Python 手工優化 1.71x**。

**正確的收斂:序列化該換工具(Rust parser/encoder 真的快一個量級);數值聚合該換演算法(增量 > 向量化重算)。整批表態「零新相依」或「全面上工具」都會做錯。**

### 2.5 ★★ EnergySub 降採樣(T5 逐像素對照 + CDP trace)

見 §1.2 表。另附 T5 的三條連帶推翻:
- **`Painting` 從頭到尾不是瓶頸**(最糟的手刻 SVG 也只佔總量 10%),真正的兩座山是 Scripting 34.31 ms 與 **Rendering/樣式重算 17.03 ms** —— 後者佔現況 30%,**在上一輪的純 JS 微基準裡完全看不見**。
- **虛擬捲動的收益遠低於直覺**:50 卡全可視 vs 只有 3 列可視,main-thread 每拍 58.12 vs 56.83 ms(噪音內)。React reconcile 與樣式重算對捲出畫面的卡照樣發生。
- **零相依的 path 化已經打贏一個 62.6 KB 的圖表庫**(26.08 vs lightweight-charts 30.44 ms),而 lightweight-charts 每圖開 7 個 canvas、50 圖 350 個、**JS heap Δ +17.16 MB 全場最高、比 18,552 個 SVG 元素還高**。Q2 那句「50 卡不要開 50 個庫實例」被坐實。

### 2.6 ★★ `slots=True` 「一行拿走 36% 的 full GC 停頓」

T4 擬真量測(150 檔 × maxlen 2000 = 30 萬長活 tick,配置 150 萬新 tick,用 `gc.callbacks` 量**自動** GC):

| | 最壞單次自動 GC 停頓 |
|---|---|
| `dataclass(frozen)`(= 現況 StockTick / Tick) | **25.53 ms** |
| `dataclass(frozen, slots=True)` | **24.63 ms(噪音內)** |
| `tuple` | 0.39 ms |
| `msgspec.Struct(gc=False)` | **0 ms(自動 GC 次數 = 0)** |

**兩者都是 GC-tracked,gen2 的 stop-the-world 掃的是「被追蹤的物件數」不是 layout。** slots 真正買到的是記憶體 −30% 與長活集合 full collect −38%,**不是盤中那一下 25 ms**。上一輪拿 `gc.collect()` 全量掃的數字去論證「盤中會不會卡」是換錯了題目。

### 2.7 ★★ 下單報告 C1(OnConnect/OnDisconnect 綁定壞了)

V2 逐層查完:sink 有實作、有 advise、advise 的是 typelib 宣告的正確 outgoing interface、方法名 dispid 1/2 對、**引數逐位元相符**、有單元測試、log level 擋不住。**沒有東西可修 —— Step 1a 照做是 no-op。**

零觸發是真的(獨立 grep:四種訊息各 0 行),但真正的候選根因是同一介面的 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect`(dispid 9/10),`grep Solace copycat/capital/*.py` **零命中**,comtypes 對 sink 未實作的事件靜默忽略。**這個假說同時解釋 3,201 則 OnNewData 正常與 OnConnect 零觸發;原假說解釋不了前者。**

順帶:`3,531 則 OnNewData` → 實際 **3,201**(差 10.3%),那是最容易查的一個 grep。

### 2.8 ★★ 回流鏈「三段並行」與它的驗收判準

- **方向相反**:`grep "GetRealBalanceReport rc" logs/*.log` = **310 筆,100% 是 `rc=1019 SK_ERROR_QUERY_IN_PROCESSING`**。每多一次 1019 精準多 ~1,060 ms;庫存段 ≥2,000 ms 的 25 條裡 **23 條(92%)窗內有 1019**。報告把一個**現行且高頻**的失效寫成「若改成並行可能撞 1019,要先用一天 prod 驗」—— 那一天的資料躺了 22 天,而結論是並行會**製造**更多 1019。
- **判準會自我污染**:`client.py:421` 每收一筆成交就覆寫 `_fill_seen_at`,而 `_log_chain_stage` 印 `now - _fill_seen_at`。三個指紋全抓到:8 條累積值**非單調遞增**、4 條缺「庫存段」起點、25 條庫存段 < 500 ms(0.5 s debounce 結構上不可能被跳過)。污染樣本 28 條中 **22 條(79%)在 server 啟動 2 分鐘內**,且方向是把數字拉小。**「grep 'balance 鏈' 的 p50 從 1,940 ms 下降」這個判準,多重啟幾次就會過,程式可以一行都沒改,而且零錯誤訊號。**
- 乾淨子集(盤中 + 單調 + 庫存段 ≥500 ms,139 條):p50 1,979 / **p90 3,027**(報告寫 4,103)/ p99 6,433。

### 2.9 ★「16 條裡有 10 條是靜默的」

V1 逐條回原始碼與測試:#1/#2 有 threading.excepthook traceback(`__main__.py:131` tee 到 log)+ `_start_healer` 的 WARNING 洪水;#4 有 `ws.py:82-97` 的 60 s 節流 WARNING + CLAUDE.md 明訂 grep 判準;#5/#7/#8/#9 有**跨語言 parity 測試(後端測試直讀前端原始碼字面)**,改任一邊 pytest 就紅、根本出不了門。**真正零訊號約 4–5 條。**

**而且報告自己的兩個 Step 各帶進一條新的零訊號失效,都沒標**:
- **Step 2 book 去重**:現況每則重送一份五檔,那份「浪費」剛好是丟包的自癒;去重後丟掉的那一則在五檔真的變動前**永遠不會被修** —— 鎖漲停時可以幾分鐘不變,**閃電梯停在錯的簿上、畫面完全正常**。這是真錢下單畫面。
- **Step 3 bytes needle**:`b'"DataType":"REALTIME"' in COMPACT` = True 但 `in SPACED` = **False**。TC4 是黑箱桌面 app,JSON 格式不是契約。needle 對不上 = **全市場資料靜默消失**,fail-closed。

### 2.10 ★「五檔 book 最壞延遲 ~3 ms」

V1:與報告自己的 §2.3 抖動源表直接矛盾 —— book 的產生與推播全在單一 event loop 上,而 corr(每秒)、group-state(每 60 秒)、GC、apply_backfill 全部排在它前面,單 loop FIFO 無優先序。

**但本輪也修正了 V1 的組件**:corr 實測 ~9 ms 不是 12.7–13.7;group-state 22.4 ms 不是 33–103;盤中自動 GC 25.5 ms 不是 71.8。所以真實最壞是 **~60 ms 量級**而不是 V1 寫的「≥100 ms」—— 仍然比報告寫的 3 ms 大一個量級,結論方向不變,但數字要用本輪的。

另外「~3 ms」這個數本身源自 `F4-ladder-highfreq.md:170`,原文自標「**需以 §7 的量測計畫驗證**」= 推估,只含前端 render JS 側,不含 layout/paint。

### 2.11 ★ 訊號 Step 0「每過一天,那一天的樣本就永久不可還原」

V3 逐件查:`data/signal_rules.json` mtime = **2026-08-15**,影子期至今**零次規則編輯**;種子卡 params **每次開機逐條印在 log**;有效規則集 = 磁碟檔 + code SHA 完全可還原;開機斷點可由 logs 檔名 + jsonl 的 rule_id epoch 重建(V3 實際重建出全部 8 個批次、3 次盤中重啟)。**只有 0c(未命中事件的族群快照,73/205 = 36%)是真的不可還原。** 標「最急」的 0a 至今零損失。

順帶 0e 的判準「重啟兩次,`data/signal_rules.json` 的 id 不變」**今天就已經成立**(`load_rules` 不回寫檔案),改不改都會過。

### 2.12 ★ winloop「收益 < 5%」

綜整 §3 引查核結論「瓶頸是純 Python CPU 不是 socket 層,收益 < 5%」,並把 winloop 列為分歧項(0 建議 / 4 有條件 / 4 不建議)。

T4 在真 stack(uvicorn 0.52.4 + FastAPI + websockets)實測:**WS RTT p50 128.7 → 95.8 µs(1.34x)、WS 吞吐 7,435 → 9,576 msg/s(1.29x)、HTTP p50 451.3 → 356.7 µs(1.27x)**;raw socket 層 1.75–1.94x。而 B02-06 / B04 當初的兩個否決理由(子行程 API、ZMQ 交接)**實測逐條被駁回**:`create_subprocess_exec` rc=0、ZMQ 阻塞 recv + `call_soon_threadsafe` 50/50 全到、`pythoncom.CoInitialize()` ok、uvicorn clean_exit,而且 winloop **支援 `add_signal_handler` 而 Proactor 不支援**。

**「< 5%」這個數字在任何一份材料裡都沒有量測出處。** 但要誠實:1.27–1.34x 是打在 socket 層,而 T4 自己也指出 starlette/FastAPI 的 Python 開銷佔大頭 —— **賣這條要用 1.34x 不是 1.94x**,而且三塊驗證(3566 條 pytest 在 winloop 下、五條 TC4 真連線、關機 lane 並行退訂)本輪一條都沒跑。

### 2.13 ★ ProcessPool 8–12x / 4–8x

T4 用真實 `simulate_sample`(512 arms × 1000 樣本、checksum 逐字驗過):熱池 **4.45x**、含 spawn **3.10x**。並抓到兩個陷阱:天真 `ex.map` **0.03x(慢 30 倍)**(4.56 MB bars 被每 task 重 pickle,而一個 arm 只有 103 B —— 4 萬倍落差);用 `initargs` 傳資料時 **16 worker(1.60x)比 4 worker(2.14x)還慢**(parent 端 pickle 是串行的)。

---

## §3 以 user 目標重排的 ROI 清單

判準:高效能、量化等級、前後端都用最快的工具、**撇除網路**(所以 88 ms 群益往返不進預算;V2 據此重算本機可控成本 ≈ 1.22 ms,其中審計兩段佔 57%)。

### Tier 0 — 一行到數行、零新相依、零契約、全部實測支持

| # | 動作 | 實測收益 | 標籤 |
|---|---|---|---|
| 0-1 | `_POLL_BACKOFF_START` 0.15 → 0.02(倍增與 1.0 s 上限不動) | 冷歷史取數 153 → 22–43 ms(**3.5x**);150 檔進群組 5.8 → 2.6 s | **實測支持**(C1 probe_05/09/10/11,真 TC4) |
| 0-2 | EcoQoS 豁免 + `timeBeginPeriod(1)`(**兩行,缺一不可**,回傳值必須檢查) | timer drift p50 12.47 → **0.556 ms(22.4x)**、p99 14.2 → 1.98 ms | **實測支持**(T4,含 `-NoNewWindow` 複驗) |
| 0-3 | `CorrState` 改純 Python 增量 running sums + `has_clients` 閘 | 每秒總成本 9.153 → **0.044 ms(208x)**;max\|Δr\| 3.9e-15(對 `toFixed(2)` 小 12 個量級) | **實測支持**(T2,7 變體頭對頭) |
| 0-4 | `_eval_volume` 300 秒窗改 running sum | 1.40–293 µs → **0.100 µs 恆定**;實況 567 筆窗 **171x**、爆量 3,000 筆 909x;`qty` 是 int,10 萬次隨機驗證 0 次不符 | **實測支持**(T2) |
| 0-5 | `evaluate_book` latch 旗標整條短路(`_clock_key` 在早退之後才付) | 未量倍數,但 `on_book` 是全庫頻率最高的 Python 工作(簿更新 ≫ 成交),機制經 V1 原始碼確認 | **機制確認,倍數仍是推估** |
| 0-6 | `audit.py:33` 的 per-append `mkdir` 搬到啟動時 | 211.5 → 139.5 µs(**佔 34%**);送單路徑付兩次 = 省 0.14 ms = 本機可控成本的 11% | **實測支持**(V2) |
| 0-7 | `capital_api.py` 三行 `dataclasses.asdict` → `{n: getattr(o,n) …}` | 單列 8.2–9.3x;route n=400 819 → 91 µs;**asdict 比真正的 JSON 序列化還貴 11.7 倍** | **實測支持**(T1) |
| 0-8 | `sys.setswitchinterval(0.001)` | 4 條 CPU 執行緒在跑時 loop p50 15.53 → 3.54 ms、p99 95.09 → 21.59 ms;背景吞吐代價 −8.7% | **實測支持**,但代價是飽和執行緒的上界,真實 listener 未量 |

### Tier 1 — 小型、有明確收益、要一個新相依或動幾處

| # | 動作 | 實測收益 | 標籤 |
|---|---|---|---|
| 1-1 | **前置**:`river_state.py:162` 的 int 鍵改 `str(m)`(與 `stock_state._minutes_payload` 既有慣例對齊) | 本身 0 收益,但不做則下一條**一上線江波圖 WS 第一則 snapshot 直接 TypeError**;wire 上其實不變(JSON 物件鍵本來就只能是字串) | **實測支持**(T1,orjson 預設對非 str 鍵 raise) |
| 1-2 | `WsBroadcaster.publish` 入口 `orjson.dumps` 編一次 + `send_text`(**保留 text frame**) | ticks 40 items N=1 **8.7x**、N=4 36.1x、N=8 77.4x;quote N=1 7.5x | **實測支持**(T1) |
| 1-3 | 三支大 payload endpoint 改 `return Response(orjson.dumps(payload))` | 個股全量 snapshot 9.31 → **1.46 ms(6.4x)**;group-state 150 檔 22.39 → 6.24 ms;9 檔 0.86 → 0.18 ms | **實測支持**(T1,四條路對照 + 讀 `routing.py:695` 取證) |
| 1-4 | `EnergySub` 量柱 + VP 長條合併單一 `<path>` | 圖牆 50 卡每拍 **56.83 → 26.08 ms(2.18x)**;該層單獨 3.12x;DOM 18,645 → 3,009 節點;heap Δ +15.56 → +8.81 MB;**逐像素相同** | **實測支持**(T5,真 Chrome CDP trace,run2/run3 差 < 6%) |
| 1-5 | 前端 `QueryClient({defaultOptions:{mutations:{networkMode:"always"}}})` | 非效能,是正確性:曝險窗**沒有時間上界**(放行需 online **且** focus,由較晚者觸發);而 `onlineManager` 讀 `navigator.onLine`,與本系統唯一的 loopback 路徑**完全不相干** | **實測支持**(V2 讀 node_modules 原始碼) |

### Tier 2 — 中型,收益大但要動契約鄰居或做產品決策

| # | 動作 | 實測收益 | 標籤 |
|---|---|---|---|
| 2-1 | **tick 持久化**(64 KB buffered append,盤後轉 parquet) | 寫入穩態 p50 0.1–0.5 µs、**最壞單筆 0.11 ms、>1 ms 在 702,860 次寫入中 0 次**;日終 60.3 MB(jsonl)/ 7.8 MB(parquet);讀回 parquet 5.0 ms vs jsonl+json 1,045.8 ms(**209x**) | **實測支持**(T3)。三個地雷:絕不逐筆 fsync(p99 2,050 µs)、`ParquetWriter.write_table` 絕不在 loop 上(最壞 **200 ms**)、每筆 commit 的 sqlite 慢 7–29x |
| 2-2 | 執行緒→loop 交接改 `deque` + 「空 deque 才排一次 drain」旗標 | 5 producer @2000 則/s:**e2e p99 10,671 → 86 µs(124x)**;接真 ZMQ SUB 飽和時**現況會掉封包**(送 426,786 / 收 81,816、e2e p50 1.66 秒),批次版不掉、47,385 msg/s(3.48x) | **實測支持**(T4)。**固定週期 ticker 是陷阱**(1 ms ticker 的 e2e p50 是 1,241 µs,差 30 倍)。碰 CLAUDE.md §4 的 seq 對齊契約 |
| 2-3 | 群組卡片變體改 canvas 2D(單檔頁維持 SVG) | 在 1-4 之上再 2.31x,**對現況 5.04x**(56.83 → 11.27 ms);DOM 209 節點(90x);heap Δ +2.29 MB(6.8x);**零相依** | **實測支持**(T5,全語彙對等、截圖逐格對過)。需 user 拍板:`CardIntradayChart` 的 doc 明文反對「同一檔兩張不一樣的圖」 |
| 2-4 | 離線回測 `ProcessPoolExecutor` + initializer(只傳路徑 / shared_memory 名) | 熱池 **4.45x**、含 spawn 3.10x | **實測支持**(T4,真 `simulate_sample` + checksum) |
| 2-5 | `overlay_sem` 後面的等待隊伍換優先權序(**保留在飛上限**) | 互動 p95 **332 → 17 ms(19.5x)**,且**收益不依賴 TC4 的併發度** | **部分實測**(C1 bench_03 是本機 ZMQ 模型,服務時間 8 ms 取自 probe_11 實測)。注意 `_DIGEST` 查核找到的更便宜第三條路:票號互斥鎖保留 `acquire/release` 介面(**必須**保留,因為 wrapper 的 `Pong()` 直接取同一把 `api.lock`) |
| 2-6 | 1K bar 整併快取 + 新增 `read_bars_arrays` 姊妹 API(**`read_bars` 一個字不動**) | 全量 14.162 → **0.195 s(72.6x,stdlib `array.array`)**;單檔隨機讀 686 → 19.4 µs(35.4x);記憶體 1,666 → 173.6 MB | **實測支持**(T3)。**前提是消費端願意改吃 array,不改則收益退回 1.87x 上限**(Amdahl) |

### Tier 3 — 正確性 / 量化基建(不在延遲軸上,但擋住「量化等級」這個目標)

| # | 動作 | 依據 | 標籤 |
|---|---|---|---|
| 3-1 | 本機時鐘:`W32Time` 實測 **Stopped / Manual**(Win11 Home 預設是 Automatic (Trigger Start)),即**無持續 NTP 校時**;09-11 有 4 則 vol_burst 的 tick 時刻 = `13:30:00` 穿過 end-exclusive 的盤中閘 = 本機鐘落後 | 所有 cooldown / 窗 / late 判定 / 盤中閘 / Discord 節流都走這顆鐘,tick 時刻走交易所鐘,**兩把尺的偏差沒有上界也沒有監測** | **實測支持**(V3)。**三份功能報告全部漏收**(S8-02 評 high,被丟掉) |
| 3-2 | 訊號 0c:未命中事件落族群快照(73/205 = 36%) | 唯一符合「每過一天就永久少一天」的一條(自選群組是覆寫式落檔,只有一份 09-08 backup) | **實測支持**(V3,205 / 132 / 73 逐字重現) |
| 3-3 | 回流鏈:消除成交觸發查詢與 60 s stale 輪詢的碰撞 + 固定 1 s 退避改短(**不是三段並行**) | 1019 零次時庫存段 p50 只有 1,022 ms;預估 p90 3,027 → ~1,250 ms(−59%) | **實測支持**(V2,310 筆 1019 對齊分析) |
| 3-4 | 回流鏈量測器去污染 + 判準改「盤中 + 單調 + 庫存段 ≥500 ms 子集的 p90」 | 否則最大改造標的的驗收不可信,且可被開機次數操縱 | **實測支持**(V2) |
| 3-5 | 訊號報告 §0 的 −2,822 改成同口徑 +4,003;影子期起算日改 09-07(同步改 CLAUDE.md) | 現況會讓人得出「線上政策層賠錢、與研究反號」而提前砍掉政策 P | **實測支持**(V3) |
| 3-6 | 下單 C1 改成**辨識**而非修:掛 `OnSolaceReplyConnection/Disconnect`(dispid 9/10)各一行 log;另加不依賴任何 SKCOM 事件的保底 watchdog(`_handle_reply` 每則留痕 → 「最後一則回報距今 N 秒」) | 原 Step 1a 是 no-op,會消耗一次「修好了」的信心 | **實測支持**(V2 讀 typelib + sink + advise) |
| 3-7 | Q1 回測↔實盤 parity gate(同一天 jsonl vs 1K 各跑一次,事件集合對稱差 ≤ 白名單) | 全掃唯一的 critical | **未量 —— 四輪零測量** |

### 明確不要做(本輪實測否決)

EnergySub 降採樣到 170 ‖ per-file parquet ‖ 線上 duckdb(單點查詢比 `json.loads` **慢 8.5x**)‖ `ORJSONResponse` / `JSONResponse`(慢 1.4–3.6x,而且**內容逐字相同、零訊號**)‖ numpy 用在 `stock_state`(系統級 52x 倒退)/ `bars.aggregate_period`(1.12x 慢)/ `overlay.compute_ma`(含 array 建構 **80x 慢**)/ `market_breadth`(0.79x)‖ 即時路徑的 numpy tick 表(等於把 `market.py` 的規則抄第三份,已有兩份 parity 契約)‖ zustand / jotai / signals ‖ `useDeferredValue`(真實節奏下 commit 率 195 → **292**)‖ `startTransition`(零效果)‖ microtask / `setTimeout(0)` 合批(機制上不可能有效)‖ React Compiler(**未先搬牆鐘計算前**)‖ free-threading ‖ `zmq.asyncio`(Proactor 上直接 RuntimeError;換 Selector 跑起來也輸給批次化的執行緒版)‖ 多開 REQ lane / 歷史專用 session ‖ `bAsyncOrder=1` 優先 ‖ 下單 Step 1a「修 OnConnect 綁定」‖ `capital/models.py` 改 msgspec.Struct(**零效能收益**且炸掉 `dataclasses.fields` 反射的 parity 測試)‖ 為 signals/audit jsonl 單獨引入 orjson(只省 25–37 ms)。

---

## §4 完整性批判

### 4.1 四輪之後,仍然沒有任何實測支撐的核心宣稱

1. **TC4 真實推播率**(尤其純簿更新的頻率)。綜整 §0 自己點名它是「十幾條 finding 的共同分母」,四輪過去仍是 0。C1 只量到週日閒置(45 s 內 PUB 4 則)。**而 T4 剛剛量出現況設計在 ~14k msg/s 就開始掉封包(送 426,786 / 收 81,816)—— 我們不知道離那個點多遠。** 更糟的是那種掉包是 ZMQ SUB HWM 的靜默丟棄,不是 `dropped_foreign_ticks` 那種有記帳的。
2. **前端實際 render 率與主執行緒占用**。同上,綜整 §0 點名的第二個共同分母。唯一的 prod trace 是 09-03 的 80 檔、93 秒,而 T5 的 50 卡合成牆最壞是 56.83 ms/拍(= 57% 主執行緒),兩者差 2 倍以上且口徑不同(整條主執行緒 vs React 層 vs 該層渲染)。**「圖牆在盤中到底佔多少」仍然沒有答案。**
3. **端到端延遲(交易所 tick → 螢幕像素)**。全部報告都是分段量測加總,沒有任何一段是端到端的。閃電梯那個「最壞 ≥60 ms」是組合出來的,而它是唯一會直接造成交易損失的量。
4. **prod 冷 overlay 端到端**(150 檔進群組)。C1 的 5.8 s 是外推;`bench_04` 因為 prod 已跑兩天、overlay cache 全熱而量不到冷取。
5. **前端 hover / 同步十字線成本**。T5 明講「這可能才是圖牆最大的那一塊」:`syncHover` 預設開,卡片繪圖區 170px 對 271 分鐘 = 0.63 px/分鐘,「只在分鐘變化時回報」的節流近乎 no-op,每次 mousemove 都可能打穿 50 張卡的 memo,而 mousemove 是 60–144 Hz、**比 10 Hz 的報價還密**。四輪零量測。
6. **repo 真實 App 一次重繪多貴**。T6 的 40 µs 是合成牆(150 張卡)的下界,repo 的 App 還掛著 RightRail / QuoteTable / IndexBar / MetricsBar / OrderPanel + 六條 TanStack Query。「狀態外移」的真收益完全取決於這個數字。
7. **Q1 回測與實盤是兩套實作**。全掃唯一的 critical,四輪(28 + 16 + 10 區)**零測量、零 parity fixture**。四份成本模型、兩邊「折數」慣例相反且數值不一致的問題,到現在還是只有 grep 證據。
8. **ASGI / uvicorn `send` 那一層的開銷**。T1 的 WS 數字只是純序列化;若那層本身要 20 µs/則,把序列化從 54 µs 壓到 6 µs 的端到端收益會被稀釋一大半。
9. **winloop 在專案 3566 條 pytest 下的綠燈**、五條 TC4 真連線、關機 lane 並行退訂(`run_grace_secs() = 83 s` 是拿 Proactor 量的)。
10. **`SUBQUOTE REALTIME` / `UNSUBQUOTE` 落在 TC4 的輕路徑還是重路徑**。C1 刻意不送(refcount 安全),所以 rollover 全量 UNSUB+SUB(~300 發)的成本估計沒有任何基礎。
11. **現況 wire 上會不會出現 NaN / Infinity**。stdlib `json.dumps(nan)` 吐非法 JSON,瀏覽器 `JSON.parse` 會 throw,`ws-reconnect.ts:215` 的 catch 只 warn → **整則訊息靜默丟棄**。capital 的四個 float 欄由群益回報字串轉、除以 0 的算式散在 route 外。未逐點查。
12. **`gc.freeze()`**。T4 指認它是「唯一可能讓 accum/GC 那組結論翻盤」的零相依修法,而且可能吃掉那 25.5 ms 的 gen2 停頓 —— **完全未量**。
13. **Chrome 側的 GC**。T6 在 Node 量到 0 筆 gc entry,Chrome 側一次都沒量。immutable accum 每筆配置約 671 個物件、200 tick/s = 134k 配置/s,對 young-gen scavenge 的影響不明。

### 4.2 哪些 modality 從來沒跑過

| Modality | 狀態 |
|---|---|
| **盤中 prod profiling**(py-spy attach 到跑著的 process) | 四輪零執行。綜整 §3 唯一全票通過的工具,一次都沒用過 |
| **負載 / 壓力測試**(合成 TC4 推播灌真 prod server) | 零。T4 的飽和測試是自建 PUB/SUB,不是打 copycat |
| **端到端延遲量測**(任何一段) | 零 |
| **長跑 / 記憶體洩漏**(24h) | 零。T5 只量到 V8 heap,Blink C++ 側(18,552 個 SVG 元素的 RenderObject / ComputedStyle)與 GPU texture 都未計 |
| **失效注入** | 本輪零。(08-28 有一次 WS 韌性真環境驗證,不在這四輪內) |
| **多分頁 N>1 的實機驗證** | 零。所有 WS 的 N 倍收益(最高 97x)都是合成 |
| **冷 cache / 冷開機** | 零。T3 全 warm(244.8 MB 第二次起全在記憶體),而冷讀正是整併格式贏更多的情境 |
| **DPR=2 / 高解析螢幕** | 零。canvas 的 raster 隨 DPR 平方成長;T5 推估不會反轉但沒測 |
| **背景分頁 / 非前景視窗** | 零。**這是 rAF 合批的潛在 blocker**:Chrome 在背景分頁會停掉 rAF,而看盤常態是多分頁 / 側放 |
| **盤中(TC4 忙碌)重驗 C1 的每一個數字** | 零。C1 全部在週日閒置態,已備妥 `RUNME_intraday_recheck.py` |
| **真實 tick 流** | 零。T3 的 tick 形狀是合成的(雞生蛋:要真實 tick 就得先做持久化) |

### 4.3 沒被任何一輪檢查到的東西

1. **`copycat/server/bars.py` 的 import 鏈把純函式層綁在 ZMQ 傳輸層上**(`bars.py` → `live/stock_source.py` → `live/tc4.py` → `import zmq`)。T3 與 T2 各自被迫先裝 pyzmq 才能 benchmark 一支純函式。這不是效能問題,但它讓任何想單獨測試 / 重用 bars 純函式的人都被迫拖進整條 TC4 相依 —— 而「可獨立測試的純函式層」正是量化系統的基本要求。
2. **`loop 上還有幾處同步檔案寫**,三輪都只抓到一半:`screen_engine.py:445` 與 `stock_watchlist.py:172`(經 `watchlist_service._save_locked`,在 async 方法內同步呼叫)各 0.52 ms(T3);`capital/client.py:396` 的 `_on_late_result` **裸呼叫 `self._audit(record)` 未經 `to_thread`**,而同檔另外三個審計寫入點都刻意走 `to_thread`(V2)。兩邊都沒進任何失效模式表。
3. **`asyncio.run` 在 lifespan 之後 join 預設 executor 最多 300 秒**(`asyncio.constants.THREAD_JOIN_TIMEOUT = 300`,V2 實測),完全不在 `run_grace_secs() = 83 s` 的預算裡,`tests/server/test_shutdown_budget.py` 的不等式也沒這一項。而預設池現在同住 TC4 ZMQ REQ(10 s)與 FinMind EOD(60 s)。**這是今天就存在的洞**,而且它反轉了綜整 Layer 2 對「拆具名 executor 要付關機預算代價」的判斷 —— 拆出去是**降低**風險。
4. **回填 worker 的「共回填 0 列」與「日檔已滑出視窗、永遠補不到」是同一行字**(V3 在 `logs/server-20260911-0905.log` 實錄)。政策列的 `t1_open`/`t2_open`/`d_close`/`d_high` 是四週對帳的**全部**經濟性資料。
5. **TC4 斷線 / 引擎降級不進 jsonl**:「那天沒訊號」與「那天沒資料」在離線讀者眼裡一模一樣,會被當成「那天沒事件」算進發生率分母。
6. **「量全鏈」與「量分段」會給出相反結論**這件事本身。T1 的 TC4 入站:全鏈 25.78(現況)vs 25.66 µs(orjson)看起來完全沒用,分段量卻是 5.12 → 2.03 µs(2.5x),省的 3.1 µs 被 19.18 µs 的 parse 與噪音吃掉。**四輪的量測方法論裡沒有「兩種都要量」這條規矩。**
7. **`_DIGEST` 查核找到的「第三條路」(票號互斥鎖)在 C1 的重評裡消失了**。C1 把優先權佇列估成 M→L 級(要改 `_req` 所有 caller 的 await 形狀),但查核明確指出可以保留 `acquire(timeout=)/release()` 介面、caller 零改動 —— 而且那個介面**必須**保留,因為 wrapper 的 `KeepAliveHelper → Pong()` 直接取同一把 `api.lock`。**C1 的 effort 估計可能高一級。**

### 4.4 方法論層級的問題(比任何單一數字都重要)

1. **burst benchmark 會給出相反的結論**。T6 的 `useDeferredValue`:飽和 burst 下 card 渲染 1000→150、actual 86.4→39.3 ms(看起來 ×2.2 大勝);真實 200 則/s 下 commit/s 195→292、React 忙 1.84%→2.21%(×0.67 變差)。**任何拿 burst 推薦節流/延後類 API 的結論都要重驗。**
2. **量測工具本身是最大的污染源**。T6:`<Profiler>` 在一般 prod build 是 no-op(commits/actualDuration 全回 0,看起來像「React 完全沒重繪」);alias 到 `react-dom/profiling` 之後 wall time 灌水 2.3 倍。T5:uPlot 把重繪延到 rAF,`performance.now()` 包 `setData` 只量到 0.9 ms(看起來比 canvas 快 7 倍),CDP trace 一照是 7.71 ms。
3. **倍數大、絕對值小**這個陷阱貫穿全場。accum 改 mutable 119–300x,值 0.28 個百分點;tick 表向量化孤立看 25.2x,套回整支 ≈ 0。**而反過來也有:0-2 的 timer 只有「兩行」,但它動的是所有 timer 驅動步驟的抖動地板。**
4. **「n 夠不夠大」常常是問錯了問題**。T2 的 breadth:n 掃到 20,000 numpy 仍平手甚至更慢,因為成本結構是 252,000 次 `_to_number` + 504,000 次 `isinstance`,**全部是 Python 函式呼叫次數不是算術**。該問的是「這個 n 裡面有多少比例是可向量化的算術」。
5. **單點量測正確 + 外推方式錯誤 = 一個 13 倍的錯誤結論,而且看起來有實測支撐**(T2 對 `corr_state.py` 檔頭的診斷:0.15 ms 沒說謊,錯在外推只乘了腿數、漏掉佔 61% 的 `_paired_returns` 與佔 19% 的 60 次 list comp)。**這比純推估更難被發現。**
6. **驗收判準量不到它宣稱要量的東西**,本輪至少五處:timeBeginPeriod 的「p50 < 1 ms」(前三秒會假 PASS)、回流鏈的 `grep p50`(可被開機次數操縱)、訊號 0e 的「檔案 id 不變」(今天就成立)、Step 3 的「ingress 每則平均 µs 下降」(命中 REALTIME 時 5.90 vs 5.93,分不出改壞還是本來沒收益)、Step 8 的「applyTick micro-benchmark」(沒指定 vp 規模,vp 小的合成資料會得出假綠燈)。
7. **`corr_state.py:5-7` 的設計理由「增量滑動窗的浮點誤差會隨執行時間累積」實測不成立**,而**那句註解會讓下一個人用錯誤的理由拒絕正確的優化**。真正的風險是窗邊界 off-by-one(修正後誤差從 8.27e-4 → 3.858e-15,降 2.1e5 倍),而守門測試如果斷言 r 在容差內(`isclose rel_tol=1e-6`)會讓 8.3e-4 的真錯**靜默通過** —— 要斷言的是 n,不是 r。而 `tests/live/test_corr_state.py:120-132` 只對 60 窗有邊界斷言,**off-by-one 只發生在最長窗**。

---

## §5 給下一步的三句話

1. **先做 Tier 0 的八條**(合計約一天工,零新相依、零契約、全部實測),然後**立刻裝儀器並重量一次** —— 因為 0-2 一裝上去,所有既有的 ms 級量測基準都會變。
2. **Layer 0 仍然是對的,但要加兩項**:除了原本的 loop lag 探針 + ingress 計數,還要加(a) **WS SUB 的丟包計數**(T4 顯示現況設計在 ~14k msg/s 開始靜默掉包,而我們不知道離那裡多遠),(b) **`send_json` / `publish` 的分段計時**(全表最大的一項被留白了三輪)。
3. **效能批與正確性批必須分開,而且正確性批的清單要重寫** —— 本輪新增三條四輪都沒抓到的:本機時鐘零紀律、`asyncio.run` 的 300 秒未預算段、`_on_late_result` 的 loop 上同步審計;同時刪掉六條被誤標為靜默的。
