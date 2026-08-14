# repro:指數分時線消失(#45 自癒上線後仍全日缺線)— backlog 第 1 輪(user 原始回饋第 8 條)

## 與前案(fix/index-chart-empty-minutes,PR #45)的關係

#45 修的是「boot 1K 回補 timeout 靜默回空 + 推播整段靜默 → 無自癒」,出貨三段:
引擎分時自癒(lag>3 分 → single-flight 重掛+重抓)、heal 成功下一則廣播帶 minutes、
前端 refetch 退避。**本輪 = #45 上線後的第一個交易日(2026-08-14)自癒實戰失效**:
自癒有觸發、但修不回,加權分時線整個上午仍空。user prompt 內嵌的候選 (2)(3) 已由
#45 處置(候選 2 的表述當時即被證偽);候選 (1) 換日路徑今日未參與(boot 即當日)。

## 活體現場(logs/server-20260814-0800.log;build 3aacc269+dirty,含 #45,後端與 master 同源)

1. `08:01:03` boot IX0001 1K 回補 30s timeout 靜默回空(連三早晨 3/3:08-12/08-13/08-14)。
2. IX0001 REALTIME 推播整個上午靜默(minutes 恆空;同機 TC4 個股推播/TradeStatus 全日正常)。
3. **自癒觸發 9 次**:09:04:00 / 09:06:00 / 09:10:01 / 09:18:01 / 09:33:01 / 09:48:02 /
   10:03:03 / 10:18:03 / 10:33:04 — 間隔 = 120/240/480/900/900/900/900/900s,
   **純倍增、無一次重置** → 每一拍 lag 都 >3 分 → minutes 全程未前進(恆空)。
4. **全日只有一筆 IX0001 history log(boot 那筆 timeout)** → 9 次 heal 的 fetch 都
   「快速返回、非 timeout、無解析 skip warning」卻帶回零有效分鐘。
5. 9 個 retry task 都完成(否則 `retry_task.done()` 閘會擋住下一發 heal)→ 排除
   ConnectionError 迴圈 / 卡死路徑。
6. server 10:45 graceful 關閉(user 手動);12:09 user 貼本輪 bug。

## 活體實驗(盤中 12:16–13:10,TC4 app 同一顆,prod server 已停無 session 衝突)

- **probe(全新 session,同窗口 2026081400-2026081406)**:12:16 當場取回 197 根
  0901–1217(到當下分鐘),0 skip、0 domain-drop → TC4 端資料可取、解析鏈無恙。
- **實驗 A(全新 session)**:全量收割消耗 cursor 後,不論是否重送 SubHistory,
  GETHISDATA("0") 都從頭給(50 列/頁)→ 健康訂閱不受 cursor 消耗影響。
- **實驗 B(黃金重現,12:21 起)**:對「當下為空」的 05-06 窗(台北 13:00–14:00)
  SubHistory 後首問 GETHISDATA("0") **立刻回 1 列窗外 stub —— 當下分鐘(12:21,
  Time=42100)的 bar**,而非空頁。⇒ **TC4 1K GETHISDATA 對空窗訂閱會回窗外 stub 列**,
  `_collect_history` 首頁非空即 break → 回 1 列垃圾且 `timed_out=False`。
  **13:01/13:02 續輪(窗內已有真 bar 1301/1302)**:同 session 重送同窗口 SubHistory,
  依然只回**凍結在訂閱建立時刻(12:21,Time=42100)的 1 列 stub**,Close 隨現價漂
  (45966→45952,= 當下大盤價)但分鐘鍵永不前進 —— 同窗口重抓永不恢復,與 prod
  全日 9 次無效 heal 同構。**對照 C1(同 session、換窗口 00-06)**:13:02 當場取回
  243 根完整 0901–1303(含窗內新 bar)→ 換窗口字串 = 全新訂閱 = 立即逃逸。
  對照 C2(新 session)腳本漏 `_ensure_connected` 未跑成(非產品訊號);「新 session
  可取」已由 12:16 probe 獨立證明。stub 機制定性:**毒化訂閱回「分鐘鍵凍結於建立
  時刻、價格為當下現價」的單列 stub** — 對 boot(08:00 建立)場景,該 stub 的鍵映不進
  0901–1330 domain,故 prod 的 minutes 恆空、heal 永遠 lag、log 全靜默,三者全部對齊。

