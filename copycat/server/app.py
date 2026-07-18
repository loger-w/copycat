"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.server.engine import EngineRuntime, QuoteSource

logger = logging.getLogger(__name__)


class SelectBody(BaseModel):
    series_id: str


def _default_source() -> QuoteSource:
    from copycat.live.tc4 import TC4QuoteSource  # 延遲 import:測試不觸 pyzmq/TC4

    return TC4QuoteSource(
        port=os.environ.get("TC4_PORT", "50774"),
        backfill_date=os.environ.get("TXO_BACKFILL_DATE"),
    )


def create_app(
    source: QuoteSource | None = None,
    *,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        runtime = EngineRuntime(
            source if source is not None else _default_source(),
            throttle_secs=throttle_secs,
            queue_maxsize=queue_maxsize,
        )
        app.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(lifespan=lifespan)
    origin = os.environ.get("FRONTEND_ORIGIN")
    if origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": {"error": "TC4_DOWN"}})

    def _runtime(request: Request) -> EngineRuntime:
        return request.app.state.runtime

    @app.get("/api/txo/series")
    async def list_series(request: Request) -> dict:
        runtime = _runtime(request)
        series = runtime.list_series()
        if not series:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return {
            "series": [
                {"series_id": s.series_id, "name": s.name, "expiry": s.expiry} for s in series
            ]
        }

    @app.post("/api/txo/select")
    async def select_series(request: Request, body: SelectBody) -> dict:
        runtime = _runtime(request)
        try:
            await runtime.activate(body.series_id)
        except KeyError:
            raise HTTPException(status_code=400, detail={"error": "UNKNOWN_SERIES"}) from None
        return runtime.latest_snapshot()

    @app.get("/api/txo/snapshot")
    async def snapshot(request: Request) -> dict:
        runtime = _runtime(request)
        snap = runtime.latest_snapshot()
        if snap["series_id"] is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return snap

    @app.websocket("/ws/txo-pnl")
    async def ws_txo_pnl(websocket: WebSocket) -> None:
        runtime: EngineRuntime = websocket.app.state.runtime
        await websocket.accept()
        try:
            await websocket.send_json(runtime.latest_snapshot())
            async for snap in runtime.snapshots():
                await websocket.send_json(snap)
        except WebSocketDisconnect:
            return

    return app
