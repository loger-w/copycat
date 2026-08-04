"""neutralize_external_env:verify 模式的外部 IO 壓制合約。

守的形狀:CAPITAL_USER_ID / DISCORD_BOT_TOKEN / DISCORD_WEBHOOK_URL 不論來自 shell env
還是 repo root .env,壓制後都不得讓 get_capital 組出真 client、不得讓 discord `_getenv`
解出 token、不得讓 notify 解出 webhook URL。歷史事故:驗證腳本以真憑證打了一次群益登入
(next-time 2026-08-04)。

restore point 刻意灌**會走到底的真值**(CAPITAL_ENV=prod + 合法 USER_ID,而不是單一
sentinel 字串)—— sentinel 會在 factory 的 `_VALID_ENVS` 閘先被擋下,測試就分不出
「壓制生效」與「值本來就不合法」(review T-2 的 vacuous 形狀);dotenv 也同理先推回
「會回真值」的實作再斷言 neutralize 清空(review T-1)。

neutralize 本身是程序生命週期語意(不還原);測試先用 monkeypatch 對同一批 key /
attr 登記還原點,teardown 由 monkeypatch 收拾 —— 不得讓空字串 leak 到其他測試。
"""

from __future__ import annotations

import os

import pytest

import copycat.capital.factory as factory
import copycat.notify as notify
import copycat.server.discord_bot as discord_bot
from copycat.server.verify import (
    CAPITAL_ENV_KEYS,
    DISCORD_ENV_KEYS,
    DOTENV_MODULES,
    neutralize_external_env,
)

ALL_KEYS = (*CAPITAL_ENV_KEYS, *DISCORD_ENV_KEYS)

#: 值域受限的 key 給合法值 —— 壓制若失效,get_capital 要真的能組出 client(才測得到)
_REALISTIC = {
    "CAPITAL_ENV": "prod",
    "CAPITAL_USER_ID": "A123456789",
    "CAPITAL_ORDER_ENABLED": "true",
    "DISCORD_WEBHOOK_URL": "https://discord.example/webhook",
}


@pytest.fixture
def _restore_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """先把 neutralize 會動到的每個 key / attr 都用 monkeypatch 摸一次(登記還原點),
    並灌入「壓制失效時會真的走到底」的值 —— neutralize 是直接賦值,monkeypatch 不會
    自動追蹤它。模組清單吃 verify.DOTENV_MODULES 同一份(review T-4)。"""
    for key in ALL_KEYS:
        monkeypatch.setenv(key, _REALISTIC.get(key, "sentinel-before-neutralize"))
    for mod in DOTENV_MODULES:
        # 推回「會回真值」的實作:conftest autouse 已把它們設成 lambda: {},維持那個
        # 狀態的話「neutralize 有沒有做事」根本分不出來(review T-1 vacuous)
        monkeypatch.setattr(mod, "_dotenv_values", lambda: {"CAPITAL_USER_ID": "from-dotenv"})
        monkeypatch.setattr(mod, "_dotenv_cache", {"CAPITAL_USER_ID": "from-dotenv"})
    monkeypatch.setattr(factory, "_client", object())
    monkeypatch.setattr(notify, "_WEBHOOK_URL", "https://discord.example/stale-cache")
    monkeypatch.setattr(notify, "_URL_RESOLVED", False)


def test_all_keys_forced_to_empty_string(_restore_point: None) -> None:
    neutralize_external_env()
    for key in ALL_KEYS:
        # 空字串(不是 delenv):factory / discord_bot 的 _getenv 都是「in os.environ
        # 即用」的新語意,空字串 = 明確清空、同時壓制 .env;delenv 反而讓 .env 值復活
        assert os.environ[key] == "", key


def test_get_capital_none_even_with_real_creds(_restore_point: None) -> None:
    """shell env 帶著真憑證(含 CAPITAL_ENV=prod)起 verify server(歷史事故的形狀)
    → 壓制後功能必須未啟用。壓制 mutation 成 no-op 時本測試必須紅(env 值會組出
    prod client)。"""
    neutralize_external_env()
    assert factory.get_capital() is None


def test_dotenv_fallback_also_neutralized(_restore_point: None) -> None:
    """雙保險第二層:未來若有 key 走回「僅未設才 fallback」舊語意,.env 也讀不到值。
    restore point 已把兩模組推回會回真值的實作,這裡斷言 neutralize 真的清掉。"""
    for mod in DOTENV_MODULES:
        assert getattr(mod, "_dotenv_values")() != {}  # 前置:確實是會回真值的狀態
    neutralize_external_env()
    for mod in DOTENV_MODULES:
        assert getattr(mod, "_dotenv_values")() == {}
        assert getattr(mod, "_dotenv_cache") is None
    assert factory._client is None


def test_discord_token_unresolvable(_restore_point: None) -> None:
    neutralize_external_env()
    assert discord_bot._getenv(discord_bot.TOKEN_ENV) == ""
    assert discord_bot._getenv(discord_bot.CHANNEL_ENV) == ""


def test_notify_webhook_unresolvable(_restore_point: None) -> None:
    """notify.py 是第三條 Discord 出口且是舊語意(值空白也 fallback .env)——
    靠 cache 釘成「已解析且為 None」壓制(review R-6)。"""
    neutralize_external_env()
    assert notify.resolve_webhook_url() is None
