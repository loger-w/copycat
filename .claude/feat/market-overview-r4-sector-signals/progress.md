# progress ledger — market-overview-r4-sector-signals

**Phase 4 自評(2026-08-06)**:3 lens(事件鏈/測試空洞/spec 對照)→ 4 P1 + 11 P2,
全 P1 CONFIRMED 修復;fix 波 A(後端 9 commits,4 對紅綠 + 1 補強)+ B(前端 1
補強 commit,mutation 五處驗非 vacuous)。C-6(jsonl 佇列共用)rejected:量級安全,
記 next-time。**S-6 errata:design §2 列 StockPage.tsx 為修改檔,實際零改動
(§9.3 的 feed 預設 exclude 已達成 SC-8)— 非漏改。**

Plan: `.claude/feat/market-overview-r4-sector-signals/implementation/PLAN.md`
(機制真相源 design.md v3;每 task 一行:編號 / commit 範圍 / review 結果)

- [x] Task 1 sector_rotation 純函式 — 86eb7e3d(red)+ 33cfc6dd(green);17 案;
  全套 2416 綠 / ruff / pyright 0;review gate PASS(忠實度抽驗 OK;members 六案
  屬等價搬全集,PLAN 列舉少一項非偏離)
- [x] Task 2 chain_store — e035f009(red)+ c266ef9e(green);10 案;全套 2426 綠
  (第 1 次 1 flake:test_index_routes ws watchdog race,implementer 已定位根因,
  與本 task 無因果 → Task 12 記 next-time);review gate PASS
- [x] Task 3 fetch_industry_chain + config 鍵 — 7d079aa8(red)+ 2d21242d(green);
  27 案兩檔;全套 2432 綠;review gate PASS(偏離皆加固性,無語意偏離)
- [x] Task 4 market_breadth.limit_judged — ed413692(red,含兩處「該變 assertion」
  先 stash 實測紅)+ 3e1da284(green);全套 2435 綠;parity fixture 未動;
  review gate PASS。裁決:rows payload 帶 limit_judged 出去(1 bool × ~2800 列
  頻寬可忽略),route 層不剝鍵 — Task 8 不需處理
- [x] Task 5 hub 新入口 — 93b74cf9(red)+ 6efe9cae(green);92 案;全套 2447 綠;
  review gate PASS。裁決:_closing 整批早退(WS 亦不推)接受 — 關機中 WS client
  正在收攤,推了也沒人收;界線(_emit/_enqueue/_event_id/slots 不動)已遵守
- [x] Task 6 engine chain 刷新 + rotation — 56c6eeef(red)+ a7710c58(green);
  105 案;全套 2465 綠;review gate PASS(偏離皆結構性:_restore_chain 命名鏡射
  慣例、加固案 3 條)
- [x] Task 7 engine diff 事件源 — 5cfa94ef(red)+ f2ca9fdb(green);16 新案 +
  整合案;全套 2481 綠(1 次既知 index ws flake,重跑綠);review gate PASS。
  裁決:MarketSignalSink Protocol 取代 TYPE_CHECKING import(fake 可注入,防循環
  同效)、payload 先算值再推狀態(修 spec 虛擬碼順序缺陷)皆接受
- [x] Task 8 app 接線 + verify — e8d57021(red)+ 16dc4b25(green);158 targeted;
  全套 2503 綠(index ws flake 又現 1 次,重跑綠 — 三度目擊,Task 12 必記
  next-time);review gate PASS。裁決:引擎 None 時 stale=loading(sibling route
  同款)接受;today 測試實際落 test_signal_routes.py;?market= 未知值當 include
  接受(傳輸量取捨非安全閘)
- [x] Task 9 前端 signal 模型與過濾 — 2bf671e9 + 5b13ae01(red×2)+ f47a4dd5
  (green);vitest 1611 綠 / tsc / eslint 0;R1 P0 mutation 驗證過(固定 key 改回
  → 雙紅);review gate PASS。注意:紅 commit 拆兩支(Phase 8 tag 機驗時留意
  兩紅配一綠的判定)
- [x] Task 10 前端 SectorSection — 0909ffe8(red)+ f71609eb(green);vitest 1637
  綠;review gate PASS(五態文案補強接受)。留意:同頁 stale 標記兩款並存
  (BreadthBand 版 vs LimitList amber 版)— Phase 6 截圖時看視覺是否需統一,
  暫記 next-time 候選
- [x] Task 11 前端 SignalTimelineSection — eded61b5(red)+ 465f97b3(green);
  vitest 1654 綠;review gate PASS(列不含價格 = 依 spec 從嚴;chip 群組全鎖)
- [x] Task 12 文件同步 — feb17bf7(🟢 chore:CLAUDE.md/總 spec 回寫/next-time
  R4 節 + ws flake 三度目擊加證)
- [x] Task 13 窗限取證工具 — evidence/breadth_side_server_r4.py(五元組側車)+
  sc4_parity_compare.py;**SC-4 窗外降級層已取證 PASS**(SC-4_parity-20260806-204443.json:
  47 產業,序列/avg/members 兩實作全等,真 FinMind snapshot 2865 列)
