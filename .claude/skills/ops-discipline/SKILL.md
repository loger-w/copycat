---
name: ops-discipline
description: 盤中/本機操作紀律(專案累積教訓)。盤中要驗任何後端改動、起第二台 server、開 worktree 或收尾清 worktree、在 worktree 直跑腳本、做 mutation 驗證迴圈、或設計含「verify 取證」的 spec 前先讀對應節。
---

# 盤中 / 本機操作紀律(2026-08-10 自專案 CLAUDE.md §8 遷移,內容未改)

> 寫入規則:新教訓屬「盤中操作 / worktree / 驗證通道」者追加到本檔對應節,保留日期與 Trigger。

## 盤中驗證通道

- **盤中不要起第二台連 TC4 的後端**(2026-07-31 紀律,理由於 2026-08-18 更正 — 結論不變):
  第二台會對 prod 已訂的 symbol 多掛一把 TC4 refcount key,而上游 feed 以 symbol 為單位 ——
  那把 key 歸零(收工退訂、或 process 死掉被 reap)就把整個 symbol 的推播帶走(**不是**舊說
  的「同 symbol 跨 session 只推一邊」,見 tc4-market-facts)— 失效樣態「原本好好的面板突然全空,
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
- **要驗「吃群益委託 / 成交」的前端功能,側車樣板 = `.claude/mod/intraday-fill-marks/evidence/
  sidecar_server.py`**(2026-08-17):真 `CapitalClient` + `FakeCom`(零 COM / 零真錢,含
  `neutralize_external_env`)、`POST /_fake/fill?seq&stock&side&price&qty&time&market=TS|TF` 一次注入
  N+D 兩筆回報 → `/api/capital/orders` 出現 `filled_qty>0` 的當日成交;`SeededStockSource` 已掛
  2330 的 stkfut catalog(CDF/QFF)並讓 `F:CDF:*` 走 2330 種子價 → 個股期合約下拉可選、合約主圖有價。
  注意種子價域(2330 ref 1200 ±2%):注入價落在 y 域外會被圖層合法丟掉(不是 bug),先算好再注入。
  (Trigger:驗三梯徽章 / 成交點 / 委託列表等吃 orders 的畫面)

- **驗 WS 心跳 / 靜默重連用「側車 event-loop stall」模擬半死連線**(2026-08-20 mod/ws-app-heartbeat):側車加
  `POST /_fake/stall?secs=N` 同步 `time.sleep` 阻塞 loop(TCP 活、零 frame、零 ping),比 suspend process / 拔網路乾淨;
  頁內掛 `MutationObserver` 記 badge 文字變化時戳 + helper 的 `console.warn` 時戳當主證(「連線中斷,重試中」只亮 ~2 s
  截不到靜態圖);patch `window.WebSocket` 記建連時間量 backoff。**觸發前先等 ≥ 1 個心跳間隔**(watchdog 收到首則 ping 才
  武裝)。Chrome MCP 背景分頁 timer 對齊 1 s 粒度(1 s backoff 實測 2 s)屬瀏覽器行為不是 bug;同分頁 dev build 下
  `Page.captureScreenshot` 偶發逾時,重試即可。樣板 `.claude/mod/ws-app-heartbeat/evidence/sidecar_server.py`。
  (Trigger:驗 WS 重連 / 心跳 / 半死連線行為)

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
- **worktree 分支 rebase merge 後的四個收尾坑**(2026-08-30 fix/futures-daily-bars-rollover 全踩 (1)–(3);(4) 同日兩次):
  (1) 主 tree 若留著同名 untracked artifact 副本(§0 第 2 點的「先寫主 tree 再 cp 進 worktree」),
  `git pull --ff-only` 會以「untracked 會被覆蓋」拒絕 —— 先 `MSYS_NO_PATHCONV=1 git show origin/master:<path> | diff -q - <path>`
  比對一致再刪副本(Git Bash 沒有 `MSYS_NO_PATHCONV=1` 時 `rev:path` 的冒號會被轉成 Windows 路徑而 fatal);
  (2) `gh pr merge --rebase` 後 `git branch -d` 必拒「not fully merged」(rebase 改寫 SHA),確認 `gh pr view --json state` = MERGED
  且 origin/master tip subject = 分支末筆後用 `-D`;`--delete-branch` 對 worktree 佔用中的分支會撞本地刪除,遠端另 `git push origin --delete`;
  (3) 收尾鏈用 `&&` 串時,任一步失敗後面的 `|| echo` 會誤印成功字樣 —— 每步印明確 exit / 狀態,不靠 `||`;
  (4) **回填 / 引用 commit SHA 一律對 `origin/master` 做 `git merge-base --is-ancestor`**:GitHub rebase merge 會重寫全部 SHA,
  PR head(含本地 rebase 後)的 SHA 在 merge 後全部不在 master。08-30 兩次踩到:`/pr-review 153` Self-Verify R8 補驗用 PR head
  db0e6d48 當基準(六顆全 yes 但全不在 master);收修 F-13 第一版照抄回填,round-1 review 才抓到。正解 = master SHA +
  「第 n 筆 + subject」(08-27 拍板),例:`a7156aac(第 1 筆 perf(live) 退避)`。
  (Trigger:worktree 分支 merge 後清理 / 回填 commit SHA 進 docs 或 artifacts)
