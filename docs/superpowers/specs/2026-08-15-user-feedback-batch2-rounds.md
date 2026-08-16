# 2026-08-15 使用者回饋第二批:分類 + 六輪 /mod 執行 prompt

> 來源:2026-08-15 user 實戰回饋 11 條(個股(期) 6 條 + 台股綜合 5 條)。四路 sonnet 調研已落
> 事實(檔案:行號內嵌各輪 prompt)。**尚未實作**;拍板項(§1)有 user 回答以回答為準,沒回答
> 走 `[auto-default]`。UI 輪一律載入 `frontend-design` + `bencium-controlled-ux-designer`
> **2026-08-15 user 已拍板 D1–D10(見 §1「拍板結果」欄),不再重問。**
> (前者管細節精緻度,後者管「設計決策先問再做」;**本專案為既有看盤 UI,一致性優先於
> 「大膽新美學」** — 不換字體/不加動效/不引入新色票,只在既有 token 內做選擇)。

## 0. 分類總表

| # | 回饋 | 類型 | 輪 | 級 | 判定依據 |
|---|---|---|---|---|---|
| 綜4 | 刪類股強弱 + 訊號時間軸(含後端 API/poller)**〔2026-08-16 已出貨:mod/remove-sector-timeline〕** | 🔴 行為刪除(/mod) | R1 | M→L(實作 45 檔) | 純減法;`fetch_snapshot`/`fetch_daily_prices` 與家數帶/連板共用,只刪專屬段 |
| 綜1 | 家數帶漲跌停底色 = 個股期漲停色(實心) | 🔴 UI(/mod) | R2 | S | 只改 `BreadthBand.tsx:29,33` tone class |
| 綜2 | 相關係數升為頂層 tab | 🔴 UI(/mod) | R2 | S | 曾是頂層,R1 spec 併入;兩處測試鎖順序 |
| 綜3 | 一頁總覽:左壓縮雙圖+家數,右漲跌停列表 | 🔴 UI 佈局(/mod) | R2 | L | 現況整頁 `overflow-y-auto` 上下堆疊,無單螢幕約束 |
| 個3 + 綜5 | 非交易日顯示最近交易日分時圖/資料 | 🔴 行為(/mod) | R3 | L | 同一根因:**全庫無交易日曆**,`trade_date=date.today()`;`TXO_BACKFILL_DATE` 是手動 env |
| 個4 | 群組圖牆分時圖 = 單檔分時圖同款設定 | 🔴 UI(/mod) | R4 | M | `MiniIntradayChart` 是精簡獨立實作,不讀 `useChartToggles` |
| 個5 | 群組頁點卡片只切閃電目標,不跳單檔 | 🔴 行為(/mod) | R4 | S | `StockPage.tsx:213-223` `selectView("single")` 一行 + 選中態視覺 |
| 個1 | 鎖定全程武裝 | 🟢 新功能 + 🔴(/mod) | R5 | M | 三座梯各自 `useReducer(reduceArm)`,無共用層;安全敏感 |
| 個2 | 現股/融資/融券/無券 改 4 顆按鈕 | 🔴 UI(/mod) | R6 | S | `PriceLadder.tsx:378-393` select;pill 樣板現成 |
| 個6 | 自選群組右側平均漲幅(未分組不做) | 🟢 新功能(/mod) | R6 | S | 全清單已訂閱,`quotes[code].chg_pct` 現成,純前端算 |

沒有一條是「線上 bug」(個3 是文件化限制),故全走 `/mod`。順序:**R1 → R2 必須串行**(同動
`IndexPage.tsx`);R3 / R4 / R5 / R6 互不相依,可各開 worktree 並行(ops-discipline 三險照過)。

## 1. 拍板清單(2026-08-15 user 已全數回答;「拍板結果」為準)

