# change-spec — 相關係數加「小日經」第七腿(R5)

分流判定:**已成形**(需求指名落點檔案 configs/correlation.json + river-colors.ts、symbol、label、
D13/D14 已拍板)→ grilling 姿態、無方向性抉擇待問;規模 **M**(4 檔:json / ts / css / test +
SKILL 文件),spec review 1 輪。

## 0. 前置 live 探測(spec 第一步)

腳本 `spikes/nk225_leg_probe.py`(一次性;Disconnect 收工),結果 `spikes/out/nk225_leg_probe.json`
+ 全量 dump `spikes/out/catalog_Fut_2026-08-17.json`。**結果摘要見 verification.md §0**;
四項:(1) Fut 全量 dump diff(OSE NK225M 仍在 / KRX 仍無);(2) QUERYINSTRUMENTINFO 存在性
oracle(三候選 + 負對照);(3) 60s 推播計數 NK225 / NK225M / SGX NK(對照 CME MES;不碰六腿本體
以免搶走 prod 推播)+ 專案 parse 函式實跑(`parse_stock_realtime`、`minute_end_from_utc_hhmmss`);
(4) 1K 當日窗 + `parse_1k_minutes`。next-time:758 跨 UTC 06/22 邊界項:本輪 20:1x 起跑不跨
邊界 → **觀察不到,不勾銷**。

**探測結果(2026-08-17 20:15 台北,OSE 夜盤)**:17 段與 06-30 快照零增減、無 KRX/KOSPI;
OSE ids = NK225/NK225M/NK225MC/NK400/F_MTP/F_TPX/G_JGB/REIT、SGX 有 NK、CME 有 NKD;oracle
三候選 true / 負對照 false;60s 推播 MES 219 / NK225 102 / **NK225M 175** / SGX NK 78(全為
成交推播);OSE `FilledTime="121550"` 6 位 → `minute_end_from_utc_hhmmss`=1216(台北 20:16 ✓),
`PreciseTime` 12 位,Bid/Ask 五檔 parse ✓;1K 當日窗三檔各 50 列、`parse_1k_minutes` 50/50、
首分鐘 NK225M Volume 3285 vs NK225 182 vs SGX NK 247。

選腿:D13 拍板 `TC.F.OSE.NK225M.HOT`;探測項 3 若 NK225M 推播計數 < NK225 的 1/5 且
< 10 則/60s → 記入 Known Risks 並在收尾回報,不改拍板(方向性抉擇屬 user)。

## 1. 成功條件

| SC | 內容 | 驗證方式 |
|---|---|---|
| SC-1 | `configs/correlation.json` legs 第 7 筆 `{"key":"NK225M","label":"小日經","symbol":"TC.F.OSE.NK225M.HOT","source":"tc4"}`;`load_config()` 讀出 7 腿、末腿 key/label/symbol/source 如上、base 仍 TXF | 新測試 `tests/test_corr_config.py::TestRepoConfigFile::test_repo_config_has_seven_legs_with_nk225m`(讀 repo 真檔 `CONFIG_PATH`,不是 tmp 假檔);`pytest tests/test_corr_config.py -q` |
| SC-2 | river 調色盤 7 組:`river-colors.ts` 三陣列各補 `*-river-7`;`index.css` 補 `--color-river-7`(非紅非綠、與前六色可辨) | `npx tsc -b` + `npm test`;新測試 `river-colors.test.ts`:三陣列長度相等且 ≥ 7、第 7 項字面值 `stroke-river-7`/`fill-river-7`/`text-river-7`;build 後 `grep -o "\.stroke-river-7\|\.fill-river-7\|\.text-river-7" frontend/dist/assets/*.css` 三個 utility 各 ≥ 1(**token 宣告 `--color-river-7` 不算數**;`[amendment 2026-08-17: review R5 — 原 grep "river-7" 會被 token 字串誤過]`) |
| SC-3 | 【畫面可指認】相關係數 tab:corr 表出現「小日經」列(base 台指列之外第 6 列非 base 腿),三窗欄有數字或「—」;江波圖 legend / 卡片出現「小日經」且線色為第 7 色(粉紫,不與台指近白重疊) | 驗證窗口:OSE 交易時段(台北 07:45–14:45 / 16:00–05:00)且 TC4 在線;`[amendment 2026-08-17: review R3 — --verify 不建 corr 引擎(create_app 不傳 corr_source → 503),該降級路徑不存在,刪除]` 窗口外降級 = 前端 vitest 餵 7 腿 fixture 斷言第 7 腿以 text-river-7 呈現(本輪在窗內,未動用);實際取證用 `evidence/corr_sidecar.py`(真 TC4 corr/futures + fake TXO + neutralize_external_env,prod 未跑時佔 8721 供 vite proxy,取證後 kill)。截圖 `evidence/SC-3-*.jpg`(claude-in-chrome 視窗 1568×778;七卡三欄第 7 卡獨佔第 4 列 **已觀察到**,落 next-time)+ user 過目 |
| SC-4 | tc4-market-facts SKILL 海外節新增一句:「日經有(OSE `NK225`/`NK225M`/`NK225MC`/`NK400` HOT + SGX `NK` + CME `NKD`);韓指無(2026-08-17 重 dump 全段仍無 KRX)」+ 探測數字 | `grep -n "KRX" .claude/skills/tc4-market-facts/SKILL.md` |
| SC-5 | 探測記錄落 verification.md §0(dump diff + 推播計數 + parse 實跑結果) | 檔案存在且含四項 |

