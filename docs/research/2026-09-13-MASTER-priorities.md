# copycat 高效能量化改造:實測優先序總表

2026-09-13。**這是主文件。** 四輪掃描(28 + 16 + 10 區、99 個 agent、24M tokens)的收斂結果。

前三輪是讀 code + 投票 + 推估;**第四輪是真的把套件裝進拋棄式 venv、拿真實資料、對真 Chrome、對開著的達錢 4 量出來的。** 所以第四輪推翻了很多前三輪的結論 —— 下面每一條都標了「實測支持」或「仍是推估」。

| 文件 | 內容 |
|---|---|
| `2026-09-13-live-view-report.md` | 看盤(已含第四輪修正) |
| `2026-09-13-order-report.md` | 下單(已含第四輪修正) |
| `2026-09-13-signal-report.md` | 訊號(已含第四輪修正) |
| `2026-09-13-architecture-perf-review.md` | 第一輪全域綜整(**部分已過時**,以本文件為準) |
| `2026-09-13-verify-bakeoff/` | 第四輪:3 份複驗 + 6 場實測擂台 + TC4 重評 + 交叉綜整 |
| `2026-09-13-arch-scan/` + `2026-09-13-order-signal-scan/` | 44 份分區長篇(證據與 benchmark 原始數字) |

---

## 0. 第四輪推翻了什麼(先讀這段,免得照舊結論施工)

