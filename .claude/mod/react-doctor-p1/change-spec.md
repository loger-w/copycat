# change-spec — react-doctor P1 批修復(mod/react-doctor-p1,2026-08-11)

規格來源:`docs/research/2026-08-11-react-doctor-triage.md` §一 P1(user 拍板,預核准)。
現況盤點:`current-state.md`(同目錄)。規模:/mod L(9 檔;無對外 API / 無 migration /
caller 零波及 — L 只因檔數)。

## 成功條件

- **SC-1 useRiver 換場 fetch 移出 updater**:`onDelta` 的 setState updater 為純函式;
  換場判定用 sessionRef(先例 `useStockStream.ts` statusRef F-1)。
  驗證:新測試「StrictMode 下盤別變更只打 1 次 /api/river/state」(紅先行)+
  既有「盤別變更 → 清空 + 換窗 + 重抓全量」綠。
- **SC-2 WatchlistSidebar 持久化移出 updater**:`toggleCollapsed` / `dropCollapsed` /
  `toggleUngroupedCollapsed` 三處 handler 內先算 next → persist → set。
  驗證:新測試「StrictMode 下 toggle 折疊寫 localStorage 恰 1 次且值正確」(紅先行,
  `vi.spyOn(Storage.prototype, "setItem")`)+ 既有折疊持久化測試綠。
  [amendment 2026-08-11: spec review P1-1 — `dropCollapsed` 的唯一呼叫者是 PUT mutation
  的 onSuccess(WatchlistManagerDialog `commit(deleteGroup…, () => onGroupDeleted(key))`),
  非事件路徑;直接讀 render 閉包在「連刪兩組、兩發 PUT 同批 resolve」下會把已清的組名寫回。
  修法改 **imperative ref 配對**(repo 先例 useStockStream accumRef):`collapsedRef` 於每個
  寫入點同步更新,三個 collapse handler 一律 `const next = new Set(collapsedRef.current)` 起手
  → 算 next → `collapsedRef.current = next` → persist → `setCollapsed(next)`。不採 reviewer
  的 useLayoutEffect 同步案:同一 tick 內兩個 onSuccess 連續執行時 layout effect 尚未跑,
  ref 仍舊值,守不住;imperative 配對是同步的,守得住。`toggleUngroupedCollapsed`(boolean、
  純點擊路徑)維持直接形式。另補 lock 測試:連刪兩組同批 resolve → localStorage 兩組名皆
  不留(現況 updater 形式本來就對 → 綠上加鎖,不掛 TDD tag,review 補強型)。]
- **SC-3 TickTape key 前插不位移**:key = `${t.t}-${ticks.length - 1 - i}`。
  驗證:新測試「追加新成交後,原有列的 DOM node 恆等(===)保留」(紅先行)+
  既有「最新在最上」「載入更多」綠。
  [amendment 2026-08-11: spec review P2-3 — stock-accum `TAPE_MAX = 200` 滿載後陣列左移,
  回推索引仍逐筆 −1 → 滿載常態盤中本修法無效(與現況同級,不惡化)。
  [auto-default: 接受此限制(triage 裁決的兩案取回推索引;真解 = stock-accum 帶單調
  序號,波及 out of scope 檔案)| reason: 行為保持批不擴 scope];限制記
  verification.md 並入 docs/next-time.md。]
- **SC-4 StockChart isFut 收斂改 render 期間調整**:刪 `useEffect`,改
  adjust-state-on-prop-change(樣板 `WatchlistManagerDialog` prevOpen);`spotModeRef`
  改 `spotMode` state。
  驗證:新測試「回現貨(還原日K)時 StockIntradayChart 零中間 commit」(紅先行,
  vi.mock 計 render 數,獨立測試檔)+ 既有 D10 期貨態 4 條 / A6 還原 4 條全綠。
  [auto-default: 不建顯式 prevIsFut state,用兩個自收斂 render 分支
  (`isFut && mode !== "intraday"` 存偏好並收斂 / `!isFut && spotMode !== null` 還原一次)
  | reason: 語意與原 effect(deps [isFut, mode],含期貨態內 mode 漂移的狀態機保險)逐分支
  等價,prevIsFut 在此無讀者;純內部實作,SC / out of scope / 對外契約全不動]
  [auto-default: spotModeRef 改 useState | reason: render 期間寫 ref 違反同一 rule
  家族,會以新 finding 形式回來;state 化後語意不變(只在 render 調整分支寫入)]
