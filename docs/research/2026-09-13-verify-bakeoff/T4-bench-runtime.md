# T4-bench-runtime —— 擂台:執行環境(event loop / GIL / 多核)實測報告

> 日期 2026-09-13。所有數字都是本次在這台機器上**實跑**出來的;推估一律標「推估」,
> 沒量到的一律標「未量」。repo 零改動、專案 `.venv` 零污染(全部跑在拋棄式 venv)。

---

## 0. 五句話結論

1. **最便宜的一項改善確實存在,但配方跟上一輪寫的不一樣。** 單獨
   `timeBeginPeriod(1)` 在這台 Windows 11 上**只有效約 3 秒**就被作業系統收回,之後
   完全退回 12.5 ms。要真的拿到 1 ms,必須**先**用
   `SetProcessInformation(ProcessPowerThrottling, ControlMask=EXECUTION_SPEED|IGNORE_TIMER_RESOLUTION, StateMask=0)`
   把本 process 從 Windows 11 的 EcoQoS 節流中豁免掉。兩行加起來:
   `asyncio.sleep(0.05)` drift **p50 12.47 → 0.556 ms(22.4×)、p99 14.2 → 1.98 ms**,
   而且在 `run.ps1` 現行的 `Start-Process -NoNewWindow` 啟動方式下實測全程穩住。
2. **winloop 裝得起來、跑得動、而且真的比較快。** Windows + Python 3.13 有官方 wheel
   (winloop 0.6.3)。raw TCP echo RTT p50 **37.9 → 19.5 µs(1.94×)**;整套
   uvicorn+FastAPI+WebSocket 端到端 WS RTT p50 **128.7 → 95.8 µs(1.34×)**。
   B02-06 / B04 列的兩個否決理由**實測都被駁回**:`create_subprocess_exec` 正常、
   ZMQ 阻塞執行緒 + `call_soon_threadsafe` 正常、`pythoncom.CoInitialize()` 正常。
3. **free-threading(3.13t)對這個 process 是硬否決,但理由只有一個:pywin32 沒有
   cp313t wheel。** `pyzmq` / `comtypes` / `fastapi` / `uvicorn` / `pydantic-core` /
   `websockets` 都裝得起來,但 `pythoncom` 是 pywin32 的一部分,缺它 = capital 的
   COM apartment 起不來 = 下不了單。順帶陣亡的還有 `msgspec` / `orjson` / `httptools` /
   `aiohttp`(→ `discord.py`)/ `winloop`。**但 3.13t 量出來的收益極大**(解析吞吐
   16 執行緒 6.57× vs GIL 的 0.95×;loop 被 CPU 執行緒拖累的量從 p99 92 ms 變成 0),
   這件事該進長期路線圖,不是丟掉。
4. **上一輪「deque + 旗標批次化 = 200 倍」的量測,方向對、數字對不上、但真實情境下
   更值得做。** 我量到的生產端成本是 **6.1 µs → 0.2 µs(30×)**,不是 0.040 µs。
   可是真正的殺傷力不在生產端:在 5 條 producer(= copycat 的 5 條 TC4 listener)、
   限速 2000 則/秒的擬真情境下,每則一次 `call_soon_threadsafe` 的
   **端到端 p99 是 10.7 毫秒**,而 deque+旗標是 **86 微秒 —— 124 倍**。
   接真 ZMQ SUB socket 的飽和測試更難看:現況設計會**掉封包**且 e2e p50 飆到 **1.66 秒**。
5. **ProcessPoolExecutor 在這台機器上的天花板是 4.4 倍,不是 8–12 倍,而且切錯法會慢
   23 倍。** 天真的 `ex.map(fn, [(arm, samples), ...])` 實測 **0.03–0.04×**(比單執行緒
   慢 23–33 倍),因為 4.56 MB 的 bars 被每個 task 重新 pickle 一次(dumps 94.5 ms /
   loads 102.7 ms),而一個 arm 的真工作只有 5 ms。必須用 initializer + 檔案/
   shared_memory 把資料送一次,才拿得到 4.27–4.45×(含 spawn 3.0–3.2×)。

---

## 1. 環境與可重現資訊

| 項目 | 值 |
|---|---|
| CPU | AMD Ryzen 7 7700,**8 physical / 16 logical** |
| OS | Windows 11 Home 10.0.26200,桌機(無電池),電源配置 = 平衡 |
| 系統 timer | `NtQueryTimerResolution` 全程回報 coarsest 15.625 ms / finest 0.5 ms / **current 1.0 ms** |
| 標準直譯器 | CPython 3.13.13(`C:\Users\USER\AppData\Local\Programs\Python\Python313`) |
| free-threading | CPython **3.13.15** free-threading build,本次用 `py install 3.13t` 裝進 `C:\Users\USER\AppData\Local\Python\pythoncore-3.13t-64`(Python Install Manager 26.3) |

拋棄式 venv(**沒有動專案 `.venv`**):

