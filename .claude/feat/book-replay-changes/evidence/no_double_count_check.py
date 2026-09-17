"""#269 review P-01 收修證據:09-16 全 80 檔,每筆成交最多被扣一次。

不變式(引擎定義):減量扣到成交 → 同時記一格有檔位的吃檔(限價 1–5 或市價 0)並加進 LevelChange.traded;
算進被擠出價位的期間成交 → 記一格五檔外的吃檔、不再進待扣。所以
- 全日 Σ 有檔位的吃檔張數 == Σ LevelChange.traded
- 每筆成交 Σ 吃檔張數 ≤ 成交張數
- Σ 五檔外吃檔張數 ≥ Σ Reappeared.traded_away(期間成交全數記成五檔外;另有到期仍扣不到、價在五檔外的)
並印 review 點名的兩個實例(3374 #2280 / #2288、6209 #754 / #756)。

用法:python no_double_count_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE = r"C:\side-project\copycat\.claude\worktrees\feat-book-replay-changes"
sys.path.insert(0, WORKTREE)
sys.path.insert(1, str(Path(__file__).parent))  # rp_load.py 與本檔同在 evidence/

from copycat import book_replay as br  # noqa: E402
from rp_load import iter_all  # noqa: E402

assert (br.__file__ or "").startswith(WORKTREE)

level_eaten = traded = beyond = away_traded = over = trades = 0
examples: dict[str, list[str]] = {}
for code, day in iter_all():
    for i, f in enumerate(day.frames):
        for c in f.changes:
            if isinstance(c, br.LevelChange):
                traded += c.traded
            elif isinstance(c, br.Reappeared):
                away_traded += c.traded_away
        if f.trade is not None:
            trades += 1
            total = sum(e.qty for e in f.eaten)
            if total > (f.trade.qty or 0):
                over += 1
            for e in f.eaten:
                if e.level is None:
                    beyond += e.qty
                else:
                    level_eaten += e.qty
        if (code, i) in {("3374", 2280), ("3374", 2288), ("6209", 754), ("6209", 756)}:
            examples.setdefault(code, []).append(
                f"#{i} 成交 {None if f.trade is None else (f.trade.price_milli, f.trade.qty)} "
                f"變動 {[c for c in f.changes if getattr(c, 'price_milli', None) in (418_000, 78_800)]} 吃檔 {f.eaten}"
            )
print(
    f"成交則 {trades:,};有檔位的吃檔 {level_eaten:,} 張 vs 價位變動算成交 {traded:,} 張 → {'相等' if level_eaten == traded else '不相等'}"
)
print(
    f"五檔外吃檔 {beyond:,} 張 ≥ 重新可見期間成交 {away_traded:,} 張 → {beyond >= away_traded};吃檔超過成交張數的成交 {over}"
)
for code, lines in examples.items():
    for line in lines:
        print(code, line)
