# feat/chart-ux-batch-0826 — 看盤 UX 四功能 + 下單後倉位延遲(/auto 疊加)

日期:2026-08-26。流程:`/auto` 疊加 `/feat`(worktree `C:\side-project\copycat-wt-chart-ux`)。
退出條件(機械):closeout 全鏈過(pytest / ruff / pyright / npm test / tsc / eslint 全綠)+ PR 開出 +
`/pr-review` 報告落檔。接續指令:`/feat`(F1–F4)+ `/bug`(F5;diagnosing-bugs 先 loop 後假說)。

grilling 逐題以建議解推進,每題標 `[auto-default]`;**方向性抉擇(SC 集合 / 對外契約 / 資料源)全部
不動**:F1–F3 純前端、F4 為 config 加腿(既有 leg schema)、F5 為既有 API 內部時序。

## F1 分時圖疊「加權 / 櫃買」即時走勢(可開關)

- 需求原文:「分時圖加上台指跟櫃買的即時走勢 可以開關」。
- `[auto-default: 「台指」= 加權指數 IX0001(TWSE),不是台指期 TXF | reason: 與「櫃買」成對的是兩個
  現貨指數;`useIndexStream` 只有 twse/otc 有逐分鐘序列,txf 只有最新價。台指期版本若要,另案]`
- `[auto-default: 疊法 = 以「相對昨收 %」映射到個股自己的價格軸:y = toY(stock.ref × (1 + idxPct))
  | reason: 個股 y 域 = [跌停, 漲停] = ±10%,指數 ±2% 恆在域內;不需第二條 y 軸;與 `MarketPane
  OverlayCard`「加權 vs 櫃買(相對昨收 %)」同一個 % 定義(`lib/index-chart-svg.ts` pct 公式)]`
- `[auto-default: 兩顆獨立 toggle 「加權」「櫃買」,進 `ChartToggles`(新鍵 `idxTwse` / `idxOtc`,
  預設**關**,不 bump TOGGLES_VERSION) | reason: 與 vp/fills 同款;預設關是因為疊線會加視覺噪音,
  user 要「可以開關」而非常駐]`
- `[auto-default: 個股單檔頁 + 群組圖牆卡片兩處都吃(toggle 列兩處都加鈕) | reason: toggles 本來
  就是共用 schema;卡片變體只讀]`
- `[auto-default: 個股 `ref` 不可得(meta.ref null / 0)→ 不畫、toggle 反灰 hint「無昨收」;指數 `ref`
  null → 該線不畫 | reason: 相對 % 沒有基準就是假線]`
- 資料流:`App.useIndexStream()` 已持有 twse/otc → `StockPage` 新 prop `index`(`{twse, otc}` useMemo)
  → `StockChart` / `GroupGridView` → `StockIntradayChart` / `CardIntradayChart` → `IntradayChartCore`
  新 prop `indexSeries`。純幾何抽 `lib/index-overlay-lines.ts::buildIndexOverlayLines(series, stockRef, g, xw)`
  (零 React 依賴,單元測試)。
- 線型:**與台股綜合頁 OverlayCard 同一組識別色**(加權 `stroke-profit` 金實線、櫃買 `stroke-idx-otc` 藍虛線;
  review 指出初稿 ink-muted / ink-dim 與綜合頁不同色、且曾誤用 river-2 = 櫃買藍畫加權);右緣末點小標籤「加權 +0.35%」
  「櫃買 −0.12%」(rem 字級)。不加 readout 欄、不參與 hover。
- index / futures mode 不提供(指數圖疊自己沒意義;期指近全軸窗與指數 09:01–13:30 不同尺)。
- Seams(測試):`lib/index-overlay-lines.test.ts`(純函式:pct → y、ref 缺 → 空、窗外分鐘剔除)+
  `StockIntradayChart.test.tsx` 一條(toggle 開 → 兩條 `data-testid="index-line-twse|otc"`;關 → 無)+
  `GroupGridView.toggle.test.tsx` 一條(圖牆鈕存在且寫 toggles)。

