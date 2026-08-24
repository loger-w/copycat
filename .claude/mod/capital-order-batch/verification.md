# R6 群益下單批 — verification

分支 `mod/capital-order-batch`(自 master `9a5b5ef6` 切出)。12 條全部落地,**零未做**。

---

## 1. commits(6,三類不混)

| # | sha | 類 | 內容 |
|---|---|---|---|
| 1 | `381b8e8c` | 🟢 test(backend) | N017/N018/N075/N098 紅測試 + N082 lock |
| 2 | `dc37dffb` | 🔴 mod(backend) | 欠帳逐筆到期 / collector 具名與 `clear()` / 夜盤交易日候選 / 平倉 tick 閘 |
| 3 | `0bd0de14` | 🟢 test(frontend) | N011/N014/N065/N080/N081/N082/N099 紅測試 + N073 lock |
| 4 | `320d0794` | 🔴 mod(frontend) | 七條行為改動 |
| 5 | `dbb62436` | 🔵 refactor(frontend) | `futCloseEstimate` 註解改口(N014-1,comment-only) |
| 6 | `bbf46383` | 🔵 refactor(frontend) | `stkfutClosePriceOf` / `armGate` 抽 module 層(react-doctor 新增 finding 的修法) |

**只 commit,未 push、未建 PR、未跑任何 `gh`。**
工作樹裡 `.claude/skills/ops-discipline/SKILL.md` 的他 session 未提交修改**全程未碰**
(`git status` 確認仍為 ` M`,不在任何一個 commit 的 path 內)。

---

## 2. 紅態證據(TDD:先紅再綠)

### 後端(commit 1 之後、commit 2 之前)

`.venv\Scripts\python -m pytest -q` → **23 failed, 2926 passed**(master 基線 2926 = 2920 + 本輪 6 條
一開始就綠的 lock)。逐條:

| 條 | 紅的測試 | 紅態訊息(節錄) |
|---|---|---|
| N017 | `test_collector_expired_debt_does_not_ride_on_a_later_abandon` | `assert got == [[]]` 得 `[]` —— 過期欠帳搭新欠帳的便車,合法空回應被多吞一次 |
| N017 | `test_collector_debt_deadlines_expire_independently` | 同上 |
| N018-1 | `test_swallowed_terminator_warning_names_the_collector` | `TypeError: BalanceCollector.__init__() got an unexpected keyword argument 'name'` |
| N018-2 | `test_clear_does_not_mark_awaiting` | `AttributeError: 'BalanceCollector' object has no attribute 'clear'` |
| N018-2 | `test_set_status_ok_does_not_leave_collectors_awaiting` | `assert (934291.69, 1) == (None, 0)` —— `reset()` 讓三段變 awaiting,watchdog 一 abandon 就記帳 |
| N018-3 | `test_no_futures_account_clears_oi_abandon_debt` | 旗標與欠帳殘留 |
| N075 | `TestTradeYmd`(6 條) | `AttributeError: module 'copycat.capital.client' has no attribute '_trade_ymd'` |
| N075 | `test_note_price_type_records_trade_date` | 同上 |
| N075 | `test_price_type_*_night_session` / `prune_keeps_overlapping`(4 條) | `TypeError: note_price_type() got an unexpected keyword argument 'trade_date'` |
| N075 | `next_trading_day`(5 條) | `AttributeError: 'TradingCalendar' object has no attribute 'next_trading_day'` |
| N098 | `test_stkfut_close_illegal_tick_rejected` | `assert 200 == 400` —— 非法檔位 1180.5 的個股期平倉照樣送到群益 |

### 前端(commit 3 之後、commit 4 之前)

| 條 | 紅的測試 | 紅態訊息(節錄) |
|---|---|---|
| N011 | `N011:市價態換到無估價合約 → 維持市價 + 送出鈕鎖定…` | `expect(market.checked).toBe(true)` 得 `false`(被靜默翻回限價) |
| N014-2 | `落點未變的 pointermove 不重繪` | `expected 8 to be 10`(3 則同落點 move = 3 次整欄重繪) |
| N014-4 | `拖曳中移入作廢帶 → 高亮改虛線且被拖的列更淡` | 找不到 `border-dashed` / `opacity-30` |
| N065 | `有反查不到的 fut 倉位 → 側欄底一行計數` | `Unable to find an element with the text: 2 筆個股期倉位無法對映` |
| N065 | `unmappedFutCount`(6 條) | `unmappedFutCount is not a function` |
| N080 | `子樹在 keydown 上 stopPropagation 時,Esc 仍解除武裝` / 鎖定態同理 | `armed` 仍為 `true` |
| N081 | 三梯各 1–2 條 | `expect(arm.hasAttribute("disabled")).toBe(true)` 得 `false` |
| N082 | `flashSource`(2 條) | `flashSource is not a function` |
| N082 | 三梯各 1 條 | `expect(bodies[1]?.source).toBe("flash-locked")` 得 `"flash"` |
| N099 | `ETF 期貨腿的平倉估價回 null` / 除權息調整單位 | 平倉鍵 `disabled` 為 `false`(拿現股 tick 表 snap 了一個不適用的檔位) |

