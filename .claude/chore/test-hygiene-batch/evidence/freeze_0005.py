"""pytest plugin:把 copycat.server.bars._now_time 凍在台北 00:05,重現午夜緩衝窗牆鐘相依。"""
import datetime as _dt
import copycat.server.bars as bars
bars._now_time = lambda: _dt.time(0, 5)
