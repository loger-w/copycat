---
name: ops-discipline
description: 盤中/本機操作紀律(專案累積教訓)。盤中要驗任何後端改動、起第二台 server、開 worktree 或收尾清 worktree、在 worktree 直跑腳本、做 mutation 驗證迴圈、或設計含「verify 取證」的 spec 前先讀對應節。
---

# 盤中 / 本機操作紀律(2026-08-10 自專案 CLAUDE.md §8 遷移,內容未改)

> 寫入規則:新教訓屬「盤中操作 / worktree / 驗證通道」者追加到本檔對應節,保留日期與 Trigger。

## 盤中驗證通道

- **盤中不要起第二台連 TC4 的後端**(2026-07-31 紀律):同 symbol 跨 session 只推一邊
  (見 tc4-market-facts),第二台會靜默搶走跑著那台的推播 — 失效樣態「原本好好的面板突然全空,
  兩邊都沒錯誤訊息」。**驗前端改動只起 vite dev server**(proxy 指 8721,零新增訂閱);**驗後端
  HTTP 層(route 形狀 / 非行情 endpoint)用 fake source + 另一個 port**(不碰 ZMQ,盤中安全)。
  同理:**不要為了看新 code 就重啟跑著的 server** — 櫃買當日序列純 in-memory,重啟即歸零;
  真要重啟先確認那份資料不再需要。(Trigger:盤中驗任何後端改動)
- **盤中驗 FinMind 類後端改動走「側車 server」**(2026-08-06 R2 實證):fake TXO source +
  真 FinMind fetchers(顯式三元組以閉包綁真 token — 顯式傳入路徑會拿 dummy token)+
  `neutralize_external_env()` + 落檔隔離目錄 + 非 canonical port,全程零 TC4/ZMQ → 盤中即可拿
  真數據做 real-env 驗證(重啟 restore、失效注入、同分鐘對照)。樣板:R2 evidence 的
  breadth_side_server.py。(Trigger:盤中驗不碰 ZMQ 的後端資料管線)
- **抄側車 / fake server 樣板時,`neutralize_external_env()` 是第一個要核的行**
  (2026-08-13 mod/trial-pause-badge 真踩):group-grid / signal-rules 世代的
  `fake_server.py` 樣板**沒有**憑證中和,照抄起服會拿 .env 真憑證登入群益**正式環境**
  (當次僅唯讀查詢無下單,但不該發生)。含中和的最新 stock-engine 側車樣板 =
  `.claude/mod/trial-pause-badge/evidence/fake_server.py`(neutralize 必須在
  `create_app` import 使用**之前**呼叫);FinMind 側車樣板見上條 r3/r4。判準:凡起真
  `create_app` 的腳本,開頭沒有 neutralize / 顯式空字串壓制 = 不合格,先補再跑。
  (Trigger:新開任何側車 / 一次性起 app 腳本 / 抄舊 evidence 樣板)
- **非 prod 進程的 `create_app` 一律必傳 `stock_watchlist_path` 隔離**(2026-08-12 XR-3
  review C-1/W-1):hub 解耦後**恆建**(不再需要 stock engine),而它的落點 = `wl_path.parent`
  —— 漏傳就落在 repo 真 `data/`,把該進程的事件寫進 prod 的 `data/signals/*.jsonl`。那份 jsonl
  是 prod today 端點 / 自選 rail 的 baseline 真相源,被灌 fake 訊號後 **prod 畫面會出現假訊號且
  同 id 去重會吃掉真訊號**(2026-08-16 前另有 breadth 對帳 seed 語意,R1 刪除後不再存在,隔離
  紀律不變)。與 `breadth_data_dir` 同一條隔離原則,指向同一個隔離目錄:
  `stock_watchlist_path=DATA_DIR / "stock_watchlist.json"`。側車樣板(r3/r4
  breadth_side_server)與 `--verify` 分支均已補;新開任何側車 / 一次性腳本照抄。
  (Trigger:寫任何非 prod 的 create_app 呼叫點)
- **`--verify` 模式的訊號鏈**:2026-08-06 R4 實測「沒有 stock engine → SignalHub 恆 None →
  訊號鏈不可達」的教訓 **已於 XR-3(2026-08-12)勾銷** —— `_make_signals` 不再看 stock 在否,
  verify server 上 hub 恆建、today 端點 200,落點在 `VERIFY_DATA_DIR`(上一條的隔離)。
  要餵真 tick 走個股訊號偵測仍需 FakeStockSource(舊樣板
  `.claude/feat/market-overview-r4-sector-signals/evidence/events_side_server_r4.py` 保留備用,
  其廣度事件段已隨 2026-08-16 R1 刪除失效)。**`--verify` 的家數帶 fake fetchers 是四元組**
  (2026-08-16 起;舊側車樣板 `sidecar_server.py` 的五元組 + `fetch_industry_chain` 已失效,
  不可照抄)。(Trigger:驗 signal_hub 改動、起 verify / 側車、或 spec 含「verify 取證」字樣)
