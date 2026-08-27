"""群益損益報告(4-2-p 未實現-彙總)列 fixture,test_client / test_fill_latency 共用。

**30 欄**對齊 prod 實列(欄形同 `tests/capital/test_balance.py::RAW_PNL_MARGIN`,2026-06-11 去敏實錄):
[1]股號 [3]種類標籤 [4]股數 [5]報告市價 [9]損益 [10]均價 [12]成交價金 [25]種類代碼(標籤亂碼時的備援;
索引語意 = `copycat.capital.balance._PNL_IDX_*`)。

舊 25 欄字面(pr-119 F-05)把成交價金放在 [11]、沒有 [25] → `_PNL_IDX_COST` 解出 0、[25] 備援永遠走不到,
而且散在兩個測試檔共六份 —— 沒人斷 `pnl_cost` 所以一直零訊號。變異一律走 `pnl_variant`(按欄索引),
不 `.replace` 猜字串。
"""

from __future__ import annotations

#: 3357 融資 3000 股,均價 150.55(配 `_BAL_3357` 的 155.63 給 balance 鏈測試斷言)。
#: 與 `test_client._PNL_3357`(prod 實列,均價 311.75)是兩組值,後者給 collector 欠帳 / 遲到那組。
PNL_3357_MARGIN: str = (
    "臺慶科,3357,新台幣,融資,3000,156.00,0.27,468000.00,464000.00,12345.00,150.55,464000.00,451650.00,"
    "0.00,665.00,0.00,1404.00,135495,316155,89,0.00,2.73,0,,Y,2,3,150.860000,A123456789,1234567890"
)


def pnl_variant(row: str, changes: dict[int, str]) -> str:
    """按欄索引改值。種類標籤 [3] 與種類代碼 [25] 要**成對**改(現股 1 / 融資 2),否則產出
    「標籤現股 / 代碼 2」自相矛盾列,把 [25] 備援遮住(pr-119 review round 1)。"""
    parts = row.split(",")
    for i, v in changes.items():
        parts[i] = v
    return ",".join(parts)