## F2 群組檢視下點側欄股票 → 圖牆切到該群組

- 需求原文:「在群組視窗點擊左邊自選清單的股票時 就切換到該群組」。
- `[auto-default: 「該群組」= 側欄上被點那一列所在的群組區段(stockRow 已帶 `group` 參數);點「未分組」
  區段列 → 不切群組(仍換右欄標的) | reason: 一檔可多組(schema v3 無唯一性),以「點的是哪一區段」
  消歧義最不猜]`
- `[auto-default: 只在 `view === "group"` 時切群組;單檔檢視下行為不變(不自動跳群組) | reason: 原文
  限定「在群組視窗」]`
- `[auto-default: `picked` 群組 state 從 `GroupGridView` 上提到 `StockPage`(controlled:`selectedGroup`
  + `onSelectGroup` **必傳**,GroupGridView 不再自持;hook `useStockGroup` 為唯一持有者),localStorage key `STOCK_GROUP_KEY` 讀寫搬到 StockPage | reason: 側欄與圖牆是
  兄弟節點,共同祖先才拿得到;GroupGridView 既有 fallback(記住的群組已刪 → 第一個)保留在讀取端]`
- 側欄契約:`onSelect: (code: string, group?: string | null) => void`(既有一參呼叫端不變)。
- Seams:`StockPage.test.tsx` 一條(群組檢視 + 點側欄 B 群列 → 圖牆 radiogroup 值 = B;點未分組列 →
  值不變)+ `WatchlistSidebar.test.tsx` 一條(onSelect 第二參 = 群組名 / null)。

## F3 群組圖牆 hover 同步十字線(可開關)

- 需求原文:「群組滑鼠 Hover 時 所有群組都同時顯示十字線 可以開關」。
- `[auto-default: 同步鍵 = 分鐘(x);其他卡片的 y = 該卡該分鐘收盤價(toY(c)),讓十字線落在各自價格線
  上;被 hover 的卡本身 y 仍跟滑鼠(自由量尺) | reason: 跨卡 y 像素沒有共同意義,以分鐘收盤為錨才是
  「同一時間各檔在哪」]`
- `[auto-default: toggle 「十字線」進 `ChartToggles`(新鍵 `syncHover`,預設**開**),只在圖牆 toggle 列
  出現(單檔頁無意義) | reason: user 要的功能預設就要看得到;可關]`
- 實作:`GroupGridView` 持 `syncMin: number | null` state;`IntradayChartCore` 新 props
  `syncHoverMin?: number | null` + `onHoverMinute?: (min: number | null) => void`(只在分鐘變化時回呼,
  不是每個 mousemove);core 內 `effHover = hover ?? (syncHoverMin !== null ? {min, y: toY(c)} : null)`。
  Readout 同步跟到該分鐘(各卡顯示同一分鐘的值)。ChartStatic memo 不受影響(hover 不在其 props)。
- Seams:`GroupGridView.test.tsx` 一條(card A svg mousemove → card B 出現 `crosshair-v`;toggle 關 →
  不出現)+ `StockIntradayChart.test.tsx` 一條(`syncHoverMin` 注入 → 十字線 + readout 該分鐘)。

## F4 相關係數加腿(VIX / 台幣 / 原油 / 台積電 / 黃金)

- 需求原文:「相關係數能否加上以下係數 我不確定達錢能否提供」。事實自查(不問 user):
  `spikes/corr_legs_probe.py`(沿 nk225_leg_probe 四步)2026-08-26 01:02 實跑,結果
  `spikes/out/corr_legs_probe.json`(gitignored;摘要落 evidence/):