- **前端「輪詢 / 重試節奏」的真環境觀測,分頁必須 visible**(2026-09-01 daily-bars 真環境驗實測):TanStack Query 的
  retryer 與 refetchInterval tick 在 `document.hidden` 分頁**整個暫停**(focusManager 閘),hidden 下白等 75 s 零請求;
  claude-in-chrome 的 MCP 分頁常落在**另一個 Chrome 視窗**、預設 hidden(連 `tabs_create_mcp` 新開的也一樣),
  `resize_window` 不會 raise 視窗 —— 要請 user 點到前景,並先用 `javascript_tool` 查 `document.visibilityState` 再開始計時;
  network 追蹤從第一次 `read_network_requests` 才開始,mount 那發要「先武裝再 reload」才拍得到 t0。
  (Trigger:用 claude-in-chrome 驗任何輪詢 / 重試 / interval 行為)
- **「關達錢 4 視窗」不等於關達錢 4**(2026-09-01 實測):關主視窗後 TOUCHANCE / QuoteZMQService / TradeZMQService /
  TCore64 process 家族照活,ZMQ 照服務,冷啟動的 server 照樣連上拿全量 —— 要製造「TC4 斷線」測試態必須整組結束
  process(工作管理員或 tray 結束);判斷法 = `Get-Process | ? ProcessName -match 'touchance|TCore|ZMQService'` 歸零才算關。
  (Trigger:設計任何需要「達錢 4 關閉」前置的測試 / 驗證)
- **bash `nohup` 起的測試 server 收不到 console Ctrl+C**(2026-09-01 實測):detach 後 `AttachConsole+GenerateConsoleCtrlEvent`
  打不進去,最後只能 `Stop-Process -Force` 強殺(lifespan 清理被跳過 → TC4 端 session 殘留 ~60 s)。測試用 server 要嘛
  用 Start-Process 留 console(配 send_ctrl_c.py),要嘛 CREATE_NEW_PROCESS_GROUP 起、之後送 CTRL_BREAK。
  (Trigger:起任何要事後優雅停掉的臨時 server)
- **突變體迴圈的還原手段決定它能不能在未 commit 的改動上跑**(2026-08-31 fix/daily-bars-siblings-rollover 踩到):腳本用
  `git checkout -- <file>` 還原 = 還原到 **HEAD**,在「review 收修寫好、還沒 commit」的樹上跑會把收修整個洗掉 —— 症狀是第一個突變體之後
  下一個突變體找不到字串(assert 0 命中)、接著全量 vitest 紅在收修新加的那條測試,零其他訊號。正解:收修**先 commit 再跑**突變體;
  或還原改走「讀進記憶體 → 寫回」/ `git stash` 差分,不用 checkout。(Trigger:寫或跑任何會改原始碼再還原的 mutation / 突變體腳本)
