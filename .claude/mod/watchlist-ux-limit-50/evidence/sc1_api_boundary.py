"""SC-1 real-env 邊界取證(打側車 8721;跑完自動還原種子自選)。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://localhost:8721"
out: list[str] = []


def put(codes: list[str], label: str) -> None:
    body = json.dumps({"codes": codes, "groups": []}).encode()
    req = urllib.request.Request(
        BASE + "/api/stock/watchlist",
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            n = len(json.loads(r.read())["codes"])
            out.append(f"[{label}] PUT {len(codes)} codes -> {r.status}, saved codes={n}")
    except urllib.error.HTTPError as e:
        out.append(f"[{label}] PUT {len(codes)} codes -> {e.code}, body={e.read().decode()}")


def get(path: str, label: str) -> None:
    try:
        with urllib.request.urlopen(BASE + path) as r:
            data = json.loads(r.read())
            keys = len(data.get("states", data))
            out.append(f"[{label}] GET group-state -> {r.status}, states/keys={keys}")
    except urllib.error.HTTPError as e:
        out.append(f"[{label}] GET group-state -> {e.code}, body={e.read().decode()}")


c50 = [str(1000 + i) for i in range(50)]
c51 = [str(1000 + i) for i in range(51)]
put(c50, "SC-1 happy: 50 檔")
put(c51, "SC-1 edge: 51 檔")
put(["12"], "regression: BAD_CODE(格式閘未動)")
get("/api/stock/group-state?codes=" + ",".join(c50), "SC-1: 50 相異碼")
get("/api/stock/group-state?codes=" + ",".join(c51), "SC-1 edge: 51 相異碼")
get("/api/stock/group-state?codes=" + ",".join(["2330"] * 51), "edge: 51 重複碼先去重")

seed = {
    "codes": ["2330", "2317", "2454", "2603", "2609", "3231"],
    "groups": [
        {"name": "觀察", "codes": ["2330", "2454"]},
        {"name": "航運", "codes": ["2603", "2609"]},
    ],
}
req = urllib.request.Request(
    BASE + "/api/stock/watchlist",
    data=json.dumps(seed).encode(),
    method="PUT",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    out.append(f"[restore] seed watchlist -> {r.status}")

text = "\n".join(out)
print(text)
with open(
    r".claude\mod\watchlist-ux-limit-50\evidence\SC-1_api-boundary.txt", "w", encoding="utf-8"
) as f:
    f.write(text + "\n")
