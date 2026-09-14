# 專案瘦身盤點:死碼 / 遺留碼 / 冗餘候選清單(唯讀,未刪任何東西)

2026-09-14。目的是給 user 逐區拍板「刪哪些」,之後由 `/refactor 專案瘦身` 分批純 🔵 刪除。
本檔只列證據與候選,**不含任何刪除決定**。

## 0. 一句話結論

**函式層級的死碡非常少;專案「大」的原因不在死碡,在三個地方:研究區(fade 回測家族 7,259 行 + 5,085 行測試)、
版控裡的流程 artifacts 與截圖(`.claude/` 52 MB、`docs/specs` 11 MB),以及本機未版控的 `spikes/`(45 MB)。**
後端測試覆蓋率 90%,零覆蓋模組只有 `__main__.py`。前端 knip 零未使用檔案。

## 1. 方法與工具(全部拋棄式,不碰專案 .venv / package.json)

| 工具 | 對象 | 結果 | 可信度 |
|---|---|---|---|
| vulture 60% / 90% | `copycat/` | 159 / 3 條候選 | 中;逐條 `git grep -w` 全 repo 交叉後,真候選 **4 條**(見 §3A) |
| knip(預設) | `frontend/` | 0 未使用檔案、33 未使用 export、33 未使用 type、12 default/named 重複匿出、1 unlisted dep | 高 |
| coverage(pytest 全量 3,566 條) | `copycat/` | TOTAL 90%(18,651 stmts / 1,871 miss) | 高 |
| graphify 零入邊 | 全 repo | 1,300 callable / 227 檔 | **低,不可用**:TS import 邊抓不到(`types.ts` 38/38「零入邊」)、FastAPI route 與 bot command 靠裝飾器 |
| git 最後改動日 | 491 檔 | 115 檔非測試自 2026-08-01 起未動 | 高(是事實,不是判定) |
| 遺留字樣 grep | 退役 / 舊版 / legacy / compat | 約 40 處 | 需人判(多為刻意保留的相容分支) |

**掃描報告的死碡點名要重驗**:F3-08 說 `energyFrom` 零讀者,實際 `stock-intraday-svg.ts:340/418` 兩個 caller(可能已修)。
D2 F-01「回報斷線偵測是死碡」是 bug 不是死碡,已排批 A(dispid 9/10)。B11 F-19 屬實(§3A)。

## 2. 規模

| 區 | 行數(非測試) | 版控大小 |
|---|---|---|
| `copycat/server` | 13,742 | |
| `copycat/backtest` | 8,907(fade 家族 7,259) | |
| `copycat/live` | 5,804 | |
| `copycat/capital` | 3,645 | |
| `copycat/data` + `replay` + `engine` | 2,527 | |
| copycat 全部 | 37,929 | 1.8 MB |
| `frontend/src` 全部 | 27,539(components 14,170 / lib 8,410 / hooks 3,984) | 3.5 MB |
| `tests/` | 61,320 | 4.3 MB |
| frontend `*.test.*` | 47,778 | (含在 frontend/src) |
| `.claude/{mod,feat,bug,refactor}` artifacts | — | **52 MB / 1,434 檔**(截圖 222 張 21 MB) |
| `docs/specs` | — | 10.9 MB(截圖 50 張 7.1 MB) |
| `graphify-out` | — | 14.8 MB(09-14 剛進) |
| 版控總計 | — | 95.8 MB / 2,618 檔 |
| 本機未版控 `spikes/` | — | 45 MB(TCPY 40 MB 含 PDF;只 11 支 probe 腳本被追蹤) |

前端 runtime 依賴只有 5 個(react / react-dom / @tanstack/react-query / clsx / tailwind-merge),無依賴瘦身空間。
後端 runtime `dependencies = []`。

## 3. 候選清單(分桶)

### A. 確定死碡,刪了零行為改動(小)