| # | 決策 | 選項 | `[auto-default]` | 拍板結果 |
|---|---|---|---|---|
| D1 | 鎖定武裝要壓掉哪些自動解除 | (a) 只壓 idle 5 分 + 換標的 + 換梯(unmount);**保留** WS 斷線 / 連 3 敗 / Esc / 手動解除 / 頁面 reload;(b) 全壓只留手動 | **(a)**(安全下限:斷線與連敗是風控不是便利) | (a) |
| D2 | 鎖定跨 reload 持久化 | (a) 只存 session 記憶體,reload 歸零;(b) localStorage | **(a)** | (a) |
| D3 | 群組卡片點擊後怎麼進單檔 | (a) 只靠檢視 pill「單檔」;(b) 雙擊卡片開單檔 | **(a)**(不加隱藏手勢) | (a) |
| D4 | 群組圖牆同款程度 | (a) 完全同一元件(含 hover 讀值列、軸標籤、高低點、VP/POC、CDP/MA/VWAP、toggle 共用),toggle 列在圖牆頂一份;(b) 同 overlay 但去掉 hover 讀值 | **(a)**(user 原話「一模一樣」) | (a) |
| D5 | 群組平均漲幅算法 | 等權平均、分母排除 `p==null`(無成交/no_data);顯示 `fmtPct` + bull/bear 三態色 | 照此 | 照此 |
| D6 | 綜合頁佈局 | **A** 左欄上半雙圖並排 + 下半 BasisRow/家數帶/騰落線,右欄漲跌停列表整高內捲;B 左欄雙圖上下堆疊;C 三欄 加權/櫃買/列表 + 家數帶橫跨底部 | **A** | **A + 追加**:騰落線(AdvanceDeclineChart)改分時圖同款配色 — net>0 段紅、net<0 段綠(線 + 面積,沿 StockIntradayChart 昨收平盤上下裁切填色手法),取代現在單色 `stroke-accent`(AdvanceDeclineChart.tsx:131) |
| D7 | 相關係數頂層 tab 位置 | 台股綜合之後第 2 顆 / 最後一顆 | **第 2 顆**(市場級視圖相鄰) | **最後一顆**(台股綜合 \| 個股(期) \| 選擇權 \| 期貨 \| 相關係數) |
| D8 | 家數帶上漲/下跌桶維持 PR #53 字色(紅字/綠字),只把停板兩桶改實心白字 | 是 / 否 | **是** | 是 |
| D9 | 交易日曆來源 | (a) 週末規則 + `configs/trading_holidays.json`(TWSE 年度休市表,年更;缺當年 → 只擋週末 + WARNING);(b) TC4 IX0001 DK 最後一根日期探測 | **(a)** 主 + (b) 作 boot 時交叉檢查(DK 最後一根 > 日曆算出的最近交易日 → WARNING 日曆過期) | (a)+(b) |
| D10 | 刪除時 `isMarketKind` 前端防禦碼 / `?market=` 參數 | 一併清 / 留 | **一併清**(user:「清乾淨」) | **清,且 user 強調「查清楚,不留任何死碼」** → R1 成功條件加:刪後全庫 grep 死碼證據 + `npx tsc -b`/pyright unused 檢查 + 手動核每個被刪函式的 caller 為零 |

## 2. 六輪 prompt 全文

---
### R1 `/mod 刪除台股綜合「類股強弱」與「訊號時間軸」(含後端 API/poller/快取)清乾淨`