### 兩條 lock 的 mutation 驗證(寫完即綠 → 必須證明它會紅)

- **N073**(`StockIntradayChart.memo.test.tsx`):把 `EMPTY_MARKS` 換成行內 `[]` → **紅**
  (`1 failed | 1 passed`),還原後綠。
  ⚠ **第一版是假 lock**:原本用「hover 讓父層重繪 → 斷言 ChartStatic 計次不動」,mutant 全綠 ——
  因為 hover 不動 `useMemo` 的 deps,`[]` 也被快取擋住。真正的鑑別力在**deps 會變**的那一半
  (`fills` 換 identity),改成 rerender 不同 `fills` 陣列後 mutant 才殺得掉。同輪教訓:
  memo 計次 lock 要先想清楚「目標 mutant 到底在哪個路徑上被觀察得到」。
- **N014-2**(`WatchlistSidebar.dragrender.test.tsx`):把 `p.to === to && p.voided === voided ? p : …`
  改回無條件造新物件 → **紅**,還原後綠。
- **N014-3**(邊價等值 ×2)與 **N082 後端 route→審計檔**:寫完即綠,是 lock 不是 fix
  (後端 `source: str` 值域本就可擴;邊價同值本來就成立,缺的是機械閘)。

---

## 3. 完成前 gate(全綠)

### repo root

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | **2949 passed**, 1 warning, 168.60s | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | `All checks passed!` | 0 |
| `.venv\Scripts\python -m pyright` | `0 errors, 0 warnings, 0 informations` | 0 |
| `.venv\Scripts\python -m copycat validate` | **42/42 PASS** | 0 |

(master 基線 2920 passed → +29 條:後端新增 23 紅測試 + 6 條 lock。)

### frontend/

| 指令 | 結果 | exit |
|---|---|---|
| `npx tsc -b` | 無輸出 | 0 |
| `npx vitest run` | **144 files / 2742 tests passed** | 0 |
| `npx eslint src` | 無輸出 | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | `Scanned 24 files` → **No issues found!** | 0 |

(master 基線 142 files / 2710 tests → +2 檔 / +32 條。)

**react-doctor 的 before/after 比對**(baseline 檔已過時,故用同分支 vs master 實測):

- commit 4 之後 `--scope changed` 報 **2 個新增 finding**:`no-giant-component` 於
  `RightRail.tsx:87` 與 `StkfutLadder.tsx:77`。
- 以全量掃描交叉驗證「是不是存量」:當前樹的 `no-giant-component` 有 9 處;把**這兩檔**
  換成 master 版本後重掃只剩 7 處 → 兩者確為**本輪新增**(不是存量),依 gate 屬 FAIL。
- 修法 = commit 6 的兩支 module 層純函式(不是調 config、不是 suppress)。之後
  `--scope changed` 回到 `No issues found!`。

---

## 4. 白名單逐條核對(§0 的表)

