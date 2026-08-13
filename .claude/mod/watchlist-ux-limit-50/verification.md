# verification — mod/watchlist-ux-limit-50(2026-08-13)

## 自動化驗證(auto-verify;指令組 = 專案 CLAUDE.md §1 覆寫)

| # | 指令 | 工作目錄 | 結果 |
|---|---|---|---|
| 1 | `.venv\Scripts\python -m pytest -q` | repo root | **2661 passed**(baseline 2659,+2 新測試;exit 0)|
| 2 | `.venv\Scripts\python -m ruff check copycat tests` | repo root | All checks passed(exit 0)|
| 3 | `.venv\Scripts\python -m pyright` | repo root | 0 errors / 0 warnings(exit 0)|
| 4 | `copycat replay four_tigers + five_tigers` → `copycat validate` | repo root | **42/42 PASS**(exit 0)|
| 5 | `npm test`(vitest) | frontend/ | **1807 passed / 112 files**(baseline 1797,+10;exit 0)|
| 6 | `npx tsc -b` | frontend/ | OK(exit 0)|
| 7 | `npx eslint src` | frontend/ | OK(exit 0)|
| 8 | `npx react-doctor@latest --scope changed --no-telemetry` | frontend/ | exit 0;1 warning(MiniIntradayChart.tsx:57 non-component export)= **存量非新增**(本輪只動該檔 :82 註解,finding 行不在 diff)→ 不擋 |

### fix 波(085ef998 + e4e3082a)增量 gate

- vitest WatchlistSidebar 兩檔:73 passed(+3);tsc / eslint:exit 0
- pytest tests/test_stock_watchlist.py:27 passed(+1 parity oracle);ruff / pyright:exit 0
- mutation 抽驗 ×3:B-1(註掉 collapsedRef 同步 → 新 lock 測試紅)/ B-2(拿掉 drag 守衛
  → 唯一新拖曳態測試紅)/ A-2(前端常數改 51 → parity 紅)— 皆還原後綠。

### 收尾最終全套(HEAD = e4e3082a + next-time 追記)

- frontend:vitest **1809 passed / 112 files**、tsc OK、eslint OK(exit 0)
- backend:pytest **2662 passed**(+1 parity oracle)、ruff All checks passed、
  pyright 0 errors(exit 0)
- tag 機驗:`check_feat_tags.py` flow=mod commits=12 → **PASS**

## 真實環境驗證(fake-source 側車 8721 + vite dev 5173;盤外,零 TC4/ZMQ)

側車:`evidence/fake_server.py`(抄 trial-pause-badge 樣板;`neutralize_external_env()`
前置 + `stock_watchlist_path` 隔離 tmp 目錄,ops-discipline 兩條紀律皆核)。

### SC-1 API 邊界(`evidence/SC-1_api-boundary.txt`)

- happy:PUT 50 檔 → **200**,saved codes=50
- edge:PUT 51 檔 → **400** `{"detail":{"error":"WATCHLIST_FULL"}}`
- regression 抽 1:PUT 壞碼 "12" → 400 `BAD_CODE`(格式閘未動)
- GET group-state 50 相異碼 → **200**,states=50
- edge:51 相異碼 → **400** `BAD_CODES`
- regression 抽 2(白名單 7):51 個重複碼 → 200,states=1(先去重再驗數,順序未動)

### SC-3 / SC-4 UI 截圖(dispatch subagent,claude-in-chrome)

- **SC-3 PASS**:三條標題列 computed `background-color: rgb(16,22,31)`(=`--color-surface`
  #10161f,頁面底 #0a0e14)、組名 `font-weight: 500`;個股列祖先鏈全 transparent、
  代號 font-weight 400。截圖 `evidence/SC-3_group-header-band.png`。
- **SC-4 PASS**:搜尋框下右對齊鈕「全部收合」→ 點擊全收、鈕變「全部展開」
  (`SC-4_collapsed.png`)→ **F5 重整後收合狀態保留** → 再點全展
  (`SC-4_expanded.png`)。
- Console:唯一 error 為存量 duplicate-key(intraday-vp 已記 next-time 條目,載入即出現、
  與側欄無關);操作全程零新增 error。

### SC-2 文案

- 單元測試層已鎖(bot + 前端三處字面「自選已達 50 檔上限」);全通道 grep gate:
  `copycat` / `frontend/src` / `tests` 的「30 檔|上限 30」殘餘命中皆為明列無關 30
  (signal 30/分、MAX_RULES、days=30、TC4 重連 30 次)— 包 1 回報 + lens A 複核。

### SC-5 效能盤點

- current-state.md §B 表 B-1~B-9 逐項評估完成;結論:50 檔下 `_CLIENT_QUEUE_MAX`(1000)
  與 60s group_snapshot 節奏、basis worker 0.2s gap 均不調參;
  已知惡化(TC4 離線 boot 還原 300s→500s)已更新 next-time.md:408 並補退出準則。
