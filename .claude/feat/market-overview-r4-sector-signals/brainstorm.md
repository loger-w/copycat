# R4 類股強弱 + 訊號事件流 — brainstorm(Phase 0)

日期:2026-08-06。總 spec:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 4
(D-1~D-7 已拍板不重議;user 指示「照總 spec §5 Round 4 做,open question 5 於 Phase 0 拍板」)。

## 0. 分流判定記錄

**已成形方案**:條件 1 中(spec 指名資料流 — sector_rotation 搬移 / signal_hub 單一匯流排 /
breadth diff 事件源 / 前端時間軸欄)+ 條件 2 中(open question 5 dedup 鍵、接線形式等
可拷問決策點)→ grilling 姿態,逐題附建議解 `[auto-default]`。無方向性抉擇
(全部決策不改寫 SC 集合、不動對外契約方向),未停等 user。

## 1. Phase 0 事實自查(拷問前提)

- **neigui 有兩套 sector 邏輯**:(A) `compute_sector_rotation`(market_today.py:277,
  吃 `TaiwanStockIndustryChain` chain_map,三層展開清單)/(B) `sector_aggregation.py`
  (只在 worktree、吃 `industry_category`)。總 spec D-3 指名的是 (A)。
- **copycat 已在手的 `dedup_sector_map` + `PRIMARY_INDUSTRY_OVERRIDE`(R2 搬入)屬於
  另一條鏈路**(universe 白名單),與 rotation 的 chain_map 無關 — spec §5 R4「含
  industry override 表」的記載對 (A) 不適用,幽靈 sector 守門測試 R2 已入
  (`tests/test_market_breadth.py`),本輪零重複工作。
- **`TaiwanStockIndustryChain` 實跑 probe(2026-08-06)**:6861 rows / 47 industries /
  512 subs,欄位 `date/industry/stock_id/sub_industry`;一檔可屬多產業(2317 落 4 個
  industry)、同 industry 多 sub(`_dedup_ids` 聯集去重涵蓋);1 request 回全表。
  probe:scratchpad `probe_industry_chain.py`。
- **breadth_engine 無對外 hook**(grep attach/callback 零命中);stock_engine 有
  `attach_signal_hub`/`detach_signal_hub` 前例(app.py:498/:508)。
- **`compute_breadth` rows 已帶 `limit_up/limit_down/touched_limit_up/touched_limit_down`**
  (market_breadth.py:362-376)→ diff 事件源直接對相鄰兩輪旗標做轉移偵測。
- **`SignalHub` 事件 id 決定性鍵** `trade_date-rule_id-code-kind-tag-time_key`
  (signal_hub.py:867);jsonl 落 `data/signals/<YYYYMMDD>.jsonl`;
  `GET /api/stock/signals/today` 已存在(app.py:982)。
- **訊號 WS 走 `/ws/stock`**(`case "signal"` → module-level bus);`useStockStream`
  無 tab active gate,全 tab 常駐連線 → index tab 的時間軸可直接吃同一條 bus。
- **`useSignalFeed` 無 kind 過濾** → market 事件會流入個股頁 SignalRail,需本輪加過濾。
- `compute_sector_rotation` 需要 raw `total_volume/yesterday_volume` — 在 assembled
  universe rows(compute_breadth 的輸入)有,rows_out 沒有 → engine 端要餵前者。

## 2. 拍板決策(grilling 決策樹)

### Q1 類股強弱搬哪套?chain_map 資料路徑?
[auto-default: 忠實搬 (A) `compute_sector_rotation` + `compute_sector_members`,新增
`TaiwanStockIndustryChain` 取數 + 7 天 disk cache(沿 neigui `_CHAIN_TTL_HOURS=168`)
| reason: D-2/D-3 拍板「搬 neigui 不重新發明」;(B) 不在 main 分支且非 spec 所指;
新 dataset 成本 1 req / 7 天,配額可忽略;D-3 理由(universe snapshot 供價格輸入、
涵蓋上櫃)不因 chain_map 靜態表而失效]

### Q2 chain cache 落點與失敗降級?
[auto-default: `data/market/industry_chain.json`(`{_version, fetched_at, rows}` 原子寫,
沿 breadth 落檔慣例);過期時盤中重抓一次、失敗沿用舊檔(stale 可用勝於 None)、
連舊檔都無 → rotation=null 降級,家數/列表零波及 | reason: 靜態表 stale 一週內無害;
失效域隔離沿總 spec §3]

