# verification — refactor/frontend-localstorage-keys(2026-08-04)

## 自動化(Phase 6)

| gate | 結果 |
|---|---|
| `npm test`(frontend/) | **1000 passed / 72 files**(baseline 996 → +3 遷移/清除測試 → review 修復輪 +1) |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |
| `check_feat_tags.py` | PASS(🔵 集中 + 🔴 遷移×2 + 🟢 測試,四 commit 三類不混) |

mutation 網(implementer 逐條實測,均已還原):migration no-op → 2 紅(含既有 App.test:211 舊字面值測試 = 守護網真的有效);優先序反轉 → 1 紅;孤兒清除 no-op → 1 紅;K-1 removeItem 拿掉 → 1 紅。

## 真實環境(Phase 7,vite dev → prod backend,DevTools MCP)

- **只有舊 key**:種 `stock-main-code=2330` + 兩孤兒鍵 → reload → 新 key `copycat-stock-main-code=2330`、舊 key 與孤兒鍵全 null、主圖標題「台積電 2330」(偏好保留);截圖 `evidence/migration-main-code-preserved.png`
- **新舊並存(K-1 修復後)**:舊 `2317` + 新 `2330` → reload → 新值 `2330` 勝出、legacy 清除、孤兒鍵清除、主圖「台積電 2330」
- console 零 error

## 行為零改變核對(Phase 8)

- 14 個未改名 key 值逐字元不變(K lens 機械 diff 法驗證:sed 還原常數名後與 master 逐行 diff,只剩宣告/import 行差異,零錯置)。
- 測試側字面值守護網完整保留(每 key 至少一處 exact 斷言)。
- 使用者可見行為:主圖偏好經遷移零遺失;其餘 key 行為不變。
- 動機解決:key 單一清單(lib/constants.ts,15 常數 + LEGACY + ORPHAN)、前綴統一、孤兒清除。
