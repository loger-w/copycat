"""#269 標準答案:以 worktree 的 `copycat.book_replay.decode` 解暫存 v2 外掛檔,產出抽樣則號的畫面期望值。

每個抽樣則 i:
- 中間欄 = 第 i、i−1 … i−59 則(新的在上;review P-02 後 user 拍板 60 則):標頭(第幾則、收到時刻、成交則的價量內外)
  與每一行的文字 / 是否淡色;沒有變動的則分「當日第一份五檔」(第一則不是五檔全空的則,同 decode)/ 五檔全空 / 沒有變動
- 成交明細 = 則號 ≤ i 的最後 20 筆成交(新的在上):時間 / 價 / 張 / 內外 / 吃檔,與「目前這則」標亮
文字格式照測試頁 JS(rpChangeLines / rpChanges / rpTape)逐字重寫;標準答案的數字全部來自 `decode` 的
dataclass(LevelChange / LeftView / Reappeared / EnteredView / Eaten),不讀外掛檔的攤平格。

抽樣:首末、隨機、每種變動各挑幾則(被擠出 / 重新可見(量有變、量沒變、期間有成交)/ 首次進入 / 市價佇列 /
減量同時有成交與撤單 / 五檔全空與其下一則 / 吃檔檔位 ≥ 2、市價、五檔外 / 沒吃檔的成交 / 時刻異常成交),
加驗收樣本(2426 買 98.0、2305 09:07:47、2489 掃單)。

用法:python rp269_expected.py <out.json>
環境變數 RP_BOOKDIR 可改指其他外掛檔資料夾(預設正式 viewer-cdp-book)。
"""

from __future__ import annotations

import bisect
import json
import os
import random
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

WORKTREE = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, WORKTREE)

from copycat import book_replay as br  # noqa: E402

assert (br.__file__ or "").startswith(WORKTREE), br.__file__

