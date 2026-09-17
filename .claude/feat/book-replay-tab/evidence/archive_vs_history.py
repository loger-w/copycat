"""#268 追加驗證:同一檔同一天,tick 存檔轉出的逐筆(extras_from_archive.py)vs 回看頁既有的達錢歷史逐筆。

比 1 分 K(開高低收量,回看頁分時 / K 線吃的就是這個)與內外盤(回看頁用 價 ≥ 賣一 / 價 ≤ 買一 判)。
用法:python archive_vs_history.py <存檔轉出資料夾>/<日期> <代號>...
"""

import json
import sys
from collections import Counter
from pathlib import Path

HIST = Path(r"C:\Users\USER\Documents\copycat-trading-review\data\ticks")


def bars(rows):
    out = {}
    for ms, p, q, _b, _a in rows:
        if not p or not q:
            continue
        i = min(269, max(0, (ms // 1000 - 32400) // 60))
        o = out.setdefault(i, [p, p, p, p, 0])
        o[1], o[2], o[3], o[4] = max(o[1], p), min(o[2], p), p, o[4] + q
    return out


def side(r):
    _ms, p, _q, b, a = r
    return "外" if a and p >= a else "內" if b and p <= b else "中"


arch_dir = Path(sys.argv[1])
for code in sys.argv[2:]:
    a = json.loads((arch_dir / f"{code}.json").read_text(encoding="utf-8"))
    h = json.loads((HIST / arch_dir.name / f"{code}.json").read_text(encoding="utf-8"))
    ba, bh = bars(a), bars(h)
    keys = sorted(set(ba) | set(bh))
    same = sum(ba.get(k) == bh.get(k) for k in keys)
    vol_a, vol_h = sum(v[4] for v in ba.values()), sum(v[4] for v in bh.values())
    diff_min = [k for k in keys if ba.get(k) != bh.get(k)]
    print(f"{code}: 筆數 存檔 {len(a)} / 歷史 {len(h)};1 分 K {same}/{len(keys)} 根完全相同;總量 {vol_a:.0f} / {vol_h:.0f};"
          f"內外盤分佈 存檔 {dict(Counter(map(side, a)))} / 歷史 {dict(Counter(map(side, h)))}")
    for k in diff_min[:3]:
        hh, mm = divmod(540 + k, 60)
        print(f"   不同 {hh:02d}:{mm:02d} 存檔 {ba.get(k)} 歷史 {bh.get(k)}")
