# Change Spec — index-board(大盤看盤改造 + 現價亂跳 bug)

> 事後重建(見 `HANDOFF.md` 開頭說明)。

## 0. 提問姿態分流

**判定:user 帶已成形改法**(明確列出要改的項目與目標狀態)→ `grilling` 姿態。
**拍板替代**:user 於 prompt 明確授權「有問題就使用 adhd 做選擇 / 不需要再特別由我來拍板 /
直接一步到底即可」→ 依 /auto 契約以 own recommendation 推進,critical decision 標 `[auto-default]`(§7)。
**發散來源**:`/adhd` 5 frame 平行(3am on-call / inversion / logistics / regulator / speedrunner),30 候選。

---

## 1. 成功條件

- **SC-1 Tab 順序與命名**:`大盤 / 個股(期) / 選擇權 / 期貨 / 相關係數`;無 localStorage 時預設停大盤;
  五個舊值仍還原到對應 tab。
- **SC-2 標的切換**:`加權 / 櫃買 / 台指期`;點台指期出現 `大台 / 小台 / 微台` 子列;選中為 accent 邊框;
  持久化(`copycat-market-key` / `copycat-market-fut`)。
- **SC-3 週期切換**:`分時 / 1~10分 / 30分 / 60分 / 90分 / 日K / 週K / 月K`(17 顆);
  分時 = 走勢折線、其餘 = 蠟燭圖(重用個股 `CandleChart`,含縮放/平移/BB);持久化 `copycat-market-tf`。
- **SC-4 加權 K 線**:日K ≥100 根、週K ≥50、月K ≥24;1~90 分由 1K 聚合(近 30 日曆日);
  圖下一行 meta 顯示「來源 · 涵蓋期間」。
- **SC-5 台指期 K 線**:大台/小台/微台切換換料;資料源**必須走 futures session**。
- **SC-6 櫃買降級誠實且不難用**:分時與 1~90 分可用(本機 MIS 5 秒取樣合成,標來源與起始時刻、
  不畫 0 量柱);日/週/月**明確拒繪**並 disabled;切到櫃買時非法週期自動落回。
- **SC-7 加權 vs 櫃買 重疊**:分時下的 toggle,既有疊線圖保留。
- **SC-8 Bug**:右上角台指只反映 `TC.F.TWF.TXF.*`;TXO 頁 spot / spot_pnl 一併正確。
  判準:與期貨 tab 大台價位一致(誤差 <5 點)。**反向判準(amendment P1-1)**:盤中連續 3 分鐘
  `spot.price` 為 None 即視為未通過。
- **SC-9 個股頁零改動**。

---

## 2. 不能破壞的既有行為(白名單)

| # | 項目 |
|---|---|
| W-1 | 個股頁全部功能 |
| W-2 | 選擇權(TXO)頁 —— 除 spot 由錯值變正確值外無行為變化 |
| W-3 | 期貨 tab 與相關係數 tab 功能與位置皆保留(僅排序後移) |
| W-4 | `useIndexStream` 的 WS merge 契約 |
| W-5 | `/api/index/state` 與 `/ws/index` 既有欄位只增不改不刪 |
| W-6 | `/api/stock/bars/{code}` 既有契約 |
| W-7 | `BarsCache` 兩段式語意與 `prune` 規則 |
| W-8 | `ChainAggregator` 對選擇權合約的分類與 `dropped_foreign_ticks` 語意 |
| W-9 | `index_engine` watchdog / 兩段式換日 / MIS 失敗保留前值 |
| W-10 | 加權 vs 櫃買重疊圖的計算與外觀;台指基差計算 |
| W-11 | `App.tsx` 的 `visited` 延後 mount 與 D-3 資料流上提 |
| W-12 | **同 symbol 的歷史一律從持有該 symbol REALTIME 訂閱的 session 問**(TXF→futures、IX0001→index) |
| W-13 | `copycat-fut-product` / `railCtx.futContract` 只由期貨 tab 驅動 |

---

## 3. 落地摘要

### 後端
- `live/models.py`:新增 `SPOT_PREFIX = "TC.F.TWF.TXF."`(含月份 leaf);`parse_realtime` 的零量放行收斂到它
- `live/aggregate.py`:`_SPOT_PREFIX` 改引用上者(`route` / `ingest_backfill` 共用)
- `live/tc4.py`:`_collect_history` + `BARS_POLL_DEADLINE` + `_POLL_BACKOFF_START` 由 `stock_source` 上提到基底
- `live/stock_source.py`:`parse_1k_bars(rows, domain)` 分鐘域參數化;新增 `fetch_bars_range_tagged`
- `live/futures_source.py`:`FUTURES_MINUTE_DOMAIN = ("0846","1345","1350")` + `fetch_bars_range`
  (SubHistory 全天窗;**不覆寫 `_rt_request`**)
