from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any

import pytest

from copycat.signal_rules import (
    CDP_LEVELS,
    COOLDOWN_MAX,
    COOLDOWN_MIN,
    INT_PARAM_KEYS,
    MAX_RULES,
    PARAM_SPECS,
    RULE_KINDS,
    Rule,
    RuleError,
    default_rules,
    load_rules,
    new_rule_id,
    normalize_rule,
    rule_config,
    save_rules,
)
from copycat.signals_config import SignalsConfig

VALID_PARAMS: dict[str, dict[str, float]] = {
    "cdp_cross": {"rearm_ticks": 5, "rearm_dwell_secs": 300},
    "surge_crash": {"pct": 2.0, "window_secs": 300},
    "surge_pullback": {"surge_pct": 2.0, "window_secs": 300, "pct": 1.0},
    "vol_burst": {
        "ratio": 3,
        "window_secs": 300,
        "min_elapsed_min": 15,
        "min_window_lots": 100,
        "min_day_lots": 500,
    },
    "limit_lock": {},
    "sweep_cluster": {
        "cluster_window_secs": 30,
        "min_sweeps": 2,
        "min_levels": 2,
        "up_pct": 0.3,
        "up_window_secs": 60,
    },
}


def make(kind: str = "cdp_cross", **over: Any) -> Any:
    """合法規則樣板;over 覆寫任一欄(含刻意的非法值)。"""
    rule: dict[str, Any] = {
        "id": "r-1-000",
        "name": f"規則-{kind}",
        "kind": kind,
        "enabled": True,
        "notify_discord": True,
        "cooldown_secs": 600,
        "params": dict(VALID_PARAMS[kind]),
        "cdp_levels": list(CDP_LEVELS) if kind == "cdp_cross" else [],
    }
    rule.update(over)
    return rule


class TestConstants:
    def test_kinds_and_levels(self) -> None:
        assert RULE_KINDS == (
            "cdp_cross",
            "surge_crash",
            "surge_pullback",
            "vol_burst",
            "limit_lock",
            "sweep_cluster",
        )
        assert CDP_LEVELS == ("ah", "nh", "cdp", "nl", "al")
        assert (COOLDOWN_MIN, COOLDOWN_MAX) == (60, 86_400)
        assert MAX_RULES == 30

    def test_param_specs_cover_every_kind(self) -> None:
        assert set(PARAM_SPECS) == set(RULE_KINDS)
        assert PARAM_SPECS["limit_lock"] == {}

    def test_param_specs_literal(self) -> None:
        """字面鎖(review B5):鍵集與值域是**跨檔契約** —— 前端 `PARAM_FIELDS` 的鍵集
        必須逐字相同(多鍵 / 缺鍵同樣是 INVALID_RULE),Dialog 的 min/max 也照這張表。

        只驗「涵蓋每個 kind」的話,悄悄改掉某條線的上下界不會有任何測試變紅,而失效
        樣態是使用者填得進去的值被後端拒收(或反過來,拒收本來合法的值)。
        """
        assert PARAM_SPECS == {
            "cdp_cross": {"rearm_ticks": (0, 50), "rearm_dwell_secs": (0, 3600)},
            "surge_crash": {"pct": (0.1, 50), "window_secs": (10, 3600)},
            "surge_pullback": {
                "surge_pct": (0.1, 50),
                "window_secs": (10, 3600),
                "pct": (0.1, 50),
            },
            "vol_burst": {
                "ratio": (1, 100),
                "window_secs": (10, 3600),
                "min_elapsed_min": (0, 240),
                "min_window_lots": (0, 1e6),
                "min_day_lots": (0, 1e7),
            },
            "limit_lock": {},
            # spec #192:掃單簇五參數;min_sweeps / min_levels 是整數鍵(INT_PARAM_KEYS)
            "sweep_cluster": {
                "cluster_window_secs": (1, 600),
                "min_sweeps": (1, 20),
                "min_levels": (1, 10),
                "up_pct": (0, 10),
                "up_window_secs": (1, 600),
            },
        }

    def test_param_specs_parity_with_frontend(self) -> None:
        """跨語言 parity(N055):前端 Dialog 自 2026-08-25 起**也擋值域**(好讓使用者
        知道是哪一格、界在哪),於是同一張表存在兩份實作。兩份漂掉沒有任何錯誤訊號 ——
        前端寬於後端 → 使用者拿回泛用的 INVALID_RULE;前端窄於後端 → 合法值被擋掉,
        而畫面上的說明還寫著錯的界。

        共用 fixture 是唯一真相:本條與前端
        `frontend/src/lib/signal-param-parity.test.ts` 各自對它斷言,
        改壞任一邊只有那一邊紅。上面的 `test_param_specs_literal` 仍留著 —— 它鎖的是
        「後端這份表的字面值」,fixture 被改壞時兩條一起紅才看得出是誰動了誰。
        """
        raw = json.loads(
            (Path(__file__).parent / "fixtures" / "signal_param_specs.json").read_text("utf-8")
        )
        expected = {
            kind: {key: (lo, hi) for key, (lo, hi) in fields.items()}
            for kind, fields in raw["specs"].items()
        }
        assert PARAM_SPECS == expected
        # review A8(#101 parity 補完):整數鍵與冷卻界也是同一張契約 —— 前端沒擋整數時
        # 使用者填 2.9 只拿到泛用 INVALID_RULE;冷卻界前端硬抄一份會漂(60/86400)。
        assert INT_PARAM_KEYS == frozenset(raw["int_keys"])
        assert (COOLDOWN_MIN, COOLDOWN_MAX) == tuple(raw["cooldown"])
        # fixture 自身健檢:int_keys 必須是 specs 裡真的存在的鍵(打錯字會讓契約悄悄變空)
        all_keys = {key for fields in raw["specs"].values() for key in fields}
        assert set(raw["int_keys"]) <= all_keys


