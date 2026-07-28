"""全域測試隔離:capital factory 的 os.environ 憑證與 repo root .env fallback 一律中和。

factory._getenv 讀 os.environ + repo root .env(Phase 6 real-env finding)— 開發機 shell
已 export CAPITAL_* 憑證、或 repo root 有真 .env 時,「未設 env」的測試會吃到真憑證,
最壞情況 lifespan 把真 SKCOM DLL 載進測試進程(segfault)。故全域 autouse 完整隔離
(review round-2 I6):CAPITAL_* 全 key delenv + 單例重置 + dotenv 中和。
需要 dotenv 行為的測試(TestDotenvFallback)自行 monkeypatch 還原真實作。
"""

from __future__ import annotations

import pytest

import copycat.capital.factory as _capital_factory

# factory 讀取的全部環境變數 key(test_factory._isolate import 同一清單,消除兩處漂移)
CAPITAL_ENV_KEYS = (
    "CAPITAL_USER_ID",
    "CAPITAL_PASSWORD",
    "CAPITAL_FULL_ACCOUNT",
    "CAPITAL_ENV",
    "CAPITAL_ORDER_ENABLED",
    "CAPITAL_MAX_QTY",
    "CAPITAL_MAX_AMOUNT",
    "CAPITAL_DLL_DIR",
    "CAPITAL_AUDIT_DIR",
    "TXO_AUDIT_DIR",
)


@pytest.fixture(autouse=True)
def _neutralize_capital_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CAPITAL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_capital_factory, "_client", None)
    monkeypatch.setattr(_capital_factory, "_dotenv_values", lambda: {})
    monkeypatch.setattr(_capital_factory, "_dotenv_cache", None)
