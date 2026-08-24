# R5 前端狀態/對話框/自選批 — verification

## 1. commits

| sha | 類 | 內容 |
|---|---|---|
| `11e19136` | 🟢 test | 十三條的行為鎖(前端 12 檔測試 + 後端 parity 斷言 + 共用 fixture) |
| `d03c70e7` | 🔴 mod | 十二條行為改動(N030 以外全部;含新檔 `useWatchlistCommit` / `signal-params`) |
| `6281afa0` | 🔵 refactor | N030 江波圖 hover 收斂(純結構,畫面逐值不變) |

三類不混:🟢 只動 `*.test.*` 與 fixture;🔴 只動實作;🔵 只動 `RiverOverlay.tsx`。
分支內 `11e19136` 與 `d03c70e7` 之間為刻意的紅態(TDD 紅先行),分支尾端全綠。

## 2. 紅態證據

### 2.1 直接紅(先寫測試、跑給自己看,再實作)

`npx vitest run`(六檔)首跑 **5 failed / 8 tests failed / 201 passed**:

| 條 | 測試 | 紅態錯誤 |
|---|---|---|
| N097 | `list-drag`「y 在最後一組下方的空白區 → null」 | `expected { group: '空組', index: +0 } to be null` |
| N097 | `list-drag`「兩條作廢帶並存」 | 同上 |
| N083 | `FuturesLadder`「resolved_contract 壞值 → 不拋」 | `expected [Function] to not throw an error but 'Error: invalid YYYYMM: 2026' was thrown` |
| N067b | `PriceLadder`「另一分頁改折數 → 輸入框與計算一起換」 | `expected '1.8' to be '0.5'` |
| N055 | `SignalRulesDialog`「參數欄位帶後端值域」 | `expected [ null, null ] to deeply equal [ '0', '3600' ]` |
| N055 | `SignalRulesDialog`「參數超出值域 → 指出哪一格」 | `Unable to find an element with the text: 線外駐留秒數須在 0–3600 之間` |
| N064 | `StkfutLadder`「非整數均價走 fmt 口徑」 | `expected '多 2 口 @100.50+800' not to contain '@100.50'` |
| N068 | `useCapital`「consumer 單獨掛載不自行輪詢」 | `expected 5 to be 1`(60 s 內多打 4 次) |

過程中修正了兩條**鑑別力不足**的斷言(先綠 → 改嚴 → 才紅):
- N064 整數案原寫 `toContain("@100")`,對 `@100.00` 同樣成立 → 改逐字比對第一顆 span。
- N067b 反向守門原用中途值 `"2."`,但 jsdom 的 `type=number` 會把非法字串正規化成 `""`(量到的是
  jsdom 而不是我的邏輯)→ 換 `"2.50"`(合法輸入,clamp 後字面不同)。

### 2.2 mutation 驗紅(綠燈到手的鎖 —— 逐條把實作改壞,確認該條會紅)

每條:套用 mutation → 跑該檔 → 還原 → 確認源碼零 `MUTANT` 殘留(全 repo grep 只剩舊 artifacts)。

| # | mutation | 對應鎖 | 結果 |
|---|---|---|---|
| M1 | 拿掉 `subscribe` 的 `storage` listener | N067a | RED(1 failed / 8) |
| M2 | `raw` 同步去掉 `lastWrite` 判別子(外部/自己一律覆寫) | N067b 反向守門 | RED(1 / 79) |
| M3 | `markSettled` 直接 return(不排契約檢查) | N114 | RED(1 / 16) |
| M4 | `zonesNow` 的 `voidAboveY` 恆 undefined | N097 元件層 | RED(1 / 100) |
| M5 | 側欄拖曳改回 render 閉包基底 `applyDrop(wl, …)` | N117 跨元件 | RED(1 / 100) |
| M6 | `submitAddGroup` 的 transform 退回 `addGroup(base,name)`(靠 dedup) | N115 | RED(1 / 45) |
| M8 | 佇列 `onDone` 加 `instances > 0` 守門 | N116 | RED(1 / 100) |
| M9 | 下移 `slot` 由 `i + 2` 改 `i + 1` | N266 | RED(2 / 45) |

