# Design v1: T 字報價籌碼表 + 游標試算(txo-tquote-cursor)

版本:v2(2026-07-18)
Changelog:
- v1 初版。
- v2 = design-review round 1(9 P2 全 accepted;0 P0/P1,退出條件 round 1 即達):DR-1 tquote lib 簽名補齊 + QuoteTable props;DR-2 xDomain 共用消除互逆漂移;DR-3 座標換算 w-full 假設顯式化;DR-4 golden regen 腳本落地;DR-5 strike 非整數點 warning;DR-6 readout 固定右上角;DR-7 不變量改推導式;DR-8 ATM 範圍外 null;DR-9 real-env 驗證路徑入 §5。
- v3 = Phase 4 自評 amendments(code-review-round-1.json):CR-1 §4.2 游標 state 只存 xMillipts、pnl 每 render 由當前 curve 派生(WS 更新即重算);CR-2 §2.2 DR-5 warning 時點改 reset()(載入時一次,snapshot 廣播路徑零洗版);CR-3 regen.py 報告改 logging(§2 禁 print 無 CLI 例外)+ regen 兩側 strip contracts 保 idempotent。

基礎:上一輪 `.claude/feat/txo-aggregate-pnl/design.md` v3 架構全沿用(TC4 → EngineRuntime → FastAPI WS → React);本輪**不動** tc4.py / handover.py / engine.py / app.py — snapshot dict 薄轉發原樣流過。

## 1. 資料流總覽

```
ChainAggregator._pos(既有,擴充 outer/inner 分量)
   │ snapshot() 新增 "contracts": [...]  ← 唯一後端改動(aggregate.py)
   ▼
EngineRuntime / FastAPI WS(不動,dict 原樣過)
   ▼
frontend types.ts(Snapshot.contracts? 新 optional 欄位)
   ├─ QuoteTable.tsx(新)── T 字表:配對 Call/Put by strike
   └─ PnlChart.tsx(改)── 游標 crosshair + readout(lib/pnl-svg 新純函數)
App.tsx:上下排版(曲線上、表格下)
```

## 2. 後端:aggregate.py 擴充(SC-1)

### 2.1 `_PosState` 內外盤分量

```python
@dataclass
class _PosState:
    net_qty: int = 0            # 既有:外 − 內(不變,續用既有累積路徑)
    net_cost_millipts: int = 0  # 既有
    volume: int = 0             # 既有:全部成交(含未分類)
    outer_qty: int = 0          # 新:外盤累積口數
    inner_qty: int = 0          # 新:內盤累積口數
```

`_ingest` 外盤分支加 `pos.outer_qty += tick.qty`、內盤分支加 `pos.inner_qty += tick.qty`。
不變量(DR-7,per-contract 未分類無獨立欄位,寫成可斷言的推導式):
- per-contract:`net_qty == outer_qty - inner_qty` 且 `volume - outer_qty - inner_qty >= 0`
- 全域:`Σ_contract (volume - outer_qty - inner_qty) == totals.unclassified_qty`
`reset()` 整個 `_pos` dict 重建 → 新欄位自然清空,不需額外處理。

### 2.2 snapshot `contracts` 欄位(對外契約,只加不改)

```json
"contracts": [
  {"symbol": "TC.O.TWF.TX4...C.43000", "cp": "C", "strike": 43000,
   "net_qty": -120, "volume": 350, "outer_qty": 100, "inner_qty": 220}
]
```

- 來源 = `self._pos` 全部項目(**含 net_qty=0 但有 volume 者**;前端依 volume 決定列集合)。
- `strike` 用**點**(int,`strike_millipts // 1000`;TXO 履約價恆為整數點)— 前端顯示零轉換。
  邊界(DR-5,不靜默截斷):`strike_millipts % 1000 != 0` → `logger.warning`(含 symbol)後整除;測試補一筆非整數 strike 的 warning 斷言(caplog)。
- 排序:strike 升冪、同 strike C 在前(deterministic,golden 可鎖)。
- 既有欄位(series_id/status/curve/beps/totals/…)shape 與數值零變動。
- `latest_snapshot()` 空態(engine.py:76)不含 `contracts` → 前端 optional。

### 2.3 golden 重生(SC-1 驗證)

