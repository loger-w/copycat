# brainstorm — 訊號規則化(題 1,方案 b)

規格來源:`.claude/feat/stock-quintet-discussion/brainstorm.md` 題 1(user 2026-08-05 拍板:
方案 b — 具名規則骨架,複合策略引擎不做;**硬性要求:刪自選即停監聽不得退化**)
→ /auto 預核准。分流判定:**已成形方案**(參考架構 treading-king active_signals 指名)。

## 目標

使用者可自建 N 條**具名訊號規則**(kind 選四類之一 + 門檻參數 + CDP 線勾選 +
cooldown + enabled + notify_discord),REST CRUD + 寫入即熱重載(不重啟),
前端規則列表 + 編輯器。取代「全域四鍵開關 + 改檔重啟才能調門檻」的現況。

## 現況(master a3d567c 實讀)

- `signals_config.py`:frozen `SignalsConfig` 全域門檻;`configs/signals.json` 覆寫檔不存在
- `live/signal_state.py`:`SignalDetector` 零 IO 狀態機,四類判定,cooldown/window/latch
  內建;`KIND_SWITCH`/`SWITCH_KEYS` 四鍵;`drop_code` 逐檔清狀態(題 4 輪已驗)
- `server/signal_hub.py`:單一 detector;`_enabled` 四鍵持久化 `data/signals_enabled.json`;
  basis worker 抓 CDP 分發;`_emit` → WS + jsonl + Discord 雙佇列;`_event_id` 決定性鍵
- API:`GET/PUT /api/stock/signals/enabled`;前端 `SignalRail` 四 toggle + `useSignalsConfig`
- treading-king 參考:active_signals CRUD + per-rule cooldown/notify_discord + 熱重載
  (`backend/routes/active_signals.py`、`models/condition.py`)

## 核心架構決策

`[auto-default: 組合式 — 每條規則一顆既有 SignalDetector 實例(以該規則參數建
SignalsConfig),detector 零改 | reason: detector 的 cooldown/window/latch/suppress 天然
per-rule 隔離;重寫 detector 吃 N 規則要把五種狀態字典全部加 rule 維度,blast radius
大一個量級且失去既有 62 條測試的保護]`

`[auto-default: CDP 線勾選 = hub 分發時過濾 basis(只餵勾選的線給該規則的 detector)|
reason: _eval_cdp 迭代 basis.items(),餵什麼評什麼,零 detector 改動]`

`[auto-default: hub 層 basis cache({code: (basis_date, cdp|None)} + staged 對應),
detector 只吃 set_basis;MFS-2 日別防護上移 hub 單點 | reason: N 顆 detector 各自
stage/swap 會有 N 份日別檢查;cache 讓新增/編輯規則零重抓(從 cache 立即分發)]`

`[auto-default: 舊 /api/stock/signals/enabled API 與 signals_enabled.json 移除讀取
(檔案留著不刪),前端 useSignalsConfig 同輪替換 | reason: 同 repo 無外部消費者;
雙軌並存會有「規則關了但舊開關開著」的二義]`

`[auto-default: 事件 id 加 rule 段(`{trade_date}-{rule_id}-{code}-...`)| reason:
同 kind 兩條規則可同 tick 同價觸發,舊 id 會碰撞去重]`

## 規則模型

```
Rule = { id: str(穩定,建立時 r-<epoch秒>-<序> 型), name: str(非空,唯一),
         kind: "cdp_cross"|"surge_crash"|"vol_burst"|"limit_lock",
         enabled: bool, notify_discord: bool, cooldown_secs: int(60..86400),
         params: kind 專屬(見下), cdp_levels: list[str]⊆{ah,nh,cdp,nl,al}(僅 cdp_cross,非空) }
params by kind:
  cdp_cross: { rearm_ticks }
  surge_crash: { pct, window_secs }
  vol_burst: { ratio, window_secs, min_elapsed_min, min_window_lots, min_day_lots }
    （window_secs 映射 surge_window_secs — 現況爆量窗與爆拉窗共用該欄,per-rule 後解耦）
  limit_lock: {}(cooldown 即全部)
儲存:data/signal_rules.json(atomic、_cache_version;壞檔 raise 同 signals_config 慣例)
```

## 成功條件(SC)

- **SC-1** 規則模型 + 儲存:`copycat/signal_rules.py` — Rule 驗證(kind/範圍/levels/
  名稱唯一非空)、load/save atomic、param 預設值自 `SignalsConfig` 取。
  驗證:pytest `tests/test_signal_rules.py`(anytime)