- `…\scratchpad\venvs\T4\`(GIL 3.13.13)—— winloop 0.6.3、pyzmq 27.2.0、msgspec 0.21.1、
  orjson 3.12.0、fastapi 0.141.1、uvicorn 0.52.4、websockets 17.1、httptools 0.8.0、
  pywin32 312、comtypes 1.4.16、httpx 0.28.1
- `…\scratchpad\venvs\T4t\`(free-threading 3.13.15)—— pyzmq 27.1.0、comtypes 1.4.16、
  fastapi 0.141.1、uvicorn 0.52.4、pydantic-core 2.41.4、websockets 17.1

腳本與原始輸出全在 `…\scratchpad\verify-bakeoff\`:

| 腳本 | 輸出 | 對決 |
|---|---|---|
| `t4_bench_timer.py` … `t4_bench_timer9.py` | `out_timer*.jsonl` / `.json`、`out_fg_*.json`、`out_runps1_*.json` | 1a timer |
| `t4_bench_loop_io.py` | `out_loopio.jsonl` | 1b socket IO |
| `t4_smoke_winloop.py` / `t4_smoke_winloop2.py` | `out_smoke.txt` / `out_smoke2.txt` | 1c winloop 風險閘 |
| `t4_bench_gil.py` | `out_gil_313.json` / `out_gil_313t.json` | 2a GIL 擴展 |
| `t4_bench_switch.py` | `out_switch.json` | 2b switchinterval |
| `t4_bench_pool.py` / `pool2` / `pool3` | `out_pool.json` / `out_pool2.json` / `out_pool3.json` | 2c ProcessPool |
| `t4_bench_cst.py` / `t4_bench_cst2.py` | `out_cst.json` / `out_cst2.json` | 3a 交接 |
| `t4_bench_zmq.py` / `t4_bench_zmq2.py` | `out_zmq_raw.txt` / `out_zmq2.jsonl` | 3b ZMQ |
| `t4_bench_dc.py` / `t4_bench_gcpause.py` | `out_dc_313.json` / `out_dc_313t.json` / `out_gcpause.json` | 4 dataclass |

`t4_bench_pool*.py` 會 `sys.path.insert` repo root 直接 import 真實的
`copycat.backtest.simulate`,跑的時候一律帶 `PYTHONDONTWRITEBYTECODE=1`,
事後 `find copycat -name "*.pyc" -newermt "-20 minutes"` 查證 **repo 內零新增 `__pycache__`**。

---

## 2. 對決 1:event loop

### 2.1 timeBeginPeriod(1) —— 上一輪的「最便宜改善」查證

**先講結論:這條成立,但不是一行,是兩行,而且只寫一行等於沒寫。**

我一開始量到的是雙峰:加了 `timeBeginPeriod(1)` 之後,**前 40 筆全部 0.1–1 ms,後面
全部 12–13 ms**。用 6 支腳本、8 種配方追下去,排除掉的假說有:重複呼叫 tbp、
`timeEndPeriod`+`timeBeginPeriod` 循環、`NtSetTimerResolution` 直呼、
HIGH_PRIORITY_CLASS、常駐一顆 armed 的 `CREATE_WAITABLE_TIMER_HIGH_RESOLUTION`、
讓 loop 每 1 ms 有一個 `call_later` —— **全部無效,一律在 ~3 秒後退回 12.5 ms**。

真正的原因是 **Windows 11 的 Power Throttling(EcoQoS)**:預設會對「背景」process
忽略 timer resolution 請求。決定性證據有兩組:

1. 同一支腳本 `Start-Process -WindowStyle Normal`(有可見 console)跑 → 全程
   p50 0.544 ms、99.4% 在 2 ms 以內;`-WindowStyle Hidden` 跑 → 3 秒後退回 12.6 ms。
2. 呼叫 `SetProcessInformation(ProcessPowerThrottling, ControlMask=EXECUTION_SPEED|IGNORE_TIMER_RESOLUTION, StateMask=0)`
   之後,即使完全無視窗,也全程穩住 0.556 ms。

> 附帶教訓:第一次寫這個 ctypes 呼叫時我沒設 `restype`/`argtypes`,
> `GetCurrentProcess()` 的偽 handle `-1` 被截成 32-bit,`SetProcessInformation`
> **靜默回 False**,害我多繞了三輪。這類 Win32 ctypes 呼叫一定要檢查回傳值。

**實測表(ProactorEventLoop,`asyncio.sleep(0.05)`,600 次,取 5 秒後的穩態段):**

| 配方 | p50 (ms) | p90 | p99 | < 2 ms 比例 |
|---|---|---|---|---|
| 現況(什麼都不做) | **12.571** | 13.430 | 14.189 | 0.0 |
| `timeBeginPeriod(1)` 單獨 | **12.514** | 13.530 | 14.301 | 0.0 |
| `SetPriorityClass(HIGH)` + tbp | 12.601 | 13.605 | 14.526 | 0.0 |
| **EcoQoS 豁免 + tbp** | **0.587** | 1.021 | 2.010 | **0.988** |
| winloop + EcoQoS 豁免 + tbp | **0.468** | 0.961 | 1.478 | **1.000** |

**用 `run.ps1` 現行啟動方式(`Start-Process -NoNewWindow`)複驗:**

| mode | 前 3 秒 p50 | 5 秒後 p50 | 5 秒後 < 2 ms |
|---|---|---|---|
| base | 12.115 | 12.469 | 0.0 |
| tbp 單獨 | 0.469 | **12.602** | **0.0** |
| qos + tbp | 0.646 | **0.556** | **0.99** |

**上一輪報告的 12.43 ms 我完全重現**(我量到 12.4–12.9 ms)。那個數字不是隨機的:
50 ms 的等待被對齊到 15.625 ms 的下一個邊界(15.625 × 4 = 62.5 ms),超額剛好 12.5 ms。

### 2.2 這 12 ms 在 prod 到底值多少 —— 一個會推翻直覺的補量

**idle loop 的 12.4 ms drift,在有推播進來的時候會自己消失一大半。**
我用一條限速 producer 執行緒不斷 `call_soon_threadsafe` 敲門,量同一個
`asyncio.sleep(0.05)`:

| 敲門速率 | drift p50 (ms) | p99 | < 2 ms |
|---|---|---|---|
| 0(完全 idle) | 12.452 | 14.301 | 0.0 |
| 10 /s | 12.238 | 15.238 | 0.05 |
| 100 /s | 3.417 | 10.055 | 0.43 |
| 300 /s | 2.893 | 3.534 | 0.44 |
| 1000 /s | **0.626** | 1.414 | **1.00** |

也就是說:盤中 TC4 推播密集時,drift 自然掉到 2–3 ms;**盤前、盤後、薄量時段、
以及所有 idle 的週期性 task,才是那 12.4 ms 真正落地的地方**。所以這兩行的收益要
誠實地說成:「把所有 timer 驅動步驟的尾巴從 ~14 ms 壓到 ~1.5 ms,盤中改善約 2–3 ms、
盤外改善約 12 ms」,而不是「全系統快 12 ms」。

copycat 裡真的會吃到的讀者:`stock_engine` 的 `call_later(0.1)` 逐筆打包 flush、
`futures_engine` 的 0.1 s 五檔 flush、`EngineRuntime._consume` 的 0.05 s 輪詢、
所有 `asyncio.sleep()` 退避。**注意 `queue.get(timeout=)` 這類不受影響**——
有東西進 queue 時它立刻返回,drift 只發生在 timeout 真的跑完的那一次。所以
**下單路徑(`capital/client.py` 的 `_cmd_q.get(timeout=0.05)`)不在受益範圍內**,
把這條算成「下單變快」是錯的。

### 2.3 winloop A/B

winloop **0.6.3** 有 `cp313-cp313-win_amd64` wheel,`pip install winloop` 一次成功。

**raw socket(asyncio streams,loopback,512 B payload,兩次重跑一致):**

| loop | echo RTT p50 (µs) | p90 | p99 | roundtrips/s | fanout 24 conns (µs/msg) |
|---|---|---|---|---|---|
| ProactorEventLoop(現況) | 37.7 / 38.0 | 41.4 / 39.1 | 67.4 / 57.2 | 25,441 / 25,760 | 20.18 / 20.35 |
| SelectorEventLoop | 29.9 / 29.5 | 31.6 / 30.4 | 48.5 / 44.2 | 32,395 / 33,076 | 13.56 / 13.57 |
| **winloop 0.6.3** | **19.5 / 19.4** | 19.8 / 19.7 | 28.6 / 27.7 | **50,030 / 50,541** | **12.03 / 11.19** |

→ winloop 對 Proactor:RTT p50 **1.94×**、p99 **2.2×**、fanout **1.75×**。

**整套真 stack(uvicorn 0.52.4 + FastAPI 0.141.1 + websockets,同 process 內量):**

| loop | HTTP p50 (µs) | HTTP p99 | WS RTT p50 (µs) | WS RTT p99 | WS msgs/s |
|---|---|---|---|---|---|
| Proactor | 451.3 | 695.6 | 128.7 | 221.3 | 7,435 |
| **winloop** | **356.7** | 614.3 | **95.8** | 168.6 | **9,576** |

→ 真 stack 的收益 **1.27–1.34×**,比 raw socket 的 1.75–1.94× 小很多 ——
因為 starlette/FastAPI 的 Python 開銷佔了大頭。**這是誠實的數字,不要用 raw 的 1.94× 去賣。**

**風險閘(這是 B02-06 / B04 當初否決 winloop 的理由,實測逐條駁回):**

| 項目 | Proactor | winloop | 判定 |
|---|---|---|---|
| uvicorn 起得來 + clean shutdown | ✅ | ✅ | 過 |
| WebSocket 收送 | ✅ | ✅ | 過 |
| ZMQ 阻塞 recv 執行緒 + `call_soon_threadsafe` | 50/50 | 50/50 | 過 |
| `pythoncom.CoInitialize()`(COM STA 執行緒) | ok | ok | 過 |
| `asyncio.to_thread` / `run_in_executor` | ok | ok | 過 |
| **`create_subprocess_exec`**(`build_info._git` 型) | rc=0 | **rc=0** | **駁回原否決理由** |
| `add_signal_handler` | NotImplementedError | **ok** | winloop 反而多支援 |
| `call_later(0.05)` 實際 | 54.4 ms | 56.1 ms | 等價 |

**未量的殘餘風險**:copycat 自己的 3566 條 pytest 沒有在 winloop 下跑過(不能碰
專案 `.venv`);TC4 真連線、群益真下單、5 條 session 同時在飛的情況沒測;
winloop 在異常路徑(socket 半關、WS 異常斷線、關機 lane 並行退訂)的行為沒測。
**這三塊是導入前必須自己補的。**

---

## 3. 對決 2:GIL 與多核

### 3.1 free-threading(3.13t)相容性 —— 裝得起來的清單

`py install 3.13t` 成功(Python Install Manager 26.3 → CPython 3.13.15 free-threading),
`sys._is_gil_enabled()` 回 `False`。逐套件實測(`pip install --only-binary=:all:`):

| 套件 | 3.13t | 說明 |
|---|---|---|
| `pyzmq` | ✅ **27.1.0**(`cp313-cp313t` wheel) | TC4 行情鏈可用 |
| `comtypes` | ✅ 1.4.16(純 Python) | — |
| **`pywin32`** | ❌ **完全沒有 wheel** | **`pythoncom` 來自 pywin32 → `capital/client.py:799` 的 `CoInitialize()` 起不來 → 下單全鏈死** |
| `fastapi` / `starlette` / `pydantic` / `pydantic-core` | ✅ | import 驗過 |
| `uvicorn`(base) | ✅ 0.52.4 | — |
| `uvicorn[standard]` | ❌ | `httptools` 無 wheel |
| `websockets` | ✅ 17.1 | — |
| `msgspec` | ❌ 無 wheel | — |
| `orjson` | ⚠️ **假成功** | pip 裝進 3.10.12 的 GIL wheel,`import orjson` → `ModuleNotFoundError: No module named 'orjson.orjson'` |
| `aiohttp` 3.x | ❌(pip 回溯到 2014 年的 0.13.1) | → **`discord.py` 整支裝不起來** |
| `winloop` | ❌ 無 wheel | winloop 與 free-threading **二選一** |

**判定:硬否決,理由是 pywin32。** 這一條符合 task 給的判準(「comtypes 裝不起來就
等於 capital 下單不能用 —— 那是硬否決」)—— 實際擋住的不是 comtypes 而是 pywin32,
但結果一樣。

### 3.2 但是收益有多大 —— 值得記在路線圖上

工作單元 = copycat TC4 listener 執行緒的真實內容
(`bytes[:-1]` → `decode("utf-8")` → `find(":")` → `json.loads` → 5 欄定點運算):

| 執行緒數 | GIL 3.13 units/s | 倍數 | FT 3.13t units/s | 倍數 |
|---|---|---|---|---|
| 1 | 309,050 | 1.00 | 264,714 | 1.00 |
| 2 | 301,111 | 0.97 | 447,005 | 1.69 |
| 4 | 292,054 | 0.95 | 824,905 | 3.12 |
| 8 | 291,607 | 0.94 | 1,445,957 | 5.46 |
| 16 | 294,503 | **0.95** | **1,739,751** | **6.57** |

單執行緒 FT 慢 17%(3.236 → 3.778 µs/unit),16 執行緒 FT 的絕對吞吐是 GIL 最佳值的 **5.6 倍**。

### 3.3 這一區最該被 copycat 看見的一張表:CPU 執行緒對 event loop 的傷害

K 條 CPU-bound Python 執行緒在跑時,loop 上 `asyncio.sleep(0.005)` 的實際 drift:

| CPU 執行緒數 | GIL 3.13 p50 | p90 | p99 | FT 3.13t p50 | p99 |
|---|---|---|---|---|---|
| 0 | 0.510 ms | 1.02 | 2.09 | 0.513 | 1.535 |
| 1 | **6.005 ms** | 6.52 | 7.48 | 0.514 | 1.532 |
| 2 | **10.013 ms** | 15.05 | 23.89 | 0.507 | 2.006 |
| 4 | **17.044 ms** | 48.61 | **92.50** | 0.510 | 2.008 |

**只要 process 裡有一條 CPU-bound Python 執行緒,event loop 的 timer 就多 5.5 ms;
四條就是 p99 92 ms。** copycat 穩態有 5 條 TC4 listener(每則推播 `json.loads`)、
5 條 KeepAlive(每則推播跑 `re.search`)、1 條 COM、最多 20 條 executor worker。
**這比 timer 精度那 12 ms 嚴重得多,而且是完全獨立的一條病因。**

### 3.4 `sys.setswitchinterval` —— 第二便宜的一行

GIL 交棒間隔預設 5 ms。調小 = loop 更快搶回 GIL,代價是背景執行緒 context switch 變多:

| CPU 執行緒 | switchinterval | loop p50 (ms) | p90 | p99 | worker units/s |
|---|---|---|---|---|---|
| 4 | 0.02 | 61.747 | 178.76 | 382.63 | 527,785 |
| 4 | **0.005(現況預設)** | **15.533** | 48.33 | **95.09** | 511,357 |
| 4 | 0.001 | 3.539 | 13.03 | 21.59 | 466,958 (−8.7%) |
| 4 | **0.0005** | **0.582** | 1.53 | **2.50** | 291,873 (−42.9%) |
| 4 | 0.0001 | 0.613 | 1.49 | 2.49 | 291,360 (−43.0%) |
| 1 | 0.005 | 5.520 | 6.41 | 10.01 | 516,093 |
| 1 | 0.0005 | 0.518 | 1.11 | 2.03 | 497,988 (−3.5%) |

**0.001 與 0.0005 之間有一道懸崖**(p99 21.6 → 2.5 ms,但 worker 吞吐 −8.7% → −43%)。
要注意 −43% 這個代價是量在**飽和的 CPU 執行緒**上;copycat 的 listener 執行緒
是事件驅動的(parse 一則就回去 `recv()` 阻塞),不是飽和態,實際代價**未量**。

### 3.5 ProcessPoolExecutor on Windows

**spawn 成本**(空 task):

| workers | ctor | 第一個結果回來 | 池熱後 map N 次 |
|---|---|---|---|
| 2 | 1.13 ms | 91.3 ms | 7.86 ms |
| 4 | 0.27 ms | 85.2 ms | 7.67 ms |
| 8 | 0.21 ms | 85.2 ms | 15.14 ms |
| 16 | 0.19 ms | 84.9 ms | 27.85 ms |

→ **spawn 一個 worker 約 85 ms,且與 worker 數無關**(平行 spawn)。

**pickle 成本**(真實 `Bar1K` 物件):

| payload | bytes | dumps | loads |
|---|---|---|---|
| 200 樣本 × 270 根 Bar1K | 4,555,521 | 94.5 ms | 102.7 ms |
| 1000 樣本 × 270 根 | 22,800,401 | ~470 ms(推估,線性外推) | 未量 |
| 一個 `StopCombo`(arm) | 103 | 0.003 ms | 0.003 ms |

**吞吐對決**(512 arms × 1000 樣本,真 `simulate_sample`,每 arm 27.6 ms,
sequential 14.12 s,`ok` 欄全部驗過 checksum 相等):

| 切法 | 熱池 (s) | 倍數 | 含 spawn (s) | 含 spawn 倍數 |
|---|---|---|---|---|
| 單執行緒 | 14.12 | 1.00 | — | — |
| ThreadPool(8) | 14.32 | **0.99**(GIL,完全沒用) | — | — |
| **proc × 8,payload 隨 task 帶**(天真切法) | 83.47 † | **0.03** | — | — |
| proc × 4,initargs 傳資料 | 6.60 | 2.14 | 7.69 | 1.84 |
| proc × 8,initargs | 7.74 | 1.82 | 8.98 | 1.57 |
| proc × 16,initargs | 8.85 | **1.60**(越多越慢) | 10.15 | 1.39 |
| proc × 8,**initializer 讀檔** | 3.30 | **4.27** | 4.41 | 3.20 |
| proc × 16,initializer 讀檔 | 3.25 | **4.35** | 4.64 | 3.04 |
| proc × 8,**shared_memory** | 3.30 | 4.28 | 4.39 | 3.22 |
| **proc × 16,shared_memory** | **3.17** | **4.45** | 4.55 | 3.10 |

† 這一列是 200 樣本的組態外推對照;同組態 512 arms × 200 樣本實測 83.47 s vs
sequential 2.81 s = 0.03×。

**為什麼 initargs 版本 worker 越多越慢?** 因為 parent 必須把 22.8 MB 依序 pickle
N 次(每個 worker 一次),那一段是**串行**的。改成 parent 只 pickle 一次落檔 /
放進 shared_memory,child 各自平行 load,才把這段攤開。

**為什麼只有 4.4× 而不是 8×?** 8 physical core(SMT 對這種吃記憶體的工作幾乎沒加成),
加上每個 worker 仍要各自 unpickle 22.8 MB(~500 ms),其中一部分落在計時窗內。
**上一輪推估的 8–12 倍,實測不成立;這台機器的實際天花板是 4.4 倍。**

---

## 4. 對決 3:交接與 ZMQ

### 4.1 `call_soon_threadsafe` vs deque+旗標

**(a) 單 producer 飽和(對照上一輪的 8.1 µs / 123k msg/s):**

| 切法 | 生產端 p50 | 生產端 p99 | 飽和吞吐 |
|---|---|---|---|
| A 每則一次 `call_soon_threadsafe` | **6.1 µs** | 18.6 µs | 141,095 msg/s |
| B deque + 旗標 | **0.2 µs** | 0.2 µs | **3,291,260 msg/s** |
| D `call_soon_threadsafe(queue.put_nowait)` | 7.9 µs | 23.8 µs | 115,998 msg/s |

→ 生產端 **30×**,飽和吞吐 **23×**。上一輪的 8.1 µs 我量到 6.1 µs(同數量級,
差異可歸因於機器狀態);上一輪的 **0.040 µs 我量到 0.2 µs —— 差 5 倍,那個數字偏樂觀**。

**(b) 5 條 producer + 限速 + 擬真 handler(~15 µs),這才是 copycat 的形狀:**

| 總速率 | 切法 | 生產端 p50 | 生產端 p99 | e2e p50 | e2e p90 | **e2e p99** |
|---|---|---|---|---|---|---|
| 500/s | A | 47.6 µs | 248 µs | 79 µs | 124 µs | 181 µs |
| 500/s | **B** | 2.4 µs | 163 µs | 45 µs | 72 µs | **100 µs** |
| 2000/s | A | 30.9 µs | 402 µs | 84 µs | 5,578 µs | **10,671 µs** |
| 2000/s | **B** | 2.3 µs | 160 µs | 40 µs | 64 µs | **86 µs** |
| 5000/s | A | 29.1 µs | 227 µs | 84 µs | 6,077 µs | 9,974 µs |
| 5000/s | **B** | 2.0 µs | 152 µs | 34 µs | 58 µs | **80 µs** |
| 10000/s | A | 25.0 µs | 327 µs | 94 µs | 6,506 µs | 11,587 µs |
| 10000/s | **B** | 1.0 µs | 159 µs | 31 µs | 56 µs | **77 µs** |
| 2000/s | C 固定 1 ms ticker | 0.8 µs | 2.6 µs | 1,241 µs | 2,339 µs | 2,477 µs |
| 2000/s | C 固定 5 ms ticker | 1.0 µs | 2.5 µs | 3,503 µs | 5,834 µs | 6,744 µs |

**三個要點:**
1. 多 producer 情境下 A 的生產端成本是 **25–48 µs p50**(不是單 producer 的 6.1 µs)——
   五條 TC4 listener 互相搶 loop 的 self-pipe + GIL。**上一輪的 8.1 µs 是單 producer 量的,
   套到 copycat 的 5 條 listener 上會低估 4–6 倍。**
2. **2000 則/秒就是 A 的崩潰點**:e2e p99 從 181 µs 跳到 10.7 ms(59×)。
3. **固定節流 ticker(C)是陷阱**:生產端最便宜,但 e2e 被 ticker 週期綁死,
   比 B 差一個數量級。**要做就做 B 的「空 deque 才排一次 drain」,不要做固定 ticker。**

### 4.2 ZMQ:阻塞執行緒 vs `zmq.asyncio`

真 `zmq.PUB`/`SUB` over `tcp://127.0.0.1`,payload = 真實形狀的 TC4 REALTIME tick JSON,
收端做完整的 `[:-1].decode → find(":") → json.loads`。