- **SC-5 冗餘 render ref 寫入刪除**:`useFuturesStream.ts:61`、`useStockStream.ts:136`
  各刪一行(imperative 配對寫入已全覆蓋)。
  驗證:兩檔既有測試全綠;doctor 對應條目消失。
- **SC-6 ref 同步規範化**:`useBreadth` 1 ref、`useIndexStream` 3 ref 搬 `useLayoutEffect`
  (宣告於 WS effect 之前);`useSignalAlerts` 的 `drop` 改 `useCallback([])` 並刪 `dropRef`。
  驗證:三檔既有測試全綠;doctor 對應條目消失。
- **SC-7 doctor 對照**:`npx react-doctor@latest --verbose --no-telemetry` 重掃,
  useRiver(115 + 連帶 94/95/100)/ WatchlistSidebar(115/51/117)/ TickTape(57)/
  StockChart(78)/ useFuturesStream(61)/ useStockStream(136)/ useBreadth(61)/
  useIndexStream(71-73)/ useSignalAlerts(82)條目全部消失,且**不新增**本批檔案的新
  finding。驗證:重掃輸出對照表寫入 verification.md。
  [amendment 2026-08-11: spec review P2-5 — fallback:若 useLayoutEffect 版觸發 doctor /
  eslint 同族新條目,**不得 disable rule**,verification.md 記「已知取捨(render 期間寫
  ref 的替代方案,triage 已裁決)」並列入 triage §四待拍板清單;lint gate 判準 =
  `npx eslint src` 退出碼(warn 不阻擋)。]

## 不能破壞的既有行為白名單(全部有既有測試釘住,assertion 一律不改)

1. useRiver:盤別變更 → 清空各腿分鐘 + 換窗 + 重抓全量;舊 seq delta 丟棄;比 delta 舊的
   snapshot 仍 union 補分鐘(P1-1);server 重啟 seq 歸零後 delta 仍生效;503 不拋;
   非 river 型別訊息忽略、壞 JSON 不崩、wsStatus open/closed(useRiver.test.ts:160-177)
   [amendment 2026-08-11: spec review P1-2 補列]。
2. WatchlistSidebar:折疊狀態寫 `WL_COLLAPSED_KEY` / `WL_UNGROUPED_KEY` 並在重載後還原;
   刪組回呼清折疊名(W-20);內容相同零 PUT(W-22)。
3. TickTape:最新在最上;三欄依參考價上色;載入更多 +30;空態句;h-full 版面。
4. StockChart:期貨態模式鈕 disabled + tooltip;殘留日K存檔收斂回江波圖且**不寫回
   localStorage**;期貨態 `/api/stock/bars` 一發不打(含收斂前 render);回現貨還原進合約前
   模式、還原只做一次;現貨態行為逐項不變。
5. useStockStream:status 比較與 refetch 留在 handler 本體(F-1 註解;本輪只刪 :136);
   :126/128/135 的 render 寫入**不動**(needs-human 刻意時序)。
6. useSignalAlerts:toast TTL 5s 自動消失;dismiss 即時移除並清 timer;VISIBLE 上限;
   market kind 不打擾;unmount 清全部 timer;**`onSignal` 訂閱恰一次、effect deps 恆穩定
   (unmount 後不再收訊號,useSignalAlerts.test.tsx:222)** — 包 A 改 deps `[]` → `[drop]`
   正碰這條,`drop` 的 useCallback deps 必須恆為 `[]`,否則 effect 重跑清光 TTL timer
   [amendment 2026-08-11: spec review P1-2 補列]。
7. useBreadth / useIndexStream / useFuturesStream:換日清 series + refetch 對齊;seq 跳號
   refetch;reconnect onopen refetch;退避 1s→30s。

## Diff 級章節(逐檔;三類標記)

依 /mod 順序 🔵 → 🔴。兩包檔案集互斥。

### 包 A 🔵(純重構,行為零差異)— commit `🔵 refactor(frontend): react-doctor P1 render ref 同步收斂 [refactor]`

- `hooks/useFuturesStream.ts`:刪 :61 `stateRef.current = state;`(含前置註解該行語意不變,
  註解酌改)。
- `hooks/useStockStream.ts`:刪 :136 `accumRef.current = accum;`。**只動這一行**。
- `hooks/useBreadth.ts`:`stateRef` 同步改 `useLayoutEffect(() => { stateRef.current = state; }, [state])`,
  宣告位置在 WS `useEffect` 之前;import 補 `useLayoutEffect`。
