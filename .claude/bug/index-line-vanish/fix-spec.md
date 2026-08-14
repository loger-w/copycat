# fix-spec:指數分時自癒失效(heal 重抓拿窗外 stub 靜默空轉)

分流判定:已成形(root cause 已由活體證據 + 兩個受控實驗釘死;修法沿證據裁決,無方向性抉擇)。

## Root cause(摘自 repro.md)

1. TC4 1K GETHISDATA 對「空窗期建立的 history 訂閱」會回**窗外 stub 列**(實驗 B:對空的
   05-06 窗首問即回當下分鐘 bar)而非空頁 → `_collect_history` 首頁非空即 break,
   `timed_out=False`、rows=1 列垃圾,**零 log**。
2. `fetch_day_minutes` 對 domain 外列靜默丟棄 → caller 拿到空 dict 無從分辨。
3. `index_engine._retry_loop` 以「fetch 沒丟例外」當成功 → heal 宣告成功、退避倍增,
   **永遠重用同一個已毒化的 (session, symbol, 1K, 窗口字串) 訂閱**,全日不恢復。
   逃逸維度已實證 = 換窗口字串(08-13 同 session 00-23 成功)或換 session(probe)。

## 修改(三檔)

> [amendment 2026-08-14: code review round-1(L2-P1-1/L1-P1-1/L1-P1-2/L1-P1-3/L1-P2-2)]
> A 段整段撤除:窗過濾對 prod boot stub(stamp `<today>00` ∈ 00..06 窗)是 no-op —
> 本 repo 所有歷史窗 start hour = 00,今日 stub 恆在窗內;且它翻轉 bars 三態語意
> (L2-P2-5)。可視性改由 `fetch_day_minutes` 的 stub 簽名 log(A′)承接。C 段進展
> 判定由「絕對 lag」改為「fetch 前後新分鐘鍵差量」(頻凍結 stub 值漂不算進展);
> 部分進展仍送達前端;variant 恢復時不歸零(僅 `_swap_day` 歸零);封頂補分辨 log。
> 下方 A 節保留原文供 review 對照,**以本 amendment 與 A′/C′ 為準**。

### A′.(取代 A)`copycat/live/stock_source.py` `fetch_day_minutes` — stub 簽名可視性

- `_collect_history` **不動**(與 master 全等)。
- `fetch_day_minutes` 解析後:`rows` 非空但 `minutes` 為空(全數域外)→ log WARNING
  固定字串(如 `1K minutes:N 列全數域外(疑似凍結 stub)`)— 這正是毒化訂閱的簽名
  (boot stub Time≈08:00 → 域外),取代 A 段的 grep 訊號。

### C′.(修訂 C)進展 = 新分鐘鍵差量;variant 黏住;封頂 log

- `_subscribe_and_backfill` 回傳「本次 fetch 是否帶來**新分鐘鍵**」(値更新不算 —
  凍結 stub 的 Close 隨現價漂,以值判定會把 stub 誤判為進展)。
- `_retry_loop`(heal 型):有新鍵 → 視為有效:設 `_push_minutes_once`(pending
  守門同既有)+`_dirty`,variant **不**遞增(該窗口在產出,繼續用);無新鍵 →
  無進展:WARNING + `_heal_variant += 1` + 不設旗標 return。
- lag 恢復處只歸零 `_heal_interval`,**不歸零 `_heal_variant`**(0 號窗口可能已毒化);
  `_swap_day` 歸零 variant(新交易日窗口字串天然全新)。
- variant 遞增至封頂(6+v ≥ 23)時,log 一行獨立固定字串(階梯已用盡),與「無進展」
  可分。
- 連線類 retry(clear_stale=True)語意完全不變。

### A. `copycat/live/tc4.py` `_collect_history` — 首頁 ready-check 誠實化(已由 amendment 撤除)

- 新增窗內判定:row 的 `f"{Date}{Time 前兩碼(zfill 6)}"` 落在 `[start, end]`(字串比較,
  含端點)才算窗內;Date/Time 缺失或不可解析 → **保守視為窗內**(過濾只丟可證明窗外的列,
  防過濾自身 bug 丟真資料)。
- 輪詢 break 條件:首頁**含至少一列窗內列**;stub-only 頁視同未備妥,續輪詢到 budget
  用盡 → 既有 timeout 路徑(log 照舊),另補一行 log 註明期間曾見窗外 stub(可 grep)。
- 收割結果過濾掉可證明窗外的列(防昨日 stub 的 Time 落入今日 domain 汙染 minutes)。

### B. `copycat/live/stock_source.py` `fetch_day_minutes` — window variant 逃逸

- 簽名:`fetch_day_minutes(code, *, window_variant: int = 0)`。
- 窗口:start 不變 `{day}00`;end hour = `min(6 + max(window_variant, 0), 23)` →
  variant 每 +1 產生新窗口字串 = TC4 端全新 history 訂閱(逃出毒化態)。
- variant 0 行為與現行完全相同。

### C. `copycat/server/index_engine.py` — heal 進展判定 + variant 遞增

- `IndexSource` Protocol:`fetch_day_minutes(self, code, *, window_variant: int = 0)`。
- `_subscribe_and_backfill(variant: int = 0)` 傳遞 variant;boot/rollover/connection
  retry 一律 variant 0(行為不變)。
- 新增 `self._heal_variant = 0`;broadcast loop 的 heal 觸發把當前 variant 傳給
  `_schedule_retry(clear_stale=False, variant=...)`;lag 恢復處(`_heal_interval = None`)
  同步歸零 `_heal_variant`。
