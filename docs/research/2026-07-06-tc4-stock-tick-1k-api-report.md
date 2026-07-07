# 達錢 4(Touchance 4.0 / TCore ZMQ)股票 Tick + 1 分 K API 實測報告

> 目的:給「用 API 觀察個股 tick 變動」的測試 session 直接接手,不用重挖。
> 用途場景:盤中 tick 流觀察 + 1 分 K,直連 TCore ZMQ(**不經 PYCHARTs 後端**)。
> 標記沿用速查表慣例:🟢實機驗證 ｜ 📘官方範例 ｜ 🟡待驗 ｜ 🔴陷阱。
> 測試日 2026-07-06(週一,盤中 12:05–12:15 實測)。測試機:本機 Win11 + TC4 桌面 app 常駐。

---

## 0. TL;DR

| 問題 | 答案 |
|---|---|
| 股票拿得到歷史 tick 嗎? | 🟢 **可以**。2330 单日 6,200 筆(2026-07-03),每頁 50 筆分頁抓 |
| tick 深度多深? | 🟢 **至少 5 年**(2021-07-06 / 2024-07-03 都有貨,價位 sanity 正確)。10 年上限未測 🟡 |
| 盤中拿得到「當天」的 tick 嗎? | 🟢 **可以,延遲秒級**。增量輪詢 pattern 已驗證(見 §6,這就是「觀察 tick 變動」的路) |
| 1 分 K? | 🟢 有,且**原始欄位含每分鐘內外盤張數**(UpVolume / DownVolume),比經後端轉出的 OHLCV 多很多料(見 §5) |
| 即時 REALTIME push? | 🔴 **目前壞的**,`SubQuote` 一律回 `invalid Date Time Format`(期貨也一樣,非股票特有)。3 種修法都失敗,根因推測見 §7。用 §6 的輪詢替代 |

---

## 1. 連線與登入 🟢

- **Port 是動態的**,每次開 TC4 從 log 抓:
  `C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-YYYYMMDD-0.log` 裡的 `RepPort:xxxxx`(2026-07-06 = `50774`,與 2026-06-22 相同,但不可寫死)。
- 依賴:`pip install pyzmq` + 官方 wrapper `tcoreapi_mq.py`(在 `trash-mr-warrant/spikes/TCPY/`,或官方 GitHub `TOUCHANCE/TCPY`)。
- 登入用公開 sample 憑證即可:`APPID="ZMQ"`,`SKEY="8076c9867a372d2a9a814ae710c256e2"` 🟢。
- LOGIN 回 `SessionKey` + `SubPort`(SUB socket 埠,歷史回補通知與 PING 走這)。
- **登入後必須跑 KeepAlive**(`api.CreatePingPong(sessionKey, subPort)`):服務端會定期 PING,沒 PONG 回去 session 會被斷。wrapper 內建,別省。
- 🔴 原版 `Connect()` 無 socket timeout,port 錯會無限 hang — 自己設 `RCVTIMEO/SNDTIMEO`(範例見 §8)。
- 🔴 **收工前務必呼叫 `api.Disconnect()`**:KeepAlive 執行緒會讓一次性腳本的 process 卡著不退出,已修進 wrapper 但呼叫端要記得收尾——細節與根因見 §11。

## 2. 代號格式 🟢

- 台積電 = `TC.S.TWS.2330`(**TWS 段,不是 TWSE**)。歷史回補用這個格式驗證通過。
- 錯格式**不會報錯**,只會永遠拿不到資料 — 拿不到先檢查代號。

## 3. 歷史回補流程(TICKS / 1K 通用)🟢

```
SubHistory(session, symbol, ktype, start, end)   # 訂閱觸發回補
→ 輪詢 GetHistory(..., qryIndex="0") 直到 HisData 非空(實測 1–2 秒就緒)
→ 分頁:qryIndex = 上一頁最後一筆的 QryIndex,續 call 直到 HisData 為空
```

- 時窗參數 `yyyymmddHH`,**UTC+0** 🔴:台北日盤 09:00–13:30 = UTC 01:00–05:30,全日抓 `"YYYYMMDD00"` ~ `"YYYYMMDD06"`。
- **每頁固定 50 筆** 🟢。2330 全日 tick 6,200 筆 = 124 頁,序列抓完約 40 秒。
- 🔴 **鐵則:序列單筆,禁止併發**(速查表 §7 同因:單一共用 REQ socket,多執行緒交錯會讓 REQ 狀態機錯亂、崩後端/client)。
- 同 session 可以先後抓多個窗口 / 多個 ktype,一段跑完再跑下一段即可。