- `server/bars.py`:`aggregate_period`(ISO 週 / 年月分桶)、`build_period`(5 年長窗,key `|L`)、
  `is_partial_last`、`_daily_tag`
- `server/index_engine.py`:櫃買分鐘 OHLC 合成 + `otc_bars()`、`bars_range()`、`_check_spot_silence`
  (窗 = 台指期日盤 ∪ 夜盤)
- `server/futures_engine.py`:`bars_range()`(固定 log `market: futures history proxy miss`)
- `server/app.py`:`GET /api/market/bars/{key}`(key ∈ TWSE/OTC/TXF/MXF/TMF;tf ∈ 1/D/W/M;
  拒繪走 200 + `meta.refusal`;error 走 `{"detail":{"error":…}}`)

### 前端
- `lib/timeframe.ts`(新):`MarketKey` / `MarketMode` / `MARKET_MODES` / `coerceMode` / `isModeAvailable`
- `lib/trading-hours.ts`(新):`inTradingHours`(自 hooks 搬移,re-export)+ `inFuturesTradingHours`
- `hooks/useMarketBars.ts`(新)、`components/index/MarketChart.tsx`(新)
- `components/index/IndexPage.tsx`:改寫為 標的列 + 週期列 + 主圖 + meta 行 + 重疊 toggle
- `components/stock/CandleChart.tsx`:新增 `showVolume`(預設 `true` = 既有行為)
- `App.tsx`:tab 順序 / 標籤 / 預設頁;`futures` prop 下傳 IndexPage

---

## 4. Backward compat

| 項目 | 策略 |
|---|---|
| `copycat-tab` | 值域不變;僅「無值」fallback 由 txo 改 index |
| `copycat-index-mode` | 舊值 `overlay`/`side` 讀時遷移為布林(重疊 toggle) |
| `copycat-market-fut` | **新 key**,不與期貨 tab 的 `copycat-fut-product` 共用 |
| `/api/stock/bars`、`/api/index/state`、`/ws/index` | 完全不動 |
| `BarsCache` | 長窗 `|L`、分鐘 `|M` 後綴隔離;`build_daily` 維持原簽名 |
| spot 前綴收斂 | 純判斷式收窄,無資料格式改動,revert 一行即回舊行為 |

## 5. Out of scope

櫃買永久歷史庫存、期指即時分時、期指夜盤 K 線、`/api/market/diag`、per-bar provenance、
期貨/相關係數 tab 內容改動、個股頁任何行為改動、`futures_engine` 間歇性零推播的既有 bug。

## 6. Known Risks

1. 加權 DK 深度 748 根(≈3 年)< 期指 1213 根(5 年)—— TC4 端上限,已由 `coverage_from` 誠實揭露
2. spot 收斂後新增「靜默空白」失效態 —— 以 `txo spot 無 TXF 推播` 節流 warning + SC-8 反向判準覆蓋
3. 櫃買合成 bar 僅當日、server 重啟即歸零
4. `aggregateBars` 對早於 09:00 的分鐘產生標記 09:00 的**短桶**(n=30 時僅含 ≤15 分鐘),首根寬度不等 —— 刻意接受

## 7. `[auto-default]` 決策

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| D1 | 是否刪期貨 / 相關係數 tab | 不刪,排序在後 | 刪 tab = 破壞性 scope 變更 |
| D2 | 三標的版面 | 單一主圖 + 標的切換鈕列 | K 線需要大面積 |
| D3 | K 線 API | 新 `/api/market/bars`,不改既有 stock bars | 前端單一入口 + 既有契約零風險 |
| D4 | 週/月 K | 後端由長窗 DK 依實際日期分桶 | TC4 無 WK/MK;固定根數分組遇連假累積錯位 |
| D5 | 30/60/90 分深度 | 沿用既有 30 日曆日窗 | 90 分 ≈73 根足夠;加深要付 20–40s 首載 |
| D6 | 櫃買降級 | 當日分 K 合成 + 日/週/月拒繪 | 誠實且不難用;永久庫存屬新 scope |
| D7 | bug 修法 symbol 判定 | `TC.F.TWF.TXF.` 產品樹前綴 | 同時涵蓋 HOT 與 leaf fallback |
| D8 | 預設 tab | 改為大盤 | 既然排第一 |
| D9 | 期指分時 | 不做,鈕 disabled | 需接新資料管線 |
| D10 | `/adhd` Phase 2 的 3 個 deepen agent | 略過 | 本 spec 即 deepen 產物 |

## 8. Review 兩輪的處置

見 `change-spec-review-round-1.json` 與 `code-review-round-1.json`。
**兩輪 finding 全數 accepted 並修畢,無駁回。**

`self_review_head`: `45bbecf`(rebase 前)/ `01c5f24`(rebase 後)
