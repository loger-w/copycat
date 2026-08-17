# change-spec — 個股訊號降噪(mod/signal-denoise)

分流判定:已成形方案(見 current-state.md §0)。user 拍板事項(2026-08-17 對話):
**不關 CDP 任何線 / 不設每日上限 / 開盤 60 秒照評估 / 駐留預設 300 秒不改 600 /
爆拉爆跌門檻 2% / 300s / 1800s 不動**。

## 1. 成功條件

- **SC-1 CDP 駐留 rearm**:suppressed 的 (code, level) 只在「價格連續待在線外(|price−v| ≥
  rearm_ticks × tick)≥ `rearm_dwell_secs`」後才解除;中途任一 tick 回到帶內即歸零重算;
  冷卻 600s 邏輯不變。**規則 params 新鍵 `rearm_dwell_secs`(float,值域 [0, 3600],預設 300;
  0 = 舊行為:立即解除)**。
  [amendment 2026-08-18: R12] **起算時點**:寫入 suppressed 的當筆 tick 若已滿足 |price−v| ≥ gap
  (跳空穿越),以該 tick 的 mono 起算;否則值為 None(線內),之後第一筆線外 tick 起算。
  驗證:`tests/live/test_signal_state.py` 新測試(線外 <300s 回帶內不解除 / 線外 ≥300s 解除 /
  0 秒 = 立即解除 / 跳空穿越當筆起算);回放 SC-6。
