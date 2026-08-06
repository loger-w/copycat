# Brainstorm — 台股綜合 R3:漲跌停列表 + 個股跳轉

日期:2026-08-06
上游:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 3
(D-1~D-7 已拍板不重議;user 指示「照總 spec §5 Round 3 做,open question 4 於 Phase 0 拍板」)

## 1. 分流判定記錄

**已成形方案**:條件 1 中(總 spec 指名資料流 = R2 breadth rows、UI 形式 = 列表 + 篩選、
跳轉機制 = setTab + setStockCode)、條件 2 中(連板數路徑 / rows 曝露面 / 觸及未鎖判定
落點皆為可拷問決策點)→ grilling 姿態。連板數路徑屬方向性抉擇(改寫 SC 集合),
已停下問 user 拍板;其餘決策 `[auto-default]`。

## 2. 決策記錄

### Q1 連板數欄位的資料路徑(總 spec open question 4)
**[user 拍板 2026-08-06:FinMind EOD 回看]** — 新增 `TaiwanStockPrice` 全市場 EOD 取數:
回看 10 交易日、每日一次快取落檔(`data/market/`)。漲停列顯示「連 N 板」
(N = 截至昨日連續漲停日數 + 今日)。成本:每日 ~10 request(配額近零)。
冷啟動即正確(相對「前向累積」的兩週不準期)。

### Q2 rows 曝露面形狀
[auto-default: REST `GET /api/market/breadth/rows`,不進 WS | reason: R2 Q7 同理由 —
WS 每 10s 推 ~2800 rows 是對非列表使用者的純浪費;REST + TanStack Query
refetchInterval(列表區可見才輪詢)讓頻寬跟著消費者走。rows 來源 = R2 已預留的
`breadth_engine.rows`(engine 內存,本輪開曝露面)。]

### Q3 觸及未鎖判定落點
[auto-default: 後端算 flag | reason: 毫元 tick 表 / `limit_up_milli` 邏輯在
`copycat/market.py`,前端無 tick 表;`compute_breadth` rows_out 補 `close` +
`touched_limit_up`(high 曾到漲停價但現價未鎖)+ 對稱 `touched_limit_down`。
真快照已實測含 `high`/`low`/`open`(2026-08-06 12:19 實跑 parse 確認,
fixture 欄位是剪裁過的子集)。]

### Q4 連板數欄語意

[amendment 2026-08-06: design review R1(P0)推翻「前端 +1」— 盤前 / 假日開站時
rows = 上一交易日收盤快照,該日已計入 streak,前端 +1 必重複計數。改為後端
`rows_state()` 以 `trade_date` vs `data_end` 算完 `streak` + `streak_capped`,
前端零日期算術。細節見 design.md v2 §3.3。]
[auto-default: rows 加 `prev_streak`(截至上一交易日的連續收盤漲停日數,int;
算不出 = null)| reason: 「今日是否漲停」由 snapshot live 判,歷史歸歷史 —
前端顯示 limit_up 列「連 {prev_streak+1} 板」;非漲停列不顯示。跌停連板不做
(需求弱,記 out of scope)。窗上限 10 日:prev_streak == 10 顯示「10+」誠實表述。]

### Q5 篩選持久化
[auto-default: localStorage 單層,不加後端 config 檔(總 spec Phase 0 再議項)|
reason: 篩選是個人視圖偏好,單機單人使用;後端 config 檔是無消費者的抽象。]

### Q6 EOD streak 的失敗降級
[auto-default: 連板欄顯示「-」、列表照出不阻塞;當日快取成功後不重打;取數失敗
沿 breadth_fetch 錯誤分類(402 長退避)| reason: 連板是附加欄,不得拖垮列表主體。]

### Q7 列表 UI 位置
[auto-default: IndexPage 下方新收合 section(CorrSection 同款慣例),位於
BreadthBand/騰落線之下、CorrSection 之上 | reason: R1 已把「區塊切換」落地成
收合 section 慣例;R4 訊號時間軸進來後再考慮整併切換器。]

## 3. 成功條件(SC gate)

- **SC-1(rows 端點)**:`GET /api/market/breadth/rows` 回
  `{enabled, trade_date, as_of, stale, streaks_ready, rows:[…]}`,row 含
  `stock_id/name/market/close/change_rate/volume_ratio/total_amount/limit_up/
  limit_down/touched_limit_up/touched_limit_down/streak/streak_capped`。
  [amendment 2026-08-06: design review R1/R17 — `prev_streak` 改為後端算完的
  `streak` + `streak_capped`;fake 取數三元組隨 R2 修為四元組。]
  驗證:pytest route 測試(fake 取數四元組 + fixture);盤中加強 = 側車 server
  (fake TXO + 真 FinMind,R2 樣板)curl 對照當下 snapshot。
  窗口:anytime(pytest);盤中(真值對照);窗外降級 = fixture 即為證據。