- **剛 `npm ci` 的 worktree 全量 vitest 必紅 1–2 條 App 級 lazy `waitFor` 測試、每次不同**(2026-08-30:5/5 次,
  `App.memo` / `App.test` / `App.corr-tab`;單檔重跑 3/3 綠;**stash 掉全部改動仍紅** → 環境不是改動)。判讀順序:
  單檔重跑 → 在 worktree 內 `git stash push` 全部改動再全量(差分)→ 主 tree master 全量對照;三步都指向環境才歸 flake,
  記 next-time 併 test-hygiene 批。(Trigger:worktree 全量 vitest 紅在 App 級測試)
- **主 tree 可能同時被另一 session 用著:`git switch` 前後各查一次 `git status`**(2026-08-24
  真踩到):session 開頭 status 乾淨,幾分鐘後 commit 完才發現多出六個他人未提交的前端改動 ——
  `git switch -c` 會把那些改動一起帶到新分支、又帶回去(內容沒壞,但對方的 branch 名在那幾分鐘
  是錯的)。docs-only / 小 chore 要開分支時:(1) switch 前查 status,有他人改動就**不切**,改用
  `git worktree add` 或把 commit 打在 detached HEAD 再 `git branch` 指過去;(2) push / PR / merge 全
  用 branch ref(`git push origin <br>`、`gh pr merge <br>`),不需要 checkout;(3) 切回去後再查一次
  status 確認改動還在。(Trigger:主 tree 開分支、多 session 並行)

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
- **claude-in-chrome 截圖驗證三個坑**(2026-08-17 R4 真踩到):(a) `computer.zoom` 會把該 tab 的
  device metrics 覆寫成 zoom 區域尺寸且**不還原**(量到 innerWidth 662×588,版面退成單欄還以為是 bug)
  → close-up 一律 PIL crop 整頁截圖,不用 zoom;(b) `resize_window` 對**最大化**的 Chrome 視窗回
  success 但無效(innerWidth 仍 2560)→ 要驗 1920×1080 / 1536×864 用**同源 iframe host**
  (`frontend/public/__viewport_host.html?w=&h=`,臨時檔收尾刪;同源才能 `contentDocument` 量測,
  container query / RO 在 iframe 內照常);(c) 收尾清 vite / 側車**不要 `taskkill //IM node.exe`**
  —— MCP server 也是 node,會一起被殺;用 `netstat -ano | grep :<port>` 取 PID 逐一 kill。
  樣板:`.claude/mod/index-intraday-core/evidence/host.html` + `__measure()` 量測 JS(SC-6 json)。
  (Trigger:claude-in-chrome 要驗特定 viewport / 要 close-up / 收尾清背景 server)
