from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from copycat.signal_rules import (
    CDP_LEVELS,
    COOLDOWN_MAX,
    COOLDOWN_MIN,
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
    "cdp_cross": {"rearm_ticks": 5},
    "surge_crash": {"pct": 2.0, "window_secs": 300},
    "vol_burst": {
        "ratio": 3,
        "window_secs": 300,
        "min_elapsed_min": 15,
        "min_window_lots": 100,
        "min_day_lots": 500,
    },
    "limit_lock": {},
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
        assert RULE_KINDS == ("cdp_cross", "surge_crash", "vol_burst", "limit_lock")
        assert CDP_LEVELS == ("ah", "nh", "cdp", "nl", "al")
        assert (COOLDOWN_MIN, COOLDOWN_MAX) == (60, 86_400)
        assert MAX_RULES == 30

    def test_param_specs_cover_every_kind(self) -> None:
        assert set(PARAM_SPECS) == set(RULE_KINDS)
        assert PARAM_SPECS["limit_lock"] == {}


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
        with pytest.raises(RuleError, match="INVALID_RULE"):
            normalize_rule(make(**{field: 1}), {})

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


class TestDefaultRules:
    def test_one_rule_per_kind_all_valid(self) -> None:
        rules = default_rules(SignalsConfig(), {})
        assert [r["kind"] for r in rules] == list(RULE_KINDS)
        assert len({r["id"] for r in rules}) == len(rules)
        assert len({r["name"] for r in rules}) == len(rules)
        by_id = {r["id"]: r for r in rules}
        for r in rules:
            others = {k: v for k, v in by_id.items() if k != r["id"]}
            assert normalize_rule(r, others) == r

    def test_legacy_flags_map_to_enabled(self) -> None:
        rules = default_rules(SignalsConfig(), {"vol_burst": False, "cdp_cross": True})
        flags = {r["kind"]: r["enabled"] for r in rules}
        assert flags["vol_burst"] is False
        assert flags["cdp_cross"] is True
        assert flags["surge_crash"] is True  # 缺鍵 = fail-open 全開
        assert flags["limit_lock"] is True

    def test_params_seeded_from_config(self) -> None:
        cfg = SignalsConfig(
            cdp_rearm_ticks=7,
            surge_pct=3.5,
            surge_window_secs=120.0,
            vol_ratio=4.0,
            vol_min_elapsed_min=20.0,
            vol_min_window_lots=200,
            vol_min_day_lots=900,
        )
        by_kind = {r["kind"]: r for r in default_rules(cfg, {})}
        assert by_kind["cdp_cross"]["params"]["rearm_ticks"] == 7
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

    def test_cooldowns_seeded_per_kind(self) -> None:
        cfg = SignalsConfig(
            cdp_cooldown_secs=300.0,
            surge_cooldown_secs=900.0,
            vol_cooldown_secs=1200.0,
            limit_cooldown_secs=180.0,
        )
        by_kind = {r["kind"]: r["cooldown_secs"] for r in default_rules(cfg, {})}
        assert by_kind == {
            "cdp_cross": 300,
            "surge_crash": 900,
            "vol_burst": 1200,
            "limit_lock": 180,
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
        assert payload["_cache_version"] == 1
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


class TestRuleConfig:
    def test_cdp_cross_mapping(self) -> None:
        base = SignalsConfig()
        rule = normalize_rule(
            make("cdp_cross", cooldown_secs=900, params={"rearm_ticks": 8}), {}
        )
        cfg = rule_config(rule, base)
        assert cfg.cdp_rearm_ticks == 8
        assert isinstance(cfg.cdp_rearm_ticks, int)
        assert cfg.cdp_cooldown_secs == 900
        assert cfg.surge_pct == base.surge_pct  # 其他 kind 欄位不動

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

    def test_limit_lock_mapping(self) -> None:
        rule = normalize_rule(make("limit_lock", cooldown_secs=180), {})
        cfg = rule_config(rule, SignalsConfig())
        assert cfg.limit_cooldown_secs == 180

    @pytest.mark.parametrize("kind", RULE_KINDS)
    def test_non_signal_fields_preserved(self, kind: str) -> None:
        base = SignalsConfig(discord_per_min=7, basis_gap_secs=0.0)
        cfg = rule_config(normalize_rule(make(kind), {}), base)
        assert cfg.discord_per_min == 7
        assert cfg.basis_gap_secs == 0.0

    def test_base_config_not_mutated(self) -> None:
        base = SignalsConfig()
        rule_config(normalize_rule(make("cdp_cross", params={"rearm_ticks": 9}), {}), base)
        assert base.cdp_rearm_ticks == SignalsConfig().cdp_rearm_ticks