- `hooks/useIndexStream.ts`:三行同步併一個 `useLayoutEffect`(deps `[twse, otc, tradeDate]`),
  位置同上;import 補 `useLayoutEffect`。
- `hooks/useSignalAlerts.ts`:`drop` 改 `useCallback((key: string) => {…}, [])`;刪 `dropRef`
  宣告與同步兩行;:96 `() => dropRef.current(key)` → `() => drop(key)`;:117
  `dismiss: (key) => dropRef.current(key)` → `dismiss: drop`;WS effect deps `[]` → `[drop]`
  (穩定,語意不變);import 補 `useCallback`、若 `useRef` 仍被 seqRef/timersRef 用則保留。
- 既有測試:全部不該紅。

### 包 B 🔴(行為修復;紅先行)

紅 commit `🔴 test(frontend): react-doctor P1 行為修復紅測試 [red]`(只加測試;
[amendment 2026-08-11: spec review P2-7 — 紅綠兩顆皆掛 🔴,本批無新功能,🟢 誤導三類判讀]):

- `hooks/useRiver.test.ts` 新增:StrictMode wrapper 下換場 delta → 換場觸發的
  `/api/river/state` 恰 1 發(現況 updater double-invoke → 多發 → 紅)。
  [amendment 2026-08-11: spec review P2-6 — 寫法照先例 useStockStream.test.ts:283-299:
  STRICT wrapper → 等 state 就緒 → 斷言 `FakeWS.instances.length === 2` → 取
  `instances.at(-1)`(對 instances[0] 發訊息會假綠:`alive=false` 丟 snapshot)→ 記錄
  `before = fetchMock.mock.calls.length` → emit 換場 delta → 等一個 macrotask 後斷言
  `calls.length === before + 1`(紅態期望不寫死 2,eager updater 可能 3)→ 並加驗 night
  snapshot 真的併進 state(session / window / minutes)。]
- `components/stock/WatchlistSidebar.test.tsx` 新增:StrictMode wrapper 下點折疊 →
  `setItem(WL_COLLAPSED_KEY, …)` 恰 1 次且值正確(現況 2 次 → 紅)。
- `components/stock/TickTape.test.tsx` 新增:render 兩筆 → 記住列 node → rerender 前插
  第三筆 → 原兩列 node `===` 保留(現況全 key 位移重掛 → 紅)。
- `components/stock/StockChart.futconverge.test.tsx` 新檔:vi.mock `StockIntradayChart`
  (named export stub,每次 render `renders.push(props.stkfut)`)→ 日K → 進合約 →
  清空紀錄 → 回現貨 → 斷言**不存在 `stkfut === false` 的紀錄** + 最終掛上 K 線圖
  (現況 effect 收斂在回現貨第一個 commit 以 stkfut=false render 一次 → 紅)。
  CandleChart 不 mock(沿既有 fetch stub)。
  [amendment 2026-08-11: spec review P2-4 — 「零 render」斷言對 useContainerSize /
  query settle 的無關 re-render 偽紅,改斷言「無 stkfut=false 紀錄」。]

綠 commit `🔴 fix(frontend): react-doctor P1 updater 副作用與收斂時點修復 [green]`(body 註
`red→green for <red-sha>`):

- `hooks/useRiver.ts`:新增 `sessionRef = useRef<string | null>(null)`;`applySnapshot` 同步
  `sessionRef.current = next.session`;`onDelta` **順序固定**
  [amendment 2026-08-11: spec review P2-1]:`if (msg.seq < seqRef.current) return;` →
  `seqRef.current = msg.seq;` → `sessionRef.current !== null && !== msg.session` 判換場
  (同步 ref + `void load()`)→ `setState(純 updater)`(updater 內以 `prev.session` 判
  清空換窗,移除 `void load()`)。舊 seq 的跨場 delta 先被 seq 守衛丟掉:不觸發 load、
  不動 sessionRef(與現況等價 — 現況 updater 也看不到它)。
- `components/stock/WatchlistSidebar.tsx`:依 SC-2 amendment 改 **collapsedRef imperative
  配對**:`collapsedRef = useRef(collapsed)`,`toggleCollapsed` / `dropCollapsed` 以
  `collapsedRef.current` 起手算 next → 同步 ref → persist → `setCollapsed(next)`
  (`dropCollapsed` 保留 `!has → return` 早退);`toggleUngroupedCollapsed` 直接形式
  (boolean、純點擊路徑)。
