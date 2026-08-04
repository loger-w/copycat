# refactor-plan — frontend-localstorage-keys(2026-08-04)

## Phase 1|Why

next-time 三處條目(2026-07-28 key 無統一前綴 + 集中管理、2026-07-29 stock-ladder-open
停用未清、2026-07-30 stock-wl-group 同類)。key 散在 8 個檔各自宣告,每輪 UI 功能都在
長新 key,無單一清單可對照(孤兒鍵就是這樣漏掉的);`stock-main-code` 是唯一漏前綴的,
與他站 localStorage 撞名風險 + 清 site data 對照困難。為什麼是現在:user 排程 3 輪
清尾款之三,且上兩輪(rail tab / river keys)又各新增 key,再拖清單更長。

## 行為邊界

- 全部 key **值不變**(除 stock-main-code 改名,由一次性 migration 保障使用者偏好不失)。
- 測試側字面值**一律保留**(它們是「集中後 key 值沒被改到」的守護網);僅 source 改 import。
- migration 與孤兒清除是改名的行為保全配套(user 指定),對使用者可見行為零差異。

## 步驟

### Step A(🔵)key 集中到 lib/constants.ts
新建 `frontend/src/lib/constants.ts`:14 個 storage key 以既有常數名風格 export
(如 `TAB_KEY` / `MAIN_CODE_KEY` / `MARKET_KEY_STORE` …,同名衝突時帶模組語意前綴),
每個 key 一行註解記用途與宿主元件。8 個 source 檔刪 local const 改 import;
**key 值一字不改**(stock-main-code 本步仍是舊值)。測試檔不動。
預估 diff ~80 行 / 9 檔。

### Step B(🔵)stock-main-code 改名 + migration + 孤兒清除
- `constants.ts`:`MAIN_CODE_KEY` 值改 `"copycat-stock-main-code"`,新增
  `LEGACY_MAIN_CODE_KEY = "stock-main-code"` 與孤兒鍵清單
  `ORPHAN_STORAGE_KEYS = ["stock-ladder-open", "stock-wl-group"]`。
- `App.tsx`:主圖股票初始化改「新 key 有值即用;否則讀舊 key,有值 → 寫新 + removeItem
  舊 → 回傳」;module 掛載時對孤兒鍵 removeItem(一次性,冪等)。
- 既有 App.test 202/211(舊字面值 setItem)不改 —— 改名後必須仍綠 = 遷移保護網。
預估 diff ~40 行 / 2 檔。

### Step C(🟢)migration / 清除測試
App.test 補:新 key 優先於舊 key;舊值遷移後寫入新 key 且舊 key 被移除;
孤兒鍵啟動後不存在。預估 diff ~40 行 / 1 檔。

### Step D|收尾
next-time 三處條目打勾;Phase 5 blast radius(grep 舊字面值殘留 — 測試檔的刻意保留除外);
gate:npm test + tsc + eslint + check_feat_tags。

## 風險註記

- migration 對「新舊 key 同時有值且不同」取新值(新 key 只可能由新版寫入,語意正確)。
- 孤兒 removeItem 冪等,對不存在的 key 是 no-op;jsdom 同樣支援。
- WatchlistSidebar.test / useChartToggles.test 自持字面值 const —— 不改,與 source
  import 並存即是雙重釘死。
