# verification — feat/chart-ux-batch-0826(#107)

日期 2026-08-26 01:00–02:00;worktree `C:\side-project\copycat-wt-chart-ux`;HEAD 26ca1a41(review round 1 收修後)。
python = `C:\side-project\copycat\.venv\Scripts\python`(3.13;editable 指主 tree,但 pytest 走 pyproject pythonpath = worktree code)。

## 自動化 gate

| gate | 指令(worktree root / frontend) | 結果 | exit |
|---|---|---|---|
| pytest 全量 | `python -m pytest -q` | 3057 passed, 3 skipped, **1 failed**:`tests/server/test_ws_disconnect.py::TestRelay::test_close_sent_runtime_error_is_not_logged_as_warning` — 單跑 3/3 綠(24 passed ×3),不在本分支 diff(ws.py / 該測試最後動於 a6b3bace);全量並行下的既有時序 flake | 0(見註) |
| pytest 收修後定向 | `python -m pytest -q tests/capital tests/test_corr_config.py` | 406 passed | 0 |
| ruff | `python -m ruff check copycat tests` | All checks passed | 0 |
| pyright | `python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `python -m copycat validate`(**在主 tree 跑**:worktree 無 out/ replay 產物(gitignored);`git diff e01a083b...HEAD -- copycat/engine copycat/replay copycat/data copycat/backtest` 為空,replay 鏈 code 逐字未動) | 42/42 PASS | 0 |
| vitest 全量 | `npx vitest run` | 150 files / 2798 tests 全綠(收修前跑;收修後 `src/components/stock src/hooks` 55 files / 1129 passed) | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 剩兩條皆**存量**(`App.tsx:116` / `GroupGridView.tsx:71` only-export-components,非本分支新增);本分支新增的 `rules-of-hooks`(idxLines useMemo 在早退之後)已於 b407471e 修掉 → 0 新增 finding | 0 |

## F5 反向驗證(/bug 特有)

`tests/capital/test_fill_latency.py` 複製到暫存目錄、以 `PYTHONPATH=主 tree(e01a083b,無修復)` 跑:
`1 failed, 1 passed` — `AssertionError: 部位推播晚於回查鏈出手(fill → 推播 464 ms):['position', 'balance-query-was-already-sent']`。
worktree(含修復)同檔:2 passed(推播早於第一次 GetRealBalance;修前 463–464 ms)。紅 → 綠 → 還原紅成立。

## 真實環境(worktree vite dev :5199 → proxy prod :8721(3fabfc7e,TC4 開著,夜間 08-25 資料);claude-in-chrome)

| 項 | 操作路徑 | 可指認結果 | 證據 |
|---|---|---|---|
| F1 happy | 個股(期)tab → 2330 單檔 → toggle 列點「加權」「櫃買」 | 主圖多出**金色實線**(加權)與**藍色虛線**(櫃買),右緣末點標「櫃買 +0.91%」/「加權 +0.9x%」;toggle 列 7 顆:均價 / CDP / MA / 量分佈 / 成交點 / 加權 / 櫃買 | `evidence/f1-index-overlay-2330.jpg` |
| F1 edge | 群組圖牆(光通,9 檔) | 每張卡各自畫出兩條指數線(同一 toggle 狀態,卡片內無按鈕) | `evidence/f3-sync-crosshair-group-wall.jpg` |
| F3 happy | 圖牆 hover 第一張卡(3081)11:07 | **九張卡同時**在 11:07 出垂直虛線 + 時間標「11:07」,各卡 readout 切到 11:07 的價量;圖牆 toggle 列第 8 顆「十字線」亮 | 同上 |
| F2 happy | 圖牆停在「光通」→ 點側欄「石英」區段的 3042 | 群組 pill 切到「石英」(高亮),圖牆換成 3042 / 2484 兩張卡,右欄閃電梯換成 3042 晶技 | `evidence/f2-sidebar-click-switches-group.jpg` |
| F4 | 探測(非 UI) | `spikes/corr_legs_probe.py` 01:02 實跑:VX 19 / CL 163 / GC 172 推播、1K 50 rows;VXM 0;TWD 全樹無 | `evidence/corr-legs-probe.md` |
| 未改功能抽查 | 選擇權 tab(首頁)/ 個股 K 線頁 toggle 列 | 選擇權損益曲線正常;個股單檔頁其餘五顆 toggle 位置與文案不變 | 首張截圖(session 內) |

未在真環境驗到(留給 user 過目 / 盤中):F1 右緣標籤與現價泡泡 / CDP 標籤在末點附近**會互疊**(1568 寬截圖可見「加權」標壓在 2400 標旁);
F3 關「十字線」後其他卡不再同步(僅 vitest 覆蓋);F4 四腿在 prod 重啟後的相關係數 / 江波圖畫面(需重啟 8721);
F5 真成交(需盤中真下單;log 已備:`成交樂觀套用部位` / `balance 鏈: … 自成交回報到達起 N ms` / `期貨部位鍵差異`)。

## 既知環境事實(本輪踩到)

- worktree `frontend/npm ci` 失敗:`package-lock.json` 與 `package.json` 不同步(@emnapi/*),主 tree 是 `npm install` 裝的;本輪以 robocopy 複製主 tree node_modules(ops-discipline 三險:不可用 junction)。
- 全量 vitest 在 dev 頁截圖時 CDP `Page.captureScreenshot` 偶發 30 s timeout(dev build 重),重試即過,不是頁面卡死。

## Rebase 後重跑(origin/master 移動:fix/tc4-logout + mod/shutdown-budget;衝突僅 GroupGridView.tsx 兩個 commit,取分支側 + master 的 readLocal 內聯)

| gate | 結果 | exit |
|---|---|---|
| `python -m pytest -q` | 3083 passed, 3 skipped(本次 ws_disconnect 亦綠) | 0 |
| `python -m ruff check copycat tests` | All checks passed | 0 |
| `python -m pyright` | 0 errors | 0 |
| `npx vitest run` | 150 files / 2799 passed | 0 |
| `npx tsc -b` / `npx eslint src` | 0 / 0 | 0 |

## /pr-review #111 收修後重跑(報告 `docs/superpowers/specs/pr-111-review{,.audit}.md`;22 條:Must 2 / Should 5 / Nice 15,F-12 / F-20 ask-user 留 next-time,其餘 20 條已修)

| gate | 結果 | exit |
|---|---|---|
| `python -m pytest -q` | 3090 passed, 3 skipped | 0 |
| `python -m ruff check copycat tests spikes/corr_legs_probe.py` | All checks passed | 0 |
| `python -m pyright` | 0 errors | 0 |
| `npx vitest run` | 150 files / 2804 passed | 0 |
| `npx tsc -b` / `npx eslint src` | 0 / 0 | 0 |

新增 seams:`tests/live/test_corr_source.py::TestTwsLegWindow`(F-01)、`tests/capital/test_store.py` 四條(F-02 seeded / clear 重播、F-03 翻倉判號、F-04 調整碼與未白名單選擇權)、`test_mapping` / `test_reply` 反例、`index-overlay-lines.test.ts` 域外 / STKFUT / NaN / stale 四條、`synchover` 回呼換人補發一條。

## 08-26 盤中真成交回填(prod `c430a662`,`logs/server-20260826-0851.log`)

13 筆整股真成交全數樂觀套用(`成交樂觀套用部位` 0.0–0.7 ms;`成交未樂觀套用` 1 筆 = 6949 上櫃零股 market=TC);
券商回查鏈落地 `部位落地 … 自成交回報到達起` **624–5538 ms**(中位 ~1.6 s;9:16 那筆 5538 ms 為當日最慢)。
修前 FakeCom 463 ms 是「鏈落地」的下界;真環境鏈 1–2 s,樂觀推播提早 3 個數量級。
期貨段整天 `期貨部位段收齊 0 列` → **當日無期貨成交,`期貨部位鍵差異` 判準仍未驗**。
`負股數` / `種類標籤未知` 零筆 → 無券當沖校準樣本仍缺。
14:31 收盤後重啟的重播段 13 筆全印 `成交未樂觀套用(零股 / 無券 / …)` —— 真正原因是 F-02「快照未落地不套」,
log 文案把它混進零股那句(留尾:分開印)。
user 回饋:倉位出現確實變快;**但「獲利價位」會變換位置** —— 候選 = 樂觀均價(純成交價)被 1–2 s 後的券商均價覆蓋、
或 next-time「鏈在途覆蓋回成交前快照」那條;待 /bug。
