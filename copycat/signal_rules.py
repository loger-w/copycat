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

RULE_KINDS: tuple[str, ...] = (
    "cdp_cross",
    "surge_crash",
    "surge_pullback",
    "vol_burst",
    "limit_lock",
)
CDP_LEVELS: tuple[str, ...] = ("ah", "nh", "cdp", "nl", "al")
COOLDOWN_MIN, COOLDOWN_MAX = 60, 86_400
#: REST 可寫入的無界量要有上限(R11)—— 熱路徑是 per-tick N × evaluate。
MAX_RULES = 30
#: v1 = 初版;v2 = cdp_cross params 多了 `rearm_dwell_secs`;v3 = append 兩張
#: surge_pullback 種子卡(spec #174;見 `load_rules` 的遷移鏈)。
_CACHE_VERSION = 3
#: 可載入版本 = 1.._CACHE_VERSION 推導(review F-10):bump 時白名單自動跟上,
#: 忘了寫轉換會在 `load_rules` 的遷移鏈斷點炸出來,而不是所有舊檔靜默變壞檔 503。
_SUPPORTED_VERSIONS: tuple[int, ...] = tuple(range(1, _CACHE_VERSION + 1))
#: v1→v2 補值。刻意是模組常數而非 `cfg.cdp_rearm_dwell_secs`:`load_rules(path)` 的簽名
#: 不吃 config,為了遷移多接一個參數會讓所有呼叫端跟著改。與種子路徑(`_seed_params` 走
#: cfg)的分歧在 `configs/signals.json` 覆寫該鍵時才會出現 —— 所以補值要 log 出來。
_DEFAULT_REARM_DWELL_SECS = 300.0

#: 逐 kind 的 params 鍵集合與閉區間值域(R1)。鍵集合是**精確集合**:多鍵 / 缺鍵同樣是
#: INVALID_RULE —— 多鍵放行等於使用者以為調到的參數其實沒接上,缺鍵則會靜默套 detector 預設。
PARAM_SPECS: dict[str, dict[str, tuple[float, float]]] = {
    "cdp_cross": {"rearm_ticks": (0, 50), "rearm_dwell_secs": (0, 3600)},
    "surge_crash": {"pct": (0.1, 50), "window_secs": (10, 3600)},
    "surge_pullback": {"surge_pct": (0.1, 50), "window_secs": (10, 3600), "pct": (0.1, 50)},
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

#: surge_pullback 種子兩張卡(spec #174 拍板:5 分鐘 +2% 武裝,回檔 1% / 2%)。
#: `pct` 是卡的**身分**(綁名稱)—— 不吃 config,否則覆寫 `pullback_pct` 會讓
#: 「爆拉回檔 1%」這個名字與實際門檻悄悄對不上。
_PULLBACK_SEEDS: tuple[tuple[str, float], ...] = (("爆拉回檔 1%", 1.0), ("爆拉回檔 2%", 2.0))


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
    elif kind == "surge_pullback":
        raw = {
            # 武裝參數借 surge 欄(per-rule config 讓兩者獨立,同 vol_burst 借窗);
            # `pct` 是卡的字面身分(_PULLBACK_SEEDS),由 `_pullback_seed_rule` 覆上
            "surge_pct": float(cfg.surge_pct),
            "window_secs": float(cfg.surge_window_secs),
            "pct": float(cfg.pullback_pct),
        }
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
        "surge_pullback": cfg.pullback_cooldown_secs,
        "vol_burst": cfg.vol_cooldown_secs,
        "limit_lock": cfg.limit_cooldown_secs,
    }[kind]
    return int(_clamp(f"{kind}.cooldown_secs", float(int(source)), COOLDOWN_MIN, COOLDOWN_MAX))


def _pullback_seed_rule(name: str, pct: float, rule_id: str, cfg: SignalsConfig) -> Rule:
    """一張 surge_pullback 種子卡:武裝參數走 `_seed_params`(單源,夾制同其他 kind),
    `pct` 為卡的字面身分覆上。`default_rules` 與 v2→v3 遷移共用 —— 兩條種子路徑分家會漂。
    """
    return {
        "id": rule_id,
        "name": name,
        "kind": "surge_pullback",
        "enabled": True,
        "notify_discord": True,
        "cooldown_secs": _seed_cooldown("surge_pullback", cfg),
        # 拍板字面 pct 恆在值域內;覆在 _seed_params 之後 —— 卡的身分不吃 config
        "params": {**_seed_params("surge_pullback", cfg), "pct": pct},
        "cdp_levels": [],
    }


