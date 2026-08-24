# R1 前端圖表標籤/版面批 verification(branch `mod/chart-label-batch`)

九條:N006 / N045 / N007 / N044 / N009 / N026 / N027 / N023 / N062。
commit:`d222df47`(🟢 red)→ `65196a11`(🔴 green)→ `413507c6`(🟢 N023 lock)。

---

## 1. 完成前 gate(皆在 `frontend/`,2026-08-24)

| gate | 指令 | 結果 |
|---|---|---|
| 型別 | `npx tsc -b` | **PASS**(exit 0,零輸出) |
| 測試 | `npm test -- --run` | **138 檔 / 2563 tests 全綠**(改動前基線 2561,本輪 +2 = N023 兩條;紅測試批的其餘案子併進既有 describe) |
| Lint | `npx eslint src` | **PASS**(exit 0,零輸出) |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | **Scanned 13 files → No issues found**(零新增 finding) |

後端未動任何 `.py` → `pytest` / `ruff` / `pyright` / `copycat validate` 本輪不涉。

## 2. 紅 → 綠 逐條證據(紅態實測值取自 `d222df47` 當下的 vitest 輸出)

| 條 | 紅態實測 | 綠態 |
|---|---|---|
| N006 | index 加權末點貼右界:`x + labelWidth("24283.54")` = 765.6 > 繪圖區右界 760(溢出 5.6px) | `x + 實寬 ≤ 760` |
| N045 | index 標籤文字 `"24283.54"`(同圖刻度印 `24284`);期指 `"23006.15"` | `"24284"` / `"23006"` |
| N007 | 日高文字(翻面態)與 VWAP 標籤中心距 **0.135px** | 恰 `EDGE_LABEL_H` = 10(`toBeCloseTo`,不多推);標記圓 cy 與 x 逐值不變 |
| N044 | hline label 與 VWAP 標籤中心距 **3.648px** | ≥ 10;線體 y1 與 label x 逐值不變 |
| N009 | `bandLabels(7 顆, {4,30})` → `[4,4,4,4,10,20,30]`(上緣四顆同 y) | `[4, 8.33, 12.67, 17, 21.33, 25.67, 30]`,相鄰間距全等 4.333、七顆兩兩相異 |
| N026 | figcaption class 無 `whitespace-nowrap` / `overflow-hidden`,四段無 `truncate` | 四項齊備,`h-4` 不動 |
| N027 | 96px 高仍 5 條(間距 ~13px < 2× 字高);139px 亦 5 條 | 96px → 3 條、間距 25.98 ≥ 20;140px → 5 條;**200 / 320px 既有測試逐值不變** |
| N062 | class 鎖 `--idx-adl-min:10rem` | `6rem`(見 §4 的量測對照) |
| N023 | (零 code 改動)mutation:`p > yTop` → `p >= yTop`(含 yBottom 側)→ 端點案**紅**,還原後 6/6 綠 | — |

**對照組(先綠、修後仍綠 = 鎖「不無故位移」)**:日高在左半場 → 極值文字 y 逐值不變;
hline 遠離 VWAP → label y 仍是「線 y − 3」;容量足夠的 `bandLabels` → 仍是既有下推佈局;
CandleChart 200px 高 → 仍 5 條;既有「末點貼右界 `x + 40 ≤ 760`」的 stock 態斷言未動且仍綠
(下限 40 保住短字的既有位置)。

## 3. 事前標為該變的既有斷言(共 2 條,皆在 change-spec 落檔後才改)

1. `stock-intraday-svg.test.ts` 走廊 A 超容案字面量 `[4,4,4,4,10,20,30]`(N009,rounds 檔已標
   「屬事前標為該變」)。
2. `IndexPage.test.tsx` class 鎖 `@[1050px]:[--idx-adl-min:10rem]`(N062,值本身就是本條要改的東西)。

其餘既有斷言一條未動(`git diff` 對既有測試檔只有 append + 上述兩處)。

## 4. N062 的證據邊界(**留給 user 真環境過目**)

CSS 層「矮視窗兩欄態不再出捲軸」**jsdom 量不到**(不套 CSS、getBoundingClientRect 恆 0),
本輪的證據是算術對照,來源 = 2026-08-20 已落檔的機械實測:

- 1536×700:主 grid `622 / 676` → 54px 捲軸;溢出源 = 家數帶 section `262 / 316`。
  316 = 家數帶固定 chrome ≈148 + gap 8 + 騰落線地板 **160**(10rem)。
  地板改 6rem(96)後該 section 需求 = 148 + 8 + 96 = **252 ≤ 262** → 不再溢出。
- 1536×864:主 grid `786 / 786`(本來就不捲),section 分到 337px、騰落線 wrapper 實得
  **181px** —— 遠高於 160 與 96 兩個地板,**兩種設定下畫面逐值相同**(地板不是指定高)。

headless 重現需要後端 8721 有真家數資料(無資料時 `BreadthBand` 走空態、高度不同,量出來
的數字對不上),故留一條:**下一個交易日盤中 1536×700 附近拉一次視窗,確認主 grid 不再出捲軸**。

## 5. 白名單 / 留尾(本輪刻意不做)

- 極值標記文字在 index 態仍走 `fmt`(`24283.54`),與同圖 `fmtIndexPts` 兩套口徑 —— 與 N006
  同型但不在 R1 清單;它畫在繪圖區內、不參與右緣寬度 clamp。**建議入 next-time**。
- `maObstacles` 的極值半寬由固定上界 `EDGE_LABEL_W / 2`(17)改為 `labelWidth(text) / 2`
  —— N007 要求「同一段文字只能有一個寬度」的直接後果;既有兩條 obstacle 測試(右緣區命中 /
  左半場不命中)在兩種算法下同號,不是行為漂移。
- `CandleChart.test.tsx` 內含一個歷史遺留的 NUL 位元組(git 判整檔 binary),N026 的 class 鎖
  因此落在新檔 `CandleChart.caption.test.tsx`。**該 NUL 未順手清**(不在本輪 scope),
  建議入 next-time。
