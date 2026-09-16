"""pr-275 review 收修驗證(F-11 重做):CLI 產的外掛檔 vs 直讀 parquet,真值側不經引擎、不經 load_day、不經 decode。

用法(worktree 根目錄):
    python .claude/bug/pr-275-review-followups/evidence/verify_against_parquet.py <外掛檔日期目錄> <tick 存檔目錄>

與 #267 版(`.claude/feat/book-replay-engine/evidence/verify_against_parquet.py`,原樣保留)的差別 = review F-11 四點:
- 文字標籤獨立驗:真值側照模組說明「文字標籤」重算時鐘點(成交、有時刻、不早於目前標籤時刻、不晚於收到超過
  60 秒),比 decode 的 (clock_ms, after)、外掛檔 `anomalous` 原始清單、以及只照格式說明從原始 payload 推出的標籤
- 母體 = parquet 的代號集合,斷言與外掛檔集合相等(少產 / 多產一檔都報)
- 第一個不符用 `next(..., None)`,前綴關係時照樣印出差異
- 空簿計數由本腳本算出並印進輸出

五層:
(a) 全量:每檔每一則 msg_seq / 種類 / 五檔 20 格 / 收到時刻軸 / 成交欄 / 文字標籤
(b) 代號集合 parquet = 外掛檔
(c) 跳轉規則:`book_at` 在 keyframe 前後(kK−1 / kK / kK+1)、首尾與隨機 200 則
(d) 指名時刻:收到時刻 ≤ T 的最後一則,標籤以真值側重算
(e) 空簿計數:賣方全空 / 買方全空 / 兩邊全空
"""

from __future__ import annotations

import datetime as _dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # worktree 根:別 import 到主 tree

import pyarrow as pa  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from copycat.book_replay import BOOK_LEVEL_FIELDS, book_at, decode, parse_plugin_js  # noqa: E402

LEVELS = list(BOOK_LEVEL_FIELDS)
TRADE_COLS = ["ms", "price_milli", "qty", "side"]
TOLERANCE_MS = 60_000  # 模組說明「文字標籤」:達錢時刻不晚於收到時刻超過這麼多
SAMPLE_CODES = {"2426"}  # spec #265 驗收素材(鎖漲停時賣方全空)


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


def truth_rows(tables: dict[str, pa.Table], code: str, day_start: int) -> list[tuple]:
    """直讀 parquet 的一檔:依 msg_seq 排序,算收到時刻軸(不倒退)與文字標籤(模組說明的時鐘點規則)。"""
    rows = []
    for kind, table in tables.items():
        sub = table.filter(pc.equal(table["code"], code))  # type: ignore[attr-defined]
        cols = {c: sub[c].to_pylist() for c in sub.column_names}
        for i in range(sub.num_rows):
            book = tuple(cols[c][i] for c in LEVELS)
            trade = tuple(cols[c][i] for c in TRADE_COLS) if kind == "t" else None
            rows.append((cols["msg_seq"][i], kind, book, cols["recv_ns"][i], trade))
    rows.sort(key=lambda r: r[0])
    out = []
    axis = None
    clock: int | None = None
    clock_index = -1
    for idx, (seq, kind, book, recv_ns, trade) in enumerate(rows):
        recv_epoch_ms = recv_ns // 1_000_000
        recv = recv_epoch_ms - day_start
        axis = recv if axis is None else max(axis, recv)
        if trade is not None:
            ms = trade[0]
            if ms is not None and (clock is None or ms >= clock) and day_start + ms <= recv_epoch_ms + TOLERANCE_MS:
                clock, clock_index = ms, idx
        out.append((seq, kind, book, axis, trade, (clock, idx - clock_index)))
    return out