- `_retry_loop`:fetch 完成後,**heal 型(clear_stale=False)且 `_minutes_lag_exceeded()`
  仍成立 → 無進展**:log WARNING(固定字串 `index 分時自癒無進展`,帶 variant)、
  `self._heal_variant += 1`、**不設 `_push_minutes_once` / 不設 `_dirty`**、return
  (下一發由既有 heal 退避觸發,帶新 variant)。
- 連線類 retry(clear_stale=True)行為完全不變。

## SC(成功條件)

- **SC-1** heal 無進展不得宣告成功:fake fetch 恆回空時,廣播不得帶 `minutes` 鍵、
  log 出現 `index 分時自癒無進展`。驗證:`pytest tests/server/test_index_engine.py -k no_progress`(新測試)。
- **SC-2** 無進展的下一發 heal 必帶遞增 variant,variant N 首次回資料 → minutes 恢復 +
  下一則廣播帶 minutes 全量(#45 行為銜接)。驗證:新引擎測試(fake 記錄 variant,
  variant>=1 回資料)。
- **SC-3**[amendment 2026-08-14 改寫] `_collect_history` 與 master 全等(A 段撤除);
  `fetch_day_minutes` 對「rows 非空但全數域外」log stub 簽名 WARNING。驗證:
  `tests/live/test_stock_source.py` 新測試(stub 列 → {} + caplog)。
- **SC-6**[amendment 2026-08-14 新增] heal 部分進展(有新鍵但仍 lag)→ minutes 送達
  廣播、variant 不遞增;無新鍵(含 stub 值漂)→ 無進展、variant +1;lag 恢復不歸零
  variant、`_swap_day` 歸零;封頂獨立 log。驗證:引擎級新測試群。
- **SC-4** `fetch_day_minutes` variant 產生的窗口字串正確(variant 1 → end `{day}07`,
  variant 20 → 封頂 `{day}23`)。驗證:source 級測試斷言 SUBQUOTE/GETHISDATA 參數。
- **SC-5**(真實環境;驗證窗口 = 次一交易日早晨,或今日 13:30 前側車)prod 形狀:boot
  timeout 日,heal 應於首發或第二發(≤ ~09:07)恢復分時線;log 可見
  `index 分時自癒無進展` → 下一發成功。窗外降級:以真 TC4 側車重演(空窗訂閱毒化 →
  引擎 heal 逃逸)一次,截 log 為證。

## 不能破壞的既有行為(白名單)

1. boot / rollover / reconnect 的 retry 語意(single-flight、ConnectionError 退避、
   clear_stale 樂觀清除)— `test_start_connection_error_*`、`test_schedule_retry_single_flight`。
2. heal 節流與無進展退避倍增(T-2/T-5 lock)、heal 不清 stale(T-4)、尾窗 13:25–13:40
   續跑(T-3)、13:30 覆蓋即停(封頂)、開盤空 minutes 豁免。
3. 廣播 scalar-only 慣例;**成功** heal 下一則帶 minutes 全量一次(#45)。
4. `fetch_day_minutes` 解析規則(UTC+8、domain 0901–1330、clamp、skipped 計數 warning)。
5. bars 三態 status(timeout/ok)契約與 `tests/live/test_stock_bars.py` 全數。
6. rollover pending/swap 語意(T-1:pending 期間 retry 不帶 minutes 出去)。

## Edge cases

1. 假日/全日無資料:heal 恆無進展 → variant 一路 +1 封頂 23,每發皆honest timeout log;
   頻率受既有退避(cap 900s)約束,不新增 churn。
2. [amendment 2026-08-14: review L1-P1-1/P1-2 反轉本條] 推播盤中死、fetch 回補到
   t-5 分(仍 lag)→ **有新鍵 = 有進展**:minutes 照送前端(#45 送達保證)、variant
   不動;判無進展的唯一條件 = 零新鍵(空結果或凍結 stub 值漂)。
2b. Known Risk(review L2-P1-2 降級):「1K 壞而指數活」的日子,盤中新建窗口的凍結
   stub 鍵落在 domain 內 → 每個新窗口貢獻一個「當下真實指數價」的稀疏點(非假價),
   差量階梯下一發即識破換窗,TC4 1K 恢復即收斂為完整線。SC-5 側車順驗 stub 語意。
3. 窗外 stub 列 Time 恰可映入 domain(如昨日 53000 → 1330):A 的結果過濾以
   Date+hour 對窗判定,擋在 parser 之前(否則會偽造「已收盤完整」讓 heal 永停)。
4. `poll_wait == 0` 測試組態:單次探測語意保留(stub-only 首頁 → 直接 timeout 路徑)。
5. Date/Time 欄位缺失或格式異常的列:不過濾(保守),交由下游 parser 既有 skipped 機制。

## Out of scope

- 櫃買 MIS 死透(無回補來源,既有文件化降級;前端分態文案在 next-time)。
- `river_backfill` / 其他 `_collect_history` caller 的重試策略(timeout 靜默回空家族,
  next-time 已登記;本輪 A 的 stub 過濾對它們是純收緊、不加重試)。
- 前端(#45 已修 refetch 韌性,本輪不動 frontend/)。
- TC4 session 級 recycle(window variant 已足;session 手術 blast radius 大,留後手)。

## 驗證窗口

SC-5 盤中層:今日 13:30 收盤前若來得及 → 側車重演;否則次一交易日早晨(prod 重啟後)
觀察 log + 畫面。窗外降級 = 引擎級測試 + 側車 log 為證,盤中觀察列入待驗交接。