## 2. 不能破壞的既有行為白名單

- W1 六腿現有 `key/label/symbol/source` 全部不動;順序不動;`base` 仍 `TXF`(`source=futures_engine`)。
- W2 `DEFAULT_CONFIG` 仍六腿(設定檔壞掉降級路徑不變);`tests/test_corr_config.py::TestDefaultConfig` 六條**不該紅**。
- W3 river 前六色 token 值與 class 名不動;三 import 檔(`RiverPanel/RiverCards/RiverOverlay`)**配色 / 資料流零改**。`[amendment 2026-08-17: review R4 — 三處使用者可見「六腿」字面值(RiverPanel.tsx:57,72 / RiverOverlay.tsx:80 aria-label)改為腿數無關「各腿」,🔴 紅先行:App.corr-tab.test.tsx ×4 + RiverPanel.test.tsx ×4 斷言先改紅 → 元件綠;W3 收窄為配色/資料流零改]`
- W4 無 TC4 時降級行為不動(引擎逐腿降級 / 前端 tc4 down 文案)。
- W5 corr_engine / corr_source / river_* 程式碼零改(SC-8 契約:加腿不改引擎)。

## 3. Backward compat / migration

- 設定檔啟動時讀一次 → prod server 重啟後第七腿才生效;無資料格式變動、無 migration。
- `[amendment 2026-08-17: review R2]` API payload **加法式**契約變動:`/api/corr/state`・`/ws/corr` 的 `legs` 多一鍵 `NK225M`、`pairs` 多一列;`/api/river/state`・`/ws/river` 的 `legs` 多一腿序列。既有鍵形狀 / 值零改 → 歸 🟢(新腿)而非 🔴,理由:沒有任何既有 caller 讀到不同的值,只有「鎖整個集合」的測試變紅(已列該紅)。前端消費者 `CorrPanel.tsx:45,71` / `RiverPanel.tsx:62-66` 渲染邏輯 `Object.keys` 動態零改(RiverPanel 檔內另有 R4 文案 🔴,見 W3);`RIVER_OFF_KEY` localStorage 舊值(已關閉腿陣列)不含新腿 → 新腿預設顯示,無 migration。其他 client(curl / 側車)只會多看到一鍵。
- 可逆:revert json 一筆 + 三常數 + 一 token 即回六腿。

## 4. Out of scope

- 韓指(TC4 無 KRX 段;D14 不做不追蹤)。
- 選 NK225 大日經 / SGX NK 替代(D13 已拍板;探測數字只記錄)。
- `DEFAULT_CONFIG` 加腿。
- 跨 UTC 06/22 邊界推播驗證(next-time:758,本輪時段不跨邊界)。
- corr 表 / river 版面對 7 腿的排版微調(動態列;若 1080p 下 7 卡片換行溢出,記 next-time)。

## 5. Edge cases

- E1 設定檔 7 腿但 TC4 無此 symbol(下架)→ 既有逐腿降級:該腿 stale / 無數字,其他腿照常(W4)。
- E2 OSE 休市(日本假日)而台股開盤 → 小日經列 stale/「—」,不影響其他腿。
- E3 river 腿數 7 = 調色盤長度,取模仍各異色;第 8 腿(未來)才回到 river-1。
- E5 `[amendment 2026-08-17: review R6]` **每日台北 14:45–16:00**(OSE 日盤收 → 夜盤開;台指夜盤 15:00 已開)小日經腿 stale;corr 三窗依窗長先後轉「—」(w60 約 1 分、w300 約 5 分、w1800 最長約 30 分,期間 n 遞減,`corr_state.py:74-78,104` 時間逐出),15:15 後三窗全「—」;江波圖夜盤窗前 60 格空白 = 預期行為,非訂閱失效(判別:16:00 後恢復推播)。`[amendment: review R2-3 分窗描述]`收尾回報一併寫明。
- E4 OSE `FilledTime` 若非 6 位 HHMMSS → `minute_end_from_utc_hhmmss` 回 None → 退本機時鐘分鐘(引擎既有 fallback);探測項 3 實測記錄。

