# Brainstorm: 綜合損益圖第二輪 — T 字報價籌碼表 + 游標試算(txo-tquote-cursor)

日期:2026-07-18。
**規格來源:user 於 /auto prompt 直接拍板**(superpowers:brainstorming user-approval HARD-GATE 之 /auto 替代條件成立,免互動確認)。
上一輪基礎:`.claude/feat/txo-aggregate-pnl/design.md` v3(架構與慣例沿用)。

## 目標

在既有 TXO 綜合損益單頁上加兩個能力:

1. **T 字報價籌碼表**:每履約價一列,Call(左)/ Put(右)兩側各顯示 淨部位 / 成交量 / 內外盤比 / 能量。資料源 = ChainAggregator 既有逐檔狀態(引擎已維護 `_pos`),只差 snapshot 開 per-contract 明細 + 前端表格。
2. **游標試算**:滑鼠在損益圖上移動,即時顯示該指數位置的到期損益(前端純計算,沿用既有 interp 邏輯,不加後端 endpoint)。

同一頁呈現(排版由實作判斷,tab 則走 `hidden` 慣例)。snapshot 契約擴充**向下相容**(舊欄位不動)。

## 現況事實(Phase 0 盤點)

- `_PosState`(aggregate.py:33)只有 `net_qty / net_cost_millipts / volume` — **內外盤量沒有分開存**,「內外盤比」必須擴充狀態機(外盤量 / 內盤量各自累積;net_qty = 外 − 內 維持既有語意)。
- `interp_pnl`(payoff.py:78)是後端 Python;前端只有 `buildScales`(pnl-svg.tsx)。游標試算需要前端版線性插值 + x 像素→毫點反解(新純函數,無後端)。
- `tests/live/test_replay_golden.py` 對 snapshot **全等**比對 → snapshot 加欄位必須同步重生 `expected_snapshot.json`。**此 assertion 事前標記「該變」**(鐵則 E 豁免條件):重生方式 = 同一份真實 tick 錄檔重跑 replay,人工抽核新欄位後覆寫 golden。
- Server(engine/app)是薄轉發,snapshot dict 原樣流過 → 後端只動 `aggregate.py`。

## 成功條件(SC)

- **SC-1 snapshot per-contract 明細**:`ChainAggregator.snapshot()` 新增 `contracts` 欄位 — 每合約 `{symbol, cp, strike(點), net_qty, volume, outer_qty, inner_qty}`,依 strike 升冪排序;既有欄位(curve/beps/totals/…)shape 與數值**完全不變**。
  驗證:`.venv\Scripts\python -m pytest tests/live/test_aggregate.py -q` — 新測試(內外盤分量累積 + contracts 欄位內容斷言)綠,**且既有測試 assertion 一字不改仍綠**(向下相容證據);golden 重生後 `pytest tests/live/test_replay_golden.py -q` 綠。
- **SC-2 T 字表**:前端新元件,每履約價一列,Call 左 / Put 右,各側顯示 淨部位、成交量、內外盤比、能量;無成交側顯示空態;與曲線同頁。
  驗證:`npm test`(frontend/)QuoteTable 測試綠(給定 contracts fixture → 斷言列數、Call/Put 配對、比值文字);real-env DevTools 截圖 `evidence/SC-2_tquote-table.png`。
- **SC-3 游標試算**:滑鼠在曲線圖內移動 → 顯示游標指數位置(點)+ 該位置到期損益(NTD,前端插值);滑出圖表或超出曲線範圍 → 不顯示。無後端變更。
  驗證:`npm test` — pnl-svg 新純函數(`invertX` / `interpCurve`)數字釘死測試 + PnlChart 互動測試(fireEvent mouse move → readout 出現/消失)綠;real-env 截圖 `evidence/SC-3_cursor-readout.png`。
- **SC-4 同頁整合**:表格與曲線同一頁完整呈現,互不遮擋。
  驗證:real-env 截圖 `evidence/SC-4_layout.png`(單頁含曲線 + 表格)。
- **SC-5 全 gate 綠**:`pytest -q` / `ruff check copycat tests` / `pyright` / `python -m copycat validate` + frontend `npm test` / `npx tsc -b` / `npx eslint src` 全 PASS。
  驗證:各指令 exit 0(不接管線,§8 教訓)。

## 拍板決策(user prompt)+ 實作級 auto-default

- 資料源 = ChainAggregator 既有逐檔狀態(user 拍板)。
- 游標試算前端純計算、不加後端(user 拍板)。
- Out of scope(user 拍板):多序列同時顯示、OI 基準、下單。
- snapshot 契約只加不改(user 拍板)。
- `[auto-default: 上下排版(曲線上、T 字表下),不用 tab | reason: 看盤場景兩者需同時可見,tab 互斥違背動機;單頁縱向滾動即可,hidden 慣例僅在 tab 方案才適用]`
- `[auto-default: 能量 = 淨部位簽名橫條(以全表 max|net_qty| 正規化,正=紅/負=綠,台股慣例) | reason: 截圖原件不在手邊;淨部位量體視覺化是 T 字表「能量」欄最常見語意,且 snapshot 已含 outer/inner/volume 原始值,前端改定義零後端成本]`
- `[auto-default: 表格只列「任一側 volume>0」的履約價 | reason: 全序列履約價可達 40+,無成交列全空是噪音;有成交即入列,列集合隨盤中自然擴大]`
- `[auto-default: 內外盤比顯示 = 外盤% (outer/(outer+inner)),雙零顯示 — | reason: 單一數字最省欄寬;outer/inner 原始值都在 payload,顯示格式可隨時改]`

## Edge cases(≥3)

1. **單側無成交**:某履約價只有 Call 有量 → Put 側顯示空(`—`),列仍要出(履約價軸完整性)。
2. **游標超出曲線 x 範圍 / curve < 2 點**:readout 不顯示、不噴 NaN;`interpCurve` 回 null。
3. **舊 snapshot 無 `contracts` 欄位**(server 尚未升級 / 空 snapshot `{"curve": [], "totals": null}`):前端 optional 處理,表格顯示「尚無成交累積」,不 crash。
4. **unclassified 量**:outer + inner ≤ volume(差 = 未分類);內外盤比分母用 outer+inner 不用 volume,避免未分類稀釋。
5. **reset / 序列切換**:contracts 明細隨 `reset()` 清空 — 既有 reset 測試涵蓋 `_pos` 清空,新欄位自然歸零。

## Out of scope

- 多序列同時顯示、OI 基準欄位、下單(user 拍板)。
- 表格排序 / 篩選互動、每檔成交價欄(spec 未列,不順手加)。
- 觸控裝置游標支援(桌面看盤工具)。
- 後端游標試算 endpoint(user 拍板:前端純計算)。

## Scope 分級

**L**(跨前後端;預估 ≥ 6 檔:aggregate.py、types.ts、QuoteTable.tsx、PnlChart.tsx、pnl-svg.tsx、App.tsx + 測試)。無鑑權 / 金流 / 對外多消費者 API(唯一消費者是本 repo frontend)→ L 但風險面低,Phase 1/2 各 max 3 輪照走。
