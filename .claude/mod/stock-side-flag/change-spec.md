# /mod 個股內外盤改讀達錢旗標 — change-spec(2026-09-15 grilling 定案)

小活分流:不開 GitHub spec / tickets issue。前置盤點與實測數字見同目錄 `current-state.md`(§1 caller map、§3 白名單、§4–5 事實)。

## 1. 目標與範圍

**做**:
1. 即時 REALTIME 的個股內外盤改以 `FlagOfBuySell` 為準:`"1"` → `inner`、`"2"` → `outer`;`"0"` / 欄缺 / 其他值 → 退回現行同則簿比 `derive_side(price, bid0, ask0)`。
2. 每日一行可觀測 INFO:`個股旗標 0:n 筆 / 欄缺 k 筆 / 總 m 筆(<交易日>)`,追蹤達錢到底給不給中立(user Q1:「未來再看看」)。
3. 文件改述(skill / CONTEXT.md / CLAUDE §4 / next-time)。

**不做(user 拍板)**:
- 回補路徑零改動:歷史 TICKS 無旗標,維持同列簿比 + `relabel_locked_side`,判不出留灰。實測「前一列簿比先看」可把判得出 80.7% → 92.7%、錯 178 → 86 筆,user 拍板 **不做**(Q1 (c));零灰的正路 = 批 C tick 存檔後回補改讀自家存檔。
- 掃單首筆外盤判準不動(`_eval_sweep` 用 `price >= tick.ask_milli` 自比,不讀 side)。
- 前端零改動(side 三值 wire 不變)。
- 歷史 TICKS `TradeVolume` 恆 0 → `apply_backfill` survivors 全數重放的重複計量:**另開 /bug**(user Q2 (a)),本案只寫進 next-time。

## 2. 設計

### T1 `copycat/live/stock_models.py`(🔴 行為改動,單一產生點)
- `StockTick` 新欄 `flag: str | None = None`:原始 `FlagOfBuySell` 字串(`"0"|"1"|"2"`;欄缺 / 空字串 → None;歷史列恆 None)。有 default → 16 處 keyword 建構點不動。**不上 wire**(`snapshot()` / 打包 item 不加鍵)。
- `parse_stock_realtime`:`flag = msg.get("FlagOfBuySell") or None`;`side = _FLAG_SIDE.get(flag) or derive_side(price, bid0, ask0)`,其中 `_FLAG_SIDE = {"1": "inner", "2": "outer"}`(模組級,唯一對映)。`bid_milli` / `ask_milli` 照存(TickTape 顯示用)。
- `parse_hist_tick`:不改邏輯,`flag=None`。
- docstring 改述:`StockTick.side` = 即時以旗標為準、回補以同列簿比;`bid_milli/ask_milli` = **成交後簿**(09-14 實測,見 current-state §4)。`derive_side` docstring 註明「旗標退路 + 回補路徑」。
- 期貨 / corr 共用同函式:期貨訊息有旗標會照讀,但兩個引擎都不讀 `side` → 無行為差;欄缺退回現況。

### T2 `copycat/server/stock_engine.py`(🟢 可觀測,零判定)
- 現貨 tick 在 `_handle_quote` 的 `ingest` 為真分支計數(`is_futures_key` 跳過;試撮 / 重複已被 ingest 短路):`_flag_stats = {"total": 0, "zero": 0, "missing": 0}`。
- 印出點兩處(同一個 helper `_log_flag_stats(day)`):`_rollover_stage2` 在 `reset()` 迴圈**之前**(帶舊 `_trade_date`),與 `close()` 開頭(帶當前 `_trade_date`)。印完歸零。**零筆也印**(判準是「那行存在」,不是數字)。
- 格式固定字面:`個股旗標 0:%d 筆 / 欄缺 %d 筆 / 總 %d 筆(%s)`。`/api/health` 不含。

### T3 文件(chore)
- `.claude/skills/tc4-market-facts/SKILL.md`:
  (a) 「同毫秒群 = 掃單」條:「首筆外盤判準 … 與 `tick.side` 在 prod 等價」→ 改為「**2026-09-15 起不等價**:`tick.side` 即時讀旗標;掃單仍用同列 `ask_milli`(成交後簿)價格比較,吃光整檔的主動買會判非外盤,留給策略 session」。
  (b) 新條「**個股 REALTIME 帶成交的那則,五檔是成交後簿**」:09-14 6,320 筆,同則簿 `derive_side` 對旗標 78.5% / 前一則訊息簿 100%;`FlagOfBuySell` 1=內 2=外 0=無法判斷(去重 0.02%);鎖跌停 5314 市價佇列列旗標全 outer = 恆等式;歷史 TICKS 無旗標、`TradeVolume` 恆 0、Bid/Ask 同為成交後簿;回補規則對帳表(current-state §5)。
  (c) §鎖漲跌停 那段「另一層 … 靠 relabel_locked_side」不動。
