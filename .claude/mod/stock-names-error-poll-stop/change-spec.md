# change-spec — useStockNames 錯誤態輪詢收斂

分流判定:已成形方案(需求指名落點檔案 + 做法「停止不是退避」,行為已由 user 在
docs/next-time.md 排程時拍板)→ 預核准,免 grilling 停等。S 級 → 0 輪 spec review。

## 成功條件

- **SC-1 錯誤終態停止輪詢**:fetch 連續失敗達上限後,3s 輪詢停止(不退避、不無限輪詢)。
  驗證:白盒測試(`namesRefetchInterval` 求值 `errorUpdateCount >= 上限` → `false`)+
  fake-timer 整合測試(永久失敗下 fetch 次數收斂後長時間 advance 不再增加)。
- **SC-2 輪詢節奏與停止條件被測試鎖住**:interval 改 1ms 或停止條件拿掉,至少一條測試轉紅。
  驗證:白盒斷言 `=== 3000`(mutation 抽驗:改 1ms → 紅);SC-1 測試(停止條件拿掉 → 紅);
  成功案「拿到資料後長時間 advance,fetch 次數不增」(next-time 原案為真 sleep 3.5s,改用
  fake timers 等價斷言 — 決定性且不吃 3.5s wall-clock,樣板 useBreadthRows.test.ts)。
- **SC-3 註解與現實對齊**:同檔 :35「error 態要能浮現(404 / 舊 build 的錯誤碼契約靠它)」
  改為與現實一致(error 態無 consumer;retry:1 的實際作用 = 壓每輪嘗試次數);docstring
  補「連續失敗上限後停止,refocus 為 backstop」。驗證:人工重讀該檔。
- **SC-4 next-time 勾銷**:docs/next-time.md 兩條 P2(:975 輪詢不退避、:979 測試不鎖節奏)
  標 `[x]` + 完成註記。驗證:diff。

## 不能破壞的既有行為白名單

- **W-1 啟動窗自動復原**:上限內連續失敗 → 3s 輪詢繼續,server 起來後不需 focus/remount
  自動拿到資料(既有測試 useStockNames.test.tsx:58「啟動窗內連續失敗後應自動復原」不得紅)。
- **W-2 成功即停**:拿到資料(哪怕空表)→ 輪詢停(refetchInterval false),穩態零成本。
- **W-3 錯誤碼契約**:404/500 的 error message 仍走 parseError(既有測試 :42、:80 不得紅)。
- **W-4 names 缺失 → 空表可用**:提示列不出現但直接打股號可用(既有測試 :35 不得紅)。
- **W-5 caller 零感知**:WatchlistSidebar / WatchlistManagerDialog 只讀 data,回傳 shape 不變。
- **W-6 refocus backstop**:停止輪詢後 refetchOnWindowFocus 預設行為不動(不顯式關閉)。
  [amendment 2026-08-11: review A-1 — 實際觸發 = 分頁 visibilitychange,非純 window focus;
  B-1 測試鎖已補(mutant refetchOnWindowFocus:false 紅)]

## 關鍵決策

- `[auto-default: 以 query.state.errorUpdateCount >= NAMES_MAX_ERROR_CYCLES 判停 |
  reason: errorUpdateCount 每輪失敗 cycle +1 且不被 retryer 覆寫(fetchFailureCount 會);
  success 後不重置無妨 — data 永存即不再輪詢]`
