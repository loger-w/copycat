"""關機預算 —— 三個讀者同源(review A1,mod/shutdown-budget)。

讀者:
- `run.ps1`:`python -c "from copycat.server.shutdown_budget import run_grace_secs; ..."` 取
  Ctrl+C 後等 backend 自行收尾的上限,超時才 `taskkill /T /F`;
- `copycat.server.__main__`:uvicorn `timeout_graceful_shutdown=WS_DRAIN_SECS`(先等 WS 收攤那段
  的上限;沒有它 lifespan 的反序 close 可能一步都輪不到);
- `copycat.server.app` lifespan:慢段 WARNING 門檻 `SLOW_CLOSE_WARN_SECS`;lane 形狀
  (`TC4_LANE_DEPTH`)是它與這裡的口頭契約,由 `tests/server/test_boot_window.py::TestShutdownLanes`
  釘住。

為什麼要同源:改動前 `run.ps1` 寫死 15 s(只算一條 session 的一發 REQ),lifespan 卻是五條
TC4 session **序列** close;TC4 半死時硬殺落在退訂中途,健康的 session 也被還原成殭屍
(下一台開頭 ~60 s 零推播,#105 要修的病原樣回來)。數字散在三處各改各的就會再漂一次,
而漂掉的症狀零錯誤訊號。`tests/server/test_shutdown_budget.py` 釘的是**不等式**,改任一邊
的常數、別的邊沒跟上就紅。

上界是「TC4 半死」情境**可計段**的數字(`tc4.close_worst_secs` 註明哪一段無上界);健康路徑
整段收尾實測 1–3 s。
"""

from __future__ import annotations

import math

from copycat.capital.client import COM_JOIN_TIMEOUT_SECS
from copycat.live.tc4 import close_worst_secs

#: uvicorn `timeout_graceful_shutdown`:WS 收攤上限(int:uvicorn 的型別是 `int | None`)。
#: 正常情況瀏覽器毫秒級回 close frame;到期後 uvicorn 自己 cancel 剩餘 WS task,relay 的
#: CancelledError 路徑既有。
WS_DRAIN_SECS: int = 5

#: lifespan 反序 close 最深的 lane:corr → futures 串鏈(corr 讀 `futures.state()`,
#: `app.py` 的既有不變式);其餘 lane(index / stock / txo)各一條 session。
#: 與 lifespan 真實形狀的綁定由 `tests/server/test_boot_window.py::TestShutdownLanes::
#: test_lane_depth_matches_the_real_shutdown_shape` 釘住(五條 session 同時卡住時同時進場
#: 的條數 = 5 − depth + 1)。
TC4_LANE_DEPTH: int = 2

#: TC4 之外的段(crosscheck cancel / breadth / signals 的 bot.close + hub drain)+ 執行緒排程。
#: 全是既有上限內的小段,合計給一個固定裕度,不逐段列(列了也是猜的數字)。
LIFESPAN_SLACK_SECS: float = 5.0

#: 單段 close 超過這個秒數就印 WARNING 點名(健康路徑整段 1–3 s,單段 > 2 s 幾乎只有
#: 「等在途 Connect 的鎖」或「REQ 撞 RCVTIMEO」兩種)。
SLOW_CLOSE_WARN_SECS: float = 2.0


def lifespan_close_worst_secs() -> float:
    """lifespan `finally` 反序 close 的最壞耗時(秒)。"""
    return TC4_LANE_DEPTH * close_worst_secs() + COM_JOIN_TIMEOUT_SECS + LIFESPAN_SLACK_SECS


def run_grace_secs() -> int:
    """`run.ps1` 的 graceful 窗:uvicorn 先等 WS 收攤,再跑 lifespan。整數 —— PowerShell 端以
    `[int]` 解析後餵 `WaitForExit(ms)`。"""
    return math.ceil(WS_DRAIN_SECS + lifespan_close_worst_secs())