## 4. TICKS 原始欄位 🟢

2026-07-03 全日 6,200 筆實測,每筆:

```json
{"Date": "20260703", "FilledTime": "10006", "TradeQuantity": "4182", "TradeVolume": "0",
 "Bid": "2415", "Ask": "2420", "TradingPrice": "2415", "PreciseTime": "10006840000",
 "OI": "", "QryIndex": "1"}
```

| 欄位 | 意義 | 注意 |
|---|---|---|
| `Date` | 交易日 YYYYMMDD | |
| `FilledTime` | 成交時刻 HHMMSS,**UTC+0、無前導零** 🔴 | `"10006"` → zfill(6) = `010006` → +8 = **台北 09:00:06** |
| `PreciseTime` | 次秒級時刻 | zfill(12) = HHMMSS+ffffff:`010006840000` = 01:00:06.840000 UTC |
| `TradingPrice` | 成交價(字串) | 2415 = 2,415 元,無小數縮放 |
| `TradeQuantity` | **該筆成交張數** | 開盤競價 4,182 張、收盤競價 4,245 張各彙總成一筆 |
| `TradeVolume` | 當日累積量 | 🔴 **歷史日恆為 "0"**;當日盤中回補才有值。要累積量自己 cumsum |
| `Bid` / `Ask` | **成交當下一檔買/賣價** | 內外盤判別直接用:價貼 Ask=外盤、貼 Bid=內盤 🟢 |
| `OI` | 未平倉(期貨用) | 股票為空字串 |
| `QryIndex` | 分頁游標 | 也是全日流水號(1 起算) |

- 首筆 09:00:06(開盤競價)、末筆 13:30:00(收盤競價)— 頭尾正確對應日盤邊界。
- 筆數量級:一筆 ≈ 一次撮合彙總(2330 全日 6,200 筆屬正常量級),非逐筆委託。

## 5. 1K 原始欄位 🟢 — 比想像中多料

2026-07-03 全日 **270 根**(09:01–13:30,含收盤競價根)。每根:

```json
{"Date": "20260703", "Time": "10100", "UpTick": "125", "UpVolume": "237",
 "DownTick": "69", "DownVolume": "4552", "UnchVolume": "0",
 "Open": "2415", "High": "2420", "Low": "2415", "Close": "2420",
 "Volume": "4789", "OI": "", "QryIndex": "1"}
```

- `Time` = 該根**收盤時刻** HHMMSS UTC(`10100` → 台北 09:01,涵蓋 09:00–09:01)。末根 `53000` = 台北 13:30 收盤競價。
- **`UpTick`/`UpVolume`/`DownTick`/`DownVolume`/`UnchVolume` = 每分鐘內外盤筆數與張數** 🟢 — 觀察買賣壓變化可以直接用 1K 就有 aggregate,不必自己從 tick 算。
- 🔴 13:25–13:30 收盤前試撮期間照樣出根但 `Volume: "0"`(價格全平),末根 13:30 才灌收盤競價量 — 統計時記得處理。
- 🔴 舊速查表寫「1K 單日 266 根」是**經 PYCHARTs 後端**的數字;直連 ZMQ 實測 270 根,且**後端只轉出 time/OHLCV — UpTick/DownVolume 這些欄位被丟掉了**。要內外盤欄位就直連 ZMQ,或之後擴後端 schema。

## 6. 盤中觀察 tick 變動 — 增量輪詢 pattern 🟢(REALTIME 壞掉時的正路)

盤中(12:10)實測:

1. `SubHistory(TICKS, "2026070600", "2026070606")` + 分頁全抓 → **3,957 筆**,最後一筆 12:09:47(台北)。
2. 等 40 秒 → **重送同窗口 `SubHistory`**(觸發回補快取更新)→ 從上次 `QryIndex=3957` 續抓 → **新增 9 筆**,最新 12:10:53 — 離抓取時刻**只差 1–3 秒**。

```
loop:
    SubHistory(session, sym, "TICKS", today_00, today_06)   # 每輪重送,觸發更新
    sleep(1~2s)
    從上次 QryIndex 續抓到空頁 → 新 tick = 這一輪的增量
    sleep(輪詢間隔)
```