- **SC-2** Hub 規則引擎:per-rule detector;per-rule enabled/cooldown/params/cdp_levels
  生效;事件 payload 帶 `rule_id`/`rule_name`;`notify_discord=false` 的規則進 WS/jsonl
  不進 Discord 佇列;`_event_id` 帶 rule 段。驗證:pytest `tests/server/test_signal_hub.py`
  規則化測試組(anytime)
- **SC-3** 熱重載:REST 寫入後**不重啟**即生效 — 新增規則立即評估(basis 自 cache 分發,
  零重抓)、編輯規則重建該顆 detector(其他規則狀態不動)、刪除即停。
  驗證:pytest(hub 層:upsert 後同 tick 觸發新規則;其他規則 cooldown 保留)(anytime)
- **SC-4** 遷移:rules 檔缺 → 由 `signals_enabled.json` 四鍵 + 全域 config 生成四條
  預設規則(名稱:CDP 穿越/爆拉爆跌/爆量/鎖漲跌停)並落檔;舊 enabled API 移除
  (route 404)。驗證:pytest(冷啟動遷移 + 舊 route 404)(anytime)
- **SC-5** 刪自選即停監聽(user 硬性要求):自選移除 → 全部規則對該檔立即停發 +
  各 detector 狀態逐出(drop_code 迴圈)。驗證:pytest
  `test_signal_hub.py::test_watchlist_removal_stops_all_rules`(anytime)
- **SC-6** REST CRUD:`GET/POST/PUT/DELETE /api/stock/signals/rules(/{id})`;
  錯誤碼 `INVALID_RULE` / `RULE_NOT_FOUND`(400/404);寫入走 hub 熱重載 + 落檔。
  驗證:pytest `tests/server/test_signal_routes.py`(anytime)
- **SC-7** 前端規則 UI(可指認):訊號欄(SignalRail)上方改列**規則清單** — 每列
  規則名 + enabled 開關;欄頂「規則」按鈕開管理 Dialog:規則列表(名稱/種類/摘要)+
  「新增規則」+ 每列 編輯/刪除;編輯表單含 名稱輸入、種類下拉(四類)、該類參數數字
  輸入、CDP 線五個勾選框(僅 cdp_cross 顯示)、cooldown 秒數、Discord 通知勾選。
  驗證:vitest component tests + AI 截圖對照 + user 過目(截圖 anytime — 規則 UI
  不依賴盤中)
- **SC-8** 訊號列帶規則名:訊號 feed 每列顯示觸發的規則名(rule_name)。
  驗證:vitest(anytime)
- **SC-9** 零退化:pytest + vitest + tsc + eslint + ruff + pyright 全綠。(anytime)

## Edge cases

1. 規則 0 條(全刪)→ 零評估零事件,hub 不炸
2. 同 kind 兩條規則同 tick 觸發 → 兩則事件、id 不碰撞、各自 cooldown
3. 編輯規則(改門檻)→ 該規則 detector 重建(cooldown/latch 歸零 — 接受,規則變了
   舊冷卻無意義);其他規則不受影響
4. cdp_cross 規則勾選部分線(如只勾 ah/al)→ 只評那些線;rearm/suppress 亦僅該線
5. 壞 rules 檔 → SignalHub 建構拋 → `_boot` 傘降級:hub=None、signals routes 503
   NOT_READY、log「訊號引擎啟動失敗」[amendment 2026-08-05: design review R9 更正 —
   app.py 的 _boot 會吞建構期例外,非 lifespan fail-fast];REST 寫入路徑 atomic
   不會產生壞檔
6. 規則名重複 / 空 / kind 非法 / cooldown 界外 / cdp_levels 空(cdp_cross)→ INVALID_RULE
7. limit_lock 規則的 latch 語意:lock/open 同一顆 detector 的 latch,per-rule 隔離
8. 遷移時 signals_enabled.json 壞檔/缺檔 → 四條規則全 enabled(fail-open 同現況)

## Out of scope

- 複合策略引擎(treading-king 六 preset)→ 第二輪
- per-symbol 規則 scope(treading-king 已淘汰,不做)
- Discord `/signals` 指令、題 5 同群摘要(掛規則屬性留欄位不實作 — **不預留欄位**,
  YAGNI,題 5 輪再加)
- 規則排序/拖曳、匯出匯入
- Discord 全域節流(30/min)改動 — 保留

## 規模分流

**L**(後端 3-4 檔 + 前端 5-6 檔,跨前後端)→ 完整流程(輪數同 M)。

## 驗證窗口

全 SC anytime(hub 測試以注入時鐘;前端截圖不依賴盤中資料 — 規則 UI 為靜態表單)。
盤中實發驗證(真 tick 觸發自訂規則)= user 過目層,非 blocking。