### Q3 rotation 計算掛哪 + 對外形狀?
[auto-default: `_run_cycle` 內以 assembled universe rows 算 rotation 存 engine;
REST `GET /api/market/sector`(`{enabled, trade_date, as_of, stale, rotation|null}`)+
`GET /api/market/sector/members?industry=&sub=`(lazy drill-down,未知 sector →
404 `{detail:{error:"SECTOR_NOT_FOUND"}}`);前端展開時輪詢 + hidden tab active gate
(R3 rows 同款),不加 WS | reason: 10s 慢變量,REST 輪詢已是 rows 前例;
rotation payload 中等(47 industries)不宜塞進 /ws/breadth 每輪廣播]

### Q4(open question 5a)鎖板/開板事件的 dedup 鍵?
[auto-default: **轉移偵測 latch + 決定性 id + 重啟 baseline**三件套:
(i) engine 持 per-code 漲/跌停 latch,相鄰兩輪旗標轉移才發事件(lock: false→true,
open: true→false);(ii) id = `{trade_date}-breadth-{code}-{kind}-{direction}-{as_of}`
(rule_id 段固定 `breadth`,time_key = 該輪 as_of,與 hub 既有 id 文法同構);
(iii) server 重啟後首輪成功 poll 只建 baseline 不發事件(SignalDetector 首 tick
慣例)→ 重啟不重發已鎖檔;(iv) 抖動抑制:per (code, kind, direction) cooldown
預設 600s(`configs/breadth.json` 新鍵 `event_cooldown_secs`,分桶語意沿
signal_state 2026-08-04 amendment — lock/open 各自桶,不吃掉鎖後真打開)
| reason: 與自選池 limit_lock 語意對齊;決定性 id 讓 jsonl 重讀 / 前端去重穩定;
baseline 抑制把重啟 spam 整類消掉]

[amendment 2026-08-06: design review R1/R5/R6 — (i) 靜默 baseline 改為 **jsonl 回放
seed + last_emitted 對帳制**:開盤即鎖首輪即發 lock(原設計把一價到底整類吞掉)、
冷卻只延後對帳不丟棄(終態收斂)、重啟 seed 回放不重發不漏發;(ii) diff gate 改
「_append 非 None」(分鐘域 09:00–13:30,消掉盤前試撮殘留分支);(iii) rows 加
`limit_judged`,缺欄輪不產假 open。詳 design.md §6。]

### Q5(open question 5b)「觸及未鎖」算不算事件?
[auto-default: 不算,記 next-time | reason: `touched_*` 是由 high/low 導出的**當日
不可逆 latch**,「首次觸及」之後整天為真,轉移語意弱;鎖後打開已由 open 事件涵蓋,
再發 touched 事件是同一資訊二發;首觸未鎖屬高噪音(邊緣股整天反覆),列表的
touched 欄(R3)已可指認。SC 集合維持 spec 草案不變]

### Q6 事件 kind 命名與來源精度標注?
[auto-default: 新 kind 字串 `market_limit_lock` / `market_limit_open`(不覆用
`limit_lock`/`limit_open`),payload 形狀同 SignalMsg(無 rule_id/rule_name);
前端以 kind 前綴識別 → 時間軸列帶「廣度」badge(FinMind 5-10s 精度),
tooltip 註記與 TC4 tick 級之別 | reason: kind 即自帶來源語意,免加 optional source
欄讓兩端判斷分岔;與自選池同 code 同刻雙發(tick 級 + 廣度級)是兩個不同 id
的兩則,不互斥 — 精度標注讓 user 可辨]

### Q7 事件怎麼進 hub?Discord?
[auto-default: breadth_engine 加 `attach_signal_hub`/`detach_signal_hub`(鏡射
stock_engine 前例);hub 加 `publish_market_events(events)` 新入口 — 繞過規則
slots,WS publish + jsonl enqueue,**硬性 notify=False**(v1 無 Discord 開關);
trade_date 與 jsonl 檔名用 hub `_trade_date_fn()`(與自選訊號同源,檔案不分岔);
never-raise(事件層壞掉不得汙染 poll loop)| reason: D-6 單一匯流排 + 預設不進
Discord;attach 前例已驗證關機順序紀律]

