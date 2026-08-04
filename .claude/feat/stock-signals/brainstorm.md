# Brainstorm:個股即時訊號(stock-signals)

日期:2026-08-04
來源:user prompt(/auto /feat)+ AskUserQuestion 四題拍板 + 兩份探索報告
(treading-king 訊號實作拆解 / copycat 個股架構盤點,見對話記錄)。

## 分流判定記錄

**已成形方案** — 條件 1 中(指名 UI 形式「自選左邊加訊號欄」、資料流「達錢 4 tick → 前端
通知 + Discord」、參考實作 treading-king),條件 2 中(Discord 架構 / 監聽範圍 / 版面 /
訊號範圍四個可拷問決策點)→ grilling 姿態。四個方向性抉擇以 AskUserQuestion 問畢,
user 拍板如下;其餘實作選擇標 `[auto-default]`。

## User 拍板(2026-08-04)

1. **Discord 接收側 = discord.py bot 跑進 copycat server**(同 asyncio loop,
   extras `[discord]`,slash commands)。需 user 建 Discord bot 應用並提供
   `DISCORD_BOT_TOKEN`(.env)— token 未設時降級:bot 不啟動、server 照常。
2. **監聽範圍 = 全自選皆監聽,群組僅分類**。不做 per 群組 / per 股票監聽開關;
   開關做在「訊號類型」層(全域)。Discord `/watch add` 可帶選填群組參數。
3. **前端訊號列表 = 自選左側新欄**(user 原案):最左新增窄欄,上半訊號流、
   下半訊號類型開關;中間圖表區彈性縮小。
4. **訊號範圍 = 全收**:CDP 穿越五線 + 爆拉/爆跌(核心)+ 鎖漲停/打開 + 爆量 +
   瀏覽器通知 + 提示音。

## 目標

把 treading-king 的即時訊號能力移植到 copycat(資料源換達錢 4/Touchance),並補齊
它最弱的前端通知環節;新增 Discord slash command 管理自選。

## 訊號定義(參數沿用 treading-king 已回測值)

| 訊號 | 觸發條件 | 去重 | 預設參數 |
|---|---|---|---|
| CDP 穿越 | live tick 價格由下而上(壓力)/由上而下(支撐)穿越 AH/NH/CDP/NL/AL 任一線(橫盤不算) | rearm:離線 ≥ 5 ticks 才重新武裝;cooldown per (code, level) | tolerance 0 tick、rearm 5 ticks、cooldown 600s [auto-default: treading-king production config 值] |
| 爆拉 / 爆跌 | 300s 窗內 price_change_pct ≥ +2.0% / ≤ −2.0% | cooldown per (code, 方向) | ±2.0% / 300s、cooldown 1800s [auto-default: treading-king 回測採用值,爆跌 −2.0 為其回測結論] |
| 爆量 | 300s 窗量 ≥ ratio × 當日分鐘均量 × 5;開盤未滿 min_elapsed 不評估 | cooldown per code | ratio 3.0、min_elapsed 15 分、cooldown 1800s [auto-default: treading-king volume_ratio schema + 保守預設;可 config 調] |
| 鎖漲停 / 打開 | 鎖上:成交價 = 漲停價且對手側委託不可得(沿用上一輪 relabel_locked_side 的制度恆等式)→ latch;打開:latch 後成交價 < 漲停價。跌停對稱 | 鎖上 / 打開各 per (code, 方向) 當日一次性 latch + cooldown | cooldown 600s [auto-default: 同 CDP 檔位] |

- CDP 基準 = 前一交易日 H/L/C,`compute_cdp`(毫元整數)現成;engine 需為整份自選
  每日備妥(開機 + rollover + 新增股票時)。[auto-default: engine 自呼 `daily_bars` +
  `build_overlay` 自建 per-code cache,不共用 route 層 OverlayCache | reason: engine
  拿不到 route 層實例,且訊號引擎不應反向依賴 route]
