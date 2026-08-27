# fix/sparse-review-followups — verification

主 tree 直做;branch 自 master `44722310` 開。來源 `docs/superpowers/specs/pr-120-review.md` F-01 ~ F-05(F-04 user 拍板
改必填);三輪 pr-review 修復鏈第三輪(鏈尾)。無 UI、無 API、無 migration;前端零改動(不跑 npm gate)。

## 1. 紅先行

- F-02(`e0d751e7`):`test_sparse_flag_is_optional_and_only_literal_true_counts` 補 caplog 斷言 → 紅 `AssertionError: []`
  (1 failed, 143 passed)→ `43608236` `_parse_legs` WARNING → 144 passed。
- review S-4(`8bbfc50e`):補 `"sparse": null` 案 + 斷言收緊 → `59faa1d7` 改 `"sparse" in item` 判 → 155 passed。

## 2. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `e0d751e7` | test | F-02 紅先行;F-03 改名;F-04 四個 caller 顯式傳 config |
| `43608236` | 🔴 | F-02 `_parse_legs` 非 bool WARNING(行為不變) |
| `f327843b` | 🔵 | F-04 config 必填、刪 fallback |
| `b7828d9e` | chore | F-01 CLAUDE.md §4 |
| `e03cf0f8` | chore | F-05 舊 verification §5 mutation 級實錄 |
| `8bbfc50e` / `59faa1d7` / `41f45bc4` / `0692efcb` | test / 🔴 / 🔵 / chore | review round 1 收修(見 JSON) |

## 3. 反向 / 守門驗證(mutation 級)

| 突變 | 結果 |
|---|---|
| F-04:prod caller `_default_corr_source(trading_calendar)`(漏傳 config) | `pyright` 1 error(還原後 0)—— 型別守住不變量 |
| F-05:`tc4._heal_tick` 的 `if sym in self._heal_sparse: continue` 兩行以 `# MUTANT` 取代 | `-k HealSparse`:`2 failed, 2 passed`(`is_exempt_from_r2` + `…while_another_leg_is_alive` 紅;R1 仍救稀疏腿那條綠);`git checkout --` 還原,grep MUTANT = 0 |
| F-02:拿掉 WARNING(= `e0d751e7` 當下) | caplog 斷言 `AssertionError: []` |

**事故**:F-04 突變腳本在還原前 crash(subprocess 路徑),突變體被接著 commit 進 `2e31a9bc`(f327843b 前身);
commit 後 `git show HEAD:copycat/server/app.py` 對照發現,`reset --soft` 回 `43608236` 重做兩筆。教訓:mutation 腳本
`try/finally` 還原、commit 前 `git diff --cached` 對照預期範圍(同 memory「commit 前查 MUTANT 殘留」)。

## 4. 白名單核對(change-spec §白名單;Standards 軸 4/4 PASS,主 session 復核)

1. `load_config` 回傳值逐字不變 —— `[False, True, False, False, False, False]`(新增 null 案亦 False)。
2. prod caller 行為不變 —— `app.py` 只改簽名 / 傳參形式(`config=corr_cfg`),同一份 config 進 source。
3. `tc4.py` 不在 diff —— `git diff 44722310...HEAD --stat` 無 tc4.py。
4. 測試改名本體不動(Spec 軸 `git show 44722310:` 逐字比對);caplog 只加不減。

## 5. pr-120 finding 對帳

F-01 PASS / F-02 PASS / F-03 PASS / F-04 PASS(keyword-only,`calendar` 預設值與兄弟工廠同形)/ F-05 PASS(Spec 軸以 pytest
plugin 執行期置空 `_heal_sparse` 獨立複現 2 failed / 2 passed,不改 repo 檔)。

## 6. 自動化 gate(最終 HEAD,主 tree)

```
3132 passed, 1 warning in 186.05s (0:03:06)   # pytest 全量
All checks passed!                             # ruff
0 errors, 0 warnings, 0 informations           # pyright
42/42 PASS                                     # copycat validate
```

## 6a. two-axis review round 1(`code-review-round-1.json`)

Standards 6(P2×1 / P3×5)+ Spec 3 P3 + 1 記錄項;零 P1;白名單 4/4;三類分離 PASS;全部收修。

## 7. 真實環境

- 行為只多 WARNING;prod 不需為本輪重啟(prod 8721 = 7f4bc98d 含 #128;#129 / #130 隨下次重啟帶上)。
- 08-28 盤後 `grep 零推播自癒 logs/server-20260828-*.log | grep SXF` 全日 0 筆(#120 本體待驗);
  手改 `configs/correlation.json` 把 sparse 打錯 → 啟動 log 點名該腿(本輪新訊號)。
