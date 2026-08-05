# brainstorm:閃電梯部位列 + 未實現損益 + 含成本打平價

日期:2026-08-05。分支 `feat/ladder-position-pnl`。

## 分流判定

已成形方案(條件 1 中:next-time 批二項 13 指名落點 PriceLadder + 需新增手續費設定;條件 2 中:存放位置/口徑/UI 形式有可拷問決策點)→ grilling 姿態。**本輪 user 顯式指示「brainstorm 設計決策停下來問,不要替 user 拍板」→ 覆寫 auto-default 停等規則,四題已實際問答(2026-08-05)。**

## User 拍板(AskUserQuestion 實答)

1. **手續費折數**:user 更正「手續費目前是 1.8」→ **預設 1.8 折**(next-time 記載的「拍板 6 折」已過時,以本輪實答為準)。存放位置未另指定 → 採建議:**前端 localStorage**(`copycat-` 前綴 key),部位條旁可編輯,純前端顯示參數不跨端。
2. **未實現損益口徑**:**前端自算含費稅**(與打平價同一套口徑,數字自洽;與群益部位 tab 的 pnl_base 容許小差)。
3. **證交稅率**:**固定 0.3% 保守值**(當沖 0.15% 情境打平價偏高 = 保守,不高估獲利)。
4. **UI 形式**:**部位條 + 梯內標記**。

## 事實(自查,不問)

- `PriceLadder.tsx`:現況只有活單殘量聚合(`aggregateLots`),部位/損益/手續費零痕跡。現價 = `last.p`(毫元)、`meta.ref/upper/lower` 可得。
- 部位:`useCapitalPositions()`(useCapital.ts:166)→ `/api/capital/positions`;`CapitalPosition = {market, stock_no, qty(空方負), name, avg_price(群益損益試算[10] 平均買進成本,元;查詢回來前可為 null), kind(TradeKind), pnl_base(含費稅息,凍結在報告市價), pnl_base_price, pnl_cost}`。
- `pnl_base_price` 前端 production 零消費(只在 types/測試)。
- 1 張 = 1,000 股;`qty` 單位 = 張(sec)。
- 費率:手續費 0.1425% × 折數,買賣各一段;證交稅賣出側(本輪固定 0.3%)。

## 計算口徑(user 拍板 2 + 3 的落地)

f = 0.001425 × 折數(預設 0.18),t = 0.003。金額基底 = 價(元) × |qty| × 1000。

- **多方(qty > 0)**:未實現 = (現價 − avg) × qty × 1000 − avg×qty×1000×f(買段)− 現價×qty×1000×(f + t)(賣段);打平價 P_be = avg × (1 + f) / (1 − f − t)。
- **空方(qty < 0,融券/無券)**:開倉 = 賣出(avg 收入已扣費稅口徑上仍以名目 avg 記);未實現 = (avg − 現價) × |qty| × 1000 − avg×|qty|×1000×(f + t)(賣段)− 現價×|qty|×1000×f(回補買段);打平價 P_be = avg × (1 − f − t) / (1 + f)。
- 損益取整數元顯示(Math.round);打平價依 fmt 慣例顯示。

## SC

- SC-1:持有當前標的部位(`market === "sec" && stock_no === code && qty !== 0`)時,閃電梯**標的列下方**出現部位條:文字含「`N 張 @ <均價>`」、「未實現 `±X`」(正 = `text-bull` 紅、負 = `text-bear` 綠,沿專案漲跌色慣例)、「打平 `<價>`」。空手(無該檔 sec 部位)不顯示。驗證:component test(fake positions)+ AI 截圖 + user 過目。
- SC-2:未實現損益依上述口徑(lib 純函數),手算例單元測試:avg=100、現價=102、qty=2、折數 0.18 → 未實現 = 4000 − 100×2000×0.0002565 − 102×2000×(0.0002565+0.003) = 4000 − 51.3 − 664.53 = +3284(round)。驗證:vitest 測試名 `ladder-position` describe。
- SC-3:打平價:同 fixture P_be = 100 × 1.0002565 / 0.9967435 = 100.35(2 位)。空方 avg=100 → P_be = 100 × 0.9967435 / 1.0002565 = 99.65。驗證:單元測試手算例。
- SC-4:梯內標記:打平價所在 tick 列(多方無條件進位到下一合法 tick、空方無條件捨去 — 保守方向)左緣出現 2px 直色條(amber/accent 類,與均價標記異色);均價所在 tick 列左緣另色(藍/accent)直色條。hover 或部位條可辨識對應。驗證:component test 斷言標記元素 data-testid 落在正確 priceMilli 列 + 截圖。
- SC-5:折數設定:部位條(或武裝列)內 `type="number"` 小輸入,值域 (0, 10],預設 1.8,persist localStorage key `copycat-fee-discount`;改值即時重算損益/打平。驗證:component test(改輸入 → 斷言重算)+ localStorage 斷言。
- SC-6:多 kind 同檔並存(現股 + 融資)→ 部位條逐 kind 一列(成本口徑不同不合併)。`[auto-default: 逐 kind | reason: 資/券成本基礎不同,合併會算錯]`
- SC-7:`avg_price === null`(損益查詢未回)→ 該列顯示 `N 張 @ —`,損益/打平顯示 `—`,梯內標記不畫;`last === null`(無現價)→ 損益 `—`、打平價照算(只依 avg)。

**驗證窗口**:SC-1/4 的真實資料層需群益登入 + 實際持倉(盤中);窗口外降級 = component test(fake positions)+ AI 截圖(vite dev + 無部位空手態)+ user 盤中過目。

## Edge cases(≥3)

1. 空方 qty < 0(融券/無券):損益與打平方向對稱反轉(SC-3 空方例)。
2. `avg_price null` / `last null`:SC-7 降級顯示,不算不猜。
3. 打平價落在漲跌停外(貼近漲跌停的部位):所在 tick 超出梯域 → 梯內標記不畫,部位條數字照顯示。
4. 多 kind 並存(SC-6)。
5. 折數輸入非法(0、負、NaN、>10):夾制回有效值,不寫入 localStorage。
6. 群益低消 NT$20/筆:**不套用**(部位是聚合,無筆數資訊;1.8 折深折戶多為月退制,即時費率視同線性)。`[auto-default: 忽略低消 | reason: 聚合部位無筆數;記 known simplification]`
7. 融資利息 / 融券借券費:**不計**(盤中工具,當日語意)。`[auto-default: 不計息費 | reason: 當沖場景息費為零或極小]`

## Out of scope

- 期貨閃電梯(FuturesLadder)的部位/損益 — 期貨費稅結構不同,另輪。
- 群益 pnl_base 平移顯示(部位 tab 現狀不動)。
- 當沖稅率 0.15% 切換(user 拍板固定 0.3%)。
- 折數設定跨裝置同步(localStorage 即可)。
- 成交回報推算「今日建倉」判定。

## S/M/L

**M**(新 lib 純函數 + PriceLadder UI 改動 + 設定持久化;單端 frontend,無跨檔契約改動)→ 走 Phase 1 design.md。
