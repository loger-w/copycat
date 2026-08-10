# Verification:/mod bars-tristate-status

2026-08-05,HEAD = 8f7d44b(自評修復後)。

## Phase 6 自動化 gate

| Gate | 指令 | 結果 | Exit |
|---|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **1720 passed**, 1 warning(baseline 1691 → +29 新測試) | 0 |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| Golden gate | replay four_tigers + five_tigers → `python -m copycat validate` | **42/42 PASS** | 0 |
| 前端測試 | `npm test`(frontend/) | **1129 passed** / 77 files(baseline 1115 → +14) | 0 |
| 前端型別 | `npx tsc -b` | 無輸出(TSC_OK) | 0 |
| 前端 lint | `npx eslint src` | 無輸出(ESLINT_OK) | 0 |

TDD 紅階段證據(implementer 回報,各 [red] commit):
- 後端 commit 8fd7999:33 failed + test_bars collection error(型別未存在);test_futures_bars 全綠不動(白名單 10)。
- 後端 commit 35347ff:4 failed,含 `KeyError: 'weird'`(worst_status 查表)= review 判定的失效樣態原文重現。
- 前端 commit 72acbd4:7 failed(接線測試 `expected 1 to be 2` = 真的量到沒重打)。
- 前端 commit 5f195f3:2 failed,同一 `TypeError: Cannot read properties of undefined (reading 'length')` = review F1 描述的鏈路。

## Phase 7 真實環境驗證

盤中紀律:8721 有 prod server 跑著(sha 8ef1346,10:31 起)→ 不動它;
走 fake source + 8723(整條路不碰 ZMQ)。腳本:scratchpad/tristate_verify_server.py
(三態依股號注入:1111=timeout / 2222=ConnectionError / 3333=ok+空 / 其他=有資料)。

### HTTP 層(curl 對 8723)— 全 PASS

| 案例 | Response | SC |
|---|---|---|
| `/api/stock/bars/1111?tf=D` | `{"code":"1111","tf":"D","bars":[],"status":"timeout"}` | SC-1 |
| `/api/stock/bars/2222?tf=D` | `{"bars":[],"status":"disconnected"}`(source raise ConnectionError → engine 轉換) | SC-2 |
| `/api/stock/bars/3333?tf=D` | `{"bars":[],"status":"ok"}` | SC-3(unit 可驗界;fake 注入) |
| `/api/stock/bars/2330?tf=D` | 3 根 bars + `"status":"ok"` | 白名單 |
| 1111 於 15s 內重打 | 仍 `"status":"timeout"`(負向快取保真,不洗白) | SC-5 |
| 1111/2222 `?tf=1&days=5` | 分 K 路徑同樣 timeout / disconnected | SC-1/2 |

### 畫面層(vite proxy 暫指 8723,claude-in-chrome 截圖對照)— 全 PASS

截圖存 `docs/specs/bars-tristate-status/screenshots/`:
- `sc1-timeout.jpg`:1111 日K → K 線圖區置中**灰字**「等待 TC4 回應中…(自動重試)」✅
- `sc2-disconnected.jpg`:2222 日K → 置中**紅字**「TC4 連線中斷,K 線暫不可用(自動重試中)」✅
- `sc3-ok-empty.jpg`:3333 日K → CandleChart 掛載(BB 鈕列在)+「無 K 線資料」✅
- `whitelist-data-renders.jpg`:2330 日K → 3 根 K 線正常渲染(有資料照畫,status 不干擾)✅

SC-4(20s 自動重試)由 hook 層 fake-timers 接線測試覆蓋(timeout 20s 後 fetch 第二次、
ok 60s 仍一次、未知值不觸發),真環境不另量。

清理:vite.config BACKEND 已 revert 8721(git status 乾淨)、8723 無 listener、
prod 8721 health 正常未受影響。