- **SC-2(連板數管線)**:純函式對 10 日 EOD fixture 算出正確 `prev_streak`
  (案例必含:除權息 spread 日、連板中斷、窗內缺日的新上市股);當日快取落檔
  `data/market/`,同日第二次啟動不再打 FinMind(pytest 以 fake 計數驗)。
  真值抽驗:實跑一次真 EOD 取數,人工對照 1-2 檔已知連板股。
  窗口:anytime(EOD 資料盤後即定,不需盤中)。
- **SC-3(列表畫面可指認)**:綜合 tab 內出現「漲跌停」區塊,表格首欄為
  代號 + 名稱(繁中),欄含現價 / 漲跌幅% / 連板 / 成交金額;篩選列可見
  「上市」「上櫃」「漲停」「跌停」「觸及未鎖」選項與成交金額門檻、股價區間輸入。
  驗證:AI 截圖(claude-in-chrome 開 vite dev)對照本表述 + user 過目雙層。
  窗口:盤中截圖優先;窗外降級 = fake/fixture 資料截圖(版面驗證不依賴真值)。
- **SC-4(篩選持久化)**:改任一篩選條件列表即時重濾,重整頁面後條件保留
  (localStorage)。驗證:vitest(assert localStorage 寫入 + 重掛載還原)。
  窗口:anytime。
- **SC-5(跳轉)**:點列表任一列 → 畫面切「個股(期)」tab、主圖標的 = 該檔代號。
  驗證:vitest App 級(點擊 → tab 與 stockCode state 變更 → StockPage 收到 code);
  盤中加強 = 真環境點擊後五檔開始跳動(截圖 + user 過目)。
  窗口:anytime(vitest);盤中(五檔跳動)。
- **SC-6(失效域隔離)**:FinMind 掛掉(`VERIFY_BREADTH_FAIL=1` 注入,R2 通道)時
  列表顯示 stale 標記、指數圖 / corr 等 TC4 系零波及。
  驗證:pytest + `--verify` server 注入實測。窗口:anytime。

## 4. Edge cases

1. **除權息日的 streak 判定**:prev_close = 當日 close − spread(EOD `spread` 欄,
   CLAUDE.md §8 語意);limit 判定用毫元精確等值(`_is_limit` 同法),不用 float 容差。
2. **新上市 / 窗內缺日**:回看窗內某日無該股 row → streak 於該處中斷歸 0(不外推);
   上市首五日無漲跌幅限制,close 天然不等於 limit 價,自然不計連板。
3. **盤中打 EOD 的資料日**:FinMind EOD 最新可得日 = 上一交易日(當日盤後才出);
   streak 一律「截至 < today 的最近可得交易日」,今日狀態只由 snapshot 判。
4. **觸及未鎖**:high == 漲停價(毫元等值)且現價未鎖;`prev_close <= 0` 或欄缺 →
   不判 touched(與 compute_breadth 既有慣例一致)。
5. **rows 與 counts 同輪同源**:列表 as_of = R2 `_apply` 同一輪的快照時刻,
   不另起取數(髒 row / 換日三分法沿 R2 機制,本輪零重複實作)。
6. **prev_streak 算不出**(EOD 取數失敗 / 快取缺):欄顯示「-」,列表主體照出。

## 5. Out of scope

- 類股強弱、訊號事件流(R4)。
- 列表迷你預覽(D-5,next-time)。
- 跌停連板數欄。
- 個股 tab 內部改動(跳轉走既有 `setTab` + `setStockCode`,StockPage 零改)。
- neigui 端任何改動(唯讀參照)。
- 後端篩選 config 檔(Q5 拍板不做)。

## 6. 執行約束(跨輪掃描 — R2 brainstorm §6 + 總 spec §6 + R2 沉澱)

- 搬邏輯不整檔貼;寫 .py 前讀 `backend-conventions`;FinMind 接入照
  `finmind-conventions`(Bearer / 錯誤分類沿 `breadth_fetch` 慣例)。
- 寫 frontend 前讀 `frontend-conventions` + `frontend-testing`;列表若有圖形元素過
  `dataviz`(純表格則免)。
- 盤中不起第二台連 TC4 的後端;HTTP 層驗證用 `--verify`(port 8722);
  盤中真 FinMind 驗證走**側車 server 樣板**(R2 實證:fake TXO + 真 fetchers +
  `neutralize_external_env()` + 隔離落檔目錄 + 非 canonical port)。
- FinMind poller 活在 server process → prod 生效需重啟,排盤後。
- 當日產物落檔防重啟歸零(streak 快取同理)。
- 驗證指令不接 `| tail` 吞 exit code;mutation 驗證防同秒 pycache(sleep 1)。
- 收尾 rebase 撞 `docs/next-time.md` 先 grep 同根因條目再新增。

## 7. 規模分流

**L**:≥5 檔(market_breadth rows 欄位擴充 / breadth_fetch EOD 取數 / streak 純函式新檔 /
breadth_engine 編排 / app route + 前端 types / 列表元件 / IndexPage / App 接線),
跨前後端。輪數同 M(2026-07-26 制)。
