"""簿重播引擎(spec #265 / ticket #267):tick 存檔的成交列 + 簿列照訊息序號重播成每則的五檔。

CONTEXT.md「簿重播」:與分點指紋的引擎回放(`copycat.replay`)是兩件事,不共用程式碼。
零 IO —— 讀檔(`ticks.load_day`)與寫檔在 CLI `book-replay`。

**一則** = 一列 tick 存檔(成交列或簿列),依 `msg_seq` 排;每列自帶完整五檔(成交列是成交後簿),
所以第 i 則的簿就是那一列的 20 格,不需要跨列累積。

**時間軸**:顯示時間 = 最近一個**時鐘點**的達錢時刻,簿列讀作「該時刻之後第 N 則」(`Frame.after`)。
時鐘點 = 成交列,且 (a) 不早於目前時鐘(時間軸不倒退)、(b) 達錢時刻不晚於 server 收到時刻超過
`CLOCK_FUTURE_TOLERANCE_MS`(收不到未來)。**不用 `recv_ns` 排序或當軸**:它比達錢時刻晚中位
614 ms 但單筆 p90 約 1 秒,會把簿變動排到觸發它的成交之前。2026-09-16 實錄三種時刻:13:30:00.000
收盤撮合晚到 5–40 秒(真時刻,推進);7772 緩撮成交晚到 118 秒(真時刻,推進);1815 開機 07:31
收到前一日 14:30 的盤後成交(未來,不推進)。不推進的成交仍是一則,只是 `after` 照數。

**外掛檔 v1**(`encode` → `plugin_js`;每檔每日一檔,回看頁 `<script src>` 懶載入):
全文一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`,JSON 物件鍵:

- `v`:1;`code`、`date`(YYYY-MM-DD);`n`:則數;`fields`:五檔 20 格欄序(= `BOOK_LEVEL_FIELDS`)
- `seq`:訊息序號,首項絕對值、其後逐則差值
- `kind`:長 n 的字串,`t` 成交 / `b` 簿
- `clock`:時鐘點攤平成 `[則號, 當日毫秒, 則號, 當日毫秒, …]`(則號遞增、毫秒不減);第 i 則的顯示時間 =
  則號 ≤ i 的最後一個點,`after` = i − 該則號;沒有這樣的點 = 首筆成交前,`after` = i + 1
- `kf`:第 0、K、2K… 則的完整 20 格(K = `kf_every`,個數 = ceil(n / K))
- `d`:長 n,第 i 則相對第 i−1 則變了的格,攤平成 `[欄號, 新值, 欄號, 新值, …]`(第 −1 則視為 20 格全 null)

值:價毫元、量張的整數;null = 該層不存在;價 0 = 鎖停的市價單佇列(0 與 null 不可混)。
解碼:逐則播放 = 從前一則套 `d[i]`;跳到第 i 則 = 取 `kf[i // K]` 再套 `d[i//K*K + 1 .. i]`(`book_at`)。
兩條路在每個 keyframe 必須逐格相等 —— `decode` 對每個 keyframe 做這個自檢。
"""

from __future__ import annotations

import base64
import datetime as _dt
import gzip
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from operator import attrgetter
from typing import Any

from copycat.ticks import BOOK_FIELDS, DEPTH, TickRow

__all__ = [
    "BOOK_LEVEL_FIELDS",
    "CLOCK_FUTURE_TOLERANCE_MS",
    "FORMAT_VERSION",
    "KEYFRAME_EVERY",
    "CodeReplay",
    "Frame",
    "ReplayFormatError",
    "book_at",
    "decode",
    "encode",
    "parse_plugin_js",
    "plugin_js",
    "replay",
]

_TAIPEI = _dt.timezone(_dt.timedelta(hours=8))

#: 外掛檔呼叫的全域函式(回看頁定義;逐筆外掛檔是 `window.__tk`,兩者分開)
_PLUGIN_CALLBACK = "window.__bk"
_PLUGIN_LINE = re.compile(r'window\.__bk\("(?P<key>[^"\\]*)","(?P<blob>[A-Za-z0-9+/=]*)"\);')

#: 外掛檔格式版本;改格式 = +1(回看頁依它選解碼規則)
FORMAT_VERSION = 1

#: 每幾則放一個完整五檔(keyframe);回看頁跳到任一則最多套這麼多則 delta
KEYFRAME_EVERY = 256

#: 成交的達錢時刻最多能比 server 收到時刻「晚」多少還算真成交。正常是早 ~0.6 秒;本機鐘落後
#: (#236 時鐘偏差,實務秒級)會讓它看起來晚幾秒。超過 = 不可能收得到的未來時刻,例如開機時
#: 收到前一日的盤後成交(2026-09-16 1815:07:31 收到、蓋 14:30),不讓它推進時間軸。
CLOCK_FUTURE_TOLERANCE_MS = 60_000

