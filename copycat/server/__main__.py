"""啟動入口:python -m copycat.server(canonical port 8721,design §4 IR-3)。"""

from __future__ import annotations

import logging
import os

import uvicorn

from copycat.server.app import DEFAULT_INDEX, DEFAULT_STOCK, DEFAULT_TRADE, create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    port = int(os.environ.get("TXO_SERVER_PORT", "8721"))
    uvicorn.run(
        create_app(
            trade_source=DEFAULT_TRADE, stock_source=DEFAULT_STOCK, index_source=DEFAULT_INDEX
        ),
        host="127.0.0.1",
        port=port,
    )


if __name__ == "__main__":
    main()