| 舊結論 | 實測真相 |
|---|---|
| 「一行 `timeBeginPeriod(1)` 把抖動壓到 0.7 ms」 | **單獨無效** —— Windows 11 EcoQoS 約 **3 秒**後收回(退回 12.602 ms)。8 種替代配方全無效。必須配 `SetProcessInformation(ProcessPowerThrottling, IGNORE_TIMER_RESOLUTION)` 才穩在 0.556 ms。**而且原本寫的驗收判準會讓錯誤實作在前三秒回報 PASS。** |
| 「TC4 無上限 → 多開 REQ lane 並行取數」 | **收益為 0。** 對真 TC4 實測:6 發目錄查詢分 1..6 條 lane,牆鐘恆約 19 s(最佳 1.04x)。8 條並發 LOGIN 全過 —— 新事實講的是**併發許可**不是**併發吞吐**。TC4 桌面 app 本身是序列化服務端。**方案刪除。** |
| 「`api.lock` 序列化是第一個要解的」 | **排序錯。** 真正的第一刀是 `_POLL_BACKOFF_START = 0.15` —— 一次冷日 K 的 153 ms 裡**有 150.5 ms 是我們自己的 `time.sleep`**,TC4 真正備妥只要 15–40 ms。而且「`api.lock` 飽和」的印象不成立:overlay sweep 期間佔用率只有 **~6%**。 |
| 「後端無事可做,最大收益是刪掉重複工作、零新相依」 | **反轉。** 延遲表把 starlette `send_json` 留白標「未量」,而它是全表最大單項(300 筆打包 **375.7 µs × 每個分頁**)。WS 換 orjson **N=1 已 8.7x、N=8 77.4x**。 |
| 「顯式 `ORJSONResponse` 反而更慢,所以 REST 不必換」 | **前半對、後半錯。** 根因是指定 `response_class` 會讓 `use_dump_json` 變 False、多跑一次 `field.serialize`。但 **`return Response(orjson.dumps(payload))` 會觸發 `routing.py:695` 的 isinstance 短路,整條 response chain 不執行** —— 個股 snapshot **9.31 → 1.46 ms(6.4x)**。 |
| 「numpy / polars 能加速數值」 | **要分開講。** CorrState:**純 Python 增量 208x、numpy 只有 10x**。1K bar:**stdlib `array.array` 追平 numpy**。breadth 換 numpy 是 **0.79x 倒退**。**序列化該換工具(Rust encoder 真快一個量級),數值聚合該換演算法(增量 > 向量化重算)。整批表態一定做錯。** |
| 「`slots=True` 一行拿走 36% 的 full GC 停頓」 | **買不到。** 擬真自動 GC:dataclass 最壞 **25.53 ms**、加 slots **24.63 ms**(噪音內)—— 兩者都 GC-tracked,gen2 掃的是被追蹤物件數不是 layout。slots 買到的是記憶體 −30% 與 full collect −38%。**而且「full GC 71–108 ms」是 `gc.collect()` 的數字,盤中真正上界是 25.5 ms。** |
| 「EnergySub 先做降採樣」 | **撤回。** 真 Chrome CDP:降採樣到 170 根只有 **1.44x 且資料失真**;單一 `<path>` **3.12x 且逐像素相同**;canvas **6.58x**。成本在元素個數的線性項上,271→170 只是沿線滑一格。 |
| repo N047 註解「真瀏覽器快一個量級」 | **高估 3 倍**(jsdom 13.09 / Chrome 4.0 = 3.3x)。而「不值得改」在單檔頁對(271 格 1.52 ms/拍)、**在圖牆錯**(50 卡 44.99 ms/拍)。 |
| 「zustand 全票否決,因為問題是 memo 邊界」 | **結論對、理由錯。** 真 Chrome prod build 跑六種架構,commit 數與 card 渲染數**完全相同(1000/1000)** —— memo 邊界現況已經正確,這些套件連「修 memo 邊界」都沒得做。收益全來自「App 不再重繪」,而那件事用 `useSyncExternalStore` 或既有的 `tick-stream` EventTarget **零新依賴**就拿得到(差 3% 在雜訊內)。 |
| 「ProcessPool 8–12x(可能 4–8x)」 | **熱池 4.45x、含 spawn 3.10x。** 而且兩個會做反的陷阱:天真 `ex.map` 是 **0.03x(慢 30 倍)**;用 initargs 時 **16 worker(1.60x)比 4 worker(2.14x)還慢**。 |
| 下單「修 OnConnect 綁定」 | **錯的診斷,照做是 no-op。** 綁定每一層都正確。根因未知,頭號候選是 `OnSolaceReplyConnection/Disconnect`(dispid 9/10)完全沒實作。 |
| 下單「`bAsyncOrder=1` 是最大標的」 | **高估一個量級。** 7.6% 是區間上界,可證下界只有 **0.56%**。真正在燒的是 **`SK_ERROR_QUERY_IN_PROCESSING`(1019):310 筆躺了 22 天,每次 +1,060 ms,庫存段 ≥2 s 的 92% 命中**。 |
| 下單「回流鏈 p50 1,940 ms,可直接 grep 驗收」 | **不可信。** `client.py:421` 每收一筆成交就覆寫 `_fill_seen_at`,污染樣本 79% 在開機 2 分鐘內且方向是把數字**拉小** —— 多重啟幾次 p50 就會下降,程式可以一行都沒改。乾淨子集 p90 是 **3,027 ms**。 |
| 訊號「線上 −2,822 vs 研究 +5,784,對不上」 | **單位錯配。** −2,822 是元/張、+5,784 是每筆 50 萬名目。同一批 23 筆換算同口徑是 **+4,003 —— 同號同量級**。 |
| 訊號「每過一天樣本永久不可還原」 | **只對六分之一成立。** 規則檔 mtime 08-15(零編輯)、種子 params 每次開機印在 log、開機斷點可重建(V3 實際重建出全部 8 批次 3 次重啟)。**真正每天在流失的只有「未命中事件的族群快照」(36%)。** |
| 看盤「16 條裡 10 條靜默」 | **高估一倍,真正零訊號約 4–5 條。** #1/#2 有 traceback + WARNING 洪水、#4 有 60 s 節流 WARNING、#5/#7/#8/#9 有跨語言 parity 測試(改任一邊 pytest 就紅)。 |

---

## 1. 依 ROI 排序的行動清單

### Tier 0 — 改一行到數行,零新相依,零契約風險

| # | 動作 | 實測收益 | 依據 |
|---|---|---|---|
| **0-1** | `_POLL_BACKOFF_START` `0.15 → 0.02`(倍增與 1.0 s 上限不動) | 冷歷史取數 **153 → 22–43 ms(3.5x)**;150 檔進群組冷 overlay **5.8 → 2.6 s** | 實測(對真 TC4 逐發拆解) |
| **0-2** | `_eval_volume` 300 秒窗改 running sum | **1.40–293 µs → 0.100 µs 恆定**(實況 **171x**、爆量 **909x**、極端 **2,931x**) | 實測(10 萬次隨機驗證 0 次不符) |
| **0-3** | EcoQoS 豁免 + `timeBeginPeriod(1)`(**兩行,缺一不可,都要檢查回傳值**) | timer drift p50 **12.47 → 0.556 ms(22.4x)**、p99 14.2 → 1.98 ms | 實測 |
| **0-4** | CorrState 改**純 Python 增量 running sums** + `has_clients` 閘 | 每秒總成本 **9.153 → 0.044 ms(208x)** | 實測 |
| **0-5** | `audit.py:33` 的 per-append `mkdir` 搬到啟動時 | 211.5 → 139.5 µs(佔 34%,而且在鎖內);送單路徑付兩次 = 省 0.14 ms | 實測 |
| **0-6** | `capital_api.py` 三處 `dataclasses.asdict` 改 dict comprehension | 單列 **8.2–9.3x**、route n=400 **819 → 91 µs**(`asdict` 比 `orjson.dumps` 還貴 11.7 倍) | 實測 |
| **0-7** | `sys.setswitchinterval(0.001)` | 4 條 CPU 執行緒在跑時 loop p50 **15.53 → 3.54 ms**、p99 **95.09 → 21.59 ms** | 實測(代價 −8.7% 飽和吞吐) |
| **0-8** | `_distribute` 補 `enabled` 檢查 | 停用規則的純死工歸零 | 機制確認 |
| **0-9** | `evaluate_book` latch 旗標短路 | 機制確認、倍數未量 | 推估 |

