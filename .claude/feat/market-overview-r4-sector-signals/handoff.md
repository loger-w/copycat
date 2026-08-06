# Handoff — R4(+ 台股綜合四輪)review 與修復 session

日期:2026-08-06。給 fresh session 的交接文件;本檔自足,不需要原對話。

## 0. 一句話現況

台股綜合 tab 四段 /feat 全數 merge 進 master(R1 PR#23 / R2 PR#26 / R3 PR#29 /
**R4 PR#31 = afea0e28**,state 已回寫 final_merge_sha);R4 自動化全綠
(pytest 2540 / vitest 1661 / ruff / pyright / validate 42),AI 截圖層全 PASS。
**未做**:user 過目(四輪)、盤中真環境層(見 §5)。本 handoff 的任務 =
fresh-context 復審 + 修復(前例:`stock-quintet-discussion` 五題復審抓到 1 P0)。

## 1. R4 交付面(review 的主要標的)

後端:
- `copycat/sector_rotation.py` — neigui 全等搬移純函式(chain_map / rotation / members)
- `copycat/server/chain_store.py` — chain 7 天快取落檔
- `copycat/server/breadth_engine.py` — **改動最重**:chain 獨立刷新 task、
  `_recompute_rotation` 單一寫入點、`sector_state/sector_members`、
  `_diff_limit_events`(**last_emitted 對帳制**:jsonl seed 回放 + 600s/桶冷卻 +
  分鐘域 gate `_append` 非 None)、`attach_signal_hub`(MarketSignalSink Protocol)
- `copycat/server/signal_hub.py` — `publish_market_events`(jsonl 先行、WS 後行、
  各自 try;trade_date 顯式傳入)、`market_event_state`(seed 回放)、
  `today_signals` 聯集讀({engine 日, 本機日} 升冪 + id 去重)、`?market=` 過濾
- `copycat/server/app.py` — `/api/market/sector(+/members)`、fetchers 五元組、
  attach/detach 接線;`verify.py`/`__main__.py` — FLIP / FAIL 隔離目錄 / 全天窗
- `copycat/market_breadth.py` — rows 加 `limit_judged`(copycat-only 鍵)

前端:
- `SectorSection.tsx`(三層展開 + 輪詢 gate `open && active && inTradingHours()`)
- `SignalTimelineSection.tsx`(倒序 / chips / 廣度 badge / 點列跳個股)
- `useSignalFeed.ts` — **queryKey 帶模式** `["stock-signals-today", market]`,
  exclude 預設(rail)/ include 分族各 cap 200(時間軸);`useSignalAlerts` 早退;
  `signal-model.ts` kind union + `isMarketKind` + `kindLabel` 兩案

事件 kind:`market_limit_lock` / `market_limit_open`;
id 文法:`{trade_date}-breadth-{code}-{kind}-{direction}-{as_of}`。

## 2. 已跑過的 review(勿重報已裁決項)

artifact 目錄 `.claude/feat/market-overview-r4-sector-signals/`:
- `design-review-round-1/2.json`:1 P0(靜默 baseline 吞開盤即鎖 → 對帳制改版)+
  9 P1 全修
- `impl-spec-review-round-1.json`:1 P0(TODAY_KEY 固定 queryKey)+ 3 P1 全修
- `code-review-round-1.json`:3 lens(事件鏈 / 測試空洞 / spec 對照)→ 4 P1 全修
  (rotation 換表不重算 / verify 取證通道×2 / App 接線零覆蓋)、9 P2 修、
  **1 rejected**:C-6 jsonl 佇列共用(量級安全,記 next-time)、1 errata(S-6)
- fix 波 mutation 驗證五處非 vacuous(App.test 接線 / SectorSection 分支)

**已裁決不修(復審時視為 known,除非找到新事實推翻)**:
1. KR-1(design.md 末節):engine trade_date 停滯日 today 聯集讀混入昨日自選列
   (外觀級;id 去重防重覆不防跨日混列)
2. C-6:廣度與規則訊號共用 jsonl 佇列 1000 drop-oldest(單輪數百 < 1000)
3. `--verify` 無 stock engine → hub None(CLAUDE.md §8 已記;事件鏈取證用
   `evidence/events_side_server_r4.py`)
4. 同頁 stale 標記兩款並存(SectorSection=bull「資料延遲」vs LimitList=amber「延遲」)
5. 成員表小型股成交額顯示 0.0(億元捨入)
6. index ws flake(`test_index_routes::test_ws_streams_index_payload`)— 既有、
   本輪三度目擊已在 `docs/next-time.md` 升優先度,**修它是獨立 /bug 不算 R4 回歸**

## 3. 建議 review 範圍(fresh context 的價值所在)

- **R4 深掃**(前次 code review 是 medium 檔位):對帳制的併發 / 時序邊界
  (poll loop 與 chain task 共享狀態、attach/detach 與 `_diff` 的競態)、
  `market_event_state` 對壞 jsonl 的韌性、前端 include 分族 cap 的排序邊界。
- **四輪整體交互**(單輪 review 看不到的):同一頁四個區塊(家數帶 / 列表 /
  類股 / 時間軸)+ corr 的輪詢與 WS 總負載、breadth_engine 一檔多職
  (家數 / 連板 / 類股 / 事件)的失效耦合、localStorage key 家族一致性、
  `/ws/stock` 單一匯流排上訊號量成長後的前端行為。
- **quintet 復審模式可沿用**:`.claude/feat/stock-quintet-discussion/` 有前例
  artifact(多 reviewer 分工 + 彙整)。

## 4. 修復紀律(修復波遵守)

- 共通鐵則照 `~/.claude/CLAUDE.md`;三類 commit 分離(🔴 行為 / 🟢 新增 / 🔵 重構);
  行為修 TDD 紅先行。subagent dispatch 一律顯式 `model: opus`。
- Review 產物落 `.claude/<flow>/<slug>/` 續號(`code-review-round-2.json` 起 —
  自評 round-1 已存在)。
- gate:`pytest -q` + `ruff check copycat tests` + `pyright` + `copycat validate` +
  (動 frontend)`npm test` / `npx tsc -b` / `npx eslint src`;
  指令不接 `| tail`;mutation 驗證防同秒 pycache(sleep 1)。
- **盤中不起第二台連 TC4 的後端**;FinMind/HTTP 層驗證用側車(§5 樣板),
  盤中不重啟 prod。

## 5. 真環境工具與未竟驗證層(修復 session 可順手補)

樣板(全部零 TC4,盤中可用):
- `evidence/breadth_side_server_r4.py` — fake TXO + **真 FinMind 五元組**,
  `SIDECAR_PORT` env(vite proxy 寫死 8721;prod 沒跑時可佔)
- `evidence/events_side_server_r4.py` — + FakeStockSource 讓 hub boot,
  事件鏈全鏈取證(jsonl 落隔離 tmp);搭 `VERIFY_BREADTH_FLIP=1`
- `evidence/sc4_parity_compare.py` — 同一份真 snapshot 餵 copycat/neigui 兩實作

未竟(窗口限定,非 blocker):
- SC-4 盤中同時刻 REST 對照(neigui `/api/market/snapshot?refresh=true` vs
  copycat `/api/market/sector`,同分鐘落檔 diff)— optional
- SC-7 盤中真事件入軸目視(09:01+ 漲停鎖板日最佳)
- 四輪 user 過目全部待做(`docs/next-time.md` 各輪節有可指認表述)

## 6. 關鍵文件地圖

- 機制真相源:`.claude/feat/market-overview-r4-sector-signals/design.md`(v3,
  changelog 含全部 review 修正)
- SC 定義:同目錄 `brainstorm.md` §3(含 amendments)
- 逐 task 記錄:`progress.md`(含每 task 裁決);Phase 7 表:`phase7-verification.md`
- 總 spec:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md`
  (§5 R4 已回寫拍板)
- 教訓:CLAUDE.md §8(verify 無 hub / 側車)、`docs/next-time.md` R4 節、
  `finmind-conventions` skill(IndustryChain 口徑)

## 7. 建議開場 prompt(新 session)

> 讀 `.claude/feat/market-overview-r4-sector-signals/handoff.md` 照它做:
> 對 R4(merged afea0e28,diff 範圍 `f9fff6a0..afea0e28` 的 copycat/frontend/tests)
> 做 fresh-context 深度 review + 四輪整體交互面,§2 已裁決項不重報;
> findings 走 receiving 三分類,accepted 修復入 master(TDD 紅先行,
> review JSON 續號落 artifact 目錄)。
