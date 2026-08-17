"""訊號規則模型(signal-rules design v2.1「SC-1 規則模型」)— 值域驗證 / 三態存取 / config 映射.

一條規則 = 一顆未改動的 `SignalDetector` 的參數來源:`rule_config()` 把規則攤成
per-rule `SignalsConfig`,所以「調參數」永遠只是換一份 config,detector 本身零改動。

**路徑由呼叫端傳入**(hub = `self._data_dir / "signal_rules.json"`,`_ENABLED_FILE` 同款):
本模組刻意不設 CWD 相對的 DEFAULT_PATH —— 測試 harness 注入 tmp_path 才不會污染真檔(R16)。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, TypedDict, cast

from copycat.fileio import atomic_write_text
from copycat.signals_config import SignalsConfig

logger = logging.getLogger(__name__)

__all__ = [
    "CDP_LEVELS",
    "COOLDOWN_MAX",
    "COOLDOWN_MIN",
    "INT_PARAM_KEYS",
    "MAX_RULES",
    "PARAM_SPECS",
    "RULE_KINDS",
    "Rule",
    "RuleError",
    "default_rules",
    "load_rules",
    "new_rule_id",
    "normalize_rule",
    "rule_config",
    "save_rules",
]

RULE_KINDS: tuple[str, ...] = ("cdp_cross", "surge_crash", "vol_burst", "limit_lock")
CDP_LEVELS: tuple[str, ...] = ("ah", "nh", "cdp", "nl", "al")
COOLDOWN_MIN, COOLDOWN_MAX = 60, 86_400
#: REST 可寫入的無界量要有上限(R11)—— 熱路徑是 per-tick N × evaluate。
MAX_RULES = 30
#: v1 = 初版;v2 = cdp_cross params 多了 `rearm_dwell_secs`(見 `load_rules` 的遷移)。
_CACHE_VERSION = 2
#: v1→v2 補值。刻意是模組常數而非 `cfg.cdp_rearm_dwell_secs`:`load_rules(path)` 的簽名
#: 不吃 config,為了遷移多接一個參數會讓所有呼叫端跟著改。與種子路徑(`_seed_params` 走
#: cfg)的分歧在 `configs/signals.json` 覆寫該鍵時才會出現 —— 所以補值要 log 出來。
_DEFAULT_REARM_DWELL_SECS = 300.0

#: 逐 kind 的 params 鍵集合與閉區間值域(R1)。鍵集合是**精確集合**:多鍵 / 缺鍵同樣是
#: INVALID_RULE —— 多鍵放行等於使用者以為調到的參數其實沒接上,缺鍵則會靜默套 detector 預設。
PARAM_SPECS: dict[str, dict[str, tuple[float, float]]] = {
    "cdp_cross": {"rearm_ticks": (0, 50), "rearm_dwell_secs": (0, 3600)},
    "surge_crash": {"pct": (0.1, 50), "window_secs": (10, 3600)},
    "vol_burst": {
        "ratio": (1, 100),
        "window_secs": (10, 3600),
        "min_elapsed_min": (0, 240),
        "min_window_lots": (0, 1e6),
        "min_day_lots": (0, 1e7),
    },
    "limit_lock": {},
}

#: 這些鍵在 `SignalsConfig` 是 int 欄位 —— 2.5 個 tick / 半張都不存在,非整數值拒收(R25)。
#: 不擋的話 `int()` 會靜默截尾,使用者填 2.9 拿到 2。
INT_PARAM_KEYS: frozenset[str] = frozenset({"rearm_ticks", "min_window_lots", "min_day_lots"})

_DEFAULT_NAMES: dict[str, str] = {
    "cdp_cross": "CDP 穿越",
    "surge_crash": "爆拉爆跌",
    "vol_burst": "爆量",
    "limit_lock": "鎖漲跌停",
}


class RuleError(ValueError):
    """error code 進 HTTPException detail.error(跨檔契約)。

    值域僅 {"INVALID_RULE", "RULE_NOT_FOUND"}(R10)—— route handler 逐碼對照,
    多一個碼就是前端拿不到對應文案。本模組只產出 INVALID_RULE。
    """


class Rule(TypedDict):
    id: str
    name: str
    kind: str
    enabled: bool
    notify_discord: bool
    cooldown_secs: int
    params: dict[str, float]
    cdp_levels: list[str]


def _bad() -> RuleError:
    return RuleError("INVALID_RULE")


def _as_int(value: object) -> int | None:
    """int 或整數值 float → int;bool / 非整數 / 非數字 → None(呼叫端轉 INVALID_RULE)。

    bool 必須先擋:它是 int 子類,不擋的話 `True` 會被當成 1 靜默通過。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _normalize_params(kind: str, raw: object) -> dict[str, float]:
    spec = PARAM_SPECS[kind]
    if not isinstance(raw, dict):
        raise _bad()
    if set(cast(dict[Any, Any], raw)) != set(spec):
        raise _bad()
    out: dict[str, float] = {}
    for key, (lo, hi) in spec.items():
        value = cast(dict[Any, Any], raw)[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _bad()
        number = float(value)
        if key in INT_PARAM_KEYS and not number.is_integer():
            raise _bad()
        if not lo <= number <= hi:  # NaN 走這條(比較恆 False)
            raise _bad()
        out[key] = number
    return out


def _normalize_levels(kind: str, raw: object) -> list[str]:
    """cdp_cross 必須非空且 ⊆ 五線(保序去重);其他 kind 必須是空 list。"""
    if not isinstance(raw, list):
        raise _bad()
    levels: list[str] = []
    for item in cast(list[Any], raw):
        if not isinstance(item, str) or item not in CDP_LEVELS:
            raise _bad()
        if item not in levels:
            levels.append(item)
    if kind == "cdp_cross":
        if not levels:
            raise _bad()
    elif levels:
        # 非 cdp 規則帶線 = 使用者以為有過濾效果,實際上 detector 根本不看 —— 直接拒。
        raise _bad()
    return levels


def normalize_rule(rule: Rule, others: dict[str, Rule]) -> Rule:
    """驗證 + 正規化成 canonical 形;任何違規一律 `RuleError("INVALID_RULE")`。

    `others` = 規則全集合**排除自身 id**(R6)—— 編輯規則但不改名不該被自己撞掉。
    冪等:`normalize_rule(normalize_rule(x, o), o) == normalize_rule(x, o)`。
    """
    raw: dict[str, Any] = dict(rule)

    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id:
        raise _bad()

    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in RULE_KINDS:
        raise _bad()

    name = raw.get("name")
    if not isinstance(name, str):
        raise _bad()
    name = name.strip()
    if not name:
        raise _bad()
    if any(other["name"].strip() == name for other in others.values()):
        raise _bad()

    flags: dict[str, bool] = {}
    for key in ("enabled", "notify_discord"):
        value = raw.get(key)
        if not isinstance(value, bool):
            raise _bad()
        flags[key] = value

    cooldown = _as_int(raw.get("cooldown_secs"))
    if cooldown is None or not COOLDOWN_MIN <= cooldown <= COOLDOWN_MAX:
        raise _bad()

    return {
        "id": rule_id,
        "name": name,
        "kind": kind,
        "enabled": flags["enabled"],
        "notify_discord": flags["notify_discord"],
        "cooldown_secs": cooldown,
        "params": _normalize_params(kind, raw.get("params")),
        "cdp_levels": _normalize_levels(kind, raw.get("cdp_levels")),
    }


def new_rule_id(epoch: int, seq: int) -> str:
    """`r-<epoch>-<seq>`;seq = hub 的單調計數(R12),不是 len(rules)——刪除後不得回收 id。"""
    return f"r-{epoch}-{seq:03d}"


def _clamp(label: str, value: float, lo: float, hi: float) -> float:
    """遷移專用夾制:`configs/signals.json` 的值域比規則寬,超界不該讓冷啟動整個炸掉。

    只用在 `default_rules`(從既有全域設定生成種子規則);使用者輸入一律走
    `normalize_rule` 的 raise —— 使用者填錯要當面拒絕,不是默默改成別的數字。
    """
    clamped = max(lo, min(hi, value))
    if clamped != value:
        logger.warning(
            "訊號設定 %s=%s 在規則值域 [%s, %s] 外,遷移時夾制成 %s", label, value, lo, hi, clamped
        )
    return clamped


def _seed_params(kind: str, cfg: SignalsConfig) -> dict[str, float]:
    raw: dict[str, float] = {}
    if kind == "cdp_cross":
        raw = {
            "rearm_ticks": float(cfg.cdp_rearm_ticks),
            "rearm_dwell_secs": float(cfg.cdp_rearm_dwell_secs),
        }
    elif kind == "surge_crash":
        raw = {"pct": float(cfg.surge_pct), "window_secs": float(cfg.surge_window_secs)}
    elif kind == "vol_burst":
        raw = {
            "ratio": float(cfg.vol_ratio),
            # SignalsConfig 無 vol_window_secs —— 爆量的滾動窗一直是借 surge_window_secs
            "window_secs": float(cfg.surge_window_secs),
            "min_elapsed_min": float(cfg.vol_min_elapsed_min),
            "min_window_lots": float(cfg.vol_min_window_lots),
            "min_day_lots": float(cfg.vol_min_day_lots),
        }
    spec = PARAM_SPECS[kind]
    return {key: _clamp(f"{kind}.{key}", value, *spec[key]) for key, value in raw.items()}


def _seed_cooldown(kind: str, cfg: SignalsConfig) -> int:
    source = {
        "cdp_cross": cfg.cdp_cooldown_secs,
        "surge_crash": cfg.surge_cooldown_secs,
        "vol_burst": cfg.vol_cooldown_secs,
        "limit_lock": cfg.limit_cooldown_secs,
    }[kind]
    return int(_clamp(f"{kind}.cooldown_secs", float(int(source)), COOLDOWN_MIN, COOLDOWN_MAX))


def default_rules(cfg: SignalsConfig, legacy_flags: dict[str, bool]) -> list[Rule]:
    """遷移種子:每 kind 一條,參數 / 冷卻取自現行全域 `SignalsConfig`。

    `legacy_flags` = 舊 `signals_enabled.json` 的四鍵;**缺鍵 = True**(fail-open,
    與舊 `_load_enabled` 的「缺檔全開」同語意 —— 遷移不該悄悄把訊號關掉)。
    """
    epoch = int(time.time())
    rules: list[Rule] = []
    for seq, kind in enumerate(RULE_KINDS):
        rules.append(
            {
                "id": new_rule_id(epoch, seq),
                "name": _DEFAULT_NAMES[kind],
                "kind": kind,
                "enabled": legacy_flags.get(kind, True),
                "notify_discord": True,
                "cooldown_secs": _seed_cooldown(kind, cfg),
                "params": _seed_params(kind, cfg),
                "cdp_levels": list(CDP_LEVELS) if kind == "cdp_cross" else [],
            }
        )
    return rules


def _migrate_v1(items: list[Any]) -> list[Any]:
    """v1 → v2:`kind == "cdp_cross"` 且 params 缺 `rearm_dwell_secs` 的規則補預設。

    只補鍵,不放寬任何驗證(補完照走 `normalize_rule`);非 dict / 非 cdp / 已帶該鍵
    的項目原樣傳遞。輸入不就地修改 —— 呼叫端手上的 payload 還要拿來與磁碟原檔比對。
    """
    out: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            out.append(item)
            continue
        obj = cast(dict[str, Any], item)
        params = obj.get("params")
        if obj.get("kind") != "cdp_cross" or not isinstance(params, dict):
            out.append(obj)
            continue
        existing = cast(dict[str, Any], params)
        if "rearm_dwell_secs" in existing:
            out.append(obj)
            continue
        logger.info(
            "訊號規則檔 v1→v2:規則 %r 補 rearm_dwell_secs=%s",
            obj.get("id"),
            _DEFAULT_REARM_DWELL_SECS,
        )
        out.append({**obj, "params": {**existing, "rearm_dwell_secs": _DEFAULT_REARM_DWELL_SECS}})
    return out


def load_rules(path: Path) -> list[Rule] | None:
    """三態(R15/R20):缺檔 → None(hub 走遷移);合法(**含空陣列**)→ list;其餘 raise。

    「空陣列 ≠ 缺檔」是刻意的:使用者把規則刪光後重啟不得復活四條預設。
    壞檔 / 驗證失敗 / 版本不符 / 超過 MAX_RULES 一律 raise —— 靜默套預設會在盤中
    無預警地改變推播行為;raise 走 `_boot` 傘 → hub None → routes 503,大聲。

    **v1 → v2 遷移(D6)**:`_cache_version == 1` 的檔案在記憶體裡補上 cdp 規則的
    `rearm_dwell_secs`(= `_DEFAULT_REARM_DWELL_SECS`)後照常驗證;**載入時不回寫檔案**,
    磁碟要到第一次 upsert 才以 v2 落檔 —— 這段就是回退窗:期間舊碼可直接讀原檔。
    回退手順(已 upsert 過):停 server → 編輯 `data/signal_rules.json`,刪掉每條 cdp
    規則的 `rearm_dwell_secs` 鍵、`_cache_version` 改回 1 → 起舊碼。
    v2 檔缺該鍵不走遷移(是壞檔,不是舊檔);1 / 2 以外的版本一律 raise(既有語意)。
    """
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        logger.error("訊號規則檔非合法 JSON(%s):%s", path, e)
        raise _bad() from e
    if not isinstance(payload, dict):
        logger.error("訊號規則檔格式非物件:%s", path)
        raise _bad()
    obj = cast(dict[str, Any], payload)
    version = obj.get("_cache_version")
    if version not in (_CACHE_VERSION, 1):
        # 版本 bump 屬開發期動作,屆時必須同時寫轉換 —— 沒寫就該在啟動時被發現。
        logger.error("訊號規則檔版本不符(%s):%r", path, version)
        raise _bad()
    raw = obj.get("rules")
    if not isinstance(raw, list):
        logger.error("訊號規則檔缺 rules 陣列:%s", path)
        raise _bad()
    items = cast(list[Any], raw)
    if len(items) > MAX_RULES:
        logger.error("訊號規則檔 %s 條超過上限 %s:%s", len(items), MAX_RULES, path)
        raise _bad()
    if version != _CACHE_VERSION:
        items = _migrate_v1(items)
    rules: dict[str, Rule] = {}
    for item in items:
        if not isinstance(item, dict):
            raise _bad()
        rule = normalize_rule(cast(Rule, item), rules)  # others = 已收的前綴(不含自身)
        if rule["id"] in rules:
            logger.error("訊號規則檔含重複 id:%s", rule["id"])
            raise _bad()
        rules[rule["id"]] = rule
    return list(rules.values())


def save_rules(path: Path, rules: list[Rule]) -> None:
    """atomic 落檔;**OSError 往外拋**(R12/R21)—— route 轉 500 RULE_SAVE_FAILED。

    吞掉這裡的失敗會讓畫面顯示新規則、重啟後跳回舊的(記憶體不得先於落檔更新)。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {"_cache_version": _CACHE_VERSION, "rules": list(rules)},
            ensure_ascii=False,
            indent=1,
        ),
    )


def rule_config(rule: Rule, base: SignalsConfig) -> SignalsConfig:
    """規則 → per-rule `SignalsConfig`(`dataclasses.replace`,base 不動)。

    `cooldown_secs` 依 kind 落到對應 `*_cooldown_secs` —— 漏映射 = per-rule 冷卻
    靜默套全域值(改了沒反應,而且沒有任何錯誤訊號)。
    vol_burst 的滾動窗映到 `surge_window_secs`:`SignalsConfig` 沒有
    `vol_window_secs`,detector 的窗一直是這個共用欄 —— per-rule detector
    讓「爆量的窗」與「爆拉的窗」得以各自獨立。
    """
    params = rule["params"]
    cooldown = float(rule["cooldown_secs"])
    kind = rule["kind"]
    if kind == "cdp_cross":
        return replace(
            base,
            cdp_rearm_ticks=int(params["rearm_ticks"]),
            cdp_rearm_dwell_secs=params["rearm_dwell_secs"],
            cdp_cooldown_secs=cooldown,
        )
    if kind == "surge_crash":
        return replace(
            base,
            surge_pct=params["pct"],
            surge_window_secs=params["window_secs"],
            surge_cooldown_secs=cooldown,
        )
    if kind == "vol_burst":
        return replace(
            base,
            vol_ratio=params["ratio"],
            surge_window_secs=params["window_secs"],
            vol_min_elapsed_min=params["min_elapsed_min"],
            vol_min_window_lots=int(params["min_window_lots"]),
            vol_min_day_lots=int(params["min_day_lots"]),
            vol_cooldown_secs=cooldown,
        )
    if kind == "limit_lock":
        return replace(base, limit_cooldown_secs=cooldown)
    raise _bad()  # normalize_rule 把關後不可達;新增 kind 忘了映射時在此炸出來