class TestNormalizeHappyPath:
    @pytest.mark.parametrize("kind", RULE_KINDS)
    def test_valid_rule_of_each_kind(self, kind: str) -> None:
        out = normalize_rule(make(kind), {})
        assert out["kind"] == kind
        assert set(out["params"]) == set(PARAM_SPECS[kind])
        assert all(isinstance(v, float) for v in out["params"].values())

    def test_name_stripped(self) -> None:
        assert normalize_rule(make(name="  盤中 CDP  "), {})["name"] == "盤中 CDP"

    def test_idempotent(self) -> None:
        once = normalize_rule(make("vol_burst"), {})
        assert normalize_rule(once, {}) == once

    def test_cooldown_bounds_inclusive(self) -> None:
        assert normalize_rule(make(cooldown_secs=COOLDOWN_MIN), {})["cooldown_secs"] == COOLDOWN_MIN
        assert normalize_rule(make(cooldown_secs=COOLDOWN_MAX), {})["cooldown_secs"] == COOLDOWN_MAX

    def test_integral_float_cooldown_coerced_to_int(self) -> None:
        out = normalize_rule(make(cooldown_secs=600.0), {})
        assert out["cooldown_secs"] == 600
        assert isinstance(out["cooldown_secs"], int)


class TestNormalizeParams:
    @pytest.mark.parametrize(
        ("kind", "key"),
        [(k, key) for k, spec in PARAM_SPECS.items() for key in spec],
    )
    def test_below_min_and_above_max_rejected(self, kind: str, key: str) -> None:
        lo, hi = PARAM_SPECS[kind][key]
        for bad in (lo - 1, hi + 1):
            params = dict(VALID_PARAMS[kind])
            params[key] = bad
            with pytest.raises(RuleError, match="INVALID_RULE"):
                normalize_rule(make(kind, params=params), {})

    @pytest.mark.parametrize(
        ("kind", "key"),
        [(k, key) for k, spec in PARAM_SPECS.items() for key in spec],
    )
    def test_bounds_inclusive(self, kind: str, key: str) -> None:
        lo, hi = PARAM_SPECS[kind][key]
        for good in (lo, hi):
            params = dict(VALID_PARAMS[kind])
            params[key] = good
            assert normalize_rule(make(kind, params=params), {})["params"][key] == float(good)

    @pytest.mark.parametrize(
        ("kind", "key"),
        [(k, key) for k, spec in PARAM_SPECS.items() for key in spec],
    )
    def test_missing_key_rejected(self, kind: str, key: str) -> None:
        params = dict(VALID_PARAMS[kind])
        del params[key]
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(kind, params=params), {})

    @pytest.mark.parametrize("kind", RULE_KINDS)
    def test_extra_key_rejected(self, kind: str) -> None:
        params = dict(VALID_PARAMS[kind])
        params["bogus"] = 1
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(kind, params=params), {})

    @pytest.mark.parametrize(
        ("kind", "key"),
        [(k, key) for k, spec in PARAM_SPECS.items() for key in spec],
    )
    def test_bool_value_rejected(self, kind: str, key: str) -> None:
        """bool 是 int 子類 —— 不排除的話 True 會被當 1 靜默通過."""
        params = dict(VALID_PARAMS[kind])
        params[key] = True  # type: ignore[assignment]
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(kind, params=params), {})

    def test_non_numeric_value_rejected(self) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("cdp_cross", params={"rearm_ticks": "5"}), {})

    def test_params_not_a_dict_rejected(self) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("limit_lock", params=[]), {})

    @pytest.mark.parametrize(
        ("kind", "key"),
        [
            ("cdp_cross", "rearm_ticks"),
            ("vol_burst", "min_window_lots"),
            ("vol_burst", "min_day_lots"),
            ("sweep_cluster", "min_sweeps"),
            ("sweep_cluster", "min_levels"),
        ],
    )
    def test_integer_keys_reject_fractional(self, kind: str, key: str) -> None:
        params = dict(VALID_PARAMS[kind])
        params[key] = float(params[key]) + 0.5
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(kind, params=params), {})

    @pytest.mark.parametrize(
        ("kind", "key"),
        [
            ("cdp_cross", "rearm_ticks"),
            ("vol_burst", "min_window_lots"),
            ("vol_burst", "min_day_lots"),
        ],
    )
    def test_integer_keys_accept_integral_float(self, kind: str, key: str) -> None:
        params = dict(VALID_PARAMS[kind])
        params[key] = float(params[key])
        assert normalize_rule(make(kind, params=params), {})["params"][key] == params[key]

    def test_float_keys_accept_fractional(self) -> None:
        params = dict(VALID_PARAMS["surge_crash"])
        params["pct"] = 2.5
        assert normalize_rule(make("surge_crash", params=params), {})["params"]["pct"] == 2.5

    def test_rearm_dwell_secs_is_float_not_integer_key(self) -> None:
        """D7:駐留秒數與 `window_secs` 同型 —— 秒不需要整數限制,2.5 秒必須收得下。

        誤加進 `INT_PARAM_KEYS` 的失效樣態是使用者填 2.5 拿到 INVALID_RULE,
        而畫面上只會顯示「規則設定不合法」,看不出是哪一欄。
        """
        params = dict(VALID_PARAMS["cdp_cross"])
        params["rearm_dwell_secs"] = 2.5
        out = normalize_rule(make("cdp_cross", params=params), {})
        assert out["params"]["rearm_dwell_secs"] == 2.5

    def test_rearm_dwell_secs_above_max_rejected(self) -> None:
        params = dict(VALID_PARAMS["cdp_cross"])
        params["rearm_dwell_secs"] = 3601
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("cdp_cross", params=params), {})