- **SC-2 碰線不算穿越(側別追蹤)**:price == v 的 tick 為「線上」,不觸發、不改變側別;穿越 =
  上一個**非線上**側別與本 tick 側別相反(下→上 from_below / 上→下 from_above)。故 291.5 →
  292.0(=線)→ 292.5 仍算一次 from_below;292.0 → 291.5 → 292.0 → 291.5 不算。
  [amendment 2026-08-18: R4/R5/R13] 側別狀態 `_side[(code, level)] = (line_value, side)`:
  (a) **通則** [amendment 2026-08-18 r2: R16]:上一側別 = `_side` 有項且 `line_value == v` 時取存值;
  否則(缺項 / 線價變動 / None→有值)以 **`prev` 推定** `sign(prev − v)`(等價既有 `prev < v <= price`
  語意,每檔每日第一次穿越照發,W1 不變)。`prev == v`(prev 在線上)且無存值 → 上一側別未知,
  本 tick 只記側別不判穿越。本 tick 側別 `sign(price − v)`:非 0 → 存 `(v, cur)`;為 0(在線上)→
  保留上一側別 `(v, last)`。穿越 = 上一側別非 0 且 cur 非 0 且相反。fresh detector 首筆 tick 早退不寫
  (第二筆起由 prev 推定,與現行相同)。
  (a') [amendment 2026-08-18 r3: C-1] `set_basis(code, …)` 一律清該 code 的 `_side`(含 None):基準盲窗
  期間 `_eval_cdp` 早退不推進側別,同線價恢復時殘留側別會誤發;清掉後退回 prev 推定 = 舊語意。
  (b) 側別更新與 dwell 計時同屬**狀態推進**,放在 `enabled` gate **之前**(與 rearm 解除同段);
  只有事件產出 / cooldown / touch / suppressed 寫入受 enabled 管 → 停用期間側別照走,重開不補發。
  (c) 不變式:同一 tick 所有 level 的側別都由同一價格序列推進,**混向 levels 不可能發生**;
  防禦:若 from_below 與 from_above 同時非空,只保留與 `sign(price − prev)` 一致的方向並 log
  warning(W2 保留單一 direction + 固定序)。
  驗證:新測試(碰線不發 / 經線上點穿越仍發一次 / 線上點來回不發 / 基準盤中重設後首筆不假發 /
  停用期間穿越 → 重開不補發)。
- **SC-3 爆拉爆跌共用冷卻**:同 code 一則 surge 或 crash 觸發後 `surge_cooldown_secs` 內,另一
  kind 也不發;`touch_count` 仍分 kind 計。驗證:新測試 surge→crash(+60s)無事件、+1801s 有;
  既有 `test_surge_emits` / `test_crash_emits` 綠。
- **SC-4 Discord 同 tick 合併**:同一 code、同一 `time`(HH:MM:SS)且在 Discord 佇列中**相鄰**的
  多 row 合成一則訊息:`🔔 A・B・C｜名稱 代號｜價格｜時間｜規則名(去重、・串接)` **+
  `_group_suffix(rows[0])`**(同群摘要照接,[amendment 2026-08-18: R1]);單則文案與現行
  `format_signal_text(row) + _group_suffix(row)` 逐字相同。jsonl 逐 row、WS 逐 row、id 不變。節流計 1 則。
  [amendment 2026-08-18: R2/R3/R11;r2: R17/R18/R22] 機制:worker 持單槽 `pending`;head = pending 或
  `await get()`;之後以 `get_nowait()` 取下一 row:同 (code, time) 併入 batch,否則存入 pending 供
  下一輪(**不得回塞佇列**,保序)。**`task_done()` 一律在送出(或送出失敗被 log)之後**,batch 內
  每 row 恰一次;pending 那則在下一輪(它當 head)送完才 `task_done()` → `_discord_queue.join()`
  仍等於「全部已送」(既有 `_Harness.settle()` 屏障語意保留)。head 為 pending 時不再 `get()`。
  `price` / `name` / `code` 取 rows[0];kind 文案**去重**(同 kind 兩規則同 tick 只印一段)、規則名
  去重;文本 > 1900 字元 → 依 row 分批送(每批各計一次節流,批尾標 `(i/N)`);後續批被節流擋下
  → `logger.warning` 含 rows[0] id 與被擋批數(缺角在 log 可見);不截斷。
  驗證:`tests/server/test_signal_hub.py` 新測試(同 tick 兩事件 → sender 1 次、文案含兩段 + 摘要;
  同 tick A + 不同 tick B 混排 → 2 則且順序不變、`join()` 返回時 B 已送出;連續三輪含 pending 的
  混排不拋 ValueError、worker 存活;超長合併 → 分批皆送達且批尾 `(i/N)`;單則文案不變)。既有 `test_two_rules_same_kind_both_fire`:`len(h.bot)` 2 → 1(該紅)。
- **SC-5 前端列表同 tick 合併(畫面可指認)**:`今日訊號` rail 中,同 code 同 time 的多則顯示為
  **一列**:第一行「時間 代號 名稱」不變;第二行 kind 文案以「・」串接(如「跌破 CDP 中軸・爆跌
  −2.10%」),規則名去重後以「・」串接;價格取該組第一則(WS 序,即 live 最新在前);點列仍
  `onSelect(code)`。單則列外觀不變。
  [amendment 2026-08-18: R8/R11] 合併列第二行**逐段各自著色**(每段 kind 文案一個 span 帶自己的
  `toneOf`,「・」分隔符 muted 且 `aria-hidden`);`<li key>` = 組內**最早到達**那則 id(輸入為「新在前」序 →
  組內最後一則;新成員前插不改 key,[amendment 2026-08-18 r3: C-4/T-11/T-12]);`price` / 段序同取到達序
  (與 Discord `rows[0]` 一致);kind 文案去重(同 kind 同文案只印一段)。截圖檔名實際為
  `evidence/SC-5-rail-merged.jpg`、`SC-7-rules-summary.jpg` + `SC-7-rules-edit-dwell.jpg`(T-6)。
  驗證:`signal-model.test.ts` 新 `groupSignals` 測試(相鄰同組併 / 不同 code 不併 / 同 code 不同
  time 不併 / 保序 / 同文案去重);`SignalRail.test.tsx` 兩則同 tick → 一 `<li>` 且文案含「・」、
  兩段各自 text-bull / text-bear;既有「訊號漲跌方向著色」測試 fixture 同 code 同 time → 合併後
  兩 span 仍各自著色(**不該紅**,斷言維持);
  截圖:evidence/SC-5-rail.png(用 today jsonl 假資料或真 server)+ user 過目。
- **SC-6 回放減量**:當日 33 檔 1 分 K(快照存 `evidence/bars-20260817.json`)重建 tick 餵
  **真 `SignalDetector`**,[amendment 2026-08-18: R6] 兩臂 = **同一份新 detector**(側別追蹤已內建)
  `dwell 300` vs `dwell 0`;dwell 減量 ≥ 25%;`2408 / 3006 / 3037 / 8064` 則數不變。腳本另印
  `data/signals/20260817.jsonl` 實際 CDP 則數(120)當旁證(近似路徑 vs 真 tick 的落差)。
  量法:`.venv/Scripts/python .claude/mod/signal-denoise/replay_cdp.py`,exit 0 = PASS;**25% 的分母
  = 本輪 dwell 0 臂實測值(腳本自印兩臂絕對數 + 百分比)**,不是 134 / 136。
  (1 分 K 路徑是近似:改前真 detector 跑同一份 K = 134、current-state §0 的獨立 sim = 136、實際
  jsonl = 120;只比相對減量。[amendment 2026-08-18 r2: R20])
- **SC-7 規則 UI**:規則對話框 CDP 規則多一欄「線外駐留秒數」(預設 300),列表摘要印
  「駐留 300 秒」;送出 payload 帶 `rearm_dwell_secs`。驗證:`SignalRulesDialog.test.tsx` 欄位 +
  摘要;截圖 evidence/SC-7-rules.png + user 過目。
- **SC-8 Migration**:既有 v1 `data/signal_rules.json` 啟動可載入(cdp 規則補 dwell 預設,記憶體
  形 v2),不 raise;`load_rules` 對 v2 檔照常;非 1/2 版本 raise。驗證:`test_signal_rules.py`
  新測試(v1 檔載入成功且 cdp params 含 rearm_dwell_secs=300;v1 檔內容不被改寫;save 後
  `_cache_version == 2`)。

## 2. 不能破壞的既有行為白名單(自評 finder 必附本節)

- W1 CDP 五線全部可用、`cdp_levels` 過濾語意不變;無每日上限;開盤 09:00:00 起即評估。
- W2 CDP 冷卻 600s per (code, level)、`touch_count` 當日累計、同 tick 多線合併成單一事件且
  levels 固定序、**單一 direction(不得混向)** — 全部不變。
- W3 rearm 距離門檻 `rearm_ticks × tick_size`(預設 5)不變;`rearm_dwell_secs = 0` 完全等於現行
  「離線即解除」。
- W4 爆拉 / 爆跌門檻 2% / 窗 300s / 冷卻 1800s 數值不變;同 kind 冷卻行為不變;爆量借用同一個窗不變。
- W5 鎖停 / 打開的 latch、per (code, kind, direction) 冷卻不變;`evaluate_book` 路徑不變。
- W6 `SignalEvent` / WS payload / jsonl row / `_event_id` / `/api/stock/signals/today` 形狀與內容
  逐 row 不變(合併只發生在 Discord 送出與前端列表顯示)。
- W7 Discord:送出文本 = `format_signal_text(row) + _group_suffix(row)`,合併版逐段保留(含摘要);`notify_discord=false` 的規則不推;
  節流 `discord_per_min`;佇列滿丟舊。
- W8 前端:toast / 桌面通知 / 嗶聲仍逐則(useSignalAlerts 不動);`mergeSignals` id 去重與
  time 降冪不變;每段 kind 文案的紅綠對應(`toneOf`)不變;規則對話框其他 kind 欄位不變。
- W9 規則 REST 驗證語意:精確鍵集合、值域、INVALID_RULE / RULE_NOT_FOUND 碼不變;
  `configs/signals.json` 未知鍵 raise 不變。[amendment 2026-08-18: R15] 預期降級:server 更新後
  **未重新整理的舊分頁**送 cdp 規則會缺 `rearm_dwell_secs` → INVALID_RULE(既有文案「規則設定
  不合法」),重新整理即恢復;接受不另做。
- W10 換日 `reset_day` 清空全部 CDP 狀態(含新的 dwell 起算)、`drop_code` 清該 code。

## 3. 決策(grilling,逐題 auto-default)

- D1 駐留量測用**牆鐘 mono**(`now_fn`),與 cooldown 同一時間軸 `[auto-default: mono | reason:
  design R11 兩條時間軸不可混用;tick.time 只顯示用]`。
- D2 「碰線不算穿越」採**側別追蹤(線上點透明)**而非嚴格不等式 `[auto-default: 側別追蹤 |
  reason: 嚴格版會漏掉 291.5→292.0→292.5 這種逐 tick 穿過線的真穿越(每個 tick 都碰到線價),
  是資訊損失;側別追蹤保留「剛好等於線價來回不算」的 user 語意]`。
- D3 dwell 起算與歸零的判定用「|price−v| ≥ gap」的絕對距離,不分上下側 `[auto-default: 不分側 |
  reason: 跨側跳空本身會產生新的穿越判定,分側只是多一種狀態;稀疏 tick 下分側會誤歸零]`。
- D4 Discord 合併粒度 = 同 code + 同 `time`(秒)且佇列相鄰 `[auto-default: 秒 | reason: row 不帶
  time_key;同秒同檔兩筆 tick 併成一則亦屬合理閱讀]`。**合併在送出端不在 emit 端**
  `[auto-default | reason: emit 端合併會改 id / jsonl 形狀,WS 重連 refetch jsonl 會出現合併前後
  兩份不同 id 的重複列(W6)]`。
- D5 前端 toast 不合併(僅列表)`[auto-default: 不動 | reason: user 指名「訊號列表」;toast TTL 5s
  疊四張的問題另議,記 next-time]`。
- D6 規則檔 migration 用 `_CACHE_VERSION` 1→2 + 載入期補鍵、不回寫 `[auto-default | reason:
  load_rules docstring 明訂「版本 bump 必附轉換」;不回寫保留 upsert 前的回退窗]`。
- D7 `rearm_dwell_secs` 是 float 秒(非 INT_PARAM_KEYS)`[auto-default | reason: 與 window_secs
  同型;秒不需要整數限制]`。

## 4. Edge cases

1. dwell 期間 tick 稀疏:線外 A tick(t0)→ 下一筆線外 tick(t0+400s)→ 400 ≥ 300 直接解除(以牆鐘差計)。
2. 線外 250s 後一筆回帶內 → 歸零;再線外 300s 才解除。
3. 基準盤中才到 / 重設(`set_basis` 在若干 tick 後或線價變動):依 SC-2 通則,首筆只 seed 側別
   不發;price == v 維持未知。[amendment 2026-08-18: R13]
4. dwell = 0:第一筆線外 tick 立即解除(既有測試 `test_rearm_released_at_five_ticks` 用 dwell 0
   等價驗舊語意 → 改為新測試以 300 驗)。
5. surge 後 crash 於 1800s 邊界:`_cooling` 用 `>` mono,+1800s 整點解除,與現行同 kind 語意一致。
6. Discord 佇列中同 tick 兩 row 之間夾了別檔 row(理論上不會:on_tick 同步 enqueue)→ 不合併,各送。
7. 前端 baseline(jsonl 反轉)與 live 同 id 去重後排序穩定;同 (code,time) 不相鄰(被別檔同秒 row
   隔開)→ 各成一組(顯示保守正確,不跨列搜尋)。
8. Discord 合併訊息超過 1900 字元(規則名無長度上限、摘要可再加一段):**bot / webhook 皆無
   既有截斷**(查證 discord_bot.py:529、notify.py)→ `_send_discord(rows)` 依 row 分批,每批 ≤ 1900
   字、各計一次節流;單 row 本身超長維持現況(不在本輪)。[amendment 2026-08-18: R3]

## 5. Out of scope

- 每日上限 / 關閉 nh、nl / 開盤窗口跳過(user 否決)。
- toast / 桌面通知合併;FuturesChart / 指數訊號;訊號規則新 kind。
- `_staged*` 家族移除(既有 next-time)。

## 6. Diff 級章節(逐檔;🔴 行為 / 🟢 新功能 / 🔵 重構)

順序 **🔵 → 🟢(純新增、無 caller:signals_config 新欄 / signal-model `groupSignals` /
Dialog 新欄)→ 🔴**。[amendment 2026-08-18: R14] 顯式覆寫 /mod 預設 🔵→🔴→🟢:🔴 依賴 🟢 的新欄
與新函式,照預設序 🔴 commit 會編譯不過;三類仍不混。

- 🔵 `copycat/live/signal_state.py`:`_suppressed` set → dict[(code, level), float | None]
  (值 None;行為等價),`reset_day` / `drop_code` 同步。測試:全綠不變。
- 🟢 `copycat/signals_config.py`:`cdp_rearm_dwell_secs: float = 300.0`。測試:`test_signals_config`
  覆寫鍵測試加一例。
- 🟢 `frontend/src/lib/signal-model.ts`:`groupSignals`(+ `SignalGroup` 型別)。測試 signal-model.test。
- 🔴 `copycat/live/signal_state.py`(前置:🟢 signals_config):(a) rearm 解除加 dwell 判定(`cdp_rearm_dwell_secs`;起算見
  SC-1);(b) 穿越判定改側別追蹤 `_side: dict[(code, level), tuple[int, int]]`(line_value, side;
  reset_day / drop_code 清;`set_basis` 不需額外清 — 線價比對即失效),更新在 enabled gate 之前;
  (c) surge/crash 冷卻鍵 `(code, "surge_crash", "")`。
  既有測試該紅:`test_rearm_released_at_five_ticks`(先改為 dwell 語意紅 → 實作綠);
  `test_cooldown_blocks_second_cross` 註解更新(不紅)。新測試:SC-1 ×4、SC-2 ×5、SC-3 ×2。
- 🔴 `copycat/signal_rules.py`:`PARAM_SPECS.cdp_cross += rearm_dwell_secs (0, 3600)`;`_seed_params`;
  `rule_config`;`_CACHE_VERSION = 2` + `load_rules` v1 轉換(`_migrate_v1`,補值 = 模組常數
  `_DEFAULT_REARM_DWELL_SECS = 300.0`,**`load_rules` 簽名不動**;[amendment 2026-08-18: R10])。既有測試該紅:
  `rearm_ticks` 精確集合 fixture(18 處)、`test_saved_file_carries_cache_version`(1→2)、
  v1 檔 fixture(仍應載入成功 — 改斷言為 v1 可載且補鍵)。新測試:SC-8 ×3。
- 🔴 `copycat/server/signal_hub.py`:`_discord_worker` 單槽 pending 合併(記帳見 SC-4);新
  `format_signal_group_text(rows)`;`_send_discord(rows)` 接 `_group_suffix(rows[0])` + 分批。
  既有測試該紅:`TestRules::test_two_rules_same_kind_both_fire`(`len(h.bot)` 2 → 1,文案含一段
  kind + 兩規則名);其餘 Discord 測試不該紅。新測試 SC-4 ×4。[amendment 2026-08-18: R7]
- 🔴 `tests/server/test_signal_routes.py`:cdp payload 加新鍵(該紅→綠)。
- 🔴 `frontend/src/components/stock/SignalRail.tsx`(前置:🟢 signal-model):改 group 渲染(逐段著色、key = 首則 id)。
  既有 `SignalRail.test.tsx`「訊號漲跌方向著色」fixture 同 code 同 time → 合併為一列但兩段各自
  著色,斷言**不該紅**;若有列數斷言依 fixture 逐一核。[amendment 2026-08-18: R7]
- 🟢 `frontend/src/components/stock/SignalRulesDialog.tsx`:新欄位 `rearm_dwell_secs` + DEFAULT_PARAMS;
  🔴 同檔 `ruleSummary` 摘要文案加「駐留 N 秒」(拆 commit)。既有測試:`SignalRulesDialog.test.tsx`
  fixture `params: { rearm_ticks: 2 }` 補新鍵(摘要斷言若比對全文則該紅);
  `frontend/src/hooks/useSignalRules.test.tsx:24` fixture 補鍵(**不該紅**,型別不擋)。[amendment 2026-08-18: R7/R14]
- 🟢 `.claude/mod/signal-denoise/replay_cdp.py` + `evidence/bars-20260817.json`:SC-6 量法。

## 7. Migration / 回退 [amendment 2026-08-18: R9]

- 前滾:`load_rules` 遇 `_cache_version == 1` → 對 `kind == cdp_cross` 且缺 `rearm_dwell_secs` 的
  params 補 `_DEFAULT_REARM_DWELL_SECS`(300.0)→ 走 `normalize_rule`;**不回寫檔案**;首次 upsert
  才以 v2 落檔。`_cache_version` 非 1/2 → raise(既有語意)。
- 回退窗:尚未 upsert 前,`data/signal_rules.json` 仍是 v1 原檔,舊碼可直接讀。
- 回退手順(upsert 後):停 server → 編輯 `data/signal_rules.json`:刪除每條 cdp 規則的
  `rearm_dwell_secs` 鍵、`_cache_version` 改 1 → 起舊碼。失效樣態(沒做):啟動 log「訊號規則檔
  版本不符」→ hub None → `/api/stock/signals/*` 503。
- `configs/signals.json`(若存在)不需改;新鍵有 dataclass 預設。
- 已知分歧 [amendment 2026-08-18 r2: R21]:遷移補值 = 常數 300(不吃 cfg,為了不動 `load_rules`
  簽名),而缺檔種子 `_seed_params` 走 `cfg.cdp_rearm_dwell_secs`;若 `configs/signals.json` 覆寫了
  該鍵,兩路徑值不同。遷移時 `logger.info` 印出補的值與規則 id 留痕;規則 UI 可見可改。

## 8. Known Risks / 註記

- 1 分 K 回放是近似;真實 tick 路徑下的減量以次一交易日 jsonl 對照(驗證窗口:2026-08-18 盤中;
  窗口外降級 = 只認 SC-6 回放數字)。
- Discord 合併依賴「on_tick 同步 enqueue、worker 之後才醒」的單執行緒事件迴圈事實;若日後 emit
  改成 await 中途讓渡,合併率下降但不會錯送(edge 6)。

---
self_review_head: 9f6171a6f17dba5cc9d96ce171908fbba688c790(自評 round-1 + fix 波後;收尾增量 review 依此判)
