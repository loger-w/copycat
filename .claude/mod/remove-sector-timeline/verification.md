# verification — mod/remove-sector-timeline

日期 2026-08-16(週日,非交易日;無 TC4 / ZMQ 相依,全部走 `--verify` fake source)。
spec:`change-spec.md`;review:`change-spec-review-round-{1,2}.json`、`code-review-round-1.json`。

## A. 自動化 gate(SC-9)— 波尾全套,主 session 親跑(`evidence/gate-full.txt`;fix 波後重跑見 §F)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | **2561 passed**(baseline 2680;−119 = 刪除的 sector/chain/market/FLIP 測試) | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed(F401/F811 淨) | 0 |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| `npm test`(vitest) | **112 files / 1830 passed**(baseline 115 / 1898;−3 檔 −68 支) | 0 |
| `npx tsc -b` | 無輸出 | 0 |
| `npx eslint src` | 無輸出 | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 13 files / No issues found(零新增) | 0 |
| `git status --porcelain frontend/vite.config.ts`(R2-3 還原檢查) | 空(取證期間臨時改 8722 已 `git checkout` 還原) | — |

## B. 真實環境(SC-1 / SC-3 / SC-7 / SC-8)

取證通道:`TXO_SERVER_PORT=8722 python -m copycat.server --verify`(health `git_sha=8948dc67`)+ vite dev
(port 5199,proxy 臨時指 8722)+ claude-in-chrome 截圖;**未抄舊側車樣板**(spec R7)。

- **SC-3**(`evidence/SC-3-SC-7-curl.txt`):`/api/market/sector` → **404**、`/api/market/sector/members?...` → **404**;
  `/api/market/breadth` 200(counts/series 正常)、`/api/market/breadth/rows` 200(rows + streaks_ready)、
  `/api/stock/signals/today` 200 `{"signals":[]}`、**`?market=exclude` 200 同結果**(舊 bundle 不炸)、
  `/api/stock/signals/rules` 200。
- **SC-1**(`evidence/SC-1-SC-7-subtabs-limit.jpg`):先 `localStorage["copycat-index-subtab"]="sector"` 再載頁 →
  subtab 列只剩「漲跌停」「相關係數」兩顆,active = 漲跌停(殘值走白名單 fallback);點「相關係數」後
  localStorage 變 `corr`(`evidence/SC-7-corr-subtab.jpg`,CorrSection 掛載、顯示等待六腿資料 — verify 無
  futures fake,與改動無關)。孤兒鍵 `copycat-sector-open` / `copycat-signal-timeline-open` 均 null。
- **SC-7 白名單畫面**:家數帶(上市/上櫃 五桶,漲停紅底 / 跌停綠底,上漲紅字 / 下跌綠字)、騰落線(+1 紅點)、
  漲跌停列表(1101 台泥 11+ 板 漲停 / 6488 跌停 / 3105 觸及未鎖)全部正常渲染 — 見 SC-1 截圖。
  加權 / 櫃買圖「等待指數資料」= verify 模式無 index source 的既有狀態,非本 PR 影響。
- **SC-8**(`evidence/SC-8-verify-fail-curl.txt` / `SC-8-verify-fail.log`):`VERIFY_BREADTH_FAIL=1` port 8723 起得來;
  log「verify 失效注入模式:四支取數全拋,落檔目錄 …\data\market-verify」(不再有 market-verify-fail 目錄,
  `ls data | grep verify` 只有 market-verify / market-verify-real);`/api/market/breadth` **200 且
  `stale:true, counts:null`**(restore 的 3 格序列仍在)= 降級不炸;rows 200;sector 404。
- 未改功能抽 2:規則 CRUD `GET /api/stock/signals/rules` 200(預設 CDP 規則等);health 端點 200。

## C. 白名單逐條(spec §2)

