"""pytest plugin:把 IndexEngine._handle_quote 打成 no-op,模擬「quote 進來但推播鏈不撥 dirty」的迴歸。

pr-135 F-01:修前 test_ws_streams_index_payload 在這個迴歸下不是紅、是 hang(每 10 s 一則 ping 永不收斂)。
"""
import copycat.server.index_engine as ie

ie.IndexEngine._handle_quote = lambda self, quote: None
