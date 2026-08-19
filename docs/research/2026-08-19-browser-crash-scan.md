# 2026-08-19 瀏覽器分頁掛掉 — 前後端全面掃描報告

## 症狀與 log

使用者用 vite dev(5173 → 8721)看盤,「用到一半瀏覽器突然掛掉」,重複發生。當時 log:

```
14:11:02 copycat.live.tc4 WARNING TC4 REALTIME 零推播自癒:TC.F.TWF.TXF.HOT 靜默 30s → 重掛(attempt 1, window_variant=1)
INFO: 127.0.0.1:62552 - "WebSocket /ws/txo-pnl" [accepted]
14:11:27 [vite] ws proxy socket error: Error: write ECONNABORTED
```

判讀:`ECONNABORTED` 是 vite ws proxy 往瀏覽器 socket 寫時對端已消失 → **瀏覽器端先死的症狀,不是原因**。
`14:11` 落在日盤收盤(13:45)到夜盤(15:00)的無行情空窗;TXF 自癒是設計內行為(期貨自癒閘不看盤別)。
只有 `/ws/txo-pnl` 一條 accepted(不是整頁 reload 的 8 條齊 accept)→ 崩潰前 25 秒該條 WS 曾單獨重連。

## 掃描方式

Opus workflow:6 維度 finder(前端 WS hook / 前端記憶體與 render / 後端 WS relay / 後端引擎+TC4 /
頁面生命週期+dev 環境 / 訊號+下單側)→ 每個 P0/P1 finding 一位反駁者親讀程式碼 + 真環境量測。
35 agents、776 次 tool use。全程唯讀。

## 結論

- 52 個 findings,29 個 P0/P1 **全部被反駁者降為 P2**;沒有一條能獨立解釋「跑一段時間分頁掛掉」。
- 兩個結構性反證:
  1. 崩潰時刻無行情 → 「tick 太多 / render 風暴」類假說在該時間點不成立。
  2. 記憶體無界成長的常見嫌疑犯逐條查過都有 cap(ticks TAPE_MAX=200、signals cap=200、
     WsBroadcaster 有界佇列、breadth 每分鐘一格、toast TTL);8 支 WS hook cleanup 完整、
     backoff 有 30s cap、JSON.parse 有 try/catch;無 `location.reload()`、無每 tick console.log。
- 真環境量測(14:22 盤後,curl + websockets 20s):`/ws/txo-pnl` 1 msg/s、23.2 KB/s(佔全部 WS
  流量 96%,內容逐字相同);其餘七條合計 ~3 KB/s。前端 JSON.parse 22.6 KB 實測 0.047 ms/次。
- 閒置分頁量測(claude-in-chrome,個股頁):heap 27 MB → 27 MB、DOM 6791 → 6791、console 零錯誤(16 分鐘)。

**因此:程式碼層找不到確定根因,需要瀏覽器端證據**(見「下一步取證」)。

## 值得修但非崩潰根因的 P2(依價值排序)