def labels_from_raw_payload(payload: dict) -> list[tuple[int | None, int]]:
    """只照模組說明「外掛檔 v1」從原始 payload 推標籤(不經 decode):沒列在 anomalous 的成交 = 時鐘點。"""
    anomalous = set(payload["anomalous"])
    trade_cells = payload["trade"]
    clock: int | None = None
    clock_index = -1
    k = 0
    labels = []
    for i, ch in enumerate(payload["kind"]):
        if ch == "t":
            if i not in anomalous:
                clock, clock_index = trade_cells[k * 4], i
            k += 1
        labels.append((clock, i - clock_index))
    return labels


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
    parquet_codes = {code for t in tables.values() for code in pc.unique(t["code"]).to_pylist()}  # type: ignore[attr-defined]

    # (b) 代號集合
    files = {f.stem: f for f in plugin_dir.glob("*.js")}
    missing, extra = sorted(parquet_codes - set(files)), sorted(set(files) - parquet_codes)
    set_ok = not missing and not extra
    print(f"(b) 代號集合:parquet {len(parquet_codes)} 檔、外掛檔 {len(files)} 檔,少產 {missing},多產 {extra} —— {'相等' if set_ok else '不相等'}")

    rng = random.Random(267)
    full_rows = full_bad = label_bad = anomalous_bad = jump_checked = jump_bad = 0
    anomalous_total = 0
    empty_ask = empty_bid = empty_both = 0
    kept: dict[str, tuple[dict, list]] = {}
    for code in sorted(set(files) & parquet_codes):
        payload = parse_plugin_js(files[code].read_text(encoding="utf-8"))
        replay = decode(payload)
        truth = truth_rows(tables, code, day_start)
        full_rows += len(truth)
        got = [
            (
                fr.msg_seq,
                "t" if fr.kind == "trade" else "b",
                fr.book,
                fr.recv_ms,
                None if fr.trade is None else (fr.trade.ms, fr.trade.price_milli, fr.trade.qty, fr.trade.side),
                (fr.clock_ms, fr.after),
            )
            for fr in replay.frames
        ]
        if got != truth:
            full_bad += 1
            first = next((i for i, (a, b) in enumerate(zip(got, truth)) if a != b), None)
            print(f"(a) {code} 不符:frames {len(got)} vs parquet {len(truth)},第一個不符在第 {first} 則(None = 前綴相同、長度不同)")
        truth_labels = [row[5] for row in truth]
        if labels_from_raw_payload(payload) != truth_labels:
            label_bad += 1
            print(f"(a) {code} 原始 payload 推出的標籤與真值不符")
        truth_anomalous = [i for i, row in enumerate(truth) if row[4] is not None and row[5][1] != 0]
        anomalous_total += len(truth_anomalous)
        if payload["anomalous"] != truth_anomalous:
            anomalous_bad += 1
            print(f"(a) {code} anomalous {payload['anomalous']} ≠ 真值 {truth_anomalous}")
        for idx in truth_anomalous:
            seq, _, _, axis, trade, _ = truth[idx]
            print(f"    時刻異常成交:{code} 第 {idx} 則 msg_seq={seq} 收到 {hms(axis)} 達錢時刻 {hms(trade[0])}")
        code_ask_empty = 0
        for _, _, book, _, _, _ in truth:
            ask_empty = all(v is None for v in book[10:])
            bid_empty = all(v is None for v in book[:10])
            empty_ask += ask_empty
            empty_bid += bid_empty
            empty_both += ask_empty and bid_empty
            code_ask_empty += ask_empty
        if code in SAMPLE_CODES:
            print(f"(e) {code} 賣方全空 {code_ask_empty} 則(共 {len(truth)} 則)")
        n, every = payload["n"], payload["kf_every"]
        picks = {0, n - 1, *rng.sample(range(n), min(200, n))}
        for k in range(1, (n - 1) // every + 1):
            picks |= {k * every - 1, k * every, min(k * every + 1, n - 1)}
        for i in sorted(picks):
            jump_checked += 1
            if book_at(payload, i) != truth[i][2]:
                jump_bad += 1
                print(f"(c) {code} 第 {i} 則 book_at 不符")
        kept[code] = (payload, truth)
    print(
        f"(a) 全量:{len(kept)} 檔、{full_rows} 則(msg_seq / 種類 / 五檔 / 收到時刻軸 / 成交欄 / 標籤),"
        f"decode 不符 {full_bad} 檔、原始 payload 標籤不符 {label_bad} 檔、anomalous 清單不符 {anomalous_bad} 檔;"
        f"時刻異常成交共 {anomalous_total} 則"
    )
    print(f"(c) 跳轉規則(keyframe 前後 / 首尾 / 隨機):{jump_checked} 則,不符 {jump_bad} 則")

    moments = [
        ("2426", "11:02:43.500"),
        ("2426", "11:02:45.700"),
        ("3441", "09:04:42.500"),
        ("2305", "09:07:47.500"),
        ("3441", "09:09:01.500"),
        ("1815", "09:00:03.000"),  # 首筆成交前(前面只有 07:31 收到的時刻異常成交)
        ("1815", "09:00:10.000"),  # 過了當日第一個時鐘點
    ]
    moment_bad = 0
    for code, at in moments:
        payload, truth = kept[code]
        target = to_ms(at)
        i = max(idx for idx, row in enumerate(truth) if row[3] <= target)
        clock_ms, after = truth[i][5]
        decoded_label = labels_from_raw_payload(payload)[i]
        last_trade = next((truth[j][4] for j in range(i, -1, -1) if truth[j][4] is not None), None)
        price = "—" if last_trade is None else f"{last_trade[1] / 1000:g}"
        book = book_at(payload, i)
        same = book == truth[i][2] and decoded_label == (clock_ms, after)
        moment_bad += not same
        label = f"首筆成交前第 {after} 則" if clock_ms is None else f"成交 {hms(clock_ms)} 之後第 {after} 則"
        print(
            f"(d) {code} 拖到 {at} → 第 {i} 則 msg_seq={truth[i][0]} 收到 {hms(truth[i][3])}"
            f"(真值側重算:{label})現價 {price}:{ladder(book)}"
            f" —— 五檔與標籤 {'皆相等' if same else '不符'}"
        )
    print(
        f"(e) 空簿:賣方全空 {empty_ask} 則、買方全空 {empty_bid} 則(兩者皆含兩邊全空);兩邊全空 {empty_both} 則"
        f" —— 不含兩邊全空則為賣方 {empty_ask - empty_both}、買方 {empty_bid - empty_both}"
    )
    ok = set_ok and full_bad == label_bad == anomalous_bad == jump_bad == moment_bad == 0
    print(f"結果:{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