**飽和(publisher 全速):**

| 收法 | 實際吞吐 | 掉封包? | e2e p50 | e2e p99 |
|---|---|---|---|---|
| `T_only`(只 recv+parse,不交接)= 上限 | **88,159 msg/s** | 無 | 96 µs | 363 µs |
| **`T_cst`(= copycat 現況)** | 13,635 msg/s | **掉**(送 426,786 / 收 81,816) | **1,660,676 µs** | 3,806,488 µs |
| `T_deque`(現況 + 批次化) | **47,385 msg/s** | 無 | 448 µs | 2,850 µs |
| `AIO_sel`(zmq.asyncio on Selector) | 29,183 msg/s | 無 | 331 µs | 1,061 µs |
| `AIO_pro`(zmq.asyncio on Proactor) | — | — | — | **RuntimeError,起不來** |

**穩態 17,330 msg/s(都跟得上):**

| 收法 | e2e p50 | p90 | p99 | max |
|---|---|---|---|---|
| `T_only` 地板 | 69.0 µs | 94.4 | 129.1 | 304 |
| `T_cst`(現況) | 197.3 µs | 322.2 | 555.8 | 1,351 |
| **`T_deque`** | **141.8 µs** | 224.9 | **356.2** | 806 |
| `AIO_sel` | 209.3 µs | 309.5 | 416.5 | 777 |

