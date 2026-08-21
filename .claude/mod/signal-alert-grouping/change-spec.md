# change-spec — 訊號 toast 與桌面通知走 groupSignals 合併 + 通知 latest-wins(mod/signal-alert-grouping,R3 / B4)

分流判定:已成形方案(§R3 指名檔案與做法;預核准)。Scope:**M**(2 源檔 + 測試)。現況見 `current-state.md`。

## 拍板(auto-default)
- `[amendment → 見末節 R5 / A2 / A11]` **D1 toast 合併鍵 = (code, time)**,與 `groupSignals` 同口徑;合併對象 = 佇列中**仍存在**(未 TTL 到期、未被 dismiss)的同鍵 toast,
  搜整個佇列不限相鄰(佇列最多十幾張)。`[auto-default | reason: 同 tick 三則到達間隔 ms 級,TTL 5s 內必在;兩檔交錯時 rail 的相鄰規則是為了不吃掉中間列,toast 佇列無此顧慮]`
- `[amendment → 見末節 R3 / A7 / A8]` **D2 合併文案 `formatGroupToastText(group)`**(signal-model 新 export):`code name <kind 段以「・」串接(groupKindLabels 到達序去重)> price`,
  price = 組內最早到那則(同 groupSignals 錨)。**不含規則名**(toast 一行,現行 formatToastText 亦無)。單則組輸出 === `formatToastText(sig)`(lock)。
  `[auto-default | reason: 沿 SignalRail 合併列 kind 段語意;規則名在 rail 另起一行,toast 放不下]`
- **D3 merge 不重設 TTL、key 不變**(key = 組內首張 toast 的 key)。`[auto-default | reason: ms 級合併,重設無意義;key 不變避免 React 卸載重掛閃爍]`
- **D4 嗶 = 每新組一聲**(merge 進既有 toast 不嗶)。`[auto-default | reason: §R3 明寫「音效每 tick 一聲即可」]`
- `[amendment → 見末節 R6 / R7 / A1 / A5]` **D5 桌面通知 latest-wins**:背景分頁收到訊號 → `pending = 該 toast 的合併文案`(同組後到者覆寫);若無排程 timer → 排在
  `max(now + COALESCE_MS(300), lastSent + NOTIFY_MIN_INTERVAL_MS(5000))` 發送;timer 到 → `notifyDesktop(pending)`,成功則 `lastSent = now`,
  pending 清空;permission 擋掉 → 不記帳(既有語意)、pending 清空。節流不變:任一 5s 窗至多 1 則;固定 tag 不變。
  `[auto-default: 300ms 合併 + trailing | reason: leading 會把未合併的首則推到 OS 且 5s 內無法更新;純 trailing 一個模型即涵蓋「窗內記最後一則、窗尾補發」]`
- **D6 unmount 清 pending timer**(與 TTL timers 同 cleanup)。

## 成功條件
- **SC-1 同 tick 三則 → 一張 toast**:emit 三則同 code+time(不同 kind / id)→ `toasts.length === 1`,text = `formatGroupToastText`(含三段 kind「・」),key 不變;
  不同 time 或不同 code → 各自一張。驗證:useSignalAlerts.test 新案。
- **SC-2 嗶每組一聲**:上例 `playBeep` 路徑 osc 建立次數 = 1;三則不同 tick = 3。驗證:沿用既有 AudioContext fake 計數。
- **SC-3 通知 latest-wins**:背景 + granted,t=0 發 A、t=10ms 發 A'(同 tick)→ 300ms 前 0 則、300ms 後恰 1 則且文案 = 合併文案;
  t=1s 再發 B → 5s 前仍 1 則,t=5s(lastSent+5000)第 2 則文案 = B;20 則連發 → 5s 窗內至多 1 則。驗證:fake timers。
- **SC-4 文案單一來源**:`formatGroupToastText(單則組) === formatToastText(sig)`;ToastStack 不動。
- **SC-5 畫面可指認(UI)**:dev 以 bus 注入同 tick 三則 → 右上角一張 toast 文案 `2330 台積電 a・b・c 2395.00`;截圖 + user 過目(Discord 合併訊息另案)。

## 不能破壞的既有行為白名單
- W1 suspended 不建節點 / closed 回收重建 / resume in-flight 守門(useSignalAlerts.test 音效 11 案,**不動**)。
- W2 固定 tag `copycat-signal`;任一 5s 窗 ≤ 1 則;permission 擋掉不消耗窗口;分頁可見不發通知;靜音不影響通知。
- W3 toast VISIBLE 4 + overflow、TTL 5s、dismiss 單張、同 id 重發 key 互異、unmount 退訂。
- W4 `formatToastText` 簽名與輸出不變;SignalRail / groupSignals 不動。
- W5 ToastStack 純展示不動。

