# fix/sparse-review-followups — change spec

來源:`docs/superpowers/specs/pr-120-review.md` F-01 ~ F-05(全 Nice;F-04 ask-user → user 08-27 晚拍板**改必填**);
三輪 pr-review 修復鏈第三輪。無 UI、無 API、無 migration。

## 現況 vs 目標

| Finding | 現況(PR #120 後) | 目標 |
|---|---|---|
| F-01 | CLAUDE.md §4 誤標症狀「session 死時該腿整場不救」寫反 | 「單腿死(其他腿還在推,R1 不成立)時整場不救;session 整條死仍由 R1 整批救」 |
| F-02 | `sparse` 非 bool 靜默變 False(fail-safe 對,無訊號) | `_parse_legs` 印 WARNING 點名 key 與原值;行為不變;caplog 斷言 |
| F-03 | `test_sparse_symbol_does_not_keep_r1_from_firing` 名與斷言方向相反 | 改名 `…_does_not_trigger_r1_while_another_leg_is_alive`,本體不動 |
| F-04 | `_default_corr_source(calendar=None, config=None)` + fallback;四個測試 caller 不帶 | `config: CorrConfig` 必填、刪 fallback;四個 caller 顯式 `load_config()` |
| F-05 | 舊 verification §5 stash 整檔(與紅先行同源) | mutation 級:只撤 `continue` 兩行,實跑 2 failed / 2 passed 記回 |

## Caller map

| 讀者 | 本次 |
|---|---|
| `app.py` lifespan(唯一 prod caller,`corr_cfg` 已帶) | 不動;漏傳即 pyright 紅(實跑突變 1 error) |
| `tests/server/test_main_wiring.py` 四個 caller | 顯式傳 `load_config()`(其中一個原本就帶自建 `CorrConfig`) |
| `corr_config._parse_legs` 讀者:`load_config` → `DEFAULT_CONFIG` 降級鏈 | 只加 WARNING,回傳值逐字同前 |
| `tc4._heal_tick` `continue`(F-05 只驗不改) | 不在 diff |

## 既有行為白名單(不得變)

1. `load_config` 對合法 / 非法 sparse 的回傳值逐字不變(`[False, True, False, False, False]` 斷言保留)。
2. `_default_corr_source` 對 prod caller 的行為不變(同一份 config 進 source);只有簽名收緊。
3. `tc4.py` 不在 diff;R1 / R2 行為不動(F-05 是驗證不是改動)。
4. 測試改名不動本體;caplog 斷言只加不減。

## 驗證 seam

- `tests/test_corr_config.py::test_sparse_flag_is_optional_and_only_literal_true_counts`(紅先行 `AssertionError: []` → 綠)。
- F-04 型別守門:prod caller 拿掉 `corr_cfg` → `pyright` 1 error(實跑;還原後 0)。
- F-05:`tests/live/test_tc4.py -k HealSparse` 撤 `continue` 兩行 → 2 failed / 2 passed。
- 真實環境:無;08-28 `grep 零推播自癒 | grep SXF` 全日 0 筆仍是 #120 本體的待驗項。