class TestNormalizeFields:
    def test_unknown_kind_rejected(self) -> None:
        rule = make("cdp_cross")
        rule["kind"] = "nope"
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(rule, {})

    def test_blank_name_rejected(self) -> None:
        for bad in ("", "   "):
            with pytest.raises(RuleError, match="INVALID_RULE"):
                normalize_rule(make(name=bad), {})

    def test_missing_id_rejected(self) -> None:
        for bad in ("", 3):
            with pytest.raises(RuleError, match="INVALID_RULE"):
                normalize_rule(make(id=bad), {})

    @pytest.mark.parametrize("field", ["enabled", "notify_discord"])
    def test_non_bool_flags_rejected(self, field: str) -> None:
        rule = make()
        rule[field] = 1
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(rule, {})

    @pytest.mark.parametrize("bad", [59, 86_401, True, 600.5, "600"])
    def test_cooldown_out_of_domain_rejected(self, bad: object) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(cooldown_secs=bad), {})


class TestNormalizeNameUniqueness:
    def test_duplicate_name_against_others_rejected(self) -> None:
        other = normalize_rule(make(id="r-1-001", name="重複"), {})
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(id="r-1-002", name="重複"), {"r-1-001": other})

    def test_duplicate_name_after_strip_rejected(self) -> None:
        other = normalize_rule(make(id="r-1-001", name="重複"), {})
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(id="r-1-002", name="  重複 "), {"r-1-001": other})

    def test_self_excluded_from_others_so_rename_noop_allowed(self) -> None:
        """R6:others 不含自身 —— 編輯規則但不改名不該被自己撞掉."""
        me = normalize_rule(make(id="r-1-001", name="我"), {})
        assert normalize_rule(make(id="r-1-001", name="我"), {})["name"] == "我"
        # 呼叫端若誤把自身放進 others,契約上就是撞名 —— 明示這個界線
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(id="r-1-001", name="我"), {"r-1-001": me})


class TestNormalizeCdpLevels:
    def test_cdp_cross_requires_non_empty_levels(self) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("cdp_cross", cdp_levels=[]), {})

    def test_unknown_level_rejected(self) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("cdp_cross", cdp_levels=["ah", "zz"]), {})

    def test_subset_kept_in_order_and_deduped(self) -> None:
        out = normalize_rule(make("cdp_cross", cdp_levels=["nl", "ah", "nl"]), {})
        assert out["cdp_levels"] == ["nl", "ah"]

    @pytest.mark.parametrize("kind", [k for k in RULE_KINDS if k != "cdp_cross"])
    def test_non_cdp_kind_must_have_empty_levels(self, kind: str) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(kind, cdp_levels=["ah"]), {})

    def test_levels_not_a_list_rejected(self) -> None:
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make("cdp_cross", cdp_levels="ah"), {})


class TestNewRuleId:
    def test_format(self) -> None:
        assert new_rule_id(1_754_400_000, 7) == "r-1754400000-007"

    def test_seq_beyond_three_digits_not_truncated(self) -> None:
        assert new_rule_id(1, 1234) == "r-1-1234"


#: default_rules / v2→v3 遷移的種子 kind 序:surge_pullback 兩張卡(1% / 2%,spec #174);
#: v3→v4 再 append 掃單簇一張(spec #192)。
SEEDED_KINDS = [
    "cdp_cross",
    "surge_crash",
    "surge_pullback",
    "surge_pullback",
    "vol_burst",
    "limit_lock",
    "sweep_cluster",
]