## 該紅 / 不該紅(useSignalAlerts.test.tsx)`[amendment → 本節整段由末節「該紅表重寫」取代,勿照此寫]`
- 該紅(🔴 預告,通知模型改 trailing):`157 分頁隱藏…發桌面通知`(需推進 300ms)、`192 連發 5 秒窗內只發第一則…`(改:300ms 後首則、5s trailing 第二則文案 = 最後一則)、
  `216 背景爆量 20 則 → 恰 1 則`(改:≤ 同 tick 併一張 → toast 佇列 1 張 + 0 overflow;通知 300ms 後 1 則)、`228 窗內被 permission 擋掉…`(推進 300ms)、
  `252 靜音…Notification 照發`(推進 300ms)、`183 tag 固定`(推進 300ms)。**佇列案 103「連發 20 則 → 4 + 16」**:fixture 若同 code+time 會併成 1 張 →
  改 fixture 為不同 time(或 code)保留原語意,不改斷言本體。
- 不該紅:音效 11 案、佇列 114/125/137/148、`165 可見不發`、`173 非 granted`。

## Out of scope
Discord 合併訊息(後端已做)、SignalRail、toast 顯示規則名、通知 renotify / 點擊聚焦。

## Edge cases
1. 同 code 同 time 但跨 TTL(第一張已消失)→ 新張(不復活)。
2. 兩檔交錯同秒(A,B,A')→ A 與 A' 併、B 獨立(D1 搜整佇列)。
3. 同 kind 兩規則同 tick → kind 段去重 → 文案只一段(沿 groupKindLabels)。
4. `[amendment → 末節 R4:fire 時重驗 hidden,可見則丟棄]` ~~背景通知 pending 期間分頁轉前景 → timer 照發~~(pending 是已判定背景時收的)`[auto-default]`。
5. unmount 時 pending timer 清掉,不發。

## Diff 級
- 🟢 `lib/signal-model.ts`:`formatGroupToastText(group: SignalGroup): string`(+ signal-model.test 單則等價 lock、三段、去重)。
- 🔴 `hooks/useSignalAlerts.ts`:佇列項改 `{ key, items: SignalMsg[], text }`(`sig` 欄改為 `items[0]`?→ **保留 `sig`= 最早到那則**以免 ToastStack / 測試契約變;新增 `items`);
  merge 邏輯;嗶每組;通知 trailing 模型(`COALESCE_MS`、`pendingRef`、`notifyTimerRef`)。
- 測試先紅後綠;三類分開:🟢 新 export → 🔴 行為。

---
## Spec review round 1 amendments(`change-spec-review-round-1.json`,13 條全 accepted;以本節為準)

- **該紅表重寫(R1 / R2 / R8 / R10)** —— 依 `sig(id)` fixture 事實:code = id、time 恆 "09:15:03":
  - 103(20 則 code 互異)**完全不動**;216 toast 斷言 `4 + overflow 16` **維持(lock,不得放寬)**,只有通知部分該紅:推進 300ms 後恰 1 則、文案 = `formatToastText(sig("s19"))`(trailing = 窗內最後一則)、tag 不變。
  - 137「同 id 重發 → key 互異」**該紅**:兩次 `sig("dup")` 同 (code,time) → `toasts.length === 1`、key = 第一張 key、osc 次數 1;另補「不同 code 的 key 唯一」保住原意。W3 措辭改「不同 (code,time) 重發 key 互異;同鍵重發併入」。
  - 157 / 183 / 228 / 252:推進 300ms 後斷言(該紅:時序)。192:第一則(t=300)文案 = `formatToastText(sig("b"))`(窗內最後一則,**由最舊改為最新**);第二則於 lastSent+5000。
  - 165 / 173 不該紅但**必須補推進** `advanceTimersByTime(5_500)` 再斷言空(否則 vacuous);173 另補「轉 granted + 新訊號 → 300ms 後恰 1 則」。
  - `ToastStack.test.tsx:27-29` factory **該紅(型別)**:`SignalToast` 新增必填 `items: SignalMsg[]`(`sig` 保留 = 最早到那則);App.test 721-741 單則 emit 不該紅。
- **D2' items 慣例(R3)**:hook 內組物件維持 SignalGroup 慣例 —— 新到者**前插** `items: [sig, ...items]`,`key/name/price` 取 `items.at(-1)`;
  `formatGroupToastText` 只吃 SignalGroup。SC-1 補字面期望:到達序 a,b,c → `…a・b・c…`、price = a 的價;signal-model.test 同。
- **Edge 4 改 (a)(R4)**:timer fire 時重驗 `document.hidden`,為 false → 丟棄 pending、不記帳(W2 字面保留)。SC 補:hidden 發 → 100ms 後轉可見 → 推進 → 0 則。
- **D1' 合併限定(R5)**:只在同鍵 toast **仍在前 VISIBLE 張內且 TTL 剩餘 ≥ 500ms** 時合併,否則另開新張(照舊插首 + 嗶)。SC 補:佇列 6 張併入第 6 張 → 新張;TTL 剩 100ms → 新張。
- **D5' pending 全域單槽(R6)**:任何背景訊號到達即覆寫(不分組)。行為改動明列:同窗內不同標的只有最後一則進 OS(固定 tag 本就單格;「看到哪則」由最舊改最新)。SC-3 補跨標的覆寫斷言。
- **SC-3 絕對時刻(R7)**:t=0 A、t=10 A'、t=299 → 0、t=300 → 1(A' 合併文案,lastSent=300)、t=1000 B、t=5299 → 1、t=5300 → 2(B)。
- **Diff 級補(R9)**:`groupIndexRef: Map<"code|time", { key; items; expiresAt }>` 為合併真值;handler 先算(純 ref)再 `setQueue`(updater 純函式,StrictMode double-invoke 安全);`drop(key)` 同步 delete;unmount 清空。
  新測試:`renderHook(..., { reactStrictMode: true })` 同 tick 三則 → osc 1、toasts 1。
