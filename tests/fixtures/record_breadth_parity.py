"""SC-1 parity oracle 產生腳本(一次性手跑,產物 `breadth_parity.json` 進版控)。

做兩件事:

1. 真打 FinMind 錄**原始** rows 三份(snapshot / TaiwanStockInfo / disposition),
   欄位剝離到只留下游用得到的,壓 fixture 體積。
2. `sys.path` 插 neigui backend,**import neigui 現碼**跑完整組裝
   (`_dedup_sector_map` → 白名單 → `filter_universe` → `compute_breadth`)算出
   expected —— 這是 copycat 側 `dedup_sector_map` → `assemble_universe` →
   `compute_breadth` 的對照真值(不是 copycat 自己算的,才有 oracle 意義)。

重跑方式(repo root)::

    .venv\\Scripts\\python tests\\fixtures\\record_breadth_parity.py

前置:repo root `.env` 有 `FINMIND_TOKEN`;`C:\\side-project\\neigui` 存在。
共 3 個 FinMind request。**盤中跑**才錄得到有意義的漲跌停分佈(盤後 / 假日
snapshot 仍可用,但 limit 桶可能全零 → 該次 fixture 對 limit 判定零覆蓋)。

注意:copycat 的漲跌停判定是毫元精確等值、neigui 是 float 半 tick 容差 ——
真實 snapshot 的收盤價都落在合法 tick 上,兩者對真資料同解;若某次錄製出現
不等,那正是「半 tick 容差吃到非停板價」的真實案例,要當成發現而非直接改測試。
"""

# neigui backend 不在本 repo,`services.*` 靠 runtime sys.path 插入解析 —— 靜態
# 檢查必然找不到,本檔整檔關閉該項(其餘型別檢查照常)。
# pyright: reportMissingImports=false

from __future__ import annotations

import datetime as _dt
import json
import sys
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NEIGUI_BACKEND = Path(r"C:\side-project\neigui\backend")
_OUT = Path(__file__).resolve().parent / "breadth_parity.json"

_API = "https://api.finmindtrade.com/api/v4"
_TIMEOUT = 60
_DISPOSITION_LOOKBACK_DAYS = 60

# 欄位剝離白名單 —— 只留純函式層真的讀到的欄
_SNAPSHOT_FIELDS = (
    "stock_id",
    "close",
    "change_price",
    "change_rate",
    "total_volume",
    "yesterday_volume",
    "total_amount",
    "date",
)
_STOCK_INFO_FIELDS = ("stock_id", "stock_name", "type", "industry_category", "date")
_DISPOSITION_FIELDS = ("stock_id", "period_start", "period_end")


def _read_token() -> str:
    env_path = _REPO_ROOT / ".env"
    text = env_path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "FINMIND_TOKEN":
            token = value.strip().strip('"').strip("'")
            if token:
                return token
    raise SystemExit(f"FINMIND_TOKEN 未設於 {env_path}")


def _get(url: str, params: dict[str, str], token: str) -> list[dict]:
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    req = Request(full, headers={"Authorization": f"Bearer {token}"})
    with urlopen(req, timeout=_TIMEOUT) as resp:
        payload = json.load(resp)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise SystemExit(f"FinMind 回應無 data 陣列:{str(payload)[:200]}")
    return data


def _strip(rows: list[dict], fields: tuple[str, ...]) -> list[dict]:
    return [{k: r.get(k) for k in fields} for r in rows]


def main() -> None:
    token = _read_token()
    today = _dt.date.today()
    start = today - _dt.timedelta(days=_DISPOSITION_LOOKBACK_DAYS)

    print("fetching taiwan_stock_tick_snapshot ...")
    snapshot = _strip(_get(f"{_API}/taiwan_stock_tick_snapshot", {}, token), _SNAPSHOT_FIELDS)
    print("fetching TaiwanStockInfo ...")
    stock_info = _strip(
        _get(f"{_API}/data", {"dataset": "TaiwanStockInfo"}, token), _STOCK_INFO_FIELDS
    )
    print("fetching TaiwanStockDispositionSecuritiesPeriod ...")
    disposition = _strip(
        _get(
            f"{_API}/data",
            {
                "dataset": "TaiwanStockDispositionSecuritiesPeriod",
                "start_date": start.isoformat(),
                "end_date": today.isoformat(),
            },
            token,
        ),
        _DISPOSITION_FIELDS,
    )
    print(
        f"rows: snapshot={len(snapshot)} stock_info={len(stock_info)} "
        f"disposition={len(disposition)}"
    )

    # --- neigui 現碼算 expected(oracle) ---
    sys.path.insert(0, str(_NEIGUI_BACKEND))
    from services.finmind_realtime import (
        _build_name_map,
        _build_type_map,
        _dedup_sector_map,
    )
    from services.market_today import compute_breadth
    from services.market_universe import _parse_active_disposition, filter_universe

    primary_sector = _dedup_sector_map(stock_info)
    name_map = _build_name_map(stock_info)
    type_map = _build_type_map(stock_info)
    watch_list = _parse_active_disposition(disposition, today)

    # _do_fetch_market_snapshot:421-431 的組裝順序(白名單 → filter_universe)
    stock_universe = [r for r in snapshot if r.get("stock_id") in primary_sector]
    universe_filter = filter_universe(
        [r.get("stock_id", "") for r in stock_universe], watch_list=watch_list
    )
    allowed = universe_filter["universe"]
    stock_universe = [r for r in stock_universe if r.get("stock_id") in allowed]

    breadth = compute_breadth(stock_universe, type_map, name_map)
    if breadth is None:
        raise SystemExit("neigui compute_breadth 回 None —— 這批 snapshot 無法當 oracle")

    buckets: dict[str, str] = {}
    for row in breadth["rows"]:
        if row["limit_up"]:
            bucket = "limit_up"
        elif row["limit_down"]:
            bucket = "limit_down"
        elif row["change_rate"] > 0:
            bucket = "up"
        elif row["change_rate"] < 0:
            bucket = "down"
        else:
            bucket = "flat"
        buckets[row["stock_id"]] = bucket

    payload = {
        "recorded_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "row_counts": {
            "snapshot": len(snapshot),
            "stock_info": len(stock_info),
            "disposition": len(disposition),
            "universe": len(stock_universe),
        },
        "snapshot_rows": snapshot,
        "stock_info_rows": stock_info,
        "disposition_rows": disposition,
        "expected_counts": {"twse": breadth["twse"], "tpex": breadth["tpex"]},
        "expected_rows_buckets": buckets,
    }
    _OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    size_mb = _OUT.stat().st_size / 1024 / 1024
    print(f"wrote {_OUT} ({size_mb:.2f} MB)")
    print(f"expected_counts: {payload['expected_counts']}")


if __name__ == "__main__":
    main()
