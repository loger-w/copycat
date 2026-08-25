# 2026-08-25 「做」批 8 PR 整體 review(#99 → #106)

新 session 乾淨視角,對 08-24 17:38 → 23:59 依序 rebase merge 進 master 的 8 個 PR 做整體 review。
fixed point `5f9d02b0`(R4 之前的 master)→ HEAD `3fabfc7e`;128 個原始碼檔 / +6915 −1026。

## 0. 方法與 gate

- `code-review-two-axis`,**逐 PR** 各派 Standards + Spec 兩個 opus reviewer(7 組 14 支),外加 1 支跨 PR 整合
  reviewer(同檔多 PR 重疊 / CLAUDE.md §4 契約交叉 / 時序交互 / 測試母體 / docs 同步)。
  每支都拿到 round-1 JSON,要求**重審被反駁的 finding**,並「對 diff 核,不信自述」。
- 主 session 獨立重跑 gate:pytest **3031 passed**(184 s)/ vitest **147 檔 2782 passed** / ruff / pyright 0 /
  `tsc -b` 0 / `eslint src` 0 —— 與 handoff 數字一致。`copycat validate` 未重跑(本輪無 replay 產物改動)。
- 主 session 親核了每個 PR 最嚴重的 1–2 條(下文標【親核】),兩處把 sub-agent 的等級**降級**、一處**推翻機制**
  另立一條較窄的真風險(§2.5)。

commit 邊界(線性;以「chore(docs): next-time 勾銷」分界):

| PR | 範圍 | 條 |
|---|---|---|
| #99 R4 WS 韌性 | `5f9d02b0..a26b0410` | 6 |
| #100+#102 /bug 期貨分時架橋 | `a26b0410..4b9440f1` + `5595bf11..9a5b5ef6` | — |
| #101 R5 前端狀態批 | `4b9440f1..5595bf11` | 13 |
| #103 R6 群益下單批 | `9a5b5ef6..979cb511` | 12 |
| #104 R7 bars / 引擎批 | `979cb511..4fab4992` | 13 |
| #105 R8 TC4 深水區 | `4fab4992..7ad28906` | 11 |
| #106 R9a storage 收斂 | `7ad28906..3fabfc7e` | 1 |

## 1. 各 PR 兩軸最嚴重(不跨軸排名)

