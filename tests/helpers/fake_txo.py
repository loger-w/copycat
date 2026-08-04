"""server route 測試共用的 TXO QuoteSource fake — re-export。

實體已上提到 `copycat/server/verify.py`(`--verify` 模式與測試共用同一份;chore
server-launch-wrapper)。此檔保留原 import 路徑,六組 route 測試不必動。
"""

from __future__ import annotations

from copycat.server.verify import C, SERIES, FakeTxoSource

__all__ = ["C", "SERIES", "FakeTxoSource"]
