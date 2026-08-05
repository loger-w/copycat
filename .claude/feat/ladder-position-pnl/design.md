# design:閃電梯部位列 + 未實現損益 + 含成本打平價(v2)

changelog:
- v1(2026-08-05):初版。
- v2(2026-08-05):design review round 1(0 P0 / 6 P1 / 11 P2,全 accepted)整併。
  P1:D1 折數輸入移武裝列(空手可設)/ D2 測試改 fetch route mock 並修既有測試 /
  D3 空方 pnl 手算例 + |qty| 計費契約 / D4 兩行式佈局 + 寬度預算 / D5 部位條移卡片底部
  (誤送風險:武裝中梯位移)/ D6 融券借券費 0.0008 入算。
  P2:D7 中間值修正 / D8 打平顯示改 fmt() / D9 示例自洽 / D10 色票定案(bg-warn / bg-ma20,
  不受 dimmed)/ D11 標記定位與 pointer-events / D12 輪詢敘述改實情 / D13 kind 值域實況 /
  D14 lastMilli<=0 歸一 / D15 last null 分支測試 / D16 取證通道(fake positions + 另 port)/
  D17 clampDiscount 契約收 string。

對應 brainstorm.md(user 四題實答:1.8 折 / 前端自算 / 稅 0.3% / 部位條+梯內標記)。

## 架構總覽

純 frontend 改動 + 一支驗證用 fake 腳本,落點:

1. **新 lib `frontend/src/lib/ladder-position.ts`**(零 React 純函數)
2. **`frontend/src/lib/constants.ts`**:新增 `FEE_DISCOUNT_KEY = "copycat-fee-discount"`
3. **`frontend/src/components/stock/PriceLadder.tsx`**:部位條(卡片底部)+ 梯內標記 + 折數輸入(武裝列)
4. **`frontend/src/components/stock/PriceLadder.test.tsx`**:既有 mockFetch 呼叫點全數補 positions 路由(D2)
5. 取證:fake positions 走既有「fake source + 另一 port」慣例(D16,見「真實環境取證」節)

資料流:`useCapitalPositions()`(既有 hook)→ `secPositionsOf(positions, code)` → 逐 kind `positionEcon` →(a)部位條(b)snap 後對照 `rows` 畫標記。現價 = `last.p`(毫元)。

## SC-2/SC-3:計算純函數(ladder-position.ts)

```ts
export const FEE_BASE = 0.001425;    // 牌告手續費率
export const SELL_TAX = 0.003;       // 證交稅(user 拍板固定 0.3%)
export const SHORT_BORROW = 0.0008;  // 融券借券費(D6:賣出價金 0.08%,kind==="short" 才計)
export const FEE_DISCOUNT_DEFAULT = 1.8; // user 實答:1.8 折

export function feeRate(discount: number): number; // FEE_BASE * discount / 10(1.8 折 = ×0.18)

export interface PositionEcon {
  pnl: number | null;            // 未實現損益(round 整數元;avg/last 缺 → null)
  breakEvenMilli: number | null; // 打平價(毫元,未 snap;avg 缺 → null)
}

/** 內部一律以 |qty| 計費,方向由 qty 符號決定(D3)。
 *  lastMilli <= 0 與 avgPrice <= 0 一律視為缺值(D14:「0 不是價格」同 buildLadder 入口)。
 *  borrow 費只在 kind === "short"(融券)計入賣段;daytrade_sell 資料源不出現(D13)。 */
export function positionEcon(
  qty: number,
  avgPrice: number | null,
  lastMilli: number | null,
  discount: number,
  kind: string,
): PositionEcon;
```

口徑(f = feeRate(discount);t = SELL_TAX;b = kind==="short" ? SHORT_BORROW : 0;px = lastMilli/1000;Q = |qty|×1000):

- **多方(qty > 0,b 恆 0 — 多方無借券)**:pnl = (px−avg)·Q − avg·Q·f − px·Q·(f+t);BE = avg·(1+f)/(1−f−t)。
- **空方(qty < 0)**:pnl = (avg−px)·Q − avg·Q·(f+t+b) − px·Q·f;BE = avg·(1−f−t−b)/(1+f)。

**手算例(測試逐字採用;D7 中間值修正)**,折數 1.8(f = 0.0002565):

| 案例 | 輸入 | 中間值 | 結果 |
|---|---|---|---|
| 多方 pnl(SC-2) | avg=100, px=102, qty=2, cash | 4000 − 51.3 − 664.326 = 3284.374 | **+3284** |
| 多方 BE(SC-3) | avg=100 | 100×1.0002565/0.9967435 | **100.352…** → snapUp = 100_500 |
| 空方 pnl(D3,無券外的融券) | avg=100, px=98, qty=−2, short | 4000 − 100×2000×0.0040565(=811.3) − 98×2000×0.0002565(=50.274) = 3138.426 | **+3138** |
| 空方 BE(short 含 b) | avg=100 | 100×0.9959435/1.0002565 | **99.569…** → snapDown = 99_500 |
| 空方虧損例(符號) | avg=100, px=103, qty=−2, short | −6000 − 811.3 − 52.839... | **−6864**(負值,費用不得變號成收益) |