- `CONTEXT.md` 市場資料語意加三條:**外盤**(買方主動,成交在賣一;即時 = 達錢旗標 2)、**內盤**(賣方主動,成交在買一;旗標 1)、**內外盤旗標**(`FlagOfBuySell`;0 = 達錢判不出,留灰;歷史 TICKS 無此欄 → 回補以成交後一檔簿比,判不出留灰;_Avoid_:拿同則五檔當成交前簿)。
- `CLAUDE.md §4` 一條:「個股 `side` 產生點 = `parse_stock_realtime` 旗標對映 `_FLAG_SIDE`,退路 `derive_side`;回補 `parse_hist_tick` 只有退路;讀者不變;漂掉症狀 = 判定率說明列回到 ~80%、盤後 log 無『個股旗標 0』行」。
- `docs/next-time.md` 新節 2026-09-15:(1) /bug 候選「歷史 TICKS `TradeVolume` 恆 0 → survivors 全重放、回補重疊窗 1–3 s 重複計量」(證據 current-state §5 事實 A);(2) 09-16 08:59 排程抓檔 `copycat-flag-capture-0916` 結果:集合競價首筆 / 試撮期旗標值 → 只改文件;(3) 「前一列簿比先看」+12 點的選項已拍板不做,批 C 後為死碼,勿重提。

## 3. 測試(seam = `parse_stock_realtime` 純函式 + engine rollover log;🔴 紅先行)
`tests/live/test_stock_models.py`(既有 `REALTIME_MSG` 無 `FlagOfBuySell` → 現有斷言 `side == "inner"` 照過 = 退路相容,**不改**):
1. flag `"2"` 且簿判 inner(2380 貼 Bid)→ `side == "outer"`、`flag == "2"`(旗標壓過簿)。
2. flag `"1"` 且簿判 outer → `inner`。
3. flag `"0"` → 走 `derive_side`(同樣本 → `inner`),`flag == "0"`。
4. 欄缺 / `""` → `flag is None`,side 同現況。
5. `parse_hist_tick` → `flag is None`。
6. 真實列 golden:09-14 raw 抓檔取 3 則(旗標 2 但同則簿判 inner 的 2426、旗標 1 但簿判 outer 的 1312、鎖跌停 5314 Ask=0)進 fixture,斷言 side 跟旗標。
`tests/server/test_stock_engine.py`:
7. 三筆現貨 tick(flag 2 / 0 / None)ingest 後 rollover stage2 → caplog 一行 `個股旗標 0:1 筆 / 欄缺 1 筆 / 總 3 筆(<舊日>)`,且之後計數歸零;`close()` 也印。零筆仍印。
8. 期貨鍵 tick 不計入。

## 4. 既有行為白名單(two-axis review 兩個 sub-agent prompt 必附)
current-state §3 全文;另加:`REALTIME_MSG` 既有斷言不改(退路相容的證據)、`snapshot()` / 打包 item 鍵集不加 `flag`、`/api/health` 不加欄、回補 / survivors / seq 語意零改動。

## 5. 驗證
- gate:`pytest -q` + `ruff` + `pyright` + `copycat validate`(後端);前端零改動不跑 npm gate(dist 不用 build)。
- 真實環境(重啟後第一個交易日;本案 dist 不變,只重啟 server):
  1. 09:30 後 `curl /api/stock/state/<自選熱門股>` → 回補段之後(自訂閱起)的 `ticks[].side` neutral 比例 ≈ 0;整體判定率說明列 ≥ 95%。
  2. 盤後 `grep "個股旗標 0" logs/server-<日>.log` 一行,`0:` 桶接近 0、`欄缺` 桶 = 0(非 0 = 達錢格式漂了)。
  3. `grep 佇列滿` 仍 0;掃單簇 / 政策列 jsonl 照常(掃單不讀 side,對照 09-15 同時段筆數量級)。
  4. 白名單逐條:VP 兩色、外盤比、能量副圖有值;鎖停股(若當日有)回補段仍靠 relabel 上色;TickTape b/a 欄照舊。

## 6. commit 切法
🟢 `test(live,server): 個股旗標 side 紅先行` → 🔴 `fix(backend): 個股內外盤改以 FlagOfBuySell 為準,0/缺欄退回簿比` → 🟢 `feat(backend): 換日 / 關機印當日旗標 0 計數` → `chore(docs): skill / CONTEXT / CLAUDE §4 / next-time`。分支 `mod/stock-side-flag`(worktree),收尾鏈 closeout.md。