- **stock-engine fake server 最新樣板 = `.claude/mod/group-grid-full-chart/evidence/fake_server.py`**
  (2026-08-17):含 neutralize、20 檔 / 多群組、合成日 bar(overlay 可算)、全日回補不看時鐘、
  realtime ±1 tick 抖動(liveP 路徑真的變);port 走 argv。盤外 `useGroupSnapshots` 不輪詢 →
  fake 重啟後首輪 snapshot 若還在回補,卡片停「回補中…」直到重整(非 bug)。
  2026-08-30 起 `StockSource` Protocol 多了 `prepare_backfill(codes)`(PR #153);`.claude/**/evidence/*_server.py` 13 支既有側車 fake
  都沒有它 —— 照抄起側車能跑,但 worker 出隊 ≥ 2 檔時會在 `except Exception` 印整段 `AttributeError` traceback(降級可用、很吵)。
  抄樣板先補 `def prepare_backfill(self, codes: list[str]) -> None: pass`(參考 `tests/helpers/fake_sources.py::FakeStockSource`)。
  (Trigger:起 fake server 驗個股 / 群組 UI)

## 零推播 / 訂閱異常排查順序(2026-08-18 開盤全站零推播實證)

1. **先看 TC4 自己的 log**:`C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-YYYYMMDD-0.log`(每天一份、盤中 50MB+)。
   `grep "<symbol>|REALTIME|"` 追一把 key 的 `AddSubQuoteCount / RemoveSubQuoteCount(... count:N, SumSubCount:M)` 生命史;
   `ReqSubQuote()` = 真的向上游掛(只在 key count 0→1 時出現);`RemoveLoginInfo` + `ExecuteCheckPingTime` = reap 殭屍 session
   (無 LOGOUT 的 process 死後 ~60s)。任一 key SumSubCount 歸 0 之後同 symbol 全死 → 見 tc4-market-facts「REALTIME 訂閱的真實模型」。
2. server 側:`py-spy dump --pid <pid>`(.venv 已裝)看 `_listen_loop` 是否全在 `sock.recv()` 閒置(閒置 = TC4 沒發,不是我們卡住);
   `/api/stock/state/<code>` 的 `no_data/book/meta` 與 `/api/futures/state` 的 `t` 是否凍結。
3. 判別 probe(scratchpad 一次性腳本):訂 **prod 沒訂過的 symbol**(如 2330)驗 TC4 基建;再訂 prod 的 symbol **換一把窗**
   (EndTime+1h)看是否活 —— 活 = key 被殺,不是 TC4 壞。**probe 一律 UNSUB + Disconnect 收工,且不要用 prod 的窗訂 prod 的 symbol**
   (退訂會把 prod feed 一起帶走)。
4. 不重啟的止血:側車 process 用變體窗持有 prod 全部 key(從 TC4 log 抓 `AddSubQuoteCount(<prod session>,…|REALTIME|…)`),
   PUB 是廣播所以 prod 立刻復活;fix 上線後再停側車(停掉那刻 feed 會再斷一次,由自癒接手)。

## 瀏覽器分頁「跑幾小時後掛掉」排查順序(2026-08-19 renderer Aw Snap 實證)

1. **OS 層先看 renderer process**(PowerShell `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"` 取 `--type=renderer`
   + `Get-Process` 的 WorkingSet / Private / CPU / 建立時間;background loop 每 60 s 寫 CSV):分頁 JS 層量不到 Blink 側記憶體。
   實證:renderer Private 15 GB、一核 100% 4.5 h,而 `performance.memory.usedJSHeapSize` 全程 ≤ 170 MB。
2. **Long Task API 只看 >50 ms,`performance.memory` 只看 V8 heap** —— 主執行緒 66% 忙 / 15 GB 膨脹都「看不見」。
   主執行緒忙碌度用 MessageChannel ping-pong 2 s 迭代數對照靜態頁(200k vs 68k);非 V8 記憶體先查
   `performance.getEntriesByType('measure'|'mark').length`(User Timing buffer 無上限、不回收)、Web Audio 節點、canvas。
3. **確認哪個分頁在哪個 process**:分頁內 `new Uint8Array(300MB)` 看哪個 renderer 跳;導到靜態頁看 CPU 是否歸 0。
   Chrome 會把同站分頁合進同一 process(同站主框架門檻),user 分頁與 MCP 分頁可能共生死。
4. **隱藏分頁 timer 被 intensive throttling 壓到每分鐘一次**(20 s 實測 `setInterval(1s)` 7 次)→ 背景清理 / 取樣不要靠
   setInterval;PerformanceObserver 回呼不受節流(同 20 s 256 次)。sampler 寫 localStorage(分頁死了仍可讀)。
5. **React 19.2 dev build Component Performance Track**:props identity 變的 re-render 每筆 `performance.measure`(~1.8 KB),
   本 app 每則 WS 全樹 re-render → 632 筆/s ≈ 1.1 MB/s。已由 `frontend/src/lib/dev-perf-guard.ts` dev-only 守門(PR #70);
   **看盤日常仍建議跑 production build**,dev server 只做開發。chrome-devtools MCP 是獨立 profile,看不到 user 的 Chrome。
   (Trigger:任何「瀏覽器用一段時間變慢 / 掛掉」回報、或在 dev server 上長時間跑 WS 重繪型頁面)
