# R9a 全站 localStorage 收斂 — verification

## 1. commits

| sha | 類 | 內容 |
|---|---|---|
| `36e8d78e` | 🟢 test | 兩個失效面的行為鎖(`lib/storage.test.ts` 新檔 11 案、`MarketPane.storage.test.tsx` 新檔 3 案、`App.test.tsx` +2 案)[red] |
| `fa0003d9` | 🔴 mod | 新檔 `lib/storage.ts` + **27 處裸奔**呼叫點搬家(行為:拋 → 退預設 / 不落檔) |
| `d8c3924e` | 🔵 refactor | **21 處已包 try/catch** 的呼叫點搬家(逐字同行為) |
| `7a57925a` | chore | react-doctor `no-event-handler` 誤報逐行 triage(inline disable + 理由落 `lib/storage.ts` 檔頭) |
| `296bd7fd` | 🟢 test | 舊 key 遷移順序契約的 lock(mutation 驗紅) |

三類不混:🟢 只動 `*.test.*`;🔴 只動實作且只碰裸奔處;🔵 只動實作且只碰已包 try/catch 處。
分支內 `36e8d78e` 與 `fa0003d9` 之間為**刻意的紅態**(TDD 紅先行),分支尾端全綠。
`.claude/skills/ops-discipline/SKILL.md` 有他 session 的未提交修改,全程未碰(收工時仍是 ` M`)。

## 2. 紅態證據

### 2.1 直接紅(先寫測試、跑給自己看,再實作)

`npx vitest run src/lib/storage.test.ts src/components/index/MarketPane.storage.test.tsx src/App.test.tsx`
於 `36e8d78e` 的實測:

| 條 | 測試 | 紅態錯誤 |
|---|---|---|
| storage 純函式 | `src/lib/storage.test.ts` 整檔 | `Error: Failed to resolve import "@/lib/storage" from "src/lib/storage.test.ts". Does the file exist?`(新模組尚不存在;`Tests: no tests`) |
| (a) 存取即拋 | `MarketPane`「仍掛得起來,標的 / 週期退回預設值」 | `expected [Function] to not throw an error but DOMException{ stack: 'SecurityError:…' } was thrown` |
| (b) 寫入拋 | `MarketPane`「加權+日K → 切櫃買:週期仍被 coerce 到分時」 | `expected false to be true`(停在 disabled 的「日K」) |
| (b) 寫入拋 | `MarketPane`「加權+分時 → 切台指期:週期仍被 coerce 到 1分」 | `expected false to be true`(停在 disabled 的「分時」) |
| (a) 存取即拋 | `App`「App 仍掛得起來,tab 退回預設『台股綜合』」 | `expected [Function] to not throw an error but DOMException{ stack: 'SecurityError:…' } was thrown` |
| (b) 寫入拋 | `App`「切 tab 不炸,畫面照樣換頁」 | `expected [Function] to not throw an error but DOMException{ stack: 'QuotaExceededE…' } was thrown` |

**過程中修掉一條鑑別力不足的斷言**(先綠 → 改嚴 → 才紅,已記在測試檔註解裡):
MarketPane 寫入側原本寫 `expect(() => fireEvent.click(...)).not.toThrow()` —— 對現況
(裸奔 `setItem`)**一樣綠**,因為 jsdom 的 `dispatchEvent` 會吞掉 listener 例外(轉成
uncaught error 報告)而不是往外拋。改成量「handler 後半段有沒有跑完」才真的紅:
`selectKey` / `selectFut` 都把 `setItem` 排在 `coerceMode` 之前,拋掉的話畫面會停在一顆
**disabled 的週期鈕**上(review P1-5 那個空白畫面組合)。
App 那兩條走 `useEffect` / render body,拋在 commit 階段 RTL 的 `act` 會真的往外拋,
`not.toThrow` 在那裡是真鎖(實測確為紅)。

### 2.2 mutation 驗紅(綠燈到手的鎖)

| # | mutation | 對應鎖 | 結果 |
|---|---|---|---|
| M1 | `if (writeLocal(MAIN_CODE_KEY, legacy)) removeLocal(LEGACY_MAIN_CODE_KEY);` 拆成兩行無條件執行 | W2 遷移順序(`296bd7fd`) | **RED** — `expected null to be '2330'`(舊 key 被刪、新 key 沒寫成 = 主圖標的永久消失) |
| M2 | `writeLocal` 的 `--scope changed` 誤報判定 | react-doctor triage | 反向 mutation:把 `writeLocal(MAIN_CODE_KEY, …)` 換回字面 `window.localStorage.setItem(…)` → finding **消失**;換回來 → finding 再現。誤報成因因此不是猜的 |

還原後 `grep -rn "MUTANT" frontend/src` = **0 行**;`npx vitest run src/App.test.tsx` 53 passed。

