# R9a 全站 localStorage 收斂(`mod/storage-consolidation`)— change spec

來源:`docs/superpowers/specs/2026-08-24-do-batch-rounds.md` §R9 **N022**。
承接 2026-08-06「`MarketPane.tsx` 七個 localStorage 呼叫點裸奔」與 2026-08-21 R10
「C8 storage 移出升 /mod」兩條舊帳,一併帶走。

**前置 grep(2026-08-25 重跑)**:`grep -rn "localStorage\." frontend/src`(去掉測試檔)
= **48 個呼叫點 / 14 個檔**(spec 記 45 處,差在多行 `setItem` 與 `removeItem` 的計法)。
其中 **27 處裸奔**(沒有任何 try/catch)、21 處各自抄了一份語意相同的 try/catch。
`lib/storage.ts` **grep 過不存在**(R10 那條只是記在 next-time,沒實作)→ 本輪新建。

---

## 0. 既有行為白名單(不可破壞;優先於本輪新行為)

### 0.1 caller map(含動態用法與測試面)

| 對象 | 讀者 / 寫者 |
|---|---|
| `Storage.prototype.getItem/setItem` 的 `vi.spyOn` | **4 個測試檔**:`IndexPage.test.tsx`(l2 零 subtab 鍵讀寫)、`LimitListSection.test.tsx`(零 OPEN_KEY 讀寫)、`WatchlistSidebar.test.tsx`(StrictMode 生效自檢 = `loadCollapsed` 讀**兩次**)、`fee-discount.test.ts`(getItem 拋 → 預設)。**全部靠 prototype 上的 spy** → `lib/storage.ts` 必須仍呼叫 `window.localStorage.getItem/setItem`,不可換成別的存取路徑,否則四條 lock 全部靜默轉 vacuous |
| `window.localStorage.clear()` / `.setItem()` 的直接使用 | 大量測試檔的 `beforeEach` 種資料;**本輪不動測試檔的 storage 慣例**(它們寫的是真 storage,讀的是同一把 key) |
| `purgeOrphanKeys()` | `App.tsx` module scope 呼叫一次 + `App.test.tsx` 直呼 |
| `readStockView()` | `App.tsx`(與 `StockPage` 共用同一份初值判讀) |
| `loadDiscount` / `persistDiscount` / `useFeeDiscount` | 閃電梯 + 自選列 + header + 群組卡(`storage` 事件 + module 級 listener 兩條通知路徑) |
| `getSoundOn` / `setSoundOn` | `SignalRail`(切換)+ `useSignalAlerts`(發聲端),`useSyncExternalStore` |
| `initialFutChartMode` / `persistFutChartMode` | `FuturesChart` + `FuturesChart.test.tsx`(直接讀 `FUT_CHART_MODE_KEY` 斷言字面值) |

### 0.2 key 字面值表(**逐字不變**;來源 `lib/constants.ts`,唯一宣告處)

| 常數 | 字面值 | 序列化格式 | 呼叫點 |
|---|---|---|---|
| `TAB_KEY` | `copycat-tab` | 純字串 | App |
| `MAIN_CODE_KEY` | `copycat-stock-main-code` | 純字串 | App |
| `LEGACY_MAIN_CODE_KEY` | `stock-main-code` | 純字串(唯一漏前綴) | App(一次性遷移) |
| `PRODUCT_KEY` | `copycat-fut-product` | 純字串 | App |
| `FUT_CHART_MODE_KEY` | `copycat-fut-chart-mode` | 純字串 | fut-chart-mode |
| `MARKET_KEY_STORE` / `MARKET2_KEY_STORE` | `copycat-market-key` / `copycat-market2-key` | 純字串 | MarketPane(`stores.key`) |
| `MARKET_MODE_STORE` / `MARKET2_MODE_STORE` | `copycat-market-tf` / `copycat-market2-tf` | 純字串 | MarketPane(`stores.mode`) |
| `MARKET_FUT_STORE` / `MARKET2_FUT_STORE` | `copycat-market-fut` / `copycat-market2-fut` | 純字串 | MarketPane(`stores.fut`) |
| `INDEX_OVERLAY_STORE` | `copycat-index-mode` | 字串 `"overlay"` / `"side"` | MarketPane(`stores.overlay`,optional) |
| `LIMIT_LIST_FILTER_KEY` | `copycat-limit-list-filter` | **JSON 物件**(8 欄) | LimitListSection |
| `RAIL_TAB_KEY` | `copycat-rail-tab` | 純字串 | RightRail |
| `CHART_MODE_KEY` | `copycat-chart-mode` | 純字串 | StockChart |
| `CHART_TOGGLES_KEY` | `copycat-chart-toggles` | **JSON 物件 + `v` 版本欄** | useChartToggles |
| `WL_COLLAPSED_KEY` | `copycat-stock-wl-collapsed` | **JSON 字串陣列** | WatchlistSidebar |
| `WL_UNGROUPED_KEY` | `copycat-stock-wl-ungrouped-collapsed` | 字串 `"1"` / `"0"` | WatchlistSidebar |
| `STOCK_VIEW_KEY` | `copycat-stock-view` | 純字串 | StockPage(寫)/ stock-view(讀) |
| `STOCK_GROUP_KEY` | `copycat-stock-group` | 純字串 | GroupGridView |
| `SOUND_KEY` | `copycat-signal-sound` | 字串 `"on"` / `"off"` | useSignalSound |
| `FEE_DISCOUNT_KEY` | `copycat-fee-discount` | `String(number)` | fee-discount |
| `RIVER_MODE_KEY` | `copycat-river-mode` | 純字串 | RiverPanel |
| `RIVER_OFF_KEY` | `copycat-river-legs` | **JSON 字串陣列** | RiverPanel |
| `ORPHAN_STORAGE_KEYS`(7 支) | 見 constants.ts | — | purgeOrphanKeys(只 remove) |

