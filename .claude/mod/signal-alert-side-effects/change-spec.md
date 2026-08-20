# Change spec:訊號提示副作用收斂(mod/signal-alert-side-effects)

> S 級(單一 production 檔 / 無對外 API / 無 migration)→ 0 輪 spec review(scope-tiers /mod S)。
> 分流判定一行:已成形(handoff R4 指名檔案行號 + 修法)。

## 成功條件

- **SC-1** `playBeep()` 在 AudioContext `state !== "running"` 時不建任何節點,改為嘗試
  `resume()`(附 `.catch` 吞掉)後直接返回;toast 不受影響。
  驗證:vitest `useSignalAlerts — 音效與靜音 > AudioContext suspended → 跳過該聲不建節點,並嘗試 resume`。
- **SC-2** 背景分頁桌面通知 tag 固定為 `"copycat-signal"`(不再用 `sig.id`),OS 層同 tag 覆蓋合併。
  驗證:vitest `useSignalAlerts — Notification > 通知 tag 固定為 copycat-signal(OS 層合併)`。
- **SC-3** 背景分頁通知節流:每 5 s 至多一則(leading edge:窗內丟棄、窗後放行;
  未實際發出的不消耗窗口)。
  驗證:vitest `useSignalAlerts — Notification > 連發訊號 5 秒窗內只發第一則,窗後放行`。
- **SC-4** 既有 2314 測試不紅(白名單全保留)。驗證:`npm test`(frontend/)全綠。

真實環境層:此改動為背景分頁 / 長時掛機副作用,無畫面可指認元素;真環境驗證 =
盤中背景分頁通知合併為單則(user 過目,驗證窗口 = 交易日盤中有訊號時;窗口外降級 = vitest 行為鎖 + user 事後回報)。

## 不能破壞的既有行為白名單

1. toast 佇列:VISIBLE=4 / TTL 5 s / dismiss 單則 / 同 id 重發 key 互異 / 文案 = formatToastText。
2. 靜音 → 不出聲,但背景 Notification 照發(review MFS-1 語意)。
3. 分頁可見 → 不發通知;permission 非 granted → 不發。
4. AudioContext 不存在(舊瀏覽器 / jsdom)→ 靜默略過,toast 照出。
5. AudioContext running → 每則一聲短嗶(880 Hz / 0.12 s / gain 0.04),單例不重建。
6. unmount 後 bus 退訂,不再收訊號。

## Out of scope

- 訊號 grouping 合成一張 toast(next-time 08-18 留尾,降噪輪範疇)。
- 其餘 handoff P2(R5 / R6 各自輪)。
- resume 成功後「補嗶」被跳過的訊號(提示音是附加價值,不補)。

## 拍板(全 auto-default,無方向性抉擇)

- [auto-default: suspended 時**跳過該聲**而非 resume 後補排 | reason: 補排會在 resume 瞬間
  連環嗶(積壓幾小時的訊號一次響),且提示音本就定位附加價值;resume() 照發讓後續訊號恢復出聲]
- [auto-default: 節流窗 5_000 ms | reason: 與 toast TTL 同量級;固定 tag 已在 OS 層合併,
  節流只防通知系統 churn,窗太長會讓背景久放後的新訊號延遲可見]
- [auto-default: 節流狀態放 hook `useRef` 而非 module 變數 | reason: hook 常駐 App 單掛載,
  ref 語意等價;測試天然隔離,免加 test-only reset export]

## Edge cases

1. context `closed`(系統回收):`state !== "running"` 同樣跳過;`resume()` reject 被 `.catch` 吞。
2. 節流窗內 permission 未 granted:`notifyDesktop` 早退回 false → 不消耗窗口,授權後首則不被舊時戳擋。
3. 爆量 20 則(背景):恰 1 則通知(第一則),toast 佇列照常 4 + overflow 16。
4. fake timers 下 `Date.now()` 與 `setTimeout` 同源推進(vitest 預設 fake Date)— 測試依此寫。

## Diff 級章節(單檔 + 測試)

### 🔴 `frontend/src/hooks/useSignalAlerts.ts`(行為改動,唯一 production 檔)

- `playBeep()`:`state === "suspended"` 分支改為 `state !== "running"` → `ctx.resume().catch(() => {})` + return(不建節點)。
- `notifyDesktop(text, tag)` → `notifyDesktop(text): boolean`:tag 固定常數 `NOTIFY_TAG = "copycat-signal"`;成功建構回 true(供節流記帳)。
- hook 內:`lastNotifyRef = useRef(-Infinity)`;`document.hidden` 分支改
  `now - lastNotifyRef.current >= NOTIFY_MIN_INTERVAL_MS(5_000)` 才呼叫,發出成功才寫時戳。

### 🔴 `frontend/src/hooks/useSignalAlerts.test.tsx`(既有測試該紅的 / 不該紅的)

- **該紅(新增,red 先行)**:SC-1 suspended 測試(現行實作會建節點 → 紅)、SC-2 tag 測試
  (現行 tag = sig.id → 紅)、SC-3 節流測試(現行每則必發 → 紅)。
- **不該紅(白名單鎖)**:既有 16 條全部維持綠(fake 基建改 getter/選項捕捉屬 test-infra,不改斷言)。
- fake 基建:`FakeAudioContext.state` 改讀 module 變數(getter)+ `resume` 計數;
  `FakeNotification` 建構子捕捉 `options.tag`。

## 三類 commit 計畫

1. `🔴 test(frontend): 訊號提示副作用紅測試(suspended 跳過 / tag 固定 / 節流)[red]`
2. `🔴 fix(frontend): playBeep suspended 不建節點 + 通知 tag 固定與 5s 節流 [green]`
3. `chore(mod-signal-alert-side-effects): artifacts`

無 🔵 / 🟢 成分;migration 無(不碰持久化)。

## Amendments

- [amendment 2026-08-20: code review F2 — suspended 每則排 resume 會累積 pending promise
  (autoplay 未解鎖時永不 settle),加 module 級 in-flight 旗標,同時間只留一發]
- [amendment 2026-08-20: code review F4 — closed context 永不復活,Edge case 1 從「skip +
  catch」改為「回收單例不 resume,下一則重建恢復出聲」;白名單 5 的「單例不重建」約束的是
  running 態,closed 回收不違反]
- [amendment 2026-08-20: code review F3 — 固定 tag 的「覆蓋」語意精確化:只發生在跨節流窗,
  窗內由節流取首則;trailing/latest-wins(窗尾補發最新一則)留 next-time]

self_review_head: aef58782
