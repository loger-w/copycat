# current-state — 刪除台股綜合頁「類股強弱(sector)」與「訊號時間軸(timeline)」subtab

分支 `mod/remove-sector-timeline`;調研日 2026-08-16;唯讀調研(未動任何源檔)。
行號皆為**本次 grep / Read 的現行行號**(HEAD = e1e33ca5 之後的工作樹)。

## 1. 分流判定

**已成形方案(user 拍板 prompt:刪除 sector + timeline 兩個 subtab,含後端 `/api/market/sector*`、industry chain poller/cache、market_limit 事件、verify 注入通道)**。不走 brainstorm;本檔為 Phase 1 caller map,直接進 change-spec。
來源:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md`(該檔 L77/L88 已有對 `normalize_universe_rows` / `_clear_chain_cache` 的預先筆記,與本次調研結論一致)。

原調研清單逐項驗證結果:**全部項目仍存在,無一已被刪除;行號多數與原清單相符或小幅漂移**(逐檔表「備註」欄標注)。額外發現原清單**未列**的糾纏點:`tests/server/test_signal_routes.py`(`TestSignalsTodayMarketParam` 整 class + `TestSignalRoutesWithoutStock` 兩個以 market 事件為載具的 XR-3 測試)、`tests/server/test_signal_hub.py`(`TestMarketEvents` / `TestMarketEventState` / `TestMarketKindText` 三個 class + `test_truncated_multibyte_tail_keeps_good_rows` 內一句 `market_event_state` 斷言)、`tests/server/test_main_wiring.py`、`tests/test_market_breadth.py` 的 `normalize_universe_rows` 三個測試、`SignalHub.today_signals` 的牆鐘日聯集(R2-3)、`frontend/src/hooks/useMarketBars.ts:45` 註解、`StockPage.test.tsx:534-535` 註解、`useSignalAlerts.ts:88` 註解。

## 2. 逐檔表

### 2a. 前端

| 檔案 | 要動的符號/區段(現行行號) | caller 清單(檔:行) | 動作 | 備註 |
|---|---|---|---|---|
| `frontend/src/components/index/SectorSection.tsx` | 整檔 | `IndexPage.tsx:21`(import)、`:222`(render) | 整檔刪 | 唯一 caller;無 lazy/動態 import |
| `frontend/src/components/index/SectorSection.test.tsx` | 整檔 | — | 整檔刪 | |
| `frontend/src/components/index/SignalTimelineSection.tsx` | 整檔 | `IndexPage.tsx:22`(import)、`:226`(render) | 整檔刪 | 唯一 caller;是 `useSignalFeed({market:"include"})` 的**唯一**呼叫端(`:80`) |
| `frontend/src/components/index/SignalTimelineSection.test.tsx` | 整檔 | — | 整檔刪 | |
| `frontend/src/lib/sector-model.ts` | 整檔 | `SectorSection.tsx:18-23`、`SectorSection.test.tsx:14` | 整檔刪 | 唯一打 `/api/market/sector*` 的前端層 |
| `frontend/src/lib/sector-model.test.ts` | 整檔 | — | 整檔刪 | |
| `frontend/src/components/index/IndexPage.tsx` | import L21-22;`SUBTABS` 陣列 L39-43 中 `["sector","類股強弱"]`(L41)、`["timeline","訊號時間軸"]`(L42);render 分支 L222 / L226 + 緊鄰註解 L220-221 / L223-225 | — | 局部刪 | `SubTab` 型別(L45)自 SUBTABS 推導,自動收窄成 `"limit"\|"corr"`;`initialSubTab`(L52-60)白名單 fallback 機制**保留**,舊 localStorage 殘值 `"sector"/"timeline"` 由既有 fallback 接住 → 不需遷移碼 |
| `frontend/src/lib/constants.ts` | L76 註解值域 `"limit" \| "sector" \| "timeline" \| "corr"` | — | 局部改(純註解) | `ORPHAN_STORAGE_KEYS`(L25-32)已含 `copycat-sector-open` / `copycat-signal-timeline-open`(08-14 舊展開殼鍵)—— **不新增**,那是既有孤兒鍵回歸;`INDEX_SUBTAB_KEY`(L82)本身留 |
| `frontend/src/lib/signal-model.ts` | `SignalKind` 含 `market_limit_lock/open`(L19-20);`isMarketKind`(L24-31);`kindLabel` market 分支(L93-96) | `useSignalFeed.ts:15,45,83`;`useSignalAlerts.ts:10,89`;`SignalTimelineSection.tsx`(多處,隨刪) | **保留**(見 §3、§6 疑點 3) | 前端「防禦濾網」:jsonl 歷史列仍可能含 market kind;若拍板連型別一起縮,則需同步改 `useSignalAlerts.ts` / `useSignalFeed.ts` / `signal-model.test.ts:66-73,88-106` / `useSignalAlerts.test.tsx:204-220` / `StockPage.test.tsx:536-546` |
| `frontend/src/hooks/useSignalFeed.ts` | `FAMILY_CAP`(L23);`MarketMode`(L25);`fetchToday` mode 分支(L28-32);`mergeByFamily`(L39-50);`opts?.market` / `mode==="include"` 分支(L63-64, L83-85, L99) | `include`:僅 `SignalTimelineSection.tsx:80`;`exclude`(預設):`StockPage.tsx:69` | 局部刪(僅 include 半邊) | **必保留**:`exclude` 全套(`fetchToday`+`?market=exclude`、`isMarketKind` live 早退 L83、`mergeSignals`、`baselineError`)= 自選訊號 rail 資料源。include 半邊刪後為死碼;是否本輪一起拔屬 scope 拍板(§6 疑點 1)。**同名陷阱**:`frontend/src/lib/timeframe.ts:10` 另有 `export type MarketMode = "day"\|"week"\|…`(K 線刻度),被 `useMarketBars.ts` / `MarketChart.tsx` / `MarketPane.tsx` 用 —— **絕不能動** |
| `frontend/src/hooks/useSignalAlerts.ts` | `isMarketKind` 早退 L89;註解 L86-88(「要看這些事件請去綜合 tab 的訊號時間軸」) | App 常駐 | 保留邏輯;L88 註解改字 | 早退保護 toast/嗶聲不被 market 事件灌爆;刪 timeline 後註解漂移 |
| `frontend/src/hooks/useMarketBars.ts` | L45 註解引用 `SectorSection` 為範例 | — | 保留(註解改字) | 純文字漂移 |
| `frontend/src/App.test.tsx` | describe `"App 類股 / 訊號時間軸跳轉個股(R4 SC-3 / SC-7)"` L296-417:helper `openSectorMember` L306-314 / `openTimelineRow` L316-322、it L324-338、L340-351、L357-383 刪;fixture `SECTOR_STATE` L67-83 / `SECTOR_MEMBERS` L85-91 / `TIMELINE_SIGNAL` L93-107;`appFetch` 內 `/api/market/sector*` 路由 L131-137 | — | 局部刪 | **同 describe 第 4 個 it L389-417(「切離台股綜合 tab → 大盤分 K 停止背景輪詢」)與本次無關,必須搬出保留**;孤兒鍵測試 L594-610 保留;L637「promise chain」無關 |
| `frontend/src/components/index/IndexPage.test.tsx` | describe `"IndexPage subtab 列(SC-2 / SC-3 / SC-5)"` L318-464(s1/s2/s2b/s2c/s3/s4/s5/s5b/s6/s7);fixture `SECTOR_STATE` L102-110;`stubFetch` sector 路由 L124-127 | — | 局部改寫(非純刪) | s1 斷言 4 顆 tab 文案;s2c/s3/s5b/s7 用 sector/timeline 當切換中繼站 → 收成 2 tab 後要重接路徑並保留測試意圖(tab 數 / fallback / getItem 拋不白屏 / 切走 unmount) |
| `frontend/src/lib/signal-model.test.ts` | `kindLabel` market 案 L66-73;`describe("isMarketKind")` L88-106 | — | 保留(隨 §疑點 3 拍板) | |
| `frontend/src/hooks/useSignalFeed.test.tsx` | describe `"useSignalFeed — market 分流(SC-8)"` L144-226:exclude 案 L145-162 **留**;include 案 L164-181 隨 include 半邊刪;L183-226 混合(兩 query key 互不干擾)需拆改 | — | 局部刪/改 | 隨 useSignalFeed.ts 決定 |
| `frontend/src/hooks/useSignalAlerts.test.tsx` | it「market 事件全免疫」L204-220 | — | 保留 | |
| `frontend/src/components/stock/StockPage.test.tsx` | it「同一條 bus 上的 market 事件不進 rail」L536-546;註解 L534-535 提「綜合 tab 的時間軸」 | — | 保留(註解改字) | 這支測試守的是 rail 濾網,刪 timeline 後仍應綠 |

### 2b. 後端

| 檔案 | 要動的符號/區段(現行行號) | caller 清單(檔:行) | 動作 | 備註 |
|---|---|---|---|---|
| `copycat/server/app.py` | `GET /api/market/sector` L1428-1446 | `sector-model.ts` | 整段刪 | 原調研未給行號 |
| `copycat/server/app.py` | `GET /api/market/sector/members` L1448-1468 | 同上 | 整段刪 | |
| `copycat/server/app.py` | `_MARKET_KIND_PREFIX` L109-112;`_is_market_kind` L115-117;`stock_signals_today` 的 `market` 參數 L1083 + docstring L1088-1091 + 過濾 L1094-1095 | 前端 `useSignalFeed.ts:32`(`?market=exclude`) | **保留 / 局部**(見疑點 2) | route 本身 = 自選 rail 端點,不可刪。`market` 參數去留待拍板:前端 exclude 模式**目前仍送** `?market=exclude`;jsonl 歷史檔可能殘留 market 列 |
| `copycat/server/app.py` | `ChainFetch` import L30;`BreadthFetchers` 五元組 L165-176(docstring L167-169 提第五槽);`_make_breadth` 真五元組 L721-727(`fetch_industry_chain` L726)、長度檢查 L733-743(「預期 5」訊息 L741 / `raise ValueError("...五元組")` L743)、拆包 L745-751、建構 `chain_fetch=chain_fetch` L763 | `verify.py::fake_breadth_fetchers`;`tests/server/test_breadth_routes.py::TestFetchersArity/TestProdWiring`;`.claude/**/sidecar_server.py`(歷史側車樣板,不改) | 局部改(5→4 元組) | 原調研「fetchers 第 5 槽」正確 |
| `copycat/server/app.py` | `breadth.attach_signal_hub(signals)` L781-782 + 註解 L776-780;`booted.breadth.detach_signal_hub()` L825 + 註解 L814-819、L822-824 | `BreadthEngine.attach/detach_signal_hub` | 整段刪 | **勿混淆** `stock.attach_signal_hub(hub)` L567-568 / `stock.detach_signal_hub()` L577-578 — 那是 `StockEngine` 的個股訊號掛點,保留 |
| `copycat/server/breadth_engine.py` | 模組 docstring 「產業鏈」段 L19-24、「全市場鎖板事件」段 L26-31 | — | docstring 改寫 | 「連板數」段 L33-37 留 |
| `copycat/server/breadth_engine.py` | import `dedup_sector_map`… 中的 `normalize_universe_rows` L64;`from copycat.sector_rotation import …` L67-72;`CHAIN_MIN_ROWS` L73;`from copycat.server.chain_store import …` L74 | — | 局部刪 | `BreadthFetchError`(L73)留 |
| `copycat/server/breadth_engine.py` | `_CHAIN_FILE` L129-131;`_MARKET_LOCK/_MARKET_OPEN` L133-137;`ChainFetch` L143;`MarketSignalSink` Protocol L146-158 | 本檔 | 整段刪 | |
| `copycat/server/breadth_engine.py` | 建構子 `chain_fetch` 參數 L217 + 賦值/註解 L229-230;chain state L265-277(`_chain_map/_chain_fetched_at/_chain_task/_chain_retry_at/_rotation/_universe_rows`);market 對帳 state L279-290(`_mkt_last_emitted/_mkt_emitted_date/_mkt_cooldown/_mkt_touch/_signal_hub`) | 本檔 | 整組刪 | |
| `copycat/server/breadth_engine.py` | `attach_signal_hub` L318-321 / `detach_signal_hub` L323-325 | `app.py:782,825`;`tests/server/test_breadth_engine.py`(TestMarketLimitEvents)、`test_breadth_routes.py::TestSignalHubWiring` | 整段刪 | |
| `copycat/server/breadth_engine.py` | `start()` 內 `self._restore_chain()` L338 + docstring L330/L333;`close()` 內 `chain` 兩行 L344、L347 | — | 局部刪 | `_restore()`/`_restore_streaks()`/streak 收攤 L343、L346 留 |
| `copycat/server/breadth_engine.py` | `sector_state()` L405-418;`sector_members()` L420-428 | `app.py:1446,1464` | 整段刪 | |
| `copycat/server/breadth_engine.py` | `_poll_loop` 內 `self._maybe_arm_chain()` L462 | — | 整行刪 | `_maybe_arm_streaks()` L461 留 |
| `copycat/server/breadth_engine.py` | `_apply` 內:註解 L652-656 + `self._universe_rows = normalize_universe_rows(universe)` L657 + `self._recompute_rotation()` L658;尾端註解 L670-673 + try/except `_diff_limit_events` L673-677 | — | 局部刪 | `_apply` 其餘(counts/trade_date/rows/append)全留;`return point` L677 邏輯保留 |
| `copycat/server/breadth_engine.py` | `_recompute_rotation()` L679-702 | `_apply:658`、`_refresh_chain:986` | 整段刪 | |
| `copycat/server/breadth_engine.py` | `_diff_limit_events()` L722-811(含小節標題 L722) | `_apply:674` | 整段刪 | `event_cooldown_secs` 讀取 L754 隨之消失 |
| `copycat/server/breadth_engine.py` | 「產業鏈刷新」小節 L846-987:`_chain_path` L848-849 / `_restore_chain` L851-888 / `_maybe_arm_chain` L890-918 / `_refresh_chain` L920-987 | `start:338`、`_poll_loop:462` | 整段刪 | `chain_ttl_hours` 讀取 L906 隨之消失 |
| `copycat/server/breadth_engine.py` | L989 起至檔尾(1358):連板數 `_maybe_arm_streaks` … `_restore_streaks`(L991-1294)、序列落檔 `_series_list/_series_path/_save/_restore`(L1298-1357) | — | **全部保留** | 已讀完全檔確認 L1069-1358 無任何 sector/chain/market 相關碼 |
| `copycat/breadth_fetch.py` | `_CHAIN_DATASET` L36;`CHAIN_MIN_ROWS` L52;`fetch_industry_chain` L113-119 | `app.py:726`;`breadth_engine.py:73,861,945`;`tests/server/test_breadth_fetch.py::TestIndustryChainRowCountLog` L327-350 | 整段刪 | 其餘四支 fetch / `INFO_MIN_ROWS` / `BreadthFetchError` / `_get_rows` 留;test 檔其餘 class(`TestRequestShape` L115-241 / `TestErrorClassification` L242-303 / `TestStockInfoRowCountLog` L304-326)留 |
| `copycat/breadth_config.py` | `event_cooldown_secs` L30;`chain_ttl_hours` L31;`load_breadth_config` 內 `event_cooldown_secs <= 0` 驗證 L47-54 | `breadth_engine.py:754,906` | 局部刪 | 其餘欄位(`poll_secs/window_*/stale_secs/backoff_max_secs/quota_backoff_secs`)留;`configs/breadth.json` 本機**不存在**(§5),刪欄位無啟動風險 |
| `tests/test_breadth_config.py` | `test_default_values` L27-28 兩行斷言;`test_load_override_r4_keys` L61-72;`test_unknown_key_near_r4_keys_raises` L75-80;`test_non_positive_event_cooldown_raises` L83-93 | — | 局部刪 | 其餘 test 留 |
| `copycat/server/signal_hub.py` | `_MARKET_LOCK/_MARKET_OPEN/_MARKET_RULE_TAG` L109-112;`_kind_text` market 分支 L140-143;`self._market_date_warned` L248;小節 L767 + `publish_market_events` L769-821 + `market_event_state` L823-845 | `publish_market_events` / `market_event_state` **唯一** caller = `breadth_engine.py:811 / 743`(全庫確認);`_kind_text` market 分支只被 `test_signal_hub.py::TestMarketKindText` 直呼(生產路徑 `notify=False` 永不到) | 整段刪 | `today_signals` L916-940 的「engine 日別 ∪ 牆鐘日」聯集(R2-3)動機源自廣度事件牆鐘日檔 → 刪後成無害冗餘,**保留**(見疑點 4);`_now_fn` 另被 detector/epoch 用(L277,L298,L981)留 |
| `tests/server/test_signal_hub.py` | `_market_event` helper L331-;`TestMarketEvents` L2040-2155;`TestMarketEventState` L2156-2187;`TestMarketKindText` L2248-2266(檔尾);`TestHistoryAndId::test_truncated_multibyte_tail_keeps_good_rows` L658-690 中 `market_event_state` 斷言 L687-690(其 fixture row kind `market_limit_lock` L671 可改任意 kind) | — | 三 class 整刪 + 一測試局部改 | `TestTodaySignalsUnion` L2188-2246 隨疑點 4 決定(留) |
| `tests/server/test_signal_routes.py` | `_market_event` L108-;`_market_event_id` L121-;`_publish_market` L128-141;`TestSignalsTodayMarketParam` L362-447(5 test);`TestSignalRoutesWithoutStock::test_market_events_reach_today_on_wall_clock_date` L702-726 / `test_ws_stock_stays_open_and_carries_market_events` L727-756;`TestWsStockSharedBroadcaster` 內 L852-857 用 market 事件當載具 | — | class 整刪 / 兩測試**改寫載具**非刪 | **原調研漏列**。L702-756 / L852-857 守的是 XR-3「hub 無 stock 仍活、`/ws/stock` 載 hub 事件」,不能連行為一起刪;要換成規則訊號當載具(hub 無 engine 時如何注入訊號需在 change-spec 設計) |
| `copycat/server/__main__.py` | `from copycat.server.chain_store import CHAIN_FILENAME` L34;`VERIFY_FAIL_DATA_DIR` L56-60;`_clear_chain_cache` L140-152;`main()` L177-179 中 `data_dir = VERIFY_FAIL_DATA_DIR` / `_clear_chain_cache(data_dir)`;註解 L185-189 提 `market_event_state` | — | 局部刪 | `FAIL_ENV_KEY` 判斷式 L177 **保留**(四支取數失效注入仍需);`VERIFY_FAIL_DATA_DIR` 存在理由(L56-59 docstring)僅為 chain 檔跨 run 持久 → 見疑點 5 |
| `tests/server/test_main_wiring.py` | `CHAIN_FILENAME` import L27;`test_verify_fail_injection_uses_isolated_dir_and_clears_chain` L142-170(用 L155/L157);`test_verify_without_fail_env_keeps_default_dir` L171-182 | — | 局部刪/改 | 隨疑點 5 |
| `copycat/server/verify.py` | 小節註解 L119(「五元組」);`_BREADTH_CHAIN` L167-178;`FAIL_ENV_KEY` docstring L180-186 中 chain 前置字句;`FLIP_ENV_KEY` L189-194;`_FLIP_1101` L196-199;`_flip_locked` L221-228;`fake_breadth_fetchers` 簽名 L255-261 / docstring L262-275(第五支段 L274-275)/ `_snapshot` FLIP 分支 L287-289 / `_industry_chain` L329-335 / 回傳 L337 | `__main__.py:183`;`tests/server/test_verify.py` | 局部刪(5→4 元組) | **`_BREADTH_INFO_ROWS` L121-130(含 `industry_category` 欄)是家數帶 fake stock_info,與 `_BREADTH_CHAIN` L171-178 是兩份獨立常數 —— 前者留、後者刪**(第三支 agent 疑點 5 之混淆在此釐清)。FLIP docstring L189-194 明寫「SC-7 廣度事件 → 時間軸唯一取證通道」→ 刪;`_snapshot`/`_snapshot_stamp`/`_now` 留 |
| `tests/server/test_verify.py` | `FLIP_ENV_KEY` import L46;`test_verify_breadth_fail_injects_all_five` L212-231(改四支,不可刪);`test_fake_chain_feeds_the_rotation_pipeline` L232-256(刪);`TestBreadthFlip` L257-322(刪) | — | 局部刪 + 一測試改 | |
| `copycat/sector_rotation.py` | 整檔 L1-200(`ChainMap` L29、`rows_to_chain_map` L32-59、`compute_sector_rotation` L115-150、`compute_sector_members` L153-199) | 僅 `breadth_engine.py:67-72` | 整檔刪 | |
| `tests/test_sector_rotation.py` | 整檔(17 test) | — | 整檔刪 | |
| `copycat/server/chain_store.py` | 整檔 L1-67(`CHAIN_FILENAME` L25、`load_chain` L28-50、`save_chain` L53-66) | `breadth_engine.py:74`;`__main__.py:34`;`test_main_wiring.py:27` | 整檔刪 | |
| `tests/server/test_chain_store.py` | 整檔 L1-149 | — | 整檔刪 | |
| `copycat/market_breadth.py` | `_ROTATION_NUMERIC_FIELDS` L293;`normalize_universe_rows` L296-319(註解 L292-305 提 rotation) | 唯一非測試 caller `breadth_engine.py:657`;`tests/test_market_breadth.py` L25 import + 三個 test(L242-290 區,呼叫於 L246/259/273/279/285/287) | 函式 + 三測試一併刪 | 純 rotation 前處理(清洗數值欄給 `_group_stats` sum),無他人用;`dedup_sector_map` L135-161 / `assemble_universe` L236-257 / `compute_breadth` 等 R2 核心**留** |
| `tests/server/test_breadth_engine.py` | `TestChainCache` L1934-2263;`TestSectorState` L2264-2585;`TestMarketLimitEvents` L2586-2953(檔尾) | — | 三 class 整刪 | 其餘 10 class(L336-1933:NormalCycle/FailureHandling/MapCache/SeriesPersistence/PollLoop/Streak×4/RowsState)留;fixture 若含 `chain_fetch=` 參數需同步拿掉 |
| `tests/server/test_breadth_routes.py` | `_ok_fetchers(*, chain: bool = False)` L125-139;`TestFetchersArity` L371-393(**改寫**:送三元組驗「預期 4 收到 3」,不可刪);`TestProdWiring` L448-516 中 `fetchers[4]` / `_chain_fetch` 斷言(局部);`TestSectorRest` L538-599;`TestSectorMembers` L600-678;`TestSignalHubWiring` L680-735(檔尾;三 test 全測 breadth hub 掛/摘 → 整刪) | — | 兩 class 整刪 + 一 class 整刪 + 兩處改 | `TestBreadthRest` L222-292 / `TestBreadthRowsRest` L293-370 / `TestBreadthWebSocket` L395-447 / `TestFailureIsolation` L517-537 留 |
| `tests/fixtures/record_breadth_parity.py` | 含 `sector` 字樣 | — | **保留** | 是 R2 家數帶 parity oracle 錄製腳本(`dedup_sector_map` 語意),非 rotation;第三支 agent 未展開,主 session 判定無關 |

### 2c. 文件

| 檔案 | 區段(現行行號) | 動作 | 備註 |
|---|---|---|---|
| `CLAUDE.md` | L63-65 breadth_engine 描述中「+ 類股輪動 chain cache + 全市場鎖板事件 kind=market_limit_lock/open,**硬性不進 Discord**」半句;L66 `chain_store、`;L70 `sector_rotation.py` 整行 | 局部刪 | 「FinMind 家數 poller + 連板 EOD task」與 `breadth_fetch`/`finmind_token` 留;§0 第 (b) 條「全市場廣度掃描」敘述仍成立(家數/連板留) |
| `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` | R4 節 L166-192;§7 Open Q5 L217-221(冷卻 600s 拍板) | 加註「R4 已於 2026-08-16 逆轉刪除」或不動 | 歷史計畫文件,非現行契約 |
| `docs/next-time.md` | L189-228(R4 收尾留尾巴整節 8 條);L1087-1134(R4 round-2 rejected 項;**XR-3 L1092-1096 與 FE-7 L1129-1133 例外保留** — 兩者為 hub 共用機制非 sector 專屬) | 整節作廢/加註 | 慣例決策(物理刪 vs 標記),見疑點 8 |
| `.claude/skills/finmind-conventions/SKILL.md` | L23-27 `TaiwanStockIndustryChain` bullet;L28-31 接入樣板措辭 | 刪 bullet;L28-31 改例證 | 同清單 L15-22 三個 dataset(tick_snapshot / TaiwanStockInfo / Disposition)留;§8 L59-77 留 |
| `.claude/skills/e2e-conventions/SKILL.md` | 含 `sector` 字樣(第三支 agent 列出未展開) | 待 change-spec 補讀 | |
| `docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` | L77/L88 預先筆記 | 不動 | 拍板文件本身 |

## 3. 「共用不能刪」清單(白名單功能依賴)

| 符號 | 位置 | 被誰用 | 證據 |
|---|---|---|---|
| `self._sector_map` / `dedup_sector_map` / `primary_sector` | `breadth_engine.py:296,559,611,838`;`market_breadth.py:135-161,236-257` | 家數帶 universe 白名單(排除指數列)、`_stale()` degraded 判定、連板 rows 原料 | `assemble_universe(rows, self._sector_map, self._disposition)` L611 → `compute_breadth` L612;`_stale` L838。**名稱含 sector 但職責是 R2 全市場廣度,與 sector_rotation 是兩條路(spec L168-171 明文)** |
| `_refresh_maps/_refresh_stock_info/_refresh_disposition/_map_due/_map_backoff`、`_type_map/_name_map/_disposition` | `breadth_engine.py:82-90, 502-594` | 家數帶 + 連板 | 同一 TaiwanStockInfo 取數三切面 |
| 連板數全套(`_maybe_arm_streaks` … `_restore_streaks`、`rows_state()`)、`copycat/limit_streaks.py`、`data/market/streaks-*.json` | `breadth_engine.py:362-403, 991-1294` | R3 漲跌停列表 | 與 chain/market 完全獨立 |
| `breadth-*.json` 序列落檔(`_save/_restore/_series_*`) | `breadth_engine.py:1298-1357` | 家數帶/騰落線 | |
| `breadth_fetch.py` 四支 fetch + `INFO_MIN_ROWS` + `BreadthFetchError` | | 家數/連板 | |
| `verify.py`:`FAIL_ENV_KEY`、`_BREADTH_INFO_ROWS`(含 `industry_category`)、`_BREADTH_QUOTES`、`_BREADTH_DAILY`、`_DAILY_PAD_ROWS`、`_snapshot/_stock_info/_disposition/_daily_prices`、`_snapshot_stamp`、`_now`、`neutralize_external_env` | L121-165, 187, 212-218, 231-252, 282-327 | verify 家數/連板取證 | `_snapshot` 是四取數點之一,只拆 FLIP 分支 |
| `StockEngine.attach_signal_hub/detach_signal_hub` | `stock_engine.py:298,301`;`app.py:568,578`;`tests/server/test_stock_engine.py:1532-` | 個股訊號 | 同名不同 class |
| `SignalHub` 本體(規則引擎、jsonl 佇列、Discord 佇列、`today_signals`/`read_signals`、`_now_fn`) | `signal_hub.py` | 個股訊號 rail / Discord | 只摘兩 method + 三常數 + 一欄位 |
| `/api/stock/signals/today` route | `app.py:1082-1096` | 自選 rail baseline | 只動 `market` 分支 |
| 前端 `isMarketKind` / `SignalKind` market 值 / `kindLabel` market 分支 / `useSignalAlerts` 早退 / `useSignalFeed` exclude 全套 | 見 §2a | 自選 rail、toast | 濾網保留(疑點 3) |
| `timeframe.ts::MarketMode` | `frontend/src/lib/timeframe.ts:10` | K 線刻度 | 同名撞名 |
| `ChainAggregator`、balance chain、cancel-chain、promise chain、TXO option chain 全部 | 見 §4 | TXO / 群益 / UI | 語意無關 |

## 4. 全庫 grep 命中歸類表

範圍 `copycat/ frontend/src/ tests/`(`scripts/` 不存在);`.claude/**` 與 `docs/superpowers/**` 大量歷史產物不逐列。

| 關鍵字 | 要刪 | 無關保留(理由) |
|---|---|---|
| `sector` | app.py sector 路由;breadth_engine sector_state/members/_rotation;sector_rotation.py;SectorSection*;sector-model*;IndexPage 局部;test_breadth_routes/engine/verify 對應段;App.test/IndexPage.test 對應段;CLAUDE.md L70 | `market_breadth.py` `dedup_sector_map`/`primary_sector`(R2 白名單);`breadth_engine._sector_map`;`tests/test_market_breadth.py` sector map 測試;`tests/fixtures/record_breadth_parity.py`;`constants.ts:30` 舊孤兒鍵 |
| `chain`(industry) | chain_store.py;breadth_fetch `fetch_industry_chain`/`_CHAIN_DATASET`/`CHAIN_MIN_ROWS`;breadth_engine chain 段;app.py L30/L726/L750/L763;`__main__` L34/L140-152/L179;verify `_BREADTH_CHAIN`/`_industry_chain`;breadth_config `chain_ttl_hours`;test_chain_store;test_main_wiring 局部;test_breadth_routes `_ok_fetchers(chain=)` | **option chain**:`copycat/live/tc4.py:3`、`live/models.py`、`live/aggregate.py::ChainAggregator`、`live/handover.py`、`server/engine.py`、`spikes/txo_chain_probe.py`、`tests/live/*`、`tests/fixtures/txo_golden/regen.py`、`tests/server/test_app.py:140`、`frontend OrderPanel.tsx`(TXO 合約鏈);**balance/cancel chain**:`capital/client.py:92,368,661`、`tests/capital/test_client.py`;**promise chain**:`WatchlistManagerDialog.tsx`、`useServerBuild.test.tsx`、`VersionDriftBadge.test.tsx`、`App.test.tsx:637`;`docs/harness/hooks/format-on-edit.py` |
| `market_limit` | breadth_engine `_MARKET_LOCK/OPEN`、`_diff_limit_events`;signal_hub 三常數 + 兩 method;SignalTimelineSection;test_signal_hub 三 class;test_signal_routes 對應;test_breadth_engine `TestMarketLimitEvents`;CLAUDE.md L65 | 前端 `signal-model.ts:19-20` 型別值(疑點 3);`app.py:109-110` 註解(隨疑點 2) |
| `market_kind` / `_is_market_kind` | — | `app.py:115-117,1095`(疑點 2);`signal-model.ts:28` / `.test.ts:101` 註解引用 |
| `MarketMode` | `useSignalFeed.ts:25` `"include"` 成員(隨疑點 1) | `timeframe.ts:10` 及 `useMarketBars.ts`/`MarketChart.tsx`/`MarketPane.tsx`(K 線刻度) |
| `mergeByFamily` / `FAMILY_CAP` | `useSignalFeed.ts:23,39-50,85,99`(隨疑點 1);`useSignalFeed.test.tsx:164-226` | — |
| `isMarketKind` | `SignalTimelineSection.tsx` 內用法(隨檔) | `signal-model.ts:24-31`;`useSignalFeed.ts:15,45,83`;`useSignalAlerts.ts:10,89`;`signal-model.test.ts:88-106` |
| `timeline` | SignalTimelineSection*;IndexPage L22/L42/L226;IndexPage.test/App.test 對應;`constants.ts:76` 註解 | `constants.ts:21,31` 舊孤兒鍵;`useSignalAlerts.ts:88`/`StockPage.test.tsx:534` 註解(改字);後端零命中 |
| `rotation` | app.py L168/L1432-1444;breadth_engine `_rotation`/`_recompute_rotation`;sector_rotation.py;`market_breadth.py:292-319`(隨 normalize 刪);`App.test.tsx:63` 註解;test_sector_rotation | — |
| `industry` / `IndustryChain` | app.py L1449-1464 參數;breadth_fetch/verify/__main__ 的 industry_chain;finmind skill L23-27 | `market_breadth.py:30-31,141-159` `industry_category`(TaiwanStockInfo 欄名,R2);`verify.py:123-129` `industry_category`(fake stock_info) |
| `publish_market_events` / `market_event_state` | signal_hub L769-845;breadth_engine L154-158,743,811;test_signal_hub/test_signal_routes 對應;`__main__.py:187` 註解 | — |
| `attach_signal_hub` / `detach_signal_hub` | `breadth_engine.py:320-325`;`app.py:782,825`;test_breadth_engine `TestMarketLimitEvents`;test_breadth_routes `TestSignalHubWiring` | `stock_engine.py:298,301`;`app.py:568,578`;`tests/server/test_stock_engine.py`;`tests/server/test_signal_routes.py::TestSignalsShutdownIsolation`(stock 掛點) |
| `VERIFY_FAIL_DATA_DIR` | `__main__.py:56-60,178`(疑點 5) | `verify.py:185` 註解;`test_main_wiring.py:157` |
| `FLIP_ENV_KEY` / `_flip_locked` / `_FLIP_1101` | `verify.py:189-199,221-228,287-289`;`test_verify.py:46,257-322` | — |
| `normalize_universe_rows` | `market_breadth.py:293-319`;`breadth_engine.py:64,657`;`tests/test_market_breadth.py:25,242-290` | — |
| `CHAIN_FILENAME` | `chain_store.py:25`;`breadth_engine.py:74,131`;`__main__.py:34,146,152`;`test_main_wiring.py:27,155` | — |
| `chain_ttl_hours` / `event_cooldown_secs` | `breadth_config.py:30-31,47-54`;`breadth_engine.py:754,906`;`tests/test_breadth_config.py:27-28,61-93`;`verify.py:192` 註解 | — |

## 5. 磁碟與 config 現況

- `data/market/`:`industry_chain.json`(769,547 bytes,08-11)**存在** — 唯一 chain 落檔,單一固定檔名(git-ignored,runtime 產物;刪碼後成孤兒檔,清理屬 ops 動作非 PR)。同目錄 `breadth-2026-08-11..14.json`(家數序列)與 `streaks-2026-08-11..15.json`(連板)**保留**。
- `data/market-verify/` / `data/market-verify-fail/`:未逐一列(verify 產物,同理可能殘 `industry_chain.json`)。
- `configs/breadth.json`:**不存在**(configs/ 只有 correlation.json、fade_uc_round*.json、strategy-v1.json)→ 現行全走 `BreadthConfig` 預設(`event_cooldown_secs=600.0` L30、`chain_ttl_hours=168.0` L31);刪欄位無「未知鍵 raise」啟動風險。
- prod server 若在跑,`data/signals/YYYYMMDD.jsonl` 內可能已含 `market_limit_*` 歷史列(疑點 2/3 的資料相容性前提)。

## 6. 疑點清單

1. **`useSignalFeed.ts` include 半邊(`MarketMode."include"`/`mergeByFamily`/`FAMILY_CAP`/`opts.market`)**:刪 timeline 後 100% 死碼,但屬同檔局部重構;鐵則 B 三類分離 → 建議本輪以 🔵 獨立 commit 一併收,或寫進 next-time。需拍板。
2. **`/api/stock/signals/today` 的 `market` query 參數與 `_is_market_kind`**:後端事件源刪除後,exclude 過濾只對「歷史 jsonl 殘留列」有意義。三選一:(a) 保留參數+過濾(零行為變更,前端 exclude 繼續送);(b) 拔參數,前端 `fetchToday` 改打裸 URL(歷史殘留列會重新出現在 rail,直到當日檔翻頁);(c) 保留至次一交易日後再拔。建議 (a) 本輪不動、列 next-time。
3. **前端 `SignalKind` market 值 / `isMarketKind` / `kindLabel` market 分支 / `useSignalAlerts` 早退**:與疑點 2 同一組相容性決策;若 (a) 則全部保留只改註解;若拔則六個測試檔連動。
4. **`SignalHub.today_signals` 的「engine 日別 ∪ 牆鐘日」聯集(R2-3,L916-940)+ `TestTodaySignalsUnion`**:動機為廣度事件牆鐘日檔;刪後成無害冗餘。建議保留(改屬 refactor 範疇)。
5. **`VERIFY_FAIL_DATA_DIR`(`__main__.py:56-60`)**:後端 agent 判「刪」、第三支 agent 判「留」。主 session 讀 docstring 確認其**唯一存在理由**是 chain 檔跨 run 持久 → chain 刪後 `VERIFY_DATA_DIR` 即可;但拆掉會連動 `test_main_wiring.py` 兩測試(L142-182)。建議刪(含 `_clear_chain_cache`),`FAIL_ENV_KEY` 判斷式本身保留(四取數注入)。
6. **`tests/server/test_signal_routes.py` L702-756 / L852-857**:以 market 事件為載具驗 XR-3(hub 無 stock 仍活、`/ws/stock` 載 hub 事件、app-level broadcaster)。刪 `publish_market_events` 後需**改用其他方式**把訊號灌進無 engine 的 hub(hub 公開面只剩 `on_tick`/規則路徑,而無 engine 時 membership/basis 由誰餵?)—— change-spec 必須設計替代載具,否則 XR-3 行為失去測試保護。**原調研漏列,風險最高的一項。**
7. **`TestFetchersArity` / `test_verify_breadth_fail_injects_all_five` / `TestProdWiring`**:五→四元組後需改寫而非刪(arity 防呆與失效注入回歸是白名單);`app.py:741` 訊息文字同步改「預期 4」。
8. **文件慣例**:`docs/next-time.md` 兩節(L189-228、L1087-1134 扣除 XR-3/FE-7)是「物理刪」還是「加註作廢」;spec R4 節是否加逆轉註記。
9. **`.claude/skills/e2e-conventions/SKILL.md`** 含 `sector` 命中,未展開;change-spec 補讀。
10. **原調研提到「`__main__.py` VERIFY_FAIL_DATA_DIR + `_clear_chain_cache` 呼叫」** 與現況一致;「app.py `_MARKET_KIND_PREFIX` 刪」與現況一致但因疑點 2 改為待拍板 —— 這是調研與現況唯一的判定分歧。