| W | 結果 | 證據 |
|---|---|---|
| W-1 家數帶 / 騰落線 / breadth REST+WS | PASS | 截圖 + curl + whitelist lens 核 `_apply`/`close`/`start` 等價 + pytest TestBreadthRest/Rows/WebSocket 綠 |
| W-2 漲跌停列表 / 連板 | PASS | 截圖(11+ 板)+ rows 200 + streak 測試 10 class 全綠 |
| W-3 個股訊號 hub / today / rail / toast | PASS | test_signal_hub / test_signal_routes 綠;today 200;前端 useSignalFeed 收斂後 queryKey/retry/invalidate 等價(lens 核) |
| W-4 XR-3 | PASS | 三支測試改載具(on_tick + locked_up state + session gate monkeypatch)後仍鎖:牆鐘日別 / ws 不 close + status seed / 共用 broadcaster;`_recv_until` 弱化一處已記(WL-P2-3,無 engine 時中間無他訊息) |
| W-5 corr subtab 原位 | PASS | 截圖 |
| W-6 INDEX_SUBTAB_KEY fallback + ORPHAN 六鍵 | PASS | 截圖 + localStorage 查 + constants.ts 六鍵未動 |
| W-7 verify FAIL 注入 / _BREADTH_INFO_ROWS / 8721 守衛 | PASS | SC-8 + test_verify 綠 |
| W-8 BreadthConfig 未知鍵 raise;configs/breadth.json 本機不存在 | PASS | test_breadth_config 綠;`ls configs` 無 breadth.json |
| W-9 同名無關符號 | PASS | grep-frontend / grep-backend 歸類表 |
| W-10 parity oracle / sector map 測試 | PASS | 未動;pytest 綠 |

## D. 死碼零容忍(SC-2 / SC-5 / SC-6;D10)

- `evidence/grep-backend.txt`:英文集 87 命中 / 中文集 18 命中,**要刪但沒刪 = 0**;無關保留全部歸類(家數帶 R2 sector map、
  fake stock_info `industry_category`、TXO option chain、群益 cancel/balance chain、StockEngine 掛點、time axis「時間軸」等)。
- `evidence/grep-frontend.txt`:**零死碼**;殘留 = `timeframe.ts::MarketMode`(K 線)、孤兒鍵字面值、fallback 測試字面值、
  promise chain、圖表 X 軸「時間軸」。
- ruff F401 / pyright unused / tsc / eslint 全淨。
- 自評 lens 抽驗漏網:CD-1(`VERIFY_WINDOW` 註解提 flip / 事件鏈路)→ fix 波修(§F)。

## E. Backward compat / migration 可逆

- API:sector 兩支 404(唯一 caller 同 PR 刪);`?market=` 忽略(curl 實證同結果;fix 波補 pytest 鎖)。
- 資料:零遷移碼。孤兒檔可手刪:`data/market/industry_chain.json`(769 KB)、`data/market-verify/industry_chain.json`。
  `data/signals/<today>.jsonl` 殘留 `market_limit_*` 列的一日 cap 200 擠壓窗:本輪週日 merge、prod 於非交易日重啟即無此窗。
- localStorage:殘值走既有 fallback(截圖實證)。
- 可逆:純刪除,`git revert` 單 PR;無 cache version 變動。
- prod 重啟前順手清 `copycat/__pycache__/sector_rotation*.pyc`、`copycat/server/__pycache__/chain_store*.pyc`(不影響 import,只免版本判讀混淆)。

## F. fix 波後重跑(待補)

fix 波 4 commit(e2b15b82 / 7b82caf0 / b4c6c5b0 / 5d501d82)後全套重跑(`evidence/gate-full-after-fix.txt`):
pytest **2563 passed**(+2 lock:lifespan close / `?market=exclude` 相容,mutation-verified)、ruff 淨、pyright 0、
validate 42/42、vitest 112 files / 1830、tsc 0、eslint 0、react-doctor No issues。
`check_feat_tags.py` → `flow=mod commits=7 PASS`。

## G. §7 回頭核 goal(對照 change-spec §1)

| SC | 判定 | 證據 |
|---|---|---|
| SC-1 兩顆 subtab + 殘值 fallback | PASS | IndexPage.test s1/s2/s2b 綠;`evidence/SC-1-SC-7-subtabs-limit.jpg`(user 過目待) |
| SC-2 前端零引用 | PASS | grep-frontend.txt;tsc/eslint 0 |
| SC-3 sector 404 / today 無 market 參數仍 200 | PASS | curl 檔;`TestSectorRemoved` + `test_legacy_market_query_param_is_ignored` |
| SC-4 四元組 | PASS | TestFetchersArity(3/5 兩側)+ test_verify all_four + TestProdWiring |
| SC-5 hub / engine 無 market、chain 符號 | PASS | grep-backend.txt;pyright/ruff |
| SC-6 死碼零容忍(英 + 中) | PASS | 兩份 grep 證據 + review lens 抽驗(CD-1 漏網已修) |
| SC-7 白名單全活 | PASS | §B/§C |
| SC-8 FAIL 注入降級 | PASS | §B SC-8 |
| SC-9 gate 全綠 | PASS | §A + §F |
| SC-10 文件同步 | PASS | commit 8948dc67 / 7b82caf0 |
