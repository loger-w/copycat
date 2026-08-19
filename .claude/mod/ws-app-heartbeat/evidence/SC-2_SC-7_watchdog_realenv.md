# SC-2 / SC-7 真環境:側車 8899(worktree code)+ vite 5199 proxy,選擇權頁 ConnectionBadge(2026-08-20 00:00–00:05)

前置:頁面載入後等 > 10 s(DevTools console 已見 ping 武裝;sidecar `/ws/txo-pnl` 每 10 s ping,SC-1 已量)。
觸發:`POST /_fake/stall?secs=45`(側車 event loop 同步阻塞 = TCP 活、零 frame)。
觀測:頁內 MutationObserver 記 badge 文字變化(`window.__badgeLog`,ISO UTC);helper 的 console.warn 時戳。

## 第一輪(stall 00:00:46 本地 = 16:00:46Z)
badge log:
  16:00:37.902Z 即時連線中
  16:01:09.578Z 連線中斷,重試中   ← watchdog 觸發(最後一則 ping 後 30 s;console: "txo-pnl: 30 s 無訊息,重連" @00:01:09)
  16:01:11.577Z 連線中             ← backoff 1 s 重連 → onConnecting(實測 2.0 s:背景分頁 timer 對齊 1 s 粒度)
  16:01:31.386Z 即時連線中         ← stall 結束(00:01:31)新連線 open,立即復原
console(其餘 WS 同時觸發,全在 30–35 s 窗):futures 35 s @01:14;index 35 s / stock 34 s @01:19。

## 第二輪(stall 00:04:05)
  16:04:31.596Z 連線中斷,重試中   ← 觸發
  16:04:33.627Z 連線中
  16:04:50.797Z 即時連線中         ← stall 結束 00:04:50 即復原
截圖:SC-7_badge_recovered_after_stall.jpg(復原後「即時連線中」,footer 更新 00:04:58)。
「連線中斷,重試中」只維持 ~2 s,未能截到靜態圖 —— 以 badge log + console 時戳為主證(spec SC-7 已註明)。

結論:SC-2 PASS(30–35 s 內觸發、卸舊 socket 立即重連、server 恢復即自癒);SC-7 PASS(兩段序列符合)。
備註:本次 Chrome MCP 分頁多次 `Page.captureScreenshot` 逾時(renderer 暫時無回應),為 dev build 既有現象(crash-scan handoff 脈絡),與本輪改動無關。
