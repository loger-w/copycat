"""測試側的「引擎就緒」等待器(mod/startup-http-window D5)。

啟動序列移到背景 task 之後,`with TestClient(app)` 返回只代表 **HTTP 面可用**,不再
等於「引擎就緒」—— 而既有 server 測試整批依賴後者(進 context 就打 route 期待 200、
或直接斷言 `app.state.signal_hub is not None`)。`BootedClient` 把那條假設補回來:
enter 之後等到 boot 序列結束才交回 client,既有斷言語意因此零改動。
"""

from __future__ import annotations

import time
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient


def wait_boot(app: FastAPI, timeout: float = 10.0, *, allow_error: bool = False) -> None:
    """輪詢 `app.state.boot_done`(跨執行緒讀 bool = GIL 原子),逾時 raise。

    done 之後檢查 `boot_error`:背景化把「序列本體拋例外」從 fail-loud(lifespan 炸、
    TestClient enter 就爆)變成 fail-silent(log + 後續引擎不啟動),等待器必須把它
    變回 loud —— 否則遷移過來的每個站點在 boot 半路崩掉時只會看到一片 503,照樣綠。
    刻意驗這條降級行為的測試顯式傳 `allow_error=True`。

    `getattr` 帶 default:lifespan 之外(沒進 context)呼叫時視為未完成,不 raise
    AttributeError 蓋掉真正的失敗訊息。
    """
    deadline = time.monotonic() + timeout
    while not getattr(app.state, "boot_done", False):
        if time.monotonic() > deadline:
            raise AssertionError(f"boot 序列未在 {timeout}s 內完成")
        time.sleep(0.005)
    error = getattr(app.state, "boot_error", None)
    if error is not None and not allow_error:
        raise AssertionError(f"boot 序列未走完即中止:{error}")


class BootedClient(TestClient):
    """`__enter__` 後自動等到引擎就緒的 `TestClient`(其餘行為完全相同)。"""

    def __enter__(self) -> BootedClient:
        super().__enter__()
        try:
            # starlette 宣告 `TestClient.app` 是 `ASGIApp`;此處恆為 create_app 的 FastAPI
            wait_boot(cast("FastAPI", self.app))
        except BaseException:
            # 逾時的 client 若不歸還,lifespan 永不關閉 → portal 執行緒與 boot task
            # 活到 process 結束,污染其後每一條測試
            super().__exit__(None, None, None)
            raise
        return self