- `components/stock/TickTape.tsx`:key 改 `${t.t}-${ticks.length - 1 - i}` + 註解(前插穩定;
  滿 200 環形丟頭時位移與現況同,不惡化)。
- `components/stock/StockChart.tsx`:刪 isFut `useEffect`;`spotModeRef` → `spotMode` state;
  render 期間兩分支(存偏好並收斂 / 還原一次);註解改述三處
  [amendment 2026-08-11: spec review P2-2 — :56「不能靠 mode 自己擋」、:64-73「ref 記著
  (A6)」、:100-102「閃一格」皆隨新機制失真,一併改述];
  `showIntraday = isFut || mode === "intraday"` 保留(防禦);清未用 import。
- `hooks/useStockBars.ts`:**僅註解**(:74-77「模式收斂是 effect(下一個 render 才生效)」
  改述為「收斂在同一 render pass 完成,但本 hook 在調整分支前呼叫,外部否決(enabled
  參數)仍是唯一保證」),零邏輯改動
  [amendment 2026-08-11: spec review P2-2 — 檔數 9 → 10,此檔 comment-only]。

## Edge cases

1. useRiver:delta 換場但 snapshot 未到(state null / sessionRef null)→ 不觸發 load
   (與現況 updater 早退等價);load 回來的 snapshot 换 session 亦同步 sessionRef。
2. useRiver StrictMode 雙 mount:兩條 effect 各自 `load()` 照舊(現況即如此,不在 scope);
   本輪只收斂「換場 delta」路徑的雙發。
3. TickTape 滿 200 筆環形:`ticks.length` 恆 200,丟頭使回推索引位移 → 與現況行為相同,
   註解記載,不視為回歸。
4. StockChart 首掛即期貨態 + 殘留 day 存檔:第一個 render 期間即收斂(intraday),
   localStorage 保持 day;`barsUrls` 恆空(既有測試釘住)。
5. useSignalAlerts:`drop` 穩定化後,TTL timer 到期呼叫的恆為同一顆函式 —— 與 dropRef
   「拿最新」語意等價(函式體只讀 ref 與 stable setter)。
6. WatchlistSidebar `dropCollapsed`:呼叫者是 mutation onSuccess(非事件路徑),連刪兩組
   同批 resolve 時兩回呼在同一 tick 連續執行 —— collapsedRef 同步更新守住,localStorage
   不得留下任一已刪組名(lock 測試釘住)[amendment 2026-08-11: spec review P1-1]。
7. useRiver 舊 seq 跨場 delta:seq 守衛先行丟棄,不觸發 load、不動 sessionRef
   [amendment 2026-08-11: spec review P2-1]。

## Out of scope(明確不動)

- `useStockStream.ts:126/128/135`(needs-human:切檔鍵 render 寫入為刻意時序)。
- `CapitalConfirmDialog` 手刻 modal(中價值,單獨拍板)。
- a11y 一行批 / js-hoist-intl / limitOnly 去重等 /chore 快修批(另開)。
- doctor.config rule disable / 降級與接 gate(§四,待 user 拍板)。
- TickTape 後端序號 key(需 API 變更,超出行為保持邊界)。

## Spec review 紀錄

Round 1(change-spec-reviewer,opus):0 P0 / 2 P1 / 7 P2,**全數 accepted** 並以
`[amendment 2026-08-11]` 逐條併入本檔(P1-1 dropCollapsed 非事件路徑 → collapsedRef
imperative 配對;P1-2 白名單補列;P2-1 seq 守衛順序;P2-2 註解三處 + useStockBars
comment-only;P2-3 TAPE_MAX 滿載限制記帳;P2-4 futconverge 斷言改 props 紀錄;
P2-5 SC-7 fallback;P2-6 StrictMode 測試細節照先例;P2-7 commit 標記統一 🔴)。
無 accepted P0 → 不加輪。

## 既有測試紅名單

**該紅:無**(行為保持批,不改任何既有 assertion)。任何既有測試變紅 = 打到不該動的,
回 spec 檢查。新增測試 4 處見包 B 紅 commit 清單。

---

self_review_head: 0b196814(code review round 1:0 P0 / 2 P1 / 10 P2 全 accepted;
fix 波 22d7cd6e + 0b196814,mutation-verified ×3;白名單 7/7 preserved)