```
/mod 刪除台股綜合「類股強弱」與「訊號時間軸」兩個 subtab,含後端 API、poller、快取、config、
verify 注入通道,清乾淨不留資源占用。

已調研事實(current-state 直接沿用,仍要 grep 一次驗證行號未漂):
【前端整檔刪】components/index/SectorSection.tsx(+.test)、SignalTimelineSection.tsx(+.test)、
lib/sector-model.ts(+.test)。
【前端局部】IndexPage.tsx:21-22 import、:39-44 SUBTABS 刪 sector/timeline 只留 limit/corr、
:222/:226 render 分支、檔頭 docstring;lib/constants.ts:82 INDEX_SUBTAB_KEY 值域註解;
lib/signal-model.ts:19-20 SignalKind market_* / :24-31 isMarketKind / :93-96 kindLabel 分支;
hooks/useSignalFeed.ts:23,25,43-50 MarketMode/mergeByFamily/FAMILY_CAP(只有 timeline 用 include)
→ 收斂回單純 mergeSignals,`?market=` 查參一併移除(D10 拍板:清);hooks/useSignalAlerts.ts:89。
測試:App.test.tsx SECTOR_STATE fixture/:131,134 mock/:306-313 openSectorMember/:325,360-374/
:600/:308,365,607,609;IndexPage.test.tsx:338(s2)/:352(s2b)/:124,127 mock;
StockPage.test.tsx:535-539(市場事件不進個股 rail — 資料源消失後改為刪除);
signal-model.test.ts kindLabel market 案例 + isMarketKind describe。
【後端整檔刪】copycat/sector_rotation.py、server/chain_store.py、tests/test_sector_rotation.py、
tests/server/test_chain_store.py。
【後端 app.py】刪 GET /api/market/sector(:1428-1446)、/api/market/sector/members(:1448-1467);
/api/stock/signals/today(:1082-1096)route 保留但 `market` 參數 + _is_market_kind/
_MARKET_KIND_PREFIX(:109-117)刪;fetchers 第 5 槽 chain_fetch(:726,:750-751,:763)刪 →
BreadthFetchers 5 元組縮 4 元組(連動 verify.fake_breadth_fetchers 與 TestFetchersArity);
breadth.attach_signal_hub/detach_signal_hub(:781-782,:820-828)刪;註解 :109-111/:165-168/:776-780。
【breadth_engine.py】刪:ChainFetch(:143)、_chain_*/_rotation/_universe_rows(:266-277)、
sector_state(:405-418)、sector_members(:420-428)、_recompute_rotation(:679-702)、
_chain_path/_restore_chain/_maybe_arm_chain/_refresh_chain(:846-987)、_CHAIN_FILE(:131)、
_MARKET_LOCK/_MARKET_OPEN(:136-137)、MarketSignalSink(:146-158)、_mkt_*/_signal_hub(:279-290)、
attach/detach_signal_hub(:320-325)、_diff_limit_events(:722-811)、_apply 尾端 try(:672-677)、
建構子 chain_fetch(:217,:230)、start/close 的 chain 收攤(:338,:344/347)、
normalize_universe_rows 寫入(:657;market_breadth.normalize_universe_rows 若無他人用一併刪)。
**保留**:家數/序列/對照表/退避核心、連板 streak 整組(:107-127,:989-1294)、state()/rows_state()。
【breadth_fetch.py】刪 fetch_industry_chain(:113-119)+_CHAIN_DATASET/CHAIN_MIN_ROWS(:36,:52)+
tests TestIndustryChainRowCountLog(:327-);**保留** fetch_snapshot/fetch_stock_info/
fetch_disposition/fetch_daily_prices(streak 用)。
【breadth_config.py】刪 chain_ttl_hours(:31)、event_cooldown_secs(:30)+ 驗證(:47-54);
tests/test_breadth_config.py 對應。**注意** configs/breadth.json 若本機存在且仍寫這兩鍵,
load_dataclass_json 未知鍵會 raise → verification 節要實查本機 configs/ 並在 PR 說明提醒。
【signal_hub.py】刪 _MARKET_LOCK/_MARKET_OPEN/_MARKET_RULE_TAG(:110-112)、_kind_text market
分支(:140-143)、publish_market_events(:769-821)、market_event_state(:823-845)、
_market_date_warned(:248);雙佇列/Discord worker/節流/jsonl 全保留。
【__main__.py】刪 VERIFY_FAIL_DATA_DIR(:60)、_clear_chain_cache(:140-152)、呼叫(:178-179)。
【verify.py】刪 _BREADTH_CHAIN(:171-178)、FLIP_ENV_KEY(:194)、_FLIP_1101(:199)、
_flip_locked(:221-228)、_industry_chain(:329-335)、_snapshot 內 FLIP 分支(:287-289);
tests/server/test_verify.py 核對。
【測試 class 刪】test_breadth_engine.py TestMarketLimitEvents(:2586-2953)/TestChainCache(:1934-2264)/
TestSectorState(:2264-2586);test_breadth_routes.py TestSectorRest(:538-600)/TestSectorMembers
(:600-680)/TestSignalHubWiring(:680-735);TestFetchersArity 改 4 元組。
【文件】CLAUDE.md:64-66 breadth_engine 說明、:70 sector_rotation.py 行;
docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md:166 起 R4 節加「2026-08-15
已刪除」註記(spec 是決策記錄不砍);docs/next-time.md:189-213 整段 + :1089/:1123/:1126 標過期;
.claude/skills/finmind-conventions/SKILL.md:26-27 TaiwanStockIndustryChain 條目標「已不接」。
【磁碟】data/ 下 chain cache 檔(CHAIN_FILENAME)verification 節列出路徑,PR 說明提醒可手刪。

白名單(不能破壞):家數帶 + 騰落線 + /api/market/breadth + /ws/breadth;漲跌停列表 + 連板 +
/api/market/breadth/rows;個股訊號 rail/toast/Discord 推送 + /api/stock/signals/today(無 market
參數);相關係數 subtab(R2 才移動);INDEX_SUBTAB_KEY 舊值 sector/timeline 被白名單擋回 limit
(零遷移)。
成功條件:pytest/ruff/pyright/validate 全綠;**死碼零容忍(user 拍板 D10)**:`grep -rn
"sector\|chain\|market_limit\|market_kind\|timeline\|rotation\|industry" copycat frontend/src tests`
只剩無關命中(逐條列出並說明為何無關);每個被刪符號在刪除前先 grep caller 清單為零才刪;
ruff `F401/F811` + pyright unused + `npx tsc -b` + eslint no-unused-vars 全淨;verification.md 附
上述 grep 輸出當證據;verify server 起得來且家數帶/漲跌停/corr 正常;
--verify 走一輪 breadth 失效注入(VERIFY_BREADTH_FAIL=1)仍降級不炸。
三類:🔴 刪除為一批(前端一 commit、後端一 commit)+ 🔵 4 元組收斂與 docstring 同步獨立 commit。
```

