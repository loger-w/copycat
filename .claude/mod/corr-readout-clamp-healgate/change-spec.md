# change-spec — 重疊圖空腿 readout 印 — / 江波圖收盤 clamp 不覆寫 / 自癒閘跨午夜查前一日(mod/corr-readout-clamp-healgate,R5 / B7+B8+B9)

分流判定:已成形方案(rounds.md §R5 三條探針證實、修法明確;預核准)。Scope:**M**(前端 1 + 後端 2 源檔 + 測試;互不重疊)。

## 現況
- **B7**(前端)`river-chart-svg.ts::buildOverlayGeometry(entries, win, size)` L138-148 `.filter(s !== null)` 把 `minutes={}` 的腿濾掉 → `g.lines` 少一腿;
  `RiverOverlay.tsx:77-83` readout 由 `g.lines.map` 產生 → 空腿在讀值列**消失**(不是印「—」);`OverlayEntry {key,label,colorIndex,leg}`。next-time 08-17 corr R5 review R-2。
- **B8**(後端)`river_models.py::offset_of(minute_end, kind)`:`end < m <= end+5` 併入 `end`(回 offset(end));`river_state.py::push` 無條件 `minutes[offset] = price`
  → 13:46–13:50 的小日經取樣蓋掉 13:45 真收盤值;`apply_backfill` 有「只填尚無值」語意。同節 review R-3;ES/NQ/YM 同類。
- **B9**(後端)`app.py::_heal_gate(calendar, clock_gate)` = `calendar.is_trading_day(_today()) and clock_gate()`;docstring 已知邊界:週六 00:00–05:00 屬週五場 → False(該救不救);
  反之週一 01:00 `is_trading_day(週一)=True` 但無夜盤 → 空 churn(clock_gate 週一凌晨為真:夜盤 15:00–05:00)。`_today()` / `_now()` 為唯一取樣點;
  測試 `tests/server/test_main_wiring.py:272-330` monkeypatch `_today`。

## 拍板(auto-default)
- **D1 B7**:readout 改由 `entries` 產生:`entries.map(e => { const line = g.lines.find(l => l.key === e.key); const hit = line?.pts.find(p => p.offset === cursor); return { key:e.key, label:e.label, colorIndex:e.colorIndex, hit }; })` → 空腿印「—」;圖上仍不畫(`buildOverlayGeometry` 不動,保留「不是 0% 直線」語意)。順序 = entries 順序(與 legend 一致)。
- **D2 B8**:`river_models` 新增 `is_close_clamped(minute_end, kind) -> bool`(`end < m <= end + _CLOSE_CLAMP`,含跨午夜展開,與 `offset_of` 同一把尺 —— 實作為 `offset_of` 內部抽 `_expand(minute_end, kind) -> (m, start, end)` 共用);
  `push`:`if is_close_clamped(...) and offset in minutes: return`(不覆寫、不更新 `_last_write`);非 clamp 路徑照舊 last-write-wins。`apply_backfill` 不動。
  `[auto-default: 只在 end 格已有值時才不覆寫 | reason: 13:45 真收盤可能因 tick 稀疏而沒落 end 格,這時 13:46 的取樣仍是最佳近似]`
- **D3 B9**:`_heal_gate` 改 `calendar.is_trading_day(_session_date()) and clock_gate()`;新增 `_session_date()`:`now = _now(); d = now.date(); return d - 1 day if now.hour < 6 else d`
  (夜盤跨午夜歸前一日那一場;06:00 切換與夜盤 05:00 收盤 + 自癒閘寬放 5 分一致)。**stock / index 的 clock_gate 凌晨恆 False**,不受影響。
  `[auto-default: 統一在 _heal_gate 處理、不分 session 類 | reason: 凌晨段只有 TXO/futures 的 clock_gate 為真;一把尺不漂]`
  既有測試 monkeypatch `_today` → **該紅(型別:取樣點換成 `_now`)**:改 monkeypatch `_now` 回 `datetime(週六/週二, 10:00)`;新增週六 01:00 → True(週五交易日)/ 週一 01:00 → False / 週三 01:00 且週二假日 → False。

## 成功條件
- SC-1 B7:`RiverOverlay` 七腿 entries 其一 `minutes={}` → readout span 數 = 7、該腿文字 `"<label> —"`、圖上 polyline 數 = 6。驗證:RiverOverlay.test 新案(既有測試不該紅)。
- SC-2 B8:`RiverState` 同腿 push(13:45, A) 後 push(13:48, B) → `minutes[offset(end)] == A`;先 push(13:48, B) 再無 13:45 → B 保留;13:44 → 13:45 照覆寫(非 clamp)。`_last_write` 不被丟棄的 push 更新。驗證:tests/live/test_river_state.py 新案。
- SC-3 B9:上述三例 + 週二 10:00 True / 週六 10:00 False(既有語意)。驗證:test_main_wiring.py 改寫 + 新案。
- SC-4 真環境:merge + 重啟 8721(13:45 後,已過)→ 本週末(週六 00:00–05:00)log `零推播自癒` 對 TXO/futures 仍活、週一凌晨不 churn;**驗證窗口 = 08-22 凌晨 / 08-25 凌晨**,窗口外降級 = SC-3 單元測試 + health sha。前端 B7 過目:相關係數 tab 重疊圖游標移入,缺資料腿印「—」。

## 白名單
- W1 `buildOverlayGeometry` 輸出不變(空腿不畫、y 域不含它);RiverOverlay 既有讀值 / lateStarts / 標籤防疊不變。
- W2 `offset_of` 簽名與輸出不變;`apply_backfill` 不動;非 clamp 分鐘 last-write-wins 不變;換場清空不變。
- W3 `_heal_gate(calendar=None)` 仍逐字等於 clock_gate;交易日白天語意不變(週二 10:00 True、週六 10:00 False);`_today()` 其他用途不動。
- W4 其他 source 工廠接線不變(test_main_wiring 其餘案綠)。

