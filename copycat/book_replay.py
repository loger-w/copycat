"""簿重播引擎(spec #265 / ticket #267):tick 存檔的成交列 + 簿列照訊息序號重播成每則的五檔。

CONTEXT.md「簿重播」:與分點指紋的引擎回放(`copycat.replay`)是兩件事,不共用程式碼。
零 IO —— 讀檔(`ticks.load_day`)與寫檔在 CLI `book-replay`。

**一則** = 一列 tick 存檔(成交列或簿列),依 `msg_seq` 排;每列自帶完整五檔(成交列是成交後簿),
所以第 i 則的簿就是那一列的 20 格,不需要跨列累積。

**排序** 只看 `msg_seq`(server 收到的全域順序,因果不會反)。

**時間軸(拖曳 / 十字線 / 對齊委託)= server 收到時刻** `Frame.recv_ms`(交易日台北零點起毫秒;本機鐘被
校時往回撥時沿用前一則,不倒退)。2026-09-16 實測:達錢**即時**個股成交時刻只到整秒(37.5 萬筆次秒
全 0),收到時刻比它晚 81–1,137 ms 且各 100 ms 桶近乎均勻 = 整秒截斷 + 約 0.1 秒延遲 —— 收到時刻本身
很穩(前提是本機鐘準;#236 時鐘偏差 WARNING 出現時軸整段跟著偏,與同一把本機鐘的群益審計時刻仍對得齊);
反過來拿整秒的達錢時刻當軸,2426「11:02:43」一格底下就有 51 則(user 2026-09-16 拍板改軸)。

**文字標籤 = 交易所的尺**:最近一個**時鐘點**的達錢時刻,簿列讀作「該時刻之後第 N 則」(`Frame.after`)。
時鐘點 = 成交列,且 (a) 不早於目前時鐘(不倒退)、(b) 達錢時刻不晚於收到時刻超過
`CLOCK_FUTURE_TOLERANCE_MS`(收不到未來)。2026-09-16 實錄三種時刻:13:30:00.000 收盤撮合晚到
5–40 秒(真時刻,當時鐘點);7772 緩撮成交晚到 118 秒(真時刻,當時鐘點);1815 開機 07:31 收到前一日
14:30 的盤後成交(未來,不當時鐘點)。不當時鐘點的成交仍是一則,`after` 照數,計入 `BookReplay.anomalous_trades`。

**外掛檔 v1**(`encode` → `plugin_js`;每檔每日一檔,回看頁 `<script src>` 懶載入):
全文一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`,JSON 物件鍵:

- `v`:1;`code`、`date`(YYYY-MM-DD);`n`:則數;`fields`:五檔 20 格欄序(= `BOOK_LEVEL_FIELDS`)
- `seq`:訊息序號,首項絕對值、其後逐則差值
- `kind`:長 n 的字串,`t` 成交 / `b` 簿
- `recv`:長 n,收到時刻(交易日台北零點起毫秒),首項絕對值、其後逐則差值(恆 ≥ 0)
- `clock`:時鐘點攤平成 `[則號, 當日毫秒, 則號, 當日毫秒, …]`(則號遞增、毫秒不減);第 i 則的標籤時刻 =
  則號 ≤ i 的最後一個點,`after` = i − 該則號;沒有這樣的點 = 首筆成交前,`after` = i + 1
- `trade`:每個成交則依序 4 格攤平 `[達錢成交時刻毫秒, 價, 張, 內外盤]`(時刻 = 存檔 `ms` 原值),內外盤為
  `"inner"` / `"outer"` / `"neutral"`;長度 = 4 × `kind` 裡 `t` 的個數,簿則不佔位。**成交則的則號不在
  `clock` 裡 = 達錢時刻異常**(`BookReplay.anomalous_trades`),它的時刻照原值保留、不一定是當日(1815 那則是前一日 14:30)
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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields  # `fields` 會跟 payload 的 fields 鍵混淆
from operator import attrgetter
from typing import Any, TypedDict

from copycat.ticks import BOOK_FIELDS, DEPTH, TickRow

__all__ = [
    "BOOK_LEVEL_FIELDS",
    "CLOCK_FUTURE_TOLERANCE_MS",
    "FORMAT_VERSION",
    "KEYFRAME_EVERY",
    "BookReplay",
    "Frame",
    "PluginFormatError",
    "PluginPayload",
    "Trade",
    "book_at",
    "decode",
    "encode",
    "parse_plugin_js",
    "plugin_js",
    "replay_books",
]

_TAIPEI = _dt.timezone(_dt.timedelta(hours=8))

#: 外掛檔呼叫的全域函式(回看頁定義;逐筆外掛檔是 `window.__tk`,兩者分開)
_PLUGIN_CALLBACK = "window.__bk"
_PLUGIN_LINE = re.compile(
    re.escape(_PLUGIN_CALLBACK) + r'\("(?P<key>[^"\\]*)","(?P<blob>[A-Za-z0-9+/=]*)"\);'
)

#: 外掛檔格式版本;改格式 = +1(回看頁依它選解碼規則)
FORMAT_VERSION = 1

#: 每幾則放一個完整五檔(keyframe);回看頁跳到任一則最多套這麼多則 delta
KEYFRAME_EVERY = 256

#: 成交的達錢時刻最多能比 server 收到時刻「晚」多少還算真成交。正常是早 ~0.6 秒;本機鐘落後
#: (#236 時鐘偏差,實務秒級)會讓它看起來晚幾秒。超過 = 不可能收得到的未來時刻,例如開機時
#: 收到前一日的盤後成交(2026-09-16 1815:07:31 收到、蓋 14:30),不讓它當時鐘點(文字標籤的時刻)。
CLOCK_FUTURE_TOLERANCE_MS = 60_000

#: 一則五檔的 20 格欄序(= tick 存檔欄名):買價 0–4、買量 0–4、賣價 0–4、賣量 0–4。
#: 價為毫元、量為張;None = 該層不存在;價 0 = 鎖停時的市價單佇列(真資料,原樣保留)。
BOOK_LEVEL_FIELDS: tuple[str, ...] = BOOK_FIELDS[BOOK_FIELDS.index("bid0") :]
assert len(BOOK_LEVEL_FIELDS) == 4 * DEPTH

_book_of: Callable[[TickRow], tuple[int | None, ...]] = attrgetter(*BOOK_LEVEL_FIELDS)


#: 一則的種類 ↔ 外掛檔 `kind` 字元(兩個方向同一張表)
_KIND_CODE: dict[str, str] = {"trade": "t", "book": "b"}
_KIND_NAME: dict[str, str] = {code: name for name, code in _KIND_CODE.items()}


class PluginFormatError(ValueError):
    """外掛檔解不回原樣:不是外掛檔、版本不認得、檔頭與內容不符,或 delta 與 keyframe 對不上。"""


@dataclass(frozen=True, slots=True)
class Trade:
    """成交則上的那一筆成交(tick 存檔成交列原值)。"""

    # 達錢成交時刻(台北 HH:MM:SS.fff 換毫秒,存檔原值;即時個股只到整秒;異常成交可能不是當日)
    ms: int | None
    price_milli: int | None
    qty: int | None  # 張
    side: str | None  # "inner" | "outer" | "neutral"(看盤引擎當時的判定)


#: 外掛檔 `trade` 每筆成交的格序 = `Trade` 欄序(encode 取值與 decode 建構同一個來源)
_TRADE_CELLS: tuple[str, ...] = tuple(f.name for f in dataclass_fields(Trade))
_trade_cells: Callable[[Trade], tuple[int | str | None, ...]] = attrgetter(*_TRADE_CELLS)


@dataclass(frozen=True, slots=True)
class Frame:
    """重播的一則 = 一列 tick 存檔當下的五檔 + 它在兩把時間尺上的位置(見模組說明)。"""

    msg_seq: int
    kind: str  # "trade" | "book"
    book: tuple[int | None, ...]  # 20 格,欄序見 BOOK_LEVEL_FIELDS
    clock_ms: int | None  # 最近一個時鐘點的達錢時刻(台北當日毫秒);None = 首筆成交前
    after: int  # 距該時鐘點第幾則(時鐘點本身 0;首筆成交前自第 1 則數起)
    recv_ms: int  # 時間軸位置 = server 收到時刻(交易日台北零點起毫秒);本機鐘回撥時沿用前一則
    trade: Trade | None  # 成交則的那筆成交;簿則 None


@dataclass(frozen=True, slots=True)
class BookReplay:
    """一檔一日的簿重播:`frames` 依訊息序號遞增。"""

    code: str
    trade_date: str
    frames: tuple[Frame, ...]

    @property
    def anomalous_trades(self) -> int:
        """達錢時刻異常、沒當成時鐘點的成交則數(晚於收到時刻超過容差,或早於目前時鐘)。"""
        return sum(1 for frame in self.frames if frame.kind == "trade" and frame.after)


class PluginPayload(TypedDict):
    """外掛檔 v1 的 JSON 物件;各鍵的意義見模組說明「外掛檔 v1」。"""

    v: int
    code: str
    date: str
    n: int
    fields: list[str]
    kf_every: int
    seq: list[int]
    kind: str
    clock: list[int]
    recv: list[int]
    trade: list[int | str | None]
    kf: list[list[int | None]]
    d: list[list[int | None]]


def replay_books(rows: Iterable[TickRow]) -> dict[str, BookReplay]:
    """一天的 tick 存檔列(任意順序、多檔交錯)→ 每檔的簿重播,鍵 = 代號。

    一次只重播一個交易日:混到別天的列 → ValueError(兩把時間尺都以交易日台北零點換算,混日算不出對的時刻)。
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
    out: dict[str, BookReplay] = {}
    for code, code_rows in by_code.items():
        code_rows.sort(key=attrgetter("msg_seq"))
        out[code] = BookReplay(code, code_rows[0].trade_date, _frames(code_rows))
    return out