### 2.3 沒有 lock 的一條(申報)

**W3「`persistDiscount` 寫失敗不通知訂閱者」寫不出有鑑別力的測試**:訂閱者被通知後會
重讀 storage 拿到**同一個舊值**,而 `useFeeDiscount` 走 `useSyncExternalStore`、
getSnapshot 回 primitive number → React 以 `Object.is` 比對後直接 bail out,連 re-render
都不會發生。也就是「通知 vs 不通知」在畫面與 hook 回傳值上**完全不可觀察**(原始碼註解
說的「白跑一輪」就是它的全部代價)。行為已逐字保留(`if (!writeLocal(...)) return;`),
但這裡不假造一個 vacuous 的鎖。

## 3. 完成前 gate(指令 / 結果 / exit;**無管線後綴**,輸出重導到檔案後再讀,exit code 直讀)

| 指令 | 工作目錄 | 結果 | exit |
|---|---|---|---|
| `npx tsc -b` | frontend/ | 0 error(輸出空) | 0 |
| `npx vitest run` | frontend/ | **147 files / 2776 tests passed**(master:145 / 2759 → **+2 檔 +17 案**) | 0 |
| `npx eslint src` | frontend/ | 0 問題(輸出 0 bytes) | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | frontend/ | 掃 19 檔,**1 finding 且為存量**(`only-export-components` @ `GroupGridView.tsx:72`) | 0 |

**react-doctor 新增 / 存量的判定方式**(`out/doctor-baseline.txt` 已過時,不採信):在同一個
工作樹把兩個被點名的檔換成 master 內容、各補一個空行讓 git 仍視為 changed(不補的話它們
會直接掉出 `--scope changed` 的範圍,量到的是「沒掃到」而不是「沒問題」),再跑一次 —— 
`only-export-components` 照樣出現(**存量**,只是行號由 78 移到 72),
`no-event-handler` 不出現(**新增**)。逐條處置見 §5。

後端 gate 未跑:本輪**零改動**落在 `copycat/`(`git diff --stat master..HEAD` 全部 19 檔皆在
`frontend/src/`),replay / golden 面不受影響。

## 4. 收斂判準 + 白名單逐條核對

### 4.1 grep 判準

```
$ grep -rn "localStorage\.\(get\|set\|remove\)Item" frontend/src --include=*.ts --include=*.tsx \
    | grep -v "lib/storage.ts" | grep -v "\.test\."
(無輸出,exit 1)
```

**0 行** —— 達成。放寬到 `localStorage\.`(含 `.clear()`、屬性存取)同樣 0 行。
測試檔內的 `window.localStorage.clear()` / `setItem` 種資料與 `Storage.prototype` 的 spy
**刻意保留**(它們寫的是真 storage、驗的是同一把 key;改走出口反而讓 lock 量不到真東西)。

未收斂的呼叫點:**0 處**。

### 4.2 白名單核對

| # | 核對方式 | 結果 |
|---|---|---|
| W1 `useState` initializer 只讀一次 | `WatchlistSidebar.test.tsx` StrictMode 自檢(`loadCollapsed` 的 getItem 恰 **2** 次)未改仍綠 | PASS |
| W2 遷移「寫成功才刪舊」 | 三條既有遷移案未改 + 新增 mutation 驗紅的 lock(M1) | PASS |
| W3 `persistDiscount` 寫失敗不通知 | 程式碼逐條保留(`if (!writeLocal(...)) return;`);不可觀察,無 lock(§2.3 申報) | PASS(申報) |
| W4 `setSoundOn` 寫失敗仍通知 | 刻意忽略回傳值 + 註解與 W3 互相指名;`useSignalSound` 既有案未改仍綠 | PASS |
| W5 `fee-discount` 的 `storage` 事件訂閱 | `subscribe` / `listeners` 逐字未動(diff 不含該區塊);既有 6 案未改 | PASS |
| W6 `MarketPane::selectKey` 寫入不可條件化 | `setItem`→`writeLocal` 一對一,順序與條件零改;`MarketPane.test.tsx` 既有案全綠 | PASS |
| W7 `useChartToggles::set` 以重讀的 storage 為 merge 基底 | `load()` 只換讀法,呼叫序不變;既有案全綠 | PASS |
| W8 `v<2` 一次性升級立刻落檔(否則 BB 關不掉) | `persist(upgraded)` 位置不動 | PASS |
| W9 四個測試檔的 `Storage.prototype` spy | `lib/storage.ts` 仍走 `window.localStorage.getItem/setItem/removeItem`;四檔全綠 | PASS |
| W10 `purgeOrphanKeys` 冪等、頂層跑一次 | 呼叫點不變;逐鍵吞的差異已申報(§5) | PASS |
| key 字面值 22 支 | 全部仍由 `lib/constants.ts` 供給,diff 零字面值改動 | PASS |
| 序列化格式 | JSON 三支(toggles / limit filter / 兩個陣列)`JSON.stringify` 參數逐字不變;`"1"/"0"`、`"on"/"off"`、`"overlay"/"side"`、`String(number)` 全不變 | PASS |
| 每個呼叫點的預設值 | change-spec §0.3 十九列逐條對過,判讀規則(白名單 / regex / `isMarketKey` / `clampDiscount`)零改 | PASS |

