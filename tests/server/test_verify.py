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

import datetime as _dt
import os

import pytest

import copycat.capital.factory as factory
import copycat.notify as notify
import copycat.server.breadth_engine as be
import copycat.server.discord_bot as discord_bot
import copycat.server.verify as verify
from copycat.limit_streaks import compute_day_limitups, compute_prev_streaks
from copycat.market_breadth import (
    assemble_universe,
    build_name_map,
    build_type_map,
    compute_breadth,
    dedup_sector_map,
    max_tick_datetime,
    parse_active_disposition,
)
from copycat.sector_rotation import compute_sector_rotation, rows_to_chain_map
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.verify import (
    CAPITAL_ENV_KEYS,
    DISCORD_ENV_KEYS,
    DOTENV_MODULES,
    FAIL_ENV_KEY,
    FLIP_ENV_KEY,
    fake_breadth_fetchers,
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


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-08-06 10:23:45", "2026-08-06 10:23:45"),  # 域內:原樣
        ("2026-08-06 09:01:00", "2026-08-06 09:01:00"),  # 下界含等值
        ("2026-08-06 13:30:00", "2026-08-06 13:30:00"),  # 上界含等值
        ("2026-08-06 16:40:00", "2026-08-06 13:11:00"),  # 盤後 → clamp(40 % 29 = 11)
        ("2026-08-06 08:30:00", "2026-08-06 13:01:00"),  # 盤前 → clamp(30 % 29 = 1)
    ],
)
def test_snapshot_stamp_clamped_into_minute_domain(now: str, expected: str) -> None:
    """fake 快照時刻在分鐘域(0901–1330)外時 clamp 進 13 時帶(review SPEC-4)。

    直接用 `datetime.now()` 的話,盤後跑 verify server 的每一輪都落在域外 → 序列恆空,
    而那與「序列接線壞掉」在畫面上完全同形 —— verify 的存在理由正是目視這條路。
    """
    assert verify._snapshot_stamp(_dt.datetime.fromisoformat(now)) == expected


def test_clamped_stamp_minute_follows_wall_clock() -> None:
    """clamp 後的**分鐘隨牆鐘變**,不得恆定(review S-1)。

    廣度事件 id 含 `time` 欄(= 快照時刻):時刻恆定 → 翻轉之後每一則的 id 完全相同
    → 前端去重把後續全吃掉,SC-7 的時間軸永遠只看得到第一則;當日序列同樣只長得出
    一格,而那與「序列接線壞掉」同形。
    """
    stamps = [verify._snapshot_stamp(_dt.datetime(2026, 8, 6, 20, m)) for m in (5, 15, 27)]

    assert len(set(stamps)) == 3
    for s in stamps:
        moment = _dt.datetime.fromisoformat(s)
        assert moment.date() == _dt.date(2026, 8, 6)  # 日期仍是當天(append 的前提)
        assert _dt.time(9, 1) <= moment.time() <= _dt.time(13, 30)  # 域內,否則不入序列


def test_fake_breadth_fetchers_feed_the_real_pipeline() -> None:
    """fake 四元組的前三支餵進真管線的**語意**斷言(review TC-6)。

    這幾支是 verify server 上目視的唯一資料源:形狀對但值域無意義(例如漲跌停那兩檔
    沒真的落在停板價、或 ETF 沒被剔除)時,畫面照樣有數字,而「接線壞掉」與「fake 資料
    本身沒覆蓋到那條路」在畫面上同形。手算:1101 前收 10.0 → 漲停 11.0;6488 前收
    10.0 → 跌停 9.0;2330(前收 995)只是上漲;2317 平盤;2454 下跌;0050 = ETF 剔除。
    """
    snapshot, stock_info, disposition, _daily, _chain = fake_breadth_fetchers()
    today = _dt.date.today()
    info_rows = stock_info("tok")
    snapshot_rows = snapshot("tok")

    watch_list = parse_active_disposition(disposition("tok", today), today)
    universe = assemble_universe(snapshot_rows, dedup_sector_map(info_rows), watch_list)
    out = compute_breadth(universe, build_type_map(info_rows), build_name_map(info_rows))

    assert out is not None
    assert out["twse"] == {"limit_up": 1, "up": 1, "flat": 1, "down": 1, "limit_down": 0}
    assert out["tpex"] == {"limit_up": 0, "up": 1, "flat": 0, "down": 0, "limit_down": 1}
    assert "0050" not in {r["stock_id"] for r in out["rows"]}

    by_id = {r["stock_id"]: r for r in out["rows"]}
    # 「觸及未鎖」是 R3 列表的第三種狀態,verify 畫面要看得到它才驗得了那條路:
    # 3105 前收 79.0 → 漲停 86.9,high 摸到但收 80.0(未鎖)
    assert by_id["3105"]["touched_limit_up"] is True
    assert by_id["3105"]["limit_up"] is False
    # 已鎖的那檔 high 同樣等於漲停價,但**不得**重複算進「觸及未鎖」桶
    assert by_id["1101"]["limit_up"] is True
    assert by_id["1101"]["touched_limit_up"] is False


