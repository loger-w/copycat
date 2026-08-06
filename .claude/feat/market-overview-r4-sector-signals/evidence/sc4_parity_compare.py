"""SC-4 parity:同一份真 FinMind snapshot rows 餵 copycat 與 neigui 兩邊純函式對照。

窗外降級路徑(design §5):不需 neigui server、不限盤中 —— snapshot 盤後回最後
一盤資料,chain 為靜態表。兩邊各自「白名單 → filter → rotation」全管線跑完,
比 industries 名稱序列全等 + 逐業 avg_change_rate 差 ≤ 0.01pp。

盤中加強層(REST 同時刻對照)另跑:curl neigui /api/market/snapshot?refresh=true
與側車 /api/market/sector 各落檔比對(需 neigui server 在跑)。

用法:.venv\\Scripts\\python sc4_parity_compare.py(repo root 或本目錄皆可)
"""

import datetime as dt
import json
import pathlib
import sys

COPYCAT = r"C:\side-project\copycat"
NEIGUI_BACKEND = r"C:\side-project\neigui\backend"
sys.path.insert(0, COPYCAT)

from copycat.market_breadth import (  # noqa: E402
    assemble_universe,
    build_name_map,
    build_type_map,
    dedup_sector_map,
    parse_active_disposition,
)
from copycat.sector_rotation import compute_sector_rotation, rows_to_chain_map  # noqa: E402
from copycat.server import breadth_fetch  # noqa: E402

env = pathlib.Path(COPYCAT, ".env").read_text(encoding="utf-8-sig")
TOKEN = [
    ln.split("=", 1)[1].strip()
    for ln in env.splitlines()
    if ln.startswith("FINMIND_TOKEN")
][0]

out_dir = pathlib.Path(__file__).resolve().parent
stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

print("fetch snapshot / stock_info / disposition / chain …", flush=True)
snap = breadth_fetch.fetch_snapshot(TOKEN)
info = breadth_fetch.fetch_stock_info(TOKEN)
disp = breadth_fetch.fetch_disposition(TOKEN, dt.date.today())
chain_rows = breadth_fetch.fetch_industry_chain(TOKEN)
print(f"snapshot={len(snap)} info={len(info)} disp={len(disp)} chain={len(chain_rows)}")

# ---- copycat 管線 ----
sector_map = dedup_sector_map(info)
type_map = build_type_map(info)
name_map = build_name_map(info)
watch = parse_active_disposition(disp, dt.date.today())
universe_cc = assemble_universe(snap, sector_map, watch)
rot_cc = compute_sector_rotation(universe_cc, rows_to_chain_map(chain_rows))

# ---- neigui 管線(同一份原始 rows)----
sys.path.insert(0, NEIGUI_BACKEND)
from services.finmind_realtime import _build_name_map as ng_name_map  # noqa: E402
from services.finmind_realtime import _dedup_sector_map as ng_sector_map  # noqa: E402
from services.industry_chain import _rows_to_map as ng_rows_to_map  # noqa: E402
from services.market_today import compute_sector_rotation as ng_rotation  # noqa: E402
from services.market_universe import filter_universe as ng_filter  # noqa: E402

ng_smap = ng_sector_map(info)
whitelisted = [r for r in snap if r.get("stock_id") in ng_smap]
allowed = ng_filter([r.get("stock_id", "") for r in whitelisted], watch_list=watch)[
    "universe"
]
universe_ng = [r for r in whitelisted if r.get("stock_id") in allowed]
rot_ng = ng_rotation(universe_ng, ng_rows_to_map(chain_rows))

# ---- 對照 ----
result = {
    "stamp": stamp,
    "universe_sizes": {"copycat": len(universe_cc), "neigui": len(universe_ng)},
    "pass": None,
    "diffs": [],
}
ind_cc = (rot_cc or {}).get("industries", [])
ind_ng = (rot_ng or {}).get("industries", [])
names_cc = [i["name"] for i in ind_cc]
names_ng = [i["name"] for i in ind_ng]
if names_cc != names_ng:
    result["diffs"].append({"kind": "industry_order", "copycat": names_cc, "neigui": names_ng})
for a, b in zip(ind_cc, ind_ng):
    if a["name"] == b["name"]:
        delta = abs(a["avg_change_rate"] - b["avg_change_rate"])
        if delta > 0.01:
            result["diffs"].append(
                {"kind": "avg_change_rate", "industry": a["name"], "delta_pp": delta}
            )
        if a["members"] != b["members"]:
            result["diffs"].append(
                {"kind": "members", "industry": a["name"],
                 "copycat": a["members"], "neigui": b["members"]}
            )
result["pass"] = not result["diffs"]
result["industries_count"] = {"copycat": len(ind_cc), "neigui": len(ind_ng)}

out = out_dir / f"SC-4_parity-{stamp}.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PASS={result['pass']} industries={result['industries_count']} → {out.name}")
if not result["pass"]:
    print(json.dumps(result["diffs"][:5], ensure_ascii=False, indent=2))
    sys.exit(1)