## Out of scope
ES/NQ/YM 以外的收盤 clamp 常數調整、corr 引擎取樣節奏、heal 退避參數。

## Edge cases
1. 13:50 後(> end+5)仍 None 丟棄(既有)。2. end 格無值時 13:46 取樣照寫(D2)。3. 05:30 週六:hour<6 → 週五 → True 但 clock_gate 已 False(夜盤 05:00 收 + 5 分寬放)→ False。
4. 06:00 整:當日;週六 06:00 → False(正確,日盤未開且週六非交易日)。5. entries 有但 g.lines 順序不同 → 以 key 對位。

## Diff 級
- 🔴 `frontend/src/components/corr/RiverOverlay.tsx`(+ RiverOverlay.test 先紅)。
- 🔴 `copycat/live/river_models.py`(新 helper,🟢 可併同 commit 因唯一 caller 是 push)+ `river_state.py` + tests/live 先紅。
- 🔴 `copycat/server/app.py`(`_session_date` + `_heal_gate`)+ test_main_wiring 改寫(該紅:`_today` → `_now` monkeypatch)+ 新案先紅。
- 後端 gate:pytest / ruff / pyright;前端 gate:vitest / tsc / eslint / react-doctor。

---
## Spec review round 1 amendments(`change-spec-review-round-1.json`,9 條全 accepted;以本節為準)
- **B7 該紅更正(R1 / R3)**:測試檔是 `RiverPanel.test.tsx`(無 RiverOverlay.test);L198-208「該分鐘沒有點的腿顯示「—」(全窗無值的道瓊不進讀值列)」**該紅**
  → 改名「全窗無值的腿也進讀值列印「—」」,`queryByText(/^道瓊 /)` 反轉為 `getByText("道瓊 —")`,L206 註解改寫。不該紅:同 describe 其餘 3 案、`RiverPanel.memo.test.tsx`、`river-chart-svg.test.ts`。
  SC-1 改用既有三腿治具 `river-test-fixtures.ts::riverState()`(台指 / 富台 / 道瓊 minutes={}):讀值列同時有 `台指 —` / `富台 —` / `道瓊 —`(游標移入後依 hit 印值或 —)、svg `polyline` 數 = 2、
  `道瓊` 不出現於 svg 右緣 `<text>`;三段文字 DOM 先後 = entries 順序。不另造七腿治具。
- **D2' B8 守門收窄(R2 / R9)**:clamp 區分兩段 —— `m == end + 1`(收盤撮合那一分鐘,13:45:xx / 05:00:xx)**允許覆寫**(base 腿 13:44:xx 每秒取樣已先填 end 格,收盤價必須進得來);
  `m >= end + 2`(13:46 起)且 end 格已有值 → 丟棄(不寫、不更新 `_last_write`)。守門插在 `river_state.py` `offset_of` 之後、寫入之前(set_session 之後)。
  helper 改為 `close_clamp_rank(minute_end, kind) -> int | None`:非 clamp 0、end+1 → 1、end+2..+5 → 2..5、窗外 None(與 `offset_of` 共用 `_expand`)。
  SC-2 改寫:push(13:44:30→825, A) → push(13:45:02→826, B) → `minutes[300] == B`;再 push(13:48→829, C) → 仍 B,`delta()` 仍回 `{m:300, p:B}`(被丟棄的 push 不更新 `_last_write`);
  end 格無值時 13:46 取樣照寫;13:44 → 13:45 照覆寫。
- **R5 留尾**:end 格被 clamp 近似值先佔後,`apply_backfill` 的真 13:45 bar 被「只填尚無值」擋掉 → 記 next-time(per-leg 旗標讓回補覆寫一次)。
- **SC-4 可觀測判準(R4)**:merge + 重啟後以探針為證:`.venv\Scripts\python -c "..."` 載 `load_trading_calendar()`、monkeypatch `app._now` 為 `datetime(2026,8,22,1,0)` / `datetime(2026,8,24,1,0)` / `datetime(2026,8,21,10,0)`,印 `_session_date()` 與 `_heal_gate(cal, in_txo_session)()`,期望 `2026-08-21 True` / `2026-08-23 False` / `2026-08-21 True`。
  真環境窗口(08-22 / 08-25 凌晨)若要看 log,需靠 TC4 靜默時才印的自癒行,**不以「無 log」判 PASS**。
- **R6 同步註解**:`app.py:309` `_heal_gate` docstring 改寫(已知邊界段作廢)、`app.py:380` `_today` docstring 改「日曆**交易日**推導的唯一取樣點;場別起始日另見 `_session_date`」、
  `river_state.py:6-7` 規則 1 補「clamp 第 2 分鐘起不覆寫」、`river_models.__all__` 加 helper。
- **R7 `_session_date` docstring**:「= 夜盤那一場的**起始日**,不是 TAIFEX 交易日;`_resolve_trade_date` / `/api/calendar` / overlay 基準日(app.py L459/460、481、906、1083、1475)一律仍走 `_today()`,不得改用」。W3 逐條列此五處。
- **R8 不變式測試**:不 monkeypatch clock 的組合案:注入 `_now` 為 05:05 / 05:06 / 06:00(週六)+ 真 `in_futures_session_now` / `in_txo_session`,斷言「hour<6 門檻 ⊇ 夜盤收盤 + 寬放」(05:05 週六 → session_date 週五 True 且 clock 寬放內;05:06 → clock False;06:00 → session_date 週六 False)。
