# Change Spec — 個股頁現價醒目化(mod/stock-price-prominence)

## 分流判定

user 帶已成形改法(「個股現價要明顯一點」— 目標單一、範圍明確 = 個股頁 header 現價),
命中 feat-phase0-2 判準「目標與落點皆可指認」→ grilling 確認路線,無方向性抉擇
(字級 / 字重的候選互換不影響 SC 集合、out of scope、對外契約)→ 依 /auto 契約推進。

`[auto-default: 現價 text-lg → text-3xl + font-semibold;漲跌 % text-xs → text-sm |
reason: 現況現價與股名同字級且更輕(股名有 bold),放大 2 級 + 半粗即成為 header 唯一
視覺焦點;text-3xl 為 rem utility 吃全站字級縮放,不違反 px-literal 禁令;不加漲跌額、
不動顏色語意,最小可逆改動]`

## 成功條件(畫面可指認)

- SC-1:個股頁 header 中,現價數字(股名右側、`page-quote` 區塊)字級**明顯大於股名**
  (現價 `text-3xl` ≈ 1.875rem vs 股名 `text-lg` = 1.125rem),字重 `font-semibold`,
  一眼即為整列最醒目元素。量法:截圖對照 + className 斷言。
- SC-2:漲跌 % 同步放大一級為 `text-sm`(原 `text-xs`),仍緊貼現價右側同色。
  `[amendment 2026-08-04: P2-2 — 非「等比」;主數字/% 比例刻意從 1.5× 拉大到 2.14×,
  讓現價成為唯一焦點]`
- SC-3:三態(漲停反白 / 跌停反白 / 未觸價文字色)的底色與文字色 **class 集合與改前
  完全相同**,截圖對照確認語意一致(只有字級變大)。
  `[amendment 2026-08-04: P2-1 — 原「逐像素同語意」不可判定,改為 class 集合斷言 +
  截圖對照;反白塊 `px-1.5` 刻意不動(字高變大後底色塊變高屬預期,見白名單 8)]`
- SC-4:窄寬度(1280px)與預設寬度各一張截圖:header 維持單列(總量/昨量不被擠到
  第二列)、圖表未出現 `<main>` 捲軸。
  `[amendment 2026-08-04: P1-1 — 字級放大對 flex-wrap 換行門檻與圖表可用高度的
  版面回歸,jsdom 全盲,必須截圖驗]`

## 不能破壞的既有行為白名單

1. 漲停 → `page-quote` 整塊 `bg-bull` + `text-white` 反白(含 % 一起反白)。
2. 跌停 → `bg-bear` + `text-white`。
3. 未觸價 → 依 chg 正負 `text-bull` / `text-bear` / `text-ink`,無底色。
4. `font-mono` 數字字體保留。
5. `last === null` 時 quote 區塊不渲染;`chg == null` 時不渲染 %。
6. header 同列其他元素(股名/代號、無資料/回補中 badge、股期價差、加入自選、
   總量/昨量)內容與樣式不動;`items-baseline` 對齊行為保留。
   `[amendment 2026-08-04: P1-1 拆出可驗版面條款 → 白名單 8、9]`
7. 既有 3 條 `page-quote` className 測試(StockPage.test.tsx:186-206)不改斷言、維持綠。
8. **1280px 寬下 header 仍單列**(總量/昨量不因現價變寬被擠到第二列);header 增高
   (line box 由 text-3xl 撐開,約 +12px)屬預期,但 StockChart 不得因此出現
   `<main>` 垂直捲軸(圖表 `flex-1` 吸收)。反白塊 `px-1.5` 不動,底色塊隨字高變高
   屬預期表現。`[amendment 2026-08-04: P1-1 + P2-1]`
9. 期貨頁(FuturesPage.tsx:54 `text-lg`)與指數頁(IndexPage.tsx:178 `text-2xl`)的
   現價字級維持現狀,本輪不動。`[amendment 2026-08-04: P2-4]`

## Backward compat / migration

無 — 純 className 視覺改動,無 API / 資料格式 / props 變更。Revert = 還原單一 commit。

## Out of scope

- 加漲跌額(絕對點數)顯示 — 未被要求,寫入 next-time 候選。
- 自選側欄 / 右欄 / 期貨頁 / 指數頁的價格字級 — user 指名「個股的現價」= 個股頁 header;
  「三頁現價字級是否統一」寫入 next-time 候選,由後續獨立決策。
  `[amendment 2026-08-04: P2-4]`
- header 版面重排(現價移位、獨立列)。

---

# Diff 級 spec(Phase 3)

## 逐檔改動

### 🔴 `frontend/src/components/stock/StockPage.tsx`(行為改動:視覺字級)

`page-quote` span(L86-102):

- `"font-mono text-lg"` → `"font-mono text-3xl font-semibold"`
- 內層 % span:`"ml-1 text-xs"` → `"ml-1 text-sm"`,並加 `data-testid="page-quote-pct"`
  `[amendment 2026-08-04: P1-2 — % span 原無任何穩定選擇器(動態文字、無 role),
  新測試需要錨點;採選項 (a) 加 testid,querySelector 方案在日後多子 span 時會靜默選錯]`
- 其餘(limitState 三態 class、渲染條件)不動。

### 🔴 `frontend/src/components/stock/StockPage.test.tsx`(先紅後綠)

新增 describe「現價醒目化」3 條(紅先行)
`[amendment 2026-08-04: P2-3 — 補相對斷言與反白並存組合,避免 vacuous test]`:

1. 未觸價 fixture:`page-quote` className 含 `text-3xl`、`font-semibold`、`font-mono`,
   **且同畫面 h2(股名)className 不含 `text-3xl`**(鎖 SC-1 相對關係)。
2. `page-quote-pct` className 含 `text-sm`。
3. 漲停 fixture:`page-quote` className **同時**含 `text-3xl` 與 `bg-bull`、`text-white`
   (驗 twMerge 未把任一方吃掉)。

## 既有測試逐一標記

| 測試 | 該紅? |
|---|---|
| StockPage.test.tsx:186 漲停反白 | 不該紅(不斷言字級) |
| StockPage.test.tsx:193 跌停反白 | 不該紅 |
| StockPage.test.tsx:200 未觸價文字色 | 不該紅 |
| 其餘 911 條 | 不該紅 |

## Commit 計畫

單一 🔴 commit(紅測試 + 實作可分 red/green 兩 commit 依 TDD 節奏)。
無 🔵 / 🟢 成分。

self_review_head: 134f778
