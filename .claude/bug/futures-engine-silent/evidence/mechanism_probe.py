"""Bug 1 機制探針:啟動時 SUBQUOTE 失敗的商品,之後有沒有任何重試路徑?

不改任何 production code,只用真 FuturesEngine + 假 source 觀察。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from copycat.server.futures_engine import FuturesEngine  # noqa: E402


class FlakySource:
    """subscribe_symbol 對指定商品拋 ConnectionError(模擬 REQ timeout 後 _dispose)。"""

    def __init__(self, fail: set[str]) -> None:
        self.fail = fail
        self.attempts: list[str] = []
        self.leaf_attempts: list[tuple[str, str]] = []
        self.on_message = None

    def subscribe_symbol(self, product: str) -> None:
        self.attempts.append(product)
        if product in self.fail:
            raise ConnectionError("simulated TC4 REQ timeout")

    def subscribe_leaf(self, product: str, ym: str) -> None:
        self.leaf_attempts.append((product, ym))

    def unsubscribe_symbol(self, product: str) -> None: ...

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        return []

    def set_on_message(self, cb) -> None:
        self.on_message = cb

    def close(self) -> None: ...


async def scenario(name: str, fail: set[str], observe: float) -> None:
    src = FlakySource(fail)
    eng = FuturesEngine(lambda: src, leaf_grace_secs=0.2)
    await eng.start()
    await asyncio.sleep(observe)
    st = eng.state()
    silent = sorted(p for p, s in st["products"].items() if s["p"] is None)
    print(f"[{name}] 訂閱失敗商品={sorted(fail) or 'none'}")
    print(f"  觀察 {observe}s 後:seq={st['seq']} 無報價商品={silent}")
    print(f"  subscribe_symbol 呼叫次數={len(src.attempts)} 明細={src.attempts}")
    print(f"  leaf fallback 補訂={src.leaf_attempts or '(未觸發)'}")
    await eng.close()
    print()


async def main() -> None:
    await scenario("全部失敗", {"TXF", "MXF", "TMF"}, 1.5)
    await scenario("僅 TXF 失敗", {"TXF"}, 1.5)


asyncio.run(main())