def _frames(rows: list[TickRow]) -> tuple[Frame, ...]:
    frames: list[Frame] = []
    clock: int | None = None
    clock_index = -1
    day_start_ms = _taipei_day_start_epoch_ms(rows[0].trade_date)
    recv_ms = rows[0].recv_ns // 1_000_000 - day_start_ms
    for i, row in enumerate(rows):
        if _is_clock_point(row, clock, day_start_ms):
            assert row.ms is not None
            clock, clock_index = row.ms, i
        recv_ms = max(recv_ms, row.recv_ns // 1_000_000 - day_start_ms)
        trade = Trade(row.ms, row.price_milli, row.qty, row.side) if row.kind == "trade" else None
        frames.append(
            Frame(row.msg_seq, row.kind, _book_of(row), clock, i - clock_index, recv_ms, trade)
        )
    return tuple(frames)


def _is_clock_point(row: TickRow, clock: int | None, day_start_ms: int) -> bool:
    """成交列當時鐘點(文字標籤時刻)的條件:有達錢時刻、不早於目前時鐘、不晚於收到時刻超過容差。"""
    if row.kind != "trade" or row.ms is None:
        return False
    if clock is not None and row.ms < clock:
        return False  # 標籤時刻不倒退
    return day_start_ms + row.ms <= row.recv_ns // 1_000_000 + CLOCK_FUTURE_TOLERANCE_MS


def _taipei_day_start_epoch_ms(trade_date: str) -> int:
    start = _dt.datetime.fromisoformat(trade_date).replace(tzinfo=_TAIPEI)
    return int(start.timestamp()) * 1000


def encode(code_day: BookReplay, *, keyframe_every: int = KEYFRAME_EVERY) -> PluginPayload:
    """一檔一日的簿重播 → 外掛檔 payload(可直接 JSON 化)。格式見模組說明「外掛檔 v1」。"""
    seq: list[int] = []
    kinds: list[str] = []
    clock: list[int] = []
    recv: list[int] = []
    trades: list[int | str | None] = []
    keyframes: list[list[int | None]] = []
    deltas: list[list[int | None]] = []
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    prev_seq = prev_recv = 0
    for i, frame in enumerate(code_day.frames):
        seq.append(frame.msg_seq - prev_seq)
        prev_seq = frame.msg_seq
        recv.append(frame.recv_ms - prev_recv)
        prev_recv = frame.recv_ms
        kinds.append(_KIND_CODE[frame.kind])
        if frame.kind == "trade":
            assert frame.trade is not None, (
                f"{code_day.code} msg_seq={frame.msg_seq} 成交則沒帶成交"
            )
            trades += _trade_cells(frame.trade)
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
        "code": code_day.code,
        "date": code_day.trade_date,
        "n": len(code_day.frames),
        "fields": list(BOOK_LEVEL_FIELDS),
        "kf_every": keyframe_every,
        "seq": seq,
        "kind": "".join(kinds),
        "clock": clock,
        "recv": recv,
        "trade": trades,
        "kf": keyframes,
        "d": deltas,
    }


