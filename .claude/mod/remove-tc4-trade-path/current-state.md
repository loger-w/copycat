# Current State:remove-tc4-trade-path(Phase 1 現況表)

日期:2026-08-04。任務來源:`docs/next-time.md` §「2026-07-28(capital-order Phase 3 順手清單)」
兩條 `[ ]`:舊 TC4 trade 路刪除 + app.py sentinel 解耦。

## 1. 刪除目標與其 caller map(grep 全量,含動態用法檢查)

### Backend(全部已標 deprecated,TradeRuntime 自 2026-07-28 起 lifespan 不啟動)

| 檔案 | 內容 | 被誰引用(import) |
|---|---|---|
| `copycat/server/trade.py` | `TradeRuntime` + `TradeSource` Protocol + 6 個錯誤類(NotReady/LiveBlocked/ConfirmRequired/PreviewExpired/InvalidOrder/SymbolNotAllowed) | `app.py:63-72`;`tests/server/test_trade_gates.py` |
| `copycat/live/tc4_trade.py` | `TC4TradeSource`(ZMQ 下單 client) | `tests/live/test_tc4_trade.py`(僅此;production 零 caller) |
| `copycat/server/fake_trade.py` | `FakeTradeSource`(TXO_FAKE_TRADE 故障注入) | **零 import caller**(原經 app.py TXO_FAKE_TRADE 分支動態啟用,該分支已在 SC-11 移除) |

動態用法檢查:grep `TXO_FAKE_TRADE` → 僅 fake_trade.py 自身 docstring + CLAUDE.md 記載(app.py 已無該分支)。無 template string / reflection 載入點。

### app.py 內的 trade 區段(隨上述刪除)

- `app.py:63-72` import `server.trade` 8 個名稱。
- `app.py:18-23` import `trade_models` 4 個名稱(BrokerRejectedError / OrderRequest / TouchanceDownError / millipts_from_price_str)。
- `app.py:119-121` `DEFAULT_TRADE` sentinel 定義。
- `app.py:142-152` `PreviewBody` / `SubmitBody`(僅 trade routes 用)。
- `app.py:238` `trade_source` 參數。
- `app.py:274-280` lifespan 內 `app.state.trade = None` + deprecated 註解。
- `app.py:434-436` futures 接線 fallback `futures_source is None and trade_source is DEFAULT_TRADE`。
- `app.py:457-460` **corr 接線同款 fallback**(`corr_source is None and trade_source is DEFAULT_TRADE`)— 任務文字只點名 futures,但刪 `trade_source` 參數必然一併處理 corr,否則 corr 正式啟動斷線。
- `app.py:495` 關機順序註解 `→ (trade) →`。
- `app.py:901-973` trade 區段:`_TRADE_ERROR_MAP`(8 entries)+ handler 迴圈 + `_broker_rejected` handler + `_trade()` helper + 4 條 `/api/trade/*` routes。

### ⚠ 不能刪的部分(capital 依賴,grep 實證)

1. **`copycat/live/trade_models.py` 整檔保留**:`capital/client.py:74` import `BrokerRejectedError`(`client.py:639` 實際 raise)。任務清單也未列此檔。`tests/live/test_trade_models.py` 隨之保留。
2. **`BrokerRejectedError` exception handler(app.py:924-935,400 + err_code/err_msg)**:`capital_api.py:7,270` 明文「AuditWriteError/BrokerRejectedError 沿用 app.py 既有 handler」。刪掉 = capital 下單被 -22 等退單時從 400 BROKER_REJECTED 變 502 TC4_DOWN(全域 handler 吞掉)→ **靜默破壞群益錯誤契約**。
3. **`AuditWriteError` handler(現在藏在 `_TRADE_ERROR_MAP` 裡,500 AUDIT_WRITE_FAILED)**:同上 capital 沿用。`_TRADE_ERROR_MAP` 刪除時此 entry 必須以獨立註冊存活。
4. `copycat/server/audit.py`:capital 審計仍在用(AuditWriteError 定義處)。僅 docstring 提及 TradeRuntime/TC4TradeSource(過時,可順手校正)。

`_TRADE_ERROR_MAP` 其餘 7 個 entry 對應的例外:6 個定義在 server/trade.py(隨檔亡)、TouchanceDownError 定義在 trade_models(保留定義,但刪 handler 後 production 無人 raise → handler 一併刪)。

