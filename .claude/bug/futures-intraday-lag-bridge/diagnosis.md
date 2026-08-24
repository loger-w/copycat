# bug/futures-intraday-lag-bridge — 診斷紀錄(diagnosing-bugs 六 phase)

User 症狀(2026-08-25 01:xx):「期貨有時候分時圖會出現線的交易不連貫;切到 K 線圖發現 K 線也還沒載入,
K 線載入完成之後分時圖就正常了。」

## Phase 1 — feedback loop

**指令**:`npx vitest run src/components/futures/FuturesChart.test.tsx -t "gate 5"`(frontend/;< 1 s;fake clock + fetch mock,確定性)。
**紅在什麼上**:bars 至 D 10:00、WS 最後成交 11:29:30、牆鐘 11:30 → 主價線 `polyline` 的點數由 2 變 3
(多出 live 索引 11:31 那一點)= core 單條 polyline 從 10:00 直線拉到 11:31 —— 就是 user 看到的「線不連貫」
(一段橫貫 90 分鐘的假直線)。紅態輸出:`expected 3 to be 2`。

定位事實(不含假說):
- 分時與分 K **共用同一份** `tf=1&session=allday` query(`useFuturesBars`)→ 「切到 K 線還沒載入」只可能是**日 K**(`tf=D`,獨立 query)。
- 日 K 對分時線的唯一影響是 CDP/MA overlay,動不到價線 → 「日 K 載完分時就正常」是**同一次 TC4 忙碌的兩個面**,不是因果。
- `IntradayChartCore` 的價線 = **一條** `<polyline points={pts(g.priceLine)}>` → 任何缺格一律直線架橋。
- 後端 `bars_range` 把當日段 `HistoryTimeoutError` 吞成 `[]`;`/api/market/bars` 再把 `build_minute` 的三態 status 丟掉
  (`bars, _ =`),`meta.source` 只看 bars 空不空 → 當日段不完整時前端**零訊號**。
- prod log(08-24,舊碼 8f8ce439):TXF 69 次 1K timeout **全部**是週日 08-23 歷史段探測(#93 已修未部署),當日段
  timeout 0 次;「分頁靜默截斷」本來就不會留 log。當下(01:46)prod 序列健康(尾根 = 牆鐘、零缺格);
  背景輪詢 `bars_lag_poll.py` 每 20 s 記尾根落後與缺格,守整晚(scratchpad `bars_lag.log`)。

## Phase 2 — 重現與最小化

最小重現 = 兩根 bar(09:00 / 10:00)+ `state.t = "11:29:30.000"` + 牆鐘 11:30。每個元素都 load-bearing:
拿掉 `state.t` 的落後(改 10:00:10)→ 綠(對照組「TMF 夜盤空檔」);牆鐘退到 10:01 → live 索引 = 末根 + 1 → 綠。

## Phase 3 — 假說(排序;user AFK,依此順序推進,回報時請 user 重排)

| # | 假說 | 可證偽預測 | 狀態 |
|---|---|---|---|
| H1 | TC4 當日段分頁「首頁已備妥但尾巴還在長」→ 後端回截到某分鐘的序列,`_today` 快取 30 s;下一輪補齊 | 若成立,背景輪詢會在某輪看到 `lag_min` 跳大、下一輪歸零;log 無痕跡 | 輪詢守夜中 |
| H2 | 當日段首頁 10 s timeout → `bars_range` 吞成 `[]` → 回歷史段 | 若成立,序列尾停在前一錨定日 05:00 → **錨定日 gate 會擋 live 點,畫面是「整天舊圖」不是架橋** → 與症狀形不符,只能解釋「日 K 載不出」那半 | 排第二 |
| H3 | 跨午夜後昨日段永久 memo 時分頁靜默截斷 → 永久缺格 | 若成立,缺格**不會**在一分鐘後自癒(與「後來正常」不符);重啟前一直在 | 排第三;同結構風險記 next-time |
| H4 | TC4 偶發 0 價 bar 被 adapter `c <= 0` 整根丟掉 → **中段挖洞**架橋(review SP1 補) | 若成立,缺格在序列中段、下一輪 TC4 修正後自癒 | gate 5 **不涵蓋**(只比尾根);記留尾 |

H1–H3 在畫面上收斂到同一條機制:**live 點無視「資料尾落後於成交」,把資料尾與現在直線相連**;H4 是同症狀的另一條路(中段),本輪未修。
**資料側根因(H1/H2 何者為真)截至出貨未被證實** —— 背景輪詢守夜中,只證明了畫面層的機制與修法。

## Phase 4 — instrument

不需要額外 log:Phase 1 的 loop 直接在 seam 上區分了三個假說共同的畫面機制;
資料側的證據由 `bars_lag_poll.py`(唯讀 GET,20 s)蒐集,不動 prod code。

## Phase 5 — fix + regression test

seam 正確(元件 + fetch mock + fake clock,就是真 caller 的路徑)。紅先行 `e6fbcd5c` → 修 `1903eae2`:
`FuturesChart` live 點加 **gate 5**:`tradeSlotOf(state.date, state.t).index − tailIndex > FUT_LIVE_LAG_MAX(5)`
且成交與末根**同錨定日** → 不追加 live 點,改印「分時資料落後 N 根(TC4 回補中)」(與模式列同一行,不抽圖高)。
判準吃 **WS 最後成交**而非牆鐘:TMF 夜盤數分鐘零成交是常態,那種空檔 bars 本來就無可補,拿牆鐘比會把
「沒人交易」講成「回補中」(對照組測試釘住)。review 收修 `7e8ac3a5`:SP2(t 停在前一場次 → 同錨定日守門)、
SP4(整分成交終點標記不 +1;門檻 3 → 5)、ST1(差 6 擋 / 差 5 放行邊界案)、ST4(提示併入模式列)、
SP3/ST5(N = 近全軸缺的 1K 根數,文案講「根」)。`db804b87` 🔵 `hhmmOf` 共用(ST3)。

## Phase 6 — cleanup

零 `[DEBUG-…]` 植入;prototype 零;背景輪詢是 scratchpad 一次性腳本(收尾停掉)。

## 反向驗證(/bug 自家 gate)

`git stash push -- FuturesChart.tsx` → `-t "gate 5"` **紅**(`1 failed`)→ `git stash pop` → **綠**(`1 passed`)。

## Blast radius

`FuturesChart` 唯一 caller = `FuturesPage`;gate 5 只影響「live 點是否追加」與一行提示;`state.t` null / 壞格式 / 死區 → gate 5 不參與(逐字回到四道 gate 的舊行為)。
K 線模式不讀 live 點。既有 40 案(含四道 gate 的五案)未改。
