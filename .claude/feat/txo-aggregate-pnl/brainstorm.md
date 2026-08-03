# Brainstorm: 台指選擇權全市場即時綜合損益圖(txo-aggregate-pnl)

日期:2026-07-18
來源:user 提供外部文章截圖(全市場 Call/Put 部位加權 → 綜合到期損益曲線 + BEP + T 字籌碼表),/feat 啟動後經 AskUserQuestion 逐項拍板。
/auto 啟動(2026-07-18):「先按照你的建議直接執行即可 後續使用有問題再修改」→ 退出條件 = 本 /feat Phase 8.5 完成;方案 A 視為 user 拍板。

## User 拍板決策(非 auto-default)

1. **本輪只做看盤子專案**;達錢 4 下單系統(個股+期貨)另開流程。
2. **MVP 範圍 = 綜合損益曲線 + 關鍵指標**;T 字報價籌碼表、滑鼠游標試算 → 下一輪。
3. **部位推估 = 當日內外盤逐筆累積**(純 Touchance tick,不打 OI 基準);語意 = 「今日新增部位的集體意志」,不含隔夜留倉。
4. **單一到期序列選單**(預設最近週選),切換 = 退訂舊鏈 / 訂新鏈 / 部位重累積。
5. **平台 = FastAPI + React,行情走達錢 4(Touchance 4.0)ZMQ API**。
6. **UI/UX 設計用 `frontend-design` + `bencium-controlled-ux-designer`**(user mid-turn 指示;於實作階段呼叫,/auto 下設計選擇標 auto-default)。

## 核心語意(演算法)

- 每檔(履約價 × C/P)累積:tick 成交價 ≥ ask → 外盤(買方主動)`net_qty += qty`;≤ bid → 內盤 `net_qty -= qty`;introspect 之間 → 不計入方向(僅計成交量)。同時累積簽名成本 `net_cost += ±qty × price`。
  - `[auto-default: 中價成交不計方向 | reason: 無方向證據,計入會汙染;截圖系統亦有內盤比欄位同款判定]`
- 到期損益曲線:在 underlying 價格網格 K 上,`PnL(K) = Σ_all_contracts (net_qty × intrinsic(K) − net_cost) × 50`(TXO 乘數 50)。
- 指標:最大獲利 / 最大虧損(網格內極值)、BEP 兩平點(PnL 過零點線性插值)、標的現價線與現價到期預估損益、Call/Put 合計淨口數、參與合約數。
- 標的現價:`[auto-default: 用 TXF 近月成交價;spike 若證實 TC4 有加權指數行情則改指數 | reason: TXO 結算標的是指數,但 TXF 誤差小且 TC4 必有]`
- 累積起點:backend 啟動時透過 TC4 歷史 tick 回補「當日開盤 → 現在」,之後接 live tick(以 timestamp/seq 去重銜接)。重啟 = 重回補。
  - `[auto-default: 回補+live 銜接進第一版 | reason: 盤中才開工具時若只從啟動累積,數字無意義;TC4 tick 歷史查詢在 2026-07-06 報告已驗過股票,選擇權由 SC-1 spike 驗]`

## 成功條件(SC gate:每條附驗證方式)

- **SC-1(spike,擋在實作前)**:`spikes/txo_chain_probe.py` 對真實達錢 4 驗證:(a) 查得指定 TXO 到期序列的合約清單(履約價 × C/P ≥ 30 檔);(b) 同時訂閱整條鏈收到 tick;(c) tick 欄位含成交價 + Bid/Ask + 量(內外盤判定可行);(d) 選擇權當日歷史 tick 回補可查。
  驗證方式:腳本 exit 0 且輸出 JSON 摘要(訂閱檔數、收到 tick 檔數、欄位覆蓋率 %、回補筆數、`contracts_count` ≥ 30 斷言),結論落 `docs/research/2026-07-18-txo-chain-probe.md`。量法:`.venv\Scripts\python spikes\txo_chain_probe.py` 的 stdout JSON。前提:達錢 4 開啟;不可用 → 記 blocker 停下回報(環境依賴,非 3 次上限適用)。
  `[amendment 2026-07-18: 執行日為週六休市 — (b) live push 流與 REALTIME 欄位語意驗證遞延至下一交易日(2026-07-20)盤中,休市日驗到「訂閱成功 + snapshot 回傳」;隔離措施 = REALTIME 對映收斂單函數 parse_realtime,Phase 7 表格 SC-1(b) 記 infra 降級不默認通過;design review DR-4 對齊]`