class TestDefaultRules:
    def test_seeded_rules_all_valid(self) -> None:
        """七條種子(五 kind 各一 + surge_pullback 兩卡)全部過 normalize、id/name 唯一。"""
        rules = default_rules(SignalsConfig(), {})
        assert [r["kind"] for r in rules] == SEEDED_KINDS
        assert len({r["id"] for r in rules}) == len(rules)
        assert len({r["name"] for r in rules}) == len(rules)
        by_id = {r["id"]: r for r in rules}
        for r in rules:
            others = {k: v for k, v in by_id.items() if k != r["id"]}
            assert normalize_rule(r, others) == r

    def test_legacy_flags_map_to_enabled(self) -> None:
        # by name 不 by kind(review F-14):kind 已非唯一鍵,dict 會把兩張回檔卡塌成一張
        rules = default_rules(SignalsConfig(), {"vol_burst": False, "cdp_cross": True})
        flags = {r["name"]: r["enabled"] for r in rules}
        assert flags["爆量"] is False
        assert flags["CDP 穿越"] is True
        assert flags["爆拉爆跌"] is True  # 缺鍵 = fail-open 全開
        assert flags["鎖漲跌停"] is True
        assert flags["爆拉回檔 1%"] is True  # 真舊開關檔沒有這一鍵 → 兩卡各自恆開
        assert flags["爆拉回檔 2%"] is True
        assert flags["掃單簇"] is True  # 同上:晚於開關檔時代,恆走缺鍵 fail-open

    def test_seed_notify_flags_quiet_for_negative_kinds(self) -> None:
        """spec #192:全新安裝的預設規則 cdp_cross / vol_burst / sweep_cluster 通知關,其餘開。

        通知關仍保證 jsonl 與 WS 照走(W3)—— 這裡只釘種子旗標,不釘 fanout。
        """
        rules = default_rules(SignalsConfig(), {})
        assert {r["kind"]: r["notify_discord"] for r in rules} == {
            "cdp_cross": False,
            "surge_crash": True,
            "surge_pullback": True,
            "vol_burst": False,
            "limit_lock": True,
            "sweep_cluster": False,
        }
        assert all(r["enabled"] for r in rules)  # 通知關 ≠ 停用:事件照記

    def test_params_seeded_from_config(self) -> None:
        cfg = SignalsConfig(
            cdp_rearm_ticks=7,
            cdp_rearm_dwell_secs=180.0,
            surge_pct=3.5,
            surge_window_secs=120.0,
            vol_ratio=4.0,
            vol_min_elapsed_min=20.0,
            vol_min_window_lots=200,
            vol_min_day_lots=900,
            sweep_cluster_window_secs=45.0,
            sweep_min_sweeps=3,
            sweep_min_levels=4,
            sweep_up_pct=0.5,
            sweep_up_window_secs=90.0,
        )
        # 回檔兩卡另由 test_pullback_seed_cards_pinned_to_names 按 name 鎖;這裡先濾掉,
        # 免得 by-kind dict 靜默塌卡讓人誤以為有斷到(review F-14)
        by_kind = {r["kind"]: r for r in default_rules(cfg, {}) if r["kind"] != "surge_pullback"}
        assert by_kind["cdp_cross"]["params"]["rearm_ticks"] == 7
        assert by_kind["cdp_cross"]["params"]["rearm_dwell_secs"] == 180.0
        assert by_kind["cdp_cross"]["cdp_levels"] == list(CDP_LEVELS)
        assert by_kind["surge_crash"]["params"] == {"pct": 3.5, "window_secs": 120.0}
        assert by_kind["vol_burst"]["params"] == {
            "ratio": 4.0,
            "window_secs": 120.0,
            "min_elapsed_min": 20.0,
            "min_window_lots": 200.0,
            "min_day_lots": 900.0,
        }
        assert by_kind["limit_lock"]["params"] == {}
        assert by_kind["sweep_cluster"]["params"] == {
            "cluster_window_secs": 45.0,
            "min_sweeps": 3.0,
            "min_levels": 4.0,
            "up_pct": 0.5,
            "up_window_secs": 90.0,
        }
        assert by_kind["sweep_cluster"]["cdp_levels"] == []

    def test_pullback_seed_cards_pinned_to_names(self) -> None:
        """兩張卡的 pct 是卡的身分(綁名稱,不吃 config);武裝參數沿 surge 全域設定。"""
        cfg = SignalsConfig(surge_pct=3.5, surge_window_secs=120.0, pullback_pct=9.9)
        by_name = {r["name"]: r for r in default_rules(cfg, {})}
        one = by_name["爆拉回檔 1%"]
        two = by_name["爆拉回檔 2%"]
        assert one["params"] == {"surge_pct": 3.5, "window_secs": 120.0, "pct": 1.0}
        assert two["params"] == {"surge_pct": 3.5, "window_secs": 120.0, "pct": 2.0}
        assert one["cdp_levels"] == [] and two["cdp_levels"] == []

    def test_cooldowns_seeded_per_kind(self) -> None:
        cfg = SignalsConfig(
            cdp_cooldown_secs=300.0,
            surge_cooldown_secs=900.0,
            vol_cooldown_secs=1200.0,
            limit_cooldown_secs=180.0,
            pullback_cooldown_secs=240.0,
            sweep_cooldown_secs=75.0,
        )
        # by name(review F-14):兩張回檔卡各自斷言,不讓 dict 塌卡
        by_name = {r["name"]: r["cooldown_secs"] for r in default_rules(cfg, {})}
        assert by_name == {
            "CDP 穿越": 300,
            "爆拉爆跌": 900,
            "爆拉回檔 1%": 240,
            "爆拉回檔 2%": 240,
            "爆量": 1200,
            "鎖漲跌停": 180,
            "掃單簇": 75,
        }

    def test_out_of_domain_config_cooldown_clamped_not_raised(self) -> None:
        """設定檔可以把冷卻設到界外 —— 遷移不得因此炸掉(clamp 並 log)."""
        rules = default_rules(SignalsConfig(cdp_cooldown_secs=1.0), {})
        by_kind = {r["kind"]: r["cooldown_secs"] for r in rules}
        assert by_kind["cdp_cross"] == COOLDOWN_MIN


