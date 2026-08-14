# current-state — mod/overview-subtabs-breadth-colors

日期:2026-08-14。Baseline:frontend `npm test` 全綠(114 files / 1894 tests,exit 0)。
範圍:純 frontend,後端零觸及。

## 任務兩件事

1. **BreadthBand 家數配色**(user 已拍板):上漲數字 `text-bull`、下跌 `text-bear`、
   平盤中性;停板兩格底色與 ink 數字不動;不給上漲/下跌加底色。
2. **四個展開區塊改 subtab**:LimitListSection / SectorSection / SignalTimelineSection /
   CorrSection 收進一列 subtab,一次只掛載一個;上方常駐區不動;新 localStorage key 記住
   上次選的 subtab;原四個 `*_OPEN_KEY` 廢止。

## 現況:BreadthBand(frontend/src/components/index/BreadthBand.tsx)

- 檔頭 6-8 行設計理由:「染色只落在格底(漲停紅底/跌停綠底),數字一律 ink token —
  紅底上的紅字在暗色盤面幾乎讀不出來;中間三格保持中性 — 五格全染等於沒有重點」。
- `BUCKETS` 常數(L17-23):每格 `{ key, label, tone }`,tone 只給格底與框線;
  limit_up = `border-bull/40 bg-bull/15`、limit_down = `border-bear/40 bg-bear/15`、
  中間三格 null(`border-line bg-surface` fallback 在 L88)。
- 數字 span(L92-95):一律 `font-mono text-sm text-ink`,testid `breadth-value-<mkt>-<bucket>`。
- 純展示元件,props 只有 `breadth`;caller 僅 IndexPage.tsx L138。
- 測試 BreadthBand.test.tsx:(f) 驗停板格底色 + 中間三格無 bg;(g) 驗 **limit_up 數字**
  text-ink 且無 text-bull — **兩者在新行為下仍然成立**(上漲/下跌數字現況無任何測試斷言字色)。

## 現況:四個收合區塊

### 共同殼型(四檔同構)

每檔尾端「收合殼」:`useState(() => try { localStorage.getItem(KEY) === "1" } catch { false })`
(Safari 私密視窗 initializer 防白屏慣例)+ `toggle()` 寫回 "1"/"0"(try/catch)+
`<section data-testid=...><button aria-expanded>標題 + 展開/收合</button>{open ? <Body/> : null}</section>`。
**收合 = unmount 不是 hidden**:body 一 unmount,輪詢 query / WS 隨之消失(省流量的核心設計)。

| 區塊 | 檔案(殼行號) | testid | 標題 | body | active gate |
|---|---|---|---|---|---|
| 漲跌停 | index/LimitListSection.tsx L479-522 | `limit-list` | 漲跌停 | `LimitListBody`(useBreadthRows 10s 輪詢)| 有(`active` prop → hook)|
| 類股強弱 | index/SectorSection.tsx L425-468 | `sector-section` | 類股強弱 | `SectorBody`(輪動快照 10s 輪詢 + FE-7 排序凍結 + 鑽取)| 有 |
| 訊號時間軸 | index/SignalTimelineSection.tsx L177-214 | `signal-timeline` | 訊號時間軸 | `TimelineBody`(一次性 query + WS bus)| **無**(檔頭註明:沒有輪詢可停)|
| 相關係數 | corr/CorrSection.tsx(全檔)| 無 testid(靠 button name)| 相關係數 | `React.lazy(CorrPage)` + Suspense(corr + river 兩條 WS)| 無(WS 推播)|

- `active` prop 語意(LimitList/Sector):App 以 `hidden` 保留 tab DOM → 「展開著被切走」
  是常態,靠 `active`(App 的 `tab === "index"`)停背景輪詢(review FE-2)。IndexPage 往下傳。
- CorrSection 的 lazy chunk 邊界:`lazy(() => import("@/components/corr/CorrPage"))` 在
  CorrSection 檔內;Suspense fallback 文字「相關係數載入中…」刻意與 CorrPanel 空狀態區分。

### localStorage keys(frontend/src/lib/constants.ts)

- 廢止對象:`CORR_OPEN_KEY`(L65 "copycat-corr-open")/ `LIMIT_LIST_OPEN_KEY`(L69
  "copycat-limit-list-open")/ `SECTOR_OPEN_KEY`(L76 "copycat-sector-open")/
  `SIGNAL_TIMELINE_OPEN_KEY`(L81 "copycat-signal-timeline-open")。
