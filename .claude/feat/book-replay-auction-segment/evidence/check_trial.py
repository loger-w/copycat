"""#273 驗收:讀正式外掛檔,核對集合競價段的則號區間與收到時刻。

用法:python check_trial.py <YYYY-MM-DD> [代號 …]
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\mod-auction-segment-273")

from copycat.book_replay import decode, parse_plugin_js  # noqa: E402

BOOK = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
CLOSE_FROM_MS = (13 * 3600 + 25 * 60) * 1000


def hhmmss(ms: int) -> str:
    return str(dt.timedelta(milliseconds=ms))[:12]


def main() -> int:
    date = sys.argv[1]
    files = sorted(BOOK.joinpath(date).glob("*.js"))
    only = set(sys.argv[2:])
    if only:
        files = [p for p in files if p.stem in only]
    versions: set[int] = set()
    with_close = 0
    runs_total = 0
    trial_msgs = 0
    total_msgs = 0
    close_start: set[str] = set()
    intraday: list[str] = []
    for path in files:
        payload = parse_plugin_js(path.read_text(encoding="utf-8"))
        versions.add(payload["v"])
        day = decode(payload)  # 逐則自檢(含 trial 區間形狀)
        frames = day.frames
        total_msgs += len(frames)
        trial_msgs += sum(f.trial for f in frames)
        ranges = list(zip(payload["trial"][::2], payload["trial"][1::2], strict=True))
        runs_total += len(ranges)
        saw_close = False
        for start, end in ranges:
            a, z = frames[start].recv_ms, frames[end].recv_ms
            if z >= CLOSE_FROM_MS:
                saw_close = True
                close_start.add(hhmmss(a)[:8])
            elif len(only) or len(intraday) < 8:
                intraday.append(
                    f"{day.code} {hhmmss(a)}–{hhmmss(z)} 第 {start}–{end} 則"
                )
        with_close += saw_close
    print(f"== {date}:{len(files)} 檔、外掛檔版本 {sorted(versions)}")
    print(
        f"   集合競價段 {runs_total} 段、{trial_msgs:,} / {total_msgs:,} 則({trial_msgs / total_msgs:.2%})"
    )
    print(
        f"   有收盤集合競價段的檔:{with_close} / {len(files)};該段起點(收到時刻)= {sorted(close_start)}"
    )
    print("   盤中段樣本:" + ("; ".join(intraday) if intraday else "(無)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