- 所有門檻收在版本化 config(`configs/signals.json`,strategy_config 慣例),
  調參 = 改 config 不動引擎。[auto-default: 沿專案慣例]

## 通道

- **推送**:WS `/ws/stock` 新增 `{"type":"signal",...}` 訊息(`_publish` 單一出口)+
  Discord 純文字。
  [amendment 2026-08-04: user 告知 Discord 憑證沿用 treading-king — 實查後
  `DISCORD_BOT_TOKEN` + `SIGNALS_DISCORD_CHANNEL_ID` 已搬入 copycat .env,而
  **兩專案都沒有 webhook URL**(treading-king 推送本來就走 bot)。故推送改走 bot
  發頻道訊息(`SIGNALS_DISCORD_CHANNEL_ID`),`notify.py` webhook 留備援
  (URL 未設 no-op),取代原「推送走 webhook」auto-default。發送仍需佇列化,
  絕不阻塞 tick 路徑。]
  [風險註記: 同 application 的 slash command sync 會覆蓋 treading-king bot 註冊的
  指令 — 該 bot 已實質退役(富邦體驗差為本輪動機),覆蓋可接受;收尾回報提醒 user。]
- **接收**:discord.py bot(slash commands `/watch add <code> [group]` /
  `/watch remove <code>` / `/watch list`),改自選走與 PUT /api/stock/watchlist 同一條
  「落檔 + set_watchlist」路徑,加 asyncio lock 防與前端並發;變更後 WS 廣播
  watchlist 變更事件讓前端自動同步。
- **歷史**:訊號落檔 `data/signals/YYYYMMDD.jsonl`(append-only)+
  `GET /api/stock/signals/today`;重啟後前端訊號列不歸零。

## 成功條件(SC)

驗證窗口標記:`anytime` = 測試/fake 可驗;`盤中` = 需真實行情。全部 SC 的自動化層
都是 anytime(pytest fake source / vitest);盤中僅影響 Phase 6 real-env 層,窗口外
降級策略逐條標明。今日(週一)為交易日,盤中驗證可行,但**盤中不起第二台連 TC4 的
後端**(§8 紀律)— real-env 以 fake source + 另 port、或收盤後重啟正式 server 驗證。

- **SC-1 CDP 穿越訊號(anytime)**:pytest 以 fake source 注入 tick 序列(prev 在 AH 下、
  curr ≥ AH)→ 斷言 `/ws/stock` 收到 `{"type":"signal","kind":"cdp_cross","code",...,
  "levels":["ah"],"direction":"from_below"}` 且 notify mock 被呼叫一次;橫盤序列與 rearm 內
  重觸不發。
  [amendment 2026-08-04: design R7 同 tick 多線合併 → 欄位 `level: str` 改
  `levels: list[str]`(固定序);review MFS-4 補此 amendment,驗收以 levels 斷言]。
  驗證:`pytest tests/live/test_signal_state.py tests/server/test_signal_hub.py -q`
  對應測試名綠(實際落點;原寫 test_signal_engine.py 為規劃期檔名)。
- **SC-2 爆拉/爆跌訊號(anytime)**:注入 300s 內漲幅 +2.1% 的 tick 序列 → 發
  `kind:"surge"`;−2.1% → `kind:"crash"`;+1.9% 不發;cooldown 內第二次不發。
  驗證:pytest 同上。
- **SC-3 爆量訊號(anytime)**:構造分鐘均量基準後注入窗量 ≥ 3× 序列 → 發
  `kind:"vol_burst"`;開盤前 15 分鐘不評估。驗證:pytest。
