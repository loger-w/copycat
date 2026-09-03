# 群組圖牆逐筆(`mod/group-grid-ticks`,C9)— verification

分支 `mod/group-grid-ticks`(worktree,自 master `a344da9f` 切出)。spec #179;tickets #180–#186。

## 1. commits(每票 🟢 紅測試 → 🔴/🟢 實作;三類不混)

| sha | 票 | 類 | 內容 |
|---|---|---|---|
| `b14f50e8` | T1 #180 | 🟢 red | 5 處單筆 `tick` 斷言改攤平 items + `TestTickBundle` 四案(含 50 檔壓測) |
| `24f77c5f` | T1 | 🔴 green | 0.1 s `ticks` 打包 + `set_view/clear_view`;單筆 `tick` 退役 |
| `20564f03` | T2 #182 | 🟢 red | view 登記 / 斷線除名 / 壞輸入 WARNING;dropped 計數;light_snapshot 加鍵 |
| `2539a712` | T2 | 🟢 green | relay `on_message` 選配;ws_stock token;`WsBroadcaster.dropped` + 60 s 節流 WARNING;`seq`/`vwap_vol` |
| `9805e26e` | T3 #183 | 🟢 red | 主圖吃打包 / 非主圖丟匯流排 / view 送與 onopen 重送 / `WsHandle.send` |
| `772a4207` | T3 | 🔴 green | `lib/tick-stream.ts`;useStockStream `ticks`;`WsHandle.send`;`StockTickMsg → StockTickItem` |
| `ff186a5b` | T4 #185 | 🟢 red | `useGroupLiveAccums` 九案;播種 seq/vwapVol;memo / geometry 變因改 tick |
| `51e99712` | T4 | 🔴 green | 卡片吃 live accum;group-state 解析 seq/vwap_vol;`setTickView` |
| `fcaad72f` | T5 #181 | 🟢 red | pill 藏盤前篩選 / 未分組 / 側欄未分組列切組翻轉 / 後端 parity |
| `08c31ae0` | T5 | 🔴 green | `SCREEN_GROUP_NAME` / `UNGROUPED_PICK` / `resolveGroupPick` |
| `b64ffb41` | T6 #184 | 🟢 red | `groupForCode` 四案 + StockPage 四段情境 |
| `125e0640` | T6 | 🟢 green | 訊號 → 切組接線 |
| `56f07e3b` | T2 回填 | 🟢 | `TestGroupSnapshot` 鍵集 additive 回填(全量 pytest 抓到的兩條) |
| `78e42219` | T4 收整 | 🔵 | doctor:ref 同步改 effect / 播種讀 quotesRef / pill flatMap(零行為) |
| `314d6e3d` | T7 #186 | 🟢 docs | CLAUDE.md §4 三條契約 / next-time C9 勾銷 / 兩支 skill 沉澱 / change-spec |
| `482ccda5` | review r1 | 🔴 fix | spec F-01(主圖檔的群組卡片也收逐筆)/ F-03(重拉早退補冷卻)/ F-04(accum 缺席收進無資料);順帶 std F-04 改名、F-06 TDZ |
| `379bf4f1` | review r1 | 🔵 | std F-03 `visibleGroups` / F-05 否決註記 |
| `c9e92ca5` | review r1 | 🟢 docs | std F-01 書面例外 / F-02 入 next-time |

**明文偏離(spec F-02)**:#181 AC 寫「(a) 藏盤前篩選 🔴 與 (b) 未分組 🟢 分開 commit」,實作是單一 `08c31ae0` —— 兩件都經
`resolveGroupPick` **同一份解析**(藏 = 過濾可見集合、未分組 = 集合多一項),拆 commit 等於把同一個函式切兩半各留一個
半成品;取捨為「一個 🔴 commit 明文含兩件」而不是製造兩個都不完整的中間態。

## 2. 紅 → 綠(紅態證據)

- T1:`-k "TickBundle or test_tick_ …"` 先紅(`IndexError: list index out of range` —— 單筆 `tick` 已不在斷言路徑);實作後
  `test_stock_engine.py` **197 passed**(含 `TestTickBundle` 4:檢視集合 / 同則多檔 seq / 訂閱池正交 / 50 檔 × 20 筆 → 1000 items、
  打包 ≤ 3 則、逐檔 seq 1..20 連續)。
- T2:四檔 `-k "LightSnapshot or Backpressure or TestRelay or TestStockWs or batch_shape"` **10 failed / 20 passed** → 實作後 **30 passed**;
  四檔全量 **215 passed**。
- T3:`useStockStream.test.ts` 整檔 import 失敗(`@/lib/tick-stream` 不存在)+ `App.memo` tick 案紅 → 實作後四檔 **4 passed**。
- T4:`useGroupLiveAccums.test.tsx` 整檔紅 + memo 五案 + geometry 一案 + stock-accum 兩案 + useGroupSnapshots 一案紅 →
  實作後八檔 **8 passed**(中途 toggle 測試 `Too many re-renders` → render 期 setState 改為合成時忽略舊層,已沉澱 skill)。