## 6. Diff 級章節(三類)

| 檔 | 類 | 動什麼 |
|---|---|---|
| `configs/correlation.json` | 🟢 | legs 末尾加 NK225M 一筆;`_comment` 不動 |
| `frontend/src/index.css` | 🟢 | `--color-river-7: #e879f9`(fuchsia;非紅非綠、與 river-4 紫 #b794f4 以飽和度區分)+ 註解改「六腿」→「腿數依設定檔(現七腿)」 |
| `frontend/src/components/corr/river-colors.ts` | 🟢 | 三陣列各補 `*-river-7` |
| `frontend/src/components/corr/river-colors.test.ts` | 🟢 新測試 | 長度一致 ≥ 7 + 第 7 項字面值(紅先行:先寫測試對 6 色紅 → 加色綠) |
| `tests/test_corr_config.py` | 🟢 新測試 | `TestRepoConfigFile` 讀 `CONFIG_PATH` 真檔:7 腿 + NK225M 欄位 + base TXF(紅先行:現檔 6 腿必紅) |
| `frontend/src/components/corr/RiverPanel.tsx:57,72` / `RiverOverlay.tsx:80` | 🔴 `[amendment 2026-08-17: review R4]` | 使用者可見「六腿」文案 → 腿數無關「各腿」(等待各腿資料… / 各腿走勢 / aria 各腿重疊走勢);與 🟢 分開 commit(c818fba1 red → 8168fba7 green) |
| `frontend/src/App.corr-tab.test.tsx` ×4 / `RiverPanel.test.tsx` ×4 | 🔴 該紅(紅先行) | 8 條斷言字串改「各腿」 |
| `.claude/skills/tc4-market-facts/SKILL.md` | 🔵 文件 | 海外節加日經/韓指事實 |
| `spikes/nk225_leg_probe.py` + `spikes/out/*.json` | 🔵 | 探測腳本 + 產物(out/ 若 gitignored 則只落 verification 摘要) |

既有測試:**除下列該紅者外皆不該紅**。該紅清單:(a) 路由四條(下 amendment)🟢 隨 SC-1;(b) 前端「六腿」文案 8 條 🔴 紅先行(上表)。`[amendment 2026-08-17: review R2-1 — 原句「全部不該紅(無 🔴)」已失真,改寫]`
`[amendment 2026-08-17: 全量 pytest gate 抓到 tests/server/test_river_routes.py 兩條(test_returns_window_and_six_legs / TestExistingCorrRouteUnaffected::test_corr_state_still_returns_pairs)以 create_app 預設路徑讀 repo 真檔並鎖六腿集合 → 屬「該紅」(腿集合正是本次改動),current-state 漏列(grep 只掃 test_corr_config)。同族另 2 條:tests/server/test_corr_routes.py::test_returns_payload_when_engine_running(六腿集合)/ test_engine_subscribes_five_tc4_legs_not_the_base(訂閱數 5)。處置:四條 assertion 改為含 NK225M 的顯式七腿集合 / 訂閱六腿(🟢 隨 SC-1;順序上實作先於改測試,gate 事後抓到,誠實記帳)。]

## 7. Known Risks

- KR-1 NK225M 夜盤流動性若明顯低於 NK225(探測數字為準)→ 江波圖分鐘缺格較多;拍板不改,記錄回報。
- KR-3 `[review R7]` 程式碼註解 / docstring「六腿」字樣散落(判準 `grep -rn 六腿 copycat frontend/src` — 含 useRiver.ts / river-chart-svg.ts(+test)/ RiverPanel.tsx 檔頭等,不寫死行號;review R2-4)— W5 引擎零改,本輪**不動**,記 next-time 一條(純註解 🔵 批次)。
- KR-4 `[review R8]` 探測腳本 + SKILL 文件 commit 前綴用了 🔵(d481c409);三類語意上屬「文件/工具(非三類)」,專案慣例 chore 可不掛 emoji;不 amend 已成 commit,記錄取捨。
- KR-2 OSE 段 parse 層假設(FilledTime 6 位)以探測項 3 為證;若探測窗零成交(僅簿更新)則 tick=None 無法驗 FilledTime,記入 verification 誠實標「未驗」。


---
self_review_head: 766b26bc
