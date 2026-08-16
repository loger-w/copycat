# verification — mod/overview-onepage-corr-tab(2026-08-16)

## 1. 自動化 gate(auto-verify;`.claude/harness.json` verify 陣列 + frontend 五步 + doctor)

| 步 | 指令(cwd) | 結果 | exit |
|---|---|---|---|
| tsc | `npx tsc -b`(frontend/) | 無輸出 | 0 |
| vitest | `npx vitest run`(frontend/) | **111 files / 1852 tests passed**(最終 HEAD 5a111c68;baseline 112 files / 1830;−3 檔刪除 CorrSection ×2 + IndexPage.corr-lazy,+2 檔 App.corr-tab / MarketPane.size;淨 +22 tests) | 0 |
| eslint | `npx eslint src`(frontend/) | 無輸出 | 0 |
| build | `npm run build`(frontend/) | 成功 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry`(frontend/) | `✔ No issues found!`(fix 波前曾新增 2 條 only-export-components → DR-1 搬 lib 後消失) | 0 |
| pytest | `.venv\Scripts\python -m pytest -q`(root) | 2562 passed / **1 failed** = `test_index_routes::test_ws_streams_index_payload`(既有已文件化 flake,`docs/next-time.md` 條目;後端本分支零 diff `git diff master..HEAD -- copycat tests` 空;單測重跑 ×3 皆綠) | 1(flake) |
| ruff | `ruff check copycat tests` | 無輸出 | 0 |
| pyright | `pyright` | 0 errors | 0 |
| copycat validate | 未跑(後端零 diff、golden gate 與本輪無關) | — | — |

## 2. 真實環境(側車 `evidence/fake_server.py`:零 TC4/ZMQ、neutralize_external_env、隔離 `data/market-sidecar-onepage/`;fake 指數線 + 真 FinMind 漲跌停 rows 59 檔 + 合成騰落序列 270 分鐘;vite dev 5173 → 8721)

截圖由 claude-in-chrome subagent 執行(本機螢幕 1281×720,以 `documentElement.style.zoom` 做等效視窗;版面全走 container query,等效成立;量測值為等效 px)。fix 波後補驗結果:

| SC | 判定 | 依據 / 量測 | 證據 |
|---|---|---|---|
| SC-1 頂層 tab | PASS | nav = 台股綜合/個股(期)/選擇權/期貨/相關係數;點入 = 六腿走勢(上)+ 相關係數表(下);右欄「此頁無可下單標的」 | `evidence/SC-1-corr-tab.jpg` |
| SC-2 subtab 退役 | PASS(vitest) | IndexPage (l1)(l2)、App purge、active gate 既有測試綠;截圖無 subtab 列 | SC-3 截圖 |
| SC-3 1920×1080 | PASS | doc 720/720;grid 1002/1002(不捲);list 2319>912(內捲);pane 710/710(不溢出);順序 基差→雙圖→家數帶→騰落線;圖內刻度/時刻/右緣標籤可讀 | `SC-3-1920.jpg` |
| SC-3 1536×864 | PASS | grid 786/786;list 2587>686;pane 495/495;cols 712.8/475.2;th 九欄不折行、徽章不直排 | `SC-3-1536.jpg` |
| SC-3 sticky | PASS | scrollTop=400 表頭九欄仍見 + inset shadow 分隔線 | `SC-3-sticky.jpg` |
| SC-4(r3 判準) | PASS | (a) 864−60:grid 786/786 不捲、pane 不溢出;(b) 664:pane 355/355 不溢出、figure 234/236 > min-h-48、三段不重疊(內容 611 < 646 故尚不需捲);壓力 640/560/480 → grid 611/562、611/482、611/402 **可捲**、pane 320/320 = min-h-80 地板不溢出 | `SC-4-short.jpg` |
| SC-5 家數帶 | PASS | 漲停實心紅底白字(18/11)、跌停實心綠底白字(1/4);上漲紅字 281/249、下跌綠字 692/535、平盤 ink 83/80 無底色 | `SC-3-1920.jpg` |
| SC-6 騰落線 | PASS | net>0 紅線+紅面積、net<0 綠線+綠面積、0 軸裁切;末值 +183 紅;0 軸 / ±437 標籤 / 時刻不重疊 | `SC-3-1920.jpg` |
| SC-7 1280 | PASS | cols none(單欄 flex-col);grid 2473>642 可捲;pane 366/366;無重疊 | `SC-7-1280.jpg` |
| SC-7 1380(容器 1031) | PASS | 仍單欄;grid 2457>699 可捲 | `SC-7-1380.jpg` |
| SC-7 1440×900 | PASS | cols 655/437 兩欄;雙圖並排(左欄 655 ≥ 640);grid 733/733 不捲;pane 442/442 | `SC-7-1440.jpg` |
| console | PASS | `error|warn` 0 則 | — |

fix 波前首輪截圖:SC-4(1536×664)與 SC-7(1280 / 1440)FAIL(pane 溢出蓋家數帶、主 grid 不捲)→ 根因 WL-1/RE-1(見 code-review-round-1.json)→ 修後補驗全 PASS。

**白名單抽驗(未改功能)**:App 既有 active gate 測試(切離 index → 列表 / 分 K 停輪詢)綠;個股(期)/ 選擇權 / 期貨 tab 順序與內容零改動(App.test 既有);corr 頁功能只搬家(App.corr-tab:兩條 WS 建立且 hidden 保留)。

**Migration 可逆**:唯一資料面改動 = `copycat-index-subtab` 進 orphan purge、`copycat-tab` 值域加回 corr;皆 git revert 可逆,無資料破壞。

## 3. 觀察(非 SC;已入 `docs/next-time.md` 2026-08-16 節)
- 1536 兩欄態右欄 ≈475px 九欄擠不下 → 水平捲軸,量比 / 狀態需右捲。
- K 線態窄 pane 字級(CandleChart 共用元件)未補償(KR-3);`EDGE_LABEL_H` 未隨 unitScale。
- 圖表四角標籤(y 軸最低值 vs 09:00;右下 NL/AL vs 13:00)在短高度下互壓;1536 下加權卡片標題折三行。
- 截圖等效法的 `viewBox` 讀值在 zoom 下不隨高度變(RO contentRect 量綱),不作判準;真螢幕以 pane 不溢出 + figure 地板判定。

## 4. 樣板 / 文件修正
- `.claude/skills/frontend-testing/SKILL.md`:`MarketColdLoad.test.tsx`(neigui 遺留)與 `CorrSection*.test.tsx`(本輪刪)兩處樣板引用改指 `MarketPane.size.test.tsx` / `App.corr-tab.test.tsx`(KR-2 / TD-3)。
- `.claude/skills/frontend-conventions/SKILL.md`:新增 2026-08-16 一頁式版面五條教訓。

## 5. Tag 機驗
`python ~/.claude/hooks/check_feat_tags.py` → `flow=mod commits=35 PASS`;手動 `git log`:[red] 14 / [green] 14 一一配對,35 commits 全帶 🔴🟢🔵。
