"""#273 驗收:讀正式外掛檔,核對集合競價段的則號區間與收到時刻。

用法:python check_trial.py <YYYY-MM-DD> [代號 …]

2026-09-19 pr-281 review #6 收修兩件:
- 盤中段只印前 8 筆,而存檔剛好列滿 8 筆 —— 看不出被截掉多少(實際 311 / 260 / 445 筆),所以改印
  「列 n / 共 m 筆」;
- 目錄空或日期打錯時 `trial_msgs / total_msgs` 會 ZeroDivisionError,改成早退。

`sys.path` 寫死已刪 worktree(`mod-auction-segment-273`)那條是 review #17,處置 `no-op`:venv 是
editable 安裝,死路徑會被靜默略過、fallback 到主 tree 的同一份 code,跑得起來;repo 內同款共 12 處
(pr-282 review #2 更正,原記 9 處),長年未爆,要收要整批收(已記 `docs/next-time.md`),不在這批挑食。
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\mod-auction-segment-273")

from copycat.book_replay import decode, parse_plugin_js  # noqa: E402

BOOK = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
CLOSE_FROM_MS = (13 * 3600 + 25 * 60) * 1000
SAMPLE = 8


def hhmmss(ms: int) -> str:
    return str(dt.timedelta(milliseconds=ms))[:12]


def main() -> int:
    date = sys.argv[1]
    files = sorted(BOOK.joinpath(date).glob("*.js"))
    if not files:
        print(f"== {date}:0 檔 —— 目錄空或日期打錯({BOOK / date})")
        return 2
    only = set(sys.argv[2:])
    if only:
        # 過濾前的清單不留著就印不出「目錄裡本來有幾支」,而「代號沒對上」與「日期打錯」
        # 要分得出來 —— 修前兩者共用同一句,會指著有 80 支檔的目錄說目錄空(pr-282 review #5)
        picked = [p for p in files if p.stem in only]
        if not picked:
            print(f"== {date}:代號 {sorted(only)} 在 {BOOK / date} 的 {len(files)} 支裡一支都沒對上")
            return 2
        files = picked
    versions: set[int] = set()
    with_close = 0
    runs_total = 0
    trial_msgs = 0
    total_msgs = 0
    close_start: set[str] = set()
    intraday: list[str] = []
    intraday_total = 0
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
                continue
            intraday_total += 1
            if only or len(intraday) < SAMPLE:
                intraday.append(f"{day.code} {hhmmss(a)}–{hhmmss(z)} 第 {start}–{end} 則")
        with_close += saw_close
    if not total_msgs:
        print(f"== {date}:{len(files)} 檔、0 則 —— 檔案裡一則都沒有({BOOK / date})")
        return 2
    print(f"== {date}:{len(files)} 檔、外掛檔版本 {sorted(versions)}")
    print(
        f"   集合競價段 {runs_total} 段、{trial_msgs:,} / {total_msgs:,} 則({trial_msgs / total_msgs:.2%})"
    )
    print(
        f"   有收盤集合競價段的檔:{with_close} / {len(files)};該段起點(收到時刻)= {sorted(close_start)}"
    )
    print(
        f"   盤中段樣本(列 {len(intraday)} / 共 {intraday_total} 筆):"
        + ("; ".join(intraday) if intraday else "(無)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
