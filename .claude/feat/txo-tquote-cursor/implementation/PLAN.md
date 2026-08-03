# Implementation Plan(condensed):txo-tquote-cursor

對應 design.md v2。TDD 順序:後端(SC-1)→ 前端 lib(SC-2/3 純函數)→ 前端元件(SC-2/3/4)。
wave 歸屬見各節標記(/auto goal_efficiency_mode 未啟用 → 標準三 commit;檔數 10 但多為小改,維持標準 TDD,紅/綠按 SC 分組)。

## 1. copycat/live/aggregate.py(SC-1)

- `_PosState` 加 `outer_qty: int = 0`、`inner_qty: int = 0`;`_ingest` 外盤分支 `pos.outer_qty += tick.qty`、內盤分支 `pos.inner_qty += tick.qty`(既有 net_qty/net_cost 行不動)。
- `snapshot()` 回傳 dict 加 `"contracts": self._contract_rows()`。
- 新私有方法:
  ```python
  def _contract_rows(self) -> list[dict]:
      # sorted(self._pos.items(), key=strike 升冪、同 strike C 在前)
      # strike_millipts % 1000 != 0 → logger.warning("non-integer strike ...", symbol)(仍整除)
      # 每項:{"symbol", "cp", "strike": strike_millipts // 1000,
      #        "net_qty", "volume", "outer_qty", "inner_qty"}
  ```
- 失敗測試(先紅):見 §2。

## 2. tests/live/test_aggregate.py(SC-1 紅測試)

新增(既有測試零改動):
- `test_snapshot_contracts_detail`:C/P 各一檔 + 外/內/未分類混合 tick → `contracts` 精確斷言(值 + strike 升冪 + C 在前)。
- `test_contracts_invariants`:多合約**手寫固定序列**(覆蓋外/內/未分類三分支各多筆,不用 random — IR-5)→ per-contract `net_qty == outer-inner`、`volume-outer-inner >= 0`;全域 `Σ(volume-outer-inner) == totals.unclassified_qty`。
- `test_contracts_reset_cleared`:ingest 後 reset → `snapshot()["contracts"] == []`。
- `test_non_integer_strike_warns`:strike_millipts=42500500 合約 → caplog 出現 warning、strike 整除呈現。
- 既有欄位向下相容由既有測試(不改)+ golden 共同守住。

## 3. tests/fixtures/txo_golden/regen.py + expected_snapshot.json(SC-1)

- `regen.py`:複製 test_replay_golden.py 的建構邏輯(讀 ticks.jsonl → contracts → ingest_backfill → snapshot(series/status/accumulated_from 同測試常數))。
  - 輸出:snapshot 先 `json.loads(json.dumps(snap))` 正規化(tuple→list,同 golden 測試;IR-3)→ pop `contracts` 後與現行 golden `==` 比對 → stdout 印 `old-keys diff: NONE`(否則列 diff 並 exit 1,不覆寫)。
  - diff=0 → 覆寫 `expected_snapshot.json`(含 contracts)。
  - stdlib only、`from __future__ import annotations`、logging 不 print?— regen 是 CLI 腳本,stdout 報告即輸出物,允許 print(同 spikes 慣例,不進 package)。
- 跑法:`.venv\Scripts\python tests/fixtures/txo_golden/regen.py`(repo root)。

## 4. frontend/src/types.ts(SC-1 契約)

- 加 `export interface ContractRow { symbol: string; cp: "C" | "P"; strike: number; net_qty: number; volume: number; outer_qty: number; inner_qty: number; }`
- `Snapshot` 加 `contracts?: ContractRow[];`(optional — 空態 snapshot 無此 key)。

## 5. frontend/src/lib/tquote.ts + tquote.test.ts(SC-2 純函數,先紅)

- design §3.2 五個 export 照簽名落地(`TQuoteRow` / `buildTQuoteRows` / `outerRatio` / `maxAbsNetQty` / `energyWidth` / `atmBoundaryIndex`)。
- `buildTQuoteRows`:group by strike(Map)→ 過濾任一側 volume>0 → 降冪 sort。同 strike 同 cp 重複 symbol 理論不發生,後者覆蓋即可(單序列內 strike+cp 唯一)。
- `atmBoundaryIndex(rows, spotPts: number | null)`:rows 降冪;`spotPts` 介於 `rows[i].strike >= spot >= rows[i+1].strike` 的第一個 i;`spotPts === null`、`rows.length < 2` 或範圍外 → null(IR-4)。等於邊界 strike 時取該界(`>=`/`<=` 皆含)。
- 測試:配對 / 過濾 / 降冪 / 0 分母 / max=0 / ATM 範圍內外 / **spotPts=null** 各數字釘死。

