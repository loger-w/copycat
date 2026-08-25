"""相關係數引擎的腿設定(SC-8;design §4)。

商品清單一律走設定檔,引擎程式碼內不得出現任何 TC4 symbol 字面值 —— 日後 TC4 上架
新商品(例如 CME single stock futures 的 TSM ADR,2026-07-27 上市但 TC4 尚未上架)
只需在 `configs/correlation.json` 加一筆。

`base` 腿的 `source` 必須是 `"futures_engine"`:台指 `TC.F.TWF.TXF.HOT` 已被既有
`futures_engine` 訂閱,本引擎不重複訂閱同一個 symbol。**理由不是「跨 session 只推一邊」**
(那是 07-28 的錯誤結論,08-18 已推翻):REALTIME 是單一 PUB port 廣播,人人收得到;真正的
風險是 TC4 的 refcount 以 `symbol|DataType|窗` 為 key 計、上游 feed 卻以 **symbol** 為單位
—— 多一把 key 就多一個「它歸零時把整個 symbol 的 feed 一起退掉」的引信(死掉沒 LOGOUT 的
session 被 reap 時尤其明顯),而失效樣態是永久零推播且無錯誤訊號。詳見
`.claude/skills/tc4-market-facts/SKILL.md`。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_CONFIG", "CONFIG_PATH", "CorrConfig", "Leg", "load_config"]

SOURCE_TC4 = "tc4"
SOURCE_FUTURES_ENGINE = "futures_engine"
_LEG_FIELDS = ("key", "label", "symbol", "source")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "correlation.json"


@dataclass(frozen=True)
class Leg:
    key: str
    label: str  # 前端顯示用繁中名(後端帶,前端不寫死對照表)
    symbol: str
    source: str  # SOURCE_TC4 = 本引擎訂閱 / SOURCE_FUTURES_ENGINE = 讀既有引擎狀態


@dataclass(frozen=True)
class CorrConfig:
    legs: tuple[Leg, ...]
    base: str
    windows: tuple[int, ...] = (60, 300, 1800)
    # per-window 門檻:共用單一值會讓 1800 秒窗剛重置後僅憑 30 筆就出數字(design review P1-1)
    min_samples: dict[int, int] = field(
        default_factory=lambda: {60: 30, 300: 100, 1800: 300}
    )
    stale_secs: float = 30.0

    def tc4_legs(self) -> tuple[Leg, ...]:
        """本引擎需自行 SUBQUOTE 的腿(排除 base — 那條讀 futures_engine)。"""
        return tuple(leg for leg in self.legs if leg.source == SOURCE_TC4)


DEFAULT_CONFIG = CorrConfig(
    legs=(
        Leg("TXF", "台指", "TC.F.TWF.TXF.HOT", SOURCE_FUTURES_ENGINE),
        Leg("TWN", "富台", "TC.F.SGX.TWN.HOT", SOURCE_TC4),
        Leg("YM", "道瓊", "TC.F.CBOT.YM.HOT", SOURCE_TC4),
        Leg("ES", "標普", "TC.F.CME.ES.HOT", SOURCE_TC4),
        Leg("NQ", "納指", "TC.F.CME.NQ.HOT", SOURCE_TC4),
        Leg("SXF", "費半", "TC.F.TWF.SXF.HOT", SOURCE_TC4),
        # 第七腿(2026-08-17 R5 上線,N021 於 2026-08-25 補進預設):`configs/correlation.json`
        # 早就有它,預設卻沒有 —— 設定檔壞掉退回這裡時,江波圖 / 相關係數會**真的少一腿**,
        # 而畫面上只是少一條線,零錯誤訊號。預設必須與 repo 真檔逐腿相同。
        Leg("NK225M", "小日經", "TC.F.OSE.NK225M.HOT", SOURCE_TC4),
        # 第 8–11 腿(2026-08-26 F4;`spikes/corr_legs_probe.py` 01:02 實測:VX 45 s 推 19 則、
        # CL 163、GC 172,1K 首頁各 50 列)。VIX 用標準 VX 不用 VXM(45 s 零推播、1K 零列);
        # 原油 / 黃金用標準 CL / GC 不用微型 MCL / MGC(相關係數看價格方向,標準合約流動性更高)。
        Leg("VX", "VIX", "TC.F.CFE.VX.HOT", SOURCE_TC4),
        Leg("CL", "原油", "TC.F.CME.CL.HOT", SOURCE_TC4),
        Leg("GC", "黃金", "TC.F.CME.GC.HOT", SOURCE_TC4),
        # 台積電走**現貨**不走個股期 CDF:CDF 的 `TC.F.TWF.` 前綴會吃台期交日夜盤閘,而現貨
        # 13:30 收盤、無夜盤,不是同一把尺。現貨段自己的閘見 `corr_source.segment_leg_gate`。
        # 台幣匯率**不加**:全樹掃 TWD / TW* 只命中 SGX 富台(既有腿)—— 達錢 4 現貨段只有
        # TWS、CME 與台期交的匯率期貨都沒有 TWD。
        Leg("TSMC", "台積電", "TC.S.TWS.2330", SOURCE_TC4),
    ),
    base="TXF",
)


def _parse_legs(raw: object) -> tuple[Leg, ...] | None:
    """未知欄位一律忽略(`_comment` 說明欄不得觸發降級);必要欄缺一 → None。"""
    if not isinstance(raw, list) or not raw:
        return None
    legs: list[Leg] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        if any(field not in item for field in _LEG_FIELDS):
            return None
        legs.append(Leg(*(str(item[field]) for field in _LEG_FIELDS)))
    return tuple(legs)


def load_config(path: Path | None = None) -> CorrConfig:
    """讀設定檔;不存在 / 壞格式 / base 不在 legs → 記 warning 後回 DEFAULT_CONFIG。

    never-raise(沿用 notify.py 慣例):設定檔壞掉不該讓整個 server 起不來,
    降級成預設腿組仍是可用狀態。
    """
    target = CONFIG_PATH if path is None else path
    if not target.exists():
        return DEFAULT_CONFIG
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("corr 設定檔讀取失敗,改用預設腿:%s", exc)
        return DEFAULT_CONFIG
    if not isinstance(raw, dict):
        logger.warning("corr 設定檔頂層非 object,改用預設腿")
        return DEFAULT_CONFIG
    legs = _parse_legs(raw.get("legs"))
    if legs is None:
        logger.warning("corr 設定檔 legs 欄格式錯誤,改用預設腿")
        return DEFAULT_CONFIG
    base = str(raw.get("base", DEFAULT_CONFIG.base))
    if base not in {leg.key for leg in legs}:
        logger.warning("corr 設定檔 base=%s 不在 legs 內,改用預設腿", base)
        return DEFAULT_CONFIG
    return CorrConfig(legs=legs, base=base)
