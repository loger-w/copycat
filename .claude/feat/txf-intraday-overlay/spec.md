# feat/txf-intraday-overlay — 個股分時圖疊「台指期」當日走勢

日期:2026-08-27。流程:`/feat`(HITL grilling 三輪,worktree `C:\side-project\copycat-wt-txf`)。
起因:PR #111 F1 把需求原文「台指」解成加權指數 IX0001;user 原意是**台指期 TXF**(08-26 拍板)。
handoff:`%TEMP%\copycat-handoff-2026-08-27-txf-overlay.md`。

## 0. 拍板(grilling 三輪,全部 user 明示)

| # | 題 | 拍板 |
|---|---|---|
| Q1 | 取代 / 並存 | **並存三顆**「加權 / 櫃買 / 台指期」;加權那條不動 |
| Q2 | 時間軸 | **只畫交集**:依既有 x 窗過濾(現股 09:00–13:30;個股期 08:45–13:45 自然全段);右緣 % = 窗內最後一點,不拉軸、不印 13:30 後的最新價 |
| Q3 | % 基準 | **結算價** = TC4 `ref`(前一交易日日盤結算價;期貨 tab 漲跌顏色 / OI 帶中心同一把尺;15:00 起算的一天只有一個基準) |
| Q4 | 資料流 | **借期貨 tab 的 `useFuturesBars("TXF")`**(allday 5 日,同一 query key → TQ 去重;不新開後端 cache、不多打 TC4)+ 期貨 WS 現價補當分鐘尾巴 |
| Q5 | 線色 | **橘實線**,新 token `--color-idx-txf: #fb923c`(江波圖 TXF 是 base 腿近白色,與均價白撞 → 不沿用) |
| Q6 | 術語 | CONTEXT.md 落三條:台指期 / 加權 / 台指(禁用) |
| Q7 | 期貨 tab 改「15:00 夜盤起算」 | **另開 /mod**,記 `docs/next-time.md`;本案不動期貨 tab 的一天定義 |
| Q8 | `useChartToggles` 跨 instance 同步 | **做**(🔴 獨立 commit):module-level store + `useSyncExternalStore`,任一處 set → 全部持有者同步 |
| Q9 | seams | **S1 + S2 + S3**(§4) |

## 1. 使用者看到什麼

- 個股單檔頁與群組圖牆的分時圖 toggle 列多一顆「台指期」(排在「櫃買」之後),預設**關**。
- 開了:一條橘色細實線疊在個股價線上,右緣小標「台指期 +0.35%」(相對結算價 %,映到個股價格軸,
  讀法同加權線:個股價線在它之上 = 今天比台指期強)。
- 反灰:個股無昨收(tooltip「無結算價」—— 台指期的基準是結算價,不叫昨收;review round 1 S2 回校)/
  期貨引擎未就緒或 TXF 結算價不可得(tooltip「無台指期資料」)。
- index WS **或**期貨 WS 任一中斷時標籤加註「(中斷)」(補尾現價走 index WS、結算價走期貨 WS,哪一條斷了
  數字都不能當「現在」讀;review round 1 Spec 2 回校);bars 抓不到(`meta.source === "unavailable"`)
  → 線不畫、鈕不反灰(資料是可回復的,TQ 60 s 輪詢會補上)。
- 夜盤不疊(現貨無盤);非交易日 / 盤後看盤 → 疊的是與個股同一個「最近交易日」的日盤段。

## 2. 資料流

```
App
├ useFuturesStream()  ──► products.TXF.ref(結算價;一天一變)+ wsStatus          (既有,常駐)
├ useIndexStream()    ──► txf {p, time}(index engine 每拍 ~1 s 轉供的台指期現價)+ tradeDate + wsStatus
├ useChartToggles()   ──► toggles.idxTxf                          (Q8 後跨 instance 同步)
├ useFuturesBars("TXF","intraday", active = wanted, enabled = wanted),wanted = tab==="stock" && toggles.idxTxf
│      └ queryKey ["futures-bars","TXF","1",5,"allday"] 與期貨 tab 同鍵 → 一份 cache、一支輪詢 timer
├ txfBarsToSeries(bars, {p, t: time, date: tradeDate}, ref, stale) ──► IndexSeries | null   (S1 純函式,useMemo)
└ indexOverlay = {twse, otc, txf} ──► StockPage → StockChart / GroupGridView → … → IntradayChartCore
                                        └ buildIndexOverlayLines(series, on, ref, g, w, xw)(既有,擴 txf 鍵)
```

- **閘 = 個股 tab + 鈕開著,同時餵 `active`(輪詢)與 `enabled`(掛載即抓 / 回焦重抓)**:只停輪詢擋不住
  後兩者,鈕關著仍會每次回焦打一發(review round 1 S1/P1 回校)。鈕關著零請求;期貨 tab 若同時在輪詢,
  TQ 同鍵只跑一支 timer。`useFuturesBars` 新增第四參數 `enabled`(預設 true,期貨 tab 不傳)。
- **補尾現價不用期貨 WS**(實作期回校):期貨 WS 是 0.1 s coalesce 流,序列 identity 每變一次圖牆 50 張卡的
  memo 就被打穿一次;改吃 index engine 每拍(~1 s)轉供的 `txf` 報價,節奏與加權線同級。結算價仍取期貨 WS。