- 孤兒鍵慣例已存在:`ORPHAN_STORAGE_KEYS`(L21,現值 stock-ladder-open / stock-wl-group)
  + `purgeOrphanKeys()`(L29,App.tsx module scope L90 呼叫一次,整段 try/catch)。
- `LIMIT_LIST_FILTER_KEY`(L72)是篩選條件,**不在廢止範圍**。
- subtab 選中值持久化的既有樣板:RightRail.tsx `initialTab()`(L34-37)— getItem 後
  白名單比對,不合法 fallback 預設。注意 RightRail 的 initializer **沒包 try/catch**
  (它不是本任務範圍);本頁四殼與 useChartToggles 的 try/catch 慣例才是要照抄的。

### Caller map(grep 全量,含測試)

**IndexPage.tsx**(唯一 production caller):L143 LimitListSection / L146 SectorSection /
L150 SignalTimelineSection / L151 CorrSection,依序排在騰落線 section 之後。
上方常駐區:BasisRow(L109)→ 雙 MarketPane grid(L111-134)→ BreadthBand +
AdvanceDeclineChart section(L137-140)。IndexPage 已有狀態:`useChartToggles`(L105)。

**測試 caller**:
- `IndexPage.test.tsx`:describe (e)(e2) 相關係數預設收合/落點、(g)(g2) 漲跌停預設收合/
  落點、(h)(h2) 類股、(i)(i2) 時間軸 — 全部靠 `getByRole("button", { name })` +
  `aria-expanded` + `compareDocumentPosition` 驗序。
- `LimitListSection.test.tsx`:「收合閘門」describe(L116-149)3 條;body 測試一律
  `localStorage.setItem(LIMIT_LIST_OPEN_KEY, "1")` 開場(`openWith` helper L84-93、
  FE-2 gate describe L154-178、HTTP 失敗 L208)。
- `SectorSection.test.tsx`:同款收合閘門 + body 測試 setItem 開場(L98/110/144/160/266/363/540/590/604)。
- `SignalTimelineSection.test.tsx`:同款(L70/113/129/337)。
- `CorrSection.test.tsx`:殼閘門 3 條(stub CorrPage 計 mount/unmount);
  `CorrSection.lazy.test.tsx`:lazy 真身 2 條(FakeWS 驗展開建線/收合斷線)。
- `App.test.tsx`:**raw 字面值** seed 舊 key(不是 import 常數):L229/259
  "copycat-limit-list-open"、L308/365 "copycat-sector-open"、L319
  "copycat-signal-timeline-open" — 跳轉全鏈與 active-gate 全鏈測試的開場;
  L215-218 nav 無「相關係數」tab;L593 `purgeOrphanKeys` 單元測。
- `fut-chart-mode.test.ts` L82-86:斷言 FUT_CHART_MODE_KEY **不在** ORPHAN_STORAGE_KEYS
  (加四個新孤兒鍵不影響)。
- 動態用法查證:grep `getItem|setItem` 全量比對過,四支 OPEN_KEY 無字串字面值旁路
  (App.test.tsx 的 raw 字串是唯一字面值使用點)。

## 現況 vs 目標

| 面向 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| BreadthBand 數字色 | 十格全 `text-ink` | 上漲 `text-bull`/下跌 `text-bear`/停板+平盤 ink | 無(props 不變) | 無(純視覺) |
| 四區塊呈現 | 各自收合殼、可同時展開 0-4 個 | 一列 subtab,恆一個掛載 | IndexPage 改組裝;四殼元件卸掉收合邏輯 | localStorage 舊 key 廢止 → 孤兒清單 purge;使用者展開偏好不遷移(見 change-spec) |
| unmount 省輪詢 | 收合 = unmount | 非 active subtab = unmount(語意等價保留) | 無 | — |
| active gate | LimitList/Sector 接 `active` | 不變 | 無 | — |
| localStorage | 四支 OPEN_KEY | 一支新 key(白名單還原 + try/catch)| constants.ts 增刪 | 舊 key 進 ORPHAN_STORAGE_KEYS |

## 風險與既有意圖(不可誤傷)

- CorrSection 的 lazy chunk 邊界與 Suspense fallback 文字鑑別度(兩個測試檔依賴)。
- SectorBody 的 FE-7 排序凍結 + 鑽取邏輯:**完全不動**(殼以下零觸及)。
- TimelineBody 無 active gate 是刻意的(一次性 query + WS bus)。
- 四殼 + 新 initializer 的 Safari try/catch 防白屏慣例。
- IndexPage 落點測試以 DOM 順序驗證常駐區 → subtab 區的相對位置。
