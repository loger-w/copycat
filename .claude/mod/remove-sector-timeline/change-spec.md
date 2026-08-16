# change-spec — 刪除台股綜合「類股強弱」與「訊號時間軸」subtab(含後端 API / poller / 快取 / config / verify 注入通道)

分支 `mod/remove-sector-timeline`;現況表 `current-state.md`(同目錄,行號以其為準)。
規格來源:user 拍板 prompt `docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R1
+ 拍板 D10(「清乾淨,不留任何死碼」)。**分流判定:已成形方案(來源 = user 撰寫 / 拍板文件
→ 預核准),grilling 只做疑點裁決,無方向性抉擇需停。**

規模:L(前後端 ≥ 20 檔、刪對外 API 兩支、改一支 route 的查參)。

## 0. 疑點裁決(對應 current-state §6;全部 `[auto-default]`,理由均落 D10「不留死碼」)

| # | 疑點 | 裁決 |
|---|---|---|
| 1 | `useSignalFeed` include 半邊 | **刪**(`MarketMode` / `mergeByFamily` / `FAMILY_CAP` / `opts.market` / `?market=` 查參全拔,收斂回 `mergeSignals(baseline, live)`;queryKey 回固定 `["stock-signals-today"]`)。刪 timeline 後 100% 死碼,且 prompt 明文。 |
| 2 | `/api/stock/signals/today` 的 `market` 查參 + `_is_market_kind` / `_MARKET_KIND_PREFIX` | **刪**。事件源(`publish_market_events`)同 PR 消失,過濾只剩「當日 jsonl 殘留列」一種語意,見 §5 edge 2。 |
| 3 | 前端 `SignalKind.market_*` / `isMarketKind` / `kindLabel` market 分支 / `useSignalAlerts` 早退 | **刪**(prompt 明文)。殘留列由 `kindLabel` 的「未知 kind 原樣回傳」兜底,不白屏。 |
| 4 | `SignalHub.today_signals` 牆鐘日聯集(R2-3)+ `TestTodaySignalsUnion` | **留**(非死碼:engine 缺席時仍是 today 端點的日別來源;屬 XR-3 行為不屬 R4)。列 next-time「可簡化」。 |
| 5 | `__main__.VERIFY_FAIL_DATA_DIR` + `_clear_chain_cache` | **刪**(prompt 明文;唯一存在理由 = chain 檔跨 run 持久)。`[amendment 2026-08-16: review R4]` 注入本身由 `verify._fail_if_injected` 直讀 env,不經 `__main__`;`__main__` 的 `if os.environ.get(FAIL_ENV_KEY) == "1":` 區塊 body 只剩兩行被刪 → 改為單行 `logger.info("verify 失效注入模式:四支取數全拋,落檔目錄 %s", data_dir)`(保留 import 與可觀測性,避免空 body)。`VERIFY_BREADTH_FAIL=1` 落 `VERIFY_DATA_DIR`。 |
| 6 | `test_signal_routes.py` 以 market 事件為載具的 XR-3 三測試 | **改載具不刪測試**:改用規則訊號 `limit_lock`。`[amendment 2026-08-16: review R1/R2]` 具體做法(helper `_emit_rule_signal(client, hub, *, trade_date)`):(1) watchlist 種子 `2330`(沿 `test_basis_falls_back_to_empty_daily_bars` 寫法,先斷言 `hub._watch == {"2330"}`);(2) **detector 有 `_in_session` 09:00–13:30 gate 且 `create_app` 未注入 `now_fn`** → helper 內 `monkeypatch.setattr(signal_state, "_SESSION_START", time(0,0))` / `_SESSION_END = time(23,59)`(模組層常數,每次呼叫都讀);(3) `portal.call(hub.on_tick, "2330", tick, state)` 送**兩筆** tick(首 tick 只初始化 `_prev`),`tick.trade_date` = 傳入的 `trade_date`(牆鐘日 / engine 日別,**不是** `_tick` 預設 2026-08-04),`state = _state(locked_up=True)`(ask 側無限價檔 → `_eval_limit_tick` 直接產 `limit_lock`,不依賴 CDP basis / cum_vol);helper 可自帶 `_tick` / `_state` 副本或從 `test_signal_hub` import。備援(on_tick 路徑仍打不通時):直接 `portal.call(hub._emit, event, rule, state)`(本檔既有測試已慣例碰 `hub._watch` / `_basis_cache` / `_trade_date_fn` 私有面)。
`[amendment 2026-08-16 r2: review R2-1/R2-2/R2-6/R2-7/R2-8]` **載具細節釘死**:(i) 鎖漲停複合簽名要求 **成交價 == `ctx.upper_milli`** 且 ask 側無限價檔 → `state = _state(upper=110_000, locked_up=True)`,兩筆 tick = `_tick(109_000, trade_date=td)` + `_tick(110_000, cum=2, trade_date=td)`(**照抄 `tests/server/test_signal_hub.py:319-321` `_Harness.lock_up`**);(ii) `_tick` / `_state` **自帶副本**放 `test_signal_routes.py` 模組層(`tests/` 無 `__init__.py`,跨檔 import 會讓 pyright 紅);(iii) helper 簽名 `_emit_rule_signal(client, hub, monkeypatch, *, trade_date)`(monkeypatch 是 function fixture,由測試傳入);session gate 用 `_dt.time.min` / `_dt.time.max`(`_in_session` end-exclusive,`23:59` 會留一分鐘偶發紅);(iv) **Discord 出口中和**:規則訊號走 `_emit` 會依 `rule["notify_discord"]`(預設 True)入 Discord 佇列 → helper 內 `monkeypatch.setattr(copycat.notify, "_URL_RESOLVED", True)` + `monkeypatch.setattr(copycat.notify, "_WEBHOOK_URL", None)`(bot token 已由 conftest 中和;webhook 的 `.env` 讀取路徑 conftest 沒罩,雖本機 `.env` 無 `DISCORD_WEBHOOK_URL`,仍不得依賴);(v) 備援 `_emit` 的入參:`rule = next(s.rule for s in hub._slots.values() if s.rule["kind"] == "limit_lock")`,`event = SignalEvent(kind="limit_lock", code="2330", price_milli=110_000, time="10:00:00", time_key="10:00:00.123", levels=(), direction="up", pct=None, touch_count=1)`(欄位見 `copycat/live/signal_state.py:63-73`),同樣先做 (iv)。**簿路 `on_book` 方案作廢**(`evaluate_book` 只產 `limit_open` 且需 tick 先設 latch)。斷言改「收到 `type=signal` 且 `code=2330`、`kind=limit_lock`」與 `trade_date == 牆鐘日`,不再釘 market id 格式。 |
| 7 | 五→四元組的 arity 測試 | **改寫不刪**:`TestFetchersArity` 送三元組驗「預期 4 收到 3」;`test_verify_breadth_fail_injects_all_five` 改「四支」;`TestProdWiring` 拿掉 `fetchers[4]` 斷言。 |
| 8 | 文件慣例 | `docs/next-time.md` 兩節**加註作廢**(不物理刪;沿 08-15 prompt「標過期」口徑);spec R4 節加「2026-08-16 已刪除」註記。 |
| 9 | `.claude/skills/e2e-conventions/SKILL.md` | 本 repo `.claude/skills/` 下**不存在**該檔(grep 證實只有 finmind-conventions 與 ops-discipline 命中)→ 無事。 |
| — | 三類 commit 順序 | 本案 **🔴 → 🔵**(顯式偏離 /mod 預設 🔵→🔴):四元組收斂**依賴**引擎 chain 段先刪(否則建構子仍需第五槽);docstring 同步同理。🟢 無。 |

## 1. 成功條件(SC)

| SC | 條件 | 驗證方式 |
|---|---|---|
| SC-1 | 台股綜合頁 subtab 列只剩「漲跌停」「相關係數」兩顆(順序不變),`localStorage[INDEX_SUBTAB_KEY]` 殘值 `sector` / `timeline` 開頁落回「漲跌停」 | vitest `IndexPage.test.tsx` s1(2 顆 tab 文案)/ s2、s2b(殘值 fallback);截圖 `evidence/SC-1-subtabs.png` —— `[amendment 2026-08-16: review R7]` **取證通道一律 `python -m copycat.server --verify`(port 8722,`fake_breadth_fetchers` 已同 PR 收四元組)+ vite dev proxy 指 8722;不得抄 `.claude/mod/overview-subtabs-breadth-colors/evidence/sidecar_server.py`(五元組 + `fetch_industry_chain`,本 PR 後 ImportError / arity ValueError → 家數帶全空與「刪過頭」同形)**;`[amendment r2: R2-3]` `frontend/vite.config.ts:9` `BACKEND` 寫死 8721 → 取證期間**臨時**改 8722,截圖後**還原**;SC-9 增列 `git status --porcelain frontend/vite.config.ts` 為空的檢查 |
| SC-2 | 前端**零**引用 `SectorSection` / `SignalTimelineSection` / `sector-model` / `isMarketKind` / `mergeByFamily` / `FAMILY_CAP` / `market_limit_*`;`useSignalFeed` 只打裸 `/api/stock/signals/today` | `npx tsc -b` + `npx eslint src` 0 error;`grep -rn` 證據落 verification.md §D |
| SC-3 | 後端 `GET /api/market/sector` / `/api/market/sector/members` → 404;`GET /api/stock/signals/today?market=exclude` 仍 200 且與裸 URL 同結果(FastAPI 忽略未知查參 —— 舊前端 cache 不炸) | pytest `test_breadth_routes.py::TestSectorRemoved`(新,兩支 404)+ `test_signal_routes.py` 既有 today 測試;verify server `curl` 落 verification.md |
| SC-4 | `BreadthEngine` 建構子無 `chain_fetch`;`BreadthFetchers` 為四元組;`app._make_breadth` 對非四元組拋 `ValueError("...四元組")`;`verify.fake_breadth_fetchers()` 回四元組 | pytest `TestFetchersArity`(改寫)、`test_verify_breadth_fail_injects_all_five`(改四支)、`TestProdWiring` |
| SC-5 | `SignalHub` 無 `publish_market_events` / `market_event_state` / `_kind_text` market 分支 / `_market_date_warned`;`BreadthEngine` 無 `attach_signal_hub` / `detach_signal_hub` / `_diff_limit_events` / chain 全套;`app.py` 不再對 breadth 掛 hub | `grep -rn` 零命中(verification.md §D)+ pyright 0 error(unused import 會被 ruff F401 抓) |
| SC-6 | 死碼零容忍:`grep -rn "sector\|chain\|market_limit\|market_kind\|timeline\|rotation\|industry" copycat frontend/src tests` 只剩「無關命中」,逐條列出並說明(對照 current-state §4 的保留理由);`[amendment 2026-08-16: review R6]` **另加中文死註解掃描** `grep -rn "廣度事件\|類股\|輪動\|時間軸\|鎖板事件\|產業鏈\|對帳 seed\|attach_signal_hub\|五元組\|五個\|五支\|清檔\|market-verify-fail\|VERIFY_FAIL_DATA_DIR" copycat frontend/src tests`(`[amendment r2: R2-4]` 追加後六詞),命中只允許「保留機制的真實理由」(逐條說明) | verification.md §D 附兩份完整輸出 + 逐條歸類表 |
| SC-7 | 白名單全活(§2):pytest 全綠、vitest 全綠;verify server(`--verify`,port 8722)`/api/market/breadth`、`/api/market/breadth/rows`、`/ws/breadth`、`/api/stock/signals/today` 200/連得上;前端家數帶 / 騰落線 / 漲跌停列表 / 相關係數 subtab 畫面正常 | pytest / vitest 數字;curl 輸出;截圖 `evidence/SC-7-*.png` |
| SC-8 | `VERIFY_BREADTH_FAIL=1 python -m copycat.server --verify` 起得來,`/api/market/breadth` 回 degraded / stale 語意而非 5xx,落檔目錄 = `data/market-verify/`(不再有 `market-verify-fail`) | 側車起服 log + curl 落 verification.md;pytest `test_main_wiring.py`(改寫的兩支) |
| SC-9 | 自動化 gate 全綠:`pytest -q` / `ruff check copycat tests` / `pyright` / `python -m copycat validate` / `npm test` / `npx tsc -b` / `npx eslint src` / `react-doctor --scope changed`(無新增 finding) | verification.md 逐條 exit code |
| SC-10 | 文件同步:CLAUDE.md 結構樹無 sector_rotation / chain_store / 類股輪動 / 鎖板事件字句;finmind skill `TaiwanStockIndustryChain` 條目標「已不接(2026-08-16 R1 刪除)」;ops-discipline 「jsonl 是 breadth 對帳 seed」理由改寫(隔離紀律本身保留);spec R4 節 + next-time 兩節加註 | Read 對照 |

## 2. 不能破壞的既有行為白名單(reviewer / finder 必對照)

- W-1 家數帶 + 騰落線:`BreadthEngine` 家數 / 序列 / 對照表(`_sector_map`、`dedup_sector_map`、`primary_sector`、`assemble_universe`、`compute_breadth`)/ 退避 / `breadth-*.json` 落檔與 restore / `/api/market/breadth` / `/ws/breadth`;`BreadthBand.tsx` / `AdvanceDeclineChart.tsx`;`useBreadth`。
- W-2 漲跌停列表 + 連板:`_maybe_arm_streaks` … `_restore_streaks`、`rows_state()`、`limit_streaks.py`、`fetch_daily_prices` / `fetch_snapshot` / `fetch_stock_info` / `fetch_disposition`、`/api/market/breadth/rows`;`LimitListSection.tsx`。
- W-3 個股訊號:`SignalHub` 規則引擎 / `on_tick` / `on_book` / `_emit` / jsonl 佇列 / Discord 佇列與節流 / `today_signals`(含牆鐘日聯集)/ `read_signals` / 規則 CRUD;`/api/stock/signals/today`(裸 URL 語意不變:回當日全部訊號)/ `/api/stock/signals/rules*` / `/ws/stock` 載 hub 訊號;`StockEngine.attach_signal_hub / detach_signal_hub`(同名不同 class,勿誤刪);前端 `useSignalFeed`(exclude 語意退化為「全部」)/ `useSignalAlerts` toast 與嗶聲 / `SignalRail` / `mergeSignals` / `formatToastText`。
- W-4 XR-3:TC4 不在時 hub 恆建、規則 CRUD 可用、today 200、`/ws/stock` 不立即 close 且首則 status seed、hub 訊號經 app 層 broadcaster 上 WS(測試改載具後仍鎖)。
- W-5 相關係數 subtab(`CorrSection`)原位不動(R2 才升頂層)。
- W-6 `INDEX_SUBTAB_KEY` 白名單還原:非法值 → `limit`;`[amendment 2026-08-16: review R10]` `ORPHAN_STORAGE_KEYS` 現有**六**鍵(`stock-ladder-open` / `stock-wl-group` / `copycat-corr-open` / `copycat-limit-list-open` / `copycat-sector-open` / `copycat-signal-timeline-open`)**一個都不刪**(後四支是 08-14 subtab 改版的孤兒鍵回歸,與本次無關)、**不新增**(`INDEX_SUBTAB_KEY` 殘值靠白名單 fallback,不進孤兒鍵)。
- W-7 `verify.py`:`FAIL_ENV_KEY` 四支取數失效注入、`_BREADTH_INFO_ROWS`(含 `industry_category` 欄 —— 與 `_BREADTH_CHAIN` 是兩份常數)、`_snapshot` / `_snapshot_stamp` / `neutralize_external_env`;`--verify` 不可用 8721 的守衛。
- W-8 `BreadthConfig` 其餘欄位與 `load_breadth_config` 未知鍵 raise 語意;`configs/breadth.json` 本機不存在(current-state §5)。
- W-9 同名無關符號:`timeframe.ts::MarketMode`(K 線刻度)、TXO option chain(`ChainAggregator` 等)、capital balance/cancel chain、promise chain 註解 —— 一律不動。
- W-10 `tests/fixtures/record_breadth_parity.py`、`tests/test_market_breadth.py` 的 sector map 測試(R2 parity oracle)不動;只刪 `normalize_universe_rows` 三支。

## 3. Backward compat / migration

- 對外 API:`/api/market/sector*` 刪 = 404。唯一 caller 是同 PR 刪除的 `sector-model.ts`;無外部消費者(私人單機工具)。無 deprecate window。
- `?market=` 查參:FastAPI 對未宣告查參**忽略**,舊 bundle 打 `?market=exclude` 仍 200 → 前後端部署順序無關。
- 資料:`data/market/industry_chain.json`(769 KB,08-11)成孤兒檔;`data/market-verify-fail/` 若存在同理。**PR 說明列路徑提醒手刪,PR 不動 data/**(git-ignored runtime 產物)。
- `data/signals/<today>.jsonl` 若含 `market_limit_*` 列(prod 若在 08-16 之前已跑且同日重啟才會):today 端點照回、前端 `kindLabel` 原樣顯示 kind 字串、`useSignalAlerts` 會 toast 一次(僅 live 推播才 toast;baseline 不 toast)。實際上事件源已消失,live 不會再有;殘留只影響同日 rail 顯示,隔日檔翻頁自癒。**零遷移碼**。`[amendment 2026-08-16: review R8]` **代價補述**:`mergeSignals` cap 200 在過濾之前 —— 漲停潮日的數百則殘留列會把自選訊號擠出 rail(白名單 W-3 的一日靜默降級窗)。規避 = ops 動作,PR 說明列:**非交易日 / 收盤後部署重啟**(本輪 08-16 週日 merge 即滿足);若必須交易日盤中重啟,先把 `data/signals/<today>.jsonl` 另存改名。
- localStorage:`INDEX_SUBTAB_KEY` 殘值走既有白名單 fallback,零遷移碼(W-6)。
- 可逆性:純刪除,`git revert` 單 PR 即還原;無 schema / cache version 變動(`BreadthConfig` 是刪欄位,舊 config 檔若含該鍵會在 load 時 raise —— 本機不存在,PR 說明提醒)。

## 4. Out of scope

- 相關係數升頂層 tab、綜合頁一頁總覽(R2)。
- `SignalHub.today_signals` 牆鐘日聯集簡化(next-time)。
- 清 `data/` 孤兒檔(ops 手動)。
- 歷史 artifact(`.claude/feat/market-overview-r4-sector-signals/**`、舊 review-diff)一律不動。
- `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` 內容不砍,只加註。

## 5. Edge cases

1. `INDEX_SUBTAB_KEY` = `"sector"` / `"timeline"` / 亂碼 / getItem 拋 → 一律 `limit`,不白屏(IndexPage.test s2 / s2b / s3 改寫後續鎖)。
2. 當日 jsonl 殘留 `market_limit_lock` 列 → today 端點原樣回、rail 顯示 kind 原字串、不炸(`kindLabel` 未知 kind 分支;`signal-model.test.ts` 既有「未知 kind 原樣回傳」案保留)。
3. `_make_breadth` 收到舊五元組(例如舊側車樣板)→ `ValueError` 明說「預期 4 收到 5」(TestFetchersArity 改寫覆蓋 3 與 5 兩側)。
4. `VERIFY_BREADTH_FAIL=1` 且 `data/market-verify/` 已有前次 `breadth-<date>.json` → restore 後四支注入仍全拋 → 家數帶 degraded(不再有 chain 快取「吸收注入」的假通過問題,因為 chain 面板已不存在)。
5. hub 無 engine 時 `on_tick` 載具:`code` 必須在 `_watch`(watchlist 種子),否則早退無訊號 —— 測試 helper 先斷言 `hub._watch == {"2330"}`(沿 `test_basis_falls_back_to_empty_daily_bars` 既有寫法)。

## 6. Diff 級章節(逐檔;三類標記)

### 🔴 commit A `fix(frontend): 刪類股強弱 / 訊號時間軸 subtab 與 market 事件分族`(前端一批)

| 檔 | 動作 |
|---|---|
| `components/index/SectorSection.tsx` / `.test.tsx`、`SignalTimelineSection.tsx` / `.test.tsx`、`lib/sector-model.ts` / `.test.ts` | 整檔刪 |
| `components/index/IndexPage.tsx` | 刪 import L21-22、SUBTABS 兩列、render 分支 L220-226 與其註解;檔頭 docstring L1-13「四個 panel」改「兩個 panel」口徑(保留「掛載閘」設計說明);Props `active` 註解 L121-126 拿掉「類股強弱」字句 |
| `lib/constants.ts` | L76 註解值域改 `"limit" \| "corr"`;`ORPHAN_STORAGE_KEYS` 不動 |
| `lib/signal-model.ts` | 刪 `SignalKind` market 兩值(含註解)、`isMarketKind`、`kindLabel` market 分支(L91-96) |
| `hooks/useSignalFeed.ts` | 刪 `FAMILY_CAP` / `MarketMode` / `mergeByFamily` / `opts` 參數 / mode 分支;`fetchToday()` 打裸 URL;queryKey 固定 `["stock-signals-today"]`;檔頭與 L17-19 註解同步 |
| `hooks/useSignalAlerts.ts` | 刪 L89 `isMarketKind` 早退 + L86-88 註解 + import |
| `hooks/useMarketBars.ts` | L45 註解改用別的例子(純字) |
| `App.test.tsx` | 刪 fixture `SECTOR_STATE` / `SECTOR_MEMBERS` / `TIMELINE_SIGNAL`、`appFetch` sector 路由、helper `openSectorMember` / `openTimelineRow`、三支 it;**第 4 支 it(切離 tab → 分 K 停輪詢)搬到新 describe 保留** |
| `IndexPage.test.tsx` | 刪 `SECTOR_STATE` fixture 與 sector stub;subtab describe 改寫:s1 = 兩顆 tab;s2/s2b 殘值 fallback 用 `"sector"` / `"timeline"` 當非法值;s2c/s3/s5b/s7 的切換中繼站改 corr ⇄ limit(測試意圖不變:fallback / getItem 拋不白屏 / 切走 unmount) |
| `signal-model.test.ts` | 刪 kindLabel market 兩案 + `describe("isMarketKind")` |
| `useSignalFeed.test.tsx` | 刪 include 案與雙 query key 案;exclude 案改「無 market 事件概念:單一 queryKey、裸 URL」(斷言 fetch URL 無查參);`[amendment 2026-08-16: review R3]` **一併刪 L125-142 的 `// 🟢 market-overview R4(SC-8)` 註解、模組級 helper `mkt()` 與 `isMarket()`**(改完零引用 → eslint no-unused-vars),describe 標題去 market 語意(改「useSignalFeed — 單一 baseline 來源」) |
| `useSignalAlerts.test.tsx` | 刪「market 事件全免疫」it |
| `StockPage.test.tsx` | 刪「同一條 bus 上的 market 事件不進 rail」it(L534-546);其餘不動 |

**該紅的既有測試**(先改紅再改實作綠):IndexPage.test s1/s2/s2b、useSignalFeed.test exclude 案(URL 斷言)。**不該紅**:其餘全部 vitest(1898 − 刪除數)。

### 🔴 commit B `fix(backend): 刪 /api/market/sector*、industry chain poller/快取、全市場鎖板事件、verify FLIP 通道`(後端一批)

| 檔 | 動作 |
|---|---|
| `copycat/sector_rotation.py`、`copycat/server/chain_store.py`、`tests/test_sector_rotation.py`、`tests/server/test_chain_store.py` | 整檔刪 |
| `copycat/server/app.py` | 刪兩支 sector route(L1428-1468);`stock_signals_today` 拿掉 `market` 參數 / docstring / 過濾;刪 `_MARKET_KIND_PREFIX` / `_is_market_kind`(L109-117);刪 `breadth.attach_signal_hub` 呼叫與註解(L776-782);`[amendment 2026-08-16: review R5]` 關機段**只刪 L825 `booted.breadth.detach_signal_hub()` 一行與 L822-824 註解**;L814-819 反序 close 註解**改寫**(拿掉「breadth 是 hub 生產者 / 先摘先收」理由,保留其餘引擎反序說明);`if booted.breadth is not None:` / `try:` / `await booted.breadth.close()` / `except` **全留**(W-1)。`ChainFetch` import 與 `_make_breadth` 第五槽**留給 commit C**(此 commit 只把 `chain_fetch=` 傳參拿掉 → 但引擎建構子若已刪參數則必須同時改;見下)。`[amendment 2026-08-16: review R6]` **中文死註解改寫**:L347、L377、L514-517(`_make_signals` docstring「廣度事件鏈是純 FinMind」→ 改「規則 CRUD 是純檔案操作、today/WS 匯流排在 app 層」)、L996、L1556 —— 凡以「廣度事件」為 XR-3 / today / ws_stock 行為理由的句子,改成不依賴已刪機制的真實理由 |
| `copycat/server/breadth_engine.py` | 刪 current-state §2b 列的全部 chain / market 段(docstring、import、`_CHAIN_FILE`、`_MARKET_*`、`ChainFetch`、`MarketSignalSink`、建構子 `chain_fetch` 參數與 state、`attach/detach_signal_hub`、`start/close` chain 收攤、`sector_state` / `sector_members`、`_maybe_arm_chain` 呼叫、`_apply` 的 normalize/rotation/diff 段、`_recompute_rotation`、`_diff_limit_events`、「產業鏈刷新」小節)。**保留**清單見 current-state §2b L59 / §3 |
| `copycat/breadth_fetch.py` | 刪 `_CHAIN_DATASET` / `CHAIN_MIN_ROWS` / `fetch_industry_chain` |
| `copycat/breadth_config.py` | 刪 `event_cooldown_secs` / `chain_ttl_hours` + 驗證 |
| `copycat/market_breadth.py` | 刪 `_ROTATION_NUMERIC_FIELDS` / `normalize_universe_rows`(唯一非測試 caller 在 engine) |
| `copycat/server/signal_hub.py` | 刪 `_MARKET_LOCK/_MARKET_OPEN/_MARKET_RULE_TAG`、`_kind_text` market 分支、`_market_date_warned`、`publish_market_events`、`market_event_state` 與小節標題;`[amendment 2026-08-16: review R6]` `today_signals`(L920-925)/ `read_signals`(L947)docstring **改寫保留理由**:牆鐘日聯集 = engine 缺席時 hub 以牆鐘為日別寫檔、engine 在場時以 engine 日別寫檔,兩者跨日窗可能不同,聯集讓 today 端點兩種來源都看得到(XR-3);不再提「廣度事件」「對帳 seed」 |
| `copycat/server/breadth_engine.py`(補) | `[amendment 2026-08-16: review R6]` L241 註解「類股熱力圖的原料」改寫為 `_sector_map` 的真實用途(家數帶 universe 白名單 / degraded 判定) |
| `copycat/server/__main__.py` | 刪 `CHAIN_FILENAME` import、`VERIFY_FAIL_DATA_DIR`、`_clear_chain_cache`、`main()` 內兩行;L185-189 註解改為「hub 落點隔離:verify 事件不得寫進 prod `data/signals/`」 |
| `copycat/server/verify.py` | 刪 `_BREADTH_CHAIN`、`FLIP_ENV_KEY`、`_FLIP_1101`、`_flip_locked`、`_industry_chain`、`_snapshot` FLIP 分支;`FAIL_ENV_KEY` 註解 L180-186 **整段重寫**(`[amendment r2: R2-4]` 四支取數點全拋、落檔目錄固定 `VERIFY_DATA_DIR`、不再有 fail 專用目錄與開機清檔);`fake_breadth_fetchers` 回四元組(型別 `BreadthFetchers` 收斂在 commit C —— **為讓 commit B 自身綠,B 內同步把 `BreadthFetchers` 改四元組與 `_make_breadth` 拆包改四**;commit C 只剩訊息文案 / docstring / 註解同步 —— 見 C) |
| `tests/server/conftest.py` | L7 註解「breadth 對帳 seed」理由改寫(隔離紀律不變) |
| `tests/server/test_breadth_engine.py` | 刪 `TestChainCache` / `TestSectorState` / `TestMarketLimitEvents`;fixture 拿掉 `chain_fetch=` |
| `tests/server/test_breadth_routes.py` | 刪 `TestSectorRest` / `TestSectorMembers` / `TestSignalHubWiring`;`_ok_fetchers` 去 `chain` 參數;`TestFetchersArity` 改「預期 4」(3 元組與 5 元組兩側);`TestProdWiring` 去 `fetchers[4]`;**新增** `TestSectorRemoved`(兩 URL 404) |
| `tests/server/test_breadth_fetch.py` | 刪 `TestIndustryChainRowCountLog` |
| `tests/test_breadth_config.py` | 刪 L27-28 兩斷言 + 三支 R4 測試 |
| `tests/test_market_breadth.py` | 刪 import + 三支 normalize 測試 |
| `tests/server/test_signal_hub.py` | 刪 `_market_event` helper、`TestMarketEvents` / `TestMarketEventState` / `TestMarketKindText`;`test_truncated_multibyte_tail_keeps_good_rows` 拿掉 `market_event_state` 斷言、fixture kind 改 `limit_lock` |
| `tests/server/test_signal_routes.py` | 刪 `_market_event` / `_market_event_id` / `_publish_market` / `TestSignalsTodayMarketParam`;三支 XR-3 測試改載具(§0 裁決 6);`[amendment 2026-08-16: review R6]` `TestSignalRoutesWithoutStock` class docstring L669-677「廣度事件鏈是純 FinMind」句改寫;`[amendment r2: R2-5/R2-9]` 刪 `import functools`(唯一使用在 `_publish_market`);`_wait_signal(client, signal_id)` 改 predicate 版 `_wait_signal(client, match: Callable[[dict], bool])`(新斷言 `kind=="limit_lock" and code=="2330"`,不釘 id);`_recv_until` 保留(WS 測試仍用);三支測試**改名 + docstring 同步**(`test_rule_signal_reaches_today_on_wall_clock_date` / `test_ws_stock_stays_open_and_carries_rule_signals` / `TestWsStockSharedBroadcaster::test_hub_signal_reaches_ws_when_engine_present` 名不變只改 body),保留「牆鐘日別 fallback」「不立即 close + status seed」「共用 broadcaster」三個真正的斷言意圖 |
| `tests/server/test_main_wiring.py` | 去 `CHAIN_FILENAME` import;`test_verify_fail_injection_uses_isolated_dir_and_clears_chain` 改為「FAIL=1 仍用 `VERIFY_DATA_DIR`,不清任何檔」(`[amendment R4]` 斷言 `create_app` 收到的 `breadth_data_dir == VERIFY_DATA_DIR`);`test_verify_without_fail_env_keeps_default_dir` 保留 |
| `tests/server/test_verify.py` | 去 `FLIP_ENV_KEY` import;`test_verify_breadth_fail_injects_all_five` 改四支(改名 `_all_four`);刪 `test_fake_chain_feeds_the_rotation_pipeline` / `TestBreadthFlip` |

**該紅的既有測試**:`TestFetchersArity`(訊息「預期 4」)、`test_verify_breadth_fail_injects_all_*`、`test_main_wiring` FAIL 注入測試、`test_signal_routes` XR-3 三支(載具改寫後先紅:呼叫 `publish_market_events` AttributeError → 改為 on_tick 載具後綠)、新 `TestSectorRemoved`(刪 route 前 200 → 紅)。
`[amendment 2026-08-16: review R9]` **事前標「該變」的 assertion 刪除**(鐵則 E 合法通道;理由一律 = 被斷言的生產者同 PR 刪除):(1) `test_signal_hub.py::test_truncated_multibyte_tail_keeps_good_rows` 的 `market_event_state` 三行斷言 + fixture kind `market_limit_lock` → `limit_lock`(`read_signals` / `today_signals` 兩斷言保留 —— 測試意圖「壞尾巴不吃掉好列」不變);(2) `test_breadth_routes.py::TestProdWiring` 的 `fetchers[4]` / `_chain_fetch` 斷言;(3) `tests/test_breadth_config.py::test_default_values` L27-28(`event_cooldown_secs` / `chain_ttl_hours` 預設值)。**不該紅**:其餘 pytest 全部。

### 🔵 commit C `refactor(backend): BreadthFetchers 四元組收斂之文案 / docstring / 型別註解同步`

- `app.py`:`BreadthFetchers` 型別 docstring(L165-176)去第五槽字句;`_make_breadth` 長度檢查訊息「預期 4」與 `raise ValueError("...四元組")`;`ChainFetch` import 已在 B 刪(否則 F401)。
- `verify.py` L119 小節註解「五元組」→「四元組」;`fake_breadth_fetchers` docstring 去第五支段。
- `breadth_engine.py` 模組 docstring 收斂為「家數 + 連板」兩段。
- 若 B 為求綠已改動上述任一行,C 只補剩餘文案;C 為空則省略(回報註明)。

### chore(docs) commit D `chore(docs): R1 刪除同步(CLAUDE.md 結構樹 / finmind skill / ops-discipline / spec R4 註記 / next-time 作廢)`

- `CLAUDE.md` L63-70;`.claude/skills/finmind-conventions/SKILL.md` L23-31;`.claude/skills/ops-discipline/SKILL.md` L31-45(理由改寫,紀律保留);`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` R4 節 + §7 Q5 加註;`docs/next-time.md` L189-228 整節加註「2026-08-16 R1 已刪除,整節作廢」、L1087-1134 除 XR-3 / FE-7 條外逐條標作廢;`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §0 表 R1 列標「已出貨(PR #)」。

### 新測試清單
- `TestSectorRemoved`(兩 URL 404)— 🔴 B。
- `test_signal_routes` XR-3 三支的新載具 helper(`_emit_rule_signal(client, hub, ...)`)— 🔴 B。
- `IndexPage.test` s2/s2b 以 `"sector"`/`"timeline"` 為非法值 — 🔴 A。
- `useSignalFeed.test`「fetch URL 無查參、單一 queryKey」— 🔴 A。

## 7. Known Risks
- 刪除量大(~4000 行測試 + ~1500 行實作),漏刪殘段由 SC-6 grep(英文 + 中文)+ ruff F401 + pyright + tsc 機械兜底;漏刪「保留段」由白名單測試兜底(pytest 2680 → 預期約 2600)。
- XR-3 載具改寫:主路 = `on_tick` + `_state(locked_up=True)` + session gate monkeypatch(§0 裁決 6);打不通 → 備援直呼 `hub._emit`;兩條都試不出 → 停下回報(鐵則 F),不砍測試。`[amendment 2026-08-16: review R1/R2 — 原「on_book」備援作廢]`

## 8. Review 記錄
- round 1:`change-spec-review-round-1.json`(P0×1 / P1×5 / P2×4,全 accepted,均已以 `[amendment 2026-08-16]` 落入上文)。
- round 2(限縮輪):`change-spec-review-round-2.json`(P0×0 / P1×3 / P2×6,全 accepted,以 `[amendment r2]` 落入上文)。退出:無 P0 → 進 §4 實作。

## 9. self_review_head
- `self_review_head: 5d501d82`(自評 round-1 + fix 波後 HEAD;fix 波只觸及 findings 內檔案,主 session 機械快篩)。
