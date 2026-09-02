# Verification — fix/pr-177-review-followups

pr-177 review 16 條 finding 的收修批(user 2026-09-02 拍板:F-01 選「接受現況」、
F-12 補 commit、其餘一輪修;F-16 維持 no-op 不動)。

## 拍板落地

- **F-01(接受現況)**:S-1 重武裝語意**不改** —— 跟鎖漲停場景「反彈未過前高 = 力竭」,
  V 型反彈後的回檔訊號仍有資訊價值。改的是文件與測試:`_eval_pullback` docstring 把
  「不可能連發」改寫成「已知且接受的代價」(沿跌仍不會連發的半句保留,它是對的);
  seam 類 docstring 同步(F-06);新增 `test_v_bounce_below_peak_rearms_and_refires_accepted`
  以 review 的實例數列(104.5 → 102.4 發 → 反彈 104.45 重武裝 → 102.36 再發)釘住接受
  的行為 —— 日後要改嚴,這條就是「該變」的那條。
- **F-02**:重武裝基線 O(1) 化 —— 波狀態加存發訊價,`窗頭早於發訊時點 ⇔ 發訊筆還在窗內
  → 基線 = 發訊價`,免逐格掃窗;公式收斂到 `_change_pct` 單源(surge / 武裝 / 重武裝同式)。
  等價性:72→73 條狀態機測試全綠 + 鼎元 replay 數字逐字不變。
- **F-03**:routes `_RULE_PARAMS` 補 kind + `test_post_surge_pullback_round_trips`(wire 鏈)。
- **F-04**:`test_seed_id_collision_with_existing_dedups`(凍 epoch 造撞);**突變體驗證**:
  移除 `while rule_id in ids` 迴圈 → 該測 FAILED,還原 → 149 passed(KILLED)。
- **F-05**:append INFO ×2 與 MAX_RULES 跳卡 WARNING ×2 補 caplog 斷言。
- **F-07**:`default_rules` / hub `_legacy_flags` 註解改寫成真機制(鍵恆在、檔案可關)。
- **F-08**:`_seed_params` 補 surge_pullback branch,種子卡改 `{**_seed_params(...), "pct": pct}`
  —— `{}` 陷阱與手抄 clamp 一起消。
- **F-09**:0 價註解收窄(峰值保護屬實;窗污染 = `_eval_surge` 既有盲點另題)。
- **F-10**:`_SUPPORTED_VERSIONS = tuple(range(1, _CACHE_VERSION + 1))` 推導。
- **F-11**:模組 docstring 四類 → 五類。
- **F-12**:`bars_2426.json`(24.5 KB)入 evidence、腳本 repo-root 相對化;
  **實跑重現**:`python .claude/feat/surge-pullback-signal/evidence/replay_2426.py` →
  「1% 卡 4 則 / 2% 卡 4 則」與 PR #177 verification 數字逐字一致。
- **F-13**:plan.md #6「configs/signals.json 可覆寫」改寫為死旋鈕事實。
- **F-14**:三處 by_kind 改 by_name(塌卡消)。
- **F-15**:`_write_versioned` module-level 單源;`TestMigrationV1ToV2` → `TestMigrationFromV1`、
  `test_one_rule_per_kind_all_valid` → `test_seeded_rules_all_valid`。
- **F-16**:no-op(review 已 REFUTED,與檔內既有格式一致)。

## Gates

| Gate | 結果 |
|---|---|
| `pytest -q` 全量 | **3348 passed, 3 skipped**(exit 0) |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors |
| `copycat validate`(four/five replay 先行) | 42/42 PASS |
| 前端 | 本批零前端檔變更,前端 gate 不適用 |
| 突變體 | F-04 迴圈移除 → 1 failed(KILLED)→ 還原 149 passed |
| 證據重跑 | replay_2426.py 自入版控輸入完整重現 |