- **SC-2(聚合引擎)**:`copycat/live/` 零 IO 狀態機 — 輸入 tick(dataclass),維護逐檔淨部位/成本,輸出曲線 + 指標 snapshot。
  驗證方式:pytest 單元測試 — 手工構造 tick 序列斷言精確淨部位、PnL(K) 網格值、BEP 插值、極值;`.venv\Scripts\python -m pytest tests/live -q` 全綠。
- **SC-3(server)**:FastAPI — `GET /api/txo/series`(可選序列清單)、`POST /api/txo/select`(切換 active 序列)、WS `/ws/txo-pnl`(節流 ~1s 推聚合 snapshot JSON,單一全域流)。TC4 來源斷線 → WS 推 `status: disconnected` 並自動重連(exponential backoff + heartbeat,§7 紀律)。
  `[amendment 2026-07-18: 原文「WS ?series= 參數 + 前端重連切換」改為 REST select + 單一 WS 流 — 單一使用者本機工具,全域 active 序列較簡,參數化 WS 屬 over-design;design review DR-2 對齊]`
  驗證方式:pytest(fake quote source 注入,斷言 WS 訊息 shape / 節流 / 斷線狀態);`pytest tests/server -q` 全綠。
- **SC-4(frontend)**:React 單頁 — 損益曲線(獲利/虧損區著色、BEP 標記、現價虛線)+ 指標卡列 + 序列選單 + 連線狀態指示。UI 繁中,Bull 紅 / Bear 綠。
  驗證方式:vitest 元件測試綠(`npm test` in frontend/);DevTools MCP 截圖對照截圖三要素(曲線著色 / BEP / 指標)存 `docs/specs/txo-aggregate-pnl/screenshots/`。
- **SC-5(E2E replay golden)**:SC-1 spike 錄下的真實 tick 檔 → replay 進引擎 → snapshot 數字 golden 測試釘住(防未來重構漂移)。
  驗證方式:`pytest tests/live/test_replay_golden.py -q` 綠;golden JSON 進版控。
- **SC-6(既有 gate 不退化)**:`pytest -q` 全綠 + `ruff check copycat tests` + `pyright` + `copycat validate` 全 PASS。
  驗證方式:四指令 exit 0(不接管線,§8 教訓)。

## Edge cases(≥3)

1. **開盤前 / 無 tick**:淨部位全 0 → 曲線恆 0,前端顯示空狀態(「尚無成交累積」),不畫假曲線。
2. **tick 缺 Bid/Ask**(欄位空或 0):該筆不計方向、只計量;引擎計數器記 `unclassified_ticks`(筆數)+ `unclassified_qty`(口數)進 snapshot(誠實揭露覆蓋率;`[amendment 2026-07-18: 雙欄位,DR-6 對齊]`)。
3. **序列切換競態**:退訂後仍在途的舊序列 tick 依 symbol 過濾丟棄(stale-drop)。
4. **結算日**:到期序列收盤後消失/不可訂 → series 清單來自 TC4 即時查詢,不 hardcode。
5. **TC4 app 中途關閉**:ZMQ 斷 → backend 自動重連(backoff)、前端顯示斷線;重連成功後重新回補 + 重訂(部位不歸零,以回補重建)。
6. **深價外檔位零成交**:不進參與合約數,曲線貢獻 0(自然處理)。

## Out of scope(本輪不做)

- T 字報價籌碼表、滑鼠游標試算互動(下一輪 /feat)
- 多序列同時訂閱 / 跨序列合成
- 前日 OI 基準模式(「兩層都要」被否決)
- 夜盤特別處理(引擎對 session 無感,TC4 推什麼累積什麼;夜盤驗證不在 SC)
- 下單系統(另開流程,過 §7 三道閘)
- 部位成本攤平 / 平倉配對精細化(以簽名成本累積,不做 FIFO)
- 加權指數 underlying 切換 UI(現價源 auto-default 一種)

## Scope 分流

**L 級**(≥5 檔、跨前後端、新增即時資料流)→ 完整流程,Phase 1/2 各 max 3 輪 review。
`goal_efficiency_mode = true` `[auto-default | reason: 預估 >15 檔(backend live/server + frontend scaffold),/auto 同時啟動,逐 SC 三 commit 會爆量;Phase 3 走 wave batch]`
