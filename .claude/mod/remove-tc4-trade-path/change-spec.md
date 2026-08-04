# Change Spec:remove-tc4-trade-path

分流判定:user 帶**已成形改法**(任務文字即 next-time.md 2026-07-28 清單原文,逐檔點名 +
契約改動已拍板「503→404」+ 解耦做法已指明「__main__ 顯式傳 DEFAULT_FUTURES」)→ grilling
縮為確認;無 counter-proposal(唯一新發現是 capital handler 依賴,屬 constraint 非替代方案)。
規模分流:S 級(純刪除 + 一處接線改寫,行為面收斂良好)。

## 成功條件(可驗收)

- SC-1:`copycat/server/trade.py`、`copycat/live/tc4_trade.py`、`copycat/server/fake_trade.py`、
  `frontend/src/hooks/useTrade.ts`、`frontend/src/components/OrdersList.tsx`、
  `frontend/src/components/OrderConfirm.tsx` 及對應測試檔(`test_trade_gates.py` /
  `test_tc4_trade.py` / `test_trade_app.py` / `OrdersList.test.tsx` / `OrderConfirm.test.tsx`)
  自 repo 消失;repo 全文 grep `TradeRuntime|TC4TradeSource|FakeTradeSource|TXO_FAKE_TRADE|useTrade|api/trade`
  在 production code 的**符號引用(import / 呼叫 / URL 字串)**零命中
  [amendment 2026-08-04: R1 — grep 語意釐清為符號引用;歷史出處註解不算,
  但 useCapital.ts 的 useTrade 註解已列入 Commit 2 校正,校正後亦不再命中]
  (docs / CLAUDE.md 記載除外)。
- SC-2:`GET /api/trade/account` 回 **404**(route 不存在)。量法
  [amendment 2026-08-04: R4 — 原寫法 create_app() 無 source 會走 _default_source()
  建真 TC4 session]:以 `tests/server/test_capital_api.py` 的 `make_client`
  (FakeQuoteSource + raise_server_exceptions=False)建 TestClient,
  `client.get("/api/trade/account").status_code == 404`。
- SC-3:`create_app` 無 `trade_source` 參數;`__main__.py` 顯式傳
  `futures_source=DEFAULT_FUTURES, corr_source=DEFAULT_CORR`;`DEFAULT_TRADE` sentinel 刪除。
  量法 [amendment 2026-08-04: R2 — __main__ 原本零測試覆蓋,漏傳 DEFAULT_CORR 的失效樣態
  是 corr/river 面板整段空白零錯誤訊號]:新增 `tests/server/test_main_wiring.py`(🟢),
  monkeypatch `uvicorn.run` 與 `create_app`,斷言 `main()` 傳給 create_app 的 kwargs
  恰為 `{stock_source: DEFAULT_STOCK, index_source: DEFAULT_INDEX,
  futures_source: DEFAULT_FUTURES, corr_source: DEFAULT_CORR}` 且不含 `trade_source`。
  (不採 real-env 重啟驗證:夜盤時段不重啟跑著的 server,CLAUDE.md §8 紀律;
  下次自然重啟時順帶目視 futures/corr/river 三面板有值。)
- SC-4:全 gate 綠:`pytest -q` + `ruff check` + `pyright` + `copycat validate` +
  frontend `npm test` + `npx tsc -b` + `npx eslint src`。
- SC-5:types.ts trade 區段 6 interface 刪除,`npx tsc -b` 證明零殘餘引用。

## 不能破壞的既有行為白名單(比新行為更重要)

- WL-1:**capital 錯誤契約**:`BrokerRejectedError` → 400 `{"detail":{"error":"BROKER_REJECTED","err_code":…,"err_msg":…}}`;
  `AuditWriteError` → 500 `AUDIT_WRITE_FAILED`。兩個 handler 必須在 app.py 存活
  (capital_api.py:7,270 明文沿用)。驗法:既有 `tests/server/test_capital_api.py` 的
  broker-rejected / audit 相關測試不動、照綠。
- WL-2:**正式啟動接線等價**:`python -m copycat.server` 啟動時 stock / index / futures /
  corr / capital 引擎照建(futures 走 `_default_futures_source()`、corr 走
  `_default_corr_source()`);測試路徑(全參數 None)照舊零連線。
  驗法 [amendment 2026-08-04: R2]:SC-3 的 `test_main_wiring.py`(None 半邊由既有
  test_capital_api / test_stock_engine 等 fake-source 測試覆蓋)。
- WL-3:`copycat/live/trade_models.py` 與 `tests/live/test_trade_models.py` 不動
  (capital/client.py 依賴 BrokerRejectedError)。
- WL-4:`copycat/server/audit.py` 的行為(append_audit / AuditWriteError / prefix 分檔)不動
  (capital 審計在用);僅 docstring 寫者描述校正。
- WL-5:全域 `Exception` handler(502 TC4_DOWN)、capital_api 顯式註冊的四類例外映射、
  其餘所有 route(quote / stock / index / futures / corr / river / signals / capital)不動。
