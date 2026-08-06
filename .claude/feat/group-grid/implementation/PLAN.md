# PLAN — 群組多檔即時分時圖(condensed;design v3 對應;v2 = impl-spec R1-R12 修入)

任務順序:T1(engine)→ T2(hub 摘要 + route + app 接線)→ T3(前端)。
細節以 design v3 為單一 spec 不重抄。

## T1 `copycat/server/stock_engine.py` + `tests/server/test_stock_engine.py`

design「SC-1/2 後端」engine 段 + 「SC-4 唯讀 batch 端點」engine 側:
- `quotes()`(local 參照 `_watchlist`、`_quote_payload` 單一定義、meta.name)
- `group_snapshot(codes)`:`state.snapshot()` 後挑 minutes/meta 兩鍵;
  **no_data 推導式 = `code in self._no_data or code not in self._states`**(R9 —
  StockDayState.snapshot() 無此鍵、engine.snapshot() 對未知 code 回 False 語意相反,
  此處刻意不同,docstring 註明);`backfilling = code in self._backfill_pending`;
  未回補(不在 `_backfilled` 且不在 `_backfill_pending`)的**已訂閱**成員
  `put_nowait((code, generation))`
- **backfill guard 兩處都改(R1)**::631 取件早退去掉 `code != self._main`(只留
  generation 比對);:653 套用 guard 同(job 自帶 code + generation;job 現形已是
  `tuple[str, int]`,不需改形)
- **雙 set(R3)**:`_backfill_pending`(入列時加;worker 取件後 — 套用/失敗/丟棄 —
  一律 discard;= dedup 與 backfilling 的唯一來源)+ `_backfilled`(**套用成功**才加
  = 今日已回補判準);**四個既有入列點**(set_main/rollover stage2/reconnect/漲跌停變)
  一併寫入 pending(成功後入 backfilled);清空點 = `_rollover_stage2` +
  `_handle_reconnect` **顯式 clear 兩 set**(R4 — reconnect 不 bump generation 是
  實碼事實,漏清 = 斷線缺口整天不補)
失敗測試:quotes 形/迭代中換名單不炸不漏/F: 偽鍵排除;group_snapshot 形/未知 code
no_data true/job 入列一次(重打不重複)/backfilling 旗標時序(pending 中 true、
成功後 false);**端到端(R1)**:非主檔成員經 group_snapshot 入列 → drain 後
`snapshot(code)["minutes"]` 有回補列;reconnect 後可重入列(R4)。
**既有測試事前標記該變(R2)**:`test_stale_backfill_not_applied_after_main_switch`
釘的舊語意(切走主檔 job 不落地)被本輪推翻 — 新契約 = 「job 落地到它自己的 state,
generation 作廢照舊」,改寫入紅 commit body 標記;`test_rollover_generation_voids_…`
不動。**commit 分類(R2)**:guard 語意改動獨立 `🔴 fix(backend)` commit
(紅 [red] → 🔴 [green]),群組新 API 才掛 🟢。

## T2 `copycat/server/signal_hub.py` + `copycat/server/app.py` + 對應測試

- hub:`groups_fn: Callable[[], list[Group]] | None`(R6 — Group 自
  `copycat.stock_watchlist` import,lambda 才過 pyright)/`quotes_fn` keyword-only
  注入(None = 停用)、on_watchlist 刷新 `_groups`(try/except 保舊值)、
  `_group_suffix(row)`(design 規則全文)、`_send_discord` 串接
- app:hub 建構傳兩 fn;route `GET /api/stock/group-state`(design v3 形狀/錯誤碼:
  空 codes 200 {}/BAD_CODES/BAD_CODE/503;無 404)
失敗測試:摘要格式逐字(含 edge 1/2/3/7 + **edge 4:自選內不屬任何群組的 code →
尾綴 ""**,R10)、groups_fn 例外保舊、notify gate 不受影響;
route 測試進 **`tests/server/test_stock_routes.py`**(R8),set_main 斷言 =
打完 group-state 後 `app.state.stock._main is None`;
**整合接線測試(R7)**:booted client + 含群組自選檔 → `app.state.signal_hub._groups`
非空 + `_group_suffix` 對群組成員 row 產非空字串(防「兩 fn 忘接、預設 None 靜默停用」)。

## T3 前端 + 測試(colocated)

- `lib/stock-accum.ts`:抽 `minutesFromRecord(rec)` 共用、`fromSnapshot` 改呼叫
  (R12:**獨立 🔵 refactor commit**,既有 stock-accum.test 全綠 = 零行為變更證據;
  不開新檔)
- `hooks/useGroupSnapshots.ts`(design v3:單一 batch query、函式形 refetchInterval
  + inTradingHours、enabled gate、空 codes 不請求;**回傳含 backfilling**,R5)
- `components/stock/MiniIntradayChart.tsx`(R5/R13 幾何補償 + R10 延伸規則 + lock tests)
- `components/stock/GroupGridView.tsx`(下拉/卡片/空態三種/R11 價格 p ?? ref/整卡 button)
- `components/stock/StockPage.tsx`(R6 pill 掛 main 頂層兩條件外;onPick;
  localStorage `copycat-stock-view`)
- `GroupGridView` 卡片三態優先序(R5):`backfilling`(「回補中…」)→ `noData`
  (「無資料」)→ 常態
失敗測試:design v3 各 lock test(x 滿版/y 域/hasRef/延伸窗規則/空群組零請求/
code=null 可切群組/卡片價 ref 態)+ **edge 5:selected group 被刪 → fallback 第一個
群組**(R10)+ **batch 整批失敗 → 全部卡片「無資料」**(R10 — edge 6 隨 batch 化
更正,brainstorm 註記)+ 文案逐字(四態)。
既有測試遷移(R11):`StockPage.test.tsx` fetch stub 補 `/api/stock/group-state`
分支(回 `{states:{}}` 或種一檔);`localStorage.clear()` 確保預設單檔檢視。

## Commit / tag

各 task 紅 [red] → 綠 [green];**T1 拆兩對**:guard 語意改動(含 R2 事前標記的既有
斷言改寫)= 🔴 fix 對;群組新 API(quotes/group_snapshot)= 🟢 feat 對。
T3 的 stock-accum 抽共用 = 獨立 🔵 refactor commit。

## 驗證 gate(Phase 5)

六 gate(pytest/ruff/pyright/vitest/tsc/eslint);validate 豁免同前三輪(零觸碰 replay 鏈)。

## 非自動化交付項

- SC-3 AI 截圖(群組 grid 常態 + 空態)+ user 過目;fake server 可種群組與分鐘資料。
- 盤中同群摘要 Discord 實發 = user 過目層。
