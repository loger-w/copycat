# Progress ledger:stock-signals

Plan:`.claude/feat/stock-signals/implementation/PLAN.md`(對應 design.md v3)

## Task 分組(依賴序,一次一個 implementer)

- T1:PLAN §1+§2 — market.tick_size_milli + signals_config.py
- T2:PLAN §3 — live/signal_state.py(SignalDetector)
- T3:PLAN §4 — server/signal_hub.py
- T4:PLAN §5+§6 — stock_watchlist.normalize + watchlist_service.py
- T5:PLAN §7 — discord_bot.py + conftest 中和 + pyproject extras
- T6:PLAN §8 — stock_engine.py 掛點
- T7:PLAN §9 — app.py lifespan + routes
- T8:PLAN §10+§11+§12 — signal-model / signal-bus / useStockStream
- T9:PLAN §13+§14+§15 — useSignalFeed / useSignalsConfig / useSignalAlerts
- T10:PLAN §16+§17 — ToastStack / SignalRail
- T11:PLAN §18+§19 — StockPage / App 整合

## 完成記錄

(每 task 追加:編號 / commit 範圍 / review 結果 / fix rounds)

- T1 ✅ 3fcffb9(red)→ c601ac2(green)。gate 1505 passed / ruff 0 / pyright 0。
  review:tag 正確、import 實測 OK;偏離 1 項(config 檔缺 → 全預設,corr_config
  同語意;壞檔仍 raise)accepted。fix rounds 0。
- T2 ✅ 7dff57e(red)→ f6885d0(green)。gate 1546 passed(41 新)/ ruff 0 /
  pyright 0(IDE 診斷 stale,scoped pyright 實測 0)。deviation 9 項:#1 reset_day
  先於 swap(已固化 design §4.1)、#3~#9 accepted;**#2 lock/open 共用冷卻桶
  rejected → T2-fix 分桶(design §3.5 amendment)**。fix rounds 1。
- T2-fix ✅ be97087(red)→ b9cd2a7(green)。gate 1547 passed / ruff 0 / pyright 0
  (scoped 實測;IDE stale)。改 5 條既有斷言全屬「該變」(advance(700) 是繞共用桶
  的痕跡)。
- T3 ✅ 3cc3a9a(red)→ a21b226(green)。gate 1567 passed(20 新)/ ruff 0 /
  pyright 0(scoped 實測;IDE stale)。mutation 反驗 2 次非 vacuous。deviation 7 項
  全 accepted;**T7 注意:route 用 `hub.today_signals()`;bot sender 同步/async 皆可**。
  fix rounds 0。
- T4 ✅ e765c64(🔵 normalize)→ 801656f(red)→ 7a3cedb(green)。gate 1586 passed
  (19 新)/ ruff 0 / pyright 0(scoped;IDE stale)。deviation 2 項 accepted
  (normalize 直測入 refactor commit 免假紅;壞現況檔 → canonical None 走覆寫 + log)。
  add 對「已在 codes 未在指定群組」= 變更,已測。fix rounds 0。
- T5 ✅ c59185f(red)→ a4ae83a(green)。gate 1617 passed 1 skipped / ruff 0 /
  pyright 0(scoped;IDE stale)。test_discord_bot 28 passed 非 vacuous。deviation
  3 項 accepted(service.current() 唯讀 accessor + 3 測;importlib lazy import 仿
  capital/com.py;handler except 邊界有具體處理)。**T7 注意:attach_discord 由
  app.py 負責;bot.hub 參數目前僅存**。fix rounds 0。
- T6 ✅ bbec8c4(red)→ 09636bf(green)。gate 1623 passed 1 skipped / ruff 0 /
  pyright 0(scoped;IDE stale)。deviation 5 項全 accepted(SignalSink Protocol、
  list(codes) 複製、trade_date property、試撮測試用 PreciseTime 時窗非 TradeStatus
  — 防 vacuous、on_tick 掛 _dirty 之後)。fix rounds 0。
- T7 ✅ 245edb7(red)→ 2a6a371(green)。gate 1638 passed 1 skipped / ruff 0 /
  pyright 0(scoped;IDE stale)。deviation 6 項全 accepted(create_bot 同步、
  data_dir=wl_path.parent、enabled body 不讓 pydantic 寬鬆轉型、_watchlist_service
  顯式閘、save_watchlist import 移除、雙重 close 已核對)。後端 T1–T7 完成。
  fix rounds 0。
- (註:`.claude/bug/asyncio-socket-send-warning/` 為平行 session 產物,本輪不碰。)
- T8 ✅ e29c6ad(red)→ f555752(green)。frontend gate 949 案全綠(39 新)/ tsc 0 /
  eslint 0。deviation 6 項全 accepted(kindLabel 吃整個 SignalMsg、前後端文案刻意
  不同源、mergeSignals 不排序 — **T9 要負責把 today 的 jsonl 舊在前反轉**、未知 kind
  fail-open、既有 stream 測試補 provider wrapper = test-infra、signal case 不過濾
  code)。fix rounds 0。
- T9 ✅ 46737f5(red)→ eaf1ebb(green)。frontend gate 969 案全綠(20 新)/ tsc 0 /
  eslint 0。deviation 6 項 accepted;**#1 green commit 改一條紅斷言(同 id 重發
  上浮 — spec 未定序,補定契約 + 加強斷言,body 有記)→ Phase 4 自評注意**;
  #3 save 送 partial patch;#5 toast key=id#seq。fix rounds 0。
- T10 ✅ 5682dfb(red)→ c35501d(green)。frontend gate 983 案全綠(14 新)/ tsc 0 /
  eslint 0。deviation 3 項 accepted(無 emoji 依鐵則、方向著色 +測試、toneOf 全
  kind 覆蓋)。顯示端二次 filterKinds(關開關舊列也隱藏)。fix rounds 0。
- T11 ✅ d3eddac(red)→ f5d451f(green)。frontend gate 991 案全綠 / tsc 0 /
  eslint 0。音效落點 = useSignalSound 輕 hook(useSyncExternalStore 跨樹同步,
  mutation check 實證非 vacuous);既有斷言零改動。fix rounds 0。
- **Phase 3 完成**:11 task + 1 fix,後端 1638 passed 1 skipped、前端 991 passed。
- **Phase 4 完成**:3 lens finder(opus)→ 0 P0 / 7 P1 / 13 P2(去重後)。
  後端修復批 11 commits(3d78d4f..268d2b3,mutation 驗證 7 輪)、前端修復批
  4 commits(994f542..7021055,mutation 驗證 2 輪)、doc 2 條(MFS-4/MFS-7)+
  design §4.3 雙佇列 amendment。全 finding 處置:18 fixed / 1 documented /
  1 doc-amendment。self_review_head = 7021055。後端 1657 passed、前端 994 passed。
