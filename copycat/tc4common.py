"""TC4 共用常數與 QryIndex 分頁 helper(stdlib-only:data/ 與 live/ 皆可 import,不拉進 zmq)。"""

from __future__ import annotations

from typing import Callable, Iterator

# Touchance 官方範例公開的 app 憑證(GitBook / TCPY sample 原樣),非帳號 secret
TC4_APPID = "ZMQ"
TC4_SKEY = "8076c9867a372d2a9a814ae710c256e2"

#: OpenAPI 登入 port(2026-07-18 實測;官方文件的 51171/51141 與現版不符)
TC4_DEFAULT_PORT = "50774"


def iter_qry_pages(
    fetch: Callable[[str], list[dict]],
    *,
    start: str = "0",
) -> Iterator[list[dict]]:
    """TC4 QryIndex 游標分頁:空頁 = 結束;末筆 QryIndex 空或停滯 = 終止(防無限迴圈)。

    None / 缺值一律視為終止:真實 TC4 資料 QryIndex 恆為 str,此 edge 僅為防呆收斂。
    """
    qry_index = start
    while True:
        page = fetch(qry_index)
        if not page:
            return
        yield page
        nxt = str(page[-1].get("QryIndex", "") or "")
        if not nxt or nxt == qry_index:
            return
        qry_index = nxt
