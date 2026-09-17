"""#270 對照:Python `decode` 當標準答案,產出抽樣則號的期望畫面,給頁面逐則比對。

每檔抽:首末兩則、隨機則、時刻異常成交前後、首次鎖漲停前後、隨機幾個「同一毫秒收到多則」的整組、
2426 驗收段(11:02:44.025 同毫秒兩則前後);另抽隨機拖曳時刻(不落在收到時刻上)驗「≤ t 的最後一則」。

期望值:第幾則 / 標籤 / 收到時刻 / 成交則文字 / 現價 / 市價佇列文字 / 買賣各價位量(展開模式全列比)。
首次鎖漲停 = 直接呼叫線上 `SignalDetector._locked_up`,簿面取值照 `signal_hub` 組 `TickContext`
(`_best_limit_price`、第一檔是否市價佇列),漲停價取回看頁 blob 的 `lim`(頁面同一份)。

用法:python rp_step_expected.py <out.json>
"""

import base64
import bisect
import gzip
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from copycat.book_replay import BOOK_LEVEL_FIELDS as F
from copycat.book_replay import decode, parse_plugin_js
from copycat.live.signal_state import SignalDetector, TickContext
from copycat.live.stock_models import _best_limit_price

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")
DAY = "2026-09-16"
CODES = ["2426", "1815", "3441", "8064", "2344", "6770", "2305", "2489", "3406", "6715"]
OUT = Path(sys.argv[1])
rng = random.Random(270)

html = (ROOT / "viewer-cdp.html").read_text(encoding="utf-8")
blob = re.search(r'<script id="blob" type="text/plain">(.*?)</script>', html, re.S)
DATA = json.loads(gzip.decompress(base64.b64decode(blob.group(1).strip())))


def hms(ms):
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fms(ms):
    return f"{hms(ms)}.{ms % 1000:03d}"


def fmt_p(milli):
    """頁面 fmtP(毫元 / 1000):≥ 100 一位小數、其餘兩位,去掉尾端 0 與小數點。"""
    v = milli / 1000
    return re.sub(r"\.?0+$", "", f"{v:.1f}" if abs(v) >= 100 else f"{v:.2f}")


def label(f):
    if f.clock_ms is None:
        return f"首筆成交前第 {f.after} 則"
    return f"成交 {hms(f.clock_ms)}" + ("" if f.after == 0 else f" 之後第 {f.after} 則")


def kind_text(f):
    if f.kind != "trade":
        return "簿則"
    t = f.trade
    side = {"outer": "外", "inner": "內"}.get(t.side, "中")
    price = "—" if t.price_milli is None else fmt_p(t.price_milli)
    qty = "—" if t.qty is None else t.qty
    s = f"成交則 {price} × {qty} 張 {side}"
    if f.anomalous_trade:
        s += f"(達錢時刻異常 {'—' if t.ms is None else fms(t.ms)},不當標籤時刻)"
    return s


def first_lock(frames, lim):
    for i, f in enumerate(frames):
        if f.kind != "trade" or f.trade.price_milli != lim:
            continue
        b = dict(zip(F, f.book))
        bids = [(b[f"bid{l}"], b[f"bidq{l}"] or 0) for l in range(5) if b[f"bid{l}"] is not None]
        asks = [(b[f"ask{l}"], b[f"askq{l}"] or 0) for l in range(5) if b[f"ask{l}"] is not None]
        best_bid, best_ask = _best_limit_price(bids), _best_limit_price(asks)
        ctx = TickContext(
            trade_date=DAY,
            upper_milli=lim,
            lower_milli=None,
            ask_limit_available=best_ask is not None,
            bid_limit_available=best_bid is not None,
            bids0_is_market=bool(bids) and bids[0][0] == 0,
            asks0_is_market=bool(asks) and asks[0][0] == 0,
            best_bid_limit_milli=best_bid,
            best_ask_limit_milli=best_ask,
            day_volume=0,
        )
        if SignalDetector._locked_up(None, f.trade.price_milli, ctx):  # 不用 self
            return i
    return -1


out = {"day": DAY, "codes": {}}
for code in CODES:
    r = decode(parse_plugin_js((ROOT / "viewer-cdp-book" / DAY / f"{code}.js").read_text(encoding="utf-8")))
    fr = r.frames
    n = len(fr)
    recv = [f.recv_ms for f in fr]
    lim = round(DATA["d"][code][DAY]["lim"] * 1000)
    lock = first_lock(fr, lim)
    if lock < 0:
        lock_text = "當日未鎖漲停"
    else:
        lf = fr[lock]
        lock_text = "跳到首次鎖漲停 " + (fms(lf.recv_ms)[:8] if lf.anomalous_trade else hms(lf.trade.ms))

    picks = {0, 1, n - 2, n - 1} | {rng.randrange(n) for _ in range(20)}
    for i, f in enumerate(fr):
        if f.anomalous_trade:
            picks |= {max(0, i - 1), i, min(n - 1, i + 1)}
    if lock >= 0:
        picks |= {lock - 1, lock, min(n - 1, lock + 1)}
    groups = [ms for ms, c in Counter(recv).items() if c >= 3]
    for ms in rng.sample(groups, min(3, len(groups))):
        lo = bisect.bisect_left(recv, ms)
        picks |= set(range(lo, bisect.bisect_right(recv, ms)))
    if code == "2426":
        picks |= set(range(61596, 61603))

    samples = []
    for i in sorted(picks):
        f = fr[i]
        b = dict(zip(F, f.book))
        buy, sell, mkt = {}, {}, []
        for l in range(5):
            bp, bq, ap, aq = b[f"bid{l}"], b[f"bidq{l}"], b[f"ask{l}"], b[f"askq{l}"]
            if bp == 0:
                mkt.append(f"市價買 {'—' if bq is None else bq} 張")
            elif bp is not None:
                buy[str(bp)] = bq
            if ap == 0:
                mkt.append(f"市價賣 {'—' if aq is None else aq} 張")
            elif ap is not None:
                sell[str(ap)] = aq
        px = next((g.trade.price_milli for g in reversed(fr[: i + 1]) if g.trade and g.trade.price_milli), None)
        samples.append(
            dict(
                i=i,
                j=bisect.bisect_right(recv, recv[i]) - 1,
                idx=i + 1,
                lab=label(f),
                recv=recv[i],
                recv_text=fms(recv[i]),
                kind=kind_text(f),
                px=None if px is None else fmt_p(px),
                mkt="、".join(mkt),
                buy=buy,
                sell=sell,
            )
        )
    drags = []
    for _ in range(10):
        t = rng.randint(recv[0], recv[-1])
        drags.append(dict(t=t, j=bisect.bisect_right(recv, t) - 1))
    out["codes"][code] = dict(
        n=n, lim=lim, lock=lock, lock_text=lock_text, recv_first=recv[0], recv_last=recv[-1],
        samples=samples, drags=drags,
    )
    print(code, "n", n, "lock", lock, lock_text, "samples", len(samples))

OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("total samples", sum(len(c["samples"]) for c in out["codes"].values()))