**0-2 是全報告 CP 值最高的一條**(成本 S、最高 2,931x、數值零風險)。唯一風險是 `reset_day` / `drop_code` / `apply_backfill` 三處清空點漏掉一個。

**0-3 的判準必須是「持續量 60 秒、p50 全程 < 1 ms」** —— 量 3 秒會 PASS 一個壞掉的實作。收益要誠實拆:盤外約 12 ms、盤中密集推播時只剩約 2 ms,且**下單路徑不在受益範圍**(`queue.get(timeout=)` 一族不受影響)。

**0-4 的守門測試必須斷言 `n{w}` 完全相等**,不是 r 在容差內 —— `isclose rel_tol=1e-6` 會讓 8.3e-4 的窗邊界 off-by-one 靜默通過。

### Tier 1 — 要新相依(orjson),但收益一個量級

| # | 動作 | 實測收益 | 前置 |
|---|---|---|---|
| **1-1** | `river_state.py:162` 的 int 鍵改 `str(m)` | 本身零收益,**但不做則 1-2 一上線江波圖第一則 snapshot 直接 TypeError** | — |
| **1-2** | `WsBroadcaster.publish` 入口 `orjson.dumps` 編一次 + `send_text` | ticks 40 items **N=1 8.7x / N=4 36.1x / N=8 77.4x**;quote N=1 7.5x → N=8 40.8x | 1-1 |
| **1-3** | 三支大 payload endpoint 改 `return Response(orjson.dumps(payload))` | 個股 snapshot **9.31 → 1.46 ms(6.4x)**、group-state 150 檔 **22.39 → 6.24 ms** | — |

**關鍵判讀:1-2 在 N=1 就已經贏 7.5–9.1x**,所以「現在只有 1–2 個分頁所以不急」是錯的推論。五份真實 payload 實測 stdlib / orjson 輸出 **byte-for-byte 相同**。

**1-3 的理由是 tail latency 不是吞吐**(HTTP 頻率低,系統級每秒只省約 0.5 ms)—— 省的是 **event-loop stall,期間 8 條 WS 全停推**。

**保留 text frame,不要改 `send_bytes`**(前端解析端不必動)。成本在測試面(8 條 WS 的 fake 要補 `send_text`)。

### Tier 1.5 — 正確性優先於效能(真錢)

| # | 動作 | 為什麼 |
|---|---|---|
| **1.5-1** | `QueryClient({defaultOptions:{mutations:{networkMode:"always"}}})` | 放行需 online **且** focus,由較晚者觸發 → 曝險窗**沒有時間上界**(真錢限價單可能在幾小時後、完全不同的價位送出)。而 `onlineManager` 讀的是 `navigator.onLine`,與本系統唯一的 loopback API 路徑**完全不相干** |
| **1.5-2** | 下單 C1 改成「**辨識而非修**」 | 掛 dispid 9/10 各一行 log + **不依賴任何 SKCOM 事件的保底 watchdog**。原 Step 1a 是 no-op |
| **1.5-3** | 訊號 0c:未命中事件落族群快照(73/205 = **36%**) | 唯一真正符合「每過一天就永久少一天」的一條;也是唯一能讓門檻敏感度分析從「結構上做不到」變「做得到」的一條 |
| **1.5-4** | **本機時鐘校時** | W32Time 實測 **Stopped / Manual** = 無持續 NTP。09-11 有 4 則 tick 時刻 = 13:30:00 穿過 end-exclusive 盤中閘 = 本機鐘落後。**兩把尺的偏差沒有上界也沒有監測** —— 這條擋住「量化等級」 |