**`zmq.asyncio` 判定:不要碰。** 三個理由,前兩個是實測的:
1. 在 `ProactorEventLoop` 上**直接 RuntimeError**
   (`Proactor event loop does not implement add_reader family of methods required for zmq`)。
   要用就得 (a) 加 `tornado>=6.1` 相依,或 (b) 全系統改 `SelectorEventLoop` ——
   後者會讓 `create_subprocess_exec` 失效、且 socket IO 比 winloop 慢 1.5×。
2. 就算換到 Selector 讓它跑起來,**它還是輸給批次化的執行緒版**(p99 417 vs 356 µs)。
3. 解碼搬到 loop 上 = 跟訊號判定 / 廣播 / 下單搶同一條執行緒(§3.3 那張表)。

---

## 5. 對決 4:dataclass

### 5.1 微基準(9 欄,對齊 `Bar1K`;600k 物件活著時 `gc.collect()`)

| 形 | 建構 µs/個 | 屬性存取 ns | bytes/個 | full GC (ms) | GC tracked | pickle B/個 |
|---|---|---|---|---|---|---|
| `dataclass(frozen=True)` | 0.6144 | 18.01 | 160.1 | **53.86** | True | 102.0 |
| `dataclass(frozen=True, slots=True)` | 0.6293 | 19.65 | 112.1 | **33.66** | True | 84.0 |
| `dataclass(slots=True)`(可變) | **0.1305** | 20.25 | 112.1 | 33.94 | True | 105.0 |
| `NamedTuple` | 0.1728 | 27.19 | 128.1 | 32.90 | True | 81.0 |
| `dict` | 0.6323 | 25.32 | 409.1 | 6.82 | **False** | 105.0 |
| `tuple` | 0.0475 | 22.21 | 120.1 | 4.71 | **False** | 77.0 |
| **`msgspec.Struct(frozen, gc=False)`** | **0.0420** | 20.99 | **96.1** | **4.40** | **False** | 81.0 |
| `msgspec.Struct(frozen)` 預設 | 0.0671 | **18.91** | 112.1 | 5.13 | **False** | 81.0 |

