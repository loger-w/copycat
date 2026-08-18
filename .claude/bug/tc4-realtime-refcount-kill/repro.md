# repro — 08-18 開盤全站零推播(自選無資料 / 五檔空 / 期貨凍結 / 指數分時空)

## 症狀(09:03 現場)
- 前端:自選每檔「無資料」、無價格 / 漲跌幅;五檔全 `—`;閃電下單「無資料」;分時線只有回補段。
- 後端:`/api/stock/state/<code>` → `no_data:true, book:null, meta:null`,ticks 只隨 30s 回補跳;
  `/api/futures/state` TXF `t=09:01:47.511`、seq 不動;index `twse.minutes` 空。
- server log 零 ERROR / 零 Traceback;py-spy dump:5 條 `_listen_loop` 全在 `sock.recv()`(tc4.py:662)閒置。
- 前一台(07:58 起)09:00:49 被關掉重啟仍同症狀;08-17 08:05 那台 log 也有 08:06:02 TXF/MXF/TMF 零推播 + 指數自癒整早無進展。

## 判別實驗(獨立 session probe,scratchpad rt_probe.py / crosskey_kill.py)
| # | 實驗 | 結果 | 結論 |
|---|---|---|---|
| A | 訂 prod 未訂的 2330 / 2317 / MES,聽 20s | 86 / 57 / 73 則 | TC4 推播基建正常,假說「TC4 壞了」否決 |
| B | 訂 prod 已訂的 3081 / TXF.HOT(同窗 00–06) | 0 / 0 則 | 這些 symbol 對任何 session 都零推播 |
| C | zombie(硬殺不 LOGOUT)後 victim 同 key 訂閱 130s | 全程有推播 | 「殭屍 reap 殺同 key」單 key 不成立 |
| D | 訂只被已死 server 訂過的 TXF/MXF/TMF.202608 leaf;TXF.HOT 換全天窗 (00–23) | 全部有推播(150–201) | 死的是 **(symbol) 上游 feed**,換一把新 key 就重掛 |
| E | 3081 換窗 (00–07) / 6451 (01–06) / 2455 同窗 (00–06) | 85 / 22 / 0 | 同上;且 prod 的 3081 因 PUB 廣播同步復活(book/meta 到、no_data false) |
| F | REALTIME 流動中對同窗做 SUBQUOTE TICKS + GETHISDATA | 前 32 → 後 195 | 歷史回補不殺 REALTIME,否決 |
| **G** | **A 訂 (2317,00–06)、B 訂 (2317,00–07);A 退訂 → B 15s 0 則;B 自己 UNSUB→SUB 同 key → 125 則;B 換窗 → 160 則** | **決定性重現** | 見下 |

## Root cause(TC4 QuoteZMQService 行為,由 `C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-20260818-0.log` 佐證)
- TC4 訂閱 refcount 以 **key = `symbol|DataType|StartTime|EndTime`** 計(`Add/RemoveSubQuoteCount ... count:N, SumSubCount:M`),
  但**上游 feed 以 symbol 為單位**:key count 0→1 時才 `ReqSubQuote(symbol)`;**任一把 key SumSubCount 歸 0 → 上游退訂整個 symbol**,
  同 symbol 其他 key(count 仍 >0)一起斷,之後對那些 key 再 SUBQUOTE 因 count>0 **不重掛上游 → 永久零推播**。
- 觸發鏈(今天):
  1. 07:58 那台 09:00:49 被 taskkill(lifespan close 沒跑完、無 LOGOUT)→ 五條 session 成殭屍。
  2. 09:00:52–57 新 server 訂同 key(count 1→2,不重掛上游,沿用殭屍建的 feed;期貨因此還流了 55s)。
  3. **09:01:52 TC4 `ExecuteCheckPingTime` reap 殭屍(`RemoveLoginInfo` ×5)**:殭屍獨持的 key(夜盤窗 `TXF.HOT|06–22`、
     08-17 舊窗 `3081|2026081700–06`、corr 腿 08-17 全天窗 …)歸零 → 上游退訂這些 symbol → 新 server 的日盤 key 全死。
  4. 個股在 07:59:09 reap 21:30 那台時就已死(同機制),所以 09:00 那台從 boot 起就 `no_data`。
- 我方缺口:任何 source 都沒有「REALTIME 零推播 → 重掛(讓自己那把 key 走 0→1)」的自癒;
  且 TXF.HOT 日盤 key 由 TXO session + futures session **雙持**,單 session UNSUB→SUB 永遠到不了 0。
- 修正既有認知:skill 「同 symbol 跨 session 只推一邊」**是錯的**(PUB port 54322 單一廣播,所有 session 都收得到),
  07-28 觀察到的其實是本 bug(重啟後 reap 殺 key)。

## 一條能變紅的指令
`.venv\Scripts\python <scratchpad>\crosskey_kill.py TC.S.TWS.2317` → `afterAunsub=0`(其餘 >0)。
(對 TC4 真環境;單元層紅測試見 verification.md)
