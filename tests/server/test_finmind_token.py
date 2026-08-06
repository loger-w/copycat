"""FinMind token 解析(`copycat/server/finmind_token.py`)。

自 `test_oi_levels.py` 隨 🔵 抽出而遷來(market-overview R2 Task 1),案例未改。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import copycat.server.finmind_token as finmind_token

#: 真實作的 restore point。**module import 期取**:conftest 的 autouse fixture 會在
#: 每條測試前把它換成 `lambda: {}`(FinMind 憑證中和),那之後就抓不到本尊了。
_REAL_DOTENV_VALUES = finmind_token._dotenv_values


@pytest.fixture(autouse=True)
def _fresh_dotenv_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_dotenv_cache` 是**解析一次就黏住**的 module 級狀態(review TC-5):conftest 已
    設 None,這裡再顯式一次讓本檔的 .env 案例彼此不互相汙染(前一條測到的檔案內容會
    直接變成後一條的答案)。"""
    monkeypatch.setattr(finmind_token, "_dotenv_cache", None)


class TestResolveToken:
    """token 解析三條語意(review TC-5)。server 不載 dotenv:
    `FINMIND_TOKEN in os.environ` 即用(含空字串 = 未設,可壓制 .env)→ 否則 repo root .env。

    conftest 的 autouse fixture 已把 `_dotenv_values` 中和成 `lambda: {}`,要驗 .env
    行為的案例自行推回真實作(同 tests/capital/test_factory.py 的 `_REAL_DOTENV_VALUES`)。
    """

    def test_env_value_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FINMIND_TOKEN", "  tok-env  ")
        assert finmind_token.resolve_token() == "tok-env"  # 兩端空白剝掉

    def test_empty_env_suppresses_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`set FINMIND_TOKEN=` 是明確的「這台不要打 FinMind」,不得被檔案值復活。"""
        monkeypatch.setattr(finmind_token, "_dotenv_values", _REAL_DOTENV_VALUES)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("FINMIND_TOKEN=tok-file\n", encoding="utf-8")
        monkeypatch.setenv("FINMIND_TOKEN", "")
        assert finmind_token.resolve_token() is None

    def test_dotenv_fallback_reads_bom_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """utf-8-sig:Windows 存的 .env 帶 BOM 會讓**首 key** 靜默失效(CLAUDE.md §8
        真踩過)→ 治具刻意把 FINMIND_TOKEN 放第一行。"""
        monkeypatch.setattr(finmind_token, "_dotenv_values", _REAL_DOTENV_VALUES)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("FINMIND_TOKEN=tok-file\nOTHER=x\n", encoding="utf-8-sig")
        monkeypatch.delenv("FINMIND_TOKEN", raising=False)
        assert finmind_token.resolve_token() == "tok-file"
