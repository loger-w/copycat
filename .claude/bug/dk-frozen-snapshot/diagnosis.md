# /bug DK 同 session 同窗口重查回凍結快照 —— 診斷紀錄(2026-09-01)

Handoff:`%TEMP%\copycat-handoff-2026-09-01-dk-frozen-snapshot.md`;prod 實錄證據見
memory `futures-daily-cache-final-boundary-shipped` 09-01 節。

## Phase 1–2:紅迴圈(受控 TCPY probe,已跑紅)

指令:`.venv\Scripts\python .claude/bug/dk-frozen-snapshot/evidence/dk_frozen_probe.py --gap-secs 150`
(需 TC4 開著 + 交易時段;自己的 session、窗口 start=today−30d ≠ prod 的 −1825d/−180d,天然不同 key)

2026-09-01 16:33–16:36 實跑(TC4 session 15:50 起,TXF 夜盤,`evidence/dk_frozen_probe_1.json`):

| 臂 | 查法 | 09-02 bar(末根) | 判定 |
|---|---|---|---|
| W1 16:33:04 | 同窗首查 | v=7875 c=46897(elapsed 0.30s) | 基準 |
| W2 16:35:34 | **同窗重查** | v=7875 c=46897 **逐字節同**(elapsed 0.001s;重送 SUBQUOTE 回 `Fail`) | **凍結(紅)** |
| V1 16:35:34 | **start −1 日 variant** | v=8138 c=46895(elapsed 0.30s) | **前進 → 逃逸成立** |
| U1 16:35:35 | UNSUB 後同窗重訂 | v=7875(SUBQUOTE 回 OK) | **UNSUB 不逃逸** |

行情對照:同 150 秒 TXF 夜盤成交 263 口 → 凍結不是「沒行情」。

## Root cause(機制定案)

TC4 QuoteZMQService 對 DK history 訂閱 key(symbol|DK|StartTime|EndTime)的內容**凍結在
key 建立時點**;同 session 同窗口重送 SubHistory + GETHISDATA 永遠回建立時點快照
(elapsed 0.001s = 端上快取直回),**UNSUB→重訂同窗也拿同一份**。逃逸維度只有
換窗口字串或換 session —— 與 1K「凍結 stub / 同窗口 cursor」家族同機制的 DK 版。

prod 症狀鏈:server 早上起 → boot 時 DK key 建立(今日 bar 進行中)→ 14:00 定稿界作廢
快照 → refetch 同窗(bars.py 的 start/end 整天不變)→ 拿回訂閱時點凍結值(非空、非
timeout)→ `daily_put` 界後寫入視為定稿 → 錯值釘到午夜。

### 附帶新事實(修正 handoff 旁證)

窗 end=0902 時 **09-02 夜盤 bar 已在**(16:33,夜盤開 1.5h)→ prod 15:16 新 session 看不到
09-02 bar 是 **窗 end=0901 的窗口排除**(DK 以交易日歸窗),不是「D+1 bar 幾小時後才出現在
新訂閱」。

## Phase 3:假說與修法(user 已在 /bug 指派方向)

機制已由受控實驗定案(非競態、非寫入 lag、非 cache 層 bug —— cache 層 10 條測試 + 3
突變體無病)。修法照 handoff §3:

1. **DK 每次取數帶窗口 variant**(選「每次都 variant」不選「僅定稿界後那一刷」:免從
   cache 層向下鑿參數,source 層自含;成本 = 熱取數 0.001s → 0.3s,可忽略):
   - 產生點:`tc4.py` 基底新 helper `_dk_start_variant(sym, start, end)` —— per
     (sym, start, end) 單調計數,第 n 次取數把 start 日期前移 n−1 日(首查 = 原窗,行為不變;
     新的一天窗字串本來就換 → 計數天然按日重置)。變體維度 = start 日期(probe V1 實證);
     end-hour 維度未驗且一天只有 24 值會繞回,不用。
   - 消費點:`futures_source.fetch_bars_range` D 分支、`stock_source.fetch_bars_range_tagged`
     D 分支、`stock_source.fetch_daily_bars` —— 三處都經 `_collect_history(sym, "DK", …)`。
   - 「含端點」契約保持:parse 後把 `t < start_date` 的頭部多收 bar 過濾掉(variant 對 caller
     完全不可見)。
   - 已知殘餘(記帳不修;spec review #3 校正距離):不同 base 窗 variant 後字串理論上可撞
     (個股 40 日與 180 日窗差 **140** 日,需同 sym 同日 140 次取數)—— 撞上的代價 = 拿到
     幾小時前的快照,且有訊號 2 兜底。序號刻意不設上界:上界 = 字串重用 = 凍結復發,
     且空結果 retry 正是靠換窗才有意義。
2. **「refetch 成功但值未前進」WARNING**(`server/bars.py`):refetch 後今日 bar 與作廢前
   墊背快照逐字節同 → 固定字串 log(grep 錨「值未前進」)。冷門股午後真零成交會誤鳴,
   字面用「疑似」;頻率 = 每次 refetch 一行,日 K refetch 稀疏。
3. 收尾:tc4-market-facts 補 DK 凍結條(含 UNSUB 不逃逸 + 窗口排除新事實)。

## Phase 5 seam

- `tests/live/test_futures_bars.py` / `test_stock_bars.py`:`sent` 捕獲 SUBQUOTE —— 同參數
  第二次 fetch 的 StartTime ≠ 第一次(紅先行)。
- `tests/server/test_bars.py`:凍結情境(界前寫入 → 過界 → refetch 回同值)→ caplog 命中
  「值未前進」;對照(值前進)→ 不鳴。