| PR | Standards 最嚴重 | Spec 最嚴重 |
|---|---|---|
| #99 | P2 N037 節流模型:測試 timer 全凍 vs 註解「拉成 1/min」矛盾,收益零證據 | P2 SP4 錯端點留在新 docstring;N036「≤ 25 s」漏 boot 期間載入情境(實為 29 s) |
| /bug | P2 [judgement] `tradeSlotOf` 純函式留在元件檔,`carry` 分支零案 | **P1** 門檻 3 的量測路徑(20 s poller)≠ prod(60 s 輪詢 + 30 s 快取),零餘裕;**P1** 尾端 0 價 bar 不在 gate 5 帳上 |
| #101 | P2 [judgement] `PARAM_DEFAULTS` 與 `PARAM_FIELDS` 分居無鎖 | **P2** N115 收修讓改名撞名靜默清掉輸入,與 change-spec 申報不符無鎖 |
| #103 | P2 `_Agg.date` 語意與 skill 衝突(親核降自 P1) | **P2** N075 綁定後仍留「同 seq + 同檔 + 同方向」誤標窗,docstring 宣稱已封 |
| #104 | **[hard]** CLAUDE.md §4 契約段產生點型別(`BarsResult`)與 code 不符 | 中 N105 休市日窗內噪音未消,change-spec / SC-2 仍宣稱「零筆」 |
| #105 | **P2** run.ps1 15 s 只算一條 session,實為五條序列 close + capital 5 s | P2(親核合併)同左;P3 `except (OSError, ValueError)` 漏 ZMQError 為 latent |
| #106 | [hard] `storage.ts:27-28`「全 repo 唯一 inline disable」事實錯 | P2 verification 引 8 個 SHA 全非 master 祖先(系統性,見 §4) |
| 跨 PR | — | **P1** `ops-discipline` skill 仍寫「首則 ping 才武裝」(#99 已退役) |

## 2. 逐 PR

### 2.1 #99 R4 WS 韌性(`mod/ws-resilience`)

**Standards**
1. P2 —【N037 節流模型自相矛盾】`ws-reconnect.test.ts:629` 的 `hideFor` 是 hidden + `setSystemTime`,timer **完全不跑**;
   `ws-reconnect.ts:157` 註解與 change-spec §1 卻寫「throttling 把 5 s tick 拉成 1/min」。若真是 1/min,tick 仍跑、
   Edge 13 守門(:156-161)每次刷新 `lastMsgAt`,回前景 grace 後 `now - lastMsgAt` 最短 ~5 s → 半死連線不判定,
   偵測退回最壞 ~30 s,不是宣稱的「≤ 5 s + ε」。四條 visibility 案全在「timer 全凍」模型下綠 + round-1 SP2 已記
   「真環境未驗」→ N037 收益零證據(鐵則 D)。補一條「節流 tick 以 60 s 間隔真的跑」的案。
2. P3 [hard] — `tests/server/test_breadth_routes.py:408` docstring 寫不存在的 `/api/breadth/state`(實際 `/api/market/breadth`);
   round-1 SP4 宣稱「路徑改正」只改了 `app.py`。
3. P3 [judgement] — `ws.py:100-104` close_sent marker 是與 uvicorn / starlette 的逐字字串契約,無版本 pin、無 parity;
   升級改字即靜默退回整段 traceback。且無法區分「對端已斷」與「relay 自己 send-after-close 的 bug」。
4. P3 [judgement] — `f1300466` 標 🟢 但內容是純測試 `[red]` commit。

**Spec**
1. P2 — 同 Standards 2(SP4 只改一半)。
2. P2 —【N036 漏一種情境】25 s 只對「分頁一直開著、server 消失後重啟」成立;若分頁在 boot 期間才載入 / 重整,
   第一發就撞 accept-then-close,新序列 1/3/7/15/31/61,boot 落在 31 s 剛過時最壞多等 **29 s**。verification §6 偏樂觀 4 s。
3. P2 —【SP3 grace 反向代價未申報】`graceUntil = now + tickMs`(:139)只由 hidden→visible 觸發、不分是否真凍結;
   分頁只切走幾十秒回來,下一個 tick 落在 grace 內被 :162 跳過 → 真半死偵測延後一整個 tick,最壞 ≈ **10 s**。
   極端:每 < 5 s 切回一次,watchdog 可被無限期壓住。
4. P3 — N038 jitter 對背景分頁完全無效(Chrome 1 s 對齊),E5 判 PASS 偏寬;§6 留尾未收。
5. P3 — N039 只包 relay `_send` / `_beat`;route 層首則 seed send(`app.py:1206/1790/1813/1856`)仍只 catch
   `WebSocketDisconnect`,close_sent traceback 噪音仍在;留尾未申報。

核過無問題:`WS_SILENCE_TIMEOUT_MS` 30 s > `WS_HEARTBEAT_SECS` 10 s 契約成立;visibilitychange 無 listener / timer 洩漏;
7 處 `close()` 全在 accept 前、第 9 處 `/ws/txo-pnl` 本無缺席分支;ST2 / ST4 / SP5 反駁站得住;白名單外零改動;
reviewer 重跑後端 68 / 前端 35 passed。

### 2.2 #100 + #102 /bug 期貨分時 live 點架橋(`fix/futures-intraday-lag-bridge`)

**Standards**
1. P2 [judgement] — `FuturesChart.tsx:95-108` `tradeSlotOf` 零 React 依賴,家在 `lib/allday.ts`(有單元測試層);
   `carry` 跨午夜分支目前**零案**。
2. P3 [judgement] — ST3 去重只做一半:`hhmmOf` 抽了,`alldayIndexOf → null 檢查 → anchorDateOf(...)` 串在 :99-107 與
   :129-133 仍逐字重複;真正的共用單位是 `slotOf(date, totalMinutes)`。
3. P3 [judgement] — gate 鏈 IIFE(:246-273)該抽 `resolveLiveSlot(...)` 純函式,五道 gate 才能直接單測。
- 備註:`26f869ff` 用 `test(` type 不在 CLAUDE.md §6 值域,但近 300 筆有 83 筆 → 該修的是 §6 漏列。

**Spec**
1. **P1** —【門檻 3 的實證路徑 ≠ prod】證據是 20 s 輪詢腳本,但前端 `POLL_MS = 60_000`(`useFuturesBars.ts:25`)+
   後端 `TODAY_TTL_SECS = 30.0`(`bars.py:42`);常數註解(:58)自列「常態 ≤ 3 格」而門檻 `> 3`(:267)= **零餘裕**。
   round-1 SP4「門檻 3 與常態 2–3 格貼邊會閃動」曾 accepted 改 5,round-2 改回 3 時引的量測不含那 60 s,等於未真正
   回應 SP4。建議 4,或以 60 s 取樣覆量一輪日盤開盤。【親核:三個數字屬實】
2. **P1** —【尾端 0 價 bar 不在 gate 5 帳上】`tailIndex`(:239-244)只跳索引不可解的 bar,未套 adapter(`futures-accum-adapter.ts:47`)
   的 `c <= 0` 跳過 → 畫的尾 ≠ gate 5 比的尾,尾端 0 價 bar 會少算落後、照樣架橋無提示。verification 只把 0 價列成
   「中段」留尾,尾端這條屬 gate 5 職責。【親核屬實】
3. P2 —「H1 證實」超出證據:§4b 是黑箱 GET,只證「資料尾落後真成交 4–5 分且事後補齊」(症狀);H1 主張的機制
   「分頁首頁已備妥但尾巴還在長」證不到 —— TC4 上游晚生成給一模一樣的曲線。應收斂成「症狀證實、機制未定」。
4. P2 — H3(昨日段永久截斷)是中段缺格,gate 5 只比尾根,diagnosis.md:37 宣稱涵蓋但結構上不涵蓋。
5. P3 — 已證實事件的覆蓋率未申報:02:44 diff 恰 3(不擋),約 02:45 才 > 3 → 提示只出現最後 ~1 分鐘。
6. P3 — 切回 tab:inactive 停輪詢,回 tab 後最多 60 s 無新 bars,期間印「TC4 回補中」—— 不架橋對、歸因錯;無測試。
- 修法層級:H1 成立下前端閘是正確層級,但 diagnosis 未正面論證(core 單條 polyline 對任何缺格架橋才是結構根因,
  SP1 以「不擴 scope」帶過)。scope creep 無。

### 2.3 #101 R5 前端狀態批(`mod/frontend-state-batch`)

**Standards**([hard] 0 條;ST3 收修核 diff 通過:`CapitalConfirmDialog.tsx:94-97` 旗標在 `onCancel()` 之前)
1. P2 [judgement] — `list-drag.ts:41-45` 六個位置參數 = `zonesNow()` 完整回傳,`WatchlistSidebar.tsx:340 / :369` 逐字重複
   (Data Clumps)。
2. P2 [judgement] — `FuturesLadder.tsx:99-105` 是 `futExchangeContract` try/catch→null 的第 5 份;`catch {}` 無 narrowing。
3. P2 [judgement] — `PARAM_DEFAULTS`(`SignalRulesDialog.tsx:38`)與 `PARAM_FIELDS` 分居兩檔,鍵集無機械鎖、無
   「預設值落在 [min,max]」斷言;漏改 → 表單空白 → 泛用 INVALID_RULE,正是 N055 要消滅的樣態(現值合法,latent)。
4. P3 — `RiverOverlay.tsx:84 const toX = xOf` 純別名(與本輪 ST7 處置不一致)。
5. P3 — `lib/fee-discount.ts:12/21` `DiscountState` / `loadDiscount` 已無外部讀者。
6. P3 — `voidBelowY` / `voidAboveY` 命名反直覺。
7. 測試微瑕 — `RiverPanel.memo.test.tsx` 偽造 default export;直呼 `actual.RiverOverlay(props)` 日後包 `memo()` 會 throw。
- commit:除已記錄的 N266 外無第二處混類;parity fixture 兩邊確實同讀一份檔。

**Spec**(13 條全部落地無漏做;W1–W10 無破口;W5 次序自述與 diff 相符)
1. **P2** —【N115 收修引入未申報 UX 回退無鎖】`components/stock/WatchlistManagerDialog.tsx:116` `setRenaming(null)` 在
   `commit` 前**無條件**跑;改名撞既有名時編輯框關閉、輸入消失,錯誤才經佇列非同步冒出。change-spec 說 eager
   「降級為純 UX(決定要不要清輸入框)」—— 那一半沒留下;這是最常見路徑。verification §5 只申報「新增群組」輸入框。【親核屬實】
2. P3 — `WatchlistManagerDialog.tsx:420-431` 註解宣稱 `aria-label` 帶組名,實作只有 `上移 ${code}`。
3. P3 — `useWatchlistCommit.ts:118` `base === null` 早退(擋「空殼整份 PUT 清空自選」)無測試、不在 M1–M9。
4. P3 — N055 契約只釘一半:`COOLDOWN_MIN/MAX`(60/86400)前端硬抄未進 parity;後端 `INT_PARAM_KEYS` 拒非整數而前端
   無對應 → 填 `2.9` 仍拿泛用 INVALID_RULE。
- 特別項:N068 已宣告「做」、方向與申報一致,`useCapitalStream` 無條件 15 s(240 req/h)停 TXO / 廣度頁零讀者照打
  (SP2 已申報);N115 撞名未變靜默(transform null → BAD_GROUP → errText);N266 slot 算術正確;佇列交錯是真交錯;
  N114 契約有 lock 但 `requestCancel` 違約案未測。

### 2.4 #103 R6 群益下單批(`mod/capital-order-batch`)— 真錢路徑

**Standards**
1. P2(親核降自 P1)—【`_Agg.date` 語意前提錯】`store.py:175-196` / `client.py:840-845` 反覆稱它「委託建立日 / 委託日」,
   skill `tc4-market-facts:218-222` 明載是**最新事件日**(`apply_reply` 有值就覆寫)。親核推演:日盤單 days=(0824,)
   被隔日事件推日期 → 出 days → 只缺標籤(fail-safe 仍成立);夜盤單 (0824,0825) 被隔日同 seq 同檔同方向外部單撞 → 誤標
   = Spec 1 同一個窗,語意衝突沒有再把窗拉寬。結論:docstring 前提錯 + 窗未封 + 無測試,與 Spec 1 併一條。
2. P2 [judgement] — `flash-locked` 兩個產生點:`flash-send.ts:52-61` `flashSource` 自陳「六個送單點共用」,`FuturesLadder.tsx:279`
   手寫字面值、`close-order.ts:40` 型別又寫一次。
3. P2 [judgement] — `store.py:81` `_price_types` 4-tuple 位置存取(:206 / :221 / prune),測試斷 `[1]` / `[2:]`
   (`test_client.py:2015-2017`);同 package `balance.py` 已有 NamedTuple 慣例。
4. P3 [hard] — `test_client.py:1998` 行長 107 > 100(E501 未 select,ruff 綠 ≠ 合規)。
5. P3 — `test_capital_api.py:1135-1140` `_audit_lines` 與 `test_client.py:103` 逐字同款 + 函式內 `import json`。
6. P3 — `capital_api.py:220-227` 與 `:195-202` tick 閘尾段六行逐字相同,docstring 自陳 scope 相同卻未抽。
7. P3 — `close-order.test.ts:23-35` `as unknown as` 雙重轉型 + 遮蔽既有 `pos()` 工廠。
- 核過無問題:無三類混類;fixture 48 欄與 `reply.py` 一致;審計 append-only 未動;deque 用注入 clock;`BAD_TICK` 走
  `detail.error`;`_calendar` catch 有具體降級;ST2 / ST4 rejected 維持。

**Spec**
1. **P2** —【N075 誤標窗未封,docstring 過度宣稱】綁 `stock_no + buy_sell` 只擋「標的或方向不同」;跨日 seq 重用 + 他處
   (群益 APP)對**同檔同方向**下限價單撞同 seq → `_price_type_of` 三項全過仍誤標市價;期貨路徑更寬(`client.py:891`
   只綁方向,stock_no=None)。code 對「跨日 seq 重置」零假設零測試;`test_store.py:466` 只釘不同標的 / 不同方向。
   `store.py:196`「回到『只缺標籤、不誤標』」與實作不符(change-spec §4 措辭反而準確)。
2. 三道閘零改 —【證實】`safety.py` / `CapitalConfirmDialog.tsx` 零 diff;`client.py` 未觸 `check_*` / `_record` / `_audit_*`;
   三個前端改動皆「收緊進入 / 放寬解除」,無新一鍵送單路徑。
3. N099 — **code 已鎖**(`RightRail.tsx:57` `isOrderBlocked` → `() => null`),不是待確認態;誤鎖面保守(`unit` 有值看
   `STOCK_FUTURE_UNITS`,null 才看 0 開頭 → 只 ETF)。→ user 要知情「spec 說待確認 / code 已落地」。
4. 欠帳 deque — 到期即丟棄不補償;與 #84 同一套 `STALE_WINDOW_S = 20`,只從單一 deadline 改逐筆;交錯推演不會比舊版
   更易瞬清。
5. WS 斷線 — `closed → conn_lost` 清 armed + locked(`flash-arm.ts:79` 既有);`connecting` 只擋再武裝;解除不留審計。
6. P3 — N082 只覆蓋梯上路徑:`CapitalPositionsList.tsx:49` `closeBodyOf` 不帶 source → rail 部位清單鎖定態平倉仍記
   `panel`;`RightRail.tsx:134` 已持 `armCtl` 做得到。
7. P3 — `_trade_ymd` 降級只做一半:`client.py::_calendar` 只 catch `(OSError, ValueError)`;`next_trading_day` 60 天找不到
   raise `RuntimeError`,`_note_price_type` 在 `_audit(record)` **之前**且無 try → 吞掉該筆晚到結果的審計行。
8. P3 — change-spec §1 N075 寫「事前標該變:無」,實際收修改了 3 條既有 client 測試 fixture(3357→2330);§4 有記 §1 未更新。
- scope creep 無;next-time 刪 12 條逐條對得上。

### 2.5 #104 R7 bars / 引擎批(`mod/bars-engine-batch`)

**Standards**
1. **[hard]** —【CLAUDE.md §4 契約段產生點型別過期】`CLAUDE.md:206` 寫 `futures_engine.py::bars_range`(`BarsResult`),
   但同分支 `3bac3e30`(ST3)已改回裸 tuple(`futures_engine.py:295` 明寫),`BarsResult` 到 `app.py:1662` 才組;漏記
   值域持有者 `stock_source.py::BarsStatus`。先寫 doc(`7e3b96fe`)後改型別,沒回校。【親核屬實】
2. P2 [judgement] — `useMarketBars.ts:24` 與 `useStockBars.ts:38` `BarsStatus` 值域雙份(後者有 `STATUSES` 執行期收斂,
   前者沒有)。
3. P2 [judgement] — `app.py:1634` `key == "TWSE"` vs `:1689` `key in FUTURES_MARKET_KEYS` 兩種表達「哪條路有 status」;
   TWSE 閉包 `:1644` 先捏 `"ok"` 餵 cache、50 行外才擋(Shotgun Surgery)。
4. P3 — `river_state.py:35` `_RANK_CLOSE_AUCTION` 零引用,`:97 / :130` 仍裸 `2`;`:101` `rank or _RANK_TRUE` 借 falsy。
5. P3 — `index_engine.py:176/180` `_is_trading_day`(恆 True)+ `_has_calendar` 同名兩義(`:505` vs `:608`)。
6. P3 — `test_index_engine.py:299/321/341` 正向斷言用固定 `sleep(0.3)`(同檔有 `wait_until` :810);`test_stock_source.py:352`
   `spy` 缺回傳型別。
7. P3 — `test_signal_routes.py:895` docstring N020 應為 N110;`FuturesChart.test.tsx:252` `textFor` async 零 await。
- 三類 commit 逐 show 核:零混類,🔵 `3bac3e30` 純重構(git mv 事故已收乾淨);`bars.py` / `futures_source.py` /
  `overlay.py` 零 diff。status 沿鏈 Literal 型別化;`build_minute` 走 `_STATUS_SEVERITY` 排序表;`HistoryTimeoutError`
  except 具體轉 `"timeout"`。

**Spec**
1. 中 —【N105 休市日噪音只做一半,spec / 驗收與 code 牴觸】SP1 收修後窗內段不吃日曆(`index_engine.py:604-606`),
   `in_watch_window_now` 純看牆鐘(:83-86)→ **休市日 09:04–13:25 仍每 60 s→900 s 空打**。但 `change-spec.md:138`
   仍寫「新碼一發都不打」、`verification.md:166` SC-2 仍寫「休市日整天零筆」(測試已誠實改名)。user 照 SC-2 驗會誤判
   回歸。要嘛改口「盤外零筆、窗內照舊」,要嘛補窗內閘(會帶回「日曆誤標整天不自癒」→ 需 user 拍板)。
   其餘各段時間表推演正確(盤中逐字舊行為、有日曆交易日 13:25–24:00 開、00:00–09:00 兩邊關、無日曆退 13:25–13:40)。
2. 中 → 【親核:reviewer 的機制不成立,另立一條較窄的 P3】reviewer 主張 `_subscribe_and_backfill` worker 先讀
   `_pending_date` 再 `.update()` 可被 `_swap_day` 插隊 —— 實際 `_merge_backfill`(:306-311)在 `_retry_loop` `await to_thread`
   返回後於 **event loop** 執行,檢查到 update 之間無 await,插不進來(:279 是 docstring 行)。但同區有另一條本輪新增
   的真風險:heal retry 的 `fetch_day_minutes` 在 rollover `set_trade_date`(:520)**之前**起跑、之後返回 → 抓的是**舊日**
   整天分鐘,卻因 `_pending_date` 已設寫進 `_pending_backfill`(:311),swap 時當最低層疊進新日(:554);新日 08:3x 只有
   零星鍵 → 舊日 09:00–13:30 整段留在新日線上直到逐分被覆寫。改動前這份落進舊日 dict、swap 整份替換所以無害。
   前提:retry 跨夜活著(TC4 整夜斷線 ConnectionError 續試;rollover :511-514 不 cancel retry)—— 窄。修法:rollover
   設 pending 時 bump `_retry_epoch`,或 merge 帶日別 tag。
3. 中低 —【N024 前置閘倒置】原文「要動之前先量」;本輪先把 1K fallback 窗 40→20 日曆日(n≤5)才把量測排 SC-1 事後補。
   推演 20 日扣春節 9 天餘 7–8 平日,冷啟動不缺 → 安全;但 verification §5「不是沒量所以不動」講的是 n=25 那半,
   真沒量的是縮的那段。SC-1 保留硬未結。
- 通過:status 不謊報(`app.py:161-170` 只在非 None 放鍵;OTC / D/W/M 連鍵都不給;`worst_status` 嚴格序);期指 tf=1
  bars 非空仍帶 status 而前端只在空態讀(SP6 已申報留尾);七腿與三顆膠囊全取 `/api/calendar`,本機時鐘只用於否決
  (`CalendarBadges.tsx:67-71`)。§0.2-6 `_swap_day` 改三層 §4 有記 §0.2 未同步。無 scope creep。

### 2.6 #105 R8 TC4 深水區(`mod/tc4-session-hardening`)— 共用層,零 TC4 真環境驗證

**Standards**
1. **P2**(與 Spec 2 合併)—【run.ps1 15 s 與 Python 側收尾預算不同源且算漏】`run.ps1:60-63` 只歸因 `_REQ_TIMEOUT_MS`
   10 s 一發,但 `app.py:1040-1058` 是 corr → futures → index → stock → runtime **序列** `await close()`,之後 capital
   (COM join ≤ 5 s);每 source 各持自己的 `_api_lock`,TC4 半死時各自卡 `Connect()` 10 s → 最壞 4–5 × 10 s + 逐檔 UNSUB
   timeout + 5 s ≫ 15 s → `Stop-Tree` 硬殺在退訂中途,靜默還原本 PR 要修的殭屍 session(下一台開頭 ~60 s 零推播)。
   數字不在 §4 契約表、無測試;console 只印「15 s 內未結束」零指向根因。【親核屬實】
2. P2 [judgement] — `tc4.py:389` 收工分支 `api.Disconnect()` 未取 `api.lock`;`_dispose`(:404-417)明訂先 acquire;
   KeepAlive daemon 呼 `Pong` 取同鎖同 socket。另多份 docstring 引「不 Disconnect 則 process 不退」對本地 patch 過的
   wrapper(`tcoreapi_mq.py:280` daemon=True)已不成立,真代價是 TC4 端不 LOGOUT。
3. P3 [hard] — `index_engine.py:328` 103 字元;7 處 class/def 前 0 空行(6 個 test 檔,base 同類計數 0)。
4. P3 [hard] — `eac98b9f` 在 `tc4.py` 補純格式空行 = 🔵 混 🔴,不在 ST4 偏離清單。
5. P3 [judgement] — `corr_engine.py:457-478` 與 `futures_engine.py:418-448` 重連對帳骨架同形且**順序已漂**(futures 先
   update pending 再 bump epoch,corr 相反);今天等價,第三引擎接同款前必抽。
6. P3 — `index_engine.py:266` docstring「不碰共享狀態」與同支讀 `_loop` / `_retry_epoch` + `subscribe_symbol` 矛盾;
   `_retry_loop(epoch=None)` 分支無 caller。
7. P3 — `stock_engine.py:46/51` 用 int 編三態(-1 / 0 / ≥1),`_wl_seq_applied` 初值(:322)與 `WATCHLIST_UNORDERED` 同 -1。
- 核過:無 `except: log; return`;跨執行緒一律 `call_soon_threadsafe` / `to_thread`;測試只換 `QuoteAPI` + FakeSource;
  `set_watchlist` `asyncio.Lock` 內 `await to_thread` 不佔 loop(等待上界整段 → 單檔)。

**Spec**
1. P3(親核降自 P1)—【`except (OSError, ValueError)` 漏 `zmq.ZMQError`】`stock_source.py:546` 註解「OSError 涵蓋
   zmq.ZMQError」事實錯(`issubclass` = False,親驗)。但 `_rt_request` 實際路徑 `_ensure_connected` `Connect()`(:379)
   與 `_req` send/recv(:459)都已收斂成 ConnectionError,json / decode 拋 ValueError 子類;鎖外裸拋只剩 `setsockopt`
   (新 context 不拋)→ **今天不可達**,是 latent 脆弱點。附帶的真風險值得記:`stock_engine.py:830` `_do()` 的
   `set_trade_date` 不在 try 內,任何非 ConnectionError 逃出即整支 task 死、自選整天空白;index `_rollover_loop` 外層
   `except Exception` 吞後 `_pending_date` 已設 → 當日不再重掛。
2. P2 — 同 Standards 1(關機 15 s 只算一條 session);另 uvicorn 先等既有 WS 收完才跑 lifespan,§6.1 判準未涵蓋。
3. P2 —【next-time 勾銷過頭】`docs/next-time.md` −66 / **+0** 行;N111 自承「ZMQ IO 仍在鎖內」、N092 只 river 真三態
   (另兩處 log-only)卻整條勾銷;§5.3–5.6 / 7.8 七項留尾只活在單輪 verification,不在追蹤 backlog。
4. P3 — N260 `_leaf_rearm` 只在 `_handle_quote`(`futures_engine.py:495`)消化,`_handle_reconnect` 不自排 → 靠別品
   推播觸發;「重連即對帳」有前提。
- 逐項:N111 收住(`removed` 以 `_refs` 為準 :472;`_release` :427 owners 空才 `unsubscribe_symbol`,與 #66 不衝突)
  **⚠ 正確性依賴 IO 在鎖內** —— §5.3 留尾「IO 移出鎖」一做 ST1 原樣復發,這個耦合沒寫進留尾;N052 兩熱點都移、
  `_api_lock` 是 `threading.Lock` 跨執行緒正確、鎖序 `_lock → _api_lock` 單向無死鎖,`index_engine.start():233` 仍同步呼
  `set_trade_date`(靠開機 `_subscribed` 空擋住,非結構性);原子化真封;對帳全集重放;窗位移 futures k∈[0..3] / TXO k∈[4..7]
  不相交、index 動 IX0001 無共用 key;N093 / N033 未做站得住。
- **最先會炸**(prod 重啟後給 user 核):(a) 次一交易日 08:00 stock stage1 / 08:30 index 換日 —— `_unsub_stale_window`
  觸發舊窗歸零 → 上游退訂整 symbol,重掛任一步失敗即整份自選 / 加權當日死;(b) 這次收工 15 s 不夠 → 殭屍 session,
  下一台開頭 ~60 s 零推播。TC4 log 四項缺兩塊:§6.5 只有反向判準無「換日成功」正向對帳;N051 逐腿閘(SXF 休市段
  自癒發數)無待核項。

### 2.7 #106 R9a storage 收斂(`mod/storage-consolidation`)

**Standards**(判準複驗:grep 0 成立;SP1 getter 鎖真打在 accessor;四 export 全有呼叫點非 Speculative Generality)
1. [hard 事實錯誤] — `storage.ts:27-28` / `verification.md:124` 寫 inline disable「全 repo 唯一一處」:master 已有
   `StockPage.tsx:109`、`useStockStream.ts:325` 兩處。該註解正是給後人的判準,寫錯比不寫糟。
2. [hard] — `auto-verify` 4.4.0 說誤報走 doctor config rules 調整,`dc077e23` 處置是 inline `App.tsx:188`;既有兩處也
   inline → 該修的是 skill 字面,但現況文件 A、code B。
3. [judgement 混類] — 🔵 `67e035f7` 夾 21 處 `console.warn` + `purgeOrphanKeys` 整迴圈一 try 改逐鍵(`constants.ts:44-48`);
   ST2 申報未處置,該輪自訂判準「產生新可觀察輸出就不算 🔵」對自己不生效。
4. [judgement E] — `storage.ts:73/84/94` catch 不分 `err.name`;處置具體不算純 log,但 `warnWrite` 把 Quota(可清)與
   SecurityError(無解)壓成同一句。
5. [judgement] — 四旗標(:40-47)唯一讀者是自己去重;私密視窗偏好靜默不落檔畫面零訊號 → 記 next-time。
6. [judgement] — `readLocal(key: string)` 打錯 key 照編譯;「不 import constants 避循環」理由弱(`import type` 擦除)。
7. nit — `storage.test.ts:89-94 / 239-243` 未 mock `console.warn`。

**Spec**(逐項 PASS:48 呼叫點 key / 序列化 / 預設值逐字零改,27 裸 + 21 包分佈重數相符;grep 0;遷移只一處
`App.tsx::initialStockCode` 走 `if (writeLocal) removeLocal` 且 `App.test.tsx:205` 有鎖;21 處 catch 回退值全等)
1. P2 — verification §1 / §8 引 8 個 SHA + review JSON `reviewed_head` 全非 master 祖先;§8.4「不重寫歷史」與 merge 方式
   矛盾(系統性,見 §4)。
2. P3 — `verification.md:16`「🔴 只動裸奔;🔵 只動已包」不成立:`dfceff39`(🔴)改了 `App.tsx` 3 處 + `RiverPanel::initialOff`
   1 處已包呼叫點(change-spec 表格是對的,verification 總結錯)。
3. P3 — `docs/superpowers/specs/2026-08-24-architecture-debt-inventory.md:24,248` §4.E 就是本案,來源指標懸空未勾銷 →
   下次讀盤點表的人會照 §4.E 重開。
4. nit — change-spec 未逐處寫退預設後 UI 行為(8 項無 UI 面敘述)。
5. nit — 無新靜默覆寫路徑;唯一新可達 = `App.tsx:182,188,193` 三 effect 掛載即無條件回寫(讀拋寫成功 → 沖成預設;
   舊碼此前白屏),change-spec §2「唯一可觀察差異」未列。

## 3. 跨 PR 整合

1. **P1** —【`ops-discipline` skill 沒跟上 #99】`ws-reconnect.ts:187-190` 現在 `onopen → arm()`,但
   `.claude/skills/ops-discipline/SKILL.md:67-68` 仍寫「觸發前先等 ≥ 1 個心跳間隔(watchdog 收到首則 ping 才武裝)」。
   #99 change-spec §2 只列 `frontend-conventions`(已改)與 CLAUDE.md,漏這一支。下次照 skill 用側車 stall 驗半死連線
   的人會多等一個心跳、並把「首則 ping 之前 watchdog 就開火」讀成 bug。【親核:HEAD 與工作樹(他 session +7 行)都還是
   舊制;該檔有他 session 未提交修改,**本 session 不動**,列給 user】
2. P2 — 同 §2.6 Standards 1(15 s 五段序列 close)。
3. P2 —【#105 內兩處對同一契約敘述互斥】`stock_engine.py:459`(新)寫「Discord interaction token(3 s)必逾時」;
   `watchlist_service.py:12`(既有)寫「15 分鐘」;`discord_bot.py:19` 說已 defer 避開 3 秒窗。逐項取鎖把上界降到「當下
   這一檔」≈ `_api_lock` 等待 10 s + `_REQ_TIMEOUT_MS` 10 s ≈ 20 s,仍遠大於 3 s —— 行為對、理由錯。
4. P3 —【#105 重連對帳整發吃掉 #104 自癒重試】`index_engine.py:385-388` `_on_reconnect_threadsafe` 走 `_schedule_retry()`
   預設(`clear_stale=True, variant=0`),`:320-321` 先 cancel 在飛的 heal;#104 把自癒窗放寬到「交易日 13:25 → 午夜」
   (暴露 ~40 倍)。疊加:盤後 heal 以 variant=N 重試中 → `_check_stale` 重連 → 改以 variant 0 重抓,成功即 `:369`
   `stale = False`,`_heal_variant` / `_heal_interval` 不重置,下次最遠等 900 s;畫面 = 徽章健康、加權分時凍結。
   【親核屬實;前提「variant 0 在新 session 是否仍毒化」未實證】
5. P4 — `set_watchlist` 的 `added` 未逐項重驗 `_refs`,舊發可能多一趟 UNSUB+SUB;純浪費。
- 查過且乾淨:CLAUDE.md §4 八條契約在 HEAD 全對得上(心跳 10 s < 靜默 30 s;訊號參數三方逐值同;`meta.status` 只在期指
  鍵給;gate 5 與 `EMPTY_TEXT` 定義域互斥);八個 WS endpoint 全走 `relay()`、八支前端 hook 全走 `connectWithRetry`;
  #106 沒碰到 #101 / #103 新增呼叫點;刪改 assertion 逐條事前標記該變;`_apply_variant` 單射;`set_trade_date` 剩兩處
  同步呼叫都在 `start()`。

## 4. 系統性 / 流程

1. **artifact 引用 SHA 全數 dangling**(主 session 掃 7 目錄):ws-resilience 4/5、bug 5/8、frontend-state 4/5、capital 7/8、
   bars-engine 11/12、tc4 7/8、storage 9/10 → **47/56 非 master 祖先**。`branch-lifecycle` 的 rebase merge 與 artifact
   引 SHA 兩條口徑互相打架;現在還 resolve 得到只是本機 object 未 gc。處置:artifact 改引 commit subject / PR 內序號,
   或 merge 後回填 master SHA(入 branch-lifecycle skill)。
2. **「先寫 doc 後改型別沒回校」**出現兩次(#104 CLAUDE.md §4 `BarsResult`;#106 `storage.ts` 「唯一一處」)+ 三處
   verification 總結與 diff 不符(#99 SP4、#106 `:16`、#103 §1)→ closeout gate 該加一條「review 收修後回校 change-spec /
   verification / CLAUDE.md §4 引用的型別與數字」。
3. **next-time 勾銷過頭**(#105 −66/+0 行;留尾只活在單輪 verification)→ 勾銷時未做的一半要回填 backlog,不是整條刪。
4. `test(` type 有 83 筆卻不在 CLAUDE.md §6 值域 → 補 §6。

## 5. 建議處置分類

**A. 該修 code(候選下一輪,依真錢 / 盤中影響排序)**
- A1 #105 關機預算:run.ps1 15 s → 依「source 數 × `_REQ_TIMEOUT_MS` + capital 5 s」同源推導(或 close 改並行 + 總上限),
  console 印哪段吃掉時間(§2.6 S1)。
- A2 #103 N075 誤標窗:同檔同方向撞同 seq 仍誤標 —— 要嘛加「送單時刻 ± 窗」或 seq 單調性檢查,要嘛改口 docstring 承認窗
  未封並釘測試(§2.4);`_note_price_type` 移到 `_audit` 之後或包 try(§2.4 Spec 7)。
- A3 /bug gate 5:`tailIndex` 套 `c <= 0` 跳過(§2.2 Spec 2);門檻 3 → 4 或 60 s 覆量(Spec 1)。
- A4 #101 N115:撞名時保留編輯框(`setRenaming(null)` 移到成功回呼)+ 鎖(§2.3 Spec 1)。
- A5 #104 N105:休市日窗內閘 —— 需 user 拍板(補閘 vs 改口)(§2.5 Spec 1);rollover 設 pending 時 bump `_retry_epoch`
  (§2.5 Spec 2 親核那條)。
- A6 #105 重連 → `_schedule_retry(variant=self._heal_variant)` 或不清 stale(§3.4);`tc4.py:389` Disconnect 取鎖(§2.6 S2)。
- A7 #99 N037 補「節流 tick 真跑」案 + grace 改「只在偵測到凍結時」(§2.1)。
- A8 #101 `PARAM_DEFAULTS` 進 parity + `COOLDOWN` + 整數檢查(§2.3)。

**B. 文件改口(不動行為)**
- CLAUDE.md:206 `BarsResult` → 裸 tuple + 值域持有者;§6 補 `test(` type。
- `storage.ts:27-28` 「唯一一處」刪;`stock_source.py:546` ZMQError 註解改正;`store.py:196` 「回到只缺標籤不誤標」改口;
  `stock_engine.py:459` 3 s 改 15 min;`test_breadth_routes.py:408` 端點;`index_engine.py:266` docstring。
- `bars-engine-batch/change-spec.md:138` / `verification.md:166` SC-2 改口;`storage-consolidation/verification.md:16`;
  `architecture-debt-inventory.md` §4.E 勾銷改指。
- **`ops-discipline/SKILL.md:67`「首則 ping 才武裝」→ 「onopen 即武裝」**(他 session 有未提交修改,由該 session 或 user 改)。

**C. user 拍板 / 知情**
- N099 平倉鍵 code 已鎖(非待確認態);N105 補窗內閘 vs 改口;N036 boot 期間載入情境最壞 29 s;N068 240 req/h 兩面代價;
  N037 收益零證據要不要補真環境。

**D. 留尾回填 backlog(next-time)**
- #105 §5.3–5.6 / 7.8 七項 + 「N111 正確性依賴 IO 在鎖內」耦合;N051 逐腿閘待核項;N039 route 層 seed send;N038 背景分頁
  無效;#106 私密視窗零訊號;/bug H3 中段缺格 + tab 切回文案;`_leaf_rearm` 不自驅;各 Duplicated Code 抽取
  (重連對帳 / tick 閘 / `futExchangeContract` / `flash-locked`)。

## 6. 反駁重審

round-1 被標 rejected 的 finding 逐一重審:#99 ST2 / ST4 / SP5、#103 ST2 / ST4、#104 ST3 收修方向 —— **全部站得住**,
無需翻案。翻案的反而是 accepted 後又改回的:/bug round-1 SP4(門檻 3 貼邊閃動)accepted → 改 5 → round-2 改回 3,
新證據不含 prod 的 60 s 輪詢,SP4 顧慮未被真正消解(§2.2 Spec 1)。
