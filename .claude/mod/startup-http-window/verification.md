# verification(mod/startup-http-window,2026-08-05)

## 自動化 gate(Phase 6;主 session 親跑,不接管線)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | **1731 passed**, 1 warning in 77.58s(baseline 1720 + 新增 11) | 0 |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |

## 真實環境(Phase 7 fake 段;不碰 ZMQ,port 18821,盤中安全)

SC-1 量測腳本:scratchpad `sc1_measure.py`(fake TXO source 注入 12s `list_series` 延遲
+ 真 uvicorn thread):

```
t(/api/health first 200) = 0.037s  (target < 1.0s;現況 baseline ≈ 12.6s)
window: /api/ready=200 {'ready': False, 'error': None} | /api/txo/snapshot=503 | /api/stock/watchlist=503
t(/api/ready true) = 12.003s  (expect ~12s+ε), error=None
after boot: /api/txo/snapshot=200
SC-1: PASS
```

## SC 對照

- SC-1 首次 200 < 1.0s:**PASS**(0.037s;改善 ~340x)。
- SC-2 四道 gate 全綠:**PASS**(上表)。
- SC-3 關機中斷不洩漏:**PASS**(test_boot_window 測試 2/3,鑑別斷言 `boot_done False` /
  `stock is None` + mutation 驗證:拿掉 `_boot` CancelledError 分支 → 測試 3 紅)。
- SC-4 select busy guard:**PASS**(測試 5 HTTP 503 HANDOVER_BUSY→200 + engine 單元
  兩條,含雙 activate 並發)。
- SC-5 prod 重啟目視:**未做**(遵守「盤中不重啟」紀律,排盤後;預期清單見 change-spec
  SC-5 amendments:啟動窗降級形狀、capital disabled 誤讀窗、一次性 query 需重載、
  「切換失敗:HANDOVER_BUSY」原始碼字串皆為預期)。

## 白名單對照(Phase 5 finder 逐條,10/10 PASS)

1. 引擎啟動順序與依賴 PASS(`_boot_engines` 順序零重排,依賴點行號逐一核)
2. 關機反序 PASS(booted record 讀取,各段獨立 try/except 續行;R4 保護在位)
3. `_boot` 降級契約 PASS(characterization 兩條斷言逐字未動且敏感度實測仍在)
4. error contract PASS(新碼 HANDOVER_BUSY 同形;三既有碼產生點未進 diff;health shape 不變)
5. `/api/stock/names` 不過閘 PASS(未進 diff,窗內 200 有測試)
6. canonical PUT / membership 種子時序 PASS(watchlist_service 未進 diff;種子到 attach 零 await)
7. --verify 模式 PASS(__main__ 未進 diff)
8. banner 最先印 PASS(lifespan 前兩行不動;窗內 /api/health 200 有測試)
9. rollover / self-heal 鏈 PASS(_maybe_self_heal 逐字未動;unsubscribe 窗的 self-heal 改為下輪天然補跑 = 收緊)
10. 既有測試 assertion 零改動 PASS(diff 零 `-` assert 行;唯一刪除 = 自評 R-T1 決議的兩行非鑑別斷言)

## 自評(Phase 5)

- round 1:2 lens(async 正確性 / 白名單+測試效度),0 P0、0 P1、5 P2 全 accepted 並修畢
  (commits e77dd0b/d1d1899/ea4a106);JSON 見 code-review-round-1.json。
- AL-3 新測試 mutation 驗證非 vacuous(退修法 → 1 failed;復原 → passed)。

## 待辦(盤後)

- prod server 自然重啟(user 排程):目視 SC-5 清單 + `/api/ready` 翻轉 + 首次 200 體感。