(brainstorm SC-2 的中間值 664.53 有誤,以本表 664.326 為準;round 後結果同 3284。)

```ts
/** 打平價 snap:多方 snapUp(第一個獲利≥0 的 tick)、空方 snapDown — 保守方向。 */
export function snapBreakEven(beMilli: number, qty: number): number;

/** 折數夾制(D17):收 string | number,內部 parseFloat + Number.isFinite,0 < v ≤ 10 → v;否則 null。 */
export function clampDiscount(raw: string | number): number | null;

/** 當前標的 sec 部位列(qty ≠ 0;排序 cash→margin→short,未知 kind 原字串標籤排最後 — D13)。 */
export function secPositionsOf(positions: CapitalPosition[] | undefined, code: string): CapitalPosition[];
```

均價標記位置:`snapNearest(Math.round(avg×1000))`。

**kind 值域實況(D13)**:sec 即時庫存來源只產 cash/margin/short;`daytrade_sell`(無券空單)資料源不提供 → 不會出現在部位條(已知限制,寫 Known Risks)。

## SC-5:折數設定(D1:空手恆可用)

`[amendment 2026-08-05: Phase 4 review ORD-1/LP-7 — 武裝列放折數框造成「與張數框同型相鄰混淆(誤打折數 → 張數靜默舊值 → 舊張數送真單)」+ 快捷鈕壓縮到 ~30px;折數不是下單控制項,移出武裝列]`

- 輸入框放**標題列右端**(「跟隨置中」鈕左側):`aria-label="手續費折數"` number input(w-10,step 0.1)+ 後綴「折」小字,恆常渲染(D1 空手可設)。武裝列維持原樣(零改動)。
- **非法值可視訊號(CALC-1)**:`clampDiscount(raw) === null` 時輸入框加 `aria-invalid="true"` + `border-loss` 紅框 — 禁止「輸入框顯示 raw、計算用舊 value 且零訊號」的靜默態;測試斷言 invalid 標記。
- 元件持兩份 state(D17):`{ raw: string; value: number }` — raw 為受控輸入值(可暫時為空/非法),value 只在 `clampDiscount(raw)` 通過時更新並 `localStorage.setItem(FEE_DISCOUNT_KEY, String(v))`;計算恆用 value。初值:`clampDiscount(localStorage.getItem(FEE_DISCOUNT_KEY) ?? "") ?? FEE_DISCOUNT_DEFAULT`。

## SC-1/SC-6/SC-7:部位條(D5:卡片底部)

位置:**價格梯 scroll 區下方、卡片最底**(scroll 區是 flex-1,部位條出現時 scroll 視窗從底部縮短,**既有價格列的 y 座標不動** — 武裝中的閃電梯不得因部位資料到達而位移點擊目標;上方插入會整梯下移,是 D-12/D-13 同類的誤送風險)。空手 → 整段 null(底部增減不位移價格列,零痕跡語意保留)。

每 kind 兩行(D4;右欄可用寬 ≈ 260px,text-xs mono):

```
第一行:現股 2張 @100.00        +3,284     ← 左:kind + 量 + 均價;右緣對齊:未實現(色)
第二行:打平 100.5                          ← text-ink-muted;□ 色點對應梯內標記色
```

- 寬度預算(D4):第一行 = 2 CJK(24px)+ mono「2張 @100.00」(~11 字 ≈ 77px)+ 右對齊 pnl(~7 字 ≈ 49px)≈ 150px + 間距,兩端對齊(justify-between)裕度充足;多 kind 逐組堆疊。
- 空方顯示「空 2張」;pnl:>0 `text-bull` 帶 `+`、<0 `text-bear`、null `—`(`text-ink-dim`);千分位 `toLocaleString`。
- 打平與均價數字顯示用 **`fmt()`**(D8:與梯列價格同一格式函式,字串級同源);打平顯示 snap 後 tick 價(與標記同值)。avg null → `N 張 @ —`、打平 `—`、無標記(SC-7)。
- `last === null` → pnl `—`,**打平照算照畫**(BE 只依 avg;D15)。

## SC-4:梯內標記(D10/D11 定案)

- 資料結構:`Map<number, string[]>`(snap 後 priceMilli → kind 標籤陣列),be / avg 各一份。
- row 容器加 `relative`;標記為 `absolute inset-y-0 w-0.5 pointer-events-none opacity-100`(D11:不吃點擊 — 左緣是刪單紅方格與買鈕;顯式 opacity 隔離 `r.dimmed` 的 `opacity-35` — 遠離現價的打平標記正是最需要看見的)。
  - 註:`opacity-35` 套在 row 容器上時子元素 opacity 無法「反淡」— 實作把 dimmed 的 opacity 改套到三個 grid 欄(內容)而非 row 容器,標記與之並列(🔵 前置小重構,行為不變)。
