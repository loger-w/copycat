# repro:台股綜合頁加權/櫃買分時圖「圖殼在、走勢線整條不見」

## 症狀(user 回報)

分時圖座標軸與昨收虛線都在,只有走勢 polyline 消失;「有時」發生,換日/開盤前後為嫌疑窗。
前端已知渲染條件:`MarketChart.tsx` 只在 `g.line.length > 0` 畫 polyline;
`buildIndexGeometry` 對空 `minutes` 降級 `line: []` → 症狀 = **series 非 null 但 minutes 空**。

## 活體現場(2026-08-13 14:44,prod localhost:8721,git_sha 12b7b4f0)

`GET /api/index/state`(存證 scratchpad `index-state.json`):

```
trade_date 2026-08-13
twse p=46021480 ref=45518070 high=46216410 low=45676540 stale=False last_minute=None  minutes_n=0   ← 加權整天 0 根分鐘
otc  p=406120   ref=402020   ...                                                      minutes_n=269  ← 櫃買 0901–1330 完整
```

**加權分時線今天整天不見**(twse.minutes 空),同時 p/ref/high/low 有今日真值 → 前端畫殼不畫線。

## 蒐證(logs/server-20260813-0822.log)

1. `08:22:30` server 啟動(當日 08:22 < 08:30,但 `create_app` 初始 `trade_date = date.today()`
   = 2026-08-13,`app.py:609`)→ **今天 rollover loop 恆走 `new_date <= trade_date` 跳過,
   換日路徑整天未參與**(排除候選 (1))。
2. `08:23:03 copycat.live.tc4 INFO history TC.S.TWS.IX0001(1K): 30.0s 內首頁未備妥,回空`
   —— 開機唯一一次 1K 回補 **timeout 被靜默降級成空結果**,`_subscribe_and_backfill` 不
   raise → `start()` 視為成功 → **`_schedule_retry` 不觸發**(retry 只接 ConnectionError,
   `index_engine.py:189-194`)。排除候選 (2) 的表述:「回補失敗走 _schedule_retry」——
   實際上 timeout 路徑**根本不走** retry,這正是缺口。
3. 整份 log 全日:無 reconnect、無 retry、無第二次 IX0001 history 請求、無 `txo spot 無 TXF
   推播`(= TC4 整體連線與 TXF 推播全日正常)。
4. 盤中 09:01–13:35 **零筆有效分鐘鍵寫入**(minutes 空 + last_minute 恆 None),但 p/high/low
   有今日終值且 stale=False → 至少有推播在**分鐘域外時刻**(盤後 snapshot)抵達過。
   → IX0001 REALTIME 推播在本 session 盤中整段靜默(TC4 已知「訂閱成功但零推播」
   間歇性家族,tc4-market-facts 訂閱節);盤後 snapshot 帶回 close/high/low 並清 stale。
5. **裁決性證據**:14:52 經 prod 自己的 index session 查
   `GET /api/market/bars/TWSE?tf=1&days=1` → **270 根完整 1K(09:01–13:30)當場取回**。
   TC4 端資料整天都在;引擎在 08:23 timeout 後**再也沒有任何機制去問第二次**。

## 歷史重現率

- 2026-08-12 08:58:19 同一條 timeout log(連續兩個早晨 2/2)——早晨冷啟動(TC4 剛開、
  同時搶 255 檔個股訂閱 + 6 腿 river 回補)時 IX0001 1K 首頁 30s 內備不齊為高機率事件。
- 2026-08-12 18:17 盤後啟動:無 timeout log(TC4 閒時回補快速成功)→「有時」的分佈
  = 早晨啟動日風險高、盤後啟動日正常,與 user 觀察相符。

## Root cause 判定

**引擎層:IX0001 分時 minutes 的資料鏈是「開機那一次 1K 回補 + 推播」雙依賴,兩者都沒有
針對『產出面(minutes 覆蓋度)』的偵測與回復機制:**

- 回補:timeout 靜默回空 = 被當成功,不排 retry(缺口 A);
- 推播:盤中整段靜默時 watchdog 只標 `stale` 展示,不觸發任何回復(缺口 B);
- rollover 的 60s 週期 fetch 只在 pending 態運作,當日 boot 不參與。

三者疊加 → 只要「早晨啟動回補 timeout」+「當日推播靜默」同日發生,加權分時線整天空,
且系統無任何自癒路徑(TC4 端 1K 資料明明整天可取)。

候選 (3)(前端換日 refetch 失敗只 warn 不重試)為**同症狀家族的獨立潛在缺陷**(inspection
確認存在:`useIndexStream.ts` 換日清空後 refetch 失敗 → 後續 WS merge 只靠 last_minute
增量重建,失敗點之前的分鐘永久缺失),但**不是今日事故路徑**(今日無換日、無 WS 斷線)。

## 櫃買(otc)側

今日櫃買正常。櫃買同症狀的已知可能:MIS 連續失敗(log 10:01 有 transient 2 次)+ 換日
swap 清空後 MIS 死透 —— MIS 無歷史來源,引擎層無法回補(既有已文件化降級)。不在本次
修復範圍,同家族前端路徑(候選 3)修復後可涵蓋其換日面。

## 重現 loop(紅指令)

engine 級 pytest(見 `tests/server/test_index_engine.py` 新增測試):
fake source 回補回空(模擬 timeout 靜默降級)+ 推播零有效鍵 + 進入 watch window 越過
lag 門檻 → 斷言引擎**應**再次呼叫 `fetch_day_minutes` 自癒 → 現行程式紅(永不重問)。

## 修復與反向驗證(2026-08-13 追記)

修復三段(詳 verification.md):
1. 引擎分時自癒(`8fb40e56`):watch window 內 minutes 落後牆鐘 >3 分 → single-flight
   retry(重掛訂閱重武裝推播 + 重抓 1K),60s 節流;自癒 retry 不清 stale(watchdog 職權)。
2. 廣播送達(`c2f88576`):retry 成功後下一則廣播 twse 帶 minutes 全量一次(否則已連線
   前端要等重整才看得到線)。
3. 前端 refetch 退避重試(`38f8312d`):換日/初載/reconnect 的 refetch 失敗不再永久缺線。

反向驗證:實作檔還原 master → 引擎 4 紅 + 前端 1 紅(紅在 minutes 空/timeout)→ 還原
HEAD → 全綠。過程中發現並修掉 heal 對 watchdog 測試的干擾 flake(6/10 → 10/10,`dce097b1`)。

## 實驗記錄(systematic-debugging;一次一假說)

- H「換日 _swap_day 清空」:被證偽 —— 今日 trade_date 從 boot 即為當日,rollover 未參與(證據 1)。
- H「回補失敗有走 retry 但重試期間空」:被證偽 —— timeout 不 raise,retry 從未排程(證據 2、3)。
- H「FilledTime 對指數不可用(每天皆然)」:被證偽 —— 若恆不可用,分時線應**每天**凍結/消失
  (含盤後啟動日的次日),與 user「有時」+ 盤後啟動日正常矛盾;判定為間歇性推播靜默(證據 4)。
- H「TC4 端當日 1K 不可得,回補重試也沒用」:被證偽 —— 證據 5(270 根當場取回)。