| # | 位置 | 問題 | 為何值得修 |
|---|---|---|---|
| 1 | `copycat/server/engine.py:295-297` | `_consume` 對外來 tick 也 `_mark_changed()`;`snapshots()` 只 1s 節流不比內容 → `/ws/txo-pnl` 每秒無條件推 22.6 KB 相同全量快照(全天常數 23 KB/s;實測 dropped_foreign_ticks 309 萬 vs 真 TXO tick 2300) | 全站最大單一 WS 流量、純浪費;route 早退時不該標 changed,或 snapshot 內容比對後才推 |
| 2 | `copycat/server/futures_engine.py:426-435` | 每則 REALTIME quote 無節流廣播完整 state(含五檔),八條 WS 中唯一沒節流者;前端 setState 在 App 根 | 盤中 TXF 推播率高;與其他引擎 1s 節流不一致 |
| 3 | `copycat/server/futures_engine.py:312-345` | leaf fallback 補訂後永不退訂;HOT 自癒回魂後同一商品雙流各廣播一次 | 訊息率單品 +100%(整流 +33%);`_leaf_fed.discard` 只是記帳 |
| 4 | 8 支 WS hook + `copycat/server/ws.py:96` | 全無應用層心跳 / 靜默 watchdog;半開連線只靠 uvicorn 20s ping | 違反專案 §7 紀律;分頁凍住 40s 會八條齊掉再齊重連 |
| 5 | `app.py:1629/1663/1686/1700`、`capital_api.py:325/347` | 引擎缺席時先 accept 再 close,前端 onopen 把 backoff 歸零 → 1 Hz 重連 | 引擎缺席時的熱迴圈;改成 accept 前判斷或 close code 區分 |
| 6 | `frontend/src/hooks/useSignalAlerts.ts:30-44` | AudioContext suspended 時 osc.stop 排在凍結的 currentTime → 音訊節點只增不減 | 自動播放政策下的隱性洩漏(需訊號量大時才顯著) |
| 7 | `frontend/src/hooks/useSignalAlerts.ts:97` | 背景分頁每則訊號 `new Notification`,tag 唯一不合併 | 訊號密集時 OS 通知洪水 |
| 8 | `copycat/server/app.py:1285` | `/api/stock/signals/today` async route 同步讀整份 jsonl → 阻塞 event loop,8 條 WS 一起卡 | 訊號檔大時 WS 抖動來源 |
| 9 | `frontend/src/hooks/useStockStream.ts:460` 等 | `ws.onerror = () => ws?.close()` 關的是共用變數當下指到的 socket,遲到的舊事件可能關掉新連線 | 重連震盪 |
| 10 | `LadderView` / `PriceLadder` / `RightRail` 無 memo;`RiverCards` / `MarketPane` 幾何無 useMemo | 與主圖無關的每則 watchlist_quote / 指數推播都重畫整梯與江波圖 | 效能清理;App.tsx:146-150 註解已自承 |
| 11 | `copycat/server/app.py:359` | 期貨自癒閘只看交易日不看盤別,13:45–15:00 / 05:00–08:45 持續 UNSUB/SUB churn | 就是 log 那行的來源;無害但吵 |
| 12 | `copycat/live/tc4.py:886` | 五個 source 各開 wildcard SUB,全市場推播 JSON 解析五次 | 後端 CPU |
| 13 | `frontend/sha-plugin.ts:64-76` | dev middleware `execSync` git 同步阻塞 vite 主行程(同行程代理 8 條 WS),每 60s + 每次聚焦 | 量測後單次數十 ms,非因果但可改 async |

其餘 P2(TRADEDATE-REFETCH-LOOP、RIVER-DELTA-ALLOC、CAPITAL-TIMERS-GLOBAL、FE-8 群組圖牆 2.5 萬 SVG 節點、
WS-TXO-SHARED-EVENT、HEAL-SET-ITERATION、CAP-QUERY-OBSERVER-FANOUT 等)見 workflow 原始輸出。

## 下一步取證(程式碼掃不到的部分)

1. **確認掛掉的形態**:分頁「Aw, Snap!」(附錯誤碼 / Out of Memory)vs 整個 Chrome 消失 vs 分頁凍住不動。
   `chrome://crashes` 看有沒有 renderer crash 紀錄與時間戳。
2. **DevTools 是否開著**:Network 面板會**保留全部 WS frames**;`/ws/txo-pnl` 23 KB/s × 5 小時 ≈ 400 MB
   全存在 DevTools 行程裡,是「開著 devtools 看盤幾小時後瀏覽器掛掉」的經典成因;React DevTools 擴充在
   dev build 下也會持有整棵 fiber tree。請對照:掛掉那次 devtools 是否開著。
3. **分頁記憶體時序**:Chrome 工作管理員(Shift+Esc)盯 5173 分頁的「記憶體佔用」+「JavaScript 記憶體」,
   每 30 分鐘記一次;或在該分頁 console 貼下方 sampler(寫 localStorage,分頁死了資料仍在):
   ```js
   setInterval(()=>{const m=performance.memory;const a=JSON.parse(localStorage.memlog||'[]');
   a.push([Date.now(),Math.round(m.usedJSHeapSize/1048576),document.getElementsByTagName('*').length]);
   localStorage.memlog=JSON.stringify(a.slice(-500));},30000);
   ```
   下次掛掉後在新分頁 `JSON.parse(localStorage.memlog)` 看曲線是緩漲(洩漏)還是平的(非記憶體)。
4. **對照 build 版**:`npm run build` + `npm run preview` 直連(不經 vite dev proxy / HMR / StrictMode
   double-effect)看是否仍掛;若不掛,問題在 dev 環境層而非產品碼。
5. 若確認是 OOM 且 devtools 未開:下一輪用 `take_memory_snapshot` 在盤中每小時抓 heap 比對 retained size 增量。

## 補充事實(user 08-19 回覆)

- 掛掉形態 = **Chrome renderer crash 畫面(Aw, Snap 類)**;當下 DevTools 未開;事後按 F12 開 DevTools
  觸發自動重整後恢復正常。→ 排除「DevTools 保留 WS frames」假說;確定是分頁 renderer 死亡(OOM 或 renderer bug)。
- 取證機制:MCP 分頁常駐 localhost:5173(個股頁),植入 localStorage sampler(每 30s:heap / total /
  DOM 數 / longtask 計數與最大值 / 各 WS 訊息數與 bytes / visibility),session cron 每 30 分鐘觀察一次;
  掛掉時由 Claude 用 DevTools MCP 蒐證。

