# 個股五題討論共識(2026-08-05,討論輪 — 不動 code)

背景:另一 session 開發中,本輪僅討論拍板。五題各自獨立開 /feat 輪實作,
本檔為各輪 Phase 0 的輸入(實作輪仍須自跑 SC gate 與 review,本檔的 SC 只是候選草稿)。

實作順序(拍板):**題4 → 題2 → 題1 → 題5 → 題3**
(4→5 順路:群組管理是同步監控的分群入口;1→5 結構:聯動提示掛在規則骨架上)

---

## 題 1:訊號規則化(方案 b)[user 拍板]

**共識**:移植 treading-king 的「具名規則」骨架,不含複合策略引擎(第二輪再議):
- 規則 = {名稱, kind(現有四類之一), 門檻參數, CDP levels 勾選, cooldown 秒數, enabled, notify_discord}
- REST 全 CRUD + 寫入即熱重載(不重啟);前端規則編輯器(參考 treading-king
  `SignalRulesDialog` + `ActiveSignalEditor`)
- 模型維持「規則全域 × 自選清單」(treading-king 同款;per-symbol scope 該專案已淘汰,不做)

**user 指定的硬性要求(treading-king 踩過的 bug,不可重現)**:
自選刪除後訊號必須立即停止監聽該檔。**copycat 現況已正確**:
- `signal_hub.py:235-243` `on_watchlist` 算 removed → 逐檔 `detector.drop_code()`
- `signal_state.py:168-171` `drop_code` 清 _prev/_window/_latch + 過濾 _cooldown
- `signal_hub.py:196,207` membership gate 先於一切評估
→ 規則化重構時此行為寫成 SC + 測試鎖死(刪除 → 該檔訊號歸零 + detector 狀態逐出)。

**現況關鍵事實**:
- 四鍵全域開關:`signal_hub.py:136`,持久化 `data/signals_enabled.json`
- 門檻:`signals_config.py:20-39` frozen dataclass;`configs/signals.json` 覆寫檔目前不存在,
  改門檻須改檔+重啟(lifespan 只讀一次 `app.py:297`)
- API 僅 `GET/PUT /api/stock/signals/enabled`(`app.py:684-698`);無門檻 API
- treading-king 參考:`backend/models/condition.py`(ActiveFilter schema v9)、
  `routes/active_signals.py`(CRUD + refresh_active_signals 熱重載)、
  cooldown key = (rule, symbol, level)(`signal_engine.py:396`)、
  `_fanout` 的 per-rule notify_discord gate(`signal_engine.py:1253`)

**設計要點**:
- 現有四鍵開關 → 遷移為預設四條規則(向後相容;`SignalRail` 四 toggle 改列規則)
- cooldown key 沿 treading-king:per (rule_id, code, level)
- Discord 節流(全域 30/min)保留,per-rule notify_discord 疊加其上
- 過載保護參考 treading-king lag auto-disable,列選配

## 題 2:分時圖價位別成交量 [user 拍板:K 線不做]

**共識**:只做分時圖;**bar 從左緣價位帶往右長、長條圖形式**(user 指定)。
- 零後端改動:當日全部 tick 的 (p, q, side) 已在 REST snapshot(`stock_state.py:199-209`
  不截斷)與 WS tick(`stock_engine.py:571-589`);唯一障礙是前端 `TAPE_MAX=200` 截斷
  (`stock-accum.ts:118,152`)→ 解法:fromSnapshot/applyTick 順手 fold 出
  `Map<priceMilli, {total, outer, inner}>` 直方圖(O(價位數),不放寬 tape)
- 桶化用 `lib/stock-tick.ts` snapDown/tickOf(顯示價位可下單紀律)
- 分色(外紅/內綠)做選配、預設單色(鎖停日 side 判定品質已知問題;CLAUDE.md §8 市價佇列條)
- 掛載:幾何純函式新增 `lib/volume-profile.ts`(SKILL.md:21 紀律);繪製插
  `StockIntradayChart.tsx` ChartStatic y 格線後、areaPolygon 前;資料層 useMemo(W-5);
  toggle 走 `useChartToggles`(加 `vp` 鍵,注意 TOGGLES_VERSION 語意)
- 重建點:seq 跳號/回補完成的全量 refetch → 直方圖與 fromSnapshot 同源重建
- hover 聯動(高亮滑鼠所在檔位的 VP bar)可順做:priceAtY+snapDown 現成

## 題 3:個股期選月 + 分時/五檔切換 + 下單直通 [user 拍板:一輪做完,含小型]

**共識(scope 比原估大,L 級)**:個股頁選定期貨合約(近月/遠月/小型)後,
**分時圖與五檔整個切換為該合約**,並可直接下單(群益)。

