---
name: finmind-conventions
description: FinMind 接入慣例與配額真相。接新 FinMind dataset、寫 probe 腳本、設計 fan-out endpoint、評估冷載入成本、寫 backend test 碰到 FinMindClient 時先讀。含 Bearer 認證、共用 window 設計、6000 req/hr 配額、conftest test 基建。
---

> 來源:2026-07-06 自 neigui 專案複製。文中「樣板」檔案路徑(services/finmind.py、conftest.py、lib/api.ts 等)指 neigui repo(C:\side-project\neigui)的 code,本專案對應實作落地後再改寫為本地路徑。

# FinMind 接入慣例

## 認證與 token

- **Sponsor tier 必須用 `Authorization: Bearer <token>` header**,**不是** `?token=` query。`?token=` 會回 400 "Token is illegal"。Probe / 直 httpx 呼叫都要套。`FinMindClient._get` 已是這個 pattern,跟著用。(Trigger:新接 FinMind dataset、寫一次性 probe 腳本時)
- **JWT 過期是日常事件**:token 的 `exp` claim 是 unix epoch,內嵌在 JWT payload。要備好「token 過期 → 真實環境驗證 blocked」的 fallback 設計(hand-built fixture + 標 known risk + real-env 驗證 deferred 路線,對應 /feat Phase 6 的 infra_fail 標準 case)。(Trigger:進入 real-env 驗證前)

## 全市場 dataset 實測量級(2026-08-06,R2 breadth 落地)

- `taiwan_stock_tick_snapshot`:**單一 request 回全市場**,盤中實錄 **2865 列**;`date` 欄
  格式 `"YYYY-MM-DD HH:MM:SS.ffffff"`(**naive、含微秒、逐檔各不相同**,偶有 Z 尾 UTC 變體 —
  `market_breadth.max_tick_datetime` 已兩者兼容 + `upper_bound` 夾制髒時刻)。
- `TaiwanStockInfo`:實錄 **4300 列**(舊估 1.6 萬是錯的);`breadth_fetch.fetch_stock_info`
  的截斷觀測門檻因此定 `< 3000` warning。
- `TaiwanStockDispositionSecuritiesPeriod`:60d 窗實錄 235 列;參數名 `start_date`/`end_date`。
- `TaiwanStockIndustryChain`(2026-08-06 R4 probe + 落地):**單一 request 回全表 6861 列**
  (47 industries / 512 subs),欄位 `date/industry/stock_id/sub_industry`;**一檔可屬多
  產業**(2317 落 4 個)、同 (industry,sub) 內可有重複列(parse 去重);**缺 `sub_industry`
  的列 neigui 口徑是整列丟不是進 "" 桶**(`sector_rotation.rows_to_chain_map`)。靜態表
  7 天 disk cache 即可(`chain_store` + `breadth_engine` 獨立刷新 task,不掛 poll 輪)。
- 本專案接入樣板:`copycat/server/breadth_fetch.py`(urllib + Bearer、402 不重試、
  TimeoutError 獨立列)+ `server/finmind_token.py`(token 解析單一份)+
  `breadth_engine`(退避 10→60s、quota 300s、map 失敗保前值不動 TTL)。
- 盤中驗證走側車 server(CLAUDE.md §8 2026-08-06 條)。

## 配額真相(2026-07-03 實測)

- **真瓶頸 = 每小時 6000 requests(rolling window),不是 per-second rate**:一檔冷 `history/major`(days=540)~360 req → **每小時只能冷載入 ~16 檔**;燒乾後全面 402 → 前端 502(HTTPStatusError)/ 503(JSONDecodeError 是 ValueError 子類)。
- `FINMIND_RATE_LIMIT_PER_SEC` code 預設 40(`services/finmind.py::get_finmind_rate_limiter`):拉高只會燒配額更快 + abort 前已燒的更多。**結構性解法是砍每檔 request 數,不是調 rate**。
- **檢查配額**:`GET api.web.finmindtrade.com/v2/user_info`(Bearer)看 `user_count / api_request_limit`。counter 有 5-8s 批次延遲 + rolling window aging 噪音,當驗證 side-channel 用時要先量 idle drift。
- Trigger:出現成串 502/503 / 設計新 fan-out endpoint / 評估冷載入成本時。