---
### R2 `/mod 台股綜合一頁總覽:左欄雙圖+家數帶壓縮、右欄漲跌停列表、相關係數升頂層 tab、家數帶停板實心色`

```
/mod 台股綜合改「一頁總覽」佈局:加權/櫃買/漲跌家數往左壓縮,漲跌停個股列表移到右欄整高,
單螢幕不捲動;相關係數自 subtab 升為頂層 tab;家數帶漲停/跌停桶底色改與個股期漲停色同款實心。
**前置:R1 已 merge**(subtab 只剩 limit/corr)。

UI 輪:載入 frontend-design + bencium-controlled-ux-designer;既有 token 內做(--color-bull/
--color-bear、border-line/bg-surface),不加字體/動效/新色。change-spec 的畫面章節附三案 ASCII
草圖(A/B/C 見拍板 D6),D6 未答走 A。

已調研事實:
【頂層 tab】App.tsx:35 `type Tab`、:49-52 initialTab 白名單、:198-204 tab 陣列
(index/stock/txo/futures)、:230 起各 tab hidden 分支、:44-48 檔頭載明 corr 於 R1 移出;
測試 App.test.tsx:433-444 鎖順序(該紅)。相關係數目前 = IndexPage.tsx:39-44 SUBTABS 的 corr
+ :227 <CorrSection/>;測試 IndexPage.test.tsx:318-329 鎖 subtab 順序(該紅)、
IndexPage.corr-lazy.test.tsx(搬到 App 層或改寫)。CorrPage.tsx vs CorrSection.tsx 哪個可獨立
掛頂層先確認。D7 拍板:放最後一顆(期貨之後);initialTab 白名單放行 "corr"。
subtab 拿掉 corr 與 limit 後只剩 0 個 → **整個 subtab 機制與 INDEX_SUBTAB_KEY 退役**
(key 進 ORPHAN_STORAGE_KEYS purge,沿 constants.ts:30-31 慣例);LimitListSection 的 active
prop(:121-126 輪詢 gate)改綁 App 層 tab==="index"(IndexPage.tsx:126 的 active)。
【佈局】IndexPage.tsx:152-153 最外層 `overflow-y-auto`(改為固定視高、子區各自 overflow);
:154 BasisRow;:155-179 雙圖 `grid-cols-[repeat(auto-fit,minmax(480px,1fr))]`;:180-185 家數帶
+ 騰落線;:186-228 subtab 容器。MarketPane.tsx:21 SIZE 640×220 固定 viewBox、:358-360 註解
「刻意不撐滿」→ 左欄高度預算重估(圖高改依容器,useContainerSize 專案已有 hook)。
LimitListSection.tsx:389 只有 overflow-x-auto、無 max-h → 右欄需 min-h-0 + overflow-y-auto。
【家數帶】BreadthBand.tsx:23-34 BUCKETS:limit_up tone "border-bull/40 bg-bull/15"(:29)、
limit_down "border-bear/40 bg-bear/15"(:33)→ 改實心 `bg-bull text-white`/`bg-bear text-white`
(個股期三處同款:WatchlistSidebar.tsx:405-406 / StockPage.tsx:276-277 / OrderBook.tsx:192-193);
D8 default:up/down 桶維持字色不動;檔頭 :6-13「染色與底色互斥」註解同步。

白名單:BasisRow、雙圖內容與 overlay(PR #52)、家數帶數值/字色、騰落線、漲跌停列表所有欄與
onOpenStock 跳個股、corr 頁功能(只是搬家)、其他三個頂層 tab 順序不動、視窗 <~1200px 時
grid 自動退回上下堆疊(auto-fit 語意保留或明訂新斷點,寫進 spec)。
成功條件(畫面可指認):1920×1080 與 1536×864 兩種常見視窗下整頁無垂直捲軸,列表在右欄
內捲;頂層 tab 列 = 台股綜合|個股(期)|選擇權|期貨|相關係數;家數帶漲停桶為實心紅底白字;騰落線漲多段紅、跌多段綠。
截圖走 claude-in-chrome 既有 session(記憶 ui-testing-claude-in-chrome),兩種視窗各一張。
三類:🔵 subtab 退役/active 改綁 → 🔴 佈局與配色 → 🟢 corr 頂層 tab。
```

