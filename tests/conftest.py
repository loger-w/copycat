"""全域測試隔離:capital factory 的 repo root .env fallback 在測試中一律中和。

factory._getenv 的 dotenv fallback(Phase 6 real-env finding)會讓「未設 env」的測試
在開發機吃到真 .env 憑證 — 最壞情況 lifespan 把真 SKCOM DLL 載進測試進程(segfault)。
需要 dotenv 行為的測試(TestDotenvFallback)自行 monkeypatch 還原真實作。
"""

from __future__ import annotations

import pytest

import copycat.capital.factory as _capital_factory


@pytest.fixture(autouse=True)
def _neutralize_capital_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_capital_factory, "_dotenv_values", lambda: {})
    monkeypatch.setattr(_capital_factory, "_dotenv_cache", None)