`tests/fixtures/txo_golden/expected_snapshot.json` 全等比對會因新欄位破 → **事前標記「該變」**(brainstorm 已記)。
重生程序(DR-4,腳本落地可重現):`tests/fixtures/txo_golden/regen.py` — 讀同一份 `ticks.jsonl` 重跑 parse → ingest_backfill → snapshot,stdout 印「舊 key 子集 diff 報告」(新 snapshot 移除 `contracts` 後與現行 golden 全等與否),確認 diff=0 才覆寫檔案。完工證據附腳本輸出。人工抽核 2-3 檔合約 outer/inner/net 手算相符後定稿。

## 3. 前端:T 字表(SC-2)

### 3.1 types.ts

```ts
export interface ContractRow {
  symbol: string; cp: "C" | "P"; strike: number;
  net_qty: number; volume: number; outer_qty: number; inner_qty: number;
}
// Snapshot 加:contracts?: ContractRow[];
```

### 3.2 `lib/tquote.ts`(純函數,可測)

```ts
export interface TQuoteRow { strike: number; call: ContractRow | null; put: ContractRow | null; }
export function buildTQuoteRows(contracts: ContractRow[]): TQuoteRow[];
// 過濾:任一側 volume > 0 才入列;依 strike 配對 C/P;strike 降冪排列
// (高履約價在上,靠近現價的 ATM 區居中 — 台股 T 字報價慣例)
export function outerRatio(row: ContractRow): number | null;
// outer/(outer+inner);分母 0 → null(顯示 —)
export function maxAbsNetQty(rows: TQuoteRow[]): number;
// 全表兩側 |net_qty| 最大值(能量條正規化分母);全空 → 0
export function energyWidth(netQty: number, maxAbs: number): number | null;
// |netQty|/maxAbs ∈ [0,1];maxAbs === 0 → null(不畫條)
export function atmBoundaryIndex(rows: TQuoteRow[], spotPts: number | null): number | null;
// spot 介於 rows[i].strike 與 rows[i+1].strike(降冪)→ 回 i(分隔線畫在 i/i+1 之間);
// spot null 或超出 [min,max] strike 範圍 → null(DR-8,不畫)
```

`[auto-default: strike 降冪(高在上) | reason: 台股選擇權 T 字報價慣例,Call 價外在上、Put 價外在下]`

### 3.3 `components/QuoteTable.tsx`(新)

- Props(DR-1):`{ contracts: ContractRow[] | undefined; spotPrice: number | null }`(App 傳 `snapshot.contracts` 與 `snapshot.spot?.price`;不收整個 snapshot,渲染面最小化)。
- 版面(單一 `<table>`,`overflow-x-auto` 容器):

  | Call 能量 | 內外盤比 | 成交量 | 淨部位 | **履約價** | 淨部位 | 成交量 | 內外盤比 | Put 能量 |

- 中央履約價欄粗體;ATM 分隔線由 `atmBoundaryIndex` 決定(`border-accent`;null → 不畫,涵蓋 spot 缺與範圍外兩態,DR-8)。
- 能量欄 = 簽名橫條:寬度 `energyWidth(net_qty, maxAbsNetQty(rows))`(null → 不畫條只顯示數字),正紅(`bg-profit`)/ 負綠(`bg-loss`)+ 數字。Bull 紅 / Bear 綠沿專案 token。
  (註:淨部位欄顯示數字、能量欄顯示條,兩欄同源不同呈現 — 對齊截圖系統「數字 + 量條」並排的閱讀法。)
- 內外盤比:`外盤%`(`outerRatio` × 100 取整 + `%`);null → `—`。
- 無成交側:整側四欄 `—`。
- `contracts` 缺 / 空 / 全無 volume → 卡片顯示「尚無成交累積」(同 PnlChart 空態文案)。
- 繁中標題:`T 字報價籌碼表`;欄頭 `能量 / 內外盤比 / 成交量 / 淨部位 / 履約價`。
- 純渲染規則遵 §3 慣例:配對 / 比值 / 條寬計算全在 `lib/tquote.ts`,元件只掛 DOM。

### 3.4 App.tsx 排版(SC-4)

`MetricsBar → PnlChart → QuoteTable → footer` 縱向排列(上下排版 auto-default,brainstorm 已記)。不用 tab → `hidden` 慣例不適用。`max-w-6xl` 既有容器不變。

## 4. 前端:游標試算(SC-3)

### 4.1 `lib/pnl-svg.tsx` 新純函數(無 React 依賴)