| 腿 | TC4 symbol | 存在 oracle | REALTIME 45 s 推播 | 1K 首頁 rows | 結論 |
|---|---|---|---|---|---|
| VIX | `TC.F.CFE.VX.HOT` | OK | 19(對照 MES 197) | 50 | **可用**(流動性低但有 tick) |
| VIX mini | `TC.F.CFE.VXM.HOT` | OK | 0 | 0 | 不用 |
| 原油 | `TC.F.CME.CL.HOT` | OK | 163 | 50 | **可用** |
| 黃金 | `TC.F.CME.GC.HOT` | OK | 172 | 50 | **可用** |
| 台積電 | `TC.S.TWS.2330` | 已由 tc4-market-facts 驗證(個股 REALTIME 全掛 `TC.S.TWS.<code>`) | 夜間無推播(預期) | — | **可用**(只在 09:00–13:30 有值) |
| 台幣匯率 | — | 全樹掃 `TWD` / `TW*` 只命中 SGX `TWN`(富台,既有腿) | — | — | **達錢不提供**:現貨段只有 TWS;CME 匯率期貨無 TWD;TAIFEX 匯率期貨無 TWD |

- `[auto-default: 四腿全加(VIX / 原油 / 黃金 / 台積電),台幣不加 | reason: 探測證據如上]`
- `[auto-default: 原油用標準 CL、黃金用標準 GC(不用 MCL / MGC 微型) | reason: 相關係數看價格方向,標準合約流動性更高;微型只是保險]`
- `[auto-default: 台積電腿用現貨 `TC.S.TWS.2330`,不用個股期 CDF | reason: 現貨是真價;CDF 有 `TC.F.TWF.` 前綴會吃台期交日夜盤閘,但現貨 13:30 收盤與台期交 13:45 不同,閘語意不對]`
- 2330 現貨腿夜間全靜默 → 既有 `taifex_leg_gate` 對非 TWF 前綴恆 True = 整晚每 300 s 一發 UNSUB+SUB。
  補 `TC.S.TWS.` 前綴的**個股日盤閘**(沿用 `stock_source.in_trading_hours_now` = 08:30–13:35,含試撮與
  收盤 5 分 pad —— 08:30 起 2330 真的有推播,閘該開;不另建第二張時段表,與 stock / index 引擎同源;
  spec 初稿寫 09:00–13:30,實作審後改為沿用既有;交易日曆 AND)。**訂閱窗必須與 stock_engine 同一把**
  (`stock_window(當日)`,PR #111 review F-01):tc4-market-facts (b) 是「任一把 key 歸零 → 上游退訂整個 symbol」,
  兩引擎各持不同 key 正是引信而非保險;同一把 key 兩邊各持一份 count 2→1 永不歸零。初稿此處把 (b) 讀反。
- 改動面(沿 NK225M 第七腿 `4d1f550d` 三檔 + 閘):`configs/correlation.json` +4 腿;`copycat/corr_config.py`
  `DEFAULT_CONFIG` 同步(load 失敗 fallback 用);`river-colors.ts` / `index.css` 調色盤 7→11(第 8–11 色避開紅綠與
  既有 7 色);`corr_source.py` 新增 TWS 閘;測試鎖:`tests/test_corr_config.py`、`tests/server/test_corr_routes.py`、
  `tests/server/test_river_routes.py`、前端 `river-colors` 相關測試。
- Seams:`tests/live/test_corr_source.py`(TWS 閘:盤中 True / 盤後 False / 非交易日 False;TWF 與海外腿行為不變)+
  `tests/test_corr_config.py`(11 腿 key/label/symbol 逐字)+ 前端 `river-colors.test.ts`(11 色不重複、class 字面值)。

## F5 下單後倉位與損益點位出現慢 → 吃到成交價即時顯示

- 需求原文:「使用者在下單後 倉位跟獲利點位都會出現得很慢 修改為使用者下單之後 吃到價格之後即時顯示」。
- `[auto-default: 走 /bug 的 diagnosing-bugs 紀律(loop 先行),不走 /perf | reason: 症狀是「慢」但不是量化指標
  題;真成交需真下單(花錢,自動模式必停)→ loop 用 FakeCom 模擬三段 COM 往返各 150 ms 的**時序重現**]`
- 鏈的事實(code 逐行,非猜測):成交 `D` → `_mark_balance_dirty(0.5 s)` → 幫浦 50 ms 圈 → `GetRealBalanceReport`
  (等 `##` / 1 s timeout)→ `GetProfitLossGWReport`(等 `##`)→ `GetOpenInterestGW`(等 `##`)→ `set_positions`
  → **唯一**一次 `capital_position` WS → 前端 200 ms debounce → refetch。三段**串行**且無查詢識別(不能平行)。
  成交事件本身帶價 / 量 / 方向 / 種類(`ReplyRecord`),但**沒有任何路徑把它套到部位**。
- 根因:部位視圖只由「券商回查鏈」餵,成交回報 → 部位之間零直接路徑;正常路徑下限 = 0.5 s + 3 段往返,
  任一段丟 `##` 再 +1 s,連續成交時後一筆要等前一輪鏈跑完(守門不重發)。
- 修法(🔴 行為改動):成交 `D` 到達當下 `store.apply_fill(rec)` 樂觀套用 + 立即 emit `capital_position`,
  回查鏈照跑、落地時全量覆蓋(真相仍是券商)。套用規則:
  - 證券(整股市場 TS/TA/TP;零股 TL/TC 整個不套,review F-21 修正):kind 由 `flag_label` 對映(現股/拍賣現股→cash、融資/代資→margin、
    融券/代券→short;無券 / 未知 → 不套,log);張數 = 該單累計成交股數 // 1000 的**增量**(`_Agg` 記已套用張數,
    部分成交正確);買 +、賣 −(融券空單本來就是負張);均價:新倉 = 成交價;同向加碼且舊均價已知 = 加權;
    減碼不動;舊均價未知 → 留 None(寧缺勿錯);`pnl_*` 清 None(舊快照對新張數是假的)。
  - 期貨(純期貨,選擇權不套):契約碼由回報 idx8 產品碼(`QEF06` → `QEF`)+ **idx33** `YYYYMM`(真樣本
    `RAW_TF_NEW` 逐欄數過:idx32 = `FIQEF`、idx33 = `202606`;spec 初稿誤寫 idx38,review 修正)經
    `mapping._month_year_codes` 組(`QEFF6`);**假設**只有 2026-06-10 一筆真樣本 → 首筆真期貨成交後核對
    log「樂觀契約碼 vs OI 契約碼」(chain 落地時若鍵不同會 warning 一行);口數 買 +、賣 −,kind cash。
  - 部位歸零(qty 0)→ 從 map 移除。
  - **只在券商快照落地過之後才套**(review F-02):開機 / `clear()` 重播期間的成交只累計,`set_positions` 落地時
    把所有委託標成已套用,之後才套增量;反手翻倉判號不判幅度(review F-03);契約碼守門 `order_code == prod + MM`(F-04)。
- `[auto-default: 前端 200 ms debounce 不動 | reason: 合併連發用;修後 fill → 畫面 ≈ 0.3 s,瓶頸已不在此]`
- 觀測補強:`_handle_reply(D)` / 三段 complete / `_finalize_positions` 各加一行 ms 級 log(含自成交起的
  耗時),讓 user 下一筆真成交就能報實測數字(現狀 `_finalize_positions` 成功路徑零 log,無法量)。
- 已知取捨:成交到達時若回查鏈正在途中(查詢早於成交發出),該輪落地會短暫覆蓋回成交前快照,
  直到下一輪(due 已重新武裝)—— 與現狀等長的空窗,不擴大。
- Seams:`tests/capital/test_fill_latency.py`(loop:FakeCom 三段各 150 ms 回 `##`,量 fill → `capital_position`
  emit 的 monotonic 差;現狀 ≈ 0.95 s → 紅;修後 < 50 ms → 綠)+ `tests/capital/test_store.py`(apply_fill 規則:
  新倉 / 加碼加權 / 減碼 / 部分成交增量 / 融券負張 / 未知種類不套 / 期貨契約碼)+ 反向驗證(revert → 紅)。