- **跑著的 server 是哪一版**:`curl -s localhost:8721/api/health` → `{git_sha, git_dirty,
  started_at}`;`git log <git_sha>..HEAD -- copycat/` 有輸出 = 後端 code 比跑著的新,該重啟。
  啟動 banner 也印同一份(`copycat server build <sha> [+dirty] started_at=…`,不用 curl 也能判)。
  「改了沒生效」先查這條再查 code(2026-07-29 曾誤查一輪;middleware range 判別含
  `-- :/copycat` 過濾)。dev(vite)下 nav 右緣 amber
  「版本落差」膠囊亮 = 同一判法命中,uncommitted 改動仍不可測。(Trigger:懷疑改動沒生效)

## Worktree 三險(2026-07-30 全數真踩到)

- **gitignored 依賴要「複製」不要「junction」**:`frontend/node_modules` 與 `spikes/TCPY` 被
  gitignore,worktree 一開就缺。junction 連回主 tree 當下可用,但 `git worktree remove --force`
  會沿 junction 把主 tree 目標內容刪掉(實測 node_modules 195 項 + TCPY 官方 wrapper 雙雙清空)。
  正確 = `Copy-Item -Recurse`(TCPY 22MB;node_modules 走 `npm ci`),或 remove 前先刪 junction。
  TCPY 復原源:另一 worktree / neigui five-tigers 同 hash 檔 / `C:\Users\USER\Downloads\
  tc4_python_api_2407\`。(Trigger:開 worktree 做前端/TC4 工作、收尾清 worktree 前)
- **`git worktree remove` 會把 worktree 內 `.claude/mod/<slug>/` artifact 一起刪**(gitignored
  產物從未進版控)。在 worktree 跑流程時 artifact 一開始就寫主 tree 的 `.claude/<flow>/<slug>/`
  (reviewer dispatch 吃絕對路徑),或 remove 前 Copy-Item 出來。(Trigger:worktree 跑流程 / 清 worktree)
- **worktree 內直跑腳本會靜默 import 主 tree 的 code**:venv 是 editable copycat(.pth 釘死主
  tree)。pytest 不受影響(pyproject pythonpath)、`python -c` 不受影響;**`python <dir>/script.py`
  的 `sys.path[0]` 是腳本所在目錄** → probe/repro 腳本 import 到主 tree,腳本正常跑完只是驗的是
  別份 code。worktree 內直跑腳本開頭要 `sys.path.insert(0, <repo root>)`。另:remove 時有 process
  開著 worktree 檔案會以 Invalid argument 失敗且先刪 `.git/worktrees/<name>` 中繼資料 → 收尾要
  `git worktree prune` + 手動 rmdir。(Trigger:worktree 寫直跑腳本 / 收尾清 worktree)

## 驗證迴圈

- **mutation 驗證的同秒 pycache 陷阱**(2026-08-05 真踩到):「改壞→跑測試→還原」同一秒內完成,
  pyc 只比對 `int(mtime)`+size 視為 fresh → 還原後不重編,出現與改動無關的假紅。還原後 `sleep 1`
  或清 `__pycache__`。(Trigger:快速 mutation 驗證迴圈)
- **claude-in-chrome 截圖驗證下 tab 多半是 `visibilityState=hidden`**(2026-08-17 R4 真踩到):
  背景 tab 不 render frame → `ResizeObserver` **不投遞** → 走 `useContainerSize` 的元件
  (StockChart / CardIntradayChart 卡片圖)量不到尺寸就不畫、視窗 resize 後 viewBox 不更新;
  `screenshot` 動作會逼出一幀(RO 隨之投遞),JS 端 `PerformanceObserver longtask` 仍量得到
  render/commit 但不含 paint。判法:`document.visibilityState` / 自掛 RO 零 hit;處置:先 screenshot
  一次再查 DOM,或 `AppActivate` Chrome 視窗;效能結論一律標「hidden tab,JS 成本」。
  (Trigger:截圖驗證含 ResizeObserver 元件、量 UI 效能)
- **stock-engine fake server 最新樣板 = `.claude/mod/group-grid-full-chart/evidence/fake_server.py`**
  (2026-08-17):含 neutralize、20 檔 / 多群組、合成日 bar(overlay 可算)、全日回補不看時鐘、
  realtime ±1 tick 抖動(liveP 路徑真的變);port 走 argv。盤外 `useGroupSnapshots` 不輪詢 →
  fake 重啟後首輪 snapshot 若還在回補,卡片停「回補中…」直到重整(非 bug)。
  (Trigger:起 fake server 驗個股 / 群組 UI)