- **SC-4 鎖漲停/打開訊號(anytime)**:注入鎖漲停簿(bids[0]=市價 0 檔位情境含)+
  漲停價成交 → 發 `kind:"limit_lock"`;隨後 < 漲停價成交 → 發 `kind:"limit_open"`;
  同日重複鎖上不重發(latch)。跌停對稱各一測。
  [amendment 2026-08-04: design review R9 — 補反例測試「首攻吃光賣盤(ask 空但無
  市價佇列、最佳限價買 < 漲停)→ 不發 limit_lock」;R20 — 補「簿上 ask 限價檔重現
  無成交 → 亦發 limit_open」]。驗證:pytest。
- **SC-5 回補不誤發(anytime)**:先 live 注入觸發一次訊號,再 `apply_backfill` 整日
  重放同序列 → 斷言零新訊號、notify mock 呼叫數不變。驗證:pytest。
- **SC-6 盤別 gate(anytime)**:wall-clock 在 09:00–13:30 外、或 tick 為試撮 → 不評估
  不發。驗證:pytest(時間可注入)。
- **SC-7 訊號歷史(anytime)**:觸發 N 筆後 `GET /api/stock/signals/today` 回 N 筆
  (含 kind/code/price/time);模擬重啟(新 engine 讀同檔)仍回 N 筆。
  [amendment 2026-08-04: design review R1 — 補「跨重啟 id 不碰撞」測試:重啟後新發
  訊號 id 不得與重啟前任一筆相同(id 為決定性鍵)]。驗證:pytest。
- **SC-8 Discord bot 指令(anytime + 真實層)**:bot 層以 fake interaction 呼叫
  handler:`/watch add 2330 群組A` → watchlist 檔含 2330 且入指定群組、engine
  `set_watchlist` 被喚、WS 廣播 `{"type":"watchlist_changed"}`;`/watch remove` 反向;
  超上限 / 非法代碼回錯誤文案不落檔。token 未設 → server 啟動正常且 bot 降級 no-op。
  驗證:pytest。真實層(anytime):token 已入 .env
  [amendment 2026-08-04: 已沿用 treading-king 憑證,不再是 user 待辦] — 以 fake
  source + 另 port 起 server,在 Discord 實發 `/watch list` 驗 bot 上線與指令回覆;
  實發驗證若撞 Discord 端問題(權限/intent)→ 降級 pytest + 註記 blocked_reason。
- **SC-9 左側訊號欄(anytime,UI)**:1600×900 截圖可指認 — StockPage 最左出現寬約
  200px 新欄,欄首標題「今日訊號」,每列顯示 `HH:MM 代號 名稱 訊號中文名 價格`,
  最新在最上;欄下半「監聽訊號」四個 toggle(CDP 穿越/爆拉爆跌/爆量/鎖板),關閉
  的類型新訊號不入列。點擊訊號列 → 主圖切至該股(header 代號改變)。驗證:vitest
  元件測試 + DevTools MCP 對 vite dev(連正式 8721 或 fake server)截圖對照 + user 過目。
- **SC-10 前端即時通知(anytime,UI)**:新訊號到達 → 右上角浮出 toast(含代號 +
  訊號名,約 5s 自動消失)+ `Notification` API(權限已授且分頁非前景時)+ 提示音
  (音效 toggle 預設開,存 localStorage)。
  [amendment 2026-08-04: design review R7 — toast 同時顯示上限 4 則,溢出「+N」;
  補測試「連續 20 則 → 畫面同時最多 4 個 toast + 溢出計數」]。
  驗證:vitest(Notification/Audio mock)+
  DevTools MCP 以 fake server 注入訊號截 toast 圖 + user 過目。
- **SC-11 前端自選同步(anytime)**:WS 收到 `watchlist_changed` → 自選清單自動
  refetch(不需手動整理)。驗證:vitest hook 測試。
