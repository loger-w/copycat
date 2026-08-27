"""pytest plugin:把 test_ws_streams_index_payload 的順序型 race 固定成「loop 那一拍先發」。

模擬的是真實序:client queue 註冊後、quote 被 _handle_quote 處理前,_broadcast_loop 恰有一則
待發 payload(MIS poll / 回補完成把 _dirty 撥成 True)→ 首則 twse.p 是 None。
"""
import time
import copycat.server.index_engine as ie
from tests.helpers.fake_sources import FakeIndexSource

_orig_stream = ie.IndexEngine.stream

def _stream(self):
    gen = _orig_stream(self)
    self._dirty = True  # 連上那一拍 loop 有東西要發
    return gen

ie.IndexEngine.stream = _stream

_orig_set = FakeIndexSource.set_on_message

def _set_on_message(self, cb):
    def delayed(q):
        time.sleep(0.05)  # 讓 loop(throttle 10 ms)那一拍先出去
        cb(q)
    _orig_set(self, delayed)

FakeIndexSource.set_on_message = _set_on_message
