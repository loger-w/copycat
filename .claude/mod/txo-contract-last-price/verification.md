# verification(mod/txo-contract-last-price,2026-08-05)

## Phase 6 自動化 gate(main session 親跑,HEAD = 486e09e)

| gate | 指令 | 結果 |
|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | **1678 passed**, 1 warning, 78.97s(baseline 1672 + 6 新測試)|
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS |
| 前端(wire 連動,SC-5) | `npm test` / `npx tsc -b` / `npx eslint src`(implementer 於修復輪跑,frontend 零 code 改動) | 72 files / 1000 tests passed;tsc OK;eslint OK |

exit code 皆 0,單獨執行無 pipe 汙染。

## TDD / mutation 證據(implementer 回報,main session 抽核)

- 🔴 round 1:改 test_snapshot_contracts_detail + ticks.jsonl 獨立斷言先紅(2 failed)→
  實作 → 1 failed(僅 golden 未重生,預期)→ regen 後綠。
- 🔴 S-2:0 價測試先紅(`assert 0.0 is None` — 0 確實穿 nullish 閘)→ `> 0` 閘後綠。
- mutation 佐證:M3 拿掉排序 seq 鍵 → ticks.jsonl 斷言 deterministic 紅(C.45500 50≠60),
  同 mutation 關掉 shuffle → 全綠(shuffle 是斷言力來源的決定性對照);M4 min() 語意 →
  latest-trade 紅(舊構造會假綠,S-4 屬實)。每次 mutation 後 `git diff --exit-code` 還原乾淨。
- golden diff 機械驗證:15/15 row 僅 +last_price;剝掉新 key 後與改動前全等 True;
  15 檔 last_price 與 ticks.jsonl 逐檔重算全中。

## Phase 7 真實環境驗證

SC-1~SC-4 由零 IO 狀態機測試 + ticks.jsonl 真實錄檔獨立斷言涵蓋(聚合層無 IO,
fake/real 無行為分岔)。SC-6(OrderPanel 市價鈕實際解鎖 / 確認框金額)需 server 重啟
吃新 code + 盤中成交:依 CLAUDE.md §8「不為看新 code 重啟跑著的 server」紀律,
留待下次自然重啟後目視(前端側已有既有測試護欄:OrderPanel.test.tsx 對 last_price=15.5
→ 市價可選 + 確認框 775 元、null → 鎖定,兩路皆綠)。「零成交合約仍鎖」為 SC-6 明訂
預期行為,勿誤判為未修好。

## 白名單

5 條逐條:S lens 機械比對(剝 key 全等 / symbol 順序一致 / 舊 key 值變更 0)+ T lens
確認唯一改動的既有斷言 = spec 標該紅的 test_snapshot_contracts_detail。全保留。
S-1(reset 窗 UX)裁決入 change-spec Known Risks + next-time。
