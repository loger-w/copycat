# 2026-07-20 TXO 綜合損益即時看盤 — 盤中驗證報告

驗證對象:memory `txo-live-pnl-shipped` 的四項盤中待驗(第一輪 design Known Risk 1 + 第二輪追加)。
環境:2026-07-20(一)日盤 09:46–10:32,達錢 4(Touchance 4.0)+ `python -m copycat.server`(port 8721)+ `npm run dev`(port 5173)。
性質:**只驗證與記錄,未修任何 code**。獨立觀測工具(第二條 TC4 session probe)腳本在 session scratchpad,關鍵數據全數收錄本文。

## 總表

| # | 待驗項 | 結果 | 一句話 |
|---|--------|------|--------|
| 1 | live REALTIME push 頻率 + rebuilt_cum 與 live TradeVolume 一致性 | **PASS** | 8/8 檔邊界差 = 0,TradeVolume 從不倒退;交接協定外部假設成立,**不需 fallback(design §2.3 T_b 邊界去重不用做)** |
| 2 | TXF 現價推播恢復 | **FAIL** | `SPOT_SYMBOL="TC.F.TWF.FITX.HOT"` 是不存在的 symbol;正確命名為 `TC.F.TWF.TXF.*`。下游(現價線/到期預估/ATM)在收到正確 symbol 推播時全部正常 |
| 3 | heartbeat / 斷線重連 + 自癒 | **FAIL** | 斷線偵測與重連本身成功,但 listener SUB socket 不跟隨新 SubPort → 每 30 秒無限重連迴圈(觀測到 24+ 次),自癒 handover 永不收斂,服務卡「回補中」不可自復 |
| 4 | T 字表 ATM 分隔線盤中視覺 | **PASS** | spot=43,150 時分隔線正確畫在 43,200/43,150 之間(spot 值靠 probe 副作用取得,見 item 2) |

另外挖出一個四項之外的 **P0 啟動 bug**(見 F-1)與多個平台事實(見「平台觀測」)。

---

## Item 1:REALTIME push 語意 + rebuilt_cum 一致性 — PASS

**方法**:獨立第二條 TC4 session,對 server snapshot 成交量前 8 檔 SUBQUOTE REALTIME 收 150 秒,收完後 GetHistory TICKS(當日全窗)重建 cum(Σqty),以每檔最後一筆 realtime 的 `PreciseTime` 為界比對。

**邊界一致性(交接協定唯一外部假設)— 8/8 全數 diff=0**:

| symbol(TX4.202607) | rt 訊息數 | 歷史 rows | 界上 Σqty(hist) | 界上 TradeVolume(live) | diff | server volume(稍後) |
|---|---|---|---|---|---|---|
| C.44000 | 789 | 1984 | 3091 | 3091 | **0** | 3094 |
| P.42000 | 872 | 1816 | 2949 | 2949 | **0** | 2950 |
| C.44500 | 564 | 1540 | 2839 | 2839 | **0** | 2841 |
| P.40200 | 255 | 1479 | 2449 | 2449 | **0** | 2451 |
| P.41000 | 724 | 1514 | 2152 | 2152 | **0** | 2157 |
| C.43600 | 829 | 1272 | 2063 | 2063 | **0** | 2079 |
| C.46000 | 74 | 388 | 1946 | 1946 | **0** | 1946 |
| C.43000 | 832 | 1037 | 1964 | 1964 | **0** | 1964 |

(server volume 略大是取樣時間晚幾秒,盤中持續累積;C.46000 完全相等。)

**push 頻率 / 語意**(150s、8 檔、共 4,939 則訊息;訊息間隔 p50=1.5ms(burst)、p95=123.5ms、max=376ms):

- REALTIME 訊息**大多不是成交**:相鄰訊息 `ΔTradeVolume == TradeQuantity` 只佔 ~4–7%(如 C.44000 58/788)。其餘是掛單簿更新重送同一筆 TradeVolume。
- 60 秒補測(3 檔)分類 TradeVolume 序列:`up=4/16/11、eq=215/273/269、down=0/0/0` — **TradeVolume 從不倒退**,非嚴格遞增全是 equal 重送。
- 結論:`ChainAggregator._ingest` 的 cum 嚴格遞增 stale-drop 恰好是正確去重鍵;成交無 conflation 漏計(server volume 與 TradeVolume 相等)。

**判定:交接協定(重建 cum → flush buffer 放行 cum 較大者)假設成立。design §2.3 fallback(T_b 邊界內容去重)不需啟動,原 prompt 預掛的 /auto 條件不成立。**

## Item 2:TXF 現價推播 — FAIL(root cause 已定位,未修)

