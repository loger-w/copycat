# PLAN — 個股期合約選擇(condensed;design v2.1 對應;v2 = impl-spec R1-R13 修入)

任務順序:T1 → T2 → T3 → T4 → T5 → T6 → T7。細節以 design v2.1 為單一 spec。

## T1 合約發現(SC-1)

檔:`tests/fixtures/catalog_fut2_sample.json`(自 spikes dump 裁,**必含價差反例節點**)、
`copycat/live/tc4.py::list_stock_futures`(R2-1 白名單規格)、
`copycat/server/stkfut_catalog.py`(新;cache/單飛/contains)、
`copycat/server/app.py` contracts route、對應 pytest(parser 反例斷言/route 404/200/502
+ **catalog 單元四條(R11):同日兩次 get 只打一次 source/併發單飛/失敗或跨日不回舊日/
contains 對別檔 prod 與不存在 ym 回 False**)。紅 [red] → 🟢 [green]。

## T2 乘數 + 下單閘(SC-2/6 後端)

檔:`copycat/stkfut_map.py`(v2 形 + R2-6 語意 + **新 accessor
`lookup_product(prod) -> {"unit": int, "kind": "std"|"mini", "code": str} | None`**
(R3:prod→entry 反向索引 + process 級 lazy cache;mapping 與 capital_api 共用單一
入口;測試以 path 注入隔離真檔))+ **實跑 refresh CLI 重生 v2 json 同 commit**、
`copycat/capital/mapping.py`(`multiplier_of` 經 lookup_product fallback;檔頭
「零 IO 純函式」約定同步改寫為「stkfut fallback 經 lookup_product 的 process 快取」)、
capital_api(BAD_TICK/PRODUCT_NOT_ALLOWED 閘,R2-8;market 單跳過)。
pytest:unit 壞 400 / 版本降級 / 檔位閘 parametrized / ETF 拒 / **refresh 混壞列
warn + 全滅 raise 不覆寫(R8)** / **unit 非標準值 characterization(如 2157 →
PRODUCT_NOT_ALLOWED 拒單;除權息契約調整誤拒記 design Known Risks,R13)**。
**既有測試事前標記該變(R2)**:`tests/test_stkfut_map.py` 三處 v1 形等值斷言
(基本 parse / standard_preferred_over_mini(語意改「兩列並存 std/mini 分欄」)/
round-trip)→ 新形期望寫入紅 commit body。
紅 → 🟢;refresh 因期交所改版失敗 → 停下回報(不手造資料)。

## T3 引擎/資料源(SC-3 核心)

檔:`copycat/live/stock_models.py`(trial_windows 參數)、`stock_source.py`
(symbol_of Protocol + F:prod:ym key + backfill symbol + _seen symbol 鍵 + 合約鍵
timer)、`stock_engine.py`(_symbol_to_key 先寫後訂/路由/set_main_contract 轉移表/
rollover 排除 F:/ingest 日盤窗/_dirty 排除)。
pytest:design v2.1 SC-3 節列的全部測試(試撮 08:50/13:27 對照、四轉移 _refs 零
洩漏、rollover 隔離、健檢分形、先寫後訂順序、**夜盤 ingest gate:期貨 key 餵
15:30/01:00 tick → minutes 不變 seq 不進位,現貨不受影響(R10)**)。
**fake source 遷移清單(R1,同 commit 對齊)**:`tests/helpers/fake_sources.py::
FakeStockSource`(含 test_boot_window 的 BlockingSubscribeStockSource 繼承鏈)、
`tests/server/test_stock_engine.py::FakeSource`、evidence fake_server 的
SeededStockSource(Phase 6 前補齊即可)— `symbol_of` 實作一律與
`stock_source.stock_symbol` 同一份規則(不得自定第二份對映)。
commit 拆(R12 機械判準):**既有 pytest 全綠且未修改任何既有 assertion = 🟢 一對;
凡需改既有 assertion 者一律獨立 🔴 對且 commit message 引用該 assertion**。