- **SC-12 全域開關持久化(anytime)**:訊號類型 toggle 寫後端
  (`GET/PUT /api/stock/signals/enabled`),關閉類型後端**不產生事件、不發送**
  (Discord 也不發),重啟保留。驗證:pytest(PUT 後注入該類觸發序列 → 不發)。
  [amendment 2026-08-04: design review R14 端點改名 config→enabled(名實相符);
  R2 措辭「不評估」→「不產生事件」(狀態推進無條件,關爆拉不得連帶廢爆量 —
  補測試:關 surge_crash 後注入爆量序列 → vol_burst 照發)]
  [auto-default: 開關存後端 config 檔而非 localStorage | reason: 開關若只在前端,
  Discord 推送不受控,違背「關掉就是不吵」直覺]

## Edge cases(≥3)

1. **回補重放**:`apply_backfill` = reset + 整日重放,訊號引擎只掛 live tick 路徑
   (SC-5 鎖死)。
2. **鎖停市價 0 檔位**:鎖停時 `bids[0]=(0,N)`,鎖停判定沿用消費端過濾(§8 條目),
   SC-4 測試涵蓋。
3. **休市日 / 盤後 stale tick**:wall-clock gate + 盤後 fresh subscribe 會回收盤
   snapshot(§8)→ 不評估(SC-6)。
4. **Discord 與前端並發改自選**:同一 asyncio lock 序列化;內容相同零寫早退
   (沿前端零 PUT 慣例)。
5. **webhook 失敗/429**:notify.py never-raise + 429 重試一次;訊號照樣進 WS + jsonl
   (三路互不阻塞,順序 WS → jsonl → Discord,仿 treading-king fanout)。
6. **server 盤中重啟**:訊號狀態(cooldown/latch)不持久,重啟後 prev tick 空 →
   首 tick 無方向不誤發。
   [amendment 2026-08-04: impl-review R15 消歧 — 原「已鎖停股票重啟後不補發鎖上」
   與 design §9 矛盾,拍板採 design 版:首 tick 只初始化,**第二筆鎖停 tick 會再發
   一次 limit_lock**(= 重啟後同訊號重發一次,已接受代價;若要求「latch 需觀察到
   未鎖→鎖轉態」則重啟後整天收不到該股鎖板訊號,代價更大)]
   [auto-default: cooldown 不持久化 | reason: 最壞情況 = 重啟後同訊號多發一次,
   代價可接受;持久化增 IO 複雜度]
7. **自選 30 檔上限 / 非法代碼**(Discord 路徑):回覆錯誤文案,不落檔。
8. **token 未設 / bot 登入失敗**:`_boot` 降級模式,server 其餘引擎不受影響。

## Out of scope

- Discord 圖卡(PNG 分時圖/五檔圖)— bot 已就位,日後升級。
- treading-king 其餘 preset 策略(漲停打開碰 CDP、breakout_retest、造山系)。
- MA 碰線訊號、cross_above/below operator 一般化、自訂規則 UI。
- per 群組 / per 股票監聽開關。
- 訊號回測 / replay 驗證框架。
- 富台/期貨/選擇權訊號(本輪僅個股)。

## 執行約束(跨輪)

- 盤中不起第二台連 TC4 的後端;驗後端 HTTP 層用 fake source + 另 port(§8 紀律)。
- 寫 .py 前讀 `backend-conventions`;寫 frontend/ 前讀 `frontend-conventions`
  /`frontend-testing`。
- 前端純判定邏輯抽 `frontend/src/lib/` 純函數單測(專案慣例)。
- `_publish` 為 WS 唯一出口;`_quote_payload` 為 watchlist_quote 唯一 builder。
- 新增 env key 讀取用「`name in os.environ` 即用 → repo root .env」新語意 + utf-8-sig。
- 訊號 jsonl 寫入走 atomic append(每筆 flush,仿 treading-king signal_writer 即時寫穿)。

## Scope 分級

**L**:跨前後端、新依賴(discord.py)、預估 ≥ 10 檔(engine 新模組 / notify 佇列 /
bot / routes / config / 前端新欄 + toast + hooks)。對外 API 新增 3 條
(signals/today、signals/config、WS 新訊息型別)。
