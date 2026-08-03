# Brainstorm — stock-terminal(個股看盤,第一輪)

日期:2026-07-21。Scope:**L**(跨前後端、≥5 檔)。
User 需求原文脈絡:自選、江波圖、五檔、明細(tick 級)顯示;下單/庫存(閃電下單、現股融資融券無券空、一鍵清倉、損益/兩平價)**拆到下一輪 /feat**(user 拍板兩輪拆);訊號引擎與 DC 機器人明確不做。

## User 決策紀錄

1. 兩輪拆:這輪純看盤,下一輪交易(群益 SKCOM,treading-king 既有實作可沿用;user 更正:treading-king 下單是群益不是富邦,token/憑證仍在)。
2. 同 app 新分頁:蓋在現有 copycat frontend(TXO 綜合損益單頁)加「個股」頁,同一 FastAPI(port 8721)。
3. 版面:單檔主視圖 + 自選側欄。
4. 自選:單一清單 ≤ 30 檔,手動輸入股號 + 拖拉排序。
5. 加值:內外盤能量副圖 + 期現對照(個股期價差);鎖板提示未選。

## 架構方向(案 A,已定案)

- 新增 `copycat/live/stock.py` 系(個股訂閱池 + 當日狀態機)+ **獨立 TC4 session**,不動現有 TXO `tc4.py`/`engine.py`(實盤在跑,零風險)。共用底層純函數(`build_rt_request`/`iter_qry_pages`/`tc4common`)與 handover 交接模式(去重主鍵 = 當日累積量 TradeVolume)。
- 訂閱池抄 treading-king `fubon_ws.py` refcount 模型:key=symbol、value=owner set(watchlist / main-view),0→1 才真訂、last owner 退才真退,真訂閱失敗回滾 bookkeeping。
- 前端「個股」頁,新 WS channel 推播;元件:WatchlistSidebar / IntradayChart / OrderBook(五檔)/ TickTape(明細)/ VolumeEnergy(內外盤副圖);SVG 純函數抽 `lib/*-svg.tsx`(專案慣例)。
- 案 B(擴充 EngineRuntime 泛化吃兩種商品)被拒:動在跑的實盤路徑,review 面積大。

## 事實依據(已驗證)

- 個股 REALTIME push 可用(2026-07-21 盤中 probe,`docs/research/2026-07-21-stock-spot-quote-order-probe.md`):**完整五檔**(Bid~Bid4/BidVolume~BidVolume4,位移命名)、UpperLimitPrice/LowerLimitPrice/ReferencePrice、開高低、昨收昨量、FlagOfBuySell、TradeStatus、當日累積 TradeVolume。
- 代號:上市 = `TC.S.TWS.<code>`;上櫃段名待驗(SC-8 spike)。
- 股票類 QUERYALLINSTRUMENT 無有效 Type(四字面值全 Fail)→ 股號存在性靠「訂閱後 N 秒有無推播」健檢。
- TC4 歷史 TICKS 可回補當日(07-06 報告)→ 中途啟動江波圖/明細完整;1K 原生帶 UpVolume/DownVolume(內外盤副圖降級源)。
- 達錢 4 無下單功能(07-21 實證),交易輪走群益。

## SC(驗證窗口標註;量法見各條)

| SC | 內容 | 驗證方式 | 窗口 / 降級 |
|---|---|---|---|
| SC-1 | 自選增刪/拖拉排序/JSON 持久化/重啟保留/上限 30(超限回 400 `WATCHLIST_FULL`) | pytest routes + vitest + 重啟實測 | anytime |
| SC-2 | 側欄每檔現價/漲跌%/總量即時跳動 | 盤中截圖(DevTools MCP) | 盤中;降級=休市日訂閱即回 snapshot 截圖 + mock 單元測試 |
| SC-3 | 江波圖:分時價線+VWAP+昨收基準(ReferencePrice)+漲跌停界+量 bar;tick 即時更新;中途啟動回補完整 | vitest svg 純函數 + 盤中截圖(回補後筆數 = 全日) | 盤中;降級=回補模式畫上一交易日 |
| SC-4 | 五檔價量即時,位移命名正確對映(Bid=最佳、Bid1=第二檔) | pytest 對映單元測試 + 盤中截圖 | 盤中;降級同 SC-2 |
| SC-5 | 明細逐筆(時間/價/單量/內外盤色),回補+live 銜接無縫(TradeVolume 去重) | pytest 交接測試 + 盤中截圖 | 盤中;降級=回補資料 |
| SC-6 | 內外盤能量副圖:每分鐘內/外盤張數 bar + 當日累積比 | pytest 分鐘聚合單元測試 + 截圖 | 盤中;降級=1K UpVolume/DownVolume 歷史資料 |
| SC-7 | 期現對照:主圖檔有個股期 → 顯示期貨現價+價差;spike 先驗個股期 symbol 發現(Type="Fut" 產品碼↔股號對映)與推播 | spike 報告 + 盤中截圖 | 盤中 08:45–13:45;降級=spike 報告 + mock |
| SC-8 | 上櫃股可看(段名 spike 驗證,候選 TWO) | spike + 任一上櫃股盤中截圖 | 盤中;降級=歷史回補驗證段名 |

## Edge cases

1. 無效/不存在股號加自選:SUBQUOTE 照回 OK → 訂閱後 N 秒無推播標「無資料」,不靜默(07-20 教訓)。
2. 試撮(08:30–09:00、13:25–13:30):試撮 tick 不得污染江波圖/明細(TradeStatus 旗標過濾,treading-king 同款;確切旗標值 Phase 1 spike 確認)。
3. 漲停鎖死 Ask 全空 / 跌停 Bid 全空:五檔與價差顯示處理空值,不得 NaN。
4. TC4 斷線/重啟:generation-following listener + 自癒回補(07-20 修法沿用)。
5. 除權息日:昨收基準一律用 ReferencePrice,不自算前收。
6. 自選 30 上限、重複加同檔(冪等)。

## Out of scope

下單/庫存/清倉(下一輪)、訊號引擎、DC 機器人、多分組自選、鎖板提示、零股/盤後定價/興櫃、警報通知。五檔點價只留事件接點(下一輪接下單匣)。

## 執行約束(專案慣例帶入)

- Backend:stdlib-only runtime 核心;fastapi/pyzmq 屬 extras [live]。`from __future__ import annotations` 首行、type hints 無例外、logging 禁 print、error contract `detail.error`、WS 需 uvicorn[standard]。
- Frontend:React 19 + TQ baseline、`@/` alias、semantic token(Bull=紅/Bear=綠)、SVG 純函數抽 lib、UI 文字繁中、vitest colocated + jsdom pragma。
- TC4:序列單筆禁併發(單 REQ socket)、UTC 時窗、SUBQUOTE 必帶 StartTime/EndTime、多 symbol 回補先全訂再收割、KeepAlive/Disconnect 紀律。
- Gate:pytest + ruff + pyright + copycat validate + npm test + tsc + eslint。

cycle-count: [see state.json]