### Frontend(全部已標 @deprecated)

| 檔案 | 被誰引用 |
|---|---|
| `src/hooks/useTrade.ts` | **零 importer**(useCapital.ts 僅註解提及;fetchJson/parseError 是檔內 private) |
| `src/components/OrdersList.tsx` | 僅 `OrdersList.test.tsx` |
| `src/components/OrderConfirm.tsx` | 僅 `OrderConfirm.test.tsx` |
| `src/types.ts` trade 區段 6 個 interface(`TradeAccount` / `OrderPreviewBody` / `OrderPreviewResult` / `SubmitResult` / `OrderRow` / `OrdersView`,types.ts:56-105) | 僅上述三檔 + 兩個測試檔。capital 區段(types.ts:107+)自有型別,零交集 |

現行 UI(RightRail.tsx / OrderPanel.tsx)已全面走 `CapitalOrdersList` + `useCapital`,不碰任何刪除目標。
`/api/trade` 字串 grep 全 frontend 僅 useTrade.ts 命中(vite proxy 是 `/api` 整段轉發,無 per-route 設定)。

### 測試檔處置

| 測試檔 | 處置 | 理由 |
|---|---|---|
| `tests/server/test_trade_gates.py` | 刪 | 測 TradeRuntime 本體 |
| `tests/live/test_tc4_trade.py` | 刪 | 測 TC4TradeSource 本體 |
| `tests/server/test_trade_app.py` | 刪 | 測「/api/trade/* 恆 503」— 該行為本身要變 404(route 消失) |
| `tests/server/test_capital_api.py` | 改 | `make_client` 的 `trade_source` 參數(:137,144)移除;`TestTradeRoutesDeprecated`(:571-576,斷言 503)刪或改 404 |
| `tests/live/test_trade_models.py` | 留 | trade_models.py 保留 |
| `frontend OrdersList.test.tsx` / `OrderConfirm.test.tsx` | 刪 | 隨元件亡 |

### 殘留註解引用(唯讀提及,不構成依賴)

- `copycat/live/tc4.py:154,172,211,512` — 引 tc4_trade 的 review finding 作設計依據(歷史出處引用,保留)。
- `tests/conftest.py:21` — 註解提及 tc4_trade.py 的 sys.path 慣例(刪 tc4_trade 後改提 tc4.py 即可)。
- `copycat/server/audit.py:1-5,23` — docstring 寫者描述過時(順手校正為 capital)。
- `copycat/capital/mapping.py:129` — 引 trade_models 手法(trade_models 保留,不動)。

## 2. sentinel 解耦(第二項任務)

現況:`__main__.py:18` 只傳 `trade_source=DEFAULT_TRADE, stock_source=DEFAULT_STOCK, index_source=DEFAULT_INDEX`;futures(app.py:434-436)與 corr(app.py:457-460)靠 `trade_source is DEFAULT_TRADE` 判「正式啟動」。

目標:`__main__.py` 顯式傳 `futures_source=DEFAULT_FUTURES, corr_source=DEFAULT_CORR`;app.py 刪 `trade_source` 參數與兩處 fallback 分支。`DEFAULT_TRADE` sentinel 隨之刪除。

## 3. Baseline

- Backend:`pytest -q` 跑中(結果見 change-spec 附記)。
- Frontend:`npm test` → **74 files / 994 tests 全 PASS**(2026-08-04 16:57)。

## 4. 現況 vs 目標對照

| 面向 | 現況 | 目標 | 對 caller 影響 | Backward compat |
|---|---|---|---|---|
| `/api/trade/*` 4 條 route | 存在,恆 503 TRADE_NOT_READY | 不存在 → 404 | 唯一 client useTrade.ts 同輪刪除;外部無人打(本機工具) | **契約改動(503→404),user 已在任務文字拍板** |
| `create_app(trade_source=…)` | 參數存在(sentinel 借用) | 參數刪除 | 呼叫點:__main__.py、test_capital_api.py、test_trade_app.py(刪) | 內部 API,同 repo 同輪改完 |
| capital 錯誤契約 | BROKER_REJECTED 400 / AUDIT_WRITE_FAILED 500 | **不變** | — | 白名單保護 |
| 正式啟動接線(futures/corr/stock/index) | trade sentinel 借用 | 各自顯式 sentinel | __main__ 一處 | 行為等價(白名單驗證) |