---
### R3 `/mod 引入交易日曆:非交易日自動以最近交易日為 trade_date(個股/群組分時圖 + 台股綜合)`

```
/mod 引入台股交易日曆,非交易日(週末/國定假日)開啟頁面時個股(期)單檔與群組分時圖、
台股綜合加權/櫃買分時圖與家數帶/漲跌停列表一律顯示最近一個交易日的資料,不再依賴手動
TXO_BACKFILL_DATE。

已調研事實(根因):全庫**沒有交易日曆**(docs/next-time.md:78-79、:512 均自承);
app.py:470-473 _make_stock / :603-610 IndexEngine / :304 TXO / :351 SignalHub fallback 都是
`trade_date = TXO_BACKFILL_DATE or date.today()`;stock_engine._checkpoint_loop:838-851 只有
`weekday()<5`;index_engine._rollover_loop:431-462 純日曆日比較(週末 pending 永不 swap 但
凍結上一交易日 — 副作用非設計;冷啟動在假日則空圖);breadth_engine._apply:596-668 靠 FinMind
回上一交易日快照被動繼承日期(冷啟動假日 counts 對但分鐘序列空,因 _append:704 要
trade_date==today_fn());_in_window:829-831 假日仍每 10s 空打 FinMind;streak(:991-1199)已用
空回應跳假日;/api/stock/bars|overlay(app.py:1045,1061)用真牆鐘、K 線不受影響(兩條日期邏輯
獨立,spec 要寫明別誤改);TXO_BACKFILL_DATE 讀取點總表:app.py:304/351/396/470-475/603-610、
live/tc4.py:407。前端 trading-hours.ts:14-47 只擋週末(:12/:24/:39 註解已預留)。

設計(D9 default):新純模組 `copycat/trading_calendar.py`(零 IO):`is_trading_day(d, holidays)`
/ `last_trading_day(today, holidays)`;holidays 來自 `configs/trading_holidays.json`(TWSE 年度
休市日;缺當年 → 只擋週末 + 啟動 WARNING 一次);`resolve_trade_date(now, holidays)`:非交易日
或交易日 08:30 前 → 最近交易日?(**注意**:交易日盤前是否要顯示前一日,依現行 stock_engine
兩段式 rollover「假日不清空/收到首 tick 才 stage2」語意,盤前本就顯示昨日 → 只需處理
「今天非交易日」情境,盤前不動)。app.py 三個 engine 的 trade_date 初始化改吃 resolve;
TXO_BACKFILL_DATE 仍為最高優先覆寫(ops 手動通道保留,CLAUDE.md §1 表格文字同步);
index_engine._rollover_loop 與 stock_engine._checkpoint_loop 的「新日」判定改 is_trading_day;
breadth_engine today_fn 注入改為交易日 today(冷啟動假日可 _restore 上一交易日序列)、
_in_window 加交易日檢查;boot 交叉檢查:IX0001 DK 最後一根日期 > 日曆最近交易日 → WARNING
「日曆可能過期」(tc4-market-facts:IX0001 DK 748 根可用)。/api/health 加 `trade_date` +
`calendar_year_loaded` 供驗證。前端 trading-hours.ts 三支接 /api/health(或新 /api/calendar)
的假日集合 → 順帶根治 next-time:512(同根因、同一份日曆,不算 scope 擴張;若 review 判 L 過大
可拆成 R3b 獨立輪)。LimitListSection.tsx:331 「今日尚無漲跌停」帶 trade_date 文案。

白名單:交易日盤中一切不變(trade_date 仍是今天;rollover 兩段式語意不變);TXO_BACKFILL_DATE
手動模式仍可用且優先;K 線 endpoint 日期邏輯不動;breadth streak 現有假日跳過邏輯不動;
FinMind 配額不增(assert 假日 poll 次數下降)。
成功條件:pytest 新增 trading_calendar 純測 + 三 engine 假日冷啟動測(today_fn 注入週六 →
trade_date=週五、index minutes 回補非空、breadth _restore 週五序列);真實環境:週六/日或
下個國定假日重啟 server 不帶 env,curl /api/health 看 trade_date,三頁分時圖非空截圖。
三類:🟢 trading_calendar + config → 🔴 engine 初始化/rollover/_in_window 改判 → 🔵 文案。
```