def test_fake_daily_prices_feed_the_streak_pipeline() -> None:
    """第四支(EOD 日線)fake 的**語意**斷言:指定股兩日皆收漲停 → streak == 2。

    形狀對但值沒真的落在停板價時,verify server 的連板欄會恆空,而那與「連板管線
    壞掉」在畫面上同形。手算:1101 close 11.0 / spread 1.0 → 前收 10.0 → 漲停 11.0。

    列數門檻同樣是語意的一部分:低於 `_DAILY_MIN_ROWS` 會被引擎當成「回應被截斷」
    → 整輪失敗 → 連板欄整天 null(design R4/R16),fake 不夠長就等於這條路沒接上。
    """
    _snapshot, _info, _disposition, daily, _chain = fake_breadth_fetchers()
    today = _dt.date.today()
    day1 = daily("tok", today - _dt.timedelta(days=1))
    day2 = daily("tok", today - _dt.timedelta(days=2))

    assert len(day1) >= be._DAILY_MIN_ROWS
    streaks = compute_prev_streaks([compute_day_limitups(day1), compute_day_limitups(day2)])
    assert streaks.get("1101") == 2
    assert streaks.get("2330") is None  # 未漲停的那檔不得混進來


def test_fake_snapshot_stamp_is_today_and_inside_minute_domain() -> None:
    """快照時刻恆為**今天**且落在分鐘域內 —— 兩者都是「序列會長格」的前提(SPEC-4)。"""
    snapshot, *_ = fake_breadth_fetchers()
    rows = snapshot("tok")

    stamp = max_tick_datetime(rows)
    assert stamp is not None
    assert stamp.date() == _dt.date.today()
    assert _dt.time(9, 1) <= stamp.time() <= _dt.time(13, 30)
    assert len({r["date"] for r in rows}) == 1  # 同一輪同一個時刻


def test_verify_breadth_fail_injects_all_five(monkeypatch: pytest.MonkeyPatch) -> None:
    """`VERIFY_BREADTH_FAIL=1` → 五支全拋(SC-3/SC-6 在真 server 上的失效注入通道)。

    第四支(EOD 日線)/ 第五支(產業鏈)漏接注入的話,FinMind 「整段掛掉」的注入其實
    漏了一條路 —— 連板 / chain 背景 task 照樣打得通,失效隔離就沒真的被驗到。
    """
    monkeypatch.setenv(FAIL_ENV_KEY, "1")
    snapshot, stock_info, disposition, daily, chain = fake_breadth_fetchers()

    for call in (
        lambda: snapshot("tok"),
        lambda: stock_info("tok"),
        lambda: disposition("tok", _dt.date.today()),
        lambda: daily("tok", _dt.date.today()),
        lambda: chain("tok"),
    ):
        with pytest.raises(BreadthFetchError):
            call()


def test_fake_chain_feeds_the_rotation_pipeline() -> None:
    """第五支(產業鏈)fake 的**語意**斷言:chain 表必須涵蓋 fake 快照的股票。

    形狀對但代號對不上 universe 時,`compute_sector_rotation` 每個群組都是 0 成員 →
    industries 空陣列,而那與「rotation 接線壞掉」在 verify 畫面上完全同形。
    """
    snapshot, stock_info, disposition, _daily, chain = fake_breadth_fetchers()
    today = _dt.date.today()
    info_rows = stock_info("tok")
    watch_list = parse_active_disposition(disposition("tok", today), today)
    universe = assemble_universe(snapshot("tok"), dedup_sector_map(info_rows), watch_list)

    chain_map = rows_to_chain_map(chain("tok"))
    assert chain_map, "chain fake 不得 parse 成空表"
    rotation = compute_sector_rotation(universe, chain_map)

    assert rotation is not None
    industries = rotation["industries"]
    assert industries, "chain 表與 fake 快照對不上 → 每個產業 0 成員"
    # 至少一個產業要有多於一檔成員(sub 展開那條路在畫面上才走得到)
    assert any(len(i["subs"]) >= 2 for i in industries)
    covered = {sid for subs in chain_map.values() for ids in subs.values() for sid in ids}
    assert {"1101", "2330", "3105"} <= covered


