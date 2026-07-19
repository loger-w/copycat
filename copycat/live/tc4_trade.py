"""TC4TradeSource:達錢 4 交易 ZMQ 介接(唯一碰 trade ZMQ 的模組;design.md v5 §2.2)。

Disposable connection 模型:TCPY wrapper 的 REQ 方法無 try/finally、Connect 內裸 recv,
timeout 即毒化 lock / REQ EFSM 壞狀態 —— 因此 (1) context 級 RCVTIMEO 讓所有 socket 有
timeout;(2) REQ 收發自組電文 + lock timeout;(3) 任何 TouchanceDownError 即丟棄整個
api 物件,下一次呼叫 lazy reconnect;(4) listener 以 conn_info generation 跟隨重連。
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import zmq

from copycat.live.tc4 import TC4_APPID, TC4_SKEY
from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderReport,
    TouchanceDownError,
    parse_accounts,
    parse_execution_report,
    parse_fill_report,
)

logger = logging.getLogger(__name__)

_REQ_TIMEOUT_MS = 5000
_SUB_TIMEOUT_MS = 1000

OnReport = Callable[[str, OrderReport], None]


class TC4TradeSource:
    """TradeSource 實作;api/session/sub_port 可注入(測試口徑,注入時不做真連線)。"""

    def __init__(
        self,
        port: str = "51207",
        *,
        api: Any | None = None,
        session: str | None = None,
        sub_port: str | None = None,
        poll_wait_secs: float = 1.0,
        lock_timeout_secs: float = 5.0,
    ) -> None:
        self._port = port
        self._api = api
        self._injected = api is not None
        self._poll_wait = poll_wait_secs
        self._lock_timeout = lock_timeout_secs
        # (session, sub_port, generation) 單一 tuple 原子發布(R4-4)
        self._conn_info: tuple[str, str, int] | None = (
            (session or "", sub_port or "", 1) if api is not None else None
        )
        self._conn_lock = threading.Lock()
        self._on_report: OnReport | None = None
        self._on_reconnect: Callable[[], None] | None = None
        self._sub_factory: Callable[[str], Any] | None = None
        self._sub_ctx: zmq.Context | None = None
        self._listener: threading.Thread | None = None
        self._stop = threading.Event()
        self.reconnects = 0

    # ---- 連線(disposable) ----

    @property
    def connected(self) -> bool:
        return self._api is not None

    def _ensure_connected(self) -> Any:
        with self._conn_lock:
            if self._api is not None:
                return self._api
            if self._injected:
                # 注入模式作廢後不重連(真連線只在 production 路徑發生)
                raise TouchanceDownError("injected api disposed")
            sys.path.insert(
                0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY")
            )
            from tcoreapi_mq import TradeAPI  # type: ignore[import-untyped]

            api = TradeAPI(TC4_APPID, TC4_SKEY)
            # Connect() 內部裸 recv → context 級 timeout 讓之後建立的 socket 全部繼承(R2-2)
            api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
            api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
            try:
                q = api.Connect(self._port)
            except (zmq.ZMQError, OSError) as exc:
                raise TouchanceDownError(f"TC4 trade connect failed: {exc}") from exc
            if q.get("Success") != "OK":
                raise TouchanceDownError(f"TC4 trade login failed: {q}")
            # wrapper KeepAlive 的 Pong 走無 try/finally 路徑會毒化 lock → 自營(R3-2)
            if api.m_objZMQKeepAlive is not None:
                api.m_objZMQKeepAlive.Close()
                api.m_objZMQKeepAlive = None  # 防 Disconnect double-Close(R4-7)
            old = self._conn_info
            self._conn_info = (q["SessionKey"], q["SubPort"], (old[2] + 1) if old else 1)
            self._api = api
            logger.info("TC4 trade connected, session=%s", q["SessionKey"][:8])
            return api

    def _dispose(self, api: Any) -> None:
        """連線作廢(R2-3);identity 檢查防丟棄新連線(R3-5);取 api.lock 防撞 in-flight(R4-2)。"""
        with self._conn_lock:
            if self._api is not api:
                return
            self._api = None
        if api.lock.acquire(timeout=self._lock_timeout):
            try:
                api.Disconnect()
            except (zmq.ZMQError, OSError):
                logger.exception("TC4 trade Disconnect failed (best-effort)")
            finally:
                api.lock.release()
        else:
            logger.warning("TC4 trade dispose: api.lock busy,跳過實體 close(洩漏優於 crash)")

    def _req_request(self, obj: dict[str, Any], *, dispose_on_error: bool = True) -> dict:
        api = self._ensure_connected()
        info = self._conn_info
        assert info is not None
        payload = {**obj, "SessionKey": info[0]}
        if not api.lock.acquire(timeout=self._lock_timeout):
            # wrapper 殘留路徑毒化 lock 也收斂到恢復機制(R3-2 保險一)
            if dispose_on_error:
                self._dispose(api)
            raise TouchanceDownError("TC4 trade api.lock timeout")
        error: Exception | None = None
        message = b""
        try:
            api.socket.send_string(json.dumps(payload))
            message = api.socket.recv()[:-1]
        except (zmq.ZMQError, OSError) as exc:
            error = exc
        finally:
            api.lock.release()
        if error is not None:
            # REQ timeout 後 EFSM 壞狀態,連線作廢(R2-1)
            if dispose_on_error:
                self._dispose(api)
            raise TouchanceDownError(f"TC4 trade request failed: {error}") from error
        return json.loads(message)

    # ---- TradeSource 介面 ----

    def accounts(self) -> list[AccountInfo]:
        return parse_accounts(self._req_request({"Request": "ACCOUNTS"}))

    def place_order(self, param: dict[str, str]) -> dict:
        resp = self._req_request({"Request": "NEWORDER", "Param": param})
        if resp.get("Success") != "OK":
            err_code = str(resp.get("ErrCode", ""))
            if err_code == "-20":  # 未建立連線 = Touchance 端故障(design R2)
                api = self._api
                if api is not None:
                    self._dispose(api)
                raise TouchanceDownError("TC4 trade not connected to broker (ErrCode -20)")
            raise BrokerRejectedError(err_code, str(resp.get("ErrMsg", "")))
        return resp

    def restore_reports(self) -> list[OrderReport]:
        return self._restore("RESTOREREPORT", parse_execution_report)

    def restore_fills(self) -> list[OrderReport]:
        return self._restore("RESTOREFILLREPORT", parse_fill_report)

    def _restore(
        self, request: str, parse: Callable[[dict[str, Any]], OrderReport]
    ) -> list[OrderReport]:
        out: list[OrderReport] = []
        qry_index = ""
        while True:
            resp = self._req_request({"Request": request, "QryIndex": qry_index})
            rows = resp.get("Orders") or []
            if not rows:
                break
            out.extend(parse(r) for r in rows)
            nxt = str(rows[-1].get("QryIndex", ""))
            if not nxt or nxt == qry_index:  # 空 = 結束;停滯 = 防無限迴圈(R3-6)
                break
            qry_index = nxt
        return out

    def subscribe_reports(
        self, on_report: OnReport, on_reconnect: Callable[[], None]
    ) -> None:
        self._on_report = on_report
        self._on_reconnect = on_reconnect
        with self._conn_lock:  # listener 建立 idempotent(R4-3)
            if self._listener is not None:
                return
            self._listener = threading.Thread(
                target=self._listen_loop, name="tc4-trade-listener", daemon=True
            )
            self._listener.start()

    def close(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            listener.join(timeout=3.0)
        api = self._api
        if api is not None:
            self._dispose(api)
        if self._sub_ctx is not None:
            self._sub_ctx.term()
            self._sub_ctx = None

    # ---- SubPort listener ----

    def _make_sub(self, sub_port: str) -> Any:
        if self._sub_factory is not None:
            return self._sub_factory(sub_port)
        if self._sub_ctx is None:
            # 不用 api.context(dispose 會 term)— listener 存活跨連線世代
            self._sub_ctx = zmq.Context()
        sock = self._sub_ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.RCVTIMEO, _SUB_TIMEOUT_MS)
        sock.connect(f"tcp://127.0.0.1:{sub_port}")
        sock.setsockopt_string(zmq.SUBSCRIBE, "")
        return sock

    def _listen_loop(self) -> None:
        sock: Any | None = None
        bound_gen = -1
        try:
            while not self._stop.is_set():
                info = self._conn_info
                if info is not None and info[2] != bound_gen:
                    # generation 變化 = lazy reconnect 換了 SubPort → 跟隨重建(R3-1)
                    if sock is not None:
                        self._close_sub(sock)
                    sock = self._make_sub(info[1])
                    bound_gen = info[2]
                    self.reconnects += 1
                    if self._on_reconnect is not None:
                        self._on_reconnect()
                    continue
                if sock is None:
                    time.sleep(min(self._poll_wait, 0.1))
                    continue
                try:
                    raw = sock.recv()
                except zmq.Again:
                    continue  # idle 是常態,不重建(R2-5)
                except zmq.ZMQError:
                    logger.exception("TC4 trade SUB socket error,重建")
                    self._close_sub(sock)
                    sock = None
                    bound_gen = -1  # 下一輪依 conn_info 重建 + on_reconnect
                    continue
                if not raw:
                    continue
                try:
                    data = json.loads(raw[:-1])
                except ValueError:
                    continue
                self.handle_sub_message(data)
        finally:
            if sock is not None:
                self._close_sub(sock)

    @staticmethod
    def _close_sub(sock: Any) -> None:
        try:
            sock.close(linger=0)
        except (zmq.ZMQError, OSError):
            logger.debug("SUB close failed (ignored)")

    def handle_sub_message(self, data: dict[str, Any]) -> None:
        """SubPort 訊息分派(listener 呼叫;測試直接呼叫驗分流)。"""
        dtype = data.get("DataType")
        if dtype == "EXECUTIONREPORT":
            if self._on_report is not None:
                self._on_report("exec", parse_execution_report(data.get("Report") or {}))
        elif dtype == "FILLEDREPORT":
            if self._on_report is not None:
                self._on_report("fill", parse_fill_report(data.get("Report") or {}))
        elif dtype == "PING":
            if self._api is None:
                return  # disposed:不觸發 lazy reconnect(R4-5)
            try:
                self._req_request({"Request": "PONG", "ID": ""}, dispose_on_error=False)
            except TouchanceDownError:
                logger.debug("PONG failed (ignored)")  # 失敗不走 dispose 鏈(R4-5)

    # ---- 測試 hook(engine.py *_for_test 慣例) ----

    def set_report_callback_for_test(self, on_report: OnReport) -> None:
        self._on_report = on_report

    def set_sub_socket_factory_for_test(self, factory: Callable[[str], Any]) -> None:
        self._sub_factory = factory

    def set_conn_info_for_test(self, info: tuple[str, str, int]) -> None:
        self._conn_info = info
