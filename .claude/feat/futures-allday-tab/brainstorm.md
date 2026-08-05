# brainstorm — 期貨 tab 原地升級:近全圖表(日盤+夜盤)+ 交易輔助十項

日期:2026-08-05。模式:/auto(退出條件 = Phase 8.5 完成)。

## 來源與預核准記錄

規格來自 user 三輪對話拍板(2026-08-05 同 session 前段),/auto 替代條件成立(共識已逐項
確認,含 counter-proposal 的採納與否決),Phase 0 走預核准路徑。拍板要點:

- 期貨 tab **原地升級**,tab 結構不變;選擇權維持獨立 tab **不併頁**(user 明示)。
- 圖表一律「**近全**」口徑:日盤 + 夜盤連續拼接、死區壓縮(13:45 收完下一根即 15:00)。
  不做日盤/夜盤切換鈕(user 拍板連續拼接;「僅日盤」模式列 later)。
- 便宜高價值四項 + 中等成本三項全納;大型功能只納**夜盤**;OCO 與成交明細明確排除。

## 分流判定記錄

已成形方案:條件 1 中(UI 形式 + 資料流 + 落點 tab 全指名)、條件 2 中(決策點已於
前三輪 grilling 姿態逐題收斂完畢)。無殘留方向性抉擇。

## 執行約束(user 指示 + 專案紀律)

- **worktree 開發**(user 指示):`.claude/worktrees/feat-futures-allday`,主 tree 另有
  session 使用中,不碰。gitignored 依賴已用複製(TCPY)/ npm ci 補齊,不用 junction。
- **盤中不起第二台連 TC4 的後端**(CLAUDE.md §8):後端 HTTP 層驗證用 fake source +
  另一 port;UI 驗證只起 vite dev(proxy 指向跑著的 8721)。
- 實作 dispatch 一律顯式帶 `opus`(模型路由 2026-08-03)。
- worktree 內直跑腳本開頭必 `sys.path.insert(0, <worktree root>)`(editable install 釘主 tree)。
- 選擇權(TXO)tab 與個股/大盤/相關係數 tab 的行為**零改動**(行為白名單)。

## 目標

期貨 tab 從「報價列 + 五檔」升級為完整的台指期看盤下單工作區:近全分時圖 / 多週期 K 線、
期現價差、結算倒數、持倉均價線、內外盤副圖、閃電梯掛單整合(顯示/刪/全撤/平倉)、
選擇權 OI 支撐壓力線。

## 成功條件(SC)

> UI SC 驗收 = AI 以 claude-in-chrome 開真實畫面對照表述截圖核對 + user 過目雙層。
> 驗證窗口標記:anytime(fake/歷史資料可驗)/ 盤中 / 夜盤;窗口外降級策略逐條標明。

- **SC-1 近全分時圖**:期貨 tab 主區(五檔下方)出現分時走勢折線圖,x 軸為兩段拼接
  分鐘域(日盤 08:46–13:45 + 夜盤 15:01–次日 05:00,死區壓縮不佔寬),軸上時間標籤至少
  含 09:00 / 13:00 / 15:00 / 21:00 / 03:00 級距,參考價虛線可見。預設顯示分時模式。
  驗證:vitest(兩段軸映射 + 元件 render)、pytest(夜盤 bars 進入回應)。
  窗口:anytime(歷史 1K);盤中/夜盤加驗即時接尾(降級:非交易時段以回補資料截圖)。
- **SC-2 K 線多週期**:圖表上方出現週期鈕列,至少含「分時 / 1分 / 5分 / 15分 / 30分 /
  60分 / 日K」,點選即切換;分 K 由 1 分 K 前端聚合(沿用 aggregateBars),夜盤 bars
  含在聚合內。驗證:vitest(模式切換 + 聚合含夜盤 bar);截圖對照。窗口:anytime。