### Q8 前端時間軸與類股面板的落點?
[auto-default: IndexPage 下方新增兩個獨立收合區塊(`LimitListSection` 同款 pattern:
localStorage open key、收合 = unmount):「類股強弱」三層展開清單(產業列 =
名稱 + 家數 + 平均漲跌% 著色 + 量比;點開子產業;成員列點擊跳個股)與
「訊號時間軸」(時間倒序、kind 篩選 chips、點列跳個股);時間軸資料 = 既有
`/api/stock/signals/today` baseline + signal bus live(重用 useSignalFeed 合成邏輯);
展開態 useState 不持久化(copycat 無 sessionStorage 慣例)| reason: R1-R3 已定型的
區塊慣例;spec 的 `GET /api/signals/today` 由既有端點滿足,不另開路由]

### Q9 SignalRail 汙染防治?
[auto-default: `useSignalFeed` 加 kind 過濾參數(SignalRail 排除 `market_*`,
時間軸全收)| reason: 個股頁訊號欄語意是自選池個股訊號,全市場鎖板一天可達
數十則,不濾則 rail 被洗版]

[amendment 2026-08-06: design review R2/R3 — 過濾必須在 feed 層 **cap 200 之前**
(mergeSignals 先截斷會讓 market 事件擠掉自選訊號);且 `useSignalAlerts`
(toast/beep/桌面通知)同樣要以 `isMarketKind` 早退 — SC-8 範圍擴為「rail 與
toast/通知皆不出現 market_*」。]

## 3. SC gate(成功條件)

- **SC-1 rotation 純函式 parity**:`compute_sector_rotation` / `compute_sector_members`
  搬移(邏輯全等、適配 copycat),neigui `test_market_today.py:239-360` 測試等價搬 +
  手算 fixture 全綠。驗證:`.venv\Scripts\python -m pytest -q tests/test_sector_rotation.py`
  (窗口:anytime)。
- **SC-2 chain 取數 + 快取**:`TaiwanStockIndustryChain` 取數落
  `data/market/industry_chain.json`;過期重抓、失敗沿用舊檔、全無 → rotation=null;
  quota 402 分類沿 `BreadthFetchError`。驗證:pytest(fake fetch 三態)+ 側車 server
  真取數一次印 industries 數(窗口:anytime — EOD 靜態表盤外可驗)。
- **SC-3 類股面板畫面可指認**:綜合 tab 下方出現「類股強弱」收合區塊,展開後為
  產業清單,每列含產業名 + `(家數)` + 著色平均漲跌%(紅漲綠跌沿專案慣例)+ 量比;
  點產業列展開子產業;點成員列畫面切個股 tab 且主圖為該檔。驗證:vitest +
  AI 截圖(claude-in-chrome 開 vite dev)對照本表述 + user 過目雙層(窗口:anytime,
  fake/--verify 出畫面;盤中加強見 SC-4)。
- **SC-4 與 neigui 同時刻對照一致**:盤中同一分鐘取 neigui snapshot 的
  `sector_rotation.industries` 與 copycat `/api/market/sector`,產業排序全等、逐業
  `avg_change_rate` 差 ≤ 0.01pp(兩邊 poll 時刻差 ≤ 10s 之內的快照)。量法:側車
  server + curl 兩端 JSON 落檔 diff(窗口:**盤中**;窗外降級 = SC-1 fixture parity +
  以錄製的同一份 snapshot rows 餵兩邊純函式對照)。
- **SC-5 diff 事件源語意**[amendment 2026-08-06: 對帳制改版]:pytest fixture 輪替驗
  (a) lock→open→relock 三轉移各發一則、id 符合
  `{date}-breadth-{code}-{kind}-{direction}-{as_of}` 文法;(b) **開盤首輪已鎖檔
  發 lock**(seed 空);盤中重啟 jsonl seed 回放 → 已發布者不重發、停機期轉移補發;
  (c) cooldown 內同桶對帳延後、冷卻結束補發,終態收斂;對向桶不受影響;
  (d) `_apply` 失敗輪 / `limit_judged=False` 列不推進狀態、不產假事件
  (窗口:anytime)。
- **SC-6 單一匯流排 + Discord 隔離**:market 事件出現在當日 jsonl 與 WS publish,
  且 Discord 佇列零收件(pytest 斷言);`/api/stock/signals/today` 回傳含 market 事件
  (窗口:anytime)。
- **SC-7 時間軸畫面可指認**:綜合 tab 下方出現「訊號時間軸」收合區塊,展開後列
  時間倒序;每列含時刻、代號名稱、事件文字;market 事件列帶「廣度」標記;頂部
  kind 篩選 chips 點擊即過濾;點列切個股 tab 設主圖。自選池訊號與全市場鎖板事件
  同軸出現。驗證:vitest + AI 截圖 + user 過目(窗口:anytime — jsonl fixture 注入;
  盤中加強 = 真事件入軸)。
