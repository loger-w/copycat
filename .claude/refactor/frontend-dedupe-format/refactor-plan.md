# refactor-plan — frontend-dedupe-format(2026-08-04)

## Phase 1|Why

`docs/next-time.md`「2026-08-03(stock-page-dedupe-deadcode)範圍外遺留」記錄的三組
duplication:同一格式字串 / 同一解析函式散在 6+ 檔,任何格式調整(如 next-time 已記的
「% 旁加漲跌額」)要同步 6 處必漂移。lib/format.ts 與 lib/api-error.ts 的單一版**已存在
且已有 8 個消費檔**,本輪純粹把殘餘的 local 副本指回去。為什麼是現在:user 排程指定
(3 輪清尾款之二),且上一輪(stock-page refactor)已把 lib 版鋪好,增量最小。

## 行為零改變邊界

- `CapitalPositionsList.tsx:79`(`>= 0`)不動,記 next-time。
- `CandleChart` 期間/跨日漲跌 = 語意變體,不動。
- `IndexBar.tsx` local `fmt`(實作與 lib 版不同)不動。
- `RiverCards.tsx` local `fmtPrice` 非重複(millipts→兩位小數固定),不動。

## 步驟(每步單獨綠 + 單獨 commit)

### Step 0(🟢 characterization,獨立 commit)
拍下三個未覆蓋站點的當前輸出:
1. `IndexBar.test.tsx` 補正號 case(chg > 0 → `+x.xx%` 前綴)。
2. `IndexPage.test.tsx` 補 Quote 漲跌字串斷言(`±pts.xx (±pct.xx%)` 整串,含正號)。
3. `RiverPanel.test.tsx` 補重疊模式 pct 軸標籤斷言(fixture 實跑後把值釘死)。
預估 diff < 60 行。

### Step A(🔵)parseError 收斂
- `lib/api-error.ts`:抽 `parseErrorDetail(res): Promise<ErrorDetail>`(detail 物件或
  `{}`,never-raise),`parseError` 改為其上的一層;`ErrorDetail` 含
  `error?/reason?/err_code?`(capital 擴充欄位)。
- `hooks/useSeries.ts`:刪 local `parseError`(與 lib 逐字相同),改 import。
- `hooks/useCapital.ts`:`parseCapitalError` 改吃 `parseErrorDetail`,只留 suffix 邏輯。
  export 不變(`useCapital.test` 直接 import 它)。
預估 diff ~50 行。

### Step B(🔵)fmtPct / chgPct 收斂
- `IndexBar.tsx`:local `chgPct(s)` body 委派 `lib` 版(null/0 gate 保留);:26 行內
  字串改 `fmtPct(chg)`。
- `IndexPage.tsx` Quote:`chgPct` 局部變數改名(避免 shadow lib import),計算改
  `chgPct(p, ref_)`(gate `ref_` truthy 保留),:186 pct 段改 `fmtPct(...)`(pts 段
  無 `%`,非 fmtPct,保留行內)。
- `FuturesPage.tsx:60`:行內改 `fmtPct(chg)`。
- `RiverCards.tsx` / `RiverOverlay.tsx`:刪 local `fmtPct`,改 import `@/lib/format`。
- `lib/signal-model.ts:78`:改 `fmtPct(sig.pct)`(import `./format`)。
預估 diff ~60 行。

### Step C|收尾
- next-time:CapitalPositionsList `>= 0` 差異記錄 + 來源條目劃掉(a)(b)(c) 已做部分。
- Phase 5 blast radius:grep 被刪符號(local parseError / fmtPct)零殘留;
  `chgPct` shadow 檢查。
- Phase 6:npm test + npx tsc -b + npx eslint src 全綠(backend 未動,pytest 不必跑;
  但收尾 gate 照 auto-verify 慣例全套跑一次)。

## 風險註記

- `fmtPct(0)` = `"0.00%"`(無正號)— 與各行內版 `v > 0` 判斷一致,零差異。
- `chgPct` lib 版無 null gate — 各呼叫端 gate 原樣保留在呼叫端(與現況相同語意)。
- Step A 的 `parseErrorDetail` 是**新 export**(加法),不動既有 `parseError` 簽名。
