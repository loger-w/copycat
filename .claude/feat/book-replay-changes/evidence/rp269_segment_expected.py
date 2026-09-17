"""#269 播放段標準答案:某檔某日收到時刻 [t0, t1] 內每一則的中間欄 / 成交明細期望值(格式同 rp269_expected)。

用法:python rp269_segment_expected.py <代號> <日期> <t0 毫秒> <t1 毫秒> <out.json>
"""

from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import rp269_expected as ex  # noqa: E402

code, date, t0, t1, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
payload = ex.br.parse_plugin_js((ex.BOOKDIR / date / f"{code}.js").read_text(encoding="utf-8"))
frames = list(ex.br.decode(payload).frames)
recv = [f.recv_ms for f in frames]
trade_idx = [i for i, f in enumerate(frames) if f.kind == "trade"]
first_book = ex.first_book_of(frames)
lo, hi = max(0, bisect.bisect_left(recv, t0) - 1), bisect.bisect_right(recv, t1)
expected = {str(i): ex.expected_at(frames, trade_idx, i, first_book) for i in range(lo, hi)}
Path(out).write_text(
    json.dumps({"code": code, "date": date, "frames": expected}, ensure_ascii=False),
    encoding="utf-8",
)
print(code, date, "frames", lo, "..", hi - 1, "count", len(expected))