#: 一則五檔的 20 格欄序(= tick 存檔欄名):買價 0–4、買量 0–4、賣價 0–4、賣量 0–4。
#: 價為毫元、量為張;None = 該層不存在;價 0 = 鎖停時的市價單佇列(真資料,原樣保留)。
BOOK_LEVEL_FIELDS: tuple[str, ...] = BOOK_FIELDS[BOOK_FIELDS.index("bid0") :]
assert len(BOOK_LEVEL_FIELDS) == 4 * DEPTH

_book_of = attrgetter(*BOOK_LEVEL_FIELDS)


class ReplayFormatError(ValueError):
    """外掛檔解不回原樣:版本不認得,或 delta 與 keyframe 對不上(編碼器壞了)。"""


@dataclass(frozen=True, slots=True)
class Frame:
    """重播的一則 = 一列 tick 存檔當下的五檔 + 它在時間軸上的位置。"""

    msg_seq: int
    kind: str  # "trade" | "book"
    book: tuple[int | None, ...]  # 20 格,欄序見 BOOK_LEVEL_FIELDS
    clock_ms: int | None  # 最近一個時鐘點的達錢時刻(台北當日毫秒);None = 首筆成交前
    after: int  # 距該時鐘點第幾則(時鐘點本身 0;首筆成交前自第 1 則數起)


@dataclass(frozen=True, slots=True)
class CodeReplay:
    """一檔一日的重播:`frames` 依訊息序號遞增。"""

    code: str
    trade_date: str
    frames: tuple[Frame, ...]


def replay(rows: Iterable[TickRow]) -> dict[str, CodeReplay]:
    """一天的 tick 存檔列(任意順序、多檔交錯)→ 每檔的重播,鍵 = 代號。

    一次只重播一個交易日:混到別天的列 → ValueError(時間軸以交易日換算,混日算不出對的時刻)。
    """
    by_code: dict[str, list[TickRow]] = defaultdict(list)
    trade_date: str | None = None
    for row in rows:
        if trade_date is None:
            trade_date = row.trade_date
        elif row.trade_date != trade_date:
            raise ValueError(
                f"一次只重播一個交易日:{trade_date} 與 {row.trade_date} 混在一起"
                f"({row.code} msg_seq={row.msg_seq})"
            )
        by_code[row.code].append(row)
    out: dict[str, CodeReplay] = {}
    for code, code_rows in by_code.items():
        code_rows.sort(key=attrgetter("msg_seq"))
        out[code] = CodeReplay(code, code_rows[0].trade_date, _frames(code_rows))
    return out


def _frames(rows: list[TickRow]) -> tuple[Frame, ...]:
    frames: list[Frame] = []
    clock: int | None = None
    clock_index = -1
    day_start_ms = _taipei_day_start_epoch_ms(rows[0].trade_date)
    for i, row in enumerate(rows):
        if _is_clock_point(row, clock, day_start_ms):
            assert row.ms is not None
            clock, clock_index = row.ms, i
        frames.append(Frame(row.msg_seq, row.kind, _book_of(row), clock, i - clock_index))
    return tuple(frames)


def _is_clock_point(row: TickRow, clock: int | None, day_start_ms: int) -> bool:
    """成交列推進時間軸的條件:有達錢時刻、不早於目前時鐘、不晚於收到時刻超過容差。"""
    if row.kind != "trade" or row.ms is None:
        return False
    if clock is not None and row.ms < clock:
        return False  # 時間軸不倒退
    return day_start_ms + row.ms <= row.recv_ns // 1_000_000 + CLOCK_FUTURE_TOLERANCE_MS


def _taipei_day_start_epoch_ms(trade_date: str) -> int:
    start = _dt.datetime.fromisoformat(trade_date).replace(tzinfo=_TAIPEI)
    return int(start.timestamp()) * 1000