基線(只有那條 600k 的 list 本身)≈ 4.4 ms,所以 `msgspec.Struct` 幾乎是**零 GC 成本**。

**上一輪「600k 物件 no-slots 71.8 ms vs slots 45.9 ms」我量到 53.9 vs 33.7 ms ——
絕對值不同(機器狀態),比值 1.6× 一致,方向重現。**

`frozen=True` 的建構成本是可變版的 **4.7 倍**(0.614 vs 0.131 µs),因為 `__init__` 走
`object.__setattr__`。`msgspec.Struct` 是 frozen dataclass 的 **1/15**。

### 5.2 擬真情境:盤中逐筆的自動 GC 停頓(這張表比上面那張重要)

情境 = 150 檔自選,每檔一條 `maxlen=2000` 的逐筆 deque(長活 300,000 個物件),
持續配置 1,500,000 個新 tick 物件。用 `gc.callbacks` 量每一次**自動** GC 的實際停頓:

| 形 | µs/tick | 自動 GC 次數 | GC 總時間 | 佔 wall | **最壞單次停頓** | gen2 次數 |
|---|---|---|---|---|---|---|
| `dataclass(frozen)` ← **`StockTick` / `Tick` 現況** | 0.7558 | 150 | 47.44 ms | 4.18% | **25.53 ms** | 1 |
| `dataclass(frozen, slots=True)` | 0.8314 | 150 | 45.43 ms | 3.64% | **24.63 ms** | 1 |
| `NamedTuple` | **0.3086** | 150 | 43.59 ms | 9.42% | 27.87 ms | 1 |
| `tuple` | 0.1161 | 150 | 6.45 ms | 3.70% | 0.39 ms | 0 |
| **`msgspec.Struct(gc=False)`** | **0.1152** | **0** | **0 ms** | **0%** | **0 ms** | 0 |