- T5:9 failed(resolveGroupPick 4 / pill 4 / StockPage 1)→ **6 files passed**;後端 parity `test_screen_engine.py` 5 passed。
- T6:5 failed(groupForCode 4 / StockPage 1)→ **3 files passed**。

## 3. 完成前 gate(全綠;`314d6e3d` 工作樹)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q`(worktree root) | **3361 passed, 3 skipped**(214.94 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four …/four_tigers`(worktree code,主 tree replay 產物) | **42/42 PASS** | 0 |
| `npx vitest run`(frontend/) | **154 files / 2959 tests passed** | 0 |
| `npx tsc -b`(frontend/) | PASS | 0 |
| `npx eslint src`(frontend/) | PASS | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | 僅剩 2 條 `no-high-complexity-react-function`(GroupGridView:131 / StockPage:78)—— **master 基準已有**(同函式,行號位移),零新增;新增的 4 條 `no-ref-current-in-render` + 1 條 `js-combine-iterations` + 1 條 missing deps 已修(`78e42219`) | 0 |

**收修後最終重跑(`c9e92ca5` 工作樹)**:`npx vitest run` **154 files / 2959 tests passed**(exit 0);
`react-doctor --scope changed` 只剩 `StockPage.tsx:78` 一條基準既有的複雜度(GroupCard 那條因收斂分支而消失),exit 0;
`tsc -b` 0、`eslint` 0(受影響五檔);後端 `test_stock_routes.py` 74 passed、ruff / pyright `app.py` 0(app.py 只動註解與型別標註;
全量 pytest 3361 的基準在 `314d6e3d`,其後後端唯一改動即此)。
**spec F-01 突變體檢驗**:把 `emitTicks(items)` 改回只送非主圖 items → `useStockStream.test.ts -t 匯流排` **2 條紅**;還原後綠
(`git diff` 空)。

ruff format:`stock_engine.py` / `ws.py` / `stock_state.py` 已 formatted;`app.py` / `test_stock_engine.py` master 版本本來就未 format,依 backend-conventions 不整檔重排(diff hunk 全在既有段落,新增段落乾淨)。

## 4. 真實環境(盤中,prod 重啟 + dist 重 build 後;T7 #186 留給 user / 下一盤中)

- [ ] ① 群組檢視卡片線與量隨成交動、與右欄主圖同步(動機判準;user 親核)
- [ ] ② 盤後 `grep "佇列滿" logs/server-*.log` 為 0
- [ ] ③ 開盤 5 分鐘 DevTools performance trace 無 > 50 ms long task(截圖入 `evidence/`)
- [ ] ④ 三件 UI 過目:pill 列無「盤前篩選」/ 有未分組成員時多「未分組」pill / 群組檢視點訊號切到含該檔的群組
- 白名單抽驗(自動化已覆蓋):W1 `book` / `watchlist_quote` 既有測試零改動綠;W3 `TestGroupSnapshot` 12 passed;W5 `TestRelay`
  既有案零改動;W8 `useGroupSnapshots` 輪詢案零改動;W9 `StockPage` 單檔檢視訊號案零改動。

## 5. Review(two-axis,fixed point `a344da9f`,reviewed head `314d6e3d`)

- 標準軸 6 條(MED 2 / LOW 4;零硬違規、白名單未破):F-01 TQ 慣例 → 書面例外;F-02 重複狀態機 → next-time;
  F-03 / F-04 / F-06 修;F-05 否決(pyright 窄化)。
- spec 軸 4 條(HIGH 1 / LOW 3):**F-01 主圖檔的群組卡片收不到逐筆 → 修**(`emitTicks(items)` 整則);F-02 commit 切分 →
  明文偏離(§1);F-03 / F-04 修。
- 收修後 gate 重跑(`c9e92ca5` 工作樹):受影響 9 個前端測試檔 passed、`tsc -b` 0、eslint 0;`test_stock_routes.py` 74 passed、
  ruff / pyright app.py 0;全量 vitest + doctor 重跑見 §3 末列。
- 逐條 findings 原文與處置:`code-review-round-1.json`。

## 6. 回頭核 goal(spec #179 / tickets AC 逐條)