**事前標「該變」的既有 assertion:0 條**(本輪沒有改動任何既有斷言)。

## 5. 申報:本輪唯一的可觀察差異(review 請看這三條)

1. **失敗時多一則 dev console 警告**(讀 / 寫 / 壞 JSON 各一次,module 級旗標)。
   舊行為 = 已包 try/catch 的 21 處完全靜默、裸奔的 27 處白屏。這是刻意的(鐵則 E:
   不吞成完全靜默),但確實是新的 console 輸出 —— 正常瀏覽器下永不觸發。
2. **`purgeOrphanKeys` 由「整迴圈一個 try」改為逐鍵各自吞**:舊版第一鍵拋就跳過其餘六鍵。
   storage 壞掉時七鍵一樣都清不掉,差別只在多試六次會拋的 no-op,無可觀察後果。
3. **react-doctor 的 inline disable 是全 repo 唯一一處**(`App.tsx` 的 `MAIN_CODE_KEY` effect)。
   選 inline 而不是 `doctor.config.json` 的理由:規則在別處抓得到真東西,關整條會丟掉真訊號。
   選 disable 而不是照規則建議重構的理由:`stockCode` 有多個寫者(自選列 / 圖牆點卡 /
   漲跌停跳轉 / 搜尋),把寫入逐一搬進每個事件處理器**正是 N022 的病灶本身**,而且掛載時
   由存檔還原的那一次回寫會一併消失。理由全文在 `lib/storage.ts` 檔頭。
   (第一版把 7 行理由寫在 App 行內 → 把 App 推過 `no-giant-component` 門檻多冒一條 finding,
   已改成行內一行指標。)

## 6. 留尾(看到但**沒有**在這次動)

1. **測試檔仍直接用 `window.localStorage`**(clear / setItem 種資料 / `Storage.prototype` spy)。
   刻意保留:那是 lock 的量測面,改走出口會讓四條既有 lock 量不到真東西。判準的 grep 也
   已排除測試檔。
2. **`out/doctor-baseline.txt` 仍是 2026-08-11 那份、已過時**(R5 那輪就記過)。本輪的新增
   判定改以「同一分支上把檔換成 master 內容再跑一次」為準(§3)。要不要重錄基線由 user 決定。
3. **`useChartToggles` 每個呼叫端各持一份 state、靠重讀 storage 當 merge 基底**:N022 沒有
   動這個設計(它是既有的跨元件同步手法)。要不要像 `fee-discount` 那樣改走
   `useSyncExternalStore` 是另一個題目。
4. **`GroupGridView.tsx` 的 `only-export-components` 存量 finding** 仍在(`gridShape` 是非元件
   export)。與本輪無關,未順手改(Scope 紀律)。
5. **`no-event-handler` 對 `writeLocal` 的誤報是上游規則的能力邊界**:日後別的 effect 用
   `writeLocal` 會再撞一次。`lib/storage.ts` 檔頭已寫明「先回來看這段,別直接把規則寫進
   doctor.config.json」。要不要對上游開 issue 由 user 決定。

## 7. 需要 user 過目(真環境;屬 user 端,本 session 做不到)

- **Safari 私密視窗**:本輪的主要動機。開站後應該**看得到畫面**(而不是白屏),偏好設定
  一律走預設值(tab = 台股綜合、標的 = 加權、週期 = 分時、圖表模式 = 江波圖、提示音 = 開),
  console 有 `storage: localStorage 讀取失敗…` 一則(**只有一則**)。
  切 tab / 切標的 / 切週期都要能動,只是重開回到預設。
- **企業政策鎖 storage**(Chrome/Edge 的 `DefaultLocalStorageSetting=2` 之類):同上。
- **配額滿**(較難人為構造):寫入失敗時操作本身要照常生效,console 有
  `storage: localStorage 寫入失敗…` 一則。
- **正常瀏覽器的回歸抽查**(最重要的一條):既有偏好設定必須**照舊還原** —— 舊瀏覽器裡
  已存的 22 支 key 全部沒有格式改動,重開站時 tab / 主圖標的 / 期貨商品 / 左右圖標的與
  週期 / 右欄 tab / 圖表模式 / 疊線開關 / 自選折疊 / 群組檢視 / 漲跌停篩選 / 折數 /
  提示音 / 江波圖腿位,應與這次改動前**逐項相同**;console 應**零** `storage:` 警告。