---
### R4 `/mod 群組圖牆分時圖改用單檔同款分時圖(overlay/toggle 全同)+ 點卡片只切閃電目標不跳單檔`

```
/mod 個股(期)群組檢視:(a) 圖牆每張卡的分時圖改與單檔分時圖一模一樣(VWAP/CDP/MA/VP+POC/
高低點/軸標籤/hover 讀值/toggle 共用同一份 useChartToggles);(b) 點卡片只更新閃電下單目標
(stockCode),不再自動切回單檔檢視,卡片顯示選中態。

UI 輪:載入 frontend-design + bencium-controlled-ux-designer;D4 default (a) 完全同款,toggle
列在圖牆頂放一份;D3 default (a) 進單檔只靠檢視 pill。

已調研事實:MiniIntradayChart.tsx(195 行,MINI_W=220/MINI_H=76,無 toggle、無 overlay、
無副圖、無軸、無讀值)與 StockIntradayChart.tsx(1009 行)是兩個實作,只共用
lib/stock-intraday-svg.ts buildIntradayGeometry;差異表:VWAP(:347,:439-459)、MA 標籤(:423-437)、
CDP(useStockOverlay,:631-634,679,690)、VP+POC(:191-192,:291-301,:458-472)、toggleDefs(:775-807)、
ChartReadout(:637,:708-771)、軸(XAxisLabels/edgePriceLabels)、高低點(:719-720,:384-421)、
現價圈(:722-725)、副圖量能(:658-661,:954)、stkfut 期貨態(:607-612)。toggle 存放:
hooks/useChartToggles.ts(localStorage CHART_TOGGLES_KEY constants.ts:94,{vwap,cdp,ma,bb,vp}),
StockChart.tsx:61 與 StockIntradayChart.tsx:616 同時存活用 set() 重讀合併(:78-86)— 圖牆
16 張同時掛也走同一機制,spec 要評估 16 個 hook 實例互寫是否有競態(建議 toggle 狀態上提到
GroupGridView 一份,卡片以 props 接收)。資料:群組用 /api/stock/group-state(app.py:1203-1231,
唯讀不 set_main),CDP/MA 需每卡打 /api/stock/overlay/{code}(app.py:1040-1078;後端有 cache、
已完成 bar 剔除/don't-cache-empty)→ 16 卡 16 請求量測落 verification。GroupGridView.tsx:106-147
GroupCard memo(:149-166 pickRef 穩定化,別打破)。點擊鏈:GroupCard button :126-131 →
StockPage.tsx:213-223 `onSelect(picked); selectView("single")` → App.tsx:106 stockCode →
railCtx(App.tsx:177-190)→ RightRail ladder 目標;useStockStream 觸發 /api/stock/state 的
set_main_contract。測試該紅:StockPage.test.tsx:704-714(點卡片自動切單檔);
GroupGridView.test.tsx:418-427 保留;新增:點卡片後 railCtx.code 換新股號(現無端到端鎖,
App.test 補)、卡片 aria-pressed/選中態、toggle 切換 16 卡同步。

方案建議:StockIntradayChart 加 `variant="card"` prop(字級/邊距縮放、readout 精簡為一列),
GroupGridView 直接掛它、MiniIntradayChart 退役(或留給其他 caller — grep 確認無他人)。
白名單:矩陣佈局(PR #50 2×2~4×4/佔滿中區/pill 群組切換/STOCK_GROUP_KEY 記憶)、單檔頁分時圖
一切不變、右欄 ladder 三梯互斥掛載、群組檢視不渲染五檔/明細/header(StockPage.test:680-681)、
onSelect 仍觸發主圖訂閱換檔。
成功條件(畫面可指認):圖牆卡片有 VWAP/MA/CDP 線與價位標籤、VP 條與 POC、高低點,單檔頁
切 toggle → 圖牆同步;點卡片:卡片出現選中框、右欄閃電梯標的代號變更、檢視仍停在「群組」。
三類:🔵 StockIntradayChart variant 化(行為不變、單檔頁截圖前後對照)→ 🔴 圖牆換元件 +
點卡片不跳單檔 → 🟢 選中態視覺 + toggle 列。
```