| # | 位置 | 說明 | 行數 |
|---|---|---|---|
| A1 | `copycat/backtest/market_features.py::compute_mkt_daily_features` | 全 repo 零 caller(只剩 `_full` 版被用) | 28 |
| A2 | `copycat/backtest/fade_pipeline.py:435-457,669-685` `mkt_daily_rows` | 恆為 None → 7 欄大盤特徵永不計算(B11 F-19 實證) | ~20 |
| A3 | `copycat/live/aggregate.py:134 last_cum` | 方法零 caller(含 tests) | 2 |
| A4 | `copycat/engine/lock_quality.py:103 current_lock_start` | 方法零 caller(含 tests) | 2 |
| A5 | 前端 33 個未使用 `export`(knip) | 只需拿掉 `export` 字,符號本身仍在用;含 `ladder-position.ts` FEE_BASE/SELL_TAX 等常數、`useFuturesBars` 兩 timeout 常數、`fee-discount.loadDiscount` 等 | 0(改關鍵字) |
| A6 | 前端 33 個未使用 `type` export | 同上;含 `types.ts` 4 個、`candle.ts` 3 個 | 0 |
| A7 | 12 個元件同時 named + default export(FuturesChart / CorrPanel / RiverPanel / MarketPane …) | 二擇一 | 12 行 |
| A8 | `frontend/eslint.config.js` 用到 `@eslint/js` 但未列 devDependencies(knip unlisted) | 是缺列不是多餘;補列或改 import | — |

**vulture 假陽性,刻意不列**:`com.py` 的 COM 結構欄位與 callback 參數名(comtypes 動態)、`_dll_cookie`(註解寫明防 GC)、
`discord_bot._hub`(註解寫明成對收攤)、`strategy_config.adv_window`(註解寫明文件化)、`LockQualitySignals` 欄位(經 `asdict`
進 replay 輸出 → golden validate 讀得到,**動它會紅 gate**)、所有 `@app.*` / `@router.*` / bot command。

### B. 研究區遺留(產品決策,不是技術判定)

| # | 區 | 規模 | 最後改動 / 最後產出 | 現況 |
|---|---|---|---|---|
| B1 | **fade 回測家族** `backtest/fade_*.py` + `quantiles.py` + `report_fmt.py` + `market_features.py` | 7,259 行 + 27 測試檔 5,085 行 + 6 份 `configs/fade_uc_round*.json` + 5 個 CLI 子指令(fade-diagnose / cells / anatomy / entry-anatomy / search) | code 2026-07-20;最後報告 `docs/evidence/fade_round5_entry_anatomy_2026-07-17.md` | memory:「fade/UC 回測五輪已了結」。覆蓋率 49–89%(全 repo 最低的一群)。結論 SoT 在 `docs/strategy-decisions.md` + `docs/evidence/`,刪 code 不刪結論 |
| B2 | T 日跟多回測 `backtest/{config,universe,features,simulate,search,stats,pipeline,report}.py` | 1,647 行 + CLI tday-features / tday-search | 2026-07-20 | 08-28 triage 已排除 tday-join;第四輪 2-5 ProcessPool 是針對它。要留就留整套 |
| B3 | 分點指紋 replay 鏈 `replay/` + `engine/` + `data/import_neigui.py` | ~1,100 行 | 2026-07-20 | **`copycat validate` 是完工 gate 的一部分 → 留**。但 `import-neigui` 是一次性匯入,可討論 |
| B4 | events 研究鏈 `data/{scan_events,label_events,backfill_brokers,backfill_daytrade}.py` + CLI | ~700 行 | 2026-07-20 | 覆蓋 76–84%;是 B1/B2 的資料前置 |
| B5 | `spikes/` 11 支 probe(版控)+ TCPY vendored(未版控 40 MB) | 4 支零引用(index_tree_probe / river_1k_probe / backfill_phaseb_1k / capital_*) | 07-15 ~ 08-30 | `tcoreapi_mq.py` 是 live 用元件(CLAUDE.md §0a),不可動;其餘 probe 是一次性 |
| B6 | TXO 看盤舊元件 `PnlChart / SeriesSelect / QuoteTable / MetricsBar / tquote.ts / pnl-svg.tsx` | ~1,000 行 | 2026-07-18~20 | knip 說**仍被 import**(TXO tab 還在)。不是死碡,是低活動區 |

B1 若刪:`cli.py` 減 5 個子指令、`tests/backtest` 減 27 檔、`configs` 減 6 份、pyproject 不變。git 歷史與 docs/evidence 保留結論。
替代方案:整包搬 `archive/` 不進 pytest testpaths(留可跑性、失去 gate 保護)。

### C. 版控體積(不是 code,但是「專案大小」的大頭)

