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
from typing import Any, Sequence, TextIO, cast

import uvicorn

from copycat.server.app import (
    DEFAULT_CORR,
    DEFAULT_FUTURES,
    DEFAULT_INDEX,
    DEFAULT_STOCK,
    create_app,
)
from copycat.server.verify import FakeTxoSource, neutralize_external_env

logger = logging.getLogger(__name__)

PROD_PORT_DEFAULT = 8721
VERIFY_PORT_DEFAULT = 8722  # 與 prod 8721 錯開:verify server 不可搶 canonical port

LOG_DIR = Path("logs")  # 相對 repo root(cwd 慣例與 .env fallback 同);.gitignore 已排除


class _Tee:
    """把一路 stdout/stderr 同時寫 console 與 log 檔。

    檔案每筆 write 即 flush:log 的價值在 crash 當下已落盤(uvicorn 或 thread 炸掉時
    沒有機會 flush)。log 檔寫壞(磁碟滿 / 檔案被鎖)只降級成 console-only 並印一次
    警告,不得拖垮 server。

    刻意不繼承 typing.TextIO(抽象方法齊全才可實例化)—— write/flush/isatty 之外
    (encoding / fileno / buffer …)全部 `__getattr__` 委派給原 stream。
    """

    def __init__(self, stream: TextIO, sink: TextIO) -> None:
        self._stream = stream
        self._sink: TextIO | None = sink

    def write(self, s: str) -> int:
        if self._sink is not None:
            try:
                self._sink.write(s)
                self._sink.flush()
            except OSError as e:
                self._sink = None  # 降級 console-only;之後不再嘗試(避免每筆都炸一次)
                self._stream.write(f"[server-log] log 檔寫入失敗,降級 console-only:{e}\n")
        return self._stream.write(s)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return False  # uvicorn 依此決定上色;ANSI 碼進 log 檔會毀掉 grep 可讀性

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


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
        app = create_app(FakeTxoSource())
        port = int(os.environ.get("TXO_SERVER_PORT", str(VERIFY_PORT_DEFAULT)))
        logger.info("verify 模式:fake source + 外部 IO env 壓制,port %d(log 不落檔)", port)
    else:
        app = create_app(
            stock_source=DEFAULT_STOCK,
            index_source=DEFAULT_INDEX,
            futures_source=DEFAULT_FUTURES,
            corr_source=DEFAULT_CORR,
        )
        port = int(os.environ.get("TXO_SERVER_PORT", str(PROD_PORT_DEFAULT)))
        if log_path is not None:
            logger.info("stdout/stderr 轉存 %s", log_path)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