---
### R5 `/mod 閃電下單「鎖定武裝」:一鍵鎖定後跨標的/跨梯/閒置不再需要重按武裝`

```
/mod 閃電下單三座梯加「鎖定」:按下後全程武裝,換標的、換梯(現股↔個股期↔期貨)、閒置 5 分
都不再解除;仍受 WS 斷線 / 連 3 敗 / Esc / 手動解除 / 頁面 reload 解除(D1 default a;D2 default
不持久化)。安全敏感:change-spec 必含「鎖定下誤觸」風險節,reviewer 帶 security lens。

已調研事實:狀態機 lib/flash-arm.ts(ArmState{armed,failStreak}:6-9;事件 :11-18;
reduceArm :24-41;ARM_IDLE_MS :3;FAIL_LIMIT :4);**非共用 hook,三梯各自** useReducer:
PriceLadder.tsx:168 / StkfutLadder.tsx:87 / FuturesLadder.tsx:62;複製貼上的 effect:換標的
(PriceLadder:280-282 依 code / Stkfut:206-208 依 instrumentKey / Futures:232-234 依 product
+ :237-239 合約失解析)、conn_lost(:285-287/:211-213/:241-244)、Esc(:290-297/:216-223/:246-254)、
idle touchIdle(:210-216/:137-143/:130-136)、send_ok/fail(:256-270/:182-196/:174-188,mutateAsync
自接 then/catch 原因見 PriceLadder:243-244);unmount=解除靠 RightRail 互斥掛載
(RightRail.tsx:133-185 三分支)。武裝鈕:LadderView.tsx:184-201(Price/Stkfut 共用,props
:64-83);FuturesLadder.tsx:304-325 自帶第三份同款 JSX。後端 safety.py 完全不感知武裝
(只看 CAPITAL_ORDER_ENABLED/max_qty/max_amount;models.py:53 source="flash" 只稽核)→ 後端不動;
若要稽核鎖定態,payload source 可擴 "flash-locked"(拍板:預設不擴,寫 next-time)。
現有測試:flash-arm.test.ts 6 案;PriceLadder.test:290,317,353,362,370,380,437;
StkfutLadder.test:219,243,257,266(缺 Esc/idle/連敗 三條 — 本輪順便補齊屬 🟢 測試,不算
scope 擴張);FuturesLadder.test:136,183,198,234,243,255,267,623;RightRail.test:183,197,210,371
(換梯不殘留 → 鎖定時該變,未鎖定時不該變);next-time.md:152-156「窗開著 Esc 不解武裝」
既有語意保留。

設計:🔵 先把 arm 狀態上提為單一 `useFlashArm` 共用 hook/context(App 或 RightRail 層,三梯
以 props/context 接),行為零變(三梯測試全綠、RightRail 換梯不殘留照舊);🟢 再加 `locked`
旗標:reduceArm 加事件 `lock`/`unlock`,`locked` 下 idle_timeout/symbol_changed 為 no-op、
換梯不 unmount 狀態(狀態在上層所以天然保留),conn_lost/send_fail×3/disarm(Esc/手動)一律
解除且同時清 locked;鎖定鈕與武裝鈕並列(LadderView + FuturesLadder 兩處;鎖定態視覺要一眼
可辨,e.g. 武裝鈕保持 pressed 且標籤「鎖定中」— 用既有 accent token,bencium 協定:spec 附
兩案讓 user 選)。
白名單:未鎖定時三梯行為與現在逐條相同(六個 flash-arm 測試 + 三梯測試不動);安全閘後端
不動;無券鎖買側、當沖 checkbox、QTY_PRESETS 不動;source="flash" 稽核不變。
成功條件:鎖定後換自選股 → 梯仍武裝可點價;鎖定後現股切個股期合約(換梯)→ 仍武裝;
放置 6 分鐘仍武裝;拔 TC4/WS 斷線 → 解除且鎖定清除;Esc → 解除;reload → 未武裝未鎖定。
真實環境走群益 test 未開通 → 用 CAPITAL_ORDER_ENABLED=false 讓送單被總開關擋,只驗武裝態
機與 UI(不真送單)。三類:🔵 上提 → 🟢 lock → 🔴(若 RightRail 測試語意調整)。
```