## T4 切換 API(SC-3)

檔:`app.py` `/api/stock/state/{code}?contract=`(regex + catalog.contains 白名單 +
BAD_CONTRACT/502 + snapshot 帶 underlying)。pytest:驗證矩陣 + set_main_contract
接線 + 白名單拒別檔合約。紅 → 🟢。

## T5 前端幾何/圖表態(SC-5)

檔:`lib/stock-intraday-svg.ts` + `lib/time-labels.ts`(XWindow 全清單 D9)、
`StockIntradayChart.tsx`(窗 prop + barW + VP/overlay 期貨態停用 — **期貨態由
顯式 prop 傳入,不從 accum.code 猜(R6)**)、`StockChart.tsx`(期貨態僅江波圖:
模式鈕 disabled + **contract≠null 時 mode 強制收斂 intraday(effect setMode,
不寫回 localStorage)+ useStockBars enabled:false(R5)**;各元件收值口徑:
StockChart/StockIntradayChart 收股號 + 期貨 prop,**OrderBook 恆收股號**(RightRail
點價 gate 依賴))。
vitest:D9 lock 全套(minuteToX/minuteOf 互逆/barW 300/hourTicksOf)+ 既有現貨與
index 呼叫端零改斷言 + **元件層(R6):期貨態 overlay/VP query 不觸發、VP toggle
disabled、模式鈕 disabled、殘留日 K mode 收斂回江波圖**。
🔵(參數化零行為)與 🟢(期貨態)分 commit。

## T6 前端資料流(SC-4)

檔:`App.tsx`(contract state/railCtx 口徑)、`hooks/useStockStream.ts`(R2-7 URL
helper + instrumentKey gate;**R9:新增 `instrumentKeyRef`(codeRef 同款每 render
指派)供 handle()/refetch() 閉包讀;WS 連線 effect 維持 `[]` 不動;切檔 effect
deps 由 `[code]` 改 `[instrumentKey]`**)、`hooks/useStkfutContracts.ts`(新)、
`StockPage.tsx`(下拉可指認 + 期現價差列期貨態清空)。
vitest:URL 形/WS 重連後 refetch URL 仍帶 ?contract=/下拉 404 隱藏/換股重置/
切合約不重建 WS。紅 → 🟢。

## T7 下單面(SC-6 前端)

檔:**`components/stock/LadderView.tsx`(新,R7 具名)** — presentation props:
rows / marketBidQty / marketAskQty / 標記 map / armed / onClickPrice / onCancelLot /
rowRef 收集 / centerRequest(自 PriceLadder 抽;**留在 container**:submit hook、
arm reducer + idle timer、折數 localStorage、部位口徑、debounce/送單提示;
R2-4 的「量 bar」字樣更正 = bidQty/askQty 數字欄);`PriceLadder.tsx` 改吃
LadderView(🔵,既有測試全綠 = 零行為證據);`StkfutLadder.tsx`(新,R2-4 規格
逐項);`RightRail.tsx`(**R4:contract≠null → market="fut" 貫穿委託/部位 tab,
positionsContent 走 fut 分支 + futCloseEstimate/futExchangeContract 比對**);
兩新錯誤碼前端文案。
vitest:R2-4 規格逐項 + R2-5 武裝解除(切 contract → aria-pressed false)+
ETF disabled + **R4:選中合約後 CapitalOrdersList/PositionsList 收到 market="fut"**。
🔵 → 紅 → 🟢。

## 驗證 gate(Phase 5)

六 gate;validate 豁免同前(零觸碰 replay 鏈)。

## 非自動化交付項

- SC-4/5 截圖:fake server 種期貨 instrument(evidence 樣板擴充)+ user 過目
- SC-6 真送單 = user prod 安全首單(§7:遠價 1 口 → APP 核對 → 刪單);自動化僅
  route 層
- D14 觀察項:prod 重啟後首日 08:45–09:00 期貨分時有資料(user 順看)
