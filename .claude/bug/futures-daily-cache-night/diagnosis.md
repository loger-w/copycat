# /bug 期貨日 K 後端 daily cache 夜盤段是早上快照 — 診斷

來源:handoff `%TEMP%\copycat-handoff-2026-08-31-daily-bars-siblings.md` §2(pr-151-review 留尾;
`frontend/src/lib/day-bars-rollover.ts:39` 明寫「那一段留 next-time」= 本條)。
分支 `fix/futures-daily-cache-night`(worktree `../copycat-wt-daily-cache-night`)。

## Phase 1–2 feedback loop(紅迴圈)

指令(worktree,0.31 s,確定性):

```
C:/side-project/copycat/.venv/Scripts/python -m pytest tests/server/test_bars.py -k morning_snapshot -q
```

`TestDailySnapshotFinality::test_period_morning_snapshot_not_served_after_close`:
09:00 首抓(今日 bar 只有夜盤那截 c=100)→ 牆鐘翻 22:00、fetcher 已有定稿 c=200 →
`build_period` 仍回 100。**RED:`assert 100 == 200`**。

最小化:兩根 bar、兩次呼叫、`_now_time` 翻一次;拿掉任一元素即綠(翻鐘不翻 → 本來就該 memo;
不給第二份 fetch → 無從斷言;單根 bar → 同構)。紅在 user 症狀本體:「收盤定稿後問到的仍是
早上快照」——15:01 錨定日翻頁後 `futures-overlay.ts` 拿部分 bar 當 CDP/MA 基準即此症狀的下游。

## Phase 3 假說(排序;user AFK,依 diagnosing-bugs 規則以自排序續行)

1. **H1(結構上已證實 + 紅測試命中)**:`BarsCache._daily` memo 鍵 `(f"{code}|L", today)`、
   `prune` 只清別天、無任何日內失效 → 界前(今日 bar 進行中)寫入的快照釘到午夜。
   預測:給「界前快照」加日內失效 → 紅測試轉綠。
2. H2(排除):前端不重抓 —— 是共犯不是根因;`day-bars-rollover.ts` 刻意選午夜界正因後端
   15:01–24:00 問了也白問。後端修好後 F5 / 新掛載即正確;前端 15:00 界屬後續 /mod(見 next-time)。
3. H3(排除):TC4 DK 本身回舊資料 —— 無證據;紅迴圈用 fake fetcher 已把 TC4 隔離在外,
   memo 層單獨重現症狀。

## 修法候選(handoff §2 三案)與拍板

- (a) 「末根 == today」短 TTL 30 s:盤中每 30 s 重付一次 DK 取數(index overlay 雖 staleTime
  Infinity,但任何掛載/失效輪詢都會打),而盤中重抓拿回的仍是部分 bar —— 純付費不治病。
- **(b) 定稿界一次失效(採)**:界前寫入的快照過 `DAILY_FINAL_TIME`(14:00)即作廢一次;
  界後寫入視為定稿。成本 = 成功路徑上界每 code 每天一次 DK 取數;refetch 失敗窗(TC4 關/忙)
  沿 `EMPTY_TTL_SECS` 節奏重試至成功,與既有空態自癒同級(review S-7 改寫)。14:00 晚於全部
  日盤收盤(現貨 13:33、期貨 13:45)留 TC4 寫入寬限,早於 15:00 錨定翻頁(消費者最早需要點
  15:01)。handoff 原建議 13:46;放寬到 14:00 因 TC4 DK 定稿寫入時點未實測,而 13:46–14:00
  之間唯一代價是「盤後立刻 F5 的人晚 14 分鐘看到定稿」(前端 staleTime 到午夜,常態不會再問)。
  handoff 原句候選 (b) 的「(交易日曆 `trading_calendar`)」**刻意拿掉**(review S-3 知情):
  掛日曆省的只是休市日每 code 至多一次白刷(且前端常態不會發第二個請求),卻要背
  trading_calendar 的檔缺 / 缺年退化路徑 —— 純牆鐘的失效方向安全(多刷一次,不會少刷)。
- (c) 期貨 tf=D 不走 memo:index overlay 失效態 60 s 輪詢會每分鐘重付 DK deadline,否決。

附帶決策:**過期後 refetch 拿空手(TC4 關/忙)→ 墊背回舊快照**(`daily_stale`)。
不墊背的話,本修會把「盤後 TC4 關著」(已知常態,handoff §1 判準第 6 條情境)從
「顯示早上快照」變成「整片空白到午夜」—— 沒消息不可蓋掉舊消息。status/tag 誠實:
墊背回應帶 fetch 實際的 status(build_daily)/ 舊 tag(build_period),不洗白。

## Blast radius(caller map)

`daily_get/daily_put` 僅兩個讀者:`build_period`(`/api/market/bars` D/W/M + `/api/index/overlay`)
與 `build_daily`(`/api/stock/bars` tf=D)。同一結構同病(個股日 K 夜間 F5 同樣拿早上快照),
修在 cache 層一次治好;個股面成本同上界(每 code 每天一次)。`build_minute` 走 `_hist/_today`
不經此層,分 K 路徑逐字不變。前端三支日 K hook 行為不變(它們本來就到午夜才再問)。