## 6. frontend/src/lib/pnl-svg.tsx + pnl-svg.test.ts(SC-3 純函數,先紅)

- 加 `xDomain(curve)`(minX/spanX,`spanX = maxX - minX || 1` 與現 buildScales 一致);`buildScales` 改呼叫它(行為不變,同檔 🔵 重構段)。
- 加 `invertX(px, curve, box)`:`v = minX + (px - pad) / innerW * spanX`;`px` 超出 `[pad, width-pad]` 或反解值超出 `[minX, maxX]` → null(兩層都擋:pad 外像素直接 null)。
- 加 `interpCurve(curve, xMillipts)`:逐段 `x0 <= x <= x1` 線性插值;`x1 === x0` 回 y0;範圍外 null(payoff.interp_pnl 同語意)。
- 測試:`invertX(scales.x(v)) ≈ v`(數個 v,容差 1e-6)、pad 外 null;interpCurve 用後端 test_payoff 同組手算數字釘。

## 7. frontend/src/components/QuoteTable.tsx + test(SC-2)

- Props `{ contracts: ContractRow[] | undefined; spotPrice: number | null }`。
- 空態(undefined / rows.length===0)→ 卡片「尚無成交累積」。
- `<div className="overflow-x-auto rounded-md border border-line bg-surface">` 內單一 `<table>`;欄序:Call 能量|內外盤比|成交量|淨部位|履約價|淨部位|成交量|內外盤比|Put 能量。
- ATM 分隔線:`atmBoundaryIndex` 非 null → **該列(i)每個 `<td>`** 加 `border-b border-accent`(IR-6:tr border 在 table 渲染不穩);jsdom 測試斷言 td class 存在。
- 能量條:`<div>` 寬 `style={{width: pct}}` + `bg-profit`/`bg-loss`;null → 只數字。淨部位正紅負綠字色。
- 標題「T 字報價籌碼表」;jsdom 測試:列數 / 值 / `—` 空側 / 空態文案。

## 8. frontend/src/components/PnlChart.tsx + test(SC-3)

- `useState<{ x: number; pnl: number } | null>`;`handleMove(e: React.MouseEvent<SVGSVGElement>)` 依 design §4.2 換算(註解綁定 w-full 等比前提);`onMouseLeave={() => setCursor(null)}`。
- crosshair:`<line>` `stroke-ink-muted` dasharray「2 3」;readout:`<text x={BOX.width - BOX.pad} y={16} textAnchor="end">`(右上角,現價標籤置中隨 spotX — 空間分離)+ `pointer-events-none`。
- 文字格式:`${formatPts(x/1000)} ▸ ${formatNtd(pnl)}`。
- 測試:**沿用既有含曲線 fixture**(curve [43M,100k]/[44M,-100k] 的 case;既有 BASE 是空 curve 早退不渲染 svg — IR-2)→ mock `getBoundingClientRect`(回 {left:0, width:960,...})→ `fireEvent.mouseMove(svg, {clientX: 480})`(viewBox 中央、pad 內,對應 43500 附近)→ readout 文字含 `formatPts(43500)`;mouseLeave → 消失。svg 元素用 `getByRole("img")` 取。

## 9. frontend/src/App.tsx(SC-4)

- `<PnlChart …/>` 下方插 `<QuoteTable contracts={snapshot.contracts} spotPrice={snapshot.spot?.price ?? null} />`。
- 其餘不動(footer 保持最底)。

## 10. Gate(SC-5)

repo root:`pytest -q` / `ruff check copycat tests` / `pyright` / `python -m copycat validate`(需 four/five replay 產物 — 若 out/ 已存在沿用,否則先跑兩份 replay)。frontend:`npm test` / `npx tsc -b` / `npx eslint src`。regen.py 屬 tests/ 樹 → ruff 範圍內,風格對齊。

**Real-env 驗證(IR-1 / DR-9;SC-2/3/4 完工證據,Phase 6 執行)**:
1. 達錢 4 開啟 → `TXO_BACKFILL_DATE=<上一交易日>`(休市日)+ `.venv\Scripts\python -m copycat.server`(port 8721)。
2. `npm run dev`(frontend/)。
3. DevTools MCP 截圖落 `.claude/feat/txo-tquote-cursor/evidence/`:`SC-2_tquote-table.png`(表格含資料)、`SC-3_cursor-readout.png`(游標懸停 readout 可見)、`SC-4_layout.png`(單頁曲線+表格全景)。
