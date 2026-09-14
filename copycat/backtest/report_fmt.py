"""報告格式 helper(T 日跟多回測報告用).

- fmt_cell(原 report._fmt):None → —;float → +.4f(|v|<1)/ .2f;int / str → str(v)。

2026-09-14 專案瘦身:fmt_num / fmt_quantiles 原是 fade 回測家族的格式器,家族整批刪除後
零 caller,一併移除(語意鎖在 git 歷史與 docs/evidence 的 fade 報告裡)。
"""

from __future__ import annotations


def fmt_cell(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.4f}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)
