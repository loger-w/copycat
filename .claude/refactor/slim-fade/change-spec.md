# refactor/slim-fade — 專案瘦身第一批:刪 fade 回測家族 + 盤點 A 桶死碼

2026-09-14。依據 `docs/research/2026-09-14-dead-code-inventory.md`(唯讀盤點),user 同日拍板:
A 桶做、B1 fade 家族全刪。

## Why gate

- fade = 2026-07 的 T+1 空方當沖研究,五輪回測結論負期望,07-20 起 code 零改動、最後報告 07-17。
  結論 SoT 在 `docs/strategy-decisions.md` + `docs/evidence/fade_*.md`,刪 code 不刪結論。
- 它是 copycat 非測試碼的 19%(7,259 / 37,929 行)、後端覆蓋率最低的一群(49–89%)、
  且是第四輪效能掃描裡「不要做」清單的來源之一(quantiles 算法不可換)。留著只增加每次全量 gate 的成本。
- 線上 server(`copycat.server`)從未 import 任何 fade 模組;`copycat validate` gate 不吃 fade。

## 行為不變承諾(Spec 軸對照)

1. `python -m copycat.server` 啟動路徑零改動(app.py / engines 未動)。
2. CLI 其餘 16 個子指令原樣(21 → 16);只少 5 個 `fade-*`。
3. `copycat validate` golden 結果與 master 相同(replay / engine 未動;A4 只刪零 caller 方法)。
4. `backtest/report.py`(T 日)輸出逐字不變:`fmt_cell` 原樣,只刪 `fmt_num` / `fmt_quantiles`。
5. 前端:只拿掉未被任何檔 import 的 `export` 關鍵字與未使用的 default export;bundle 行為不變。

## 範圍(白名單)

刪:`copycat/backtest/fade_*.py`、`market_features.py`、`quantiles.py`、`tests/backtest/test_fade_*`、
`tests/test_fade_*.py`、`tests/test_cli_fade.py`、`tests/test_market_features.py`、`configs/fade_uc_round*.json`、
`cli.py` 五個子指令、`report_fmt.fmt_num / fmt_quantiles`、`aggregate.last_cum`、`LockTracker.current_lock_start`、
`tests/test_shared_infra_characterization.py` 12 → 3 條(移除的 9 條全為已刪符號的特徵化:quantile_round / quantile_trunc / quantiles_round ×6、fmt_num、fmt_quantiles、load_fade_config;pr-230 review F-03 補列)、
前端 knip 33 export / **32** type export(盤點 A6 寫 33,差額 1 = `_KindDomainsMatch` 型別機驗必須保留 export;`export type { Group, Watchlist }` 只降 Group 一個符號;pr-230 review F-07)/ 9 個未使用 default export(盤點 A7 寫 12,其中 App / CorrPage / FuturesPage / IndexPage / StockPage 走 `lazy(() => import())`,default 必須留;A7 高估,非漏做)。
另兩處文件層同動:`.claude/skills/{tc4-market-facts,backend-conventions}/SKILL.md` 三條指向已刪路徑的教訓改寫(語意保留、路徑改述)、`configio.py` docstring 去掉 fade_config 舉例。
A8(`@eslint/js` 補列 devDependencies)獨立 chore commit,不混進 refactor commit(review Standards #1)。

不動:`docs/**`、`.claude/mod/fade-round-2`(歷史 artifact)、`backtest/{config,universe,features,simulate,search,stats,pipeline,report}.py`(T 日)、
`replay/ engine/ data/`、`spikes/`、任何 runtime 行為。

## 不在本批(盤點其他桶,另案)

B2 T 日回測、B4 events 資料鏈、B6 TXO 舊元件、C 版控體積(trace 17 MB)、D 相容分支(D1 **不可刪**:prod
`data/signal_rules.json` 仍是 v1,每次開機靠遷移鏈升到 v5;D2 可刪待拍板)。