**1.5-1 的坑**:那一行**絕不能放進 `queries` 層** —— `queryClient.js:271-273` 會靜默關掉全站輪詢 hook 的 `refetchOnReconnect`。判準要補 focus 那一半:斷網 → 送單失敗 → 恢復 → 切分頁再切回 → **不得有單送出**。

### Tier 2 — 結構性,effort M–L

| # | 動作 | 實測收益 |
|---|---|---|
| **2-1** | tick 持久化(64 KB buffered append,盤後轉 parquet) | 寫入 p50 **0.1–0.5 µs**、最壞單筆 0.11 ms、**702,860 次寫入中 >1 ms 有 0 次**;日終 60.3 MB(jsonl)/ **7.8 MB(parquet)**;讀回 **5.0 ms vs 1,045.8 ms(209x)** |
| **2-2** | 執行緒→loop 交接改 deque + 「空 deque 才排一次 drain」旗標 | 5 producer @2000 則/s 的 e2e p99 **10,671 → 86 µs(124x)**;真 ZMQ SUB 飽和時現況**會掉封包**(送 426,786 / 收 81,816)而批次版不掉、吞吐 3.48x |
| **2-3** | EnergySub 量柱 + VP 長條合併單一 `<path>` | 圖牆 50 卡每拍 **56.83 → 26.08 ms(2.18x)**;DOM **18,645 → 3,009 節點**;逐像素相同、零新相依 |
| **2-4** | `overlay_sem` 後面的等待隊伍換優先權序(保留在飛上限) | 互動 p95 **332 → 17 ms(19.5x)**,而且**收益不依賴 TC4 的併發度** —— 現在知道 TC4 不能並行,所以這是唯一的賭注 |
| **2-5** | 離線回測 `ProcessPoolExecutor` + initializer(**只傳檔案路徑,child 各自 load**) | 熱池 **4.45x**、含 spawn **3.10x**。`ThreadPool(8)` 是 0.99x(GIL 下完全沒用) |
| **2-6** | 回流鏈:消除成交觸發查詢與 60 s stale 輪詢的碰撞 + 固定 1 s 退避改短 | 1019 零次時庫存段 p50 只有 1,022 ms;預估 p90 **3,027 → ~1,250 ms(−59%)** |

**2-1 的三個地雷**:絕不逐筆 `fsync`(p99 2,050 µs / 全日 345 s)、`ParquetWriter.write_table` 絕不在 loop 上(單次最壞 200 ms)、每筆 commit 的 sqlite 慢 7–29x。

**2-2 必須做旗標版不要做固定週期 ticker**(1 ms ticker 的 e2e p50 是 1,241 µs,差 30 倍)。碰 CLAUDE.md §4 的 seq 契約;下單回報那兩處(`client.py:826/856`)建議先不動。

**2-5 切錯法會比單執行緒慢 30 倍。規劃時不要按 8x 排期。**

**2-6 的驗收判準必須改成**「盤中 09:00–13:30、累積值單調遞增、庫存段 ≥500 ms 子集的 p90」並追 `grep -c 1019` —— 否則最大改造標的的驗收可被開機次數操縱。

### Tier 3 — 需要你拍板

| # | 決策 | 取捨 |
|---|---|---|
| **3-1** | 群組卡片變體改 **canvas 2D**(單檔頁維持 SVG) | 在 path 化之上再 **2.31x**、對現況 **5.04x**;DOM 209 節點(90x)。**但 `CardIntradayChart` 的 doc 明文反對「同一檔在卡片與單檔頁是兩張不一樣的圖」** |
| **3-2** | 1K bar 整併快取 + 新增 `read_bars_arrays` 姊妹 API | 全量 **14.162 → 0.195 s(72.6x**,stdlib `array.array`,numpy 甚至略慢);單檔隨機讀 **35.4x**;記憶體 1,666 → 173.6 MB。**前提是 9 處 caller 願意改吃 array**;不改則 Amdahl 退回 1.87x 上限 |
| **3-3** | 掃單簇母體:同秒群 vs 同毫秒群 | 決定四週後那場對帳能不能成立。同時要修 `tc4-market-facts` skill 那條錯誤條目 |
| **3-4** | **Q1:回測與實盤 parity gate** | **四輪唯一的 critical,而且四輪零測量、零 parity fixture。** 四份成本模型、兩邊「折數」慣例相反且數值不一致,誰改誰都不會有錯誤訊號。**不該混進效能批** |

---

## 2. 明確不要做

