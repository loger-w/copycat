"""全域測試隔離:capital factory 的 os.environ 憑證與 repo root .env fallback 一律中和。

factory._getenv 讀 os.environ + repo root .env(Phase 6 real-env finding)— 開發機 shell
已 export CAPITAL_* 憑證、或 repo root 有真 .env 時,「未設 env」的測試會吃到真憑證,
最壞情況 lifespan 把真 SKCOM DLL 載進測試進程(segfault)。故全域 autouse 完整隔離
(review round-2 I6):CAPITAL_* 全 key delenv + 單例重置 + dotenv 中和。
需要 dotenv 行為的測試(TestDotenvFallback)自行 monkeypatch 還原真實作。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import copycat.capital.factory as _capital_factory
import copycat.server.discord_bot as _discord_bot
from copycat.server.verify import CAPITAL_ENV_KEYS, DISCORD_ENV_KEYS

# TC4 官方 wrapper(spikes/TCPY)不在版控(.gitignore:9)→ 乾淨 checkout 與新 worktree
# 一律缺它。真的要 import 它的測試必須 skip 而非紅:紅會讓「環境沒裝」看起來像「程式壞了」。
# 路徑與 live/tc4.py 的 sys.path.insert 指向同一處(repo_root/spikes/TCPY)。
TCPY_DIR = Path(__file__).resolve().parent.parent / "spikes" / "TCPY"

requires_tcpy = pytest.mark.skipif(
    not (TCPY_DIR / "tcoreapi_mq.py").exists(),
    reason=f"TC4 官方 wrapper 不在版控,此環境未就緒:{TCPY_DIR}",
)

# key 清單的唯一一份住在 copycat/server/verify.py(--verify 模式的 env 壓制同一組;
# 上面 import 即 re-export — test_factory._isolate 沿用 `from tests.conftest import` 不變)
__all__ = ["CAPITAL_ENV_KEYS", "DISCORD_ENV_KEYS", "requires_tcpy"]


@pytest.fixture(autouse=True)
def _neutralize_capital_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CAPITAL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_capital_factory, "_client", None)
    monkeypatch.setattr(_capital_factory, "_dotenv_values", lambda: {})
    monkeypatch.setattr(_capital_factory, "_dotenv_cache", None)


@pytest.fixture(autouse=True)
def _neutralize_discord_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAPITAL_* 同型隔離(impl-review R5):開發機 shell 或 repo root .env 裡的真 bot
    token 一旦流進測試,`create_bot` 的降級路徑會靜默走成「真的去登入 Discord」。"""
    for key in DISCORD_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_discord_bot, "_dotenv_values", lambda: {})
    monkeypatch.setattr(_discord_bot, "_dotenv_cache", None)