def encode(day: CodeReplay, *, keyframe_every: int = KEYFRAME_EVERY) -> dict[str, Any]:
    """一檔一日的重播 → 外掛檔 payload(可直接 JSON 化)。格式見模組說明「外掛檔 v1」。"""
    seq: list[int] = []
    kinds: list[str] = []
    clock: list[int] = []
    keyframes: list[list[int | None]] = []
    deltas: list[list[int | None]] = []
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    prev_seq = 0
    for i, frame in enumerate(day.frames):
        seq.append(frame.msg_seq - prev_seq)
        prev_seq = frame.msg_seq
        kinds.append("t" if frame.kind == "trade" else "b")
        if frame.after == 0:
            assert frame.clock_ms is not None
            clock += [i, frame.clock_ms]
        delta: list[int | None] = []
        for field, value in enumerate(frame.book):
            if value != state[field]:
                delta += [field, value]
        deltas.append(delta)
        state = list(frame.book)
        if i % keyframe_every == 0:
            keyframes.append(list(frame.book))
    return {
        "v": FORMAT_VERSION,
        "code": day.code,
        "date": day.trade_date,
        "n": len(day.frames),
        "fields": list(BOOK_LEVEL_FIELDS),
        "kf_every": keyframe_every,
        "seq": seq,
        "kind": "".join(kinds),
        "clock": clock,
        "kf": keyframes,
        "d": deltas,
    }


def plugin_js(payload: Mapping[str, Any]) -> str:
    """payload → 外掛檔全文:一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`。

    gzip `mtime=0`:同一份資料重產出逐位元組相同的檔(重跑 CLI 不製造無意義差異)。
    """
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    blob = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")
    key = json.dumps(f"{payload['code']}|{payload['date']}")
    return f'{_PLUGIN_CALLBACK}({key},"{blob}");'


def parse_plugin_js(text: str) -> dict[str, Any]:
    """外掛檔全文 → payload(`plugin_js` 的反函數)。形狀不對 → ValueError。"""
    match = _PLUGIN_LINE.fullmatch(text.strip())
    if match is None:
        raise ValueError("不是簿重播外掛檔(找不到 window.__bk(...) 一行)")
    return json.loads(gzip.decompress(base64.b64decode(match["blob"], validate=True)))


def book_at(payload: Mapping[str, Any], index: int) -> tuple[int | None, ...]:
    """第 `index` 則的五檔,走回看頁跳轉的規則:該則之前最近的 keyframe + 其後到該則的 delta。"""
    every = payload["kf_every"]
    base = (index // every) * every
    state = list(payload["kf"][index // every])
    for delta in payload["d"][base + 1 : index + 1]:
        for k in range(0, len(delta), 2):
            state[delta[k]] = delta[k + 1]
    return tuple(state)


def decode(payload: Mapping[str, Any]) -> CodeReplay:
    """外掛檔 payload → 重播(`encode` 的反函數;回看頁解碼規則的 Python 版)。

    自檢:逐則套 delta 到每個 keyframe 位置都必須與 keyframe 逐格相等 —— 回看頁「播放」走 delta、
    「跳轉」走 keyframe,兩條路對不上 = 同一刻兩份簿。不相等 / 版本不認得 → ReplayFormatError。
    """
    if payload.get("v") != FORMAT_VERSION:
        raise ReplayFormatError(f"外掛檔版本 {payload.get('v')!r} 不認得(本版解 {FORMAT_VERSION})")
    code, n, every, keyframes = payload["code"], payload["n"], payload["kf_every"], payload["kf"]
    if list(payload["fields"]) != list(BOOK_LEVEL_FIELDS):
        raise ReplayFormatError(f"{code} 五檔欄序與本版不同:{payload['fields']}")
    lengths = (len(payload["seq"]), len(payload["kind"]), len(payload["d"]))
    if lengths != (n, n, n):
        raise ReplayFormatError(f"{code} 檔頭 n={n} 與 seq / kind / d 長度 {lengths} 不符")
    if len(keyframes) != -(-n // every):
        raise ReplayFormatError(
            f"{code} keyframe 個數 {len(keyframes)} 不符(n={n}、每 {every} 則一個)"
        )
    points = iter(zip(payload["clock"][::2], payload["clock"][1::2], strict=True))
    next_point = next(points, None)
    clock: int | None = None
    clock_index = -1
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    frames: list[Frame] = []
    msg_seq = 0
    for i, (seq_step, kind, delta) in enumerate(
        zip(payload["seq"], payload["kind"], payload["d"], strict=True)
    ):
        msg_seq += seq_step
        for k in range(0, len(delta), 2):
            state[delta[k]] = delta[k + 1]
        if i % every == 0 and state != keyframes[i // every]:
            raise ReplayFormatError(
                f"{code} 第 {i} 則:delta 累積結果與 keyframe 不符"
                f"({state} ≠ {keyframes[i // every]})"
            )
        if next_point is not None and next_point[0] == i:
            clock, clock_index = next_point[1], i
            next_point = next(points, None)
        frames.append(
            Frame(msg_seq, "trade" if kind == "t" else "book", tuple(state), clock, i - clock_index)
        )
    return CodeReplay(code, payload["date"], tuple(frames))