```ts
export function xDomain(curve: CurvePoint[]): { minX: number; spanX: number };
// DR-2:x 軸 domain 單一來源 — buildScales 與 invertX 皆呼叫它,單邊修改不再靜默破互逆
export function invertX(px: number, curve: CurvePoint[], box: ScaleBox): number | null;
// SVG 使用者座標 px → 毫點;超出 [minX,maxX] 對應範圍 → null
// 與 buildScales.x 嚴格互逆(測試:invertX(scales.x(v)) ≈ v)
export function interpCurve(curve: CurvePoint[], xMillipts: number): number | null;
// 與後端 payoff.interp_pnl 同語意:線段線性插值,範圍外 null(payoff.py:78 對照)
```

`buildScales` 內部改用 `xDomain`(行為不變,既有測試不動 — 屬本輪實作的同檔重構)。

### 4.2 PnlChart.tsx 互動

- `onMouseMove`:`getBoundingClientRect()` + `clientX` → 換算 SVG viewBox 座標(`px = (clientX - rect.left) / rect.width * BOX.width`)→ `invertX` → `interpCurve` → `useState<{xMillipts, pnl} | null>`。null → 清除。`onMouseLeave` → 清除。
  換算假設(DR-3):SVG 渲染盒與 viewBox 等長寬比(現況 `className="w-full"`、高度隨比例、preserveAspectRatio 預設 meet)— 實作於 svg 元素旁留一行註解綁定此前提;改高度拘束時換算需改用 CTM。
- Readout 渲染(cursor 非 null 時):垂直 crosshair 虛線(`stroke-ink-muted`)+ **固定右上角**文字 `<x 點位> ▸ <formatNtd(pnl)>`(DR-6:不隨游標移動,與現價標籤〔隨 spotX 置中於頂部〕空間分離;`pointer-events-none` 防抖動迴圈)。與現價線(`stroke-accent`)視覺區隔。
- 既有現價線 / BEP / 分區渲染零變動;無 `useEffect`(事件驅動 state,lint 規則自然過)。
- curve < 2 點時既有早退分支已擋(不進 SVG 渲染)。

## 5. 測試策略

| 層 | 內容 |
|---|---|
| tests/live/test_aggregate.py | 新增:外/內/未分類混合 tick 序列 → `contracts` 欄位精確斷言(§2.1 兩條推導式不變量)、排序 deterministic、reset 後清空、非整數 strike warning(caplog,DR-5)、**既有測試 assertion 一字不改**(向下相容) |
| tests/live/test_replay_golden.py | golden 重生後照跑(assertion 不改,fixture 換);regen.py 輸出舊 key 子集 diff = 0(DR-4) |
| frontend lib/tquote.test.ts | buildTQuoteRows(配對/過濾/降冪)、outerRatio(含 0 分母)、maxAbsNetQty/energyWidth(max=0 → null)、atmBoundaryIndex(範圍內/外/null,DR-8)數字釘死 |
| frontend lib/pnl-svg.test.ts | invertX 互逆性 + 邊界 null;interpCurve 對照後端手算例(同一組數字兩邊釘) |
| frontend QuoteTable.test.tsx | RTL(jsdom pragma / cleanup 慣例):列數、Call/Put 值、單側空態 `—`、無資料空態文案 |
| frontend PnlChart.test.tsx | 既有測試不動;新增 fireEvent.mouseMove → readout 文字出現、mouseLeave → 消失(jsdom 無 layout → mock `getBoundingClientRect`) |
| real-env(DR-9) | 達錢 4 開啟 → `TXO_BACKFILL_DATE=<上一交易日> .venv\Scripts\python -m copycat.server`(休市日)+ `npm run dev` → DevTools MCP 截 `evidence/SC-2_tquote-table.png`、`SC-3_cursor-readout.png`、`SC-4_layout.png` |

## 6. SC 對應表

| SC | 章節 |
|---|---|
| SC-1 | §2(aggregate 擴充 + golden 重生) |
| SC-2 | §3(tquote lib + QuoteTable) |
| SC-3 | §4(pnl-svg 純函數 + PnlChart 互動) |
| SC-4 | §3.4(App 排版) |
| SC-5 | §5 + 既有 gate(pytest/ruff/pyright/validate/npm test/tsc/eslint) |

## 7. Known Risks

(暫無 — review 後補)
