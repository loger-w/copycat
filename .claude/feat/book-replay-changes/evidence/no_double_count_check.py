"""#269 review P-01 收修證據:09-16 全 80 檔,每筆成交最多被扣一次。

前兩條不變式是引擎結構保證,修前修後皆成立,只當健檢用(pr-279 review F-21):
- 全日 Σ 有檔位的吃檔張數 == Σ LevelChange.traded
  (book_replay.py:_traded 每扣一次同時記一格吃檔並累加 traded,兩者恆同步)
- 每筆成交 Σ 吃檔張數 ≤ 成交張數
  (book_replay.py:_absorb 的 take = min(remaining, trade.qty),不會超扣)
真正能反映 P-01(同一筆成交在價位回來後被 _absorb 再扣一次)的是第三條「Σ 五檔外吃檔張數 ≥
Σ Reappeared.traded_away」,但全日加總會被別檔的餘量蓋掉(修前 commit 全日仍是 969 ≥ 808;
逐檔才看得出 3374 是 58 < 59、6209 是 55 < 61)。所以額外逐檔比較,列出 beyond_code <
away_traded_code 的代號 —— 修後應為空,若非空即代表這一檔有 P-01 那種重複扣。

並印 review 點名的兩個實例(3374 #2280 / #2288、6209 #754 / #756)。

用法:python no_double_count_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, WORKTREE)
sys.path.insert(1, str(Path(__file__).parent))  # rp_load.py 與本檔同在 evidence/

from copycat import book_replay as br  # noqa: E402
from rp_load import iter_all  # noqa: E402

assert (br.__file__ or "").startswith(WORKTREE), br.__file__

level_eaten = traded = beyond = away_traded = over = trades = 0
per_code: dict[str, list[int]] = {}  # code -> [beyond, away_traded]
examples: dict[str, list[str]] = {}
for code, day in iter_all():
    bucket = per_code.setdefault(code, [0, 0])
    for i, f in enumerate(day.frames):
        for c in f.changes:
            if isinstance(c, br.LevelChange):
                traded += c.traded
            elif isinstance(c, br.Reappeared):
                away_traded += c.traded_away
                bucket[1] += c.traded_away
        if f.trade is not None:
            trades += 1
            total = sum(e.qty for e in f.eaten)
            if total > (f.trade.qty or 0):
                over += 1
            for e in f.eaten:
                if e.level is None:
                    beyond += e.qty
                    bucket[0] += e.qty
                else:
                    level_eaten += e.qty
        if (code, i) in {("3374", 2280), ("3374", 2288), ("6209", 754), ("6209", 756)}:
            examples.setdefault(code, []).append(
                f"#{i} 成交 {None if f.trade is None else (f.trade.price_milli, f.trade.qty)} "
                f"變動 {[c for c in f.changes if getattr(c, 'price_milli', None) in (418_000, 78_800)]} 吃檔 {f.eaten}"
            )
print(
    f"成交則 {trades:,};有檔位的吃檔 {level_eaten:,} 張 vs 價位變動算成交 {traded:,} 張 → "
    f"{'相等' if level_eaten == traded else '不相等'}(結構恆等式,修前修後皆成立,不是 P-01 的證據)"
)
print(
    f"五檔外吃檔 {beyond:,} 張 ≥ 重新可見期間成交 {away_traded:,} 張 → {beyond >= away_traded};"
    f"吃檔超過成交張數的成交 {over}(全日加總,會被單檔餘量蓋掉,逐檔結果見下)"
)
violations = {code: tuple(v) for code, v in per_code.items() if v[0] < v[1]}
print(
    f"逐檔 beyond < away_traded(P-01 可判別的跡象,修後應為空):{len(violations)} 檔"
    + (f" {violations}" if violations else "(無)")
)
for code, lines in examples.items():
    for line in lines:
        print(code, line)