def default_rules(cfg: SignalsConfig, legacy_flags: dict[str, bool]) -> list[Rule]:
    """遷移種子:每 kind 一條(surge_pullback 例外 = 兩張卡),參數 / 冷卻取自現行
    全域 `SignalsConfig`。

    `legacy_flags` = 舊 `signals_enabled.json` 的鍵值;**缺鍵 = True**(fail-open,
    與舊 `_load_enabled` 的「缺檔全開」同語意 —— 遷移不該悄悄把訊號關掉)。
    注意 hub 的 `_legacy_flags` 以 `SWITCH_KEYS`(現五鍵)起手 → surge_pullback 鍵
    **恆在**:真舊檔沒這鍵 → True;手改過的檔寫 false 則兩張種子卡照關(review F-07,
    刻意如實 —— 開關檔語意就是逐鍵覆蓋)。
    """
    epoch = int(time.time())
    rules: list[Rule] = []
    for kind in RULE_KINDS:
        if kind == "surge_pullback":
            for name, pct in _PULLBACK_SEEDS:
                rule = _pullback_seed_rule(name, pct, new_rule_id(epoch, len(rules)), cfg)
                rule["enabled"] = legacy_flags.get(kind, True)
                rules.append(rule)
            continue
        rules.append(
            {
                "id": new_rule_id(epoch, len(rules)),
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


def _migrate_v2(items: list[Any]) -> list[Any]:
    """v2 → v3:append 兩張 surge_pullback 種子卡(spec #174 一次性注入)。

    武裝參數 / 冷卻走 `SignalsConfig()` **預設值**(= 拍板值):`load_rules(path)` 的
    簽名不吃 config(v1 補值同理由),與 `default_rules` 種子路徑的分歧只在
    `configs/signals.json` 覆寫 surge 鍵時出現,append 內容 log 出來可對帳。
    撞名 → 跳過該卡(使用者已有同名規則,重命名等於替使用者做決定);
    會超過 `MAX_RULES` → 跳過並 WARNING(遷移不得讓載入 raise → routes 503)。
    輸入不就地修改;v2 **空陣列也照塞**(一次性升級注入,不是復活 v3 世界的刪除)。
    """
    existing = [cast("dict[str, Any]", item) for item in items if isinstance(item, dict)]
    names = {str(obj.get("name", "")).strip() for obj in existing}
    ids = {obj.get("id") for obj in existing}
    cfg = SignalsConfig()
    epoch = int(time.time())
    seq = len(items)
    out: list[Any] = list(items)
    for name, pct in _PULLBACK_SEEDS:
        if name in names:
            logger.info("訊號規則檔 v2→v3:已有同名規則,跳過種子卡 %r", name)
            continue
        if len(out) >= MAX_RULES:
            logger.warning("訊號規則檔 v2→v3:規則數已達上限 %s,跳過種子卡 %r", MAX_RULES, name)
            continue
        rule_id = new_rule_id(epoch, seq)
        while rule_id in ids:
            seq += 1
            rule_id = new_rule_id(epoch, seq)
        seq += 1
        ids.add(rule_id)
        rule = _pullback_seed_rule(name, pct, rule_id, cfg)
        logger.info("訊號規則檔 v2→v3:append 種子卡 %r params=%s", name, rule["params"])
        out.append(rule)
    return out


def load_rules(path: Path) -> list[Rule] | None:
    """三態(R15/R20):缺檔 → None(hub 走遷移);合法(**含空陣列**)→ list;其餘 raise。

    「空陣列 ≠ 缺檔」是刻意的:使用者把規則刪光後重啟不得復活四條預設
    (在當前版本 v3 上原樣成立;v2 空檔照樣拿到 v3 的種子卡 —— 那是升級注入,見下)。
    壞檔 / 驗證失敗 / 版本不符 / 超過 MAX_RULES 一律 raise —— 靜默套預設會在盤中
    無預警地改變推播行為;raise 走 `_boot` 傘 → hub None → routes 503,大聲。

    **遷移鏈(D6 + spec #174)**:v1 → `_migrate_v1` 補 cdp 的 `rearm_dwell_secs` →
    v2;v2(含補完的 v1)→ `_migrate_v2` append 兩張 surge_pullback 種子卡 → v3,
    之後照常驗證;**載入時不回寫檔案**,磁碟要到第一次 upsert 才以 v3 落檔 ——
    這段就是回退窗:期間舊碼可直接讀原檔。
    回退手順(已 upsert 過):停 server → 編輯 `data/signal_rules.json`,刪掉兩張
    surge_pullback 種子卡、(要退到 v1 再)刪 cdp 的 `rearm_dwell_secs` 鍵、
    `_cache_version` 改回 2(或 1)→ 起舊碼。
    v2 檔缺 cdp 新鍵不走遷移(是壞檔,不是舊檔);1 / 2 / 3 以外的版本一律 raise。
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
    if version not in _SUPPORTED_VERSIONS:
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
        if version == 1:
            items = _migrate_v1(items)
        items = _migrate_v2(items)
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
    if kind == "surge_pullback":
        # 武裝參數借 surge 欄(per-rule config 讓回檔卡與 surge_crash 卡各自獨立,
        # 與 vol_burst 借窗同一模式);回檔門檻 / 冷卻落 pullback 專屬欄。
        return replace(
            base,
            surge_pct=params["surge_pct"],
            surge_window_secs=params["window_secs"],
            pullback_pct=params["pct"],
            pullback_cooldown_secs=cooldown,
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
