# 2026-08-22 日間鏈 R1–R10(PR #78–#87)review 結果

> 對照 `2026-08-21-daytime-chain-rounds.md` 各輪定義的問題與契約;10 個 reviewer(opus,唯讀)
> 各負責一輪,獨立重跑目標測試檔 / 自寫探針。本檔 = 結論與開工依據;處置進度記於各 PR 與
> `docs/next-time.md`。

## 總表

| 輪 | PR | 問題是否解掉 | P0 | P1 | P2 | 處置 |
|---|---|---|---|---|---|---|
| R1 CDP 右緣標籤避讓 | #78 | 部分 | – | 1 | 1 | /mod(VWAP 併進避讓) |
| R2 a11y 批 | #79 | 是 | – | – | 5 | next-time |
| R3 訊號提示合併 | #80 | 是 | – | – | 4 | next-time |
| R4 拖曳作廢 + snap 口徑 | #81 | 是 | – | – | 4 | next-time |
| R5 readout / clamp / 自癒閘 | #82 | 是(B9 08-22 凌晨 prod log 實證) | – | – | 3 | next-time |
| R6 日曆可見性 | #83 | 是 | – | – | 4 | /mod 小批(日曆輪詢週期) |
| R7 BalanceCollector 遲到 ## | #84 | 部分 | **1** | **2** | 4 | /bug(欠帳計數) |
| R8 timeout 旗標家族 | #85 | 部分(期貨三態未交付,已記留尾) | – | – | 6 | /bug 小批(timer/記帳/兜底) |
| R9 回補進度 + tape=0 | #86 | 是 | – | – | 4 | /mod 小批(tape_omitted 前端) |
| R10 housekeeping | #87 | 是(C1–C7 AST 全等獨立複現) | – | – | 4 | next-time |

## P0 / P1

### R7 #84 — P0 `copycat/capital/balance.py:293-298` 欠帳窗一次性
`stale_until, self._stale_until = self._stale_until, None` 吞一個終止符即關窗;`abandon()` 只記
時間戳不記筆數。連續兩輪死查詢 → 第一個遲到 `##` 被吞、第二個照 flush 空 staging →
`set_positions([])`(原 bug 兩輪即重現)。探針:seeded `[('3357',3)]` → 兩個欠帳 `##` → store `[]`。

### R7 #84 — P1 `balance.py:216` 窗外遲到 `##` 對有庫存帳戶同樣清空
PR/docstring/next-time 把代價寫成「只影響真空帳戶」;`test_empty_account_clears_positions_after_stale_window`
fixture 自己先 seed 3357 再被清。20 s 無量測根據。

### R7 #84 — P1 `balance.py:303` 舊輪 row 關窗並併進新輪 staging
flush 出跨輪混合快照(可復活已出清的幽靈部位);F7 只記「截斷」。

### R1 #78 — P1 `StockIntradayChart.tsx:595-599` VWAP 就地標籤仍與 MA 價位標疊印
spec 問題 = 11 顆 / 9 對;交付 = 帶內 7 顆(走廊 A)。change-spec 以「A×B 水平不相交」推「9 對歸零」,
推論管不到 B×C(VWAP anchor=start vs MA 價位標 anchor=end,x 區間重疊,VWAP 不進 obstacles)。
PR 自附 SC-4-2330-band-closeup.png 可見白 `2387.74` 壓琥珀 `2380`;SC-4-grid-2455 同。

## 主要 P2(依輪)

- **R1** `stock-intraday-svg.ts:643-666` 超容(dropOverflow=false)上緣 clamp 成完全同 y(`[4,4,4,4,10,20,30]`),矮卡片比改前更糊。
- **R2** `MarketPane.tsx:493` 週期 radiogroup 內塞「重疊」toggle(新引入 aria-required-children 違規,與 GroupGridView 同批相反決定);`OrderPanel.tsx:66` 估價暫缺時市價靜默單向收斂限價;`RadioPills.tsx:84` StockChart 停用 pill 新增 cursor-not-allowed;`RadioPills.test.tsx:260` onInteract 雙觸發只 `toHaveBeenCalled()`;SC-5 未涵蓋 OrderPanel 且 before/after 跨 build 模式。
- **R3** `useSignalAlerts.ts:187` 合併是與 `groupSignals` 不等價的第二套(相鄰 vs 全索引)且未註記;`:106` 通知走 setTimeout 後背景 >5 分鐘 intensive throttling 未實測;`signal-model.ts:82` `formatToastText` 只剩測試在用;`ToastStack.tsx:29` 無 line-clamp。
- **R4** `RightRail.tsx:285` 註解稱後端 400 BAD_TICK,實際平倉路由不過 `_require_legal_tick`;`WatchlistSidebar.tsx:334` 每 pointermove 新建 drag 物件;缺兩處邊價顯式等值 lock;作廢態視覺與「放回來源組」不可分辨。
- **R5** 封關夜誤差只留在已勾銷條目;`river_state.py:72` clamp 守門先佔非名次小者贏;跨午夜表缺午夜前夜盤正例。
- **R6** `useTradingCalendar.ts:37` staleTime Infinity + 6 h 背景停擺 → 跨午夜膠囊遲到數小時;週末補班漏設零提示(已記);膠囊不讀 `years_loaded`;盤前聯集標題落差(D3' 已知)。
- **R7** profit 段 `000` 表頭先關窗使欠帳窗失效;WARNING 無 collector 名;`_set_status("ok")` 用 reset 清欠帳順手開 `_awaiting`;`_query_open_interest` 無期貨帳號提前 return 不清 `_oi_abandoned`。
- **R8** `stock_source.py:753` AND 判準窄殘餘;`stock_engine.py:474-495,543-549` 退訂/切主圖不取消在途逾時 timer 不清 `_backfill_timeouts`;`futures_engine.py:297` 期貨三態未交付;`corr_engine.py:329-341` 整輪被丟卻印「已併回」;`corr_engine.py:386` retry task 無兜底;F9 格式夾 🔴。
- **R9** `engine.py:251` `phase`/`attempts_max` write-only;`buffer is None` 路徑 phase≠status 無測;`StockPage.tsx:463` 群組切單檔首 paint 空 tape 與無成交同形(後端 `tape_omitted` 前端不讀);`handover.attempt` / `tape=0` 契約未登記 CLAUDE.md §4。
- **R10** `corr_config.py:97/100/104/108` logger 仍印「預設六腿」而 next-time 已 `[x]`;ArmRow 武裝/鎖定態期望取自改後 DOM;spec C3 子項作廢(已記);85cf4e1e 跨四條合併 commit。
