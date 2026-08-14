# verification — mod/overview-subtabs-breadth-colors

日期:2026-08-14。HEAD:71272009(紅波 9326143d → 綠 9062544a / 53551f4d → review fix
066e5b1f / 71272009)。

## 自動化驗證(auto-verify;指令來源 = .claude/harness.json + CLAUDE.md §1 frontend 加項)

| step | command | cwd | exit | 證據 |
|---|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | repo root | 0 | 2680 passed, 1 warning in 150.74s |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | repo root | 0 | All checks passed! |
| pyright | `.venv\Scripts\python -m pyright` | repo root | 0 | 0 errors, 0 warnings, 0 informations |
| vitest 全套 | `npm test` | frontend/ | 0 | 115 files / **1898 passed**(baseline 114/1894;+corr-lazy 新檔) |
| tsc | `npx tsc -b` | frontend/ | 0 | 無輸出 |
| eslint | `npx eslint src` | frontend/ | 0 | 無輸出 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | frontend/ | 0 | Scanned 17 files,No issues found(新增 finding = 0) |

紅波 TDD 證據:紅波 commit 時觸及範圍 261 tests 中 106 failed(全斷言層失敗,無腳手架
TypeError;該紅全紅 / 不該紅全綠,無 spec 未列意外紅)→ 綠波後同範圍全綠。

## 真實環境驗證(web shape)

環境:側車 server(`evidence/sidecar_server.py`,R4 樣板:fake TXO + 真 FinMind EOD +
`neutralize_external_env()` + 隔離 `data/market-sidecar-overview-subtabs/` +
`stock_watchlist_path` 隔離)佔 8721(prod 未跑,盤後)+ vite dev 5173。
health 確認 `git_sha=71272009` = HEAD(版本落差判法)。

- API 抽驗:`GET /api/market/breadth` → 200,真 EOD:twse 漲停18/上漲276/平盤83/下跌691/
  跌停1;tpex 11/248/80/531/4(SC-1 截圖的對照真值)。
- UI 截圖(dispatch subagent,claude-in-chrome):SC-1 / SC-2 / SC-3 逐條對照,
  結果見下節(截圖 `evidence/SC-*.png`)。
- Edge(jsdom 層鎖,盤後無法在真環境重現者以測試代):非法 localStorage 值 fallback
  (s4)、getItem/setItem throw((s5)(s5b))、active gate 全鏈(App.test L357-383)。
- 未改功能 regression 抽 2:上方常駐區(基差列 + 雙 pane;IndexPage.test (a)-(d3) 原文
  綠)+ App 跳轉全鏈(App.test 漲跌停/類股/時間軸 → 個股(期),斷言主體原文綠)。

## UI 截圖對照結果(dispatch subagent,claude-in-chrome,約 5 分)

- **SC-1 PASS**:上市/上櫃「上漲」276/248 紅字、「下跌」691/531 綠字;漲停 18/11 暗紅底
  格內數字墨色(非紅)、跌停 1/4 暗綠底格內數字非綠;平盤 83/80 中性無底;上漲/下跌格
  無漲跌色底。截圖 `evidence/SC-1-breadth-band.png`。
- **SC-2 PASS**:騰落線下框盒頂部一列四顆 tab(read_page 全表僅 4 個 tab 元素,無任何
  「展開/收合」殘留);預設「漲跌停」選中且列表非空(真 EOD 漲停列);點類股強弱/相關
  係數內容互斥切換;panel 留白正常無雙倍內距(review A-1 修後)。截圖
  `SC-2-subtabs-limit.png` / `SC-2-subtabs-sector.png` / `SC-2-subtabs-corr.png`。
- **SC-3 PASS**:停在類股強弱 → reload 仍停在類股強弱。截圖 `SC-3-subtab-persist-reload.jpg`。
- Console:零新增紅色 error;唯一噪音 = `useIndexStream` 503 WARNING(TC4 不在的預期降級)。
- 側車與 vite 已於取證後停止(8721 釋還)。

## Phase 7:SC 與白名單逐條(重讀 change-spec.md 對照)

### SC
- [x] SC-1 家數字色:BreadthBand.tsx BUCKETS valueTone;測試 (l)(m)(n)(o)(p);
  截圖 SC-1-breadth-band.png(main session 親核:276/248 紅、691/531 綠、停板底色白字、
  平盤中性)+ 待 user 過目
- [x] SC-2 subtab 列:IndexPage.tsx tablist + 條件 render;(s1)(s2)(s2b)(s2c);截圖
  SC-2-subtabs-{limit,sector,corr}.png(main session 親核 limit 張:四 tab 一列、列表非空、
  無舊收合列)+ 待 user 過目
- [x] SC-3 記憶/還原:(s2)(s3)(s4)(s5)(s5b);真環境 reload 截圖 SC-3-subtab-persist-reload.jpg
- [x] SC-4 舊 key 廢止:constants 刪四常數 + ORPHAN 追加;purge 測試(App.test L594-604 鎖
  六鍵清 + 活鍵存);grep 零 production 殘留(lens B 查證)
- [x] SC-5 unmount 語意:stub 層 (s1)(s7) + 真身層 IndexPage.corr-lazy.test.tsx(零 WS +
  正向對照)+ CorrSection.lazy (c) unmount 斷線

### 白名單(lens B 逐條查證 PASS + 波尾全套綠 + 截圖)
- [x] W1 常駐區零觸及(diff 未碰;順序鏈測試原文綠;截圖可見)
- [x] W2 非 active subtab = unmount((s7) 計數 / corr-lazy WS)
- [x] W3 active gate 全鏈(App.test 三條 gate 測試斷言主體原文綠;timeline 仍無 gate)
- [x] W4 SectorBody FE-7 / LimitList 篩選零觸及(diff 未碰 body;截圖篩選列健在)
- [x] W5 lazy 邊界 + fallback 文案(兩測試檔鎖;chunk 邊界未移)
- [x] W6 BreadthBand 三態/桶序/停板底色((a)-(k) 原文綠;(f)(g) 原文不動)
- [x] W7 App 跳轉全鏈(三條跳轉測試僅改 seed,斷言主體原文綠)
- [x] W8 Safari try/catch(initialSubTab / selectSubtab 均包;(s5)(s5b) 鎖)
- [x] W9 孤兒鍵(既有兩鍵仍清;活鍵反向鎖;fut-chart-mode.test 零觸及綠)

### Migration 可逆性
- [x] code 可 git revert;被 purge 的舊鍵值僅「展開/收合」UI 偏好,revert 後回預設一次,
  無資料損失(spec Backward compat 節判定可接受)。