| 要求 | 實作 | 測試 / 證據 |
|---|---|---|
| US1 每張卡片線 / 量 / 現價隨成交前進 | `useGroupLiveAccums` + `CardIntradayChart(accum)` | `useGroupLiveAccums.test` 連續套用案;memo test「一則只含一檔的 tick」;真環境 ① 待盤中 |
| US2 主圖與卡片同一則同一次重繪 | 後端一則打包;前端 `ticks` case 一次 setAccum + `emitTicks(items)` 整則 | `useStockStream.test`「一則含主圖 3 筆 → commit 一次」「整則原序上匯流排」(review F-01 修後) |
| US3 主圖最多晚 0.1 s | `tick_flush_secs=0.1` `call_later` | `TestTickBundle` 同窗一則;user 拍板接受 |
| US4 50 檔開盤不卡 | 打包 ≤ 10 則/s | 真環境 ③ trace 待盤中(自動化不可驗) |
| US5 / US6 seq 連續、跳號只重拉那一檔 | per-code seq;`group-state?codes=X` 單飛 + pending 重放 + 冷卻 | hook 測試「跳號 → 只重拉那一檔」「在飛 pending 重放」「失敗冷卻」;`TestTickBundle` 逐檔 seq 1..20 |
| US7 丟包計數 + 節流 WARNING | `WsBroadcaster.dropped` / `_note_drop` | `test_drops_are_counted_and_warned_once_per_window`;真環境 ② grep 待盤後 |
| US8 只收看得到的檔 | `set_view` / `_tick_targets`;`setTickView` 掛載 / 換組 / 卸載 | `test_watchlist_member_is_not_bundled_until_a_view_registers_it`;`TestStockWsView` |
| US9 重連重送 view | `onOpen` → `sendView(getTickView())` | `useStockStream.test`「onopen(重連)重送當下集合」 |
| US10 訊號層不受影響 | `_handle_quote` 訊號掛點未動 | 既有 signal_hub 測試零改動綠(全量 3361) |
| US11 訂閱池不變 | `set_view` 不碰 `_refs` | `test_set_view_does_not_touch_the_subscription_pool` + route 版 |
| US12 pill 藏盤前篩選(側欄照舊) | `resolveGroupPick` / pill flatMap | GroupGridView.test「pill 列不含盤前篩選」「記住盤前篩選 → fallback」 |
| US13 未分組 pill 不落檔 | `UNGROUPED_PICK` sentinel;`ungroupedCodes(wl)` 現算 | 「有未分組成員 → 多一顆」「未分組空 → 沒有」;localStorage 只記 sentinel |
| US14 側欄未分組列切到未分組 | StockPage sidebar onSelect | StockPage.test 翻轉案 |
| US15 / US16 訊號切組 | `groupForCode` + StockPage SignalRail onSelect | watchlist-model.test 四案;StockPage.test 四段情境 |
| US17 盤外 60 s 輪詢不變 | `useGroupSnapshots` 未動 | `useGroupSnapshots.test` 輪詢案零改動 |
| US18 單筆 tick 退役 | `_handle_quote` 只累積 | `TestTickBundle`「單筆 tick 型別退役」斷言;前端 `StockTickItem` 無 type |
| US19 group-state additive | `light_snapshot` 加 `seq` / `vwap_vol` | `TestLightSnapshot` 三案 + route 鍵集 + `TestGroupSnapshot` 兩條回填 |
| US20 群組名 parity | `SCREEN_GROUP_NAME` ↔ `SCREEN_GROUP` | `test_screen_group_name_parity_with_frontend` |
| US21 50 檔壓測是單元 | FakeSource 50 × 20 | `test_pressure_50_codes_20_ticks_each_land_in_few_bundles_seq_contiguous` |
| US22 trace 截圖入 docs | — | 真環境 ③ 待盤中(evidence/ 目錄已建) |
| 白名單 W1–W13 | 見 change-spec §3 | 既有測試零改動綠;review 兩軸皆報「未破」 |
| 不做 rAF | change-spec §2.6 | doctor / 全量 vitest 綠;量到 long task 才加(③) |

未完成 = 真環境 ①②③④(需 prod 重啟 + dist 重 build + 盤中),明列於收尾回報與 next-time C9 條。

## 09-03 開盤真環境驗證(排程 session;prod 8d42098d 08:23 起、dist 08:59 重 build)

- **① PASS**:群組檢視(玻璃)四卡 12 秒對比 readout 全前進(51.6→51.7 / 113.5→115 /
  107.5→107 / 140→139.5),卡片線與量隨成交動。截圖 `evidence/group_grid_live_2026-09-03_0905.jpeg`;
  「與右欄主圖同步」的目視半邊請 user 過目。
- **③ PASS**:09:01–09:03 devtools performance trace 93 s(`evidence/trace_2026-09-03_0902.json.json.gz`),
  RunTask 148,274 個、**>50 ms = 0**(最大 36.7 ms 一次,常態尖峰 ~18 ms)。
- **④ PASS**:群組檢視 pill 列 = 玻璃/光通/MLCC/矽晶圓/CCL/ALL IN/**未分組**,無「盤前篩選」
  (側欄自選清單顯示「盤前篩選 43」群組屬正常 —— 判準只管 pill 列)。
- ② 佇列滿 grep 留盤後(14:07 排程)。
- 附註:「版本落差」badge 亮著 = dist(08:59 build,含 33aba77e docs commits)比 backend
  (8d42098d)新兩筆 docs-only commit,功能等價,下次重啟自然消。前置事故一則:08:41 發現
  dist 仍是 09-01 舊 build(#187 後端已把單筆 tick 退役 → 舊前端聽不懂新格式),08:59 由排程
  session 代跑 `npm run build` 補上。
