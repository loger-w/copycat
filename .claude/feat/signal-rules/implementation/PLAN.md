# PLAN — 訊號規則化(condensed;design v2.1 對應;v2 = impl-spec review R1-R10 修入)

任務順序:T1(signal_rules 模型)→ T2(hub 規則引擎,**純加法**)→ T3(rules routes)
→ **T3b(enabled 家族退役,🔴 單一跨檔 commit)** → T4(前端)。design v2.1 的簽名/
映射表/測試遷移表為單一 spec,本檔只列任務切分與 commit 紀律,細節**以 design 為準
不重抄**。

## T1 `copycat/signal_rules.py`(新)+ `tests/test_signal_rules.py`(新)

design「SC-1 規則模型」節全簽名照抄(PARAM_SPECS 值域、normalize_rule others 排自身 +
int 鍵拒非整數、new_rule_id、default_rules、load 三態+版本+MAX_RULES raise、save OSError
拋、rule_config 映射表含 vol_burst.window_secs→surge_window_secs 與 int() cast)。
失敗測試:值域 parametrized(每 kind 合法/違域/缺鍵/多鍵/bool 拒)、名稱唯一排自身、
levels 規則、三態(缺檔 None/空陣列 []/壞 JSON raise/版本不符 raise/超 MAX raise)、
default_rules 對 legacy flags 的 enabled 對映、rule_config 逐 kind 欄位斷言(含 cooldown
落點與 int 型別)。

## T2 `copycat/server/signal_hub.py` + `tests/server/test_signal_hub.py`(**純加法**,R1)

design「SC-2/3/5 hub」節全部:`_RuleSlot`(frozen dataclass)、slots 單 dict、
`_rule_seq`、basis cache `(basis_date, cdp)`、`_staged_cache`+`_staged_date` 三動作、
**`_resolve_basis` 做日別比對與丟棄(不寫 cache/不分發/不餵 None);`_distribute(code)`
只做 levels 過濾與 set_basis(R9)**、`_seed_slot`、CRUD 順序(save 成功 → 同步區塊
swap+seed)、per-rule try/except 評估迴圈、now_fn 三處注入、fanout(rule_id/rule_name/
新 _event_id/notify_discord gate/format_signal_text 附規則名)、遷移(load None →
default_rules(legacy)落檔)、**drop_code 逐 slot + 雙 cache pop(R3)**、docstring
id 格式同步。
**enabled 家族本任務不刪**(R1):`_enabled`/`set_enabled`/routes 暫存共存(舊 API
仍可用但已不影響評估 — 評估只讀 slots);`_load_enabled` **保留改名 `_legacy_flags()`**
(遷移專用,R2)。

commit:
1. 紅測試 `[red]`:規則組 + 改寫類既有測試(key set∪{rule_id,rule_name}、新 id 含
   rule 段、staged/rollover 改 hub cache 斷言、`hub._detector` monkeypatch 改逐 slot)+
   design 邊界 edge 1/2/3/4/6/7/8 測試(**edge 5 的 503 降級歸 T3,R4;T2 只測
   `load_rules 壞檔 raise → SignalHub 建構往外拋`**)+
   `test_watchlist_removal_stops_all_rules`(R3:≥2 規則、移除後兩顆皆停發、雙 cache
   無該 code)+ `test_migration_reads_legacy_flags`(R2:預寫 `{"vol_burst": false}`
   → 冷啟動後該預設規則 enabled False)
2. 實作 `🟢 feat(backend): 訊號規則引擎(per-rule detector + 熱重載) [green]`

## T3 `copycat/server/app.py` + `tests/server/test_signal_routes.py`(既有檔)

design「SC-4/6 routes」節:四條 rules route、RuleBody、錯誤碼三張(400/404/500
RULE_SAVE_FAILED)、PUT path id 為準、handler 與 WatchlistError 同區。
紅:CRUD happy + 錯誤碼 parametrized + 熱重載(PUT 後 hub.rules() 反映)+
RULE_NOT_FOUND 404 + **`test_bad_rules_file_degrades`(R4:壞 rules 檔 → hub None +
四條 rules route 503 NOT_READY)**。此任務**不動** enabled routes。

## T3b enabled 家族退役(🔴 單一跨檔 commit,R1/R6)

1. 紅 `🟢 test(backend): 舊 enabled route 退役契約 [red]`:
   `test_legacy_enabled_route_gone`(hub 就緒下 GET/PUT `/api/stock/signals/enabled`
   皆 404,R5)
2. `🔴 fix(backend): 移除訊號 enabled 開關家族(route 404) [green]` — 同一 commit:
   hub 的 `enabled()`/`set_enabled`/`_enabled`/`_enabled_set`/`_as_set`/`_enabled_lock`/
   `_write_enabled`(`_legacy_flags` 與 `_ENABLED_FILE` 常數**保留**)+ app.py 兩條
   enabled routes + `SignalsEnabledBody` + test_signal_hub 的 enabled 3 條
   (:461/:494/:527)+ test_signal_routes 的 `TestSignalsEnabledRoute` 5 條 +
   兩處 503 清單(:169-175/:251-261)換打 rules route。
   純刪除的測試變更在此 🔴 commit 內(非獨立 chore — 它們與行為移除同生死,R6)。

## T4 前端(signal-model / useSignalRules / StockPage / SignalRail / SignalRulesDialog
/ **useSignalsConfig.ts 刪除(R7,連同其測試同一清理 commit)**)

design「SC-7/8 前端」節 + 測試遷移表(useSignalsConfig.test 刪、signal-model filterKinds
describe 刪、SignalRail ≥3 條重寫、StockPage.test stub 補 rules 分支)。
紅測試另補(R8):`useSignalRules.test.tsx`(POST/PUT 分歧以 fetch stub 斷 method+URL、
400 errText 取 detail.error、成功 invalidate)+ SignalRail 的 `rule_name` 缺值 →
kind 文案 fallback 一條(升級當日舊 jsonl 情境)。
commit:清理(刪檔類,chore 無 emoji tag)→ 紅 [red](規則列/Dialog/表單/feed 規則名,
文案逐字)→ 綠 [green]。dialog 樣板 = WatchlistManagerDialog;jsdom 紀律照
frontend-testing skill。

## 驗證 gate(Phase 5)

pytest -q 全案 + ruff + pyright + vitest + tsc -b + eslint 全綠。
`copycat validate` 豁免(R10):本 feature 零觸碰 replay/engine 鏈;harness.json verify
陣列無 validate;worktree 無 data 種子(前兩輪同慣例,豁免理由記 automated-verification.md)。

## 非自動化交付項

- SC-7 AI 截圖(規則列 + Dialog 開啟 + 編輯表單三張)+ user 過目;規則 UI 不依賴盤中。
- 盤中真 tick 觸發自訂規則 = user 過目層(非 blocking)。