def plugin_js(payload: PluginPayload) -> str:
    """payload → 外掛檔全文:一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`。

    gzip `mtime=0`:同一份資料重產出逐位元組相同的檔(重跑 CLI 不製造無意義差異)。
    """
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    blob = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")
    key = json.dumps(f"{payload['code']}|{payload['date']}")
    return f'{_PLUGIN_CALLBACK}({key},"{blob}");'


def parse_plugin_js(text: str) -> PluginPayload:
    """外掛檔全文 → payload(`plugin_js` 的反函數)。不是一行 `window.__bk(...)` → PluginFormatError。"""
    match = _PLUGIN_LINE.fullmatch(text.strip())
    if match is None:
        raise PluginFormatError(f"不是簿重播外掛檔(找不到 {_PLUGIN_CALLBACK}(...) 一行)")
    payload: PluginPayload = json.loads(
        gzip.decompress(base64.b64decode(match["blob"], validate=True))
    )
    expected_key = f"{payload.get('code')}|{payload.get('date')}"
    if match["key"] != expected_key:
        # 回看頁以呼叫鍵配對懶載入的請求:鍵與內容不符 = 畫面掛到別檔別日的簿
        raise PluginFormatError(f"外掛檔呼叫鍵 {match['key']!r} 與內容 {expected_key!r} 不符")
    return payload