- 新鮮度:秒級(非 push 即時,但對「觀察變動」足夠)。
- 當日盤中回補的 `TradeVolume` 有值(= 累積量),與歷史日恆 0 不同,可直接用。
- 多檔監控:**仍然序列**,一檔一輪抓完再換下一檔(§3 鐵則)。單檔一輪增量通常 1 頁內,幾百 ms,序列掃 10–20 檔仍在可用範圍 🟡(多檔實際輪詢成本未實測)。

## 7. 🔴 已知問題:REALTIME SubQuote 全面失敗(2026-07-06)

- 症狀:`SubQuote` 一律回 `{"Success": "Fail", "ErrMsg": "invalid Date Time Format"}`,SUB socket 上收不到任何 REALTIME push。
- 已試(3 次上限已滿,停):
  1. 正常流程(同 session 先訂過歷史)→ 失敗
  2. 乾淨 session、先 `UnsubQuote` 再 `SubQuote` → 失敗
  3. 對照組:台指期 `TC.F.TWF.FITX.HOT` + 股票兩種代號變體 → **全部同錯誤** ⇒ 非股票特有、非代號問題、非 session 汙染
- 根因推測(未證實):歷史訂閱(同為 `SUBQUOTE` request、帶 `StartTime/EndTime`)完全正常 ⇒ 服務與 session 都活著;唯獨**不帶時間欄位**的 REALTIME 變體被服務端的時間欄位驗證擋下 — 懷疑現行 QuoteZMQService 版本改了電文契約(無條件驗 `StartTime/EndTime`),手上的 TCPY wrapper 是舊版。
- 後續修法方向(給有需要 push 的 session):(a) REALTIME 請求帶 dummy `StartTime/EndTime` 試打;(b) 抓官方最新 TCPY / QuantBridge 電文文件(行情篇 PDF 在 `spikes/TCPY/`)比對;(c) 翻 `QuoteZMQService-*.log` 看服務端怎麼記這筆請求。
- **對本次需求不阻塞**:觀察 tick 變動走 §6 輪詢即可。

## 8. 最小可用範例(單檔可帶走)

依賴:`pyzmq` + `tcoreapi_mq.py`(放同目錄)。Python 3.13 實測 OK。

```python
# -*- coding: utf-8 -*-
"""拉一檔股票的 TICKS(或 1K):序列單筆、UTC 時窗、QryIndex 分頁。"""
from __future__ import annotations
import json, time, zmq
from tcoreapi_mq import QuoteAPI

PORT = "50774"          # 每次開 TC4 從 QuoteZMQService-*.log 的 RepPort 確認
SYM = "TC.S.TWS.2330"   # TWS 段,不是 TWSE
KTYPE = "TICKS"          # 或 "1K"
START, END = "2026070300", "2026070306"  # UTC+0!台北日盤 = UTC 01:00-05:30

api = QuoteAPI("ZMQ", "8076c9867a372d2a9a814ae710c256e2")
api.socket = api.context.socket(zmq.REQ)
api.socket.setsockopt(zmq.RCVTIMEO, 30000)   # 原版無 timeout 會 hang,必設
api.socket.setsockopt(zmq.SNDTIMEO, 5000)
api.socket.setsockopt(zmq.LINGER, 0)
api.socket.connect(f"tcp://127.0.0.1:{PORT}")
api.socket.send_string(json.dumps(
    {"Request": "LOGIN", "Param": {"SystemName": api.appid, "ServiceKey": api.ServiceKey}}))
login = json.loads(api.socket.recv()[:-1])
assert login.get("Success") == "OK", login
api.CreatePingPong(login["SessionKey"], login["SubPort"])   # KeepAlive 必開
session = login["SessionKey"]

api.SubHistory(session, SYM, KTYPE, START, END)
for _ in range(60):                                          # 等回補就緒(實測 1-2s)
    if api.GetHistory(session, SYM, KTYPE, START, END, "0").get("HisData"):
        break
    time.sleep(1)

rows, qi = [], "0"
while True:                                                  # 每頁 50 筆
    his = api.GetHistory(session, SYM, KTYPE, START, END, qi).get("HisData", [])
    if not his:
        break
    rows += his
    qi = str(his[-1]["QryIndex"])
print(f"{len(rows)} rows")
# 時間解讀:FilledTime/Time 為 HHMMSS、UTC+0、無前導零 → zfill(6) 後 +8h = 台北

api.Disconnect()   # 🔴 一次性腳本收工前務必呼叫,見 §11——不然 process 不會退出
```

## 9. 環境紀錄