- **SC-3 夜盤資料貫通**:後端 `/api/market/bars/{TXF|MXF|TMF}?tf=1` 回應包含夜盤
  分鐘 bar(15:01–05:00 段),13:45 與 15:01 兩根在序列中相鄰;日 K 口徑(TC4 DK 含
  不含夜盤量)以實測記錄於 design.md。驗證:pytest(兩段分鐘域解析,含跨午夜歸屬);
  真實抽驗 [amendment 2026-08-05: 量法補 session 參數(design review D13)] =
  `curl -s "localhost:<port>/api/market/bars/TXF?tf=1&days=5&session=allday"` 以 python
  數 bars 長度(單交易日 ≈300 日盤 + ≈840 夜盤)、抽查 15:01 與 00:0x bar 存在、
  13:45 與 15:01 相鄰。窗口:anytime(歷史資料)。
- **SC-4 商品切換同步(迴歸保護)**:TXF/MXF/TMF 切換鈕切換後,圖表資料、報價列、
  右欄閃電梯同步換為該商品(既有同步行為不退化)。驗證:vitest 既有 + 新增圖表跟隨測試。
  窗口:anytime。
- **SC-5 期現價差**:期貨頁 header 報價列出現「價差 +N / −N」(TXF 現價 − 加權指數現值,
  正逆價差變色:正=bull 色、逆=bear 色);加權無值(夜盤)時顯示「價差 —」。
  驗證:vitest(三態:正/逆/無值);截圖。窗口:anytime(fake 資料)。
- **SC-6 結算日倒數**:header 出現「結算 T-N」badge(依 resolved_contract 月份第三個
  週三計,當日 = T-0);T-0 時 badge 轉警示色(amber)且閃電梯頂部出現「今日結算」警示列。
  驗證:vitest(日期計算:月初/月中/跨月/正好第三週三);截圖。窗口:anytime。
- **SC-7 持倉均價線**:圖上疊加水平均價線 —— 當群益期貨部位的商品與當前圖表商品相符時
  出現,線旁標籤含「均價 + 方向(多/空)+ 口數」;無部位或未登入不畫。
  驗證:vitest(有/無部位、商品不符);fake 資料截圖。窗口:anytime(降級:
  真實部位視 user 帳戶而定,fake 截圖 + user 過目)。
- **SC-8 內外盤能量副圖**:K 線模式(分 K)下,主圖下方出現內外盤量副圖(每根 bar
  外盤紅柱/內盤綠柱);資料源 = 1K row 的 UpVolume/DownVolume,後端 bars API 新增
  對應欄位;整段無量資料(any(v>0) 為 false)時副圖隱藏。
  驗證:pytest(欄位解析 + API shape)、vitest(render + 隱藏判定);截圖。窗口:anytime。
- **SC-9 掛單顯示在閃電梯**:[amendment 2026-08-05: Phase 1 現況查核發現此功能**已完整
  存在** —— `splitMyLots` 聚合活單映射到梯列 + 紅方格點刪(直刪無彈窗,`FuturesLadder.tsx`
  `cancelLot`)。本 SC 降級為**迴歸保護**:既有掛單顯示與點刪行為零退化。]
  驗證:既有 vitest 測試全綠(futures-ladder / FuturesLadder 測試檔)。窗口:anytime。
- **SC-10 一鍵全撤 / 一鍵平倉**:閃電梯頂部出現「全撤」鈕(撤當前商品全部未成交期貨
  掛單;武裝下即點即撤,同 SC-9 判準)與「平倉」鈕(平掉當前商品全部期貨部位;送新單
  有風險 → 走既有 CapitalConfirmDialog 二次確認)。無掛單/無部位時對應鈕 disabled。
  驗證:vitest(兩鈕狀態 + 確認流)。窗口:anytime(fake)。
- **SC-11 OI 支撐壓力線**:[amendment 2026-08-05: 口徑更新(design review D9/R2-5,
  FinMind 真樣本佐證)—— 全域 max 會選到深度價外垃圾履約價(實測 call max @55000),
  改為:**當月契約(contract_date 精確等值)+ trading_session=position +
  現價 ±10% 帶內** OI 最大] 日 K 與分 K 圖上疊加兩條水平線 —— 帶內 OI 最大的
  call 履約價(壓力,標籤「壓 <strike>」)與 put 履約價(撐,標籤「撐 <strike>」),
  hover/旁註含 OI 口數與資料日期(EOD);資料源 = FinMind(接入慣例照 §5 樣板:Bearer /
  rate limit / atomic cache);FINMIND_TOKEN 未設或取數失敗 → 線隱藏、圖表照常。
  驗證:pytest(service mock HTTP + 降級)、vitest(疊線 render);截圖。窗口:anytime。