**這是本區塊最違反直覺的一條:`slots=True` 對 GC 停頓幾乎沒幫助(25.53 → 24.63 ms,
在雜訊內)。** 因為兩者都是 GC-tracked,gen2 的 stop-the-world 掃的是「被追蹤的物件數」,
不是物件的 layout。`slots` 真正買到的是**記憶體 −30%** 和**長活集合 full collect −38%**,
不是盤中的那一下 25 ms 卡頓。

**要消掉那 25 ms 卡頓只有兩條路:(a) 換成不被 GC 追蹤的型別(`tuple` /
`msgspec.Struct`),或 (b) `gc.freeze()` + 調 threshold。** 前者實測歸零。

### 5.3 free-threading 下的 dataclass(附帶量到的代價)

| 形 | 3.13 屬性存取 ns | 3.13t 屬性存取 ns | 倍數 |
|---|---|---|---|
| `dataclass(frozen)` | 18.01 | 32.60 | **1.81× 慢** |
| `dataclass(frozen,slots)` | 19.65 | 33.05 | 1.68× 慢 |
| `NamedTuple` | 27.19 | 31.02 | 1.14× 慢 |
| `tuple` | 22.21 | 27.22 | 1.23× 慢 |

free-threading 的屬性存取代價不小 —— 這也解釋了 §3.2 單執行緒慢 17%。