- **SC-5 注入手段(R11)**:臨時 `if (import.meta.env.DEV) (window as any).__emitSignal = emitSignal;`(signal-bus.ts,**截圖後同 PR 內移除**);payload 三則同 code 2330 / 同 time / kind cdp_cross、surge、vol_burst。
- R12:current-state caller 結論 = 唯一掛載點 App.tsx:163(→ ToastStack App.tsx:400),StockPage 僅共用 useSignalSound;per-hook ref 即全域。
- R13:同批改寫 useSignalAlerts.ts:76-80 / 132-139 註解為 trailing 模型。

---
## Spec review round 2 amendments(限縮輪,`change-spec-review-round-2.json`,11 條全 accepted;收斂)

- **A1 192 絕對時刻表**:t=0 emit a、b → t=299 → 0 則、t=300 → 1 則(文案 = b,lastSent=300)→ t=5299 emit b2 → 仍 1 則 → t=5300 emit c(pending 覆寫為 c)→ t=5598 → 仍 1 則、t=5599 → 2 則(文案 = c,= max(5299+300, 300+5000))。測試標題改「300ms 合併 + lastSent+5s 窗尾補發」。
- **A2 / A11 D1'' 合併條件**:刪「前 VISIBLE 張內」;改為「同鍵 entry 存在且 TTL 剩餘 ≥ 1500ms」才合併(真值 = `groupIndexRef` 的 `expiresAt`);**合併時在 `setQueue` updater 內把該張純粹地移到佇列首**(key / TTL 不變,純 reorder → overflow 區的張被併也會浮上來可見)。後到者最短可見 1500ms 為明示 auto-default。
- **A3 drop 守衛**:`SignalToast` 內帶 `groupKey`(`"code|time"`);`drop(toastKey)` 取該 toast 的 groupKey 後 `const g = index.get(groupKey); if (g?.key === toastKey) index.delete(groupKey)`(stale drop 不得刪新 entry)。SC 補:舊張 TTL 到期後,同鍵新訊號仍併入新張。
- **A4 165**:先斷言 toasts 1,`advanceTimersByTime(400)` 後斷言 notified 空(推進量 < TTL)。
- **A5 228 / 173 絕對時刻**:t=0 emit a(permission default)→ t=300 timer 觸發、notifyDesktop false、lastSent 仍 −Infinity、pending 清空、notified 空 → t=310 轉 granted、emit b → t=610 恰 1 則(誤記帳會延到 5300,斷言抓得到)。SC-3 併入同組時刻。
- **A6 StrictMode 案**:加字面斷言 `items.length === 3` 與 text === `2330 台積電 cdp_cross・surge・vol_burst <price>`(kindLabel 現回 kind 原字)。
- **A7 兩種 key 明寫**:`SignalToast.key = id#seq`(React key,永不變);hook 內建構給 `formatGroupToastText` 的 `SignalGroup.key = items.at(-1).id`(不外露)。137 補充案改「同 (code,time) 被 D1'' 判為新張時兩張 toast key 互異」。
- **A8**:`formatGroupToastText` 沿用 `.filter(x => x !== "")`;signal-model.test 補 name === "" 單則等價案。
- **A10**:注入口寫 `declare global { interface Window { __emitSignal?: typeof emitSignal } }` + `if (import.meta.env.DEV) window.__emitSignal = emitSignal;`(截圖後移除)。
- A9:本體五處已就地標 `[amendment → 末節]`。

---
## Code review round 1 amendments(`code-review-round-1.json`)
- C1:真實 hidden tab 的 setTimeout 最低 1s clamp → 合併窗實測 ≈1s(可接受;user 過目時量首則延遲)。
- C2:fire 時已回前景 → 丟棄,與 toast TTL 同長 → 極端情況兩邊皆無痕(接受:前景抵達路徑 = rail)。
- C3:`SignalToast.groupKey` 移除(drop 反查不需要)。C4:expiresAt 牆鐘與 setTimeout 單調混用 → 註解記 NTP 取捨(同 lastNotifyRef)。C5:cleanup 刻意不清 queue(effect 僅掛一次)註解。
- C7:SC-5 過目條件補「1 張三段合併 + 3 張單則 + 溢出列」多行觀感由 user 判斷是否比照 B3 加 line-clamp。