### 0.3 預設值表(讀不到 / 壞值時的落點,**逐一不變**)

| 呼叫點 | 預設 | 判讀規則 |
|---|---|---|
| `App::initialTab` | `"index"` | 白名單 `stock/futures/txo/corr`,其餘皆 index |
| `App::initialProduct` | `"TXF"` | 只認 `MXF` / `TMF` |
| `App::initialStockCode` | `null` | 新 key 優先;只有舊 key 才遷移 |
| `MarketPane` futKey | `"TXF"` | 只認 `MXF` / `TMF` |
| `MarketPane` marketKey | `defaultKey`(prop) | `isMarketKey` |
| `MarketPane` mode | `coerceMode(key, "intraday")` | key 的 fallback **同源 `defaultKey`** |
| `MarketPane` overlay | `false` | 無 overlay key ⇒ 恆關;舊值 `"overlay"` 讀時遷移為布林 |
| `RightRail::initialTab` | `"flash"` | 只認 `orders` / `positions` |
| `StockChart::initialMode` | `"intraday"` | regex `^(intraday\|day\|m([1-9]\|10))$` |
| `fut-chart-mode` | `"intraday"` | `isFutChartMode`(由 `FUT_CHART_MODES` 推導) |
| `stock-view` | `"single"` | 只認 `"group"` |
| `GroupGridView` | `null` | 原樣回字串 |
| `LimitListSection` | `DEFAULT_FILTER` | 逐欄 `pickBool` / `pickText` |
| `useChartToggles` | `DEFAULTS` + `{...DEFAULTS,...flags}` + `v<2` 一次性升 `bb` | 形狀檢查不可省 |
| `WatchlistSidebar` collapsed | `new Set()` | 只收字串元素 |
| `WatchlistSidebar` ungrouped | `false` | 只認 `"1"` |
| `useSignalSound` | `true`(開) | `!== "off"` |
| `fee-discount` | `FEE_DISCOUNT_DEFAULT` | `clampDiscount(raw ?? "")` |
| `RiverPanel` mode / off | `"side"` / `[]` | 只認 `"overlay"`;off 只收字串元素 |

### 0.4 不可破壞的語意(W 表)

