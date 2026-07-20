"""報告格式 helpers — 兩份 _fmt 語意不同**並存不合併**(int / str 處理不一樣).

- fmt_cell(原 report._fmt):None → —;float → +.4f(|v|<1)/ .2f;int / str → str(v)。
- fmt_num(原 fade_report._fmt):float | int → format(spec);其他(含 str)→ —。
- fmt_quantiles(原 fade_anatomy / fade_entry_anatomy 兩份逐字相同的 _fmtq)。
"""

from __future__ import annotations


def fmt_cell(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.4f}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def fmt_num(v: object, fmt: str = ".4f") -> str:
    return f"{v:{fmt}}" if isinstance(v, float | int) else "—"


def fmt_quantiles(q: object, spec: str = ".2%") -> str:
    if not isinstance(q, dict):
        return "—"
    parts = []
    for key in ("p25", "p50", "p75", "p90"):
        v = q.get(key)
        parts.append(format(v, spec) if isinstance(v, float) else "—")
    return "/".join(parts) + f"(n={q.get('n')})"
