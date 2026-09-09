# refactor/bars-cache-daily-entry — 設計記錄(handoff W3 SESSION B1)

## Why gate

- **動機**:`copycat/server/bars.py::BarsCache` 的日 K memo 是三份同鍵 `(code, today)` dict
  (`_daily` / `_daily_tag` / `_daily_pre_final`)。每次 `daily_put` / `prune` 要三處同步,漂掉零錯誤訊號
  (純記憶體無界成長,或「無快照但標記還在」這類 `_period_pre_final` 假設被打破)。two-axis review J3
  (bug/futures-daily-cache-night)已判「第三份起收成 `_DailyEntry` 的效益高於單點改動成本」,
  next-time 09-07 盤點列 W3 B1,user 拍板做。
- **為什麼是現在**:W1 批(PR #202)剛把 `prune` 三段清理的測試補齊(B11),保護就位;
  W2(PR #211)後日 K 定稿界語意穩定,不會再有並行的行為改動撞這段。

## 設計(codebase-design 詞彙)

- **Module** = `BarsCache` 日 K memo;**interface** = `daily_get / daily_stale / daily_put /
  daily_tag_get / daily_tag_put / pre_final_written_at` + `prune`。全 repo 零處直戳三份 dict
  (grep `_daily_tag|_daily_pre_final` 只剩歷史 artifact / review 報告),所有 caller
  (`build_daily` / `build_period` / `_warn_if_not_advanced` / `_period_*` / tests)都走這個 seam。
- **Seam 不動、公開方法簽名不動**。`_DailyEntry`(`@dataclass`,三欄皆 Optional 預設 None)是
  implementation 內的 internal seam;不匯出到別的 module。不合併 `daily_put` + `daily_tag_put`:
  `build_daily` 沒有 tag,合併 = 改 interface = 越界成 mod。
- **必須保住的 interface 事實**(改前先以 characterization 釘住,🟢 commit 4afce9b6):
  1. tag 不被 bars 的覆寫帶掉(entry 用 `setdefault` 而非整格替換);
  2. 只有 tag 沒 bars 不算快照(`daily_get` / `daily_stale` / `pre_final_written_at` 全回 None);
  3. tag put 不動 bars 與界前標記;
  4. 空 bars 的 `daily_put` 對三欄全 no-op,含過界也不 pop 標記(墊背路徑靠它)。
- **結構收益**:`prune` 三段收一段(同鍵同格 = 結構保證);「無快照時標記必也不在」的寫入半邊仍是
  `daily_put` 的**單點約定**(空手早退、標記只隨非空 bars 寫入)—— 從「兩條跨 dict 約定」收成
  「一條單點約定 + prune 結構保證」,三欄型別上各自 Optional、不是型別級保證(review Spec-01 回校)。
- **不做**:`daily_put` 簽名加 tag 參數、對 `build_daily` 路徑補 tag、`_DailyEntry` 加方法。

## 步驟(每步單獨綠)

1. 🟢 `test(backend)` characterization 四條(4afce9b6)。
2. 🔵 `refactor(backend)`:`_DailyEntry` + 六方法 + `prune` + 三處 docstring(`_period_stale_or_empty`
   註解、`build_period` docstring 的「三處 → 兩處」、`PeriodBars` docstring「pop → 清成 None」);
   test_bars.py 註解回校。收修:更名底線前綴(S-02 / Spec-02)、四條 characterization 搬
   `TestDailyEntryFields`(S-05);`slots=True`(S-03)拒絕 —— grep 實測 copycat dataclass 主流是
   `frozen=True` 無 slots,可變型鄰居(`stock_state` / `aggregate`)亦裸 `@dataclass`。
3. 收尾:two-axis review(Standards 主、Spec 對照「行為不變」)→ gate → PR。