| # | 項 | 大小 | 選項 |
|---|---|---|---|
| C1 | `.claude/{mod,feat,bug,refactor}` 流程 artifacts | 52 MB / 1,434 檔,截圖 222 張 21 MB | (a) 維持(可追溯)(b) 截圖轉 git LFS(c) 已結案 topic 的 evidence 截圖降解析度(d) 搬出 repo 到 Documents |
| C2 | `docs/specs` 截圖 | 50 張 7.1 MB | 同上 |
| C3 | `graphify-out` | 14.8 MB | 已進版控;每次重建 graph 都會再長一版 → 建議只在需要時重建、或改 gitignore 只留 GRAPH_REPORT.md |
| C4 | 本機 `spikes/TCPY` 40 MB | 未版控 | 不影響 repo;PDF 三份是官方文件,留 |

### D. 遺留相容分支(**不是死碡**,是「舊資料還在就不能刪」)

| # | 位置 | 相容的是什麼 | 何時可刪 |
|---|---|---|---|
| D1 | `signal_rules.py` v1→v2→v3 migration 鏈 + `signal_hub._legacy_flags`(`signals_enabled.json` 唯讀) | prod `data/signal_rules.json` 舊版 | 確認 prod 檔已是 v3 且 `signals_enabled.json` 可退役後 |
| D2 | `stock_watchlist.py` v1(只有 codes)讀時遷移 | 舊自選檔 | prod 已 v2;backup 檔也 v2 → 可刪,但要留一條「v1 直接拒收」的錯誤 |
| D3 | `App.tsx:110 LEGACY_MAIN_CODE_KEY` localStorage 遷移 | 使用者瀏覽器舊 key | 只有 user 一台機器;確認 localStorage 已無舊 key 即可刪 |
| D4 | `MarketPane.tsx:344` 舊值 "overlay"/"side" 讀時遷移 | 同上 | 同上 |
| D5 | `app.py:1550`、`capital_api.py:267`、`SignalRail.tsx:54`、`StockIntradayChart.tsx:1223` 「舊前端 / 舊後端」缺欄 default | 前後端版本落差 | **留**:部署一律同版但 VersionDriftBadge 存在的理由就是它會發生 |

### E. 大檔(冗餘合併的候選母體,需 codebase-design,不在瘦身批)

`app.py` 2,133 / `fade_cells.py` 2,007 / `stock_engine.py` 1,832 / `signal_hub.py` 1,767 / `StockIntradayChart.tsx` 1,724 / `tc4.py` 1,317。
其中 `app.py` 有 44/96 callable 是 route(routing 抽 router 是 /refactor 題,不是刪碡)。

## 4. 覆蓋率(後端)

TOTAL 90%。最低 25 個模組裡 **13 個是 fade 家族、5 個是 data backfill、1 個 cli**。live / server 核心全在 89% 以上。
零覆蓋只有 `__main__.py`(3 stmts)。前端覆蓋率未跑(`@vitest/coverage-v8` 未裝,不順手裝)。

## 5. 建議的刪除批順序(等拍板)

1. **A 桶**一批(A1–A8):純 🔵,全量 gate,不需重啟(除 A3/A4 在 live/engine,重啟時順帶)。
2. **B1 fade** 若拍板刪:獨立一批,同時刪 tests/backtest 對應 27 檔 + configs 6 份 + cli 5 子指令 + `docs/superpowers` 內 fade plan 不動。
   gate = pytest / ruff / pyright / `copycat validate`(validate 不吃 fade)。
3. **D1–D4** 各自確認 prod 資料版本後刪,每條一 commit,錯刪的症狀是啟動時舊檔讀不進 → 要先備份 `data/*.json`。
4. **C 桶**是 git 操作(LFS / 搬移),不進 /refactor,單獨決定。
5. **B2/B4/B6** 建議先不動:B2 是第四輪 2-5 的標的、B4 是 B1/B2 前置、B6 仍在用。

## 6. 本輪沒做

- 前端覆蓋率、knip 進階 include(classMembers 等,指令參數錯一次未重試)。
- docs 內容冗餘(`docs/next-time.md` 132 KB、superpowers plans 與 specs 的重複)未盤,屬文件整理不屬 code。
- 沒有逐檔讀 fade 家族確認「結論是否全部落地 docs/evidence」;刪之前要做這一步。

原始輸出:`%LOCALAPPDATA%\Temp\claude\C--side-project-copycat\38ca5162-…\scratchpad\inventory\`
(`vulture_60.txt` / `vulture_xcheck.tsv` / `knip.json` / `coverage_report.txt` / `last_touch.tsv` / `graph_orphans.json`)。