| # | 白名單項 | 核對方式 | 結果 |
|---|---|---|---|
| W1 | 總開關 `CAPITAL_ORDER_ENABLED` | `safety.py` diff 為空;`test_safety.py` / `test_capital_api.py` 的 disabled 案全綠 | 不變 |
| W2 | `MAX_QTY` / `MAX_AMOUNT` | `safety.py` diff 為空 | 不變 |
| W3 | `_bad_price`(NaN / ≤0) | 同上 | 不變 |
| W4 | `_require_legal_tick` | 只**新增**第三個 caller(close route);`_stkfut_gates` / `_correct_price_tick_gate` 逐字未動(diff 確認) | 只增不減 |
| W5 | `PRODUCT_NOT_ALLOWED` | `_is_tickable_stkfut` 逐字未動;`TestOrderStkfutGates` 全綠 | 不變 |
| W6 | 二次確認窗 | `CapitalConfirmDialog.tsx` **零 diff**;`CapitalConfirmDialog.test.tsx` 全綠 | 不變 |
| W7 | 清除路徑寬於進入路徑 | `reduceArm` 零 diff;`ArmRow` 的 `armDisabled && !armed` 零 diff;新增測試「已武裝後 WS 轉 connecting → 解除鈕恆可按」×3 梯 | 不變(且新測試釘住) |
| W8 | 每筆 req/res append-only 審計 | `_record` / `_audit_blocked` / `_audit_after` / `_on_late_result` 零 diff;新增 route→審計檔端到端 lock ×2 | 不變 |
| W9 | 雙環境隔離 / env banner | `factory.py` / `status_view` 零 diff | 不變 |
| W10 | 平倉去重鎖 | `close_position` 零 diff(N098 的閘在 route 層,更早) | 不變 |
| W11 | 「估不出價 → 平倉鍵鎖住」 | `futCloseEstimate` 的 ≤0 守門逐字未動;N099 只**多一個**回 null 的理由 | 只增不減 |
| W12 | `marketButtonState` 三態 | 零 diff | 不變 |
| W13 | `isOrderBlocked` | 零 diff;多一個讀者(平倉估價) | 只增不減 |
| W14 | 欠帳窗語意(每個 `##` 消耗一筆 / rows 不動欠帳 / `_awaiting` 守門 / 窗外作廢) | 既有 9 條 `test_balance.py` 欠帳案**零改動**全綠 | 語意保留 |
| W15 | `_stale_until` / `_owed` 觀測窗 | 改成唯讀 property;既有 5 支測試的斷言零改動全綠 | 相容 |
| W16 | `reset(keep_abandoned=True)` | 三段呼叫點零 diff | 不變 |
| W17 | 價格別 fail-safe 方向(只缺標籤、不誤標) | 新比對集合是舊行為**超集** + 只多一個有語意根據的日子;`test_price_type_still_rejects_unrelated_day` 明確釘住「昨日仍不帶」 | 不變鬆 |
| W18 | `OrderRecord.unit` 字面值 | `_to_record` 的 unit 分支零 diff | 不變 |
| W19 | `positions` 的 `code` 衍生欄 | route 零 diff(N065 不加 wire 欄) | 不變 |
| W20 | `positionsByCode` 跳過 code null | 零 diff | 不變 |
| W21 | 作廢落點高亮回來源組 | `move` 的「三種 null 走同一條」語意逐字保留(只多一個 `voided` 旗標與 identity 短路);兩條既有測試的**負向**斷言未動 | 不變 |
| W22 | `EMPTY_MARKS` 等模組常數 | `fill-marks.ts` / `StockIntradayChart.tsx` **零 production diff**(N073 只補測試) | 不變 |
| W23 | 窗內 `stopPropagation` | `CapitalConfirmDialog.tsx` 零 diff(N080 改的是 window 監聽相位) | 不變 |

**真錢紀律**:全程零真送單、零真登入;所有測試走 `tests/conftest.py` 的憑證中和 + `FakeCom`;
未新增任何會打群益正式環境的腳本;`.env` 未讀未寫。

---

## 5. 判定型決定(review 請重點看這幾條)

1. **N075 選交易日口徑、不選 ±1 日窗**,且以「本機日 + 交易日兩個候選」的加法形式落地。
   理由全文在 change-spec §1 N075 —— 一句話:±1 會多接受「昨日」,而那正是 seq 重用**誤標**
   的方向;交易日口徑產生的日期恆落在前端 `ymdWindow(±1)` 之內,兩邊不衝突。加法形式是
   為了不拿「回報日到底是本機日還是交易日」這個**未實證**的假設去換掉一個現在可能有效的比對。
2. **N065 不加後端 `code_missing` 欄**,改在前端就地數 —— `code: string|null` 已在 wire 上,
   再加聚合欄是同一事實兩個來源。
3. **N080 改 `useFlashArm` 的監聽相位,不動確認窗**的 `stopPropagation` —— 動窗會牽動 4 個
   caller 的所有 Esc 語意(含非武裝態),blast radius 大得多。
4. **N073 判定「做得出來」而非沿用 cr1 的 rejected** —— 可計次探針不在 `fill-marks`
   (關態確實沒有),而在 `ChartStatic` render body 的 `buildVwapLabel`。
5. **N081 的 setup 連鎖**:四個測試檔的 `beforeEach` wsStatus 預設 `connecting → open`。
   這是**前提**變更不是期望變更,既有斷言逐字未動;要驗連線閘的案自己設 `connecting`。
6. **commit 6 的 refactor 是 gate 驅動的**,不是順手改:react-doctor 新增 finding 屬 FAIL,
   修法選「把純函式搬到 module 層」而非調 config / suppress。

---

## 6. 未做 / 留尾

**未做:無。**12 條全部落地(含條文寫「另案」的 N080 與 cr1 曾 rejected 的 N073)。

留尾(寫進清單、本輪不動):

1. `store._price_types` 的 prune 規則改成「候選集合不相交才刪」後,**理論上**同一交易日
   跨兩個本機日的項會多留一輪(上限 = 該日送出的單數)。實務量級極小(一天幾十筆),
   但若日後 server 長跑到跨週,值得量一次 dict 大小。
2. `_trade_ymd` 的夜盤時段界寫死 15:00 / 05:00(不是精確的商品交易時間表)。
   多算 / 少算一小時的後果只有「標籤缺一個字」,但若日後有商品在 14:xx 收盤後仍可下單,
   這條要跟著商品表走。