class TestLoadSaveRules:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """None = 沒這個檔 → hub 走遷移;與「空陣列」語意不同."""
        assert load_rules(tmp_path / "nope.json") is None

    def test_empty_list_round_trips_as_empty(self, tmp_path: Path) -> None:
        """使用者刪光規則不得復活預設(邊界 1)."""
        path = tmp_path / "rules.json"
        save_rules(path, [])
        assert load_rules(path) == []

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        rules: list[Rule] = [
            normalize_rule(make("cdp_cross", id="r-1-000", name="A"), {}),
            normalize_rule(make("vol_burst", id="r-1-001", name="B"), {}),
        ]
        save_rules(path, rules)
        assert load_rules(path) == rules

    def test_saved_file_carries_cache_version(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        save_rules(path, [])
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 4
        assert payload["rules"] == []

    def test_bad_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_non_object_payload_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_version_mismatch_raises(self, tmp_path: Path) -> None:
        """版本 bump = 開發期動作,屆時必須同時寫轉換 —— 大聲不靜默."""
        path = tmp_path / "rules.json"
        path.write_text(json.dumps({"_cache_version": 999, "rules": []}), encoding="utf-8")
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_invalid_rule_in_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        bad = make("cdp_cross", cooldown_secs=5)
        path.write_text(
            json.dumps({"_cache_version": 1, "rules": [bad]}, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_duplicate_names_in_file_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        rules = [make(id="r-1-000", name="同"), make(id="r-1-001", name="同")]
        path.write_text(
            json.dumps({"_cache_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_duplicate_ids_in_file_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        rules = [make(id="r-1-000", name="甲"), make(id="r-1-000", name="乙")]
        path.write_text(
            json.dumps({"_cache_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_over_max_rules_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        rules = [make(id=f"r-1-{i:03d}", name=f"n{i}") for i in range(MAX_RULES + 1)]
        path.write_text(
            json.dumps({"_cache_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_exactly_max_rules_ok(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        rules = [make(id=f"r-1-{i:03d}", name=f"n{i}") for i in range(MAX_RULES)]
        path.write_text(
            json.dumps({"_cache_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8"
        )
        loaded = load_rules(path)
        assert loaded is not None and len(loaded) == MAX_RULES

    def test_save_oserror_propagates(self, tmp_path: Path) -> None:
        """R12/R21:落檔失敗必須往外拋(route 500 RULE_SAVE_FAILED),不得吞掉."""
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        with pytest.raises(OSError):
            save_rules(blocker / "rules.json", [])


def _write_versioned(path: Path, version: int, rules: list[Any]) -> None:
    """預寫指定版本的規則檔(兩個遷移測試類共用 —— review F-15 收單源)。"""
    path.write_text(
        json.dumps({"_cache_version": version, "rules": rules}, ensure_ascii=False),
        encoding="utf-8",
    )


class TestMigrationFromV1:
    """SC-8 + 遷移鏈:既有 v1 規則檔在載入期補 `rearm_dwell_secs` 並走完 v2→v3
    種子注入與 v3→v4(掃單簇種子 + 通知翻旗),不回寫檔案(§7 回退窗;save 落當前版本 v4)。

    沒有這條轉換,升級後第一次啟動就是 `load_rules` raise → hub None →
    `/api/stock/signals/*` 全數 503,而且盤中才會發現。
    """

    def _v1_cdp(self) -> dict[str, Any]:
        rule = make("cdp_cross", id="r-1-000", name="舊 CDP")
        rule["params"] = {"rearm_ticks": 5}  # v1 形:沒有 rearm_dwell_secs
        return rule

    def test_v1_file_loads_with_dwell_backfilled(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 1, [self._v1_cdp(), make("limit_lock", id="r-1-001", name="鎖停")])

        loaded = load_rules(path)

        # v1 → v2 補鍵之外,遷移鏈尾端(v2 → v3 → v4)另 append 兩張 surge_pullback 種子卡
        # 與一張掃單簇種子卡,並把舊 CDP 規則的通知翻 false
        assert loaded is not None and len(loaded) == 5
        assert loaded[0]["params"] == {"rearm_ticks": 5.0, "rearm_dwell_secs": 300.0}
        assert loaded[0]["notify_discord"] is False
        assert loaded[1]["params"] == {}
        assert loaded[1]["notify_discord"] is True
        assert [r["kind"] for r in loaded[2:]] == [
            "surge_pullback",
            "surge_pullback",
            "sweep_cluster",
        ]

    def test_v1_file_not_rewritten_on_load(self, tmp_path: Path) -> None:
        """不回寫 = upsert 前還留著回退窗(§7):舊碼可以直接讀回原檔。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 1, [self._v1_cdp()])
        before = path.read_text(encoding="utf-8")

        load_rules(path)

        assert path.read_text(encoding="utf-8") == before

    def test_v1_migration_logs_rule_id_and_value(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """補值與種子路徑(`cfg.cdp_rearm_dwell_secs`)可能不同 → 補了什麼要留痕(§7 已知分歧)。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 1, [self._v1_cdp()])
        with caplog.at_level("INFO"):
            load_rules(path)
        assert "r-1-000" in caplog.text
        assert "300" in caplog.text

    def test_v2_file_missing_new_key_rejected(self, tmp_path: Path) -> None:
        """精確集合仍在(W9):v2 檔缺鍵不是「舊檔」,是壞檔 —— 不得順手補。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [self._v1_cdp()])
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_v2_file_with_new_key_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [make("cdp_cross", id="r-1-000", name="新 CDP")])
        loaded = load_rules(path)
        assert loaded is not None
        assert loaded[0]["params"]["rearm_dwell_secs"] == 300.0

    def test_v1_file_with_new_key_kept_as_is(self, tmp_path: Path) -> None:
        """v1 檔已帶新鍵(手改過)→ 不覆蓋成預設。"""
        path = tmp_path / "rules.json"
        rule = make("cdp_cross", id="r-1-000", name="手改")
        rule["params"] = {"rearm_ticks": 5, "rearm_dwell_secs": 60}
        _write_versioned(path, 1, [rule])
        loaded = load_rules(path)
        assert loaded is not None
        assert loaded[0]["params"]["rearm_dwell_secs"] == 60.0

    def test_v1_invalid_rule_still_raises(self, tmp_path: Path) -> None:
        """遷移只補鍵,不放寬其他驗證。"""
        path = tmp_path / "rules.json"
        bad = self._v1_cdp()
        bad["cooldown_secs"] = 5
        _write_versioned(path, 1, [bad])
        with pytest.raises(RuleError, match="INVALID_RULE"):
            load_rules(path)

    def test_save_after_v1_load_lands_v4(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 1, [self._v1_cdp()])
        loaded = load_rules(path)
        assert loaded is not None
        save_rules(path, loaded)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 4
        assert payload["rules"][0]["params"]["rearm_dwell_secs"] == 300.0
        # v1 鏈到 v4 也吃到通知翻旗(舊 CDP 規則通知關)與掃單簇種子
        assert payload["rules"][0]["notify_discord"] is False
        assert payload["rules"][-1]["kind"] == "sweep_cluster"

    def test_version_zero_and_five_still_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        for version in (0, 5):
            _write_versioned(path, version, [])
            with pytest.raises(RuleError, match="INVALID_RULE"):
                load_rules(path)


class TestMigrationV2ToV3:
    """spec #174 種子注入:v2(或 v1 補鍵後)檔在載入期 append 兩張 surge_pullback
    種子卡,不回寫檔案(回退窗同 v1→v2;第一次 upsert 才以當前版本落檔)。

    「空陣列不得復活預設」的既有語意只約束 **當前版本(v4)** 檔:v2→v3 / v3→v4 是
    一次性升級注入,使用者在 v4 世界刪掉種子卡後(save 已落 v4)不再回來。
    spec #192 起 v2 檔會一路鏈到 v4:兩張回檔卡之後再 append 掃單簇種子。
    """

    def test_v2_file_gets_two_seed_cards_appended(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [make("surge_crash", id="r-1-000", name="爆拉爆跌")])
        with caplog.at_level("INFO"):
            loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 4
        seeds = loaded[1:3]
        assert [r["name"] for r in seeds] == ["爆拉回檔 1%", "爆拉回檔 2%"]
        assert loaded[3]["kind"] == "sweep_cluster"  # v3→v4 接續 append
        assert seeds[0]["params"] == {"surge_pct": 2.0, "window_secs": 300.0, "pct": 1.0}
        assert seeds[1]["params"] == {"surge_pct": 2.0, "window_secs": 300.0, "pct": 2.0}
        for seed in seeds:
            assert seed["kind"] == "surge_pullback"
            assert seed["enabled"] is True
            assert seed["notify_discord"] is True
            assert seed["cdp_levels"] == []
        # 撞既有 id 的去重見 test_seed_id_collision_with_existing_dedups(這裡 id 空間不相交)
        assert len({r["id"] for r in loaded}) == 4
        # append 內容要留痕(對帳判準,v1 遷移 log 前例同款;review F-05);v3→v4 再一張
        assert caplog.text.count("v2→v3:append 種子卡") == 2
        assert caplog.text.count("v3→v4:append 種子卡") == 1

    def test_seed_id_collision_with_existing_dedups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_migrate_v2` 的 while 去重迴圈(review F-04):既有規則恰佔走種子要配的 id
        (`r-<epoch>-001`)時要往前找,不得產出重複 id —— 沒有迴圈的症狀是
        `load_rules` 對重複 id raise → 開機 hub None → signals routes 整組 503。"""
        import copycat.signal_rules as signal_rules_mod

        epoch = 1_700_000_000
        monkeypatch.setattr(signal_rules_mod, "time", types.SimpleNamespace(time=lambda: epoch))
        path = tmp_path / "rules.json"
        # len(items)=1 → 種子 seq 自 1 起 → 第一張卡想配 r-1700000000-001,恰被佔走
        occupied = make("surge_crash", id=f"r-{epoch}-001", name="爆拉爆跌")
        _write_versioned(path, 2, [occupied])
        loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 4  # 沒有去重迴圈時這裡是 raise
        assert len({r["id"] for r in loaded}) == 4

    def test_seed_skip_on_max_rules_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """跳卡 WARNING 是滿載使用者「沒拿到那張卡」的唯一訊號(review F-05)。"""
        path = tmp_path / "rules.json"
        _write_versioned(
            path, 2, [make("limit_lock", id=f"r-1-{i:03d}", name=f"規則{i}") for i in range(30)]
        )
        with caplog.at_level("WARNING"):
            loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 30
        assert caplog.text.count("跳過種子卡") == 3  # 兩張回檔卡 + 掃單簇

    def test_v2_empty_file_still_gets_seeds(self, tmp_path: Path) -> None:
        """一次性升級注入:v2 空檔(v2 世界刪光的)也拿到新功能的種子。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [])
        loaded = load_rules(path)
        assert loaded is not None
        assert [r["name"] for r in loaded] == ["爆拉回檔 1%", "爆拉回檔 2%", "掃單簇"]

    def test_v2_file_not_rewritten_on_load(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [])
        before = path.read_text(encoding="utf-8")
        load_rules(path)
        assert path.read_text(encoding="utf-8") == before

    def test_v4_file_never_reseeded(self, tmp_path: Path) -> None:
        """v4 檔刪光就是刪光 —— 既有「空陣列 ≠ 缺檔」語意在當前版本上原樣成立。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 4, [])
        assert load_rules(path) == []

    def test_seed_skipped_on_name_collision(self, tmp_path: Path) -> None:
        """使用者已有同名規則 → 跳過那一張(不 raise、不重複名稱)。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [make("surge_crash", id="r-1-000", name="爆拉回檔 1%")])
        loaded = load_rules(path)
        assert loaded is not None
        assert [r["name"] for r in loaded] == ["爆拉回檔 1%", "爆拉回檔 2%", "掃單簇"]
        assert loaded[0]["kind"] == "surge_crash"  # 既有那條原樣保留

    def test_seed_skipped_when_would_exceed_max_rules(self, tmp_path: Path) -> None:
        """29 條 → 只塞得下 1% 卡(2% 與掃單簇跳過);30 條 → 全跳過(不得讓 load raise)。"""
        path = tmp_path / "rules.json"
        many = [make("limit_lock", id=f"r-1-{i:03d}", name=f"規則{i}") for i in range(29)]
        _write_versioned(path, 2, many)
        loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 30
        assert loaded[-1]["name"] == "爆拉回檔 1%"

        full = [make("limit_lock", id=f"r-1-{i:03d}", name=f"規則{i}") for i in range(30)]
        _write_versioned(path, 2, full)
        loaded_full = load_rules(path)
        assert loaded_full is not None and len(loaded_full) == 30
        assert all(r["kind"] == "limit_lock" for r in loaded_full)

    def test_save_after_v2_load_lands_v4_and_stable(self, tmp_path: Path) -> None:
        """load → save → load 不再增生(v4 檔不重播種)。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 2, [make("surge_crash", id="r-1-000", name="爆拉爆跌")])
        loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 4
        save_rules(path, loaded)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 4
        again = load_rules(path)
        assert again == loaded


class TestMigrationV3ToV4:
    """spec #192 一次性遷移:v3(或更舊,鏈到 v3 之後)檔在載入期 (a) append 掃單簇種子
    (enabled、通知關、冷卻 60、參數 = 全域設定預設)、(b) cdp_cross / vol_burst 規則通知
    改 false 逐條 log;載入不回寫,第一次 upsert 才落 v4。

    回退手順寫在 `load_rules` docstring:停 server → 刪掃單簇卡、通知改回 true、
    `_cache_version` 改 3 → 起舊碼。
    """

    def _v3_set(self) -> list[Any]:
        return [
            make("cdp_cross", id="r-1-000", name="CDP 穿越"),
            make("surge_crash", id="r-1-001", name="爆拉爆跌"),
            make("vol_burst", id="r-1-002", name="爆量", notify_discord=True),
            make("limit_lock", id="r-1-003", name="鎖漲跌停"),
        ]

    def test_v3_file_gets_sweep_seed_and_quiet_flags(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, self._v3_set())
        with caplog.at_level("INFO"):
            loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 5
        seed = loaded[4]
        assert seed["kind"] == "sweep_cluster"
        assert seed["name"] == "掃單簇"
        assert seed["enabled"] is True
        assert seed["notify_discord"] is False
        assert seed["cooldown_secs"] == 60
        assert seed["params"] == {
            "cluster_window_secs": 30.0,
            "min_sweeps": 2.0,
            "min_levels": 2.0,
            "up_pct": 0.3,
            "up_window_secs": 60.0,
        }
        assert seed["cdp_levels"] == []
        flags = {r["name"]: r["notify_discord"] for r in loaded}
        assert flags == {
            "CDP 穿越": False,
            "爆拉爆跌": True,
            "爆量": False,
            "鎖漲跌停": True,
            "掃單簇": False,
        }
        # 其餘欄位逐字不變(只翻通知旗)
        assert loaded[0]["params"] == {"rearm_ticks": 5.0, "rearm_dwell_secs": 300.0}
        assert loaded[0]["enabled"] is True
        # 逐條 log(對帳判準):兩條被翻旗的規則各一行、種子一行
        assert caplog.text.count("v3→v4:規則") == 2
        assert "r-1-000" in caplog.text and "r-1-002" in caplog.text
        assert caplog.text.count("v3→v4:append 種子卡") == 1

    def test_v3_flip_only_touches_cdp_and_vol_kinds(self, tmp_path: Path) -> None:
        """兩張回檔卡 / 鎖停 / 爆拉爆跌的通知不動(白名單 W11 之外沒拍板要動的東西不動)。"""
        path = tmp_path / "rules.json"
        rules = [
            make("surge_pullback", id="r-1-000", name="爆拉回檔 1%"),
            make("surge_crash", id="r-1-001", name="爆拉爆跌"),
            make("limit_lock", id="r-1-002", name="鎖漲跌停"),
        ]
        _write_versioned(path, 3, rules)
        loaded = load_rules(path)
        assert loaded is not None
        assert [r["notify_discord"] for r in loaded[:3]] == [True, True, True]

    def test_v3_already_quiet_rule_not_logged_twice(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """使用者早就把 CDP 通知關掉 → 不翻、不 log(log 只講「改了什麼」)。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, [make("cdp_cross", id="r-1-000", notify_discord=False)])
        with caplog.at_level("INFO"):
            loaded = load_rules(path)
        assert loaded is not None and loaded[0]["notify_discord"] is False
        assert caplog.text.count("v3→v4:規則") == 0

    def test_v3_seed_skipped_on_name_collision(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, [make("surge_crash", id="r-1-000", name="掃單簇")])
        loaded = load_rules(path)
        assert loaded is not None
        assert [r["kind"] for r in loaded] == ["surge_crash"]  # 既有那條原樣保留、不重複名

    def test_v3_seed_skipped_when_full_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(
            path, 3, [make("limit_lock", id=f"r-1-{i:03d}", name=f"規則{i}") for i in range(30)]
        )
        with caplog.at_level("WARNING"):
            loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 30
        assert caplog.text.count("v3→v4") == 1 and "跳過種子卡" in caplog.text

    def test_v3_empty_file_still_gets_seed(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, [])
        loaded = load_rules(path)
        assert loaded is not None
        assert [r["name"] for r in loaded] == ["掃單簇"]

    def test_v3_file_not_rewritten_on_load(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, self._v3_set())
        before = path.read_text(encoding="utf-8")
        load_rules(path)
        assert path.read_text(encoding="utf-8") == before

    def test_v4_file_flags_untouched(self, tmp_path: Path) -> None:
        """v4 檔 = 使用者在規則視窗開回 CDP 通知後落的檔 → 載入不得再翻回去。"""
        path = tmp_path / "rules.json"
        _write_versioned(path, 4, [make("cdp_cross", id="r-1-000", notify_discord=True)])
        loaded = load_rules(path)
        assert loaded is not None and loaded[0]["notify_discord"] is True

    def test_save_after_v3_load_lands_v4_and_stable(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        _write_versioned(path, 3, self._v3_set())
        loaded = load_rules(path)
        assert loaded is not None and len(loaded) == 5
        save_rules(path, loaded)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 4
        assert load_rules(path) == loaded


class TestRuleConfig:
    def test_cdp_cross_mapping(self) -> None:
        base = SignalsConfig()
        rule = normalize_rule(
            make("cdp_cross", cooldown_secs=900, params={"rearm_ticks": 8, "rearm_dwell_secs": 120}),
            {},
        )
        cfg = rule_config(rule, base)
        assert cfg.cdp_rearm_ticks == 8
        assert isinstance(cfg.cdp_rearm_ticks, int)
        assert cfg.cdp_rearm_dwell_secs == 120.0
        assert cfg.cdp_cooldown_secs == 900
        assert cfg.surge_pct == base.surge_pct  # 其他 kind 欄位不動

    def test_cdp_rearm_dwell_secs_zero_maps_through(self) -> None:
        """W3:0 = 舊行為(離線即解除);0 是合法值,不得被當成「沒設」而落回 base 預設。"""
        base = SignalsConfig(cdp_rearm_dwell_secs=300.0)
        rule = normalize_rule(
            make("cdp_cross", params={"rearm_ticks": 5, "rearm_dwell_secs": 0}), {}
        )
        assert rule_config(rule, base).cdp_rearm_dwell_secs == 0.0

    def test_surge_crash_mapping(self) -> None:
        rule = normalize_rule(
            make("surge_crash", cooldown_secs=900, params={"pct": 3.5, "window_secs": 120}), {}
        )
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.surge_pct == 3.5
        assert cfg.surge_window_secs == 120.0
        assert cfg.surge_cooldown_secs == 900

    def test_vol_burst_mapping_uses_surge_window_secs(self) -> None:
        """SignalsConfig 無 vol_window_secs;per-rule detector 讓 surge_window_secs 可共用."""
        rule = normalize_rule(
            make(
                "vol_burst",
                cooldown_secs=1200,
                params={
                    "ratio": 4.5,
                    "window_secs": 90,
                    "min_elapsed_min": 20,
                    "min_window_lots": 150,
                    "min_day_lots": 800,
                },
            ),
            {},
        )
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.vol_ratio == 4.5
        assert cfg.surge_window_secs == 90.0
        assert cfg.vol_min_elapsed_min == 20.0
        assert cfg.vol_min_window_lots == 150
        assert isinstance(cfg.vol_min_window_lots, int)
        assert cfg.vol_min_day_lots == 800
        assert isinstance(cfg.vol_min_day_lots, int)
        assert cfg.vol_cooldown_secs == 1200

    def test_surge_pullback_mapping(self) -> None:
        """武裝參數映既有 surge 欄(per-rule config,與 vol_burst 借窗同一模式);
        回檔門檻與冷卻映 pullback 專屬欄。"""
        rule = normalize_rule(
            make(
                "surge_pullback",
                cooldown_secs=900,
                params={"surge_pct": 3.0, "window_secs": 120, "pct": 1.5},
            ),
            {},
        )
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.surge_pct == 3.0
        assert cfg.surge_window_secs == 120.0
        assert cfg.pullback_pct == 1.5
        assert cfg.pullback_cooldown_secs == 900

    def test_limit_lock_mapping(self) -> None:
        rule = normalize_rule(make("limit_lock", cooldown_secs=180), {})
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.limit_cooldown_secs == 180

    def test_sweep_cluster_mapping(self) -> None:
        """五參數 + 冷卻各自落到 `sweep_*` 專屬欄;整數鍵映成 int。"""
        rule = normalize_rule(
            make(
                "sweep_cluster",
                cooldown_secs=120,
                params={
                    "cluster_window_secs": 45,
                    "min_sweeps": 3,
                    "min_levels": 4,
                    "up_pct": 0.5,
                    "up_window_secs": 90,
                },
            ),
            {},
        )
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.sweep_cluster_window_secs == 45.0
        assert cfg.sweep_min_sweeps == 3 and isinstance(cfg.sweep_min_sweeps, int)
        assert cfg.sweep_min_levels == 4 and isinstance(cfg.sweep_min_levels, int)
        assert cfg.sweep_up_pct == 0.5
        assert cfg.sweep_up_window_secs == 90.0
        assert cfg.sweep_cooldown_secs == 120

    @pytest.mark.parametrize("kind", RULE_KINDS)
    def test_non_signal_fields_preserved(self, kind: str) -> None:
        base = SignalsConfig(discord_per_min=7, basis_gap_secs=0.0)
        cfg = rule_config(normalize_rule(make(kind), {}), base)
        assert cfg.discord_per_min == 7
        assert cfg.basis_gap_secs == 0.0

    def test_base_config_not_mutated(self) -> None:
        base = SignalsConfig()
        rule_config(
            normalize_rule(
                make("cdp_cross", params={"rearm_ticks": 9, "rearm_dwell_secs": 30}), {}
            ),
            base,
        )
        assert base.cdp_rearm_ticks == SignalsConfig().cdp_rearm_ticks
        assert base.cdp_rearm_dwell_secs == SignalsConfig().cdp_rearm_dwell_secs