- be 標記 `left-0`、`bg-warn`(theme 既有 `--color-warn: #f0b429`;D10 — 不用 palette 字面色);avg 標記 `left-1`、`bg-ma20`(紫,與 accent 現價語意區隔)。同列並存即並排。
- `title` 帶 kind 標籤 — `[amendment 2026-08-05: LP-1 — pointer-events-none 元素永不觸發 tooltip;title 改掛 row 容器(be/avg 併成一句),標記本身不帶 title]`。部位條第二行**兩顆色點**:`bg-warn` 對應「打平 <snap 值>」、`bg-ma20` 對應「均價」標籤(**不帶數字** — CALC-3:第一行 @ 顯示真均價原值,標線位置是 snapNearest 近似,兩口徑數字不並列;標線身分靠色點 + row title)。
- `[amendment 2026-08-05: LP-4]` dimmed 列的 row 分隔線改 `border-line/20`(移欄後 border 不再吃 row opacity,不降階會比改動前亮)。
- `[amendment 2026-08-05: CALC-2]` `positionEcon` qty=0 → 全 null(「0 不是部位」,同 px() 歸一精神)。
- 打平/均價 tick 不在 rows(超出梯域)→ 不畫,部位條照顯示。

## 測試設計(D2:fetch route mock)

- **慣例**:沿 `PriceLadder.test.tsx` 既有 `mockFetch`(spy `globalThis.fetch` + route 前綴表;未登記 URL throw)。**本輪需動既有測試**:
  1. 抽共用 helper:預設 routes 帶 `/api/capital/orders`(空)+ `/api/capital/positions`(空)+ 既有各測試的自訂 route 疊加。
  2. 既有 ~20 個 it 的 mockFetch 呼叫點改走 helper(🔵,行為不變);**市價單列 describe 目前無 mockFetch,補上**。
  3. `RightRail.test.tsx` 已有 positions 路由 — 不動,跑綠確認。
- `frontend/src/lib/ladder-position.test.ts`(新):上表五組手算例逐字;feeRate(1.8 → 0.0002565);clampDiscount("" / "0" / "-1" / "abc" / "11" / 0 / NaN → null;"1.8" / 1.8 / 10 → 值);snapBreakEven 方向;secPositionsOf(過濾 market/code/qty0、排序、未知 kind 殿後);positionEcon:lastMilli=0 → pnl null(D14)、lastMilli=null → pnl null 且 breakEvenMilli 非 null(D15)、avgPrice<=0 → 全 null。
- `PriceLadder.test.tsx` 新增:部位條文字(SC-1)、空手零痕跡、多 kind 兩組(SC-6)、avg null 顯示 —(SC-7)、last null 打平照畫(D15)、be/avg 標記 testid 落正確列 + title 帶 kind(SC-4)、dimmed 列標記不淡化、折數輸入改值重算 + localStorage(SC-5)、非法輸入不寫入且計算沿用舊值、空手態改折數可寫入(D1)。

## 真實環境取證(D16)

盤中紀律(CLAUDE.md §8)下的可視通道:**fake source + 另一 port** — 既有 tests/server fake 基建起一台不碰 ZMQ 的 server(或 vitest 之外用 vite dev + 對 `/api/capital/positions` 的本地 override script),餵假部位(cash 2 張 @100 + short −2 張 @100)截圖對照 SC-1/SC-4 可指認表述;真持倉畫面 = user 盤中過目。截圖工具:**claude-in-chrome**(user 2026-08-05 指示:用既有 Chrome session,不另開)。

## 接點與風險

- **輪詢實情(D12)**:RightRail 三 tab 互斥 render → 閃電 tab 下本 hook 是唯一 `capital-positions` 訂閱者 = 新增一條 15s 輪詢;後端只讀 in-memory store 成本可忽略;群益未登入時該輪詢週期性回錯(TQ retry 1)→ 畫面呈空手態,無新 UI 噪音。
- PriceLadder 每 tick re-render:計算 O(kinds) 純算術,無 memo 需求。
- Known simplification:不套低消 NT$20(聚合無筆數)、不計融資利息(借券費已入算 — D6)。

## Known Risks

- `daytrade_sell`(無券空單)不會出現在 sec 即時庫存(上游 `_KIND` 只認 T/C/L)→ 無券當沖部位在部位條上不可見(D13)。當前下單頻道本就標示無券為特殊流程,接受;若群益日後補資料源自然出現。
- 群益 `avg_price` 語意 = 損益試算[10]「平均買進成本」,是否含費未文件化 — 打平價以「名目均價 + 自算費稅」口徑計,若群益已內含買段費用則打平價略保守(偏高),方向安全。
