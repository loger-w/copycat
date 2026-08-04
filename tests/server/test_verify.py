"""neutralize_external_env:verify 模式的外部 IO 壓制合約。

守的形狀:CAPITAL_USER_ID / DISCORD_BOT_TOKEN 不論來自 shell env 還是 repo root .env,
壓制後都不得讓 get_capital 組出真 client、不得讓 discord `_getenv` 解出 token。
歷史事故:驗證腳本以真憑證打了一次群益登入(next-time 2026-08-04)。

neutralize 本身是程序生命週期語意(不還原);測試先用 monkeypatch 對同一批 key /
attr 登記還原點,teardown 由 monkeypatch 收拾 —— 不得讓空字串 leak 到其他測試。
"""

from __future__ import annotations

import os

import pytest

import copycat.capital.factory as factory
import copycat.server.discord_bot as discord_bot
from copycat.server.verify import (
    CAPITAL_ENV_KEYS,
    DISCORD_ENV_KEYS,
    neutralize_external_env,
)

ALL_KEYS = (*CAPITAL_ENV_KEYS, *DISCORD_ENV_KEYS)


@pytest.fixture
def _restore_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """先把 neutralize 會動到的每個 key / attr 都用 monkeypatch 摸一次(no-op set),
    讓 teardown 有還原點 —— neutralize 是直接賦值,monkeypatch 不會自動追蹤它。"""
    for key in ALL_KEYS:
        monkeypatch.setenv(key, "sentinel-before-neutralize")
    for mod in (factory, discord_bot):
        monkeypatch.setattr(mod, "_dotenv_values", getattr(mod, "_dotenv_values"))
        monkeypatch.setattr(mod, "_dotenv_cache", getattr(mod, "_dotenv_cache"))
    monkeypatch.setattr(factory, "_client", factory._client)


def test_all_keys_forced_to_empty_string(_restore_point: None) -> None:
    neutralize_external_env()
    for key in ALL_KEYS:
        # 空字串(不是 delenv):兩個模組的 _getenv 都是「in os.environ 即用」的新語意,
        # 空字串 = 明確清空、同時壓制 .env fallback;delenv 反而會讓 .env 值復活
        assert os.environ[key] == "", key


def test_get_capital_none_even_with_real_creds(_restore_point: None) -> None:
    """shell env 帶著真憑證起 verify server(歷史事故的形狀)→ 壓制後功能必須未啟用。"""
    neutralize_external_env()
    assert factory.get_capital() is None


def test_dotenv_fallback_also_neutralized(_restore_point: None) -> None:
    """雙保險第二層:未來若有 key 走回「僅未設才 fallback」舊語意,.env 也讀不到值。"""
    neutralize_external_env()
    assert factory._dotenv_values() == {}
    assert discord_bot._dotenv_values() == {}
    assert factory._dotenv_cache is None
    assert discord_bot._dotenv_cache is None


def test_discord_token_unresolvable(_restore_point: None) -> None:
    neutralize_external_env()
    assert discord_bot._getenv(discord_bot.TOKEN_ENV) == ""
    assert discord_bot._getenv(discord_bot.CHANNEL_ENV) == ""