---

## 6. 給 copycat 的具體建議(按性價比排序)

### R1 【立刻做,兩行】EcoQoS 豁免 + `timeBeginPeriod(1)`

放在 `copycat/server/__main__.py` 的 prod 進入點(`--verify` 模式也可以一起)。
**兩行缺一不可** —— 只寫 `timeBeginPeriod` 實測 3 秒後失效。

- 收益(實測):所有 timer 驅動步驟 drift p50 **12.47 → 0.556 ms**、p99 **14.2 → 1.98 ms**;
  盤中密集推播時段實際改善約 2–3 ms,盤外 / 薄量時段約 12 ms。
- 成本:兩個 ctypes 呼叫,零相依。**必須檢查回傳值**(handle 截斷會靜默失敗)。
  收尾配對呼叫 `timeEndPeriod(1)`。
- 風險:提高 timer 解析度會略增 CPU 喚醒次數與耗電 —— 桌機常駐 24 小時的場景可忽略。
  對既有契約**零影響**(不改任何 wire 格式、不改任何行為判準)。
- 判準:加了之後 `grep` 不到任何行為變化;要驗就量一支 `asyncio.sleep(0.05)` 探針。

### R2 【立刻做,一行,但要挑值】`sys.setswitchinterval`

- `0.001`:loop p99 **95.1 → 21.6 ms**,飽和 worker 吞吐 **−8.7%**。
- `0.0005`:loop p99 **95.1 → 2.50 ms**,飽和 worker 吞吐 **−43%**。
- 建議先上 `0.001`,實測 copycat 真實 listener 執行緒(事件驅動、非飽和)的吞吐影響
  之後再決定要不要進到 0.0005。**那個 −43% 是飽和態的上界,copycat 的實際代價未量。**

### R3 【高收益,中風險】TC4 listener → loop 的交接改成 deque + 旗標

六個 `call_soon_threadsafe` 產生點(`stock_engine.py:1150`、`engine.py:365`、
`futures_engine.py:565`、`index_engine.py:420`、`corr_engine.py:262`、
`capital/client.py:826/856`)。

- 收益(實測,5 producer + 限速):e2e p99 在 2000 則/秒 **10,671 → 86 µs(124×)**;
  接真 ZMQ 的飽和測試,現況設計**會掉封包且 e2e p50 飆到 1.66 秒**,批次版不掉。
- **要做「空 deque 才排一次 drain」,不要做固定週期 ticker**(實測固定 1 ms ticker
  的 e2e p50 是 1.24 ms,比旗標版差 30 倍)。
- 風險:`_handle_quote` 的呼叫次序語意會從「一則一個 callback」變成「一批一個 callback」。
  `stock_engine` 的逐筆打包(`_pending_ticks` / `_flush_ticks`)已經是這個形狀,
  但 `seq` 對齊契約(CLAUDE.md §4「快照與打包的 seq 對齊」)是兩道閘,**改交接層
  等於動到那條契約的上游,要重新走一次 review**。
- 這條**不是** stdlib-only 的問題(deque 是 stdlib),純粹是正確性風險。

### R4 【中收益,低風險,要驗】winloop

- 收益(實測,真 stack):WS RTT p50 **1.34×**、WS 吞吐 **1.29×**、HTTP p50 **1.27×**;
  搭配 R1 之後 timer drift 0.468 ms(比 Proactor 的 0.556 ms 再好一點)。
- 成本:一個 C extension 相依(`winloop>=0.6.3`,進 `[live]` extras);Windows-only
  —— 對這個專案本來就是 Windows-only,不是新限制。
- **B02-06 / B04 的兩條否決理由實測被駁回**:subprocess 正常、ZMQ 執行緒正常、COM 正常。
- 導入前必補(**本輪未量**):(a) 專案 3566 條 pytest 在 winloop 下全綠;
  (b) 五條 TC4 session 同時在飛 + 真連線;(c) 關機 lane 並行退訂 + Ctrl+C 路徑
  (`shutdown_budget` 的 83 s 預算是拿 Proactor 量的)。
- 判準:`/api/health` 加一欄印 loop class,或啟動 log 印一行。

### R5 【回測專用,不碰 runtime】ProcessPool 切法修正

`backtest/search.py` / `pipeline.py` 若要上多核:

- **絕對不要** `ex.map(fn, [(arm, samples), …])` —— 實測 **0.03×**(慢 33 倍)。
- 用 `initializer` 只傳**路徑**或 `shared_memory` 名稱,child 各自 load。
- 天花板 **4.4×**(8 physical core),含 spawn **3.0–3.2×**。不是 8–12×。
- 一個 worker spawn ~85 ms;`chunksize` 要設(512 task 用 chunksize=8–16 實測差 1.4×)。
- 這條是**離線工具**,不進 server process,對 runtime 契約零影響。