3. N098 對 **ETF 期貨 / 除權息調整腿的平倉**仍是後端放行分支(與改價面同一條逃生口),
   守門只剩前端 N099。要真正收掉需要「哪些單位算股票期貨」的權威來源 —— 與
   `_STOCK_FUTURE_UNITS` 的 Known Risk 同一件事。
4. `RightRail.tsx` / `StkfutLadder.tsx` 已貼著 `no-giant-component` 門檻,下一次動這兩檔
   大概率會再被標;真正的解法是把 `positionsContent` / 梯身各自拆檔(獨立 /refactor)。
5. `unmappedFutCount` 目前只在**側欄**顯示。單檔 header 與群組卡同樣會靜默跳過那幾筆,
   要不要各補一行,等 user 看過側欄那行的觀感再決定。

---

## 7. 需 user 過目(prod / 真環境)

畫面類(重 build + 重啟 8721 後):

- [ ] **OrderPanel(N011)**:TXO 面板選「市價」→ 換到無成交合約 → 市價 pill 應**維持選中**、
      送出鈕反灰並印「此合約尚無成交估價,市價暫不可送出」;換回有成交合約 → 鈕自動解鎖。
- [ ] **自選拖曳(N014-4)**:拖到側欄外 / 搜尋區作廢帶 → 來源組框應是**虛線灰**(不是實線橘)、
      被拖的列更淡。這是新的視覺語彙,要 user 確認一眼分得出「放開會取消」。
- [ ] **武裝鈕(N081)**:群益 WS 未就緒時,三座梯的**武裝鈕**現在也反灰並帶「連線未就緒,
      無法武裝」。要確認這不會在盤中正常連線抖動時擋到手感(connecting 一閃即過的窗)。
- [ ] **側欄底一行(N065)**:若當下有 `code` 反查不到的個股期倉位,側欄最底會多一行
      「n 筆個股期倉位無法對映」。**沒有那種倉位時看不到** —— 要驗得刻意持一口除權息調整腿。
- [ ] **平倉鍵(N099)**:ETF 期貨 / 除權息調整腿的部位,平倉鍵應**鎖住**(與該標的的送單面一致)。
      這是**收緊**:user 若原本靠它平過那類倉,現在得走群益 APP。**請確認這是要的。**

真環境 / 安全首單類(有真錢或需盤中窗口):

- [ ] **N082 稽核**:鎖定態送一筆最小單位單,確認 `capital-YYYYMMDD.jsonl` 的
      `req.source == "flash-locked"`(未鎖定仍是 `"flash"`)。屬「安全首單」類,需 user 親做。
- [ ] **N098 平倉檔位閘**:標準個股期部位,故意用不合檔位的價按平倉 → 應回 400 `BAD_TICK`
      而不是送到群益。正常路徑(前端 `edgeOf` 已 snap)打不到,要驗得繞過前端估價。
- [ ] **N075 夜盤標籤**:夜盤(≥15:00)送一筆個股期 / 期貨**市價**單,次日確認委託列表
      仍帶「市價」標籤 —— 這是本條唯一能實證「回報的委託建立日到底是哪一種語意」的機會,
      請順手記下該筆的 `date` 欄。
- [ ] **N017 / N018 欠帳窗**:盤中觀察 `capital-com` 的 log —— 「忽略放棄輪遲到的終止符」
      現在會帶段名(`balance` / `profit` / `oi`)。若部位面板仍有「瞬清一輪」的樣態,
      該行的段名就是下一步的線索。

## 8. two-axis review round 1 收修(主 session)

| 項 | 處置 |
|---|---|
| ST1/SP1(P1)| `store.note_price_type` 綁 `stock_no` / `buy_sell`,`_price_type_of` 等值才帶出;`client._side_code`;三個 caller + `_on_late_result` 帶綁定;`test_store` 兩案(同 seq 不同標的 / 方向 → None;完全相符 → 帶出;None = 不綁)+ `test_client` N075 案補綁定斷言;三條既有 client 案的回報 fixture 股號改對上請求(`_stock_evt_raw(stock=)`,斷言不動) |
| SP3 | `closeBodyOf(pos, price, source?)` + FuturesLadder 鎖定態平倉帶 `flash-locked`;`close-order.test` 兩案 |
| SP2 | `useFlashArm.test` 真 dialog 端到端案 |
| ST5 | `MARKET_ESTIMATE_MISSING` 常數 |
| ST3 | import 清理 |
| ST2 / ST4 | 反駁(理由見 change-spec §4)|

**收修後 gate**:pytest **2951 passed** / ruff / pyright 0 / tsc / vitest **144 files 2745 tests** / eslint / react-doctor No issues。
