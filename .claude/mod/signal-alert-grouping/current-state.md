# current-state — 訊號提示合併(R3 / B4)

來源:rounds.md §R3(預核准)。證據:next-time 08-20 signal-alert-side-effects 節兩條 + 08-18 denoise 節「toast/桌面通知不合併」。

## 現況
- `hooks/useSignalAlerts.ts`:bus `onSignal` 每則 → 新 toast(key=`id#seq`、text=`formatToastText(sig)`、TTL 5s、VISIBLE 4 + overflow)+
  背景分頁桌面通知(固定 tag `copycat-signal`,**leading edge** 5s 節流:窗內首則發、其餘丟)+ `getSoundOn()` 時每則一聲 `playBeep()`。
- `lib/signal-model.ts`:`formatToastText(sig)` = `code name kindLabel price`;`groupSignals(list)`(相鄰同 code+time 併組,錨最早到)、
  `groupKindLabels(group)`(到達序去重 kind 段)、`groupRuleNames(group)` —— 目前只有 `SignalRail.tsx:130` 用(顯示層合併,「WS payload / jsonl / toast 仍逐則」)。
- `components/ToastStack.tsx`:純展示 `toasts[].text`。`hooks/useSignalSound.ts`:開關真值。
- 同 tick 三則(CDP 穿越 + 爆拉 + 爆量)→ 三張 toast、三聲嗶、桌面通知只見最舊那則(leading)。

## Caller map
- `useSignalAlerts`:`App.tsx`(常駐)→ `ToastStack`;`StockPage.tsx` 只 import ToastStack?(grep:App.tsx / StockPage.tsx / ToastStack.tsx)。
- `formatToastText`:useSignalAlerts + 測試 `useSignalAlerts.test.tsx:148`。
- `groupSignals/groupKindLabels/groupRuleNames`:SignalRail + `signal-model.test.ts`。
- 測試:`useSignalAlerts.test.tsx`(toast 佇列 5 案 / Notification 8 案 / 音效 11 案)、`ToastStack.test.tsx`、`App.test.tsx:704-740`。

## 現況 vs 目標
| 面向 | 現況 | 目標 |
|---|---|---|
| toast | 每則一張 | 同 code+time 併一張(文案沿 SignalRail 合併列:kind 段「・」串接) |
| 嗶 | 每則一聲 | 每 tick(每新組)一聲 |
| 桌面通知 | leading 5s 節流,窗內後到者丟 | latest-wins:300ms 合併 + 5s 節流下的 trailing 補發,文案 = 該組合併文案 |
| 三條 lock | suspended 不建節點 / closed 重建 / 固定 tag + ≤1 則/5s | 不變 |