N030 不走 mutation 改走**自檢斷言**:`ticks`/`pts` 兩個探針在掛載時 `toBeGreaterThan(0)`,
再斷言 mousemove 後 delta 為 0,同時 `overlayRenders` delta 為 3 —— render body 確實跑了三次,
所以「刻度與 polyline 字串 +0」不是探針沒接上。

## 3. 完成前 gate(指令 / 結果 / exit;無管線後綴,exit code 直讀)

| 指令 | 工作目錄 | 結果 | exit |
|---|---|---|---|
| `npx tsc -b` | frontend/ | 0 error | 0 |
| `npx vitest run` | frontend/ | **142 files / 2710 tests passed**(master:141 / 2679 → +1 檔 +31 案) | 0 |
| `npx eslint src` | frontend/ | 0 問題 | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | frontend/ | **No issues found**(掃 23 檔) | 0 |
| `.venv\Scripts\python -m pytest -q` | repo root | **2920 passed**(+1) | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | repo root | All checks passed | 0 |
| `.venv\Scripts\python -m pyright` | repo root | 0 errors, 0 warnings, 0 informations | 0 |

react-doctor 過程:第一輪出現 **4 個新增 finding**(存量不算),逐條以**改 code** 消化,未動 doctor config:
1. `only-export-components`(SignalRulesDialog:52)← 我把 `PARAM_FIELDS` export 出去 → 表搬 `lib/signal-params.ts`。
2. `no-prop-callback-in-render`(WatchlistManagerDialog:79,error 級)← hook 回傳的 `setError` 在 render 期間被呼叫 →
   改成「錯誤 state 歸呼叫端、hook 只回報 `onError(code|null)`」(設計上也更對:三個 caller 的錯誤各自長在不同位置)。
3. `prefer-module-scope-pure-function` ×2(`rejectIfUnchanged` / `applyDrop`)→ 兩者都已不吃元件閉包 → 移模組層。
4. `no-giant-component`(PriceLadder:197)← 我加的折數同步邏輯把它推過門檻 → 抽成 `useFeeDiscountField`(`lib/fee-discount.ts`)。

`copycat validate` 未跑:本輪零改動落在 `copycat/`(僅 `tests/` 新增一條 parity 斷言 + fixture),
replay/golden 面不受影響。

## 4. 白名單逐條核對

| # | 核對方式 | 結果 |
|---|---|---|
| W1 | `list-drag.test.ts` 既有 9 案不改 + 新增「未傳 voidAboveY → 位元不變」 | PASS |
| W2 | 「連點兩次同一刪除鈕 → 只送一筆 PUT」等 dedup 案不改 | PASS |
| W3 | 「連續操作」四案(序列化 / 逐發 onDone / 失敗短路 / 新動作)不改 | PASS |
| W4 | 側欄「載入失敗 → 管理鈕不渲染」「pending → 不渲染」兩案不改;佇列另加 `base === null` 早退 | PASS |
| W5 | `CapitalConfirmDialog` 既有 16 案不改(含 unmount 零 callback / StrictMode showModal 恰一次) | PASS |
| W6 | 折數既有 6 案不改(非法值 / 字面 key / 三處同 tick 同數字) | PASS |
| W7 | 個股期 / 期貨梯送單、武裝、活單徽章、平倉對象案全數不改 | PASS |
| W8 | 送出 payload 的 `params` 鍵集斷言不改(`{rearm_ticks, rearm_dwell_secs}`) | PASS |
| W9 | `RiverPanel.test.tsx` 幾何數字案不改(腿名 x、末點、讀值列) | PASS |
| W10 | `useCapital` 既有 invalidate 五案不改 | PASS |

事前標「該變」且實際改動的既有斷言,只有兩條(均在 change-spec §1 登記):
`StkfutLadder`「@100.00 → @100」、`RiverPanel.memo`「`ticks` 探針 → `overlayRenders` 探針」。

## 5. 未做 / 留尾(交還 user)

**未做:0 條**(13 條全數落地)。

留尾(看到但**沒有**在這次動):
1. **`CapitalPositionsList` 的 `avg_price.toFixed(2)` 沒跟著 N064 改**:那是表格欄位(對齊靠固定小數位),
   與 N064 講的「同一畫面同一筆數字兩個字面」不是同一件事。要不要統一是 user 的取捨。