class TestBreadthFlip:
    """`VERIFY_BREADTH_FLIP=1`:1101 依**牆鐘**分鐘在「鎖漲停 ↔ 非鎖」兩態切換(SC-7 取證)。

    翻轉週期取 `minute // 11` 的奇偶(> 事件冷卻 600s,每次翻轉必發一則事件);判別子
    刻意是**牆鐘**而不是 `_snapshot_stamp` clamp 後的快照時刻 —— 後者在盤後恆為 13:00,
    分鐘永遠不動,verify server 上一則事件都不會出現。
    """

    @staticmethod
    def _rows(now: _dt.datetime, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
        """指定牆鐘下的 fake 快照(整份 —— 翻轉不得改到 1101 以外的列)。"""
        monkeypatch.setattr(verify, "_now", lambda: now)
        snapshot, *_ = fake_breadth_fetchers()
        return snapshot("tok")

    @staticmethod
    def _limit_up_1101(rows: list[dict]) -> bool:
        """快照 → 真管線 → 1101 的 `limit_up`(事件 diff 讀的就是這個旗標)。"""
        _snapshot, stock_info, disposition, *_ = fake_breadth_fetchers()
        today = _dt.date.today()
        info_rows = stock_info("tok")
        watch_list = parse_active_disposition(disposition("tok", today), today)
        universe = assemble_universe(rows, dedup_sector_map(info_rows), watch_list)
        out = compute_breadth(universe, build_type_map(info_rows), build_name_map(info_rows))
        assert out is not None
        row = next(r for r in out["rows"] if r["stock_id"] == "1101")
        assert row["limit_judged"] is True  # 缺欄輪會被 diff 整列跳過 → 一則事件都不發
        return row["limit_up"]

    def test_flip_off_keeps_1101_locked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未設 FLIP → 兩個相鄰週期都是既有的「已鎖」狀態(既有行為不得改變)。"""
        monkeypatch.delenv(FLIP_ENV_KEY, raising=False)
        for minute in (5, 15):
            rows = self._rows(_dt.datetime(2026, 8, 6, 10, minute), monkeypatch)
            assert self._limit_up_1101(rows) is True

    def test_flip_toggles_by_wall_clock_minute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(FLIP_ENV_KEY, "1")
        locked = self._rows(_dt.datetime(2026, 8, 6, 10, 5), monkeypatch)  # 5 // 11 = 0(偶)
        opened = self._rows(_dt.datetime(2026, 8, 6, 10, 15), monkeypatch)  # 15 // 11 = 1(奇)

        assert self._limit_up_1101(locked) is True
        assert self._limit_up_1101(opened) is False
        # 其餘列的**價量**不得被翻轉波及(否則家數帶會跟著跳,兩件事在畫面上混在一起);
        # `date` 本來就跟著牆鐘走,不在比對範圍
        def _quotes(rows: list[dict]) -> list[dict]:
            others = [r for r in rows if r["stock_id"] != "1101"]
            return [{k: v for k, v in r.items() if k != "date"} for r in others]

        assert _quotes(locked) == _quotes(opened)

    def test_flip_ignores_clamped_snapshot_minute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """盤後兩個**快照時刻相同**的牆鐘仍必須翻轉。

        牆鐘 20:04 與 20:33 clamp 後同為 13:04(分鐘 % 29 相同),但翻轉週期
        (`minute // 11` 奇偶)不同 —— 判別子若寫成快照時刻的分鐘,這裡兩次會拿到
        同一態,而 verify server 幾乎都在盤後跑,那等於整條 SC-7 取證路徑靜默失效。
        """
        monkeypatch.setenv(FLIP_ENV_KEY, "1")
        a = self._rows(_dt.datetime(2026, 8, 6, 20, 4), monkeypatch)  # 4 // 11 = 0(偶)
        b = self._rows(_dt.datetime(2026, 8, 6, 20, 33), monkeypatch)  # 33 // 11 = 3(奇)

        assert a[0]["date"] == b[0]["date"] == "2026-08-06 13:04:00"
        assert self._limit_up_1101(a) != self._limit_up_1101(b)


def test_notify_webhook_unresolvable(_restore_point: None) -> None:
    """notify.py 是第三條 Discord 出口且是舊語意(值空白也 fallback .env)——
    靠 cache 釘成「已解析且為 None」壓制(review R-6)。"""
    neutralize_external_env()
    assert notify.resolve_webhook_url() is None
