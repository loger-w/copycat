# refactor/f20-corr-leg-keys-from-config — verification

來源:/pr-review #111 F-20 ask-user(`docs/superpowers/specs/pr-111-review.md`);user 2026-08-26 拍板「改」。
改動:`tests/server/test_corr_routes.py` / `test_river_routes.py` 四份 11 腿 key 字面集合 → `load_config(CONFIG_PATH)`
導出 `_LEG_KEYS` / `_PAIR_KEYS`(pairs = legs − base);逐字契約只留 `tests/test_corr_config.py::_EXPECTED_LEGS`。
🔵 純測試整理,行為與生產碼零改動(diff 只在 tests/)。

## 自動化 gate(主 tree,commit 61ca1373)

| gate | 結果 | exit |
|---|---|---|
| `pytest -q tests/server/test_corr_routes.py tests/server/test_river_routes.py tests/test_corr_config.py` | 31 passed, 1 warning | 0 |
| `ruff check copycat tests` | All checks passed! | 0 |
| `pyright tests/server/test_corr_routes.py tests/server/test_river_routes.py` | 0 errors, 0 warnings | 0 |

全套 pytest / validate 不重跑:diff 不碰生產碼,四份字面集合原本就與 repo config 相等(改前綠、改後綠,語意等價)。

## Review 收修後重跑(f121326f + S3 收修 commit)

31 passed / `ruff check copycat tests` All checks passed / pyright 三檔 0 errors。mutation(spec 軸實證):drop-GC / add-XX 兩種變異下 corr.legs / corr.pairs / river.legs 三條斷言全翻紅。

## 真實環境

不適用(測試檔重構,無 runtime 行為)。
