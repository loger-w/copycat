"""全域測試隔離:外部 IO 憑證(capital / discord / FinMind)與 .env fallback 一律中和。

factory._getenv 讀 os.environ + repo root .env(Phase 6 real-env finding)— 開發機 shell
已 export CAPITAL_* 憑證、或 repo root 有真 .env 時,「未設 env」的測試會吃到真憑證,
最壞情況 lifespan 把真 SKCOM DLL 載進測試進程(segfault)。故全域 autouse 完整隔離
(review round-2 I6):CAPITAL_* 全 key delenv + 單例重置 + dotenv 中和。
需要 dotenv 行為的測試(TestDotenvFallback)自行 monkeypatch 還原真實作。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import copycat.capital.factory as _capital_factory
import copycat.server.discord_bot as _discord_bot
import copycat.server.finmind_token as _finmind_token
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


#: FinMind(finmind_token)是第四條外部 IO 出口。key 名在此重述一份而不 import 常數:
#: 那是新模組的私有名,測試基建不該綁它的內部符號
#: (verify.py 檔頭同一條理由:不讓 [live] extras 變成整套測試的硬依賴)。
FINMIND_ENV_KEY = "FINMIND_TOKEN"


@pytest.fixture(autouse=True)
def _isolate_watchlist_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """hub 落點隔離(XR-3 SC-8)—— **必須住在 root conftest,不得下放 tests/server/**。

    SignalHub 解耦後恆建,`data_dir` = `wl_path.parent`:沒顯式傳 `stock_watchlist_path`
    的 app 測試會落在 repo 真 `data/`,把 `signal_rules.json` / fake 訊號寫進 prod 的
    `data/signals/*.jsonl`(today 端點的歷史真相源)。故 autouse 一次隔離
    `app.py` call-time 讀的模組級 `WATCHLIST_DEFAULT_PATH`;顯式傳路徑的測試不受影響。

    住 root 的理由(2026-08-20 實證,pytest 9.1.1):子目錄 conftest 的 autouse 在
    「server 檔、tests 根檔、server 檔」交錯的命令列參數順序下,**最後那個 server 檔
    的測試會靜默丟失該 fixture**(收集期 closure 就少它;root conftest 的 autouse 不受
    影響)。這正是 `TestConftestWatchlistIsolation` 在三檔子集紅、單跑與全套綠的根因。

    不頂層 import `copycat.server.app`(同 `_neutralize_finmind_env` 的理由:不讓
    [live] extras 變成整套測試的硬依賴)—— 收集階段會 import 所有被選測試模組,
    任何會呼叫 `create_app` 的 run 到 fixture 執行時模組必已在 `sys.modules`;
    不在就代表這輪根本沒有人碰 server app,無隔離對象。
    """
    app_mod = sys.modules.get("copycat.server.app")
    if app_mod is None:
        return
    monkeypatch.setattr(app_mod, "WATCHLIST_DEFAULT_PATH", tmp_path / "stock_watchlist.json")


@pytest.fixture(autouse=True)
def _neutralize_finmind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAPITAL_* / DISCORD_* 同型隔離(review LF-4)。

    開發機 shell 或 repo root .env 的真 FINMIND_TOKEN 一旦流進測試,任何漏 patch
    `oi_levels.urlopen` 的路徑就會**真的**打 FinMind —— 燒配額,而且測試結果從此
    隨上游資料變動(失效樣態是偶發紅,最難查的那一種)。
    需要 token 的測試自行 `monkeypatch.setenv`(或直接把 token 當引數傳)。

    patch 目標是 `finmind_token`(token 解析的唯一一份;stdlib-only 故可頂層 import,
    不會把 fastapi 拉進每一條測試)—— 消費端(oi_levels / breadth)不必逐一中和。
    """
    monkeypatch.delenv(FINMIND_ENV_KEY, raising=False)
    monkeypatch.setattr(_finmind_token, "_dotenv_values", lambda: {})
    monkeypatch.setattr(_finmind_token, "_dotenv_cache", None)
