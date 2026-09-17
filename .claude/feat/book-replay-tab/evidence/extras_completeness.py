"""#268 追加 round-2 P2-02:非群組個股 tick 存檔逐筆 vs FinMind 日線(量 / 開高低收)—— 找出存檔不完整的日子。"""

import json
from pathlib import Path

R = Path(r"C:\Users\USER\Documents\copycat-trading-review\data")
DATE = "2026-09-16"
daily = json.load(open(R / "daily_extras.json", encoding="utf-8"))
for f in sorted((R / "ticks_archive" / DATE).glob("*.json")):
    c = f.stem
    rows = json.loads(f.read_text(encoding="utf-8"))
    fm = next((r for r in daily[c] if r["date"] == DATE), None)
    if not rows or not fm:
        print(c, "無資料")
        continue
    vol = sum(r[2] for r in rows)
    fm_vol = fm["Trading_Volume"] / 1000
    first = rows[0][0] // 1000
    px = [r[1] for r in rows]
    print(
        f"{c} 筆 {len(rows):>5} 首筆 {first // 3600:02d}:{first % 3600 // 60:02d}:{first % 60:02d} 量 {vol:>6.0f}/{fm_vol:>6.0f} = {vol / fm_vol:5.1%}  "
        f"開 {px[0]}/{fm['open']} 高 {max(px)}/{fm['max']} 低 {min(px)}/{fm['min']} 收 {px[-1]}/{fm['close']}"
    )