## 觀察紀錄

| 時間(台北) | heap MB | DOM | longtask 數 / max ms | 備註 |
|---|---|---|---|---|
| 14:15 | 27 | 6791 | – | 基線(sampler 未裝) |
| 14:31 | 27 | 6791 | – | 閒置 16 分鐘無變化 |
| 14:45 | 30 | 6791 | 0 / 0 | sampler 植入 |
| 15:07 | 47–70(GC 鋸齒) | 5426→5507 | 5 / 174 | 分頁 hidden(取樣被節流成 60s);15:00 夜盤開,DOM 6 分鐘 +80 節點,heap 無單向上升 |
| 15:37 | 55–76(鋸齒,基線 47→57) | 6049(+542/30min) | 5 / 174 | 成長來源=hidden TXO 頁報價表列數(夜盤契約逐一有成交才長列,上限=鏈 143 檔),有界;非洩漏跡象 |
| 16:07 | 67–106(谷底爬升:每 10 分鐘 min 30/45/37/43/55/60/55/67) | 6339 | 5 / 174 | **heap 谷底約 +35MB/小時 趨勢**,尚未達回報門檻(30 分鐘 <50MB),但若日盤 tick 量級下成比例放大即為嫌疑;下輪續看谷底是否被 major GC 拉回 |
| 16:37 | 74–117(谷底 67/61/75/74,爬升放緩 ~+8MB/30min) | 6480 | 115 / 375 | 長任務 30 分鐘內 +110 次(max 375ms,可能分頁被切到前景);heap 趨勢仍微升、未達門檻 |
| 17:07 | 89–130(谷底 74/78/81/89,單向 +12MB/30min;2h15m 累積谷底 +59MB) | 6534 | 115 / 375 | 慢速洩漏樣態確立(谷底不被 major GC 拉回);devtools MCP 為獨立 profile 看不到此分頁,heap snapshot 需 user 在 DevTools Memory 手動抓兩份(相隔 30 分)交我比對 |
| 17:37 | 94–152(谷底 86/91/94/99,+10MB/30min 持平) | 6560 | 115 / 375 | 趨勢不變;等 user 的兩份 heapsnapshot |
| 18:07 | 107–162(谷底 99/100/105/107,+8MB/30min) | 6600 | 115 / 375 | 趨勢不變;3h20m 谷底 30→107 |
| 18:37 | (CDP 逾時,無法取樣) | – | – | **MCP 分頁 renderer 凍結**:javascript_tool `Runtime.evaluate` 45s 逾時、截圖回「Cannot access contents」 |

### 18:40 OS 層證據(renderer 凍結當下)

```
PID 10572  --type=renderer  建立時間 14:11:27(= user 回報的 vite ECONNABORTED 時刻,即 F12 重整後新生的 renderer)
  WorkingSet 6,188 MB / Private 15,330 MB / 累積 CPU 15,707 s(4.5 小時內 ≈ 一顆核心 100% 全程)
  10 秒取樣 CPU delta = 10.05 s(此刻仍滿載一核);29 threads
  最忙 thread 24288 = 12,250 s(其餘 926 / 539 / 295 / 290 s)
其他 renderer 全部 <260 MB、CPU <160 s;系統 free 9.7 GB / 31.8 GB(不是系統層 OOM)
```

判讀:
- 同一 renderer 自 14:11:27 起**單一執行緒持續 100% CPU + 記憶體線性膨脹到 15 GB commit**,這就是「跑幾小時後 Aw Snap」的直接成因(renderer 撞 V8/沙盒上限或 GC thrash 後被殺)。
- 取樣分頁(同 site,極可能同 process)的 V8 heap 全程只 30→160 MB、主執行緒長任務僅 115 次 →
  **膨脹的不是這個分頁的 JS heap、燒 CPU 的也不是主執行緒**。嫌疑:user 那個分頁(不同頁面 / 狀態)或
  非 V8 記憶體(Web Audio 節點、ArrayBuffer、canvas/layer 備份、worker)。前端程式碼無 Worker;
  Web Audio 只在 `useSignalAlerts.ts:playBeep`(R4 finding:suspended 時節點永不結束)。
- 需要 user 端確認:Chrome 工作管理員(Shift+Esc)PID 10572 對應哪個分頁、該分頁停在哪一頁;
  對該分頁開 DevTools → Performance 錄 10 秒看哪條 thread 滿載;Memory → heap snapshot。

### 19:07 renderer 10572 死亡;19:09 重載後在新 renderer 16404 立刻重現 → 根因定位