- WL-6:frontend 現行 UI(RightRail / OrderPanel / CapitalOrdersList / useCapital)零改動;
  既有 994 個 frontend 測試除被刪的兩檔外照綠。

## Backward compat / migration

- `/api/trade/*` 503→404:**契約改動,user 拍板**。唯一 client(useTrade.ts)同輪刪除;
  無外部 consumer(本機單人工具)。無資料 migration(TradeRuntime 從未在現行 server 持久化
  任何狀態;audit orders-*.jsonl 舊檔僅是歷史記錄,讀取端本來就不存在)。
- `create_app` 簽名變更:內部 API,repo 內呼叫點(__main__、test_capital_api)同輪改完。
- 可逆性:純刪除 + 單 commit 接線改寫,`git revert` 即可整段還原。

## Out of scope

- `trade_models.py` 瘦身(移除 OrderRequest / millipts_from_price_str / to_neworder_param /
  TouchanceDownError 等 capital 不用的部分)— 記 next-time,本輪不動(任務清單未列)。
- `tc4.py` 內引用 tc4_trade review finding 的歷史註解(:154,172,211,512)— 出處引用,保留。
- audit.py `prefix="orders"` 預設值調整(現無人用 orders prefix)— 行為面不動。
- [amendment 2026-08-04: R7] `frontend/src/lib/trade-text.ts` 的 `orderStatusText` /
  `orderSideText` 本輪後成 test-only(唯一 production consumer 是被刪兩元件;檔案本身
  由 `tradeErrorText` / `shortSymbol` 的既有 consumer 共用,不可整檔刪)— 瘦身記
  next-time,本輪不動。
- CLAUDE.md / next-time.md 的記載更新 → 收尾 chore commit 做,不算 code scope。

---

# Diff 級 spec(Phase 3)

三類分離:🔴(行為改動:刪除 + 503→404 + 簽名變更)+ 🟢(test_main_wiring.py,
[amendment 2026-08-04: R2])+ 🔵(註解 / 文件校正)。
順序 **🟢[red] → 🔴[green] → 🔵** [amendment 2026-08-04: R5 — 原宣告「🔵 → 🔴」與 commit
標號矛盾;🔵 內容全是描述被刪物件的註解,必須後行][amendment 2026-08-04: 自評 F4 —
實際 commit 順序為紅測試先行(🟢 test [red] → 🔴 fix [green] → 🔵),符合鐵則 C,
此處記載對齊 git 歷史]。

## Commit 1(🔴 行為改動):刪除舊 TC4 trade 路 + sentinel 解耦

### 刪檔

- `copycat/server/trade.py`
- `copycat/live/tc4_trade.py`
- `copycat/server/fake_trade.py`
- `tests/server/test_trade_gates.py`
- `tests/live/test_tc4_trade.py`
- `tests/server/test_trade_app.py`
- `frontend/src/hooks/useTrade.ts`
- `frontend/src/components/OrdersList.tsx`
- `frontend/src/components/OrderConfirm.tsx`
- `frontend/src/components/OrdersList.test.tsx`
- `frontend/src/components/OrderConfirm.test.tsx`

### `copycat/server/app.py`

- 刪 import:`from copycat.server.trade import (…)` 全段(:63-72);
  `trade_models` import 縮為 `BrokerRejectedError` 一個名稱(OrderRequest /
  TouchanceDownError / millipts_from_price_str 隨 routes 亡)。
- [amendment 2026-08-04: R3] `from typing import …` 移除 `Literal`(刪
  PreviewBody/SubmitBody 後全檔零使用 → ruff F401;其餘 Final / cast / TypeVar /
  Callable 仍在用)。
- 刪 `DEFAULT_TRADE` sentinel(:119-121 併註解);`DEFAULT_STOCK` 等其餘 sentinel 不動。
- 刪 `PreviewBody` / `SubmitBody`(:142-152)。
- `create_app` 簽名刪 `trade_source` 參數(:238)。
- lifespan:刪 `app.state.trade = None` + deprecated 註解段(:274-280)。
- futures 接線(:430-443):條件簡化為
  `futures_source is DEFAULT_FUTURES → _default_futures_source();else cast(source)`,
  刪 `trade_source is DEFAULT_TRADE` fallback 分支;註解改述「__main__ 顯式傳
  DEFAULT_FUTURES」。
- corr 接線(:457-463):同款簡化(`corr_source is DEFAULT_CORR` 單一判準)。
- 關機順序註解(:495)刪 `(trade)`。
- trade 區段(:901-973)整段改寫:
  - 刪 `_TRADE_ERROR_MAP` + handler 註冊迴圈、`_trade()` helper、4 條 `/api/trade/*` routes。
  - **保留並獨立註冊**兩個 capital 沿用的 handler:
    `AuditWriteError` → 500 `AUDIT_WRITE_FAILED`(從 map 改為單獨 `app.add_exception_handler`
    或 decorator);`_broker_rejected`(:924-935)原樣保留。
    區段註解改述「capital 沿用的例外映射(capital_api.py 明文依賴)」。

