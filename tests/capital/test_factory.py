"""get_capital() 工廠:env 分支 + 單例 + prod banner(SC-9/10)。

只建構不 start:SkcomCapitalCom 建構子是惰性的(setup() 才載 DLL),
CI 無 COM 環境也要能走完全部分支。單例重置慣例:
monkeypatch.setattr(factory_mod, "_client", None)。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import copycat.capital.factory as factory_mod
from copycat.capital.com import SkcomCapitalCom
from copycat.capital.factory import get_capital

_ENV_KEYS = (
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
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(factory_mod, "_client", None)


def _set_minimal(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    monkeypatch.setenv("CAPITAL_USER_ID", "A123456789")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


# ---------------------------------------------------------------------------
# 未啟用 / env 分支
# ---------------------------------------------------------------------------


def test_user_id_unset_returns_none() -> None:
    assert get_capital() is None


def test_unknown_env_returns_none_and_logs_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_minimal(monkeypatch, CAPITAL_ENV="production")  # 拼錯不可默認正式
    with caplog.at_level(logging.ERROR, logger="copycat.capital.factory"):
        assert get_capital() is None
    assert any(
        r.levelno == logging.ERROR and "CAPITAL_ENV" in r.getMessage() for r in caplog.records
    )


def test_defaults_env_test_and_order_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch)
    client = get_capital()
    assert client is not None
    assert client._env == "test"
    assert client._safety.order_enabled is False


def test_order_enabled_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, CAPITAL_ORDER_ENABLED="true")
    client = get_capital()
    assert client is not None
    assert client._safety.order_enabled is True


# ---------------------------------------------------------------------------
# 上限:未設/空/0/解析失敗 → None = 不限(user 拍板,與 treading-king fail-closed 相反)
# ---------------------------------------------------------------------------


def test_max_unset_means_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch)
    client = get_capital()
    assert client is not None
    assert client._safety.max_qty is None
    assert client._safety.max_amount is None


def test_max_empty_or_zero_means_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, CAPITAL_MAX_QTY=" ", CAPITAL_MAX_AMOUNT="0")
    client = get_capital()
    assert client is not None
    assert client._safety.max_qty is None
    assert client._safety.max_amount is None


def test_max_parse_failure_unlimited_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_minimal(monkeypatch, CAPITAL_MAX_QTY="abc")
    with caplog.at_level(logging.WARNING, logger="copycat.capital.factory"):
        client = get_capital()
    assert client is not None
    assert client._safety.max_qty is None
    assert any(
        r.levelno == logging.WARNING and "CAPITAL_MAX_QTY" in r.getMessage() for r in caplog.records
    )


def test_max_values_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, CAPITAL_MAX_QTY="5", CAPITAL_MAX_AMOUNT="1000000.5")
    client = get_capital()
    assert client is not None
    assert client._safety.max_qty == 5
    assert client._safety.max_amount == 1000000.5


# ---------------------------------------------------------------------------
# prod banner(SC-10)
# ---------------------------------------------------------------------------


def test_prod_banner_masks_full_account_last4(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_minimal(monkeypatch, CAPITAL_ENV="prod", CAPITAL_FULL_ACCOUNT="1234567890A")
    with caplog.at_level(logging.WARNING, logger="copycat.capital.factory"):
        client = get_capital()
    assert client is not None
    banners = [r.getMessage() for r in caplog.records if "群益正式環境" in r.getMessage()]
    assert banners and "****890A" in banners[0]
    assert "1234567" not in banners[0]  # 帳號本體不得入 log


def test_prod_banner_falls_back_to_user_id_last4(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_minimal(monkeypatch, CAPITAL_ENV="prod")
    with caplog.at_level(logging.WARNING, logger="copycat.capital.factory"):
        client = get_capital()
    assert client is not None
    banners = [r.getMessage() for r in caplog.records if "群益正式環境" in r.getMessage()]
    assert banners and "****6789" in banners[0]


def test_test_env_no_banner(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_minimal(monkeypatch, CAPITAL_ENV="test")
    with caplog.at_level(logging.WARNING, logger="copycat.capital.factory"):
        assert get_capital() is not None
    assert not any("群益正式環境" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 組裝細節 + 單例
# ---------------------------------------------------------------------------


def test_com_is_skcom_with_dll_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, CAPITAL_DLL_DIR=r"C:\skcom")
    client = get_capital()
    assert client is not None
    assert isinstance(client._com, SkcomCapitalCom)
    assert client._com._dll_dir == r"C:\skcom"


def test_audit_base_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, TXO_AUDIT_DIR="txo-audit", CAPITAL_AUDIT_DIR="cap-audit")
    client = get_capital()
    assert client is not None
    assert client._audit_base == Path("cap-audit")


def test_audit_base_falls_back_to_txo_then_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch, TXO_AUDIT_DIR="txo-audit")
    client = get_capital()
    assert client is not None
    assert client._audit_base == Path("txo-audit")
    monkeypatch.setattr(factory_mod, "_client", None)
    monkeypatch.delenv("TXO_AUDIT_DIR")
    client2 = get_capital()
    assert client2 is not None
    assert client2._audit_base == Path("data/audit")


def test_singleton_second_call_same_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal(monkeypatch)
    first = get_capital()
    assert first is not None
    assert get_capital() is first


class TestDotenvFallback:
    """Phase 6 real-env finding:server 不載 dotenv 檔,factory 需逐 key「環境變數 →
    repo root dotenv 檔」fallback(對齊 cli._resolve_finmind_token / notify 慣例)。"""

    def test_reads_capital_keys_from_repo_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / ".env").write_text(
            "CAPITAL_USER_ID=A123456789\nCAPITAL_ENV=test\nCAPITAL_PASSWORD=pw\n"
            "CAPITAL_FULL_ACCOUNT=9800123\n# comment\nCAPITAL_MAX_QTY=\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        client = get_capital()
        assert client is not None
        assert client._user_id == "A123456789"
        assert client._full_account == "9800123"

    def test_os_environ_wins_over_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / ".env").write_text(
            "CAPITAL_USER_ID=FILEUSER99\nCAPITAL_ENV=prod\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CAPITAL_USER_ID", "ENVUSER123")
        monkeypatch.setenv("CAPITAL_ENV", "test")
        client = get_capital()
        assert client is not None
        assert client._user_id == "ENVUSER123"
        assert client._env == "test"