時序與量測(全部實測):
- 19:07 PID 10572 消失;MCP 分頁變錯誤頁(截圖被拒 / localStorage 拒存取)。sampler 最後一筆 18:18:55
  (V8 heap 115 MB)→ 之後主執行緒凍死到被殺;**V8 heap 全程最高 169 MB,與 15 GB 無關**。
- 19:09:43 重載 → 新 renderer 16404 2 分鐘內 CPU 84 s、WS 362 MB,之後每分鐘 +70 MB、CPU ~75% 一核
  (與 10572 的 1.1 MB/s 同速率)。分頁導去靜態頁 `/__build/sha` → CPU 立刻歸 0 → 是 app 頁本身。
  在分頁內配 300 MB 後 16404 跳 +384 MB → 確認 16404 就是 MCP 分頁的 process(user 分頁不在其中)。
- 主執行緒忙碌度:MessageChannel ping-pong 2 秒迭代數 靜態頁 200,033 vs app 頁 68,052 → **主執行緒 ~66%
  忙,但全是 <50 ms 短任務**(所以 Long Task 觀察器看到 0,之前的 P2 判斷被這點誤導)。
- 8 條 WS 實測 10 秒:futures 17.9 msg/s、stock 3.6、txo-pnl 1.2(23 KB/s)、corr/river 1.2 → 不是 IO 風暴。
- **`performance.getEntriesByType('measure').length`:載入 1 分鐘 21,746 → 10 秒後 +6,318(632 筆/秒)
  → 75,179**。名稱 `​LadderView` / `​Btn` / `​SideCells` …,detail =
  `{devtools:{track:"Components ⚛", properties:[["Changed Props",""],["  rows","Referentially unequal but deeply equal objects. Consider memoization."]]}}`。
- `performance.clearMeasures()` 清掉 75,179 筆 → renderer Private 762 → 624 MB(**−138 MB ≈ 1.8 KB/筆;
  × 632 筆/秒 ≈ 1.1 MB/s,與 15 GB / 4.5 h 完全吻合**),之後又開始爬。

## 根因(已確認)

**React 19.2.7 development build 的 Component Performance Track**(`react-dom-client.development.js:4104-4180`):
元件 re-render 且 `alternate.memoizedProps !== props` 時,用 `performance.measure("​"+name, {detail:{devtools:…}})`
(還先跑 `addObjectDiffToProperties` 算 props diff);只有 props 同 identity 才走不留痕的 `console.timeStamp`。
`supportsUserTiming` 在 Chrome 恆 true。Chrome 的 User Timing 條目(mark/measure)**沒有緩衝上限、不在 V8 heap、
永不自動回收** → 每秒數百筆 × 1.8 KB 線性累積,幾小時後 renderer 吃到數 GB → Aw Snap。
同時 props diff 計算讓主執行緒常態 ~66% 忙(短任務)。

放大因子(本 app 特性):每則 WS 訊息(夜盤 ~25/s,日盤更高)都讓 App 根 setState → 五頁全樹 re-render,
且幾乎所有子元件 props 都是新 identity(無 memo / useMemo)→ 每則訊息數十~數百個元件各留一筆 measure。
這正是 workflow 被降為 P2 的 FE-1 / ALL-TABS-MOUNTED / FE-4 / FE-3 等「無記憶體滯留所以非根因」的 findings ——
它們的 V8 推論沒錯,錯在沒算到 Blink 側的 User Timing buffer。

**只影響 `npm run dev`(development build)**;production build(`npm run build`)沒有這段程式。
user 的 14:11 崩潰與 19:07 崩潰都是同一機制。

## 修法(待拍板,建議 /bug 走流程)

1. **立即緩解(dev-only,一行)**:`main.tsx` 在 `import.meta.env.DEV` 下 `setInterval(() => { performance.clearMeasures(); performance.clearMarks(); }, 10_000)`。
   不影響 DevTools Performance 錄製(trace 在發出當下就被擷取)。MCP 分頁已裝同款暫時緩解,由 loop 驗證走平。
2. **看盤日常改跑 production build**(`npm run build` + `vite preview` 或靜態 serve 指向 8721):
   根本上不該整天用 dev server 看盤;也順便拿掉 StrictMode double-render / dev 診斷開銷。
3. 放大因子(R6 memo 邊界 / R2 futures 節流 / FE-1 App 根 setState)仍值得做,但屬效能,不是洩漏本體。
| 19:55 | 67(修後版重載) | 6240 | – | **修後版(observer 閾值 5000)**:measure 條目 2,138(上限內震盪);renderer 16404 私有記憶體 ~150–200MB 走平 25 分鐘、25280(另一分頁)480MB 走平;sampler 重植(含 measures 欄) |
