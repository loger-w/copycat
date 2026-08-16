"""啟動入口:python -m copycat.server(canonical port 8721,design §4 IR-3)。

兩種模式(統一啟動包裝,next-time 2026-08-04 兩條的單一解):

- **prod(預設)**:真 source 四路 sentinel + stdout/stderr 全程 tee 到
  `logs/server-YYYYMMDD-HHMM.log` —— asyncio warning 事故那次差點無檔案證據可查,
  log 落檔不能靠 operator 記得手動重導向。
- **--verify**:fake TXO source + 其餘引擎不啟動 + 外部 IO env 壓制(群益 / Discord
  不真連),port 預設 8722 —— 盤中驗 HTTP 層專用,整條路不碰 ZMQ(CLAUDE.md §8)。

兩種模式 port 都可用 TXO_SERVER_PORT 覆寫。
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence, TextIO, cast

import uvicorn

from copycat.breadth_config import BreadthConfig
from copycat.server.app import (
    DEFAULT_BREADTH,
    DEFAULT_CORR,
    DEFAULT_FUTURES,
    DEFAULT_INDEX,
    DEFAULT_STOCK,
    create_app,
)
from copycat.server.verify import (
    FAIL_ENV_KEY,
    FakeTxoSource,
    fake_breadth_fetchers,
    neutralize_external_env,
)

logger = logging.getLogger(__name__)

PROD_PORT_DEFAULT = 8721
VERIFY_PORT_DEFAULT = 8722  # 與 prod 8721 錯開:verify server 不可搶 canonical port

# 錨定 repo root(build_info._REPO_ROOT 同慣例):.gitignore 的 `/logs/` 只認 root,
# cwd 相對會在子目錄起 server 時長出未被 ignore 的 logs/(review R-7)
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

#: verify server 的家數帶序列落檔目錄。**不可與 prod 共用** `data/market/`:兩台會寫
#: 同一個 `breadth-<date>.json`,verify 的 fake 六檔快照有機會蓋掉 prod 當日的完整
#: 序列(prod 下一輪雖會寫回,但夾縫中重啟 prod 就會 restore 到那一格 fake)。
VERIFY_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "market-verify"

#: --verify 的家數帶輪詢窗:全天。prod 預設窗(09:00–13:40)之外 `_poll_loop` 只跑
#: 首圈,而 verify server 幾乎都在盤後跑 —— flip 翻轉、失效注入、事件鏈路全都要
#: 「第二輪之後」才看得到,窗照抄 prod 等於整條取證路徑只剩一格(review C-2)。
VERIFY_WINDOW = ("00:00", "23:59")


class _Tee:
    """把一路 stdout/stderr 同時寫 console 與 log 檔。

    檔案每筆 write 即 flush:log 的價值在 crash 當下已落盤(uvicorn 或 thread 炸掉時
    沒有機會 flush)。log 檔寫壞(磁碟滿 / 檔案被鎖)只降級成 console-only 並印一次
    警告,不得拖垮 server。

    刻意不繼承 typing.TextIO(抽象方法齊全才可實例化)—— 文字寫入介面之外
    (encoding / fileno …)`__getattr__` 委派給原 stream。**已知洞:`.buffer` 的
    binary 寫入不落檔**(委派直達原 stream;review R-1),目前 server 內無人走那條路。
    """

    def __init__(self, stream: TextIO, sink: TextIO) -> None:
        self._stream = stream
        self._sink: TextIO | None = sink

    def _degrade(self, e: Exception) -> None:
        self._sink = None  # 降級 console-only;之後不再嘗試(避免每筆都炸一次)
        self._stream.write(f"[server-log] log 檔寫入失敗,降級 console-only:{e}\n")

    def write(self, s: str) -> int:
        if self._sink is not None:
            try:
                self._sink.write(s)
                self._sink.flush()
            except (OSError, ValueError) as e:  # ValueError = sink 已被 close(review R-3)
                self._degrade(e)
        return self._stream.write(s)

    def writelines(self, lines: Iterable[str]) -> None:
        # 不委派:委派拿到的是原 stream 的 bound method,sink 整個被繞過(review R-1)
        for s in lines:
            self.write(s)

    def flush(self) -> None:
        # sink 也要 flush:今天 write 每筆已 flush,但這裡不能依賴那件事 —— 若未來拿掉
        # per-write flush,flush() 靜默漏檔案的症狀正是本 feature 要防的(review R-4)
        if self._sink is not None:
            try:
                self._sink.flush()
            except (OSError, ValueError) as e:
                self._degrade(e)
        self._stream.flush()

    def isatty(self) -> bool:
        return False  # uvicorn 依此決定上色;ANSI 碼進 log 檔會毀掉 grep 可讀性

    def __getattr__(self, name: str) -> Any:
        # object.__getattribute__:未初始化實例(copy/deepcopy 的 __new__ 空殼)用一般
        # 屬性存取查 _stream 會再進 __getattr__ 無限遞迴(review R-2)
        return getattr(object.__getattribute__(self, "_stream"), name)


def _setup_prod_log() -> Path | None:
    """prod 模式:sys.stdout / sys.stderr 換成 tee。

    必須在 logging.basicConfig 之前呼叫 —— StreamHandler 在建構當下就快取
    sys.stderr,晚換的話 logging 那路進不了檔案。開檔失敗回 None(console-only 降級),
    啟動不可因 log 基建掛掉而失敗。
    """
    try:
        LOG_DIR.mkdir(exist_ok=True)
        path = LOG_DIR / datetime.now().strftime("server-%Y%m%d-%H%M.log")
        sink = path.open("a", encoding="utf-8", errors="replace")
    except OSError as e:
        sys.stderr.write(f"[server-log] log 檔開啟失敗,降級 console-only:{e}\n")
        return None
    sys.stdout = cast(TextIO, _Tee(sys.stdout, sink))
    sys.stderr = cast(TextIO, _Tee(sys.stderr, sink))
    return path


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    unknown = [a for a in args if a != "--verify"]
    if unknown:
        raise SystemExit(f"未知參數:{unknown}(僅支援 --verify)")
    verify = "--verify" in args

    log_path = None if verify else _setup_prod_log()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if verify:
        neutralize_external_env()
        port = int(os.environ.get("TXO_SERVER_PORT", str(VERIFY_PORT_DEFAULT)))
        if port == PROD_PORT_DEFAULT:
            # run.ps1 會在 operator 的 shell 留下 TXO_SERVER_PORT=8721;vite proxy 寫死
            # 8721,verify server 佔住它的失效樣態是「畫面整片 fake/空而零錯誤訊號」
            # (review R-5)。要真的在 8721 驗,顯式改設其他值再改回來,或先想清楚。
            raise SystemExit(
                f"--verify 不可用 canonical port {PROD_PORT_DEFAULT}"
                "(TXO_SERVER_PORT 殘留?verify 預設 8722,或顯式設非 8721 的 port)"
            )
        data_dir = VERIFY_DATA_DIR
        if os.environ.get(FAIL_ENV_KEY) == "1":
            # 注入本身由 `verify._fail_if_injected` 直讀 env,這裡只留可觀測性:
            # 「四支取數全拋」與「FinMind 真的掛了」在畫面上同形,log 是唯一的分辨點。
            logger.info("verify 失效注入模式:四支取數全拋,落檔目錄 %s", data_dir)
        app = create_app(
            FakeTxoSource(),
            # 家數帶走 fake 取數(不打真 FinMind)+ 獨立落檔目錄(不覆蓋 prod 當日序列)
            breadth_fetchers=fake_breadth_fetchers(),
            breadth_data_dir=data_dir,
            # SignalHub 解耦後(XR-3)verify server 也會建真 hub,而 hub 的落點 =
            # 自選檔所在目錄。不隔離的話 verify 進程會往 prod 的 `data/signals/*.jsonl`
            # 寫 fake 訊號 —— 那份是 `/api/stock/signals/today` 的歷史真相源(前端斷線
            # 自癒的 baseline),prod 畫面上會多出從未發生過的訊號列。
            # 與 breadth_data_dir 同一條隔離原則(上方 VERIFY_DATA_DIR)。
            stock_watchlist_path=data_dir / "stock_watchlist.json",
            breadth_config=BreadthConfig(
                window_start=VERIFY_WINDOW[0], window_end=VERIFY_WINDOW[1]
            ),
        )
        logger.info("verify 模式:fake source + 外部 IO env 壓制,port %d(log 不落檔)", port)
    else:
        app = create_app(
            stock_source=DEFAULT_STOCK,
            index_source=DEFAULT_INDEX,
            futures_source=DEFAULT_FUTURES,
            corr_source=DEFAULT_CORR,
            breadth_fetchers=DEFAULT_BREADTH,
        )
        port = int(os.environ.get("TXO_SERVER_PORT", str(PROD_PORT_DEFAULT)))
        if log_path is not None:
            logger.info("stdout/stderr 轉存 %s", log_path)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
