# verification — feat/txf-intraday-overlay

日期:2026-08-27(盤後)。worktree `C:\side-project\copycat-wt-txf`,HEAD 857feb7a(review round 1 收修後)。

## 1. 自動化 gate(全部在收修 commit 857feb7a 之後重跑)

| Gate | 指令(cwd) | 結果 | exit |
|---|---|---|---|
| 前端測試 | `npx vitest run`(frontend/) | 152 檔全綠(總數見 §1.1) | 0 |
| 型別 | `npx tsc -b`(frontend/) | 0 錯 | 0 |
| Lint | `npx eslint src`(frontend/) | 0 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | 1 warning `GroupGridView.tsx:70` only-export-components —— **存量**(master 同一行 `export function gridShape`,本分支對該檔 diff 不含 70 行);零新增 finding | 0 |
| 後端測試 | `C:\side-project\copycat\.venv\Scripts\python -m pytest -q`(worktree root;worktree 無 .venv,借主 tree venv,pyproject pythonpath 指 worktree) | 3112 passed, 3 skipped(後端零 code 改動,跑它是 CLAUDE.md §1 gate 要求) | 0 |
| Ruff | `... -m ruff check copycat tests` | All checks passed | 0 |
| Pyright | `... -m pyright` | 0 errors, 0 warnings | 0 |
| copycat validate | 未跑:後端 / replay 零改動,validate 需先跑兩份 replay(分鐘級),與本案無關 | — |

### 1.1 測試總數
見本檔末「附錄」(去 ANSI 重跑一次 `--reporter=dot` 取總數)。

### 1.2 Seams(spec §4)對應測試
- S1 `frontend/src/lib/txf-overlay-series.test.ts` 14 條(終點標記 −1 / 錨定日日盤段 / 凌晨錨定 / 0 價 / 亂序 p / 錨定日 ≠ trade_date 不疊 / ref 缺 → null / 空 bars / 補尾 5 條 / stale)
  + `frontend/src/lib/index-overlay-lines.test.ts`「txf 鍵」1 條(SPOT / STKFUT 兩窗)。
- S2 `frontend/src/hooks/useChartToggles.test.ts`「A set → B 同步」+「外部清空回預設」2 條(+ 既有 15 條全綠,零 assertion 改動)。
- S3 `StockIntradayChart.indexlines.test.tsx`「idxTxf 開 → index-line-txf / 反灰無台指期資料 / 無結算價」1 條;
  `GroupGridView.test.tsx` 九鈕表加 `["idxTxf","台指期"]`;`useFuturesBars.test.ts`「enabled=false 零 fetch」1 條(review 收修)。
- 事前標記的既有斷言變更:toggle 鈕數 7 → 8(`StockIntradayChart.index.test.tsx` / `.variant.test.tsx`)、
  12 個測試檔 `ChartToggles` fixture 補 `idxTxf: false`(schema 擴充,不改任何行為斷言)。

## 2. 真實環境(prod 8721 = 59b70213,15:20 盤後重啟;worktree `vite --port 5175` proxy → 8721;claude-in-chrome 既有 session)

| # | 情境 | 結果 | 證據 |
|---|---|---|---|
| happy | 個股頁 2330 分時圖 toggle 列 | 八鈕 `均價 CDP MA 量分佈 成交點 加權 櫃買 台指期`,台指期排在櫃買之後 | `evidence/stock-2330-toggle-row-afterhours.jpg`;DOM 讀值:`{t:"台指期", disabled:true, title:"無昨收"}`(當時尚未收修文案) |
| edge 1 | 反灰理由 | 三顆指數鈕皆 disabled,理由 = 個股 `meta` 為 None(`GET /api/stock/state/2330?tape=0` → `meta: null`;TC4 盤後重啟不重送參考價,F1 的加權 / 櫃買同樣反灰)—— 這是環境限制不是本案 bug | curl 落 scratchpad `st2330.json` |
| edge 2 | TXF 側資料 | `GET /api/market/bars/TXF?tf=1&days=1&session=allday` → 695 根、`00:00`–`16:34`、`status: ok`;`/api/futures/state` TXF `ref=46064000`、`p=46351000`、`date=2026-08-27` → `txfBarsToSeries` 有料可算(錨定日 08-27 日盤段在內) | scratchpad `txf1.json` / `fut.json` |
| 未改功能 1 | 群組圖牆 toggle 列 | 九鈕 `… 加權 櫃買 台指期 十字線`,卡片正常回補 / 繪圖 | `evidence/group-grid-toggle-row-afterhours.jpg` |
| 未改功能 2 | 台股綜合 / 期貨 tab | 頂列指數帶正常(加權 45975.22 / 櫃買 400.38 / 台指 46341);期貨 tab 未動 | 截圖頂列 |

**沒拍到的**:橘色台指期線本體與右緣「台指期 ±x.xx%」標籤 —— 今晚 prod 所有個股 `ref` 皆 null(上表 edge 1),三條疊線在真環境都畫不出來。線的幾何與標籤由 S1 / S3 測試釘住(`stroke-idx-txf` class、`台指期 -1.00%` 文案、SPOT / STKFUT 兩窗交集);**真環境畫面列為次一交易日 user 過目項**(個股頁開「台指期」鈕 → 橘實線 + 右緣標籤;同開「加權」對照顏色可分)。

## 3. 回頭核 goal(spec #121)
- 三顆並存 ✓(§1 / S3);交集只畫 ✓(`buildIndexOverlayLines` 依 xw 過濾,S1 index-overlay-lines txf 條兩窗斷言);
  結算價基準 ✓(`ref` 取期貨 WS `FuturesProductState.ref`;標籤 hint「相對結算價 %」);
  借期貨 tab bars + 零新請求 ✓(同 queryKey;`enabled`/`active` 雙閘,useFuturesBars 測試);
  橘 token ✓(`--color-idx-txf: #fb923c`,`stroke-idx-txf` 字面 class);glossary 三條 ✓(CONTEXT.md);
  Q7 入 next-time ✓;Q8 module store ✓(S2);seams S1+S2+S3 ✓;白名單(不動後端 / 不 bump 版本 / index·futures 態無鈕)✓(review Spec 軸逐條核過)。
- 未做(user 未要求、review 延後):S4 疊線表格化 / S5 分鐘編解碼收斂 → next-time。

## 附錄:測試總數(收修後 `npx vitest run --reporter=dot`,去 ANSI)

```
Test Files  152 passed (152)
     Tests  2847 passed (2847)
```