- 鈕關著時餵空料(bars / quote 皆空),series 只隨 ref / stale 換 identity(鈕仍能判「有沒有台指期資料」)。
- **不新增 TC4 訂閱、不動後端**。

## 3. `txfBarsToSeries` 語意(S1)

輸入:`bars: readonly Bar[]`(allday 5 日,升冪)、`quote: {p, t, date} | null`(期貨 WS)、`ref: number | null`、
`wsStale: boolean`。輸出 `IndexSeries | null`(`{p, ref, high, low, stale, minutes}`,與加權 / 櫃買同形 →
`buildIndexOverlayLines` 零改動吃得下)。

1. **錨定日** = `anchorDateOf(最後一根 bar)`(`lib/allday.ts` 既有;凌晨 ≤05:00 屬前一日),且**必須等於
   `quote.date`(個股頁的交易日)**,否則整條不疊(交易日凌晨 05:00–08:46 bars 還錨在前一日;review round 1
   Spec 5 回校;quote 沒給日期時不擋)。只取 `t` 日期 = 錨定日且 **HHMM ∈ [0846, 1345]**(日盤段;夜盤
   1501–2359 / 0000–0500 剔除)。
2. **分鐘鍵 = bar 終點標記 − 1 分**:期指 1K 是終點標記(08:45 開盤首根標 0846),個股 / 指數的分鐘鍵是
   起點(09:01 那分鐘的價鍵 `0901`;tc4-market-facts 期指節 (d))。不減一,整條線右移一格,兩張圖都畫得出來零訊號。
3. **0 價閘**:`c <= 0` 整根剔除(TC4 偶發 "0",後端原樣轉 0;同 `futures-overlay.ts::usable` / `futuresBarsToAccum`)。
4. **WS 補尾**:`quote.date === 錨定日` 且 `quote.t` 的分鐘 > bars 最後一根換算後的分鐘 且落在日盤段 → 追加
   `{HHMM: p}`。bars 每 60 s 才更新,沒有這步線尾永遠落後最多一分鐘。**不覆寫**既有 bar 分鐘(bar 是收盤價,
   WS 是瞬時價,兩者不同尺)。
5. `ref` null / ≤0 / NaN → 回 **`null`**(= 「無台指期資料」,鈕反灰;review round 1 Spec 4 回校:回 `{ref:null}`
   會讓鈕可按、線永遠不畫 = 零訊號)。bars 空 → `minutes = {}`(線不畫、鈕不反灰;不當錯誤)。
6. `stale = wsStale`(index WS 或期貨 WS 任一非 open);`p` = 依分鐘最大者(與 lastMinute 同尺,輸入亂序不分家);
   `high/low` **恆 null**(分鐘收盤價的極值與 `IndexSeries.high/low` 後端口徑不同、無讀者;review round 1 S7 / Spec 3)。

## 4. Seams(user 拍板 Q9)

- **S1** `frontend/src/lib/txf-overlay-series.test.ts`(純函式):錨定日 / 日盤段 / 夜盤剔除 / 終點標記 −1 /
  0 價 / ref 缺 / 補尾只在 bars 之後且不覆寫 / 空 bars。加 `index-overlay-lines.test.ts` 一條:`txf` 鍵映到 y 域。
- **S2** `frontend/src/hooks/useChartToggles.test.ts` 加一條:兩個 instance,A `set` → B 的 `toggles` 同步。
- **S3** `StockIntradayChart.indexlines.test.tsx` 加一條:`idxTxf` 開 → `data-testid="index-line-txf"`;
  `GroupGridView.test.tsx` toggle 表加 `["idxTxf", "台指期"]`。

## 5. 不做 / 白名單

- 不動期貨 tab、不動後端、不加訂閱。
- 不把 x 軸拉到 08:45(Q2)。
- `TOGGLES_VERSION` 不 bump(新鍵,舊存檔自然補預設;同 `vp` / `fills` 條)。
- index / futures mode 的 IntradayChartCore 不給鈕(同 F1)。
- 江波圖調色盤不動(F4 契約:色數 ≥ 腿數,與本案無關)。

## 6. Tickets

| # | 類 | 內容 | blocked by |
|---|---|---|---|
| T1 | 🔴 | `useChartToggles` 跨 instance 同步(S2) | — |
| T2 | 🟢 | `lib/txf-overlay-series.ts` + `index-overlay-lines.ts` 擴 `txf`(S1) | — |
| T3 | 🟢 | 接線:App 掛 hook / `ChartToggles.idxTxf` / 兩處鈕 / token / 線色(S3) | T1, T2 |
| T4 | 🟢 | docs:CONTEXT.md 三條 glossary、next-time Q7、CLAUDE.md §4 契約補一行 | — |

## 7. Done

`npm test` + `npx tsc -b` + `npx eslint src` + react-doctor(changed)全綠;後端 gate 不動 code 仍跑
`pytest -q`(docs 改動不影響);two-axis review 處置完;closeout 全鏈;UI 截圖(claude-in-chrome
既有 session,prod preview)進 `evidence/`。
