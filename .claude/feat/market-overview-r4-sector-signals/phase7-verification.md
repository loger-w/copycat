# Phase 7 verification — market-overview-r4-sector-signals(2026-08-06)

state 一致性自檢:current_phase=7、completed=[-1..6],artifact(design v3 / 三輪
spec review JSON / code-review-round-1 / automated round-1 / real-env round-1 /
evidence 11 檔)與 git log 對得上。自動化總量:pytest 2518 / vitest 1661 /
ruff / pyright / validate 42 全綠(Phase 5 round-1)。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 rotation 純函式 parity | `copycat/sector_rotation.py:32/70/108/146`(rows_to_chain_map / _group_stats / compute_sector_rotation / compute_sector_members) | `tests/test_sector_rotation.py` 17 案全綠(neigui :239-360/:407-447 等價搬 + 缺 sub 整列丟) | `evidence/SC-4_parity-20260806-204443.json`(真資料 47 產業兩實作全等 — parity 即 SC-1 的實機層) | `tests/test_market_breadth.py` 46 案(同族純函式)綠 |
| SC-2 chain 取數 + 快取 | `copycat/server/breadth_fetch.py`(fetch_industry_chain)/ `chain_store.py:load_chain/save_chain` / `breadth_engine.py:_maybe_arm_chain/_refresh_chain/_restore_chain`(+ C-1 修 `_recompute_rotation`) | `TestChainCache`(test_breadth_engine.py:1801 起)+ `tests/server/test_chain_store.py` 10 案 + chain fetch 三案(test_breadth_fetch.py);三態/空表不換表/退避/hang 不阻塞全綠 | `evidence/SC-2_SC-3_api-sidecar-real.txt`(真取數 6861 rows 落檔 `_version 1`;probe 47 industries) | `_refresh_stock_info` 對照表家族既有測試綠 |
| SC-3 類股面板 | `frontend/src/components/index/SectorSection.tsx` + `lib/sector-model.ts` + `IndexPage.tsx:139-146`;routes `app.py /api/market/sector(+members)` | `SectorSection.test.tsx` 22 案(含 T-3 四分支)+ route 三態/members 三語意(test_breadth_routes.py)+ App 全鏈接線(App.test.tsx R4 describe 3 案,mutation 驗證過) | 截圖:`evidence/SC-3a_sector-panel-industries.png` / `SC-3b_sector-drilldown-members.png` / `SC-3c_member-click-jump.png`(真資料,逐欄與 API 對照)+ user 過目(收尾請 user 確認) | R3 漲跌停列表區塊同頁並存(截圖內可見)+ `/api/market/breadth/rows` 1954 列完好 |
| SC-4 與 neigui 同時刻一致 | 同 SC-1/SC-2 管線 | SC-1 全套(fixture parity 層) | `evidence/SC-4_parity-20260806-204443.json`:同一份真 snapshot(2865 列)餵兩實作 → 47 產業名稱序列全等、逐業 avg_change_rate 差 0、members 全等(**窗口外降級層,brainstorm 明定**);盤中同時刻 REST 層記 next-time(optional) | universe 組裝路徑 = R2 parity oracle 既有測試綠 |
| SC-5 diff 事件源語意 | `breadth_engine.py:_diff_limit_events`(seed/對帳/cooldown)+ `market_breadth.py`(limit_judged) | `TestMarketLimitEvents`(test_breadth_engine.py:2285 起)16+ 案:三轉移/首輪即發/`test_restart_seed_replays_jsonl`/冷卻終態收斂/unjudged 跳過/hub None 早退/換日 re-seed/壞值逐筆(+T-2 touch 續數) | `evidence/SC-5_SC-6_market-events-live.txt`:events server 首輪 seed 空 → 1101/6488 即發 lock,id 文法逐字、as_of 隨牆鐘(S-1 生效) | `_apply` 三分法/序列落檔既有測試綠(105 案檔全綠) |
| SC-6 單一匯流排 + Discord 隔離 | `signal_hub.py:publish_market_events/market_event_state/today_signals 聯集`(+S-4 修 jsonl 先行) | test_signal_hub.py 92→更多案:`TestMarketEventState`(:1959)/publish 兩則→ jsonl 2・Discord 0/_closing/日別 warning/today 聯集+同日回歸(+T-5 route 防禦) | 同上 live 檔:today 端點回傳含 market 事件、jsonl 隔離落檔;Discord 由 notify=False + pytest 佇列 0 斷言 | 規則訊號 `_emit` 路徑既有測試綠(hub 檔全綠);今晨 prod 真 jsonl(207 則)未受影響 |
| SC-7 時間軸 | `frontend/src/components/index/SignalTimelineSection.tsx` + `signal-model.ts kindLabel` + `useSignalFeed` include 分族 | `SignalTimelineSection.test.tsx` 21 案(倒序/badge/chips 過濾/分族擠壓/同軸/點列)+ App 全鏈(timeline row click) | 截圖:`SC-7a_timeline-initial.png` / `SC-7b_timeline-market-events.png`(兩事件列+badge title 逐字)/ `SC-7c_chip-market.png`+`SC-7c_chip-cdp-empty.png` / `SC-7d_row-click-jump.png` + user 過目 | corr 區塊同頁並存;console 零新增 error(兩輪各查) |
| SC-8 rail/toast 不受汙染 | `useSignalFeed.ts`(exclude 預設 + queryKey 帶模式)/ `useSignalAlerts.ts` 早退 / `signal-model.ts isMarketKind` | useSignalFeed 測試(250 market + 3 自選 → 3 則;雙掛載雙 fetch — R1 P0 mutation 驗證)+ useSignalAlerts 早退案 + StockPage rail 案 | `evidence/SC-8_rail-no-market.png` + DOM 查證(market 字樣零洩漏) | 既有 SignalRail/alerts 全部測試綠(1661 全套) |

**結論:8/8 PASS**(UI SC 的第二層 = user 過目,收尾回報逐條列出)。
無 FAIL 分流;rollbacks 空;meta-cycle 未觸發。