def book_at(payload: PluginPayload, index: int) -> tuple[int | None, ...]:
    """第 `index` 則的五檔,走回看頁跳轉的規則:該則之前最近的 keyframe + 其後到該則的 delta。"""
    every = payload["kf_every"]
    base = (index // every) * every
    state = list(payload["kf"][index // every])
    for delta in payload["d"][base + 1 : index + 1]:
        _apply_delta(state, delta)
    return tuple(state)


def _apply_delta(state: list[int | None], delta: Sequence[Any]) -> None:
    """`[欄號, 新值, 欄號, 新值, …]` 套到 20 格上(欄號與值混在同一串,所以收 Any)。"""
    for k in range(0, len(delta), 2):
        state[delta[k]] = delta[k + 1]


def decode(payload: PluginPayload) -> BookReplay:
    """外掛檔 payload → 簿重播(`encode` 的反函數;回看頁解碼規則的 Python 版)。

    自檢:逐則套 delta 到每個 keyframe 位置都必須與 keyframe 逐格相等 —— 回看頁「播放」走 delta、
    「跳轉」走 keyframe,兩條路對不上 = 同一刻兩份簿;收到時刻不得倒退。這些或檔頭不符 → PluginFormatError。
    """
    _check_header(payload)
    code, every, keyframes = payload["code"], payload["kf_every"], payload["kf"]
    trades = iter(zip(*[iter(payload["trade"])] * len(_TRADE_CELLS), strict=True))
    points = iter(zip(payload["clock"][::2], payload["clock"][1::2], strict=True))
    next_point = next(points, None)
    clock: int | None = None
    clock_index = -1
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    frames: list[Frame] = []
    msg_seq = recv_ms = 0
    for i, (seq_step, kind, recv_step, delta) in enumerate(
        zip(payload["seq"], payload["kind"], payload["recv"], payload["d"], strict=True)
    ):
        if recv_step < 0:
            raise PluginFormatError(f"{code} 第 {i} 則:收到時刻倒退 {recv_step} ms")
        msg_seq += seq_step
        recv_ms += recv_step
        _apply_delta(state, delta)
        if i % every == 0 and state != keyframes[i // every]:
            raise PluginFormatError(
                f"{code} 第 {i} 則:delta 累積結果與 keyframe 不符"
                f"({state} ≠ {keyframes[i // every]})"
            )
        if next_point is not None and next_point[0] == i:
            clock, clock_index = next_point[1], i
            next_point = next(points, None)
        kind_name = _KIND_NAME[kind]
        trade = Trade(*next(trades)) if kind_name == "trade" else None
        frames.append(
            Frame(msg_seq, kind_name, tuple(state), clock, i - clock_index, recv_ms, trade)
        )
    return BookReplay(code, payload["date"], tuple(frames))


def _check_header(payload: PluginPayload) -> None:
    """檔頭與內容的形狀一致(逐則的 keyframe 自檢與收到時刻不倒退在 `decode` 迴圈裡)。"""
    if payload.get("v") != FORMAT_VERSION:
        raise PluginFormatError(f"外掛檔版本 {payload.get('v')!r} 不認得(本版解 {FORMAT_VERSION})")
    missing = set(PluginPayload.__required_keys__) - set(payload)
    if missing:
        raise PluginFormatError(f"外掛檔缺鍵:{sorted(missing)}")
    code, n, every, kinds = payload["code"], payload["n"], payload["kf_every"], payload["kind"]
    if list(payload["fields"]) != list(BOOK_LEVEL_FIELDS):
        raise PluginFormatError(f"{code} 五檔欄序與本版不同:{payload['fields']}")
    lengths = tuple(len(payload[key]) for key in ("seq", "kind", "recv", "d"))
    if lengths != (n, n, n, n):
        raise PluginFormatError(f"{code} 檔頭 n={n} 與 seq / kind / recv / d 長度 {lengths} 不符")
    if len(payload["kf"]) != -(-n // every):
        raise PluginFormatError(
            f"{code} keyframe 個數 {len(payload['kf'])} 不符(n={n}、每 {every} 則一個)"
        )
    if not set(kinds) <= _KIND_NAME.keys():
        raise PluginFormatError(f"{code} kind 有不認得的字元:{set(kinds) - _KIND_NAME.keys()}")
    width, trade_count = len(_TRADE_CELLS), kinds.count(_KIND_CODE["trade"])
    if len(payload["trade"]) != width * trade_count:
        raise PluginFormatError(
            f"{code} trade 長度 {len(payload['trade'])} 不是成交則數 × {width}({trade_count} 則)"
        )
    clock_values = payload["clock"]
    if len(clock_values) % 2:
        raise PluginFormatError(f"{code} clock 長度 {len(clock_values)} 不是偶數")
    prev_index, prev_ms = -1, None
    for index, ms in zip(clock_values[::2], clock_values[1::2], strict=True):
        on_trade = prev_index < index < n and kinds[index] == _KIND_CODE["trade"]
        if not on_trade or (prev_ms is not None and ms < prev_ms):
            raise PluginFormatError(
                f"{code} 時鐘點 [{index}, {ms}] 不合法:則號須遞增且落在成交則、毫秒不減"
            )
        prev_index, prev_ms = index, ms
