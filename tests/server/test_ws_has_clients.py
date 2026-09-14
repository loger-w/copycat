"""`WsBroadcaster.has_clients()`(perf #244):corr 引擎「沒人聽就不算」的閘,語意 = 有沒有活著的 stream。

登記 / 除名在 `stream()` 的 try / finally:進 generator 才算連上,generator 收掉才除名。
"""

from __future__ import annotations

from copycat.server.ws import WsBroadcaster


async def test_has_clients_follows_stream_lifecycle() -> None:
    b = WsBroadcaster()
    assert b.has_clients() is False

    gen = b.stream(seed=[{"type": "seed"}])
    first = await gen.__anext__()  # 進 generator = 登記
    assert first == {"type": "seed"}
    assert b.has_clients() is True

    await gen.aclose()  # 收掉 = 除名
    assert b.has_clients() is False


async def test_has_clients_counts_any_of_many() -> None:
    b = WsBroadcaster()
    g1 = b.stream(seed=[{"type": "a"}])
    g2 = b.stream(seed=[{"type": "b"}])
    await g1.__anext__()
    await g2.__anext__()
    assert b.has_clients() is True
    await g1.aclose()
    assert b.has_clients() is True  # 還有一個在聽
    await g2.aclose()
    assert b.has_clients() is False
