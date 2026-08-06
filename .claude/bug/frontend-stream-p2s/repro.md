# repro — frontend-stream-p2s(quintet review F-1~F-5,前端五條 P2 批次修)

來源:`.claude/bug/stkfut-order-channel/review-findings.md`(前端三題 reviewer,
每條含 file:line trace + 自我反駁)。branch:`fix/frontend-stream-p2s`
(基準 f6a60675 = origin/master)。穩定重現 = 紅測試(vitest 構造時序)。

## F-1:`refetch()` 副作用寫在 `setStatus` updater 內(StrictMode 雙發)

- trace:`useStockStream.ts:219-225` 把「主圖回補完成 → 全量 refetch」判斷與呼叫
  塞進 `setStatus((prev) => {...void refetch(); return next;})`。React updater 契約
  是純函式;StrictMode(main.tsx:11 全站)double-invoke → 第一次設
  `refetchingRef=true`,第二次進 in-flight 分支設 `pendingRefetchRef=true`(:104-108)
  → 第一次 finally 讀旗標**再發一次真的 fetch**(:129-132,合併不丟棄語意)。
  每次回補完成串行多打一份 MB 級 snapshot(`_TICKS_MAXLEN=20_000`)。
- 修法:比較搬出 updater —— 用 ref 存上一則 status(如 `statusRef`),
  「backfilling → 非 backfilling 且 key 相符」的判斷與 `refetch()` 呼叫在
  message handler 本體做,updater 只回 next(純函式)。

## F-2:`book` WS 訊息無 stale guard 也不進 pending buffer

- trace:`tick` 有兩道時序保護(refetch 中進 `pendingRef` :161-164、重放只收
  `seq > snap.seq` :117-119);`book`(:177-188)直接 `accumRef.current={...acc,book}`。
  時序:t0 發 fetch(server 凍結簿)→ t0+δ 新 book 推播套用 → t0+Δ snapshot 回來
  整份覆蓋 → **新簿被較舊 snapshot 回捲**,鎖板/盤後推播稀疏時回捲窗數十秒
  (鎖板正是 §0a 核心場景)。五檔、鎖停 badge、量 bar 分母一起回捲。
- 修法:refetch 進行中收到的 `book` 存 `pendingBookRef`(只留最新一份,含
  instrumentKey 標記);snapshot 套用後若 pendingBook 的 key 相符 → 蓋回;
  key 不符丟棄。切檔時清。
- 方向性的誠實記帳(review A-3):「推播必比 snapshot 新」是**近似恆定不是恆定** ——
  snapshot 凍結在後端 handle 該 request 的當下(不是前端送出的當下),誤差 =
  request 單程延遲,那個窗內產生的推播理論上可能比 snapshot 舊。localhost 下窗是
  次毫秒級,而回捲窗可達數十秒,取這一邊。真正定序要 book seq(後端未發,不在本輪)。

## F-3:`refetch` 非 2xx / throw 靜默失敗無重試 → 頁面釘「載入中…」

- trace:`:113` `if (res.ok)` 無 else、`:124-126` catch 只 console.warn;
  兩路都不改 accum(null)不設錯誤態不排重試。`accum===null` 時 tick 早退(:166)
  → seq-gap 自癒死路;唯一活路 WS onopen(沒斷就不發)。#28 的 `?contract=`
  讓 502/503 從正常操作可達。
- 修法:失敗(非 2xx 或 throw)→ 排程重試(backoff 1s→2s→4s,cap 8s,
  不設次數上限但排程前檢查:instrumentKey 未變 + WS 仍在 + 元件未 unmount);
  切檔 / unmount 時取消 pending 重試。不新增 UI 錯誤態(重試會自癒;避免
  掃到文案層 scope)。

## F-4:`<TickTape key={code}>` 沒跟上 instrumentKey

- trace:`StockPage.tsx:381`;code 在換月與現貨↔合約時恆不變 → TickTape 不重掛,
  「載入更多」展開筆數跨 instrument 存活。同頁 :90-93 pickerOpen 與 #28 的
  instrumentKey 貫穿(useStockStream deps / RightRail centerRequest / StkfutLadder
  武裝)都已對齊,獨漏此處。
- 修法:key 改 instrumentKey(`instrumentKeyOf(code, contract)`,同頁已有來源)。

## F-5:VP 價位帶 `half = tickOf(p)/2` 在 tick 級距邊界跨過鄰檔

- trace:`volume-profile.ts:64-66`;p=100.00 元 → tickOf=500 → 帶下緣 99_750,
  但下方合法檔位 99.90 的帶上緣 99_950 → 重疊 0.2 元,fillOpacity 疊加看起來
  像該帶量特別集中。發生在 10/50/100/500/1000 元**五**個級距邊界
  (`stock-tick.ts` 的 `TICK_TABLE` 有五個交界;原記「四個」漏了最低的 10 元那道)。
- 修法:帶邊界改「與相鄰合法檔位的中點」—— bottom=(p+stepDown(p))/2、
  top=(p+stepUp(p))/2(stock-tick.ts 已有 stepDown/stepUp 或等價 helper,
  沿單一定義,不自寫第二份 tick 規則);非邊界檔位結果與現行等價
  (中點 = p±tick/2),僅邊界檔位收斂,測試鎖跨級距案例。

## 實驗記錄

- 五條 trace 由 review finder 附自我反駁(含測試缺口實證:useStockStream.test.ts
  status 測試未鎖 fetch 次數上界、book 測試無 refetch 交錯案例、volume-profile
  測試全在單一級距內構造);主 session 覆核修法方向。
- 執行證據 = 各紅測試(Phase 8 反向驗證)。
