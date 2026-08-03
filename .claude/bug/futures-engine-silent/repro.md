# Bug 1 — futures_engine 間歇性整段零推播

**狀態:未重現(5/5 嘗試皆健康)。依鐵則 A + user 指示,本輪不改 code。**
Phase 1 交付 = 「什麼條件下會發生」的收斂結果,不是修法。

---

## 1. 重現嘗試(全部失敗 = 沒發生)

環境:2026-07-30 夜盤(台指期夜盤 15:00–05:00),達錢 4 開著,ZMQ 50774。
原始通報的失敗是 2026-07-29 17:33 起跑的 server 到 00:50 為止 TXF/MXF/TMF 全 `p=null`、`seq=0`。

| # | 條件 | 起跑時刻 | 結果 |
|---|------|---------|------|
| 1 | 夜盤冷啟動(手動,完整 log) | 16:34:15 | 22 秒後三品全有值(seq=308) |
| 2 | hard kill 前一台 → 10s → 重啟 | 16:36:49 | seq=145,silent=none |
| 3 | 同上,連續第 2 次 | 16:37:09 | seq=150,silent=none |
| 4 | 同上,連續第 3 次 | 16:37:29 | seq=99,silent=none |
| 5 | 同上,連續第 4 次 | 16:37:49 | seq=125,silent=none |

證據:`trial1_night_coldstart.log`、`trial{2..5}_restart.log`、`trial1_poll.txt`、
`restart_trials.txt`(自動化腳本 `restart_trials.py`)。

### 因此被排除的候選條件

- **「夜盤冷啟動就會壞」** — 排除。5 次夜盤冷啟動全正常。
- **「前一台被 hard kill、TC4 session 殘留」** — 排除。第 2–5 輪皆為 `Stop-Process -Force`
  之後 10 秒重啟,全正常。
- **「連續快速重啟」** — 排除。連四輪間隔 ~20 秒,全正常。
- **「同一個 process 起了兩份 app」** — 排除。實測 `python -m copycat.server` 確實有兩個
  process(parent/child),但 **parent 是 1 執行緒、0 連線的 stub**,child 才持有全部
  5 條 TC4 session 並綁 8721。不是兩份 app 在搶訂閱。

### 原記載中被推翻的一點

CLAUDE.md §8 與 handoff 都把主因指向「TXO runtime 的 `SPOT_SYMBOL = TC.F.TWF.TXF.HOT`
與 futures_engine 同 symbol,TC4 只推一邊」。**這條解釋不了通報的症狀** —— 只有 TXF 會撞,
`MXF` / `TMF` 沒有任何其他模組訂閱,卻同樣 `p=null`。同 symbol 衝突最多只能解釋 TXF 一品。

---

## 2. 蒐證(archaeology)

`.claude/feat/realtime-correlation/evidence/` 內三份 server log 都**不是**通報那台
(17:33 起跑那台的 stdout 未被保存)。它們是當晚 00:51 / 00:53 的 agent 重啟:

- `server.log`(00:51:05 起)、`server2.log`(00:53:47 起)、`server_day.log`(10:24 起,
  bind 8721 失敗即關,不是健康那台)。
- `server2.log` 00:57:30 有 `futures TMF HOT 零推播,補訂 leaf 202608` —— 只有 TMF,
  代表當時 TXF/MXF **有**資料。故連這兩份都不是「三品全 null」的狀態。

### 唯一的結構性訊號:啟動期的 REQ 逾時

各次啟動的 TC4 connect 時間差:

| 執行 | connect 間隔 | 判讀 |
|---|---|---|
| server.log(00:51) | 10.488 → **40.564**(30.076s) | 3 × `_REQ_TIMEOUT_MS`(10s) |
| server2.log(00:53) | 51.882 → **54:21.935**(30.05s) | 同上 |
| trial 1(16:34) | 23.270 → 33.229(9.96s) | 1 × 10s |

`_req()` 逾時 → `_dispose(api)` 丟棄連線 → 下次呼叫 `_ensure_connected()` 重連並再印一行
`TC4 connected`。所以「TC4 connected」行數 ≠ 引擎數,而是引擎數 + 逾時重連次數。
**當晚 TC4 的 REQ 通道比今天慢得多(30s vs 10s 的逾時累積)。**

---

## 3. 機制:一條讀 code 就成立、且與症狀完全吻合的缺口

`FuturesEngine._subscribe_all`(`server/futures_engine.py:127`)對每品 `subscribe_symbol`,
`except ConnectionError` 只 log warning 就跳下一品。**失敗的商品之後沒有任何重試路徑**:

1. 失敗的 symbol 不會進 `TC4QuoteSource._subscribed`;而 `_check_stale()` 的重訂閱迴圈
   只走 `list(self._subscribed)`(`live/tc4.py:456`)→ 永遠不會補訂它。
2. leaf fallback 由 `_handle_quote` → `_schedule_leaf_fallback` 觸發,**需要先收到推播**。
   三品全訂閱失敗 = 零推播 = leaf fallback 永不啟動。

探針實測(`mechanism_probe.py`,真 `FuturesEngine` + 假 source,不改 production code):

```
[全部失敗] 訂閱失敗商品=['MXF','TMF','TXF']
  觀察 1.5s 後:seq=0 無報價商品=['MXF','TMF','TXF']
  subscribe_symbol 呼叫次數=3 明細=['TXF','MXF','TMF']     ← 每品只試一次,永不重試
  leaf fallback 補訂=(未觸發)
```

`seq=0` + 三品 `p=null` + 零 leaf fallback —— **與通報症狀逐項相同**。

> 誠實界定:探針證明的是「啟動期訂閱失敗 → 該品永久靜默」這條缺口真實存在,
> **不等於**證明 2026-07-29 當晚就是走這條。第二個 scenario(僅 TXF 失敗)顯示三品皆
> silent 是假 source 不推播的產物,不可拿來當證據。

---

## 4. 下一次它再發生時,怎麼一次定案

這條機制有**可證偽的預測**:若當晚走的是它,server log 一定有

```
copycat.server.futures_engine WARNING futures <TXF|MXF|TMF> subscribe ... failed
```

(`_subscribe_all` 的 `logger.warning("futures subscribe %s failed", product)`)。

所以:**下次期貨面板整段空著時,先 grep server log 有沒有這行。**
- 有 → 機制確認,修法 = 讓 `_subscribe_all` 的失敗品進重試佇列
  (或把失敗 symbol 也記進 `_subscribed` 讓 `_check_stale` 接手)。
- 沒有 → 機制不是它,回到「訂閱成功但 TC4 不推」那一類,要從 SubPort / listener 執行緒
  存活兩個方向查。

**前提:server 要留 log。** 通報那台沒留 stdout,是這輪定位不了的直接原因。
建議日常啟動一律導向檔案(`python -m copycat.server > logs/server-YYYYMMDD-HHMM.log 2>&1`)。

---

## 5. 連帶影響(未變)

`corr_engine` base 腿讀 `futures_engine.state()`;上游空著時五對相關係數全 `None`
(引擎行為正確、有測試覆蓋,只是畫面沒數字)。本輪未動。