## Root cause 判定(依證據 1–5 + 實驗 B 首步)

**自癒鏈的「成功」判準是輸入面(fetch 沒丟例外)而非產出面(minutes 是否前進):**

- `index_engine._retry_loop`:`_subscribe_and_backfill` 不 raise 即視為成功並 `return`
  (`_push_minutes_once`/`_dirty` 照設)— fetch 回空或回窗外 stub 都算「成功」。
- `stock_source.fetch_day_minutes`:domain 外的列**靜默丟棄**(不計 skipped、無 log)
  → 「1 列窗外 stub」與「整窗有效資料」在 caller 眼裡無法區分,零訊號。
- `_collect_history`:首頁非空即 break — TC4 會以窗外 stub 列「非空」騙過輪詢,
  逾時判定失效(`timed_out=False`)。
- heal 的重抓固定重用**同 (session, symbol, ktype, 窗口字串)** 的 history 訂閱;實測
  該訂閱一旦於「窗內無資料」時建立即進入 stub 態,重送 SubHistory 逃不出去;而
  (a) 同 session 換窗口字串(08-13 14:52 的 00-23 fetch,270 根)與 (b) 新 session
  同窗口(今日 12:16 probe,197 根)都能當場取回 → 逃逸維度 = 窗口字串或 session,
  不是重送次數。

三者疊加:boot 空窗 timeout → heal 每次重抓拿 1 列窗外 stub → 宣告成功 → 退避倍增
→ 全日缺線,且**除了第一筆 boot timeout 外整天零 log**。

## 實驗記錄(systematic-debugging;一次一假說)

- H「rows 全被 domain 濾掉(parser 壞)」:被證偽 — probe 197 根 0 丟棄,parser 對
  真資料無恙;真相是「rows 本身是窗外 stub」(實驗 B)。
- H「heal 的 fetch 也 30s timeout」:被證偽 — timeout 必留 log,全日僅 boot 一筆(證據 4)。
- H「retry task 卡死/ConnectionError 迴圈」:被證偽 — 9 發 heal 純倍增節奏要求每個
  task 都在間隔內完成(證據 3、5)。
- H「heal fetch 拿到窗內當下 bar(lag 應恢復)」:被證偽 — 若 09:04 拿到 0904 bar,
  09:06 lag=2 不會再 heal;觀測 09:06 有 heal → 拿到的列必為 domain 外(證據 3)。
- H「TC4 當日資料不可得」:被證偽 — probe/實驗 A 當場全量取回。

## 修復與反向驗證(2026-08-14 追記)

修復兩波(commit 見 verification.md / PR):
1. 核心波:`fetch_day_minutes(window_variant=)` 窗口逃逸 + 引擎 heal 產出面判定
   (紅先行 4 commits)。
2. review fix 波(code-review-round-1.json):revert tc4 窗過濾(L2-P1-1:對 boot
   stub 為 no-op)、進展改「新分鐘鍵差量」、部分進展仍送達前端、variant 恢復不歸零
   (僅 `_swap_day` 歸零)、封頂獨立 log、stub 簽名 log(3 commits)。

反向驗證:核心波 revert → 8/9 新測試紅、紅在症狀(stub 偽造完整日 / variant 參數
不存在 / 無進展照樣廣播 / variant 恆 0)→ 還原 → 71/71 綠。fix 波 red commit 實跑
4 failed / 33 passed。詳 verification.md。

修復後的當日事故重演(推演,SC-5 次晨實測待驗):boot timeout(log 照舊)→ 09:04
heal v0 拿凍結 stub → 全數域外 →「疑似凍結 stub」+「分時自癒無進展」兩行 log,
variant→1 → 09:06 heal v1 全新窗口 → 全量回補 → 廣播帶 minutes → 分時線 ~09:06 回來
(對照修復前:全日不回、零 log)。