- **SC-8 SignalRail 不受汙染**[amendment 2026-08-06: 範圍擴大]:個股頁訊號欄、
  toast、聲響、桌面通知皆不出現 `market_*` 事件;過濾在 feed 層 cap 之前
  (250 則 market + 3 則自選 → rail 仍見那 3 則)(vitest;窗口:anytime)。

## 4. Edge cases(≥3)

1. **chain_map 全不可得**(無網 + 無舊檔):rotation=null,前端區塊顯示「資料未就緒」,
   家數/列表/事件流零波及(失效域隔離)。
2. **盤中重啟**:latch baseline 重建,已鎖檔不重發 lock;重啟期間漏掉的 open 不補發
   (可接受 — jsonl 缺角但無假事件)。
3. **停板邊緣抖動**(close 在停板價 ±1 tick 來回):cooldown 600s 上界 = 每桶每 600s
   一則;lock 桶與 open 桶互不干擾(鎖後 600s 內真打開不被吃)。
4. **換日**(breadth trade_date 三分法前進):latch 全清 + 重建 baseline,不把昨日
   鎖板帶進今日。
5. **同檔同刻雙發**(自選池 tick 級 + 廣度級):兩個不同 id 的兩則,時間軸都顯示、
   精度標記可辨;SignalRail 只顯示 tick 級那則。
6. **幽靈 industry**(chain_map 產業與 universe 無交集):members=0 → skip
   (neigui `_zero_members_industry_skipped` 既有行為,測試同搬)。
7. **髒 row 輪 / 統計全空輪**:`_apply` 失敗路徑不產 rows → 不 diff、latch 不推進。
8. **market 事件 code 非自選**:點擊跳轉走 `setStockCode` 任意代號既有路徑,可行。

## 5. Out of scope

- 「觸及未鎖」事件(Q5 拍板不做,記 next-time)。
- 大盤級衍生訊號(騰落背離、basis 突變)— 總 spec non-goal。
- market 事件的 Discord 開關 UI / 規則化(v1 硬性不進 Discord)。
- neigui (B) `sector_aggregation`(above_ma20 / amount share 熱力圖那套)。
- 時間軸的歷史日回看(只做當日;jsonl 按日分檔,回看留 next-time)。
- neigui 端任何改動(唯讀參照)。
- 期貨 tab 改動;個股 tab 除 SignalRail kind 過濾外零改動。

## 6. 執行約束(跨輪掃描 — R3 brainstorm §6 + 總 spec §6 + R2/R3 沉澱)

- 搬邏輯與測試不整檔貼(neigui httpx/async → copycat 慣例);寫 .py 前讀
  `backend-conventions`;FinMind 接入照 `finmind-conventions`(Bearer / 錯誤分類沿
  `breadth_fetch`;新 dataset 進 `_ATTEMPTS=2` / 402 quota 慣例)。
- 寫 frontend 前讀 `frontend-conventions` + `frontend-testing`;類股清單與時間軸為
  清單型 UI(非圖表)免過 `dataviz`;若後續加圖形元素再過。
- 盤中不起第二台連 TC4 的後端;HTTP 層驗證 `--verify`(port 8722);盤中真 FinMind
  驗證走側車 server 樣板(R2 實證,CLAUDE.md §8)。
- FinMind poller / hub 活在 server process → prod 生效需重啟,排盤後。
- 當日產物落檔防重啟歸零(chain cache 落檔;事件 jsonl 本身即落檔)。
- 新 WS 不開(本輪零新 WS endpoint);hub publish 沿既有 `/ws/stock` 路。
- 驗證指令不接 `| tail`;mutation 驗證防同秒 pycache(sleep 1)。
- 收尾 rebase 撞 `docs/next-time.md` 先 grep 同根因條目再新增。
- attach/detach 順序紀律:attach 必須在 hub start 之後、shutdown 先 detach 再 close
  (stock_engine 前例 app.py:494-508)。

## 7. 規模分流

**L**:≥5 檔(breadth_fetch 新 fetcher / sector_rotation 純函式新檔 / chain cache /
breadth_engine 編排+diff / signal_hub 新入口 / app routes / 前端兩區塊 + useSignalFeed
+ types),跨前後端。輪數同 M(2026-07-26 制)。
