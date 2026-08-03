# Verification — next-time-behavior-fixes(2026-08-03)

## 自動化(收尾最終,含 review 修復後;主 session 親跑或親驗 implementer 回報)

| Gate | 結果 |
|---|---|
| `pytest -q` | **1493 passed**(refactor 輪基準 1486 → M1-M4 +6 → review 修復 +1) |
| `npm test` | **913 passed / 66 files**(基準 893 → M4-M9 +12 → review 修復 +8) |
| `ruff check copycat tests` | All checks passed! |
| `pyright` | 0 errors, 0 warnings |
| `npx tsc -b` / `npx eslint src` | exit 0 / exit 0 |
| `copycat validate` | **42/42 PASS** |

TDD:M1-M9 與收尾 review 的行為修全部紅測試先行,紅因逐條驗證
(M4 分母 90 vs 60、M5 [0,0] flat、M6 bar 壓成 16%、M9 TypeError、TQ-1 close 中斷、
FC-3 單列 0 元可點);TQ-4 斷言位置以 mutation(拔 except publish)實測會咬。

## 真實環境(fake source + uvicorn port 8899,零 ZMQ — 盤中不起第二台連 TC4)

SMOKE PASS 6/6:
- `/api/stock/state/2330`:M3 六個死欄位(cum_inner/cum_outer/tc4/backfilling/stkfut_prod/
  meta.y_close)全消;`vwap_vol` 存在、舊 `vol` 不存在(FC-2 改名後狀態)
- `/api/stock/bars/2330?tf=D&days=abc` → **200**(M1;修前 400 BAD_DAYS)
- health shape / names 2401 / watchlist / BAD_CODE 400 / index 未配置 503 全部照舊
- capital 登入失敗降級路徑照舊(其餘引擎照起)

## UI 過目

M5/M6/FC-3 的畫面差異(鎖停 badge、市價列、閃電梯 0 值歸一)**需要鎖停日的簿**才觀察得到,
盤後 fake 環境不可見 — 留待下個鎖停/盤中時段 user 過目(known risk 已記
code-review-round-1.json)。其餘 item(M1/M2/M3/M4/M9)無畫面差異,以測試 + smoke 為證。
