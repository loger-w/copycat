# progress ledger — mod/trading-calendar

對應 spec:`.claude/mod/trading-calendar/change-spec.md`(現況 `current-state.md`)。

| # | 內容 | commit 範圍 | review |
|---|---|---|---|
| 0 | baseline pytest 2563 passed;branch 開好;spec + current-state 落檔 | — | spec review round 1:P0×2/P1×7/P2×3 全 accepted → amendments R1-R12;round 2 限縮輪 dispatched |
| 1 | Pkg1 🟢 trading_calendar.py + configs/trading_holidays.json + tests(31) | 983b058(red) → a2937dd(green) | gate 綠(pytest 全套 2594、ruff、pyright 0);tag 核對 OK |
| — | spec review round 2(限縮):P1×3/P2×6 全 accepted → amendments R2-1..R2-9;無 P0 → 退出 | — | JSON round-2 落檔 |
| 2a | 🔴 三引擎 is_trading_day 注入(stock now_fn/_checkpoint_secs;index rollover gate;breadth _in_window 雙呼叫端 + rows_state docstring)+ 測試 | 5105feb→7992e57(stock)/ d2cfeca→6a300d9(index)/ 9b5027f→b44012d(breadth) | tests/server 1079 passed、ruff、pyright 0;tag 核對 OK;偏差 6 條(測試 fixture 選擇,合理) |
| 2b | 🔴 app.py 佈線(create_app trading_calendar / _today / _resolve_trade_date / overlay 基準日 / DK crosscheck 背景 task / GET /api/calendar)+ __main__ prod + test_calendar_wiring(16)+ 🔵 docs | 12d1aa5→7805e07(app)/ d8320be→8c1d9c8(main)/ 7d519b6(docs) | tests/server+calendar 1126 passed、ruff、pyright 0;偏差 3(crosscheck task 掛 app.state 供測試等待;breadth today_fn 恆傳 _today 閉包;create_app 加 docstring) |
| 3 | 前端:🟢 trading-calendar.ts + useTradingCalendar(App 掛)+ types;🔴 trading-hours 三支吃日曆(AllDay 前一日分支);🔴 LimitList 日期膠囊 + 空態文案 | 0ff4f20→cc5164c / 57ca500→9d24fd0 / 2f18b1e→fd2941b | vitest 1871 passed、tsc、eslint、react-doctor 0 新增 |
| 波尾 | 後端全套 gate:pytest 2620 passed + 1 flake(test_ws_disconnect recv timeout,已知、與本輪無關)、ruff、pyright 0、replay×2 + validate 42/42 | — | 進 §5 自評 |
| fix | code review round 1 fix 波(C1/S1 P1 + 10 P2;mutation-verified ×5) | b09bdbc..5147f86(11 commits) | pytest 2627、ruff、pyright 0、vitest 1872、tsc/eslint 綠;self_review_head=5147f864 |
| 收尾 | run.ps1 註解同步(c1353f15);verification.md + evidence 3 截圖;check_feat_tags PASS(31 commits);增量 review round-2 = 純註解 0 finding | c1353f15 | 進 branch-lifecycle 收尾 |
