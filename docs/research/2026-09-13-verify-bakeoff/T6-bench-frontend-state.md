# T6-bench-frontend-state —— 擂台:前端狀態與 render(實測報告)

日期 2026-09-13。**repo 零改動**(唯讀)、**專案 .venv 零接觸**(本區塊只用 npm,不碰 Python)。
所有數字都標明是「實測」或「推估」;查不到的標「未量」。

---

## 0. Setup(可重現)

| 項目 | 值 |
|---|---|
| 拋棄式專案 | `C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\verify-bakeoff\T6\` |
| Node / npm | v24.13.0 / 11.6.2(實測) |
| 瀏覽器 | Chrome 152.0.0.0(Windows NT 10.0 x64),chrome-devtools MCP 驅動 |
| React / ReactDOM | **19.3.0** |
| Vite / plugin-react | 6.4.3 / 4.7.0 |
| 對決套件 | zustand 5.0.15 / jotai 3.0.0 / @preact/signals-react 3.12.0 / babel-plugin-react-compiler **1.0.0** |
| build | `vite build`(production、esbuild minify);Profiler 量測需 `resolve.alias: {"react-dom/client": "react-dom/profiling"}` |
| 服務 | `vite preview --port 5199`(compiler 關)/ `--port 5200 --outDir dist-compiler`(compiler 開) |

**repo 未安裝的東西一個都沒動**:copycat `frontend/node_modules` 全程未觸及,T6 自帶 node_modules。

### 腳本與原始輸出

| 檔 | 內容 |
|---|---|
| `T6/bench-accum.mjs` → `T6/out-accum.txt` | 擂台 1 accum 五種模式 × 三種 vp 檔位數 |
| `T6/bench-accum-gc.mjs` → `T6/out-accum-gc.txt` | 擂台 1b 配置量 / 長尾(60000 筆) |
| `T6/compiler-walltime.mjs` → `T6/out-compiler-walltime.txt` | 擂台 3b **編譯期**:六個 case 的 compiler 產物全文 + 機械判定 |
| `T6/src/main.jsx`、`T6/src/shared.js` | 瀏覽器擂台(2 / 3 / 4 / 5)全部程式碼 |
| `T6/out-dist-chart.json` | 擂台 2 狀態分發(逐檔更新) |
| `T6/out-broadcast-chart.json` | 擂台 2b 廣播(150 檔同時) |
| `T6/out-batching.json` | 擂台 4 批次化 + automatic batching 探針 |
| `T6/out-paced.json` / `out-paced2.json` / `out-paced2.txt` | 擂台 4c **定速**投遞(真實節奏) |
| `T6/out-react19.json` | 擂台 3 useDeferredValue / startTransition + freeze(compiler 關) |
| `T6/out-compiler-perf.json` | compiler 開的同組數字 |
| `T6/out-combined.json` / `out-combined.txt` | 擂台 5 合併負載 |

### 輸入的真實形狀(逐字取自 repo)

取自 `frontend/src/lib/stock-accum.ts`:`minutes` = `Map<number, MinuteAgg{c,v,i,o,u,h,l}>` 共 **271 格**
(`X_START_MIN` 540 → `X_END_MIN` 810);`vp` = `Map<number, VpCell{t,o,i}>`;`ticks` = `TickRow[]`
`slice(-200)`(`TAPE_MAX`)。vp 檔位數取 60 / 200 / 900 三檔 —— 900 是 `applyTick` 註解自己寫的
「autofit 的低價股(tick 0.01 元)可以近千檔」。牆面 150 檔 = `WATCHLIST_LIMIT`(CLAUDE.md §4)。

---

## 1. Baseline:repo 內現成的 prod trace(不是我量的,是既有紀錄)

`.claude/mod/group-grid-ticks/verification.md` §「09-03 開盤真環境驗證」:

| 項目 | 值 | 來源 |
|---|---|---|
| 取樣 | 09-03 09:01–09:03,**93 秒**,prod build,真實 80 檔自選 | verification.md ③ |
| RunTask 個數 | 148,274 | 同上 |
| **> 50 ms long task** | **0** | 同上 |
| 最大單一 task | **36.7 ms** | 同上 |
| 常態尖峰 | ~18 ms | 同上 |
| 整機 busy | **24.9 %** | user 轉述之 trace 摘要 |
| 同日盤後 `grep 佇列滿` | 0 命中(零丟包) | verification.md ② |

**這份 baseline 已經是「沒有 long task」的狀態。**下面所有對決都要放在這個前提下讀:
不是在修一個已經壞掉的畫面,是在問「還能不能更快、代價是什麼」。

⚠️ 口徑差異(必須講清楚):24.9% busy 是**整條主執行緒**(含 paint / layout / GC / 五條流的
WS 解析 / TanStack Query / SVG 光柵化);我下面量的 `React忙%` 只有 **React render + commit**
那一段。兩者不可直接相減 —— 見 §7 的歸屬討論。

---

## 2. 擂台 1:accum 更新模式(Node,純 JS)

5000 筆 tick、31 reps 取 p50。原始輸出 `T6/out-accum.txt`。

### vp = 200 檔(典型中價股)

| 模式 | p50 | p95 | µs/tick | 相對現況 |
|---|---|---|---|---|
| **A 現況 immutable**(`new Map`×2 + 陣列 spread) | 68.28 ms | 75.02 ms | **13.656** | ×1.00 |
| C `Object.freeze` immutable | 71.96 ms | 86.52 ms | 14.392 | ×0.95(更慢) |
| E 混合(內層 mutable + 頂層新物件) | 0.698 ms | 0.767 ms | 0.140 | **×97.8** |
| D 全 mutable + version counter | 0.620 ms | 0.640 ms | 0.124 | ×110.1 |
| **B index-offset 定長陣列**(頂層仍換 identity) | **0.573 ms** | 0.593 ms | **0.115** | **×119.2** |

### 三種 vp 規模

| vp 檔位數 | A 現況 µs/tick | B 最快 µs/tick | 倍數 |
|---|---|---|---|
| 60 | 10.502 | 0.109 | ×96.7 |
| 200 | 13.656 | 0.115 | ×119.2 |
| **900**(低價股 autofit) | **35.082** | 0.117 | **×299.9** |

### 歸因(vp=200,A 的子成本拆解)

| 子操作 | p50 | µs/tick | 佔 A |
|---|---|---|---|
| 只 `new Map(minutes)` 271 格 | 41.00 ms | 8.200 | **60.0 %** |
| 只 `new Map(vp)` 200 格 | 26.22 ms | 5.244 | **38.4 %** |
| 只 `[...ticks].slice(-200)` | 3.44 ms | 0.687 | 5.0 % |

> 與上一輪「minutes 佔 82%」的關係:那個數字在 **vp 檔位少**時成立(vp=60 時 minutes 約佔 78%)。
> vp 檔位一多,兩顆 Map 就變成 6:4。**兩顆都要處理,只修 minutes 只拿得到六成。**

### 擂台 1b:長尾與配置(60000 筆 = 200 tick/s × 300 s,vp=200)

| 模式 | 總時間 | p50 | p99 | **p99.9** | max | heapUsed |
|---|---|---|---|---|---|---|
| A 現況 | 860.4 ms | 12.90 µs | 30.60 µs | **107.00 µs** | 330.7 µs | 12.8 → 16.8 MB |
| E 混合 | **16.3 ms** | 0.20 µs | 0.50 µs | **1.50 µs** | 169.2 µs | 12.6 → 22.0 MB |

(`PerformanceObserver({entryTypes:["gc"]})` 在 node 24 回報 0 筆 —— **未量到 GC 事件**;
p99.9 的 107 µs 是 young-gen scavenge 透出來的間接證據,不是直接量測。)

### 這一格的誠實結論

**倍數很大,絕對值很小。** A 在 200 tick/s 的真實速率下 = 860 ms / 300 s = **主執行緒 0.29%**,
最壞單筆 330 µs(遠低於 50 ms long task 門檻)。換成 B 省下的是 0.29 個百分點。

**代價**(CLAUDE.md §4 口徑):
- B / D / E 都**破壞深層 immutability**。`stock-accum.ts` 的 `extendMinutes` 註解逐字寫著
  「不就地改傳入的 Map:來源是 TQ cache 的物件,污染它會讓下一次 render 拿到被改過的『快取』
  而看不出來」—— 改 mutable 正是去踩這顆雷。
- B 另外要重寫 `foldVp` 的 **export 契約**(後端 parity fixture 的對照面,change-spec AD-2)、
  `vpTruncated`、以及 `volume-profile.ts` / `stock-intraday-svg.ts` 兩個消費端。
- D(全 mutable + version)還會打掉 `GroupCard` 的 memo 邊界 —— 那是 50 張卡的命根(§4)。
  **E 是唯一保住 memo 邊界的 mutable 變體**,也只比 B 慢 22%。

---

## 3. 擂台 2:狀態分發(真 Chrome、prod build、150 訂閱者)

150 張卡,每張 render body 做 271 點 SVG path(= `CardIntradayChart` 的等價成本)。
**每則更新各自一個 macrotask**(`MessageChannel`,逐字模仿 WS onmessage)。1000 則。
原始 `T6/out-dist-chart.json`。

| 變體 | wall | React 淨(減 noreact) | **commits** | card 渲染 | **App 渲染** | Profiler actual | 幀距 p95 | LT>50ms |
|---|---|---|---|---|---|---|---|---|
| noreact(驅動器底噪) | 116.7 ms | — | 0 | 0 | 0 | 0 | 16.8 ms | 0 |
| **props(現況:狀態在 App)** | 616.8 ms | 500.1 ms | **1000** | 1000 | **1000** | **92.8 ms** | 17.1 ms | 0 |
| uSES(useSyncExternalStore) | 517.1 ms | 400.4 ms | 1000 | 1000 | **0** | 71.6 ms | 17.5 ms | 0 |
| bus(module EventTarget + 自帶 useState) | 500.5 ms | 383.8 ms | 1000 | 1000 | 0 | **65.0 ms** | 17.3 ms | 0 |
| zustand(selector) | 517.4 ms | 400.7 ms | 1000 | 1000 | 0 | **62.8 ms** | 17.0 ms | 0 |
| zustand-shallow(每檔一 slice) | 617.0 ms | 500.3 ms | 1000 | 1000 | 0 | 74.5 ms | 17.0 ms | 0 |
| jotai(atom per code) | 567.3 ms | 450.6 ms | 1000 | 1000 | 0 | 84.3 ms | 17.1 ms | 0 |
| signals(元件內讀 `.value`) | 483.7 ms | 367.0 ms | 1000 | 1000 | 0 | 82.1 ms | 17.0 ms | 0 |

> wall 被 profiling build 灌水(同組在一般 prod build 是 props 267 ms / jotai 183 ms);
> **`react_actual_ms` 與 `commits` 才是跨變體可比的量。**

### 三個關鍵事實

1. **commit 數全部一樣 = 1000。**換哪一套 store 都不會少一次 commit。
   commit 率由「訊息用幾個 task 送達」決定,不由狀態住在哪決定。
2. **card 渲染全部一樣 = 1000。**現況的 memo 邊界**已經是對的**(`CardProps` memo + 只有那一檔
   換 identity)。沒有任何 store 能把「一筆成交要重畫那一張卡」再往下砍。
3. 唯一真實差異是 **App 渲染 1000 → 0**,值 = `react_actual` 92.8 → 62.8~71.6 ms,
   即 **每則約 20–30 µs**。200 則/s 下 = **4–6 ms/s = 主執行緒 0.4–0.6 個百分點**。

### 擂台 2b:廣播(150 檔同時更新,60 輪)—— 架構完全無效的場景

| 變體 | 每輪 ms | commit/輪 | card 渲染/輪 | actual/輪 | 幀距 p95 | 幀距 max | LT>50 |
|---|---|---|---|---|---|---|---|
| noreact | 2.227 | 0 | 0 | 0 | 16.8 | 16.8 | 0 |
| props | 20.297 | 1 | 150 | 6.948 ms | 26.5 | 27.7 | 0 |
| uSES | 21.388 | 1 | 150 | 8.627 ms | 27.8 | 34.5 | 0 |
| bus | 20.295 | 1 | 150 | 8.578 ms | 25.2 | 26.5 | 0 |
| zustand | 24.745 | 1 | 150 | 7.827 ms | 30.4 | 32.8 | 0 |
| jotai | **19.462** | 1 | 150 | 7.857 ms | 22.5 | 29.0 | 0 |
| signals | 21.687 | 1 | 150 | 8.772 ms | 26.6 | 30.4 | 0 |

全部 1 commit / 150 card render / 20±2 ms。**全部 150 檔都變了的時候,沒有任何架構能少畫一張卡。**
這正是 repo 每秒一拍的 `watchlist_quote` 批與 60 s 群組重播種的形狀。

### → 上一輪「zustand 0 建議 / 5 反對」的驗證結果

**實測支持駁回,而且理由要修正得更準。**
上一輪的理由是「問題是 memo 邊界不是計算量」。實測顯示:memo 邊界**現況已經正確**
(每則更新只重畫 1 張卡),所以 zustand 連「修 memo 邊界」這件事都沒得做;
它拿到的 30 µs/則差異來自「App 不再重繪」,而那件事 **uSES / EventTarget 用零新依賴就拿得到**
(bus 變體 65.0 ms 甚至比 zustand 的 62.8 ms 只差 3%,在雜訊內)。
**zustand / jotai / signals 三者彼此的差距(62.8 / 84.3 / 82.1)比它們對現況的改善還不穩定。**

---

## 4. 擂台 4:批次化 —— 唯一真的降 commit 率的手段

### 4a. React 19 的 automatic batching 在 WS onmessage 生效嗎?

探針結果(`T6/out-batching.json` 的 `autobatch`):

| 情境 | commits | card 渲染 |
|---|---|---|
| **同一個 onmessage 內連呼 5 次 setState** | **1** | 5 |
| **5 則訊息分別在 5 個 task** | **5** | 5 |
| Promise microtask 內連呼 5 次 | 1 | 5 |
| `setTimeout` callback 內連呼 5 次 | 1 | 5 |

**答案:生效,但救不到重點。** React 19 確實會把**同一個 task 內**的多次 setState 併成一次 commit
(這對後端 `ticks` 打包訊息一則含多檔是有效的 —— 一則打包 = 一次 commit,repo 現況已經吃到了)。
但它**無法跨 task 合批**,而 80–200 則/s 就是 80–200 個獨立 task。

### 4b. 顯式合批模式(定速 200 則/s,5 秒,150 張 chart 卡)

`out-paced.json` / `out-paced2.txt`:

| 變體 | mode | 實到/s | **commit/s** | card 渲染/s | **React 忙%** | 幀距 p95 | 幀距 max | LT>50 |
|---|---|---|---|---|---|---|---|---|
| props | **immediate(現況)** | 195.3 | **195.3** | 195.3 | **1.84** | 16.9 | 17.4 | 0 |
| props | **rAF 合批** | 194.6 | **58.6** | 194.6 | **1.23** | 16.8 | 17.0 | 0 |
| props | microtask 合批 | 195.3 | 195.3 | 195.3 | 2.25 | 17.0 | 17.5 | 0 |
| props | `setTimeout(0)` 合批 | — | 999/1000 則 | — | — | — | — | 0 |
| deferred | immediate | 194.6 | **291.9** | 194.6 | 2.21 | 17.0 | 17.5 | 0 |
| deferred | rAF | 194.6 | 117.2 | 194.6 | 1.84 | 16.8 | 18.7 | 0 |
| transition | immediate | 194.6 | 194.6 | 194.6 | 2.30 | 17.1 | 18.7 | 0 |
| transition | rAF | 194.6 | 58.6 | 194.6 | 1.38 | 16.8 | 17.4 | 0 |
| uSES | immediate | 194.6 | 194.6 | 194.6 | 1.69 | 16.9 | 17.3 | 0 |
| uSES | rAF | 195.3 | **58.8** | 195.3 | **1.28** | 16.8 | 16.9 | 0 |

**rAF 是唯一會動 commit 率的招:195 → 58.6(×3.33,上限 = 螢幕更新率 60 Hz)。**
microtask 與 `setTimeout(0)` **完全無效** —— 因為每則訊息本來就已經在自己的 task 裡,
microtask 在同一 task 結尾就排空、`setTimeout(0)` 又開一個新 task,兩者都沒有跨 task 聚合能力。

**但 card 渲染數完全不變(195.3 → 194.6)。** rAF 只省掉 commit 的**固定開銷**(App 重繪 +
150 次 createElement + 150 次 memo 比較 + reconcile),不省每張卡自己的工 —— 因為每則更新
屬於不同的檔,那張卡終究要重畫。

### 4c. 800 則/s(開盤尖峰的 4 倍)

| 變體 | mode | 實到/s | commit/s | card 渲染/s | React 忙% | 幀距 max | LT>50 |
|---|---|---|---|---|---|---|---|
| props | immediate | 778.6 | 194.7 | 778.6 | 4.10 | 19.4 | **0** |
| props | rAF | 778.5 | 58.6 | 778.5 | 3.78 | 17.8 | **0** |

(800 則/s 時 immediate 的 commit 率自己就掉到 ~195 —— React 在來不及時會把仍在排隊的更新
併進同一次 commit。**這是 React 自帶的背壓,不是我設的合批。**)

---

## 5. 擂台 5:合併負載(最接近真實的一組)

逐筆 N 則/s(各自 macrotask)**+ 每秒一次 150 檔報價廣播**,150 張 chart 卡,6 秒。
`T6/out-combined.txt`:

| 變體 | mode | 逐筆/s | commit/s | card 渲染/s | **React 忙%** | 幀距 p50 | 幀距 p95 | 幀距 max | **LT>50** |
|---|---|---|---|---|---|---|---|---|---|
| **props(現況)** | immediate | 200 | 195.7 | 317.7 | **2.38** | 16.7 | 17.0 | 24.7 | **0** |
| props | rAF | 200 | 59.0 | 315.7 | 1.83 | 16.7 | 17.3 | 24.5 | 0 |
| uSES | immediate | 200 | 196.8 | 318.5 | 2.03 | 16.7 | 17.7 | 27.7 | 0 |
| uSES | rAF | 200 | 59.6 | 317.4 | **1.74** | 16.7 | 16.8 | 29.5 | 0 |
| props | immediate | **800** | 194.8 | 900.7 | **4.83** | 16.7 | 17.8 | 27.4 | **0** |
| props | rAF | 800 | 58.8 | 895.5 | 4.46 | 16.7 | 16.8 | 19.1 | 0 |

**在真實尖峰的 4 倍負載下,整個 React 層佔主執行緒 4.83%,零 long task,最大幀距 27.4 ms。**

---

## 6. 擂台 3:React 19 特性

### 6a. useDeferredValue / startTransition

**飽和 burst**(1000 則盡速投遞,`out-react19.json`):

| mode | wall | commits | **card 渲染** | actual | 幀距 max |
|---|---|---|---|---|---|
| plain | 684.0 ms | 1001 | **1000** | 86.4 ms | 18.0 |
| **deferred** | 451.5 ms | 1001 | **150** | **39.3 ms** | 19.1 |
| transition | 767.1 ms | 1000 | 1000 | 86.9 ms | 20.2 |

**定速 200 則/s**(`out-paced2.txt`,同上表):

| mode | commit/s | card 渲染/s | React 忙% |
|---|---|---|---|
| plain(props) | 195.3 | 195.3 | **1.84** |
| **deferred** | **291.9** | 194.6 | **2.21** |
| transition | 194.6 | 194.6 | 2.30 |

**⚠️ 結論在兩種節奏下相反,burst 那個數字是假的。**
`useDeferredValue` 只有在「更新比 React 畫得完還快」時才會**丟掉中間值**(burst:1000 則只畫 150 次);
一旦 React 跟得上(真實的 200 則/s),它就退化成**每則兩次 render**(緊急的舊值 + 延後的新值),
commit 率從 195 **漲到 292**、React 忙% 從 1.84 **漲到 2.21**。

`startTransition`:**零效果**(194.6 → 194.6,actual 86.4 → 86.9)。把單一 setState 標成 transition
不會讓它跟誰合併。

### 6b. ★ React Compiler 的牆鐘凍結風險 —— **確認為真,雙重證據**

這是本區塊最重要的發現,是**正確性**問題不是效能問題。

#### 證據一:編譯期(`out-compiler-walltime.txt`,babel-plugin-react-compiler 1.0.0)

把 `FuturesChart.tsx:282-307` 的 IIFE 形狀餵進 compiler,產物是:

```js
let t3;
if ($[1] !== holidaySet) {
  t3 = liveSlotOf(new Date(), holidaySet);   // ★ 牆鐘落在 cache guard 內側
  $[1] = holidaySet;
  $[2] = t3;
} else {
  t3 = $[2];                                  // ★ holidaySet 沒換 → 永遠拿快取
}
const live = t3;
```

`holidaySet` 是 `useTradingCalendar` 來的日曆集合,**一天才換一次 identity**。
→ `new Date()` 一整天只會執行一次。

六個 case 的機械判定:

| case | 形狀 | 牆鐘在 cache guard 內? | 判定 |
|---|---|---|---|
| 1 | `FuturesChart` IIFE(**repo 真實形狀**) | **★ 是**(guard = `$[1] !== holidaySet`) | **會凍** |
| 2 | `const now = new Date()` 進字串 | **★ 是**(guard = `$[0] !== label`) | **會凍** |
| 3 | `Date.now()` 只參與**純量**布林運算 | 否 | 安全 |
| 4 | `f(bars, accum, new Date())`(= `mergeLiveMinuteBars` 形狀) | **★ 是**(guard = accum/bars/code) | **會凍**(accum 不動時) |
| 5 | 對照組:無牆鐘 | — | 正常 memo 化 |
| 6 | 牆鐘在 `useMemo` 內、deps 不含它 | (compiler 不改 useMemo) | 本來就已經是 bug |

**規則歸納(實測導出)**:compiler 只快取「**產生物件 / 呼叫**」的運算,不快取純量表達式。
所以 **`Date.now()` 直接做數值比較是安全的;`new Date()` 餵進任何函式呼叫則會被連同結果一起快取**。

#### 證據二:runtime 真的凍住(同一份 code、同一台 Chrome、只差 build flag)

`FreezeHost` 每 30 ms 推一次假 WS 更新(`state` 換 identity、`holidaySet`/`slice`/`anchorDate` 恆定),
量 900 ms 內 `liveIndex` 出現過幾個相異值:

| build | `distinct_live_values` | 樣本 | 判定 |
|---|---|---|---|
| `dist`(compiler **關**,port 5199) | **30** | 59446, 59476, 59506, 59536, 59566 … | 正常跟著走 |
| `dist-compiler`(compiler **開**,port 5200)第 1 次 | **1** | `17256` | **凍住** |
| `dist-compiler` 第 2 次 | **1** | `18199` | **凍住**(凍在不同的掛載瞬間) |

bundle 側佐證:`dist-compiler` 有 `compiler-runtime` import 與 5 個 `memo_cache_sentinel`,
`dist` 只有 1 個(非 compiler 來源)。

**兩次獨立執行都凍、且凍在不同值 = 它確實凍在「掛載那一刻」。風險為真,不是理論。**

#### 6c. compiler 換到的效能(同組對照)

| 情境 | compiler 關 | compiler 開 | 改善 |
|---|---|---|---|
| 逐檔 1000 則 props `actual_ms` | 92.8 | 86.3 | −7.0% |
| 逐檔 1000 則 uSES `actual_ms` | 71.6 | 62.4 | −12.8% |
| 廣播 60 輪 `actual/輪 ms` | 6.948 | 6.707 | −3.5% |
| 定速 200/s immediate React 忙% | 2.36 | 1.85 | −0.51 pp |
| 定速 200/s rAF React 忙% | 1.52 | 1.14 | −0.38 pp |
| **commit/s(兩種 mode)** | 194.6 / 58.6 | **194.6 / 58.6** | **0** |
| **card 渲染(1000 則)** | 1000 | **1000** | **0** |

**compiler 換到 0.4–0.5 個百分點的主執行緒,代價是兩處真錢畫面的靜默凍結。**

---

## 7. 卡片 render 成本的分解(給「那 24.9% 到底是什麼」定位)

同一台 Chrome、同一組定速 200 則/s:

| 卡片型態 | `react_actual_ms`(1000 則) | 每次 commit | React 忙% |
|---|---|---|---|
| chart 卡(271 點 SVG path) | 93.3 | 93.3 µs | 1.82 |
| text 卡(純文字讀數) | 40.3 | 40.3 µs | 0.78 |
| **差額 = ChartBody 的工** | **53.0** | **53.0 µs** | 1.04 |

純 JS 幾何微量測(µs/次,150 檔牆的每張卡每次都要做一遍):

| 寫法 | µs |
|---|---|
| `extentOf`(271 格取極值) | **0.30** |
| **現況 `d += … .toFixed(1)`** | **30.45** |
| 改陣列 `push` + `join("")` | 33.10(**更慢**) |
| 去掉 `toFixed`,改整數位運算 | 24.58(只快 19%) |

**讀法**:一次 commit 的 93.3 µs 裡,幾何字串佔 30.45 µs(33%)、App 層固定開銷
(150 createElement + 150 memo 比較 + reconcile)佔約 40 µs(43%)、其餘是 SVG 屬性寫入與 commit。
`toFixed` **不是**主因,字串拼接本身才是;換 `join` 反而更慢。

**對 24.9% 的歸屬(推估,不是實測)**:我量到的 React render+commit 在真實合併負載下是 **2.38%**。
即使把 repo 的六條流、TanStack Query、WS JSON 解析全算進去,React 層也遠不到 24.9%。
剩下的 ~22 個百分點**我沒有量到**(要量必須跑 repo 的 server 與 prod build,本輪硬紀律禁止)
—— 合理的去處是 paint / SVG 光柵化 / style-layout / GC / WS 訊息解析,**但這是推估,標記為未量。**
→ **這是本區塊最該追的 open question,而不是再去優化 React。**

---

## 8. 最後回答:要把 App commit 率從 80–200 次/秒降下來,最有效的是哪一招?

### 實測排序(定速 200 則/s + 每秒廣播,150 張 chart 卡)

| # | 招式 | commit/s | 降幅 | React 忙% | 省下 | 判定 |
|---|---|---|---|---|---|---|
| **1** | **rAF 合批** | 195.7 → **59.0** | **×3.32** | 2.38 → 1.83 | **−0.55 pp** | **唯一真的降 commit 率的招** |
| 2 | 狀態外移(uSES / EventTarget,零新依賴) | 195.7 → 196.8 | **×1.00** | 2.38 → 2.03 | −0.35 pp | 降的是 App render 不是 commit |
| 3 | 1+2 疊加 | → **59.6** | ×3.28 | 2.38 → **1.74** | **−0.64 pp** | 兩招不衝突,可疊 |
| 4 | React Compiler | 194.6 → 194.6 | ×1.00 | 2.36 → 1.85 | −0.51 pp | **有正確性風險,見 §6b** |
| 5 | accum 改 mutable/定長陣列 | 不變 | ×1.00 | (Node 側 0.29% → 0.01%) | ~−0.28 pp | 倍數大絕對值小 |
| 6 | 換 state library(zustand / jotai / signals) | 不變 | ×1.00 | 差異在雜訊內 | ~0 | **駁回** |
| 7 | `useDeferredValue` | 195.3 → **291.9** | **×0.67(變差)** | 1.84 → 2.21 | **+0.37 pp** | **真實節奏下反效果** |
| 8 | `startTransition` | 194.6 → 194.6 | ×1.00 | 2.30 vs 2.30 | 0 | 零效果 |
| 9 | microtask / `setTimeout(0)` 合批 | 195.3 → 195.3 | ×1.00 | — | 0 | **機制上不可能有效** |

### 一句話

**只有 rAF 合批會動 commit 率(×3.3,上限 60/s);其餘全是在動「每次 commit 多貴」,不是「commit 幾次」。**

### 但更重要的一句話

**這個預算本來就不是瓶頸。** 現況在真實尖峰 4 倍的負載(800 則/s + 每秒廣播)下,
React 層只佔主執行緒 **4.83%**、long task **0 次**、最大幀距 **27.4 ms** —— 與 09-03 prod trace
的「>50 ms = 0、最大 36.7 ms」互相印證。
把 commit 率從 195 降到 59,買到的是 **0.55 個百分點**的主執行緒。
`.claude/mod/group-grid-ticks/change-spec §2.6` 當初寫的「不做 rAF,量到 long task 才加」
**在實測後依然成立**。

---

## 9. 量測的侷限(什麼情況下結論會反轉)

1. **合成牆 ≠ repo 的 App。** 我的 150 張卡沒有 `RightRail` / `QuoteTable` / `IndexBar` /
   `MetricsBar` / `OrderPanel` / 六條 TanStack Query。App 重繪在 repo 裡比我量到的 40 µs **貴**;
   若 repo 的 App 有未 memo 的重元件,§8 第 2 名(狀態外移)的排名會往上跑。**未量。**
2. **沒有 paint / 光柵化。** 我的卡片 SVG 在畫面上很小;repo 的分時圖大得多,`<path>` 重繪的
   光柵化成本我沒隔離出來。若那才是 24.9% 的主體,**所有 React 層的招式排名都不重要**。
3. **profiling build 的 wall time 被灌水**(props 267 → 617 ms)。跨變體比較一律用
   `react_actual_ms` 與 `commits`,不要用 wall。
4. **Node 的 accum 數字不等於 Chrome。** 擂台 1 在 node v24 的 V8 跑,與 Chrome 152 的 V8 版本不同;
   倍數關係應該穩健,絕對值不要直接搬。
5. **GC 未量到。** node 的 gc PerformanceObserver 回報 0 筆;p99.9 尾巴是間接證據。
   Chrome 側的 GC 我完全沒量。
6. **800 則/s 時 immediate 的 commit 率自己掉到 195** —— 這表示 React 自帶背壓,
   我的「commit/s」在飽和區不是自變數。200 則/s 那一組才是乾淨的對照。
7. **Windows 計時器**:`setInterval(10)` 實際達成 194.6/s(目標 200),偏差 2.7%,可接受;
   但 `frame_gap_p50` 恆為 16.7 ms 表示量測期間都有 vsync,背景分頁會完全不同。

---

## 10. 給後續的具體建議

| 招 | 判定 | 用在哪 | 條件 |
|---|---|---|---|
| **React Compiler** | **不建議(現狀)** | — | **先把 `FuturesChart.tsx:282-307` 與 `StockChart` 的牆鐘計算移出 render body**(搬進 `useState`+`setInterval` 的秒級 tick state,或加 `"use no memo"` directive)才可評估;否則開了就是兩處真錢畫面靜默凍結,零錯誤訊號 |
| **rAF 合批** | 有條件導入 | `useStockStream` 的 `ticks` case | 只有量到 long task 才做(§2.6 原判斷成立)。做的話**主圖那一檔要走直通**,否則逐筆明細會多 16 ms 延遲 |
| **狀態外移 uSES** | 有條件導入 | App 的六條流 → module store | 零新依賴、與現有 `tick-stream.ts` 同風格。但收益 0.35 pp,**應由「App 重繪會不會拖到未 memo 的重元件」決定,不由本數字決定** |
| **zustand / jotai / signals** | **不建議** | — | commit 率零改變、彼此差異在雜訊內、加 runtime 依賴違反 stdlib-only 精神(前端雖非 stdlib-only,但 `dependencies` 只有 5 個是刻意的) |
| **accum 改 index-offset / mutable** | **不建議(現狀)** | — | ×119 但只值 0.28 pp,且要破 `foldVp` export 契約 + TQ cache 不可污染的紀律。真要做,**選 E(內層 mutable + 頂層新物件)**:保住 memo 邊界、只比最快的 B 慢 22% |
| **`useDeferredValue`** | **不建議** | — | 真實節奏下 commit 率反增 50% |

### 最該做的一件事(不是效能改動)

**去量那 ~22 個百分點。** 在 repo 現有的 DevTools trace 上做一次 Bottom-Up 歸因
(Scripting / Rendering / Painting / System / GC 分帳),確認主執行緒到底花在哪。
本區塊已經證明 **React render + commit 不是主體**;再往 React 層優化是在雕 2–5% 的東西。