| # | 既有行為 | 守住的方式 |
|---|---|---|
| W1 | **`useState` lazy initializer 只讀一次**的語意 | 讀取一律仍在 initializer 內同步呼叫;`WatchlistSidebar.test.tsx` 的 StrictMode 自檢(`loadCollapsed` 讀 **2** 次)不改仍綠 |
| W2 | **App 舊 key 遷移:`setItem` 成功才 `removeItem`** | `writeLocal` 回傳布林,`if (writeLocal(...)) removeLocal(...)`。寫失敗還刪舊 key = 弄丟使用者的主圖標的;三條既有遷移測試不改 |
| W3 | **`fee-discount::persistDiscount` 寫失敗不通知訂閱者** | 同上布林:`if (!writeLocal(...)) return;`。通知了只會讓訂閱者再讀一次舊值 |
| W4 | **`useSignalSound::setSoundOn` 寫失敗仍通知**(與 W3 刻意相反) | 刻意忽略回傳值,註解互相指名 |
| W5 | `fee-discount` 的 `storage` 事件監聽 + module 級 listener 集合 | 完全不碰(`subscribe` / `listeners` 逐字未動) |
| W6 | `MarketPane::selectKey` 的「**寫入不可條件化**」(任何標的切換都沖成當下有效值) | `setItem`→`writeLocal` 一對一,順序與條件零改 |
| W7 | `useChartToggles::set` 的「merge 基底是**重讀的 localStorage**」 | `load()` 內部換讀法,呼叫序不變 |
| W8 | `useChartToggles` 的 `v<2` 一次性升級**必須立刻落檔**(否則 BB 關不掉) | `persist(upgraded)` 位置不動 |
| W9 | 四個測試檔對 `Storage.prototype` 的 spy | `lib/storage.ts` 仍走 `window.localStorage.getItem/setItem/removeItem` |
| W10 | `purgeOrphanKeys` 冪等、在 App module 頂層跑一次 | 呼叫點與冪等性不變(逐鍵吞的差異見 §2) |

---

## 1. 處置

### 1.1 新檔 `frontend/src/lib/storage.ts`(唯一出口)

```ts
readLocal(key: string): string | null          // 讀失敗 = 沒設過,同一條退路
writeLocal(key: string, value: string): boolean // true = 真的落檔了
removeLocal(key: string): boolean
readLocalJson(key: string): unknown             // 未設 / 空字串 / 壞 JSON / 存取即拋 → null
```

判定型決定(逐條寫明理由,交 review):

1. **`writeLocal` / `removeLocal` 回布林而不是 `void`** —— 有兩個呼叫端要分辨成敗(W2 / W3)。
   回 `void` 的話那兩條語意只能各自再抄一份 try/catch,等於沒收斂。
2. **`readLocal` 讀失敗回 `null` 而不是丟出可辨識的錯誤** —— 18 個呼叫點的處理方式**全部**是
   「退預設」,分辨「沒設過」與「讀不到」對它們沒有任何用處,而多一個分支就是多一條沒人走的路。
3. **加 `readLocalJson`,不加 `writeLocalJson`** —— 讀側有 4 個呼叫點各自抄「try 包住 getItem +
   JSON.parse」(壞 JSON 與存取失敗要收成同一個退路);寫側 `writeLocal(k, JSON.stringify(v))`
   已經一行,包一層只是多一個名字。API 面越小越好。
4. **`readLocalJson` 回 `unknown` 不回泛型 `T`** —— 存進去的是使用者瀏覽器裡的舊資料,
   `as T` 會讓「schema 變了」這件事在型別上消失。四個呼叫點本來就各自驗形狀,原樣保留。
5. **警告 module 級只發一次,讀 / 寫 / 壞 JSON 三個旗標各自獨立** —— 完全靜默違反鐵則 E;
   每次都印會把 console 洗掉(讀取端住在 render 路徑上)。三個旗標分開是因為它們是不同故障
   (政策鎖 vs 配額滿 vs 資料壞),共用一個會讓先發生的把另一個永久靜音。
6. **不做 in-memory fallback** —— 寫不進去就是這次不記住。假裝成功會讓「同分頁看起來記住了、
   重開就沒了」比乾脆不記住更難解釋,而且多一份與 storage 不同步的真相。
7. **本檔不 import `lib/constants.ts`** —— 出口不該知道有哪些鍵;方向是 `constants.ts` →
   `storage.ts`(`purgeOrphanKeys` 用 `removeLocal`),單向無環。

### 1.2 呼叫點搬家(48 → 0)

| commit 類 | 檔 | 處數 | 行為 |
|---|---|---|---|
| 🔴 | `App.tsx` | 7 讀寫 + 3 已包 | 裸奔的 7 處由「拋」變「退預設 / 不落檔」;遷移順序改由 `writeLocal` 布林表達(W2) |
| 🔴 | `MarketPane.tsx` | 10 | 同上(四個 initializer + 五個 handler) |
| 🔴 | `RiverPanel.tsx` | 3 裸 + 1 已包 | 同上;`initialOff` 併入 `readLocalJson` |
| 🔴 | `RightRail.tsx` | 3 | 同上 |
| 🔴 | `StockChart.tsx` | 2 | 同上 |
| 🔴 | `WatchlistSidebar.tsx` | 2 裸(persist ×2) | 同上 |
| 🔵 | `constants.ts` / `stock-view.ts` / `fut-chart-mode.ts` / `fee-discount.ts` / `useSignalSound.ts` / `useChartToggles.ts` / `LimitListSection.tsx` / `GroupGridView.tsx` / `StockPage.tsx` / `WatchlistSidebar.tsx`(loaders) | 21 | 逐字同行為,只是把各自那份 try/catch 換成出口 |