2. **N068 的代價要 user 知道**:`useCapitalPositions` 現在**只在 `useCapitalStream` 在場時才輪詢**。
   prod 由 App 保證在場;但日後若有人在 App 之外掛個股頁 / 圖牆,部位會停在掛載那一發直到 WS 事件。
3. **N115 的輸入框**:佇列視窗內撞名時文案會出來,但輸入框在 eager 放行時已清空 —— 使用者要重打一次組名。
   「保留輸入內容直到套用成功」是另一個題目(要把輸入框變成 pending-aware)。
4. **N118 的「加股 + 刪組交錯」走不到**:建議列在 `isPending` 期間停用(review F1),故該組合無法從 UI 觸發,
   已在測試註解申報;若日後放寬停用條件,這條要補鎖。
5. **N030 只收了「字串重組」,沒收「render body 重跑」**:cursor 仍住在 `RiverOverlay`,每則 mousemove 一次
   render(現況拍照 = 3)。要往下收得換手法(cursor 下沉到子元件 / 十字線獨立成一層),是另一個題目。
6. **`out/doctor-baseline.txt` 已過時**(2026-08-11 那份):本輪比對時發現它與現況差距不小,
   新增 finding 的判定改以「同一分支 before/after 兩次 `--scope changed`」為準。要不要重錄基線由 user 決定。

## 6. 需要 user 過目(畫面 / 真環境)

- **管理窗的 ▲/▼ 兩顆鈕**(N266):字級 `0.625rem`、上下堆疊在列首,窄窗下的觀感與誤觸半徑。
- **規則窗的值域文案**(N055):`線外駐留秒數須在 0–3600 之間` 的句型與冷卻秒數一致,但參數多起來時是否嫌吵。
- **閃電梯折數框跨分頁**(N067):開兩個分頁改折數,確認框與損益同步。
- **側欄下方空白區拖曳**(N097):容差為一列高,貼著最後一列下緣放開仍會 append —— 手感要真滑鼠試。
- **dev console**(N114):跑 `npm run dev` 開任一確認窗按確認 / 取消,console 應**零** `CapitalConfirmDialog` 警告
  (四個 caller 都守約);若有,代表某條路徑沒卸載,那正是這條要抓的東西。

## 7. two-axis review round 1 收修(主 session)

| 項 | 處置 |
|---|---|
| SP1 N115 | 撞名早退拿掉(只留保留名 / 空白前置),撞名一律 transform 回 null → BAD_GROUP;既有 N115 案未改仍全綠 |
| ST3/SP4 | `requestCancel` 旗標回到 `onCancel()` 之前(重入保護),`markSettled` 拆為各路徑自設旗標 + `armContractCheck` |
| ST1/ST2/SP3 | CLAUDE.md §4 登錄「訊號規則參數值域前後端同表」;fixture `_note` / pytest docstring / 前端測試檔頭三處路徑改指 `lib/signal-params.ts` / `lib/signal-param-parity.test.ts` |
| ST5 / ST6 / ST7 | 🔵:`useFeeDiscountField` 直呼 `useFeeDiscount()`;RiverOverlay memo 回傳 `xOf` 供十字線共用;刪 `errorMessage` 別名 |
| ST4 | 反駁:N266 與 N115/N117/N118 同檔同 hunk,不拆 commit(偏離記錄) |

**收修後 gate**:`npx tsc -b` PASS / `npx vitest run` **142 files / 2710 tests** / `npx eslint src` PASS / react-doctor No issues / `pytest tests/test_signal_rules.py` 122 passed / ruff PASS。

### 申報(review 補的、要 user 知道)
- **SP2 N068 反向代價**:`useCapitalStream`(provider)現在**無條件**每 15 s 打 `/api/capital/positions`,停在 TXO / 廣度頁也照打;舊行為是零 observer 零請求(但 prod header 恆掛部位讀者,實務上舊版也幾乎恆輪詢)。要不要加「有讀者才輪詢」由 user 拍板。
- **SP5**:`useWatchlistCommit` reject 發 `BAD_GROUP` 後,同批後續動作成功會 `onError(null)` 洗掉文案 —— 與 §5 第 3 條(輸入框清空)同題,pending-aware 回饋另開題。
- **SP6**:`instances 0→1` 整份重置是測試隔離加的 prod 語意;三 writer 全卸載且 PUT 在途時新佇列 base 回退(`setQueryData` 兜底,風險低)。