### R6 【要談】`msgspec.Struct` 取代熱點 dataclass

- 收益(實測,盤中逐筆情境):`StockTick` / `Tick`(現況 `@dataclass(frozen=True)`,
  無 slots)換成 `msgspec.Struct(frozen=True, gc=False)` → 建構 **0.756 → 0.115 µs(6.6×)**、
  自動 GC 從 150 次 / 47.4 ms / **最壞單次 25.5 ms** 變成 **0 次 / 0 ms / 0 ms**。
- **成本是這份報告裡最重的一項:它會打破 `dependencies = []`(runtime stdlib-only)。**
  msgspec 是 C extension。而且它**在 free-threading 上沒有 wheel**,等於把 R7 的門關死。
- 中間路線(**零新相依**):把 `StockTick` / `Tick` 補上 `slots=True`。
  實測買到記憶體 **160 → 112 B(−30%)**、長活集合 full collect **−38%**,
  但**買不到那 25 ms 的盤中卡頓**(slots 仍是 GC-tracked)。誠實說:這是小收益。
- 另一條零相依路線(**本輪未量**):`gc.freeze()` 在開機完成後呼叫,把長活物件移出
  gen2 掃描範圍。理論上能吃掉那 25 ms,但沒量過,不敢寫成建議。

### R7 【長期,現在不做】free-threading

- 硬否決理由只有 **pywin32 沒有 cp313t wheel**(→ `pythoncom` → capital COM apartment)。
  次要陣亡:msgspec / orjson / httptools / aiohttp(→ discord.py)/ winloop。
- 但收益量到了:解析吞吐 16 執行緒 **6.57×**(GIL 是 0.95×);
  **loop 完全不再被 CPU 執行緒拖累**(GIL 下 4 條執行緒 p99 92.5 ms → FT 下 2.0 ms)。
- 復查條件:pywin32 出 cp313t/cp314t wheel。在那之前這條路是關的。
  (替代想法:把下單拆成獨立 process 留在 GIL build —— 本輪未評估。)

---

## 7. 違反直覺 / 推翻既有結論的地方(給整份報告的勘誤)

1. **`timeBeginPeriod(1)` 單獨呼叫在 Windows 11 上是沒用的** —— 只撐 3 秒。
   必須先做 EcoQoS 豁免。這一條上一輪沒抓到,而它決定了「最便宜的改善」到底成不成立。
2. **`NtQueryTimerResolution` 全程回報 current = 1.0 ms,但那是系統級的,量不出本
   process 有沒有真的拿到 1 ms。** 拿它當判準會得到「已經是 1 ms 了不用改」的錯誤結論。
3. **12.4 ms 的 drift 在推播密集時會自己掉到 2–3 ms**(1000 則/秒時只剩 0.63 ms)。
   把它當成「全系統延遲 +12 ms」會高估收益。
4. **上一輪的 `call_soon_threadsafe` 8.1 µs 是單 producer 量的。**
   copycat 有 5 條 TC4 listener,多 producer 實測是 **25–48 µs p50 / 227–402 µs p99**。
5. **deque 批次化的 0.040 µs/call 偏樂觀,實測 0.2 µs。** 但這不重要 ——
   真正的收益在端到端 p99(10.7 ms → 86 µs),比生產端成本重要 100 倍。
6. **`slots=True` 救不了盤中的 GC 卡頓**(25.53 → 24.63 ms,雜訊內)。
   上一輪的「600k no-slots 71.8 ms vs slots 45.9 ms」是 `gc.collect()` 全量掃的數字,
   套到「盤中會不會卡」這個問題上是**換錯了題目**。
7. **ProcessPool 的天真切法比單執行緒慢 33 倍**,而且 8–12 倍的推估在這台 8 核機器上
   不成立(實測上限 4.4×)。
8. **worker 越多不一定越快**:initargs 傳資料時 16 worker(1.60×)比 4 worker(2.14×)慢,
   因為 parent 端 pickle 是串行的。
9. **`zmq.asyncio` 在 ProactorEventLoop 上根本起不來**(RuntimeError),
   而且就算換到 Selector 讓它跑起來,還是輸給批次化的阻塞執行緒版。
10. **winloop 支援 `add_signal_handler`,ProactorEventLoop 不支援。**
    這對 `run.ps1` 的 Ctrl+C graceful shutdown 路徑可能是個意外的加分項(未深究)。
11. **`pip install orjson` 在 3.13t 上會「成功」但 import 直接炸** ——
    裝得起來不等於能用,相容性矩陣一定要驗到 import。

---

## 8. 未量 / 本輪做不到的事

1. **copycat 自己的測試套件在 winloop / 新 timer 設定下沒跑過**(不能碰專案 `.venv`)。
2. **TC4 真連線、群益真下單全鏈沒測**(硬紀律禁止)。所有 ZMQ 數字都是自建
   PUB/SUB over loopback,payload 形狀對齊但不是真的 TC4。
3. **`sys.setswitchinterval` 對 copycat 真實(非飽和)listener 執行緒的吞吐代價未量。**
4. **`gc.freeze()` 能不能吃掉那 25 ms gen2 停頓,未量。**
5. **winloop 在異常路徑的行為未測**:socket 半關、WS 異常斷線、5 session 並行關機退訂、
   `shutdown_budget` 的 83 s 預算在 winloop 下是否仍成立。
6. **把下單拆成獨立 GIL process、行情走 free-threading process** 這條混合路線沒評估。
7. 所有數字都是**單機單次時段**量的;機器忙碌狀態(我自己的 benchmark 互相干擾)
   會讓絕對值漂動 ±20%,但比值在兩次重跑間都一致。
