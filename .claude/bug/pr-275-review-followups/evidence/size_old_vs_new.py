"""F-07 大小對照:CLI 產的新格式外掛檔 vs 同資料還原成舊格式(時鐘點清單 `clock` = [則號, 毫秒] 攤平)。

用法(worktree 根目錄):
    python .claude/bug/pr-275-review-followups/evidence/size_old_vs_new.py <外掛檔日期目錄>

舊格式由解碼結果重建:時鐘點 = after == 0 的則(#267 版 encode 的定義),`clock` 放回原本 `anomalous` 的鍵位,
其餘鍵原樣;兩邊都走同一支 `plugin_js`(gzip level 9、mtime 0)。另核對新格式重編碼 == 檔案原文。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # worktree 根:別 import 到主 tree

from copycat.book_replay import decode, parse_plugin_js, plugin_js  # noqa: E402


def main(plugin_dir: Path) -> int:
    old_total = new_total = clock_points = anomalous = 0
    same_text = True
    for path in sorted(plugin_dir.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        payload = parse_plugin_js(text)
        replay = decode(payload)
        same_text &= plugin_js(payload) == text
        clock: list[int] = []
        for i, frame in enumerate(replay.frames):
            if frame.after == 0:
                assert frame.clock_ms is not None
                clock += [i, frame.clock_ms]
        old = {
            ("clock" if key == "anomalous" else key): (clock if key == "anomalous" else value)
            for key, value in payload.items()
        }
        new_total += len(text)
        old_total += len(plugin_js(old))  # type: ignore[arg-type]
        clock_points += len(clock) // 2
        anomalous += len(payload["anomalous"])
    print(
        f"檔數 {len(list(plugin_dir.glob('*.js')))}、時鐘點 {clock_points:,}、時刻異常成交 {anomalous}"
    )
    print(f"舊格式(clock 清單)總位元組 {old_total:,}")
    print(
        f"新格式(anomalous 清單)總位元組 {new_total:,}({(new_total - old_total) / old_total * 100:+.1f}%)"
    )
    print(f"新格式重編碼 == 檔案原文:{same_text}")
    return 0 if same_text else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
