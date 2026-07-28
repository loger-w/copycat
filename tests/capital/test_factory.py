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
from tests.conftest import CAPITAL_ENV_KEYS

# 收集期捕捉真 dotenv 解析函式 — conftest autouse 會把它換成 lambda: {}
# (monkeypatch 只在測試執行期生效,收集期模組屬性仍是真貨;
# 經 `import tests.conftest` 拿函式會踩雙重 import,捕到已 patch 的假貨 —
# import 常數 CAPITAL_ENV_KEYS 無此問題,tuple 值相等即可)
_REAL_DOTENV_VALUES = factory_mod._dotenv_values


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest 全域 autouse 已做同樣隔離;此處保留 = 本檔不依賴 conftest 存在的防禦
    for key in CAPITAL_ENV_KEYS:
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
        # 註解行放在真值行之後:過濾若失效,prod/true 會覆蓋掉真值 → 斷言抓得到(T1)
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        (tmp_path / ".env").write_text(
            "CAPITAL_USER_ID=A123456789\nCAPITAL_ENV=test\nCAPITAL_PASSWORD=pw\n"
            "CAPITAL_FULL_ACCOUNT=9800123\n# comment\nCAPITAL_MAX_QTY=\n"
            "# CAPITAL_ENV=prod\n  # CAPITAL_ORDER_ENABLED=true\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        client = get_capital()
        assert client is not None
        assert client._user_id == "A123456789"
        assert client._full_account == "9800123"
        assert client._password == "pw"  # T9
        assert client._safety.max_qty is None  # T9:空值 = 不限
        assert client._env == "test"  # T1:註解行不得覆蓋
        assert client._safety.order_enabled is False  # T1:前導空白註解行不得生效

    def test_bom_first_key_read(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # T2/I4:Windows 編輯器常存 UTF-8 BOM,.env 首 key 不得靜默失效
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        (tmp_path / ".env").write_text("CAPITAL_USER_ID=A123456789\n", encoding="utf-8-sig")
        monkeypatch.chdir(tmp_path)
        client = get_capital()
        assert client is not None
        assert client._user_id == "A123456789"

    def test_undecodable_env_file_warns_and_treated_as_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # I4:cp950 等壞編碼檔不得炸 get_capital — never-raise,警告後視同無 .env
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        (tmp_path / ".env").write_bytes("CAPITAL_USER_ID=許功蓋\n".encode("cp950"))
        monkeypatch.chdir(tmp_path)
        with caplog.at_level(logging.WARNING, logger="copycat.capital.factory"):
            client = get_capital()
        assert client is None
        assert any(
            r.levelno == logging.WARNING and ".env" in r.getMessage() for r in caplog.records
        )

    def test_value_containing_equals_kept_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # T3:partition 只切第一個 =,密碼含 = 不得截斷
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        (tmp_path / ".env").write_text(
            "CAPITAL_USER_ID=A123456789\nCAPITAL_PASSWORD=a=b==\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        client = get_capital()
        assert client is not None
        assert client._password == "a=b=="

    def test_dotenv_reread_on_each_assembly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # T4:每次組裝重讀 .env — 首次無檔回 None 後補檔,重置單例即讀得到
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        monkeypatch.chdir(tmp_path)
        assert get_capital() is None
        (tmp_path / ".env").write_text("CAPITAL_USER_ID=A123456789\n", encoding="utf-8")
        monkeypatch.setattr(factory_mod, "_client", None)
        client = get_capital()
        assert client is not None
        assert client._user_id == "A123456789"

    def test_empty_env_var_suppresses_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # I5:`set KEY=` 清空 = 明確未設,.env 不得復活下單開關(安全方向)
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
        (tmp_path / ".env").write_text(
            "CAPITAL_USER_ID=A123456789\nCAPITAL_ORDER_ENABLED=true\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CAPITAL_ORDER_ENABLED", "")
        client = get_capital()
        assert client is not None
        assert client._safety.order_enabled is False

    def test_os_environ_wins_over_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(factory_mod, "_dotenv_values", _REAL_DOTENV_VALUES)
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
