"""訊號影子政策層的純函式(spec #192):族群判定 + 四條政策 P / B-a / B-b / S 的命中判斷。

零 IO、無狀態:輸入是「自己的量」「同伴的快照」「群組結構」「門檻」,輸出是政策命中清單與
可直接落列的脈絡欄位。接線層 `SignalHub` 持有 per-day 計數、notify 判定與 payload 組裝;
本模組只回答「這一顆掃單簇事件命中哪幾條政策、族群脈絡是什麼」。

**政策四條寫死在 code**(2026-09-07 拍板,不進規則 CRUD),門檻只走 `SignalsConfig` 的
`policy_*` 欄覆寫。定義沿研究 `combo_events.py::group_feats`(`_up3` / `_leader` /
`_locked_before`)與 HANDOFF §8 拍板:

- 族群 = 該檔所屬自選群組中,名稱不是盤前篩選群組名(恆排除)且不在 `policy_exclude_groups`
  者;多組取成員**聯集**(保序去重);同伴 = 族群成員扣自己。
- `chg` = (價 − 參考價) ÷ 參考價 × 100;`to_limit` = (漲停價 − 價) ÷ 價 × 100(漲停價缺 → None)。
- 同伴無報價(`chg_pct` None)不計;P / B 至少一檔同伴有報價。
- P:同伴 ≥ `peer_up_pct` 為 0 且 chg < `max_chg_pct` 且族群沒人鎖過。
- B-a:自己最強(chg ≥ 同伴最大 chg)且同伴 ≥ peer_up_pct ≥ 1 且 chg < max_chg_pct 且沒人鎖過。
- B-b:B-a 拿掉 chg < max_chg_pct。
- S:盤前篩選成員且 chg < max_chg_pct(無族群條件)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from copycat.live.stock_models import _best_limit_price
from copycat.stock_watchlist import Group

__all__ = [
    "POLICIES",
    "PeerQuote",
    "PolicyContext",
    "evaluate_policies",
    "locked_up_flag",
    "resolve_groups",
    "tod_bucket",
    "touched_upper_flag",
]

#: 四條政策的固定序(同一事件命中多條時列的順序 / Discord 標記並列的順序)。
POLICIES: tuple[str, ...] = ("P", "B-a", "B-b", "S")


class PeerQuote(TypedDict):
    """引擎 `policy_quotes()` 一檔的形狀(engine 產生、hub 讀 name / chg_pct / touched_upper /
    locked_up;三邊共用同一個型別,review F-05)。值欄位 None = no_data / 缺 meta / 未成交。"""

    name: str
    price: int | None
    ref: int | None
    upper: int | None
    chg_pct: float | None
    high: int | None
    touched_upper: bool | None
    locked_up: bool | None


def touched_upper_flag(high: int | None, upper: int | None) -> bool | None:
    """鎖過 = 當日成交價曾觸及漲停價(`high >= upper`);任一缺 → None(不是 False:不知道)。"""
    return (high >= upper) if high is not None and upper is not None else None


def locked_up_flag(
    price: int | None, upper: int | None, asks: list[tuple[int, int]]
) -> bool | None:
    """當下鎖死 = 現價 = 漲停且限價賣側空(鎖停時 TC4 第一檔是市價佇列 0,不算限價 ——
    `_best_limit_price` 與訊號層 `_context` 同一把尺);價 / 漲停任一缺 → None。
    engine `policy_quotes`(同伴)與 hub `_emit_policies`(自己)共用這一份定義(review F-03)。"""
    if price is None or upper is None:
        return None
    return price == upper and _best_limit_price(asks) is None


@dataclass(frozen=True)
class PolicyContext:
    """一顆掃單簇事件的族群脈絡(直接對應政策列的欄位)。"""

    groups: list[str]
    screen_member: bool
    peers: list[dict[str, Any]]  # [{code, name, chg_pct, touched_upper, locked_up}] 含無報價者
    peers_up: int
    peer_max: dict[str, Any] | None  # {code, name, chg_pct} | None
    leader: bool
    peer_touched: bool
    hits: list[str]  # ⊆ POLICIES,固定序


def resolve_groups(
    code: str,
    groups: list[Group],
    *,
    screen_group: str,
    exclude: tuple[str, ...],
) -> tuple[list[str], list[str], bool]:
    """回 (族群組名清單, 同伴清單(聯集保序去重、扣自己), 是否盤前篩選成員)。"""
    names: list[str] = []
    peers: list[str] = []
    screen_member = False
    for g in groups:
        if code not in g["codes"]:
            continue
        name = g["name"]
        if name == screen_group:
            screen_member = True
            continue
        if name in exclude:
            continue
        names.append(name)
        for member in g["codes"]:
            if member != code and member not in peers:
                peers.append(member)
    return names, peers, screen_member


def evaluate_policies(
    *,
    chg: float,
    group_names: list[str],
    peer_codes: list[str],
    screen_member: bool,
    quotes: dict[str, PeerQuote],
    peer_up_pct: float,
    max_chg_pct: float,
) -> PolicyContext:
    """四條政策的命中判斷(呼叫端已保證參考價可得、價 > 0)。"""
    peers: list[dict[str, Any]] = []
    quoted: list[tuple[str, str, float]] = []
    peer_touched = False
    for peer in peer_codes:
        q: dict[str, Any] = dict(quotes.get(peer) or {})
        raw_chg = q.get("chg_pct")
        peer_chg = float(raw_chg) if isinstance(raw_chg, (int, float)) else None
        touched = q.get("touched_upper")
        name = str(q.get("name") or "")
        peers.append(
            {
                "code": peer,
                "name": name,
                "chg_pct": peer_chg,
                "touched_upper": touched if isinstance(touched, bool) else None,
                "locked_up": q.get("locked_up") if isinstance(q.get("locked_up"), bool) else None,
            }
        )
        if peer_chg is not None:
            quoted.append((peer, name, peer_chg))
        if touched is True:
            peer_touched = True
    peers_up = sum(1 for _c, _n, c in quoted if c >= peer_up_pct)
    peer_max: dict[str, Any] | None = None
    if quoted:
        best = max(quoted, key=lambda item: item[2])
        peer_max = {"code": best[0], "name": best[1], "chg_pct": best[2]}
    leader = peer_max is not None and chg >= float(peer_max["chg_pct"])
    under_cap = chg < max_chg_pct
    hits: list[str] = []
    if quoted and not peer_touched:
        if peers_up == 0 and under_cap:
            hits.append("P")
        if leader and peers_up >= 1 and under_cap:
            hits.append("B-a")
        if leader and peers_up >= 1:
            hits.append("B-b")
    if screen_member and under_cap:
        hits.append("S")
    return PolicyContext(
        groups=list(group_names),
        screen_member=screen_member,
        peers=peers,
        peers_up=peers_up,
        peer_max=peer_max,
        leader=leader,
        peer_touched=peer_touched,
        hits=hits,
    )


def tod_bucket(secs: float) -> str:
    """研究五桶(自午夜秒數):< 09:10 → 0900、< 09:30 → 0910、< 10:30 → 0930、< 12:00 → 1030、其餘 1200。"""
    if secs < 9 * 3600 + 10 * 60:
        return "0900"
    if secs < 9 * 3600 + 30 * 60:
        return "0910"
    if secs < 10 * 3600 + 30 * 60:
        return "0930"
    if secs < 12 * 3600:
        return "1030"
    return "1200"