| 項目 | 值 |
|---|---|
| 測試日 | 2026-07-06(週一)盤中 12:05–12:15 |
| TC4 | 本機常駐(TOUCHANCE / TCore64 / QuoteZMQService 皆 08:53 起) |
| RepPort | 50774(當日 log 確認) |
| Python | 3.13(`C:\...\Programs\Python\Python313`,pyzmq 27.1.0)。🔴 `py` launcher 預設 3.14 **沒裝 pyzmq** |
| wrapper | `trash-mr-warrant/spikes/TCPY/tcoreapi_mq.py`(官方 sample) |
| 探測腳本 | session scratchpad `probe_stock_ticks.py` / `probe_1k_realtime.py` / `probe_realtime_control.py` / `probe_incremental_poll.py`(核心邏輯已收進 §8) |

## 10. 帶回速查表的更新(公司 session 那份)

- §2:`TICKS` 股票 🟢 有貨(單日 6,200 筆 / 每頁 50);深度 🟡→🟢 至少 5 年(10 年仍未測)。
- §2 新增:TICKS / 1K **原始欄位表**(本報告 §4 §5)— 後端 `/api/history/range` 只轉 OHLCV,內外盤欄位(tick 的 Bid/Ask、1K 的 Up/DownVolume)都被丟掉。
- §5 新增:REALTIME SubQuote 現版本壞(`invalid Date Time Format`,期貨股票皆然),替代 = 盤中增量輪詢(本報告 §6)。
- §7 補充:盤中同窗口重送 `SubHistory` + 從上次 `QryIndex` 續抓 = 安全的增量模式,仍需序列。
- §11 新增:`tcoreapi_mq.py` 的 KeepAlive 執行緒生命週期 bug 已修好,`Disconnect()` 是新公開方法,呼叫端必記得收尾。

## 11. 🔴 已知問題:KeepAlive 執行緒預設非 daemon,一次性腳本收工後 process 不會退出

- **症狀**:抓取腳本(如 `fetch_1k.py`)印出 `done`、程式邏輯已跑完,但 `python.exe` process 仍在背景占用記憶體、持續跟 TC4 做 PING/PONG——2026-07-06 在另一個下游專案(neigui,broker-signature-explorer 研究)實測,**5 支這樣的一次性抓取腳本因此變成孤兒 process**,其中一支(`probe_tc4.py`)空轉近 4 小時才被發現。
- **根因**:`tcoreapi_mq.py::KeepAliveHelper.__init__` 開的 `threading.Thread` 沒有設 `daemon=True`。Python 規則是 process 要等**所有非 daemon 執行緒**結束才會真正退出,即使 main thread(腳本主體)已經 `return`。`ThreadProcess` 內是 `while True: recv()` 永久阻塞迴圈,原本的 `Close()` 只設一個 flag,不會真的中斷卡在 `recv()` 的執行緒——收到下一筆 PING 才會檢查 flag,若沒有下一筆訊息就永遠卡著。
- **修法**(已修進 `spikes/TCPY/tcoreapi_mq.py`,2026-07-06):
  1. 執行緒改 `daemon=True`——保底:即使忘記呼叫任何清理,process 仍能正常退出。
  2. `KeepAliveHelper` 自己持有一個 `zmq.Context()`(原本是在 `ThreadProcess` 內建立匿名 context,外部完全拿不到、無法中斷),`Close()` 時呼叫 `context.term()` 強制中斷卡住的 `recv()`(拋 `zmq.ZMQError`,`ThreadProcess` 捕捉後跳出迴圈收工),不再只是消極等下一筆 PING 才檢查 flag。
  3. `TCoreZMQ` 新增公開方法 `Disconnect()`(依序:停 keepalive → 關 socket → 關 context),**任何一次性腳本收工前都要呼叫這個**,見 §8 範例最後一行。
- **驗證**(smoke test,2026-07-06):登入 → 起 keepalive → 呼叫 `Disconnect()` → 腳本 `return` 後,`tasklist` 確認對應 PID **立即消失**,不再殘留(修復前跑同樣流程,process 會無限期掛著)。
- **檢查方式**:抓取腳本跑完後 `Get-Process python`(PowerShell)確認沒有殘留;若還有殘留,代表忘記呼叫 `Disconnect()`,或是還在用專案裡沒同步這個修法的舊版 wrapper 複本。
- **長駐服務(非一次性腳本)不受影響**:若你的下游專案是常駐監聽(例如即時 tick 服務、WebSocket bridge),process 本來就該一直活著,不需要呼叫 `Disconnect()`——這個修法只解決「短命腳本收工後該退出卻不退出」的問題。