### `copycat/server/__main__.py`

- import 改為 `DEFAULT_FUTURES, DEFAULT_INDEX, DEFAULT_STOCK`(+ 既有)+ `DEFAULT_CORR`;
  `create_app(...)` 傳
  `stock_source=DEFAULT_STOCK, index_source=DEFAULT_INDEX, futures_source=DEFAULT_FUTURES, corr_source=DEFAULT_CORR`,
  不再傳 `trade_source`。

### `tests/server/test_capital_api.py`

- `make_client` 刪 `trade_source` 參數(:137,144)。
- `TestTradeRoutesDeprecated`(:571-576)改為斷言 404(route 已除役)並更名
  `TestTradeRoutesRemoved` — 這是 SC-2 的落點;或等價新測試。
  (503 斷言 = 「該紅的既有測試」,合法改 assertion 通道:spec 已事前標記。)

### `frontend/src/types.ts`

- 刪 trade 區段(:56-105)6 個 interface:`TradeAccount` / `OrderPreviewBody` /
  `OrderPreviewResult` / `SubmitResult` / `OrderRow` / `OrdersView` + 區段註解。

### 既有測試預期

- 該紅(🔴):test_capital_api.py 的 503 斷言(改 404)。刪除的 5 個測試檔不算紅。
- 不該紅:其餘全部。test_capital_api 其餘測試(含 broker-rejected 400 / audit 500)
  一根都不准動。
- [amendment 2026-08-04: R6] **名稱相近但必留**:`tests/server/test_trade_audit.py` 與
  `tests/server/test_audit_prefix.py` 只測 `copycat/server/audit.py`(WL-4 的唯一直接
  覆蓋)— **不得誤刪**。
- [amendment 2026-08-04: R9] 數字對賬:待刪 backend 3 檔 = **44 tests**(collect-only
  實測)、frontend 2 檔 = **9 tests**(vitest 實測)。目標:backend
  1664 − 44 + test_main_wiring 新增數 ≥ **1620** passed、0 failed;frontend
  **72 files / 985 tests** passed。

## Commit 2(🟢 新測試):`tests/server/test_main_wiring.py`

- [amendment 2026-08-04: R2] 先紅(現行 `__main__.py` 傳 trade_source、未傳
  futures/corr → 斷言 fail)→ 刪除+解耦 commit 的 `__main__.py` 改動使其綠。實際
  commit 順序 🟢[red] → 🔴[green] 分開 [amendment 2026-08-04: 增量 review AC-1 —
  原句「🔴 → 🟢」與 git 相反;本檔「Commit N」標號 = 內容分類,非落地順序,
  實際順序見 Diff 級 spec 開頭宣告]。
- 內容:monkeypatch `uvicorn.run`(no-op 捕 app)與 `copycat.server.app.create_app`
  (spy 捕 kwargs),呼叫 `main()`,斷言 kwargs 恰為
  stock/index/futures/corr 四個 DEFAULT_* 且無 `trade_source` 鍵。

## Commit 3(🔵 註解 / 文件校正,行為零改動)

- `copycat/server/audit.py`:docstring 寫者描述改為 capital CapitalClient(過時的
  TradeRuntime / TC4TradeSource 描述移除);`audit_path` 的 prefix 註解同步校正。
- `tests/conftest.py:21`:註解 `live/tc4.py / tc4_trade.py` 改 `live/tc4.py`。
- [amendment 2026-08-04: R1] `frontend/src/hooks/useCapital.ts:9,83,87`:useTrade
  引用改述(fetch helper / parseError 慣例自述,不再指向已刪檔)。
- [amendment 2026-08-04: R6] `tests/server/test_audit_prefix.py:1,3` docstring 的
  「orders-*(TC4 trade)」與 test_trade_audit 描述同步校正。
- 測試斷言不動,pytest 結果與 Commit 2 後完全相同。

## 收尾 chore(不入三類):CLAUDE.md §0 corr_engine 段 deprecated 記載移除、
`.env` 段 `TXO_FAKE_TRADE 已失效` 記載移除、next-time.md 兩條 `[ ]` 勾銷、
trade_models 瘦身候選 + trade-text.ts 瘦身候選記入 next-time
[amendment 2026-08-04: R7]、
next-time.md 兩處失準同步 [amendment 2026-08-04: R8]:`:514` 的「trade_source 啟動
旗標佈線」改述為 `futures_source=DEFAULT_FUTURES`;`:179` 的 TCPY 路徑計數把
`live/tc4_trade.py:91` 移除(production 三處 → 兩處,收斂條件同步改)。

## 新測試清單

- SC-2 的 404 測試(由 test_capital_api 503 測試改寫)。
- SC-3 的 `tests/server/test_main_wiring.py` [amendment 2026-08-04: R2]。

## Baseline(2026-08-04)

- backend `pytest -q`:**1664 passed**(69.8s);待刪 3 檔 collect = 44
- frontend `npm test`:**74 files / 994 tests passed**;待刪 2 檔 = 9 tests

self_review_head: b20356f