BOOKDIR = Path(
    os.environ.get("RP_BOOKDIR", r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
)
PLAN = {
    "2026-09-16": ["2426", "2305", "2489", "3441", "8064", "1815", "2344", "6715", "3406", "6770"],
    "2026-09-17": ["2426", "3441", "2303"],
}
CHG_KEEP, TAPE_KEEP = 60, 20
rng = random.Random(269)


def hms(ms: int) -> str:
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fms(ms: int) -> str:
    return f"{hms(ms)}.{ms % 1000:03d}"


def tick_milli(p: int) -> int:
    return 10 if p < 10000 else 50 if p < 50000 else 100 if p < 100000 else 500 if p < 500000 else 1000 if p < 1000000 else 5000


def rp_px(p: int) -> str:
    tk = tick_milli(p)
    return f"{p / 1000:.{0 if tk >= 1000 else 1 if tk >= 100 else 2}f}"


def fmt_p(milli: int) -> str:
    v = milli / 1000
    return re.sub(r"\.?0+$", "", f"{v:.1f}" if abs(v) >= 100 else f"{v:.2f}")


def qty(n: int) -> str:
    return f"{n:,}"


def side_txt(side: str) -> str:
    return "賣" if side == "ask" else "買"


def at(side: str, price: int) -> str:
    return f"市價{side_txt(side)}" if price == 0 else f"{side_txt(side)} {rp_px(price)}"


def dur(ms: int) -> str:
    if ms < 9950:
        # pr-279 review F-25:Python `:.1f` 逢半取偶,頁面 toFixed(1) 不是;250 / 1250 … 9250 ms
        # 兩邊在恰好卡在 0.05 邊界時會差一碼(例如 2250 ms 頁面「2.3 秒」、`:.1f` 是「2.2 秒」)。
        # 改成對 ms / 1000 這個 float 的實際二進位值取 ROUND_HALF_UP,0–9949 ms 逐值比過與 toFixed(1) 零差異。
        return f"{Decimal(ms / 1000).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} 秒"
    s = int(ms / 1000 + 0.5)
    if s < 60:
        return f"{s} 秒"
    if s < 3600:
        return f"{s // 60} 分 {s % 60} 秒"
    return f"{s // 3600} 時 {s % 3600 // 60} 分"


def side_cell(side: str | None) -> str:
    return "外" if side == "outer" else "內" if side == "inner" else "中"


def first_book_of(frames: list[br.Frame]) -> int:
    """當日第一份五檔 = 第一則不是五檔全空的則(沒有 = -1);decode 在這一則之前與這一則都不收變動。"""
    return next((i for i, f in enumerate(frames) if any(v is not None for v in f.book)), -1)


def change_lines(frames: list[br.Frame], j: int, first_book: int) -> list[dict]:
    f = frames[j]
    if not f.changes:
        if j == first_book:
            text = "當日第一份五檔(沒有前一份可比)"
        elif all(v is None for v in f.book):
            text = "五檔全空(達錢清空五檔,常見於暫緩撮合開始;不算撤單)"
        else:
            text = "五檔沒有變動"
        return [{"dim": True, "text": text}]
    out = []
    for c in f.changes:
        match c:
            case br.LevelChange():
                parts = [f"+{qty(c.added)} 掛單"] if c.after > c.before else []
                if c.traded:
                    parts.append(f"−{qty(c.traded)} 成交")
                if c.after < c.before and c.cancelled:
                    parts.append(f"−{qty(c.cancelled)} 撤單")
                out.append({"dim": False, "text": f"{at(c.side, c.price_milli)} {qty(c.before)} → {qty(c.after)} {'、'.join(parts)}"})
            case br.LeftView():
                out.append({"dim": True, "text": f"{at(c.side, c.price_milli)} {qty(c.qty)} 張被擠出五檔"})
            case br.Reappeared():
                where = at(c.side, c.price_milli)
                if c.left_qty == c.now_qty and not c.traded_away:
                    out.append({"dim": True, "text": f"⟳ {where} 回到五檔,量沒變({qty(c.now_qty)} 張,離開 {dur(c.away_ms)})"})
                else:
                    net = c.net_placed
                    sign = "+" if net > 0 else "−" if net < 0 else ""
                    out.append(
                        {
                            "dim": False,
                            "text": f"⟳ {where} 回到五檔"
                            f"離開時 {qty(c.left_qty)} → 現在 {qty(c.now_qty)}"
                            f"離開期間成交 {qty(c.traded_away)} → 淨掛 {sign}{qty(abs(net))}"
                            f"離開 {dur(c.away_ms)}"
                            "(一次掛進或分次堆積無法分辨)",
                        }
                    )
            case br.EnteredView():
                out.append({"dim": False, "text": f"{at(c.side, c.price_milli)} 首次進入五檔 {qty(c.qty)} 張(之前沒看過,不算掛單)"})
    return out


def trade_text(f: br.Frame) -> str:
    t = f.trade
    assert t is not None
    price = "—" if t.price_milli is None else fmt_p(t.price_milli)
    q = "—" if t.qty is None else qty(t.qty)
    return f"成交 {price} × {q} {side_cell(t.side)}"


def eat_text(eaten: tuple[br.Eaten, ...]) -> str:
    if not eaten:
        return "—"
    parts = []
    for e in eaten:
        s = side_txt(e.side)
        where = f"{s}五檔外" if e.level is None else f"市價{s}" if e.level == 0 else f"{s}{e.level}"
        parts.append(f"吃 {where} −{qty(e.qty)}")
    return "、".join(parts)


def expected_at(frames: list[br.Frame], trade_idx: list[int], i: int, first_book: int) -> dict:
    msgs = []
    for j in range(i, max(-1, i - CHG_KEEP), -1):
        f = frames[j]
        head = [f"第 {qty(j + 1)} 則", f"{fms(f.recv_ms)} 收到"]
        if f.kind == "trade":
            head.append(trade_text(f))
        msgs.append({"cur": j == i, "head": head, "lines": change_lines(frames, j, first_book)})
    last = bisect.bisect_right(trade_idx, i) - 1
    tape = []
    if last < 0:
        tape.append({"cur": False, "cells": ["這一則之前還沒有成交"]})
    for k in range(last, max(-1, last - TAPE_KEEP), -1):
        j = trade_idx[k]
        f = frames[j]
        t = f.trade
        assert t is not None
        tape.append(
            {
                "cur": j == i,
                "cells": [
                    "—" if t.ms is None else hms(t.ms),
                    "—" if t.price_milli is None else fmt_p(t.price_milli),
                    "—" if t.qty is None else qty(t.qty),
                    side_cell(t.side),
                    eat_text(f.eaten),
                ],
            }
        )
    return {"msgs": msgs, "tape": tape}


def picks_for(code: str, frames: list[br.Frame]) -> set[int]:
    n = len(frames)
    picks = {0, 1, 2, n - 2, n - 1} | {rng.randrange(n) for _ in range(12)}
    buckets: dict[str, list[int]] = {}

    def add(name: str, i: int) -> None:
        buckets.setdefault(name, []).append(i)

    for i, f in enumerate(frames):
        for c in f.changes:
            match c:
                case br.LeftView():
                    add("left", i)
                case br.Reappeared():
                    add("re_same" if c.left_qty == c.now_qty and not c.traded_away else "re_changed", i)
                    if c.traded_away:
                        add("re_traded", i)
                    if c.away_ms >= 60_000:
                        add("re_long", i)
                case br.EnteredView():
                    add("entered", i)
                case br.LevelChange():
                    if c.price_milli == 0:
                        add("queue", i)
                    if c.traded and c.cancelled:
                        add("mixed", i)
        if all(v is None for v in f.book):
            add("cleared", i)
            add("after_cleared", min(n - 1, i + 1))
        if f.kind == "trade":
            if not f.eaten:
                add("eat_none", i)
            for e in f.eaten:
                add("eat_off_view" if e.level is None else "eat_queue" if e.level == 0 else "eat_deep" if e.level >= 2 else "eat_1", i)
            if f.anomalous_trade:
                add("anomalous", i)
    for name, idx in buckets.items():
        picks |= set(rng.sample(idx, min(3, len(idx))))
    return picks


def main() -> None:
    out: dict = {"cases": []}
    for date, codes in PLAN.items():
        for code in codes:
            payload = br.parse_plugin_js((BOOKDIR / date / f"{code}.js").read_text(encoding="utf-8"))
            frames = list(br.decode(payload).frames)
            recv = [f.recv_ms for f in frames]
            trade_idx = [i for i, f in enumerate(frames) if f.kind == "trade"]
            first_book = first_book_of(frames)
            picks = picks_for(code, frames)
            if (code, date) == ("2426", "2026-09-16"):  # 驗收:買 98.0 回到五檔(第 41,957 則)
                # pr-279 review F-29:期望值一律來自 br.decode,產出前對驗收樣本補字面斷言 ——
                # 引擎在真資料上把這兩則算壞的話(例如淨掛算成別的值),這裡要先炸,而不是等 verify_changes 594/594 照過。
                reap = next(c for c in frames[41956].changes if isinstance(c, br.Reappeared))
                assert (reap.side, reap.price_milli) == ("bid", 98_000), reap
                assert (reap.left_qty, reap.now_qty, reap.traded_away, reap.net_placed) == (
                    39,
                    120,
                    0,
                    81,
                ), reap
                assert round(reap.away_ms / 1000) == 155, reap.away_ms
                picks |= set(range(41954, 41960))
            if (code, date) == ("2305", "2026-09-16"):  # 回歸:09:07:47 那三次不再算掛單
                picks |= {10147, 10148, 10149, 10163, 10164}
            if (code, date) == ("2489", "2026-09-16"):  # 掃單吃檔;驗收:賣 39.2 回到五檔(第 11,609 則)
                reap = next(c for c in frames[11608].changes if isinstance(c, br.Reappeared))
                assert (reap.side, reap.price_milli) == ("ask", 39_200), reap
                assert (reap.left_qty, reap.now_qty, reap.traded_away, reap.net_placed) == (
                    80,
                    0,
                    80,
                    0,
                ), reap
                assert round(reap.away_ms / 1000) == 11, reap.away_ms
                lo = bisect.bisect_left(recv, 10 * 3600000 + 4 * 60000 + 31_208)
                picks |= set(range(lo, lo + 10))
            for i in sorted(p for p in picks if 0 <= p < len(frames)):
                land = bisect.bisect_right(recv, recv[i]) - 1
                out["cases"].append(
                    dict(code=code, date=date, i=i, recv=recv[i], land=land, n=len(frames), **expected_at(frames, trade_idx, i, first_book))
                )
            print(date, code, "frames", len(frames), "picks", len(picks))
    Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("cases", len(out["cases"]))


if __name__ == "__main__":
    main()
