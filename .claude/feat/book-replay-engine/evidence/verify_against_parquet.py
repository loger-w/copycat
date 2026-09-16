"""#267 抽樣驗證:外掛檔解回來的每一則 vs 直讀當日 parquet 的同一則(不經引擎、不經 load_day)。

用法(worktree 根目錄):
    python .claude/feat/book-replay-engine/evidence/verify_against_parquet.py <外掛檔日期目錄> <tick 存檔目錄>

三層:
(a) 全量:每檔 `decode` 的每一則 —— msg_seq / 種類 / 五檔 20 格 / 收到時刻軸(parquet recv_ns 自算、
    不倒退)/ 成交則的 [達錢時刻, 價, 張, 內外盤] —— 對 parquet 依 msg_seq 排序後的每一列;
(b) 跳轉規則:`book_at` 在 keyframe 前後(kK−1 / kK / kK+1)、首尾與隨機 200 則;
(c) 指名時刻:spec #265 的驗收素材,時刻 T(收到時刻軸)→ 收到時刻 ≤ T 的最後一則。
"""

from __future__ import annotations

import datetime as _dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # worktree 根:別 import 到主 tree

import pyarrow.compute as pc  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from copycat.book_replay import BOOK_LEVEL_FIELDS, book_at, decode, parse_plugin_js  # noqa: E402

LEVELS = list(BOOK_LEVEL_FIELDS)
TRADE_COLS = ["ms", "price_milli", "qty", "side"]


def hms(ms: int | None) -> str:
    if ms is None:
        return "首筆成交前"
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def to_ms(text: str) -> int:
    hh, mm, rest = text.split(":")
    ss, _, frac = rest.partition(".")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int((frac + "000")[:3])


def ladder(book: tuple[int | None, ...]) -> str:
    bids = [f"{book[i] / 1000:g}×{book[5 + i]}" for i in range(5) if book[i] is not None]  # type: ignore[operator]
    asks = [f"{book[10 + i] / 1000:g}×{book[15 + i]}" for i in range(5) if book[10 + i] is not None]  # type: ignore[operator]
    return f"買 [{', '.join(bids) or '空'}] | 賣 [{', '.join(asks) or '空'}]"


def main(plugin_dir: Path, ticks_dir: Path) -> int:
    day = plugin_dir.name
    tz = _dt.timezone(_dt.timedelta(hours=8))
    day_start = int(_dt.datetime.fromisoformat(day).replace(tzinfo=tz).timestamp()) * 1000
    stem = day.replace("-", "")
    base = ["code", "msg_seq", "recv_ns", *LEVELS]
    tables = {
        "t": pq.read_table(ticks_dir / f"{stem}.parquet", columns=[*base, *TRADE_COLS]),
        "b": pq.read_table(ticks_dir / f"{stem}-book.parquet", columns=base),
    }
    rng = random.Random(267)
    files = sorted(plugin_dir.glob("*.js"))
    full_rows = full_bad = jump_checked = jump_bad = 0
    decoded: dict[str, tuple[dict, list]] = {}
    for f in files:
        code = f.stem
        payload = parse_plugin_js(f.read_text(encoding="utf-8"))
        replay = decode(payload)
        rows: list[tuple] = []
        for kind, table in tables.items():
            sub = table.filter(pc.equal(table["code"], code))  # type: ignore[attr-defined]
            cols = {c: sub[c].to_pylist() for c in sub.column_names}
            for i in range(sub.num_rows):
                book = tuple(cols[c][i] for c in LEVELS)
                trade = tuple(cols[c][i] for c in TRADE_COLS) if kind == "t" else None
                rows.append((cols["msg_seq"][i], kind, book, cols["recv_ns"][i], trade))
        rows.sort(key=lambda r: r[0])
        truth = []
        axis = None
        for seq, kind, book, recv_ns, trade in rows:
            recv = recv_ns // 1_000_000 - day_start
            axis = recv if axis is None else max(axis, recv)
            truth.append((seq, kind, book, axis, trade))
        full_rows += len(truth)
        got = [
            (
                fr.msg_seq,
                "t" if fr.kind == "trade" else "b",
                fr.book,
                fr.recv_ms,
                None if fr.trade is None else (fr.trade.ms, fr.trade.price_milli, fr.trade.qty, fr.trade.side),
            )
            for fr in replay.frames
        ]
        if got != truth:
            full_bad += 1
            first = next(i for i, (a, b) in enumerate(zip(got, truth)) if a != b)
            print(f"(a) {code} 不符:frames {len(got)} vs parquet {len(truth)},第一個不符在第 {first} 則")
        n, every = payload["n"], payload["kf_every"]
        picks = {0, n - 1, *rng.sample(range(n), min(200, n))}
        for k in range(1, (n - 1) // every + 1):
            picks |= {k * every - 1, k * every, min(k * every + 1, n - 1)}
        for i in sorted(picks):
            jump_checked += 1
            if book_at(payload, i) != truth[i][2]:
                jump_bad += 1
                print(f"(b) {code} 第 {i} 則 book_at 不符")
        decoded[code] = (payload, truth)
    print(f"(a) 全量:{len(files)} 檔、{full_rows} 則(五檔 + 收到時刻軸 + 成交欄位),不符 {full_bad} 檔")
    print(f"(b) 跳轉規則(keyframe 前後 / 首尾 / 隨機):{jump_checked} 則,不符 {jump_bad} 則")

    moments = [
        ("2426", "11:02:43.500"),
        ("2426", "11:02:45.700"),
        ("3441", "09:04:42.500"),
        ("2305", "09:07:47.500"),
        ("3441", "09:09:01.500"),
    ]
    for code, at in moments:
        payload, truth = decoded[code]
        target = to_ms(at)
        recv_axis = [t[3] for t in truth]
        i = max(idx for idx, v in enumerate(recv_axis) if v <= target)
        points = list(zip(payload["clock"][::2], payload["clock"][1::2], strict=True))
        clock_idx, clock_ms = max(((idx, ms) for idx, ms in points if idx <= i), default=(-1, None))
        last_trade = next((truth[j][4] for j in range(i, -1, -1) if truth[j][4] is not None), None)
        price = "—" if last_trade is None else f"{last_trade[1] / 1000:g}"
        book = book_at(payload, i)
        same = "逐格相等" if book == truth[i][2] else "不符"
        print(
            f"(c) {code} 拖到 {at} → 第 {i} 則 msg_seq={truth[i][0]} 收到 {hms(truth[i][3])}"
            f"(成交 {hms(clock_ms)} 之後第 {i - clock_idx} 則)現價 {price}:{ladder(book)} —— parquet 同一則 {same}"
        )
    return 0 if full_bad == 0 and jump_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