- `[auto-default: NAMES_MAX_ERROR_CYCLES = 20(≈ 首輪 retry 1-2s + 19 輪 × 3s ≈ 60s 涵蓋窗)|
  reason: PR #20 後 server bind 0.037s,60s 足以涵蓋「先開前端後起 server」常態;永久 404
  一分鐘內收斂;refocus 仍是停止後復原後門。上限值屬內部實作,互換不改 SC/契約,非方向性]`
  [amendment 2026-08-11: review A-2/B-5 — 算術更正:interval timer 每次 state 更新重啟,
  每輪 = 1s backoff + 3s = 4s,20 輪實際 ≈ 77s(非 60s)。上限值 20 維持不動]
  [amendment 2026-08-11: review A-1/B-1(P1)— 「refocus 後門」精確化:v5 focusManager
  只聽分頁 visibilitychange(hide→show),純 window focus 不觸發;兩 caller 常駐掛載
  無 mount 後門。行為維持「停止」(拍板),後門語意入註解與測試鎖;
  [auto-default: 知情接受 visibilitychange/reload 為僅有復原路徑,不加 keepalive |
  reason: 60s 級心跳實質是退避到地板,牴觸「停止」拍板;分頁切換/重整在本機看盤
  workflow 屬常態操作]]
- `[auto-default: 匯出具名 namesRefetchInterval + 兩常數供白盒測試 |
  reason: frontend-testing skill 明列「輪詢行為改斷言 refetchInterval 求值結果(白盒但可紅)」;
  hook 對外 signature 不變]`
- `[auto-default: 停止語意=fake timers 長 advance 斷言 fetch 次數不增(取代真 sleep 3.5s)|
  reason: 同 skill 樣板 useBreadthRows;決定性、零 wall-clock flake,斷言強度等價]`

## Out of scope

- 其他啟動窗 REST query 的失敗終態盤點(next-time :768 另條,不動)。
- refetchOnWindowFocus 行為調整、error 態 UI 呈現(無 consumer,維持現狀)。
- 退避(backoff)設計 — 已拍板為停止。

## Edge cases

1. 失敗 19 輪後第 20 輪成功 → data 永存,停止輪詢(W-2 路徑,errorUpdateCount 不歸零無妨)。
2. 達上限停止後分頁 visibilitychange(hide→show)→ 觸發一次 refetch;再失敗
   errorUpdateCount 續增仍停;成功則復原。[amendment 2026-08-11: review A-1 —
   原寫「window refocus」,v5 只在分頁可見性切換觸發;整合測試已鎖此雙向行為]
3. 空表 `{names: []}` → success(非 error),即停(W-2;空陣列 !== undefined)。
4. body 合法 JSON null / names 欄位缺失 → 既有 M9 行為不變(W-3/W-4)。

## Diff 級章節(逐檔)

| 檔 | 類別 | 動作 |
|---|---|---|
| `frontend/src/hooks/useStockNames.ts` | 🔵 | 抽出 `namesRefetchInterval` 具名 export(行為不變)+ 修正 :35 與現實不符註解(SC-3 前半,零行為) |
| 同上 | 🔴 | 加 `NAMES_MAX_ERROR_CYCLES`,`errorUpdateCount >= 上限` → false;docstring 對齊(SC-1/SC-3 後半) |
| `frontend/src/hooks/useStockNames.test.tsx` | 🟢 | 新增:SC-1 白盒 3 條(data 定義 → false / 上限內 → 3000 / 達上限 → false,前兩條為 lock)+ fake-timer 整合(永久失敗收斂、成功案不增)(SC-2) |
| `docs/next-time.md` | docs | 兩條 P2 勾銷(SC-4) |
| `.claude/mod/stock-names-error-poll-stop/` | chore | artifacts |

既有測試該紅/不該紅:**全部不該紅**(無測試鎖「錯誤態無限輪詢」舊行為;:58 復原測試在
上限內不受影響)。新測試:白盒「達上限 → false」+ 整合「停止後不增」在 🔴 前為紅([red])。
lock 類(3000 節奏、成功即停)無紅可先行 → mutation 抽驗 + `[lock]` tag。

---

## 自評收斂記錄

- code-review round 1:2 lens(opus/high),P1 ×1(A-1+B-1 合併)+ P2 ×6,全 accepted 修畢
  (`code-review-round-1.json`);mutation 抽驗三刀皆紅後還原(3000→1 / 移除成功即停 /
  refetchOnWindowFocus:false)。
- self_review_head: 819f810e
