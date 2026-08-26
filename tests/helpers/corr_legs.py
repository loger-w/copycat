"""corr / river route 測試共用的腿集合 —— 單一定義處(F-20 review S3)。

來自 repo configs/correlation.json;逐字契約只鎖在 tests/test_corr_config.py::_EXPECTED_LEGS,
這裡導出的是「route 要把設定檔那組原封不動吐出來、配對 = 各腿 vs base」的相對語意。
"""

from __future__ import annotations

from copycat.corr_config import CONFIG_PATH, load_config

CFG = load_config(CONFIG_PATH)
LEG_KEYS = frozenset(leg.key for leg in CFG.legs)
PAIR_KEYS = LEG_KEYS - {CFG.base}
