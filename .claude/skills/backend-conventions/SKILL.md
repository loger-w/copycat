---
name: backend-conventions
description: Python / FastAPI 後端風格慣例(專案特化)。寫或改 copycat/ 下任何 .py、新增 endpoint、外部 IO client、錯誤處理、pytest 測試前先讀。
---

# Python 風格(專案特化)

> 2026-07-28 自專案 CLAUDE.md §2 整節遷移(neigui backend-conventions 同款瘦身),內容未改。

只列非顯而易見、跨檔一致的:

- **`from __future__ import annotations` 強制**寫在每個 `.py` 第一行(註解後)。
- Type hints **無例外**:函式參數 + 回傳、module-level globals。`dict | None` / `list[dict]` 風格,不要 `Optional` / `List`。
- **Logging**:`logger = logging.getLogger(__name__)`,**禁止** `print`。
- **FastAPI error contract**(若採 FastAPI 後端):`raise HTTPException(status_code=..., detail={"error": "<code>"})` — frontend 依賴 `detail.error` 字串解析。新 endpoint 不要塞自由文字。
  - 502 = upstream 故障;503 = 服務尚未就緒;400 = 用戶錯;404 = 找不到。
- **全域 exception handler**(從第一天就開):`@app.exception_handler` 在 `main.py`,route 內**只 raise 不 catch**。避免 trash-cmoney `routes/options.py` 6 處重複 try/except 的債。
- **外部 IO 慣例**(類比 trash-cmoney `services/finmind.py` 樣板):
  - Module-level singleton client,不要每次 `new`。
  - 所有外部呼叫先過 rate limiter / token bucket。
  - JSON cache 用 `atomic_write_json` / `read_json`,寫入帶 `_cache_version`,版本 bump 即失效。
  - 同 key 並發走 `_run_once` inflight dedup。
- **async**:`httpx.AsyncClient(timeout=30.0)` + `await`。同步阻塞函式不要混進 route handler。WebSocket / Stream 用 `asyncio` event loop。
- **錯誤處理**:catch 要具體(`httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException`,以及 DQ4 SDK 特有 exception),不裸 `except`。`except Exception` 只在 route 邊界 + 一定要 `logger.exception` + 轉 502。
- **測試**:pytest + `asyncio_mode = "auto"`,async test 不用 `@pytest.mark.asyncio`。Mock 走 `monkeypatch`,不 `unittest.mock`。
- **Ruff**:line-length 100。Format 跟既有檔對齊,不順手重排既存格式。
  判「既有檔是否已 formatted」用 `git show master:<file> > tmp.py && ruff format --check tmp.py`,**不要用 stdin `ruff format --check -`**(2026-08-28 真踩:stdin 模式對未 format 的 test_client.py 靜默回「已 format」,隨後整檔 format 把不相干既有行一起重排;還原 = checkout master 版重跑確定性替換腳本)。只對**新檔** format 最省事。
- **pyright basic**(從第一天就開)— type hint 已寫齊,加 checker 拿免費 invariant check。


---

# §8 遷移附錄(2026-08-10,內容未改)

## HTTP / 依賴 / 演算法選型

- **urllib 的 SSL read timeout 以 `TimeoutError` 拋出,不包在 `URLError`**,retry 的 except 集合
  要含它,否則長跑批次中途炸。(2026-07-07,Trigger:寫任何 HTTP retry)
- **純 `uvicorn` 沒有 WebSocket protocol 支援**,WS upgrade 直接 404(錯誤訊息不提示缺件)—
  要 `uvicorn[standard]`。(2026-07-18,Trigger:新增 WS endpoint / 部署裝依賴)
- **`statistics.correlation` 是 stdlib(3.10+)且夠快**:1800 樣本 0.15ms、六腿五對三窗完整 tick
  6.43ms。相關係數不必自寫增量統計量(整批重算讓「增量 vs 整批一致」恆真);常數序列拋
  `StatisticsError`,catch 後回 `None`。(2026-07-30,Trigger:要算相關/共變異數想引 numpy 或自寫時)
- **長跑 pipeline 必須有進度 log**:round 1 fade-search 跑 6 小時全程黑箱。fold/arm/generation
  邊界各 log 一行(含完成比例與耗時)。(2026-07-11,Trigger:預期 >10 分鐘的批次/搜索迴圈)

## env / 設定讀取

- **server 不載 dotenv 檔**:runtime 讀設定一律「`name in os.environ` 即用(含空字串 = 未設,
  可壓制 .env)→ 否則 repo root .env」逐 key fallback(capital/factory 慣例;cli/notify 舊慣例是
  「僅未設才 fallback」,下單開關類安全 key 必須用新語意)。讀 .env 用 `utf-8-sig` + never-raise
  (Windows BOM 讓首 key 靜默失效 — 真踩過)。測試側 `tests/conftest.py` 全域中和 dotenv +
  delenv CAPITAL_*(否則真憑證流入測試,最壞載真 SKCOM DLL → segfault,實測過)。
  (2026-07-28,Trigger:新增 env 讀取 / env 相依測試)

## Rollover / 兩段式狀態機

- **rollover stage1/stage2 可在同一同步區塊內連發(快路徑),掛兩段通知的模組不能假設中間有
  await**(2026-08-04 stock-signals 實證):快路徑(週六補市日 / checkpoint 沒跑)在同一則 quote
  內連跑 stage1→stage2,「stage1 排非同步預備、stage2 消費」的設計在此路徑預備必為空;更陰的是
  預備 job 事後完成的殘留會被下次快路徑誤當有效 → 用日別標記(basis_date)驗證,不符即丟。
  (Trigger:掛 rollover 兩段通知 / stage1 預備 stage2 消費的設計)