---
### R6 `/mod 個股頁兩件小 UI:交易別 select 改四顆按鈕 + 自選群組列右側平均漲幅`

```
/mod 個股(期)兩件互不相干的 S 級 UI(同輪、分 commit):
(a) 閃電梯交易別「現股/融資/融券/無券」由 <select> 改四顆並列按鈕(pill,單選);
(b) 自選清單每個群組標題列組名右側顯示該群組等權平均漲幅(未分組不顯示)。
UI 輪:載入 frontend-design + bencium-controlled-ux-designer;沿既有 pill 樣板不另造。

(a) 事實:PriceLadder.tsx:39-44 TRADE_KINDS(cash/margin/short/daytrade_sell — 「無券」就是
daytrade_sell,非第五值)、:378-393 <select aria-label="交易別"> 受控 tradeKind(可由 RightRail
經 tradeKind/onTradeKind 上提,Props :146-149)、:325 buyLocked={tradeKind==="daytrade_sell"}
與 :227 雙保險、:52-54 kindLabel;資料流 types.ts:118-127 → useCapital.ts:190-191 →
capital_api.py:70,227-234 → models.py:16 → mapping.py:52,196 sFlag(全鏈不動,純 UI);
測試 PriceLadder.test.tsx:391-407(無券鎖買側,查詢方式若靠 select role 該變)。pill 樣板:
StockPage.tsx:189-208(aria-pressed + border-accent/text-accent vs border-line/text-ink-dim)、
GroupGridView.tsx:187-207(容器 role="group"+aria-label);Stkfut/Futures 梯是「當沖」checkbox
不在範圍。
(b) 事實:WatchlistSidebar.tsx:294-333 sectionHeader(順序 摺疊指示 :326-328 → 組名 :329 →
檔數 :330;插入點在 :330 前)、呼叫點未分組 :578-584(不傳)/群組 :621-627(傳 avgPct);
stockRow :335-498 用 quotes[code](props,來源 useStockStream.ts:100 watchlist state,WS
watchlist_quote :336-386;型別 :18-36 含 chg_pct、無 prev_close、ref 與 p 互斥不可算漲幅);
後端 stock_engine set_watchlist:381-420 全清單 refcount 訂閱(:416),收合不影響訂閱 → 純前端
`mean(codes.map(c=>quotes[c]?.chg_pct).filter(non-null))`,p==null 排除分母(D5);三態色沿
GroupGridView.tsx:69-76 / stockRow :411-431 同構規則;fmtPct(lib/format.ts);測試
WatchlistSidebar.test.tsx:570-620 標題列視覺 describe(新增案例避免 within(header).getByText
撞組名文字);wlReady/EMPTY_WL 危險窗不算數。
白名單:(a) trade_kind 送出值與無券鎖買側不變、tradeKind 上提/持久語意不變;(b) 群組展開
收合/全部展開/底色帶/檔數/上限 50 文案/拖曳排序等 PR #48 行為不變、未分組列無平均。
成功條件(畫面可指認):(a) 四顆按鈕單選、選「無券」買側鎖;(b) 群組列「組名 +x.xx% 檔數」
且色隨正負,無成交檔不入分母(測試以 quotes fixture 鎖)。
三類:🔴 (a) select→pill / 🟢 (b) 平均漲幅,各自 commit。
```

## 3. 執行備忘

- 每輪開跑前重 grep 一次行號(本檔行號為 2026-08-15 master `7704e5ab` 快照)。
- R2 依賴 R1;R3/R4/R5/R6 可並行 worktree(記憶 mutation-reviewers-serial 與 ops-discipline
  三險照過)。
- 完成一輪:勾銷本檔 §0 對應列 + memory `user-feedback-batch-2026-08-15` 對應條。