### 1.3 react-doctor 誤報 triage(第 4 個 commit)

收斂後 `--scope changed` 多出一條 `no-event-handler`(`App.tsx` 的 `MAIN_CODE_KEY` effect)。
**實測證據**:同一個 effect 把 `writeLocal(...)` 換回字面 `window.localStorage.setItem(...)`,
finding 立刻消失 → 規則把「字面上的 localStorage 成員呼叫」認成合法的 external-store 同步,
看不穿一層具名函式。處置 = **只關那一行**(inline `react-doctor-disable-next-line`),
不動 `doctor.config.json`。規則建議的「搬進事件處理器」在這裡是反向的:`stockCode` 有多個
寫者,逐一補一份寫入正是 N022 的病灶,且掛載時由存檔還原的那一次回寫會消失。
理由全文落在 `lib/storage.ts` 檔頭(行內只留指標 —— 第一版把 7 行理由寫在 App 裡,
反而把 App 推過 `no-giant-component` 門檻多冒一條 finding)。

---

## 2. Backward compat / migration

- **零 storage 格式改動**:key 字面值、序列化格式、值域判讀規則全部逐字沿用(§0.2 / §0.3)。
  舊瀏覽器裡已存的資料照讀,**不需要任何遷移碼**;`App` 的 `stock-main-code` → `copycat-stock-main-code`
  一次性遷移仍在,只是條件從 try/catch 改成布林。
- **零 API 契約改動**、零後端改動(本輪不動 `copycat/`)。
- 唯一的可觀察差異(申報,見 §3 verification):
  1. 失敗時多一則 **dev console 警告**(每種故障一次)。舊行為是完全靜默(已包的 21 處)或白屏(裸奔的 27 處)。
  2. `purgeOrphanKeys` 由「整迴圈一個 try」改為**逐鍵各自吞** —— 舊版第一鍵拋就跳過其餘六鍵。
     storage 壞掉時七鍵一樣都清不掉,差別只在多試六次會拋的 no-op,無可觀察後果。
- 可逆 = revert 本分支;`lib/storage.ts` 是新檔,48 個呼叫點的舊寫法都在 git 歷史內。

---

## 3. 測試 seams(皆為真 caller 走的 seam)

- **純函式**:`src/lib/storage.test.ts`(新;11 案)—— 讀 / 寫 / 刪 / JSON 四支的成功與失敗態、
  警告只發一次且讀寫旗標獨立。用 `vi.resetModules()` + 動態 import 拿乾淨的 module 級旗標
  (**不加 test-only 的 reset export**;沿用同一份 module 的話第二個 it 起恆不警告,斷言會靜默轉 vacuous)。
- **元件(a)存取即拋**:`MarketPane.storage.test.tsx`(新)+ `App.test.tsx`(既有檔加一案)。
  挑 MarketPane 是因為它呼叫點最密(10 處)且四個 initializer 全在 render 路徑上;
  挑 App 是因為它是「整站白屏」的那一層(連帶蓋到 `RightRail::initialTab`)。
- **元件(b)寫入拋 QuotaExceededError**:同兩檔。
  **斷言刻意不用 `expect(fireEvent.click(...)).not.toThrow()`** —— jsdom 的 `dispatchEvent`
  會吞掉 listener 例外,那條對現況(裸奔 setItem)一樣綠、是假的鎖(第一版寫成那樣,實測綠 → 改掉)。
  改量「handler 後半段有沒有跑完」:`selectKey` / `selectFut` 都把 `setItem` 排在 `coerceMode`
  之前,拋掉的話畫面停在一顆 **disabled 的週期鈕**上(P1-5 那個空白畫面組合)。
  App 那一條走 `useEffect`,拋在 commit 階段 RTL 的 `act` 會真的往外拋 → `not.toThrow` 在那裡是真鎖。
- **既有 assertion 零改動**(沒有任何一條事前標「該變」)。