- **SC-12 夜盤時窗**:前端交易時窗判定(控制分 K 輪詢)涵蓋夜盤兩段(含跨午夜與
  **星期維度** [amendment 2026-08-05: design review D7 — 夜盤後半屬前一交易日]),
  夜盤時段輪詢照常、日盤收盤後 **13:51–14:54** 與 05:06–08:39 停輪詢
  [amendment 2026-08-05: 邊界以 design §4.2 為準(R2-9);vitest 補(週三 13:47)T、
  (週三 14:56)T 兩個邊界對]。
  驗證:vitest 以(星期, 時刻)對:(週三 10:00)T /(週三 14:30)F /(週三 16:00)T /
  (週四 00:30)T /(週六 00:30)T /(週六 10:00)F /(週日 20:00)F /(週一 03:00)F /
  (週一 08:50)T。窗口:anytime。

## Edge cases(≥3)

1. **跨午夜歸屬**:夜盤 00:00–05:00 的 bar 台北日曆日已是次日 —— 分鐘 key 與序列排序
   必須按時間軸連續(15:00 段在前、00:00 段在後),不可按 (date, time) 字典序把凌晨段
   排到隔日日盤後面。回補窗要抓「昨日 + 今日」兩個 UTC 日才湊得齊完整近全序列。
2. **週五夜盤 → 週一日盤**:拼接按「實際有 bar 的序列」推進,不可按日曆日 +1 推算;
   週末無資料日不得產生空洞或斷點錯位。
3. **TC4 timeout / disconnected**:[amendment 2026-08-05: design review D8 —
   `/api/market/bars` 路徑**本來就無三態**(空態以 `meta.source="unavailable"` 表述,
   個股路徑的 tristate 不經過這裡),已知取捨:本輪沿用單一表述不引入三態,期貨圖表
   空態文案用進行式不下結論。個股 bars 的 tristate 鏈不受本輪改動(迴歸保護)。]
4. **鎖停市價佇列 price=0**:閃電梯新增掛單標記時不得依賴 `bids[0]` 為最佳限價
   (§8 教訓);掛單價位映射走既有 limit-only 慣例。
5. **換月 rollover**:resolved_contract 變更(HOT 換月)時結算倒數重算、掛單/均價線
   的商品匹配以期交所碼 + 月份契約為準,不殘留舊月狀態。
6. **群益未登入 / 1097 / token 缺**:SC-7/9/10 全部安靜降級(不畫線、無標記、鈕
   disabled),圖表與行情功能照常,不得因 capital 缺席而報錯。
7. **加權指數夜間無推播**:SC-5 顯示「價差 —」,不得沿用日盤最後值假裝即時。
8. **指數/稀疏商品無量**:SC-8 副圖以資料判定(any(v>0)),不以商品類別判定。

## Out of scope

- 停損停利 / OCO 自動出場單(§7 三道閘另輪)。
- 成交明細 time & sales(期貨引擎不保留 tick,D5 拍板不翻案)。
- 選擇權併入期貨 tab(user 拍板獨立)。
- 「僅日盤」顯示模式切換鈕(兩段尺已分開定義,之後要加很便宜)。
- 結算日逢假日順延的精確化(無假日行事曆;第三週三為近似,known limitation)。
- 週選擇權結算倒數(期貨 tab 只看台指期當月契約結算)。
- 夜盤的加權現貨指數替代源(期現價差夜間就是無現貨,顯示 — 是正確行為)。

## 規模分流

**L**:跨前後端(bars API 欄位新增 + FinMind 新 service + 前端圖表/閃電梯/時窗多檔),
預估 ≥ 10 檔。輪數同 M(Phase 1 預設 1 輪 + P0 限縮加輪;Phase 2 固定 1 輪)。