| 項目 | 實測理由 |
|---|---|
| 多開 TC4 REQ lane | 1..6 條 lane 牆鐘恆約 19 s(1.04x) |
| numpy 用在 CorrState / breadth / 1K bar | 208x vs 10x;0.79x 倒退;array.array 追平 |
| numpy / polars 用在即時狀態機 | `_apply` 1.96 µs/tick 已是增量式 |
| polars / DuckDB 加速回測搜索 | 已是 Python int bitmask 走 C 層 bitwise |
| zustand / jotai / valtio / signals | commit 數與現況完全相同;收益用 uSES 或既有 EventTarget 零依賴就拿得到 |
| Web Worker | 問題不在計算量 |
| `uvloop` | Windows 不支援 |
| 顯式 `ORJSONResponse` | 讓 `use_dump_json` 變 False,**2x 退步且完全無訊號** |
| EnergySub 降採樣 | 1.44x 且資料失真 |
| `slots=True` 為了 GC 停頓 | 25.53 → 24.63 ms 在噪音內 |
| 手動指定 `--loop` / `--http` / `--ws` | 已是 Windows 上最好組合 |
| `uvicorn --reload` | 每次存檔重建五條 TC4 session,付 60 s 零推播 |
| `market.py` 換浮點 | **影響下單價格正確性**,且有跨語言 parity 契約 |
| `quantiles.py` / `bollinger.ts` 換算法 | 靜默改掉已發布報告 / 災難性抵銷 |
| 送單路徑的 Python 微優化 | 全部 1.14 ms / 89.6 ms |
| React Compiler(未驗證前) | 會凍住刻意不進 memo 的牆鐘計算 —— **真錢畫面正確性風險** |

---

## 3. 四輪之後仍然沒有答案的(下一輪該補)

1. **TC4 真實推播率**(尤其純簿更新)—— 十幾條結論的共同分母,四輪零進展。而 T4 剛量出現況設計在 **~14k msg/s 就開始掉封包**(ZMQ SUB HWM 的**靜默**丟棄,不是有記帳的 `dropped_foreign_ticks`),我們不知道離那個點多遠。
2. **前端實際 render 率與主執行緒佔用** —— 三個口徑(T5 的 56.83 ms/拍、T6 的 2.38%、trace 的 24.9%)不可互換。
3. **端到端延遲(交易所 tick → 螢幕像素)** —— 完全沒量過任何一段,而它是唯一會直接造成交易損失的量。
4. **前端 hover / 同步十字線** —— T5 明講「這可能才是圖牆最大的那一塊」:`syncHover` 預設開、節流近乎 no-op、mousemove 是 60–144 Hz(比 10 Hz 的報價還密)。四輪零量測。
5. **`gc.freeze()`** —— 唯一可能讓 GC 那組結論翻盤的零相依修法,完全未量。
6. **`py-spy` 盤中 prod profiling** —— 全票通過的唯一工具,四輪零使用。
7. **盤中重驗 C1 的每一個數字** —— 全部在週日閒置態量的。已備妥 `RUNME_intraday_recheck.py` 與三條判準。
8. **winloop 的三塊硬驗證** —— 3566 條 pytest、五條 TC4 真連線、關機 lane。本輪不能碰專案 `.venv` 所以一條都沒跑。
9. **現況 wire 上會不會出現 NaN / Infinity** —— stdlib 吐非法 JSON、瀏覽器 `JSON.parse` throw、`ws-reconnect.ts:215` 的 catch 只 warn → **整則訊息靜默丟棄**。換 orjson 反而會修掉它(吐 null),但屬行為改動。
10. **兩個從來沒被抓到的結構問題**:(a) `bars.py` 的 import 鏈把純函式層綁在 ZMQ 傳輸層上(T2 與 T3 各自被迫先裝 pyzmq 才能 benchmark 一支純函式);(b) `asyncio.run` 在 lifespan 之後 join 預設 executor **最多 300 秒**(`THREAD_JOIN_TIMEOUT`),完全不在 `run_grace_secs()=83 s` 預算裡。

### 方法論層級的三條空白(影響所有未來量測)

- 沒有「**全鏈與分段兩種都要量**」—— T1 的 TC4 入站全鏈 25.78 vs 25.66 µs 看起來沒用,分段卻是 2.5x。
- 沒有「**burst 與定速兩種節奏都要量**」—— T6 的 `useDeferredValue` 在兩種節奏下結論**相反**。
- 沒有「**量測工具本身的污染要先扣掉**」—— Profiler 在 prod build 是 no-op、alias 後 wall 灌水 2.3 倍;uPlot 把重繪延到 rAF,`performance.now()` 量到 0.9 ms 而 CDP 是 7.71 ms。