## 共用 window 設計

- `services/finmind.py::fetch_taiwan_option_daily_window` 是「一份 250-day window 給三個 endpoint 共用」的範本。新 chip endpoint 跟著:
  - 用 `_run_once(f"window_{cache_key}", ...)` inflight dedup
  - Invalidation 必須在 `_run_once` coroutine 內、dedup 之後、實際 fetch 之前
  - parse cache 用 `_invalidate_chip_parse_caches(end_date)` pattern delete(`utils.cache.chip_cache_dir().iterdir()` 單次掃)
- Refresh 流前端要設「全 hook refresh 一起跑」(`mp.refresh(); ow.refresh(); pcr.refresh(); inst.refresh()`),**不要**用 `queryClient.invalidateQueries` cascade — cascade 不會帶 `refresh=true` 到後端,sibling 撞 parse cache 拿到 stale。

## Service module 呼叫 FinMind

- **新 service module 走 FinMind 要 wrap `get_finmind()` per-module**:寫成 `def get_finmind(): from services.finmind import get_finmind as _real; return _real()`(`services/market_universe.py` 是樣板),test `monkeypatch.setattr(mu, "get_finmind", ...)` 才能 patch 不影響其他 service module。**禁止直接 `from services.finmind import get_finmind`** 進 service module(test fixture 就無法獨立 swap)。(Trigger:新 service module 需呼叫 FinMind 時)

## Backend test 基建

- `backend/tests/conftest.py` 統一處理 `FinMindClient` singleton reset + `FINMIND_TOKEN` env + `CHIP_DATA_DIR` env + `NoOpBucket` 跳過 rate limiter。每個新 test 檔**不**要再寫 `_reset_singleton`,直接用 conftest 的 autouse。`bypass_finmind_rate_limiter` 是 opt-in fixture(非 autouse)。(Trigger:新增 backend test 檔時)


---

# §8 遷移附錄(2026-08-10,內容未改)

- **`TaiwanStockPrice` 無 data_id 全市場回傳含權證等**,一天 ~3 萬 rows;334 天真跑灌了 4.2M
  rows 進 prices.csv。`backfill_finmind` 已內建 known_ids 過濾(冷啟動空檔會 warning),別移除。
  (2026-07-07,Trigger:碰 backfill / 新增 FinMind dataset)
- **`TaiwanStockDayTrading` 的 `BuyAfterSale` 欄位 'Y' 或 '＊' = 僅可先買後賣** — 對先賣後買的
  空方策略即不可交易,當沖資格過濾必須把這類標記視為 excluded。(2026-07-10,Trigger:當沖資格
  proxy / DayTrading 過濾)
- **`TaiwanOptionDaily` 口徑**(2026-08-05 真樣本):每契約/履約價/CP 有 `trading_session ∈
  {position, after_market}` 兩列,**OI 只在 position 列**;`contract_date` 值域含月(202608)、
  週(202608W1)、每日(202608F1)→ 月契約用精確等值 filter 自然排除;**全域 max OI 會選到
  深度價外垃圾履約價**(實測 call max @55000),撐壓要在現價帶內(±10%)取 max。
  (Trigger:選擇權 OI / 撐壓線 / 新增 TaiwanOption* dataset)

- **期貨 / 選擇權 chip 的四支具名 dataset**(§5 補強資料源,2026-08-10 回填):
  `taiwan_options_snapshot` / `taiwan_futures_snapshot`(備援,主要走 TC4 push)、
  `TaiwanOptionInstitutionalInvestors`(+`AfterHours` 夜盤)、
  `TaiwanOptionOpenInterestLargeTraders`(大戶 OI)、
  `TaiwanOptionFinalSettlementPrice`(結算價)。
