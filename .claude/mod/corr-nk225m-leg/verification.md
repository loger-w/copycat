# verification — 相關係數加「小日經」第七腿(R5)

分支 `mod/corr-nk225m-leg`;日期 2026-08-17(週一,OSE 夜盤時段取證)。

## 0. 前置 live 探測(SC-5)

腳本 `spikes/nk225_leg_probe.py`(Disconnect 收工 ✓,stdout 末行 `disconnected`);產物
`spikes/out/nk225_leg_probe.json` + `spikes/out/catalog_Fut_2026-08-17.json`(out/ gitignored,摘要於此)。
20:15 台北起跑,60s 監聽。

| 項 | 結果 |
|---|---|
| (1) Fut 全量 dump diff | 17 段 = 06-30 快照(added [] / removed []);**無 KRX 段、全樹零命中 KOSPI / 韓**;OSE ids `F_MTP/F_TPX/G_JGB/NK225/NK225M/NK225MC/NK400/REIT`;SGX 有 `NK`;CME 有 `NKD` |
| (2) QUERYINSTRUMENTINFO oracle | NK225 ✓ / NK225M ✓ / SGX NK ✓ / 負對照 `TC.F.OSE.NOPE_XX.HOT` ✗ / 對照 MES ✓ |
| (3) 推播計數 60s | MES 219 / NK225 102 / **NK225M 175** / SGX NK 78(全為成交推播,tick≠None);OSE `FilledTime="121550"` → `minute_end_from_utc_hhmmss`=1216(台北 20:16 ✓);`PreciseTime` 12 位;五檔 Bid/Ask parse ✓(NK225M bids [[69085000,10],[69080000,31]]);OSE OpenTime 160000 / CloseTime 144500 |
| (4) 1K 當日窗 | 三檔首頁各 50 列,`parse_1k_minutes` 50/50;首列 `Time=100` → 分鐘 481(08:01);首分鐘 Volume NK225M 3285 vs NK225 182 vs SGX NK 247 |
| next-time:758 跨 UTC 06/22 邊界 | 本輪 20:1x 起跑不跨邊界 → **未觀察到,不勾銷** |

結論:D13 (a) 小日經 `TC.F.OSE.NK225M.HOT` 流動性最佳且 parse 層零改即通;D14 韓指做不到(事實已入 SKILL)。

## 1. 自動化 gate

| 指令 | 結果 |
|---|---|
| `pytest -q` | 見 §1a(最終全量) |
| `ruff check copycat tests spikes/nk225_leg_probe.py` | All checks passed |
| `pyright` | 0 errors |
| `copycat validate` | 42/42 PASS |
| `npm test`(vitest) | 見 §1a |
| `npx tsc -b` / `npx eslint src` | exit 0 / exit 0 |
| `vite build` + utility grep | 見 §1a(`.stroke-river-7` / `.fill-river-7` / `.text-river-7`) |
| `react-doctor --scope changed` | No issues found |

### 1a. 最終全量(收尾前重跑)

- `pytest -q` → **2652 passed**(baseline 2650 + 新 2;含 4 條該紅 assertion 改後綠)
- `ruff check copycat tests spikes/nk225_leg_probe.py` → All checks passed
- `pyright` → 0 errors, 0 warnings
- `copycat validate` → 42/42 PASS
- `npx vitest run` → 127 files / **2198 passed**(含 river-colors.test.ts 3 條 + 8 條「各腿」斷言)
- `npx tsc -b` exit 0;`npx eslint src` exit 0
- `vite build` ✓;`grep -o ".stroke-river-7|.fill-river-7|.text-river-7" dist/assets/*.css` → 各 1(token 宣告不計)
- `npx react-doctor@latest --scope changed --no-telemetry` → No issues found(自評修復後曾新增 2 條
  js-combine-iterations,已合併迭代後回到 No issues)

### 1b. 自評(code review round-1)後增量重跑
- vitest 127 files / **2200 passed**(+ R-1 註記測試 + token 守衛);tsc 0 / eslint 0 / react-doctor No issues
- pytest corr 三檔 29 passed;ruff All checks passed(後端 diff 自 §1a 後零改,pytest 全量不重跑)

## 2. 真實環境(SC-3)

側車 `evidence/corr_sidecar.py`:真 TC4 corr + futures 引擎、fake TXO、`neutralize_external_env()`、
隔離 data dir;prod 8721/8722 確認未跑後佔 8721(vite proxy 寫死);取證後 taskkill,ports free。
`/api/health` `git_sha=5f150459`。

- `/api/corr/state`(evidence/SC-3-corr-state.json):七腿全部 `stale:false`,NK225M mid 69102.5;
  pairs `NK225M` n60=60 w60=0.499(60s 窗)— 表列數字真算。
- `/api/river/state`(evidence/SC-3-river-minutes.json):六腿各 332 分鐘、**NK225M 272 分鐘**
  (16:00 OSE 夜盤開 → 20:3x;1K 回補 + live 接續 ✓;E5 15:00–16:00 空窗預期)。
- 截圖 `evidence/SC-3-overlay-nk225m.jpg`:標題「各腿走勢」、勾選列第 7 顆「小日經」chip fuchsia、
  重疊圖右緣「小日經」標籤 fuchsia(與台指白 / 標普薰衣草紫可辨)、下方相關係數表第 6 列
  「小日經」0.59 / 0.60 / 0.60。
- 截圖 `evidence/SC-3-cards-nk225m.jpg`:並排七卡,第 7 卡「小日經 69050.00 -0.18%」fuchsia 線自
  16:00 起;三欄格局第 7 卡獨佔第 4 列(版面微調 out of scope,記 next-time)。
- 白名單抽驗:六腿標籤 / 順序 / 顏色未變(截圖);台股綜合頁未受影響(截圖 1 家數帶正常)。

### 2a. 自評 R-1 補的畫面元素(未截圖,jsdom 測試鎖)
- 重疊圖標頭列右側「小日經 自 16:00 起算 0%」(夜盤;日盤時 OSE 07:45 早於台指 08:45 → 不標)。
  `RiverPanel.test.tsx` 以納指 09:55 fixture 鎖住;真畫面待 prod 重啟 user 過目。

## 3. 白名單逐條

- W1 六腿 key/label/symbol/source/順序不動、base TXF:`TestRepoConfigFile::test_repo_config_first_six_legs_match_default` ✓
- W2 DEFAULT_CONFIG 六腿:`TestDefaultConfig` 6 條綠 ✓
- W3 前六色不動(`river-colors.test.ts` 前六組鎖 ✓);三檔配色 / 資料流零改(僅文案 🔴 amendment)✓
- W4 無 TC4 降級:引擎程式碼零改,`test_returns_503_with_error_code_when_engine_disabled` 綠 ✓
- W5 corr_engine / corr_source / river_* 零改:`git diff master --stat -- copycat/` 只有無(見 §4)✓

## 4. Migration 可逆

無資料 migration。回退 = revert 🟢 commit(json 一筆 + 三常數 + 一 token)+ 🔴 文案 commit;
`git diff master --stat -- copycat/` = 空(引擎零改)。