**現象**:盤中 status=live 後 `snapshot.spot.price` 恆為 `None`,前端「標的現價」「現價到期預估」皆 `—`;server log 無 SUBQUOTE fail(357 檔全報成功)。

**診斷鏈**(全部獨立 probe,未動 server):

1. 訂 `TC.F.TWF.FITX.HOT` REALTIME 60 秒 → SUBQUOTE 回 `{"Success":"OK"}` 但 **0 則訊息**;明確合約 `FITX.202607` 同樣 0。
2. `FITX` 當日歷史 TICKS → 0 rows。
3. `QUERYALLINSTRUMENT Type="Fut"`(12,840 strings)→ **TWF 期貨產品碼裡沒有 FITX、也沒有任何 `.HOT` 葉子**;台指期是 `TC.F.TWF.TXF.202608...`。
4. 訂 `TC.F.TWF.TXF.HOT` 與 `TC.F.TWF.TXF.202608` → **立刻有 REALTIME 推播**(TradingPrice 43234/43150,TradeVolume ~41,000,五檔簿俱全;Quote 的 `Security` 欄位值是 "FITX" — 舊命名只活在該欄位,不在 symbol 樹)。

**Root cause**:`copycat/live/models.py` 的 `SPOT_SYMBOL = "TC.F.TWF.FITX.HOT"` 在現版 TC4 symbol 命名空間不存在;TC4 對不存在 symbol 的 SUBQUOTE 照回 OK(不驗證),故一直無錯誤訊號。

**下游驗證(意外但完整)**:probe 訂閱 TXF 期間,server 的 spot 竟出現 43,150 — 證實 **TC4 SubPort 推播不分 session**(server 用空 topic filter 全收,別條 session 訂的 symbol 也會推進來),而 server 端 `TC.F.*` 分流 → spot → 前端「標的現價 43,150」「現價到期預估 -NT$ 2,049萬」全部正常運作。**壞的只有 symbol 常數一個點。**

**連帶更正**:CLAUDE.md §8 / 07-18 記錄「休市日期貨(FITX)不推 snapshot」的歸因錯誤 — 不是「期貨不推」,是 **FITX symbol 根本不存在**,平日也永遠不會推。另 trade 下單面板的商品清單含 `FITX.HOT`(`orderable_symbols` 引同一常數),同受影響。

## Item 3:heartbeat / 斷線重連 + 自癒 — FAIL(重連成功但永不收斂)

**方法**:10:11:42 kill 達錢 4(TOUCHANCE + TCore64),10:11:45 重啟(user 指示允許)。app 自動登入,port 50774 於 ~190–335 秒後恢復。

**正常的部分**:

- `10:12:12` stale 偵測準時(kill 後恰 30s):`TC4 stale >30.0s, reconnecting...`
- 重連期間 `Connect()` 在 ZMQ REQ 上阻塞等 app 回來(不是 error+backoff 路徑;exponential backoff 分支此場景未觸發)。
- `10:17:20` `TC4 connected(新 session)` → `TC4 reconnected (total=1)` → `self-heal: re-running handover (forced=True)`,前端 badge 正確轉「回補中」,agg reset(ticks=0)、spot 依 DR-13 保留。

**失敗的部分(P0/P1)**:

- `tc4.py _listen_loop` 的 SUB socket **只在啟動時 connect 一次 `self._sub_port`**;`_check_stale` 重連後 `_ensure_connected` 更新了 `self._sub_port`,但**既有 listener 從不重建連線** → 新 session 的推播(含 PING)永遠收不到 → 30 秒後再判 stale → 再重連。
- 實測:`10:17:50` 起**每 30 秒一輪**,至 `10:32:07` 已 `TC4 reconnected (total=30)`,無收斂跡象(觀測至此人工停掉 server)。
- 連鎖效應:每輪重連換掉 `self._api`/`self._session`,把進行中的自癒 backfill(GetHistory 逐檔收割)扯斷 — backfill log 停在 `40/356 symbols`(10:17:49)後再無進度,`handover done` 次數停在 1(僅啟動那次)。**snapshot 卡在 `status=backfilling, ticks=0` 達 15 分鐘(10:17–10:32,直到人工停 server)**,前端持續「回補中」+ 全部歸零(自癒期間不保留 last-known-good 顯示,盤中體驗 = 長時間空白)。
- 對照:trade 端 `tc4_trade.py` 有 generation-following listener(R3-1,conn_info generation 變化即重建 SUB socket)正確處理了同一問題;quote 端缺這一塊。

**判定:斷線後系統不可自復,必須重啟 server。**(修法方向:listener 跟隨 SubPort generation 重建,同 tc4_trade 模式;本次未修。)

