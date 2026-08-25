# corr legs probe(2026-08-26 01:02,TC4 開著、prod :8721 在跑;候選不在 prod 腿清單)

指令:`TCPY_DIR=<main>/spikes/TCPY python spikes/corr_legs_probe.py --listen-secs 45 --poll-secs 6`

```
catalog: {"exchange_ids_now": ["CFE", "CME", "CME_CBT", "ENXT_PAR", "EUREX", "HKFE", "ICE", "ICE_SGX", "LIFFE", "NSE", "NYBOT", "OSE", "SGX", "TOCOM", "TWF_CHIP", "TWF_Futures", "Thailand Futures Exchange"], "exchange_ids_2026_06_30": [], "added": ["CFE", "CME", "CME_CBT", "ENXT_PAR", "EUREX", "HKFE", "ICE", "ICE_SGX", "LIFFE", "NSE", "NYBOT", "OSE", "SGX", "TOCOM", "TWF_CHIP", "TWF_Futures", "Thailand Futures Exchange"], "removed": [], "cfe_instrument_ids": ["VX", "VXM"], "cme_has": {"CL": true, "MCL": true, "GC": true, "MGC": true, "6E": true, "6J": true}, "twd_hits": {"SGX": ["TWN"]}}
oracle: {"TC.F.CFE.VX.HOT": true, "TC.F.CFE.VXM.HOT": true, "TC.F.CME.CL.HOT": true, "TC.F.CME.MCL.HOT": true, "TC.F.CME.GC.HOT": true, "TC.F.CME.MGC.HOT": true, "TC.F.CFE.NOPE_XX.HOT": false, "TC.F.CME.MES.HOT": true}
push_counts: {"TC.F.CME.MES.HOT": 197, "TC.F.CFE.VX.HOT": 19, "TC.F.CFE.VXM.HOT": 0, "TC.F.CME.CL.HOT": 163, "TC.F.CME.MCL.HOT": 152, "TC.F.CME.GC.HOT": 172, "TC.F.CME.MGC.HOT": 187} trade_counts: {"TC.F.CME.MES.HOT": 197, "TC.F.CFE.VX.HOT": 19, "TC.F.CFE.VXM.HOT": 0, "TC.F.CME.CL.HOT": 163, "TC.F.CME.MCL.HOT": 152, "TC.F.CME.GC.HOT": 172, "TC.F.CME.MGC.HOT": 187}
1k: {"TC.F.CFE.VX.HOT": [50, 3], "TC.F.CFE.VXM.HOT": [0, 3], "TC.F.CME.CL.HOT": [50, 3], "TC.F.CME.MCL.HOT": [50, 3], "TC.F.CME.GC.HOT": [50, 3], "TC.F.CME.MGC.HOT": [50, 3]}
disconnected
{"ok": true, "oracle": {"TC.F.CFE.VX.HOT": true, "TC.F.CFE.VXM.HOT": true, "TC.F.CME.CL.HOT": true, "TC.F.CME.MCL.HOT": true, "TC.F.CME.GC.HOT": true, "TC.F.CME.MGC.HOT": true, "TC.F.CFE.NOPE_XX.HOT": false, "TC.F.CME.MES.HOT": true}, "twd_hits": {"SGX": ["TWN"]}, "push_counts": {"TC.F.CME.MES.HOT": 197, "TC.F.CFE.VX.HOT": 19, "TC.F.CFE.VXM.HOT": 0, "TC.F.CME.CL.HOT": 163, "TC.F.CME.MCL.HOT": 152, "TC.F.CME.GC.HOT": 172, "TC.F.CME.MGC.HOT": 187}, "trade_counts": {"TC.F.CME.MES.HOT": 197, "TC.F.CFE.VX.HOT": 19, "TC.F.CFE.VXM.HOT": 0, "TC.F.CME.CL.HOT": 163, "TC.F.CME.MCL.HOT": 152, "TC.F.CME.GC.HOT": 172, "TC.F.CME.MGC.HOT": 187}, "out": "C:\\side-project\\copycat-wt-chart-ux\\spikes\\out\\corr_legs_probe.json"}
```