**已探明的路徑**:
- 合約發現:`QUERYALLINSTRUMENT Type="Fut2"` → StockFutures 樹,節點名自帶股號
  (「台積電(2330)」),Contracts = 全月份 leaf(5-6 口);小型是獨立節點。
  現行 code 零覆蓋;`tc4.py list_series()`(:262-276)骨架可改 Type。
  快取/刷新策略必須做(合約每月換,TXO「不可 hardcode」同教訓);
  可順便取代/校驗 `stkfut_map.json`(現僅 268 檔標準、無月份、無契約單位)
- 訂閱:leaf symbol(`TC.F.TWF.CDF.202609`)與現行 stkfut HOT 腿字串不同 → 無同
  symbol 衝突;`futures_source.subscribe_leaf`(:63-71)字串組裝現成,但缺對外
  「指定商品+月份」API;引擎歸屬待設計(擴 stock_engine vs 泛化 FuturesEngine —
  後者現成有五檔/漲跌停/resolved_contract,但 products 靜態、非清單商品直接丟棄)
- **分時圖分鐘域**:期貨 08:45–13:45,不是個股 0901–1330;
  `stock_source.parse_1k_bars(rows, domain)` 的 domain 參數就是為此(CLAUDE.md §8 期指條);
  1K 當日回補四段皆實證可用
- 下單:`mapping.to_exchange_symbol` 對 `CDF.202609→CDFI6` 已可用;前端送 YYYYMM 繞開
  resolved_contract;**唯一硬卡點 = MULTIPLIERS 無個股期乘數**(標準 2000/小型 100)→
  refresh-stkfut-map 已刮得到契約單位,落檔即可;safety 金額閘依賴正確乘數
- UI:個股頁加合約下拉(現貨/近月/次月/…/小型系列);`FuturesLadder` 寫死 `.HOT`
  (:121)需參數化

## 題 4:Discord 自選補齊 [user 拍板:權限不設]

**共識**:補齊群組管理指令;**「加進哪個群組」的答案 = group 參數 autocomplete**:
- `/watch add` 的 `group` 參數掛 `app_commands.autocomplete` → 動態列出現有群組名
  (打新名字 = 建新群組,行為與現況一致)
- 新增 `/watch groups`:列出全部群組(**含空群組**,修 `_format_watchlist` :210-212
  空群組不列的盲點)+ 各群成員數
- 新增:`/watch ungroup <code> <group>`(只移出群組不刪自選)、群組刪除/改名
- `stock_names.json` 軟白名單:查無代碼 → 回覆帶警告(仍可加;存在性零驗證是已知現況)
- 「未分組」保留名 bot 路徑要擋(現只有前端擋,`WatchlistManagerDialog.tsx:94,108`)
- add 回覆差異化:no-op(零寫早退)要跟真新增分文案
- 錯誤碼文案 bot `_ERROR_TEXT` 與前端 `errText` 兩份同步(新增碼時)
- 已確認現有 add/remove/list 與前端 PUT 同鎖同路徑(`watchlist_service.py`)、
  WS 廣播即時 → 不需重做

## 題 5:群組多檔即時分時圖(同步看盤)[user 拍板:改方向]

**user 修正**:不是三窗相關係數儀表 UI,是**多檔個股「即時分時圖」同屏**
(產業群組成員的 live 走勢牆,一眼看出誰在同步拉);傾向 sub-tab 呈現。
Discord 聯動通知要;領先落後不做。

**共識設計**:
- 個股頁 sub-tab「群組」:選自選群組 → 成員 mini 分時圖 grid(2-3 欄,
  每張 = 該檔 live 分時線 + 現價/漲跌幅;點擊切到單檔檢視)
- 疊圖(歸一化 % 對齊的單張多線圖)列為 grid 之外的選配檢視,實作輪再議
- 資料面(後端幾乎零改):`_states` 對全部自選股都有完整 StockDayState
  (`stock_engine.py:113,206`);初載走既有 `GET /api/stock/state/{code}` per 成員,
  live 更新走既有每秒 `watchlist_quote`(p/chg_pct/vol)延伸最後一分鐘點。
  mini 圖不需 full tick 流。若逐檔 GET 太碎再議群組聚合 endpoint / WS 分鐘 delta
- Discord 聯動:群組成員觸發爆拉/鎖板訊號時,訊息附同群摘要
  (「2330 爆拉 +2.3%,同群:3034 未動、3443 +0.9%」)。掛在題 1 規則骨架上
  (規則屬性:是否帶同群摘要)→ **題 1 先行**
- 同步率數字(CorrState 全配對)降級為 mini 圖角落 badge 或不做,實作輪看畫面密度定

**現況關鍵事實**:mini 圖分鐘序列原料 = snapshot.minutes(MinuteAgg 有 c/v/i/o/h/l);
自選上限 30 檔,群組典型 3-8 檔,前端負荷可控;`CorrState`(corr_state.py)泛用、
全配對成本趨近零(stdlib correlation 0.15ms/1800 樣本),若要 badge 隨時可掛。

---

## 探查報告出處

四份探查(訊號/圖表/個股期/Discord)結論已內嵌上文;treading-king 參考實作
路徑:`C:\side-project\treading-king`(active_signals schema、規則編輯器、bot 設計)。
