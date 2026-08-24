# R3 個股串流/顯示雜項批 — verification

分支 `mod/stream-ui-misc`(自 `e48314a5` master 切出)。只 commit 不 push。

## 1. commits(紅 → 綠 → 🔵)

| sha | 類 | 內容 |
|---|---|---|
| `e216d4d4` | 🟢 red | 八條的 failing test(N008/N120/N119/N109/N108/N262/N265/N013)+ change-spec |
| `a2738219` | 🔴 green | 八條實作 + `App.test` tc4 文案斷言同步(事前標為該變) |
| `6697f9ce` | 🔵 refactor | N121 / N012 / N013 三條記錄性(註解 + 判定,零行為) |
| `7fb796e4` | 🔵 refactor | `buildOverlayGeometry` 改單趟 for(doctor 新增 finding 歸零) |

## 2. 紅 → 綠(紅態證據)

紅態(`e216d4d4` 當下)兩批共 **19 failed / 340 passed**:

- 批一(`stock-accum` / `TickTape` / `RadioPills` / `index-chart-svg`):9 failed / 79 passed
  - `TickRow.n 單調序號(N120)` ×4
  - `TickTape 滿載後 key 穩定(N120)` ×1(`expected <tr> to be <tr> // Object.is equality` = 整片重掛)
  - `RadioPills onInteract` ×3(`expected "spy" to be called 2 times, but got 4 times`)
  - `buildOverlayGeometry 每條線帶回原始 index` ×1
- 批二(`MarketPane` / `useIndexStream` / `useBreadth` / `ToastStack` / `StockPage` / `StockIntradayChart`):10 failed / 261 passed
  - `StockIntradayChart VP 載入佔位(N008)` ×3
  - `useIndexStream 同 tick 兩則訊息(N119)` ×2、`useBreadth 同 tick 兩則訊息(N119)` ×1
  - `StockPage TC4 斷線告警列` ×1、`MarketPane 櫃買快照源中斷(N108)` ×1
  - `MarketPane 重疊單邊 ref 缺值(N262)` ×1、`ToastStack 長文案 clamp(N013)` ×1

刻意寫下即綠(既有行為的 lock,非紅測):N121 accum gate 前提、N262 兩腿都在的對照組、
N108 三個不誤報案、N119 useBreadth 兩格 last_minute(該支本來就用 functional updater)、
N265 直接點 radio 本體。

## 3. 完成前 gate(全綠)

| 指令 | 結果 |
|---|---|
| `npx tsc -b`(frontend/) | PASS(exit 0,無輸出) |
| `npx vitest run`(frontend/) | **140 files / 2656 tests passed** |
| `npx eslint src`(frontend/) | PASS(無輸出) |
| `npx react-doctor@latest --scope changed --no-telemetry` | **No issues found**(第一輪曾出 2 個新增 `js-combine-iterations` → `7fb796e4` 修掉) |
| `.venv\Scripts\python -m pytest -q`(repo root) | 2913 passed(後端零改動,回歸確認) |

⚠ flake 記錄:全套第一次跑時 `App.test.tsx` / `App.memo.test.tsx` 各有一條 `waitFor` 逾時
(兩次跑到的還不是同一條),單獨重跑與後續兩次全套皆 100% 綠 —— 屬既有的 App 級整鏈
timing flake(與本輪改動無關:兩條斷言的內容分別是右欄葉子換股與 capital WS 單一連線)。

## 4. 白名單(既有行為)逐條核對

| # | 既有行為 | 核對方式 | 結果 |
|---|---|---|---|
| W1 | TickTape 前插時 DOM node 恆等 | 既有恆等案未改動 | PASS |
| W2 | ticks 上限 200 / VP 折全量 | `keeps tick tape bounded to latest 200 rows`、`fromSnapshot 對原始全量 ticks fold` | PASS |
| W3 | onInteract 點已選中 / 停用不發 / onChange 語意 | 既有三案未改斷言內容(只收緊次數) | PASS |
| W4 | 重疊兩腿都在時的線色 / 標籤 / 幾何 | `各線相對各自 ref 的 % 共域`、`ref null 的線被略過` + 新增對照組 | PASS |
| W5 | 兩支 hook 的 merge 契約 | `useIndexStream` 9 / `useBreadth` 12 案全綠 | PASS |
| W6 | 四態分時圖 toggle 列版面 | N008 新案鎖 class / disabled / aria-pressed / 顆數 / 字數全同 | PASS |
| W7 | toast 文案與 TTL / 合併行為 | `useSignalAlerts` 全案未改、ToastStack 只加 class | PASS |
| W8 | wsStatus closed 的「伺服器連線中斷」 | `伺服器斷線顯示重連告警列(文案不變)` | PASS |

## 5. 未做 / 留尾(交還 user)

1. **N109 真分態需後端**:`tc4:"down"` 的兩個來源(engine 在但 TC4 斷 / 無 engine 模式)
   在前端沒有可分辨訊號 —— `app.py:1822` 的 seed 與 engine 發的 status 形狀逐值相同,
   `/api/health` 刻意不含引擎健康度。本輪走「一句對兩態都誠實」;要真分態得在 seed 加欄位
   (後端檔,R3 外)。
2. **N108 判別子是啟發式**:用「加權已有 ≥2 分鐘格而櫃買整片空」推斷 MIS 死透。
   真環境沒看過反例,但它推的是相關性不是因果 —— 若哪天櫃買改由別的來源餵,要回來重看。
3. **畫面待 user 過目**(prod build 後):
   - 群組 → 單檔切換那一瞬,分時圖 toggle 列的「載入中」佔位(是否不跑版、是否看得懂);
   - tc4 斷線告警列的新文案長度(單行是否過長);
   - 櫃買 pane 的「櫃買快照源中斷」(真環境要等 MIS 真的壞才看得到);
   - toast 合併文案 clamp 2 行的觀感。
4. **N120 的號在回補後整段平移**(`apply_backfill` 讓 seq 跳增 +1000):key 仍單調唯一,
   但那一次全量 refetch 之後明細會整片重掛一次 —— 與改前同級,不是新問題。
