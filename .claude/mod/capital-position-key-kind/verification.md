# verification(mod/capital-position-key-kind,2026-08-05)

## Phase 6 自動化 gate(main session 親跑,HEAD = 4b7a011)

| gate | 指令 | 結果 |
|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | **1691 passed**, 1 warning, 78.03s(baseline 1678 + 13 新測試)|
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS |
| 前端測試 | `npm test`(frontend/) | **1002 passed** / 72 files |
| 前端型別 | `npx tsc -b` | OK(exit 0)|
| 前端 lint | `npx eslint src` | OK(exit 0)|

exit code 皆 0,單獨執行無 pipe 汙染。

## TDD / mutation 證據(implementer 回報,main session 抽核)

- 🔴 backend round 1:3 failed 先紅(position_for 簽名 / 複合鍵 carry-over / profit kind)。
- 🔴 frontend round 1:2 failed 先紅(close body 缺 kind / 缺種類標籤);React key 測試
  反證(rowKey 回退 stock_no → duplicate key warning 真的紅)。
- review 修復輪:5 failed 先紅(審計 kind KeyError / market 掃描 / 重複鍵 warning /
  422);A-2 mutation(拿掉 market="sec" → 誤導性「無部位可平」重現)。
- 兩個 review lens 各自實跑反證(inflight 兩鍵分離、getNodeText 守門)。

## Phase 7 真實環境驗證

SC-1~SC-4 由零 IO store/client 測試全鏈覆蓋(COM 層 FakeCom,test 沙盒群益端未開通
1097 — 既有限制)。**SC-7(真環境)未完成,已記 next-time 待補**:白天 session 群益
登入正常後打 `GET /api/capital/positions` + 目視面板部位列(單一種類帳戶畫面應與現況
一致,sec 列多「現/資/券」小字);同檔資+集保並存為低頻狀態,兩列並存需等實際持倉。
依 memory「群益夜間登入 fail 待白天觀察」,此為既定驗收路徑非略過。

## 白名單

9 條逐條:兩個 lens 對照 + 修復輪複核全保留(orders 未動、merge_fut 邏輯不動、
close 映射不動、inflight 三端同鍵、scan_key 保守、error shape / WS 形狀不變、
fut 列外觀不變、profit 寧缺語意不變)。dup guard 未按 kind 細分 = 白名單 5 顯式接受,
記 next-time。

## Migration 可逆性

無持久化;wire 為 additive optional 欄位(revert 後舊 body 照常);store 純 in-memory
重啟即重建 — 可逆。
