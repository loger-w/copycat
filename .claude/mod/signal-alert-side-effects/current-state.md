# 現況(mod/signal-alert-side-effects)

> 來源:2026-08-19 瀏覽器崩潰掃描 handoff R4(P2,驗證者判非崩潰根因但與「跑久後掛」時間相依性最像)。
> 分流判定:已成形(handoff 已指名落點檔案 + 修法)→ 免發散,S 級 0 輪 review。

## 問題 1:AudioContext suspended 時的節點洩漏

`frontend/src/hooks/useSignalAlerts.ts:30-46` `playBeep()`:

- `ctx.state === "suspended"` 時 `void ctx.resume()` 後**照樣**建 oscillator + gain 並
  `osc.stop(ctx.currentTime + 0.12)` — suspended 時 `currentTime` 凍結,graph 不推進,
  排程的 stop 永不執行 → 已 start 未 stop 的節點不可 GC,每則訊號洩兩個節點。
  autoplay policy 下 resume() 可能永不成功(需 user gesture),整天看盤只增不減。
- `void ctx.resume()` 在 context closed 時回 rejected promise 且無 catch → unhandled rejection。

## 問題 2:背景分頁 Notification 洪水

`useSignalAlerts.ts:97` `notifyDesktop(text, sig.id)` — tag 用唯一 `sig.id`,
每則訊號各佔一則 OS 通知,爆量時疊成一排不合併、無任何節流。

## Caller map(grep useSignalAlerts|playBeep,含動態用法零命中)

| 符號 | caller | 影響 |
|---|---|---|
| `useSignalAlerts()` | `App.tsx:141`(唯一,常駐掛載) | 回傳 shape 不動 → 零影響 |
| `playBeep()` | hook 內部 `:99` + 測試 | export 簽名不動 |
| `notifyDesktop()` | module 私有,hook 內部 `:97` 唯一 caller | 簽名改(去 tag 參數)僅內部 |
| `SignalToast` type | `ToastStack.tsx` / 測試 | 不動 |

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| suspended 嗶聲 | resume + 照建節點(洩漏) | resume(附 catch)+ **跳過該聲**,不建節點 |
| closed 嗶聲 | createOscillator throw 被吞(碰巧沒漏) | 同上,state !== "running" 一律跳過 |
| Notification tag | `sig.id`(每則一格) | 固定 `"copycat-signal"`(OS 層覆蓋合併) |
| Notification 頻率 | 每則必發 | 每 5 s 至多一則(hook ref 節流,leading edge) |
| Backward compat | — | 無對外 API / 無持久化資料,App 內部行為;無 migration |