## Item 4:T 字表 ATM 分隔線 — PASS

spot=43,150 期間(來源見 item 2 下游驗證),T 字表在 **43,200 與 43,150 列之間**畫出水平分隔線,位置與 spot 吻合;spot=None 時不畫(DR-8),與 vitest 鎖定行為一致。

截圖:
- `docs/specs/txo-aggregate-pnl/screenshots/2026-07-20_live_initial.png` — 盤中主畫面(曲線 + 3 BEP + 「即時連線中」;現價 `—` 為 item 2 現象)
- `docs/specs/txo-aggregate-pnl/screenshots/2026-07-20_tquote_no-atm-line.png` — spot=None 時無分隔線(DR-8)
- `docs/specs/txo-aggregate-pnl/screenshots/2026-07-20_tquote_atm-region.png` — spot=43,150 時分隔線在 43,200/43,150 之間

---

## 四項之外的發現

### F-1(P0):trade 連線失敗 → zmq Context GC 卡死 event loop,server 永不 bind

第一次啟動(無 `TXO_FAKE_TRADE`)時,quote handover 完成後 `TC4 trade 連線失敗,status=touchance_down`(port 51207 不存在,本機達錢 4 未開 trade 服務)— 設計上 trade 失敗不應波及 quote(review B1),但 **port 8721 永遠沒 bind**,uvicorn 停在 `Waiting for application startup.`,CPU ~3%(阻塞非忙迴圈)。py-spy dump:

```
Thread MainThread (idle):
    term (zmq\sugar\context.py:264)
    destroy (zmq\sugar\context.py:322)
    __del__ (zmq\sugar\context.py:140)
    _run_once (asyncio\base_events.py:2062)   ← event loop 內 GC 觸發
```

機制:`tc4_trade._ensure_connected` 建了 `TradeAPI`(內含 zmq Context + REQ socket),`Connect()` timeout 後 raise `TouchanceDownError`,該 api 物件變垃圾;GC 在 event loop thread 跑 `Context.__del__ → destroy → term`,REQ socket 有未決訊息 + 預設 linger=-1 → **無限期阻塞 main thread**。lifespan 的 try/except 接得再好也擋不住 GC 路徑。

影響:凡是 trade port 不通的環境(相當常見 — 達錢 4 沒開下單模組就是這狀態),整個看盤 server 起不來。本次驗證以 `TXO_FAKE_TRADE=1` 繞過後續流程。(修法方向:dispose 失敗連線時顯式 `close(linger=0)` + `context.term()` 於 worker thread,或建 Context 時設 `LINGER=0`;未修。)

### 平台觀測(記入 lessons 候選)

1. **TC4 SubPort 推播不分 session**:任一 session 訂的 symbol,所有 SubPort listener(空 topic filter)都收得到。寫多連線工具(probe/server 並行)時要意識到互相汙染;也是 item 2 下游意外被驗證的原因。
2. **SUBQUOTE 對不存在的 symbol 回 Success=OK**:訂閱成功 ≠ symbol 存在;要驗 symbol 得走 QUERYALLINSTRUMENT 或看有無推播。
3. **REALTIME 訊息 ~93–96% 是簿更新重送**(TradeVolume equal),成交只佔少數;TradeVolume 單調不減。頻率尖峰 p50 間隔 1.5ms,消費端要能吃 burst。
4. **交接期 buffer 用量**:啟動 handover 兩次實測 buffered=99,767 / 109,377(訂閱→回補完成 ~3.5–4.5 分鐘,357 檔)。cap=200,000,若回補拖過 ~8 分鐘(TC4 慢或盤更忙)會溢出 → 無限重跑回補的風險鏈(P2,注意即可)。
5. **達錢 4 冷啟動到 OpenAPI port 可用 ~190–335 秒**(自動登入);斷線重連的等待主要花在這裡。
6. asyncio `socket.send() raised exception` 警告(1/s)於 WS client 斷開後短暫出現,無實害,順帶記錄。

## 建議後續(未動工,等拍板)

1. **P0**:修 F-1(trade 失敗路徑 zmq Context 清理)— 影響所有 trade port 不通的啟動。
2. **P0/P1**:修 item 3(quote listener 跟隨 SubPort generation,參考 tc4_trade R3-1 模式)— 不修則任何一次達錢 4 重啟/斷線都要人工重啟 server。
3. **P1**:修 item 2(`SPOT_SYMBOL` → `TC.F.TWF.TXF.HOT`,並同步更正 CLAUDE.md §8 的 FITX 歸因與 trade 商品清單)。
4. item 1 結論落 CLAUDE.md §8 / memory:交接去重制假設已盤中證實,fallback 免做。
