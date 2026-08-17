# current-state — 相關係數加「小日經」第七腿(R5)

快照:master `c945d474`(2026-08-17)。來源 prompt:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R5(D13 a / D14 已拍板)。

## 1. 腿設定鏈(caller map)

| 面 | 檔案:行 | 現況 | 動態用法 |
|---|---|---|---|
| 設定檔 | `configs/correlation.json` | 六腿(TXF futures_engine + TWN/YM/ES/NQ/SXF tc4);`_comment` 明寫「新增一腿只需在 legs 加一筆(SC-8)」;`_todo_tsm` 佔位先例 | 由 `corr_config.load_config()` 讀,未知欄忽略 |
| 設定載入 | `copycat/corr_config.py:23-25,54-64,81-106` | `DEFAULT_CONFIG` 六腿(never-raise fallback);`load_config` 檔缺/壞/base 不在 legs → 預設 | `server/app.py` 起 corr_engine 時呼叫(路徑預設 `CONFIG_PATH`) |
| 引擎訂閱 | `copycat/server/corr_engine.py:132-143,164-184` | 依 `config.tc4_legs()` 逐腿 `subscribe_raw` + 失敗重試,無 symbol 字面值 | — |
| 引擎路由 | `corr_engine.py:224-246` | `_by_symbol[quote.Symbol]` → leg;`parse_stock_realtime` + `minute_end_from_utc_hhmmss(FilledTime)`;**FilledTime 欄寬跨段一致的假設只在 TWF/CME/CBOT/SGX 實證過,OSE 未驗** → 探測項 3 實跑 parse | — |
| River 共用 | `corr_engine.py:104,319,361-363` | river 與 corr 共用 `config.legs`;1K 回補 `collect_1k_minutes`(OSE 1K 支援度未驗 → 探測項 4) | — |
| 行情源 | `copycat/live/corr_source.py:31-34,54-56` | 全天窗 `({ymd}00,{ymd}23)`,不限交易所段 | — |
| 後端測試 | `tests/test_corr_config.py:11-36`(六腿數量鎖,對 DEFAULT_CONFIG)、`:43-59`(第七腿契約樣板 TSM) | 預設六腿測試**不該紅**(只改 json 不動 DEFAULT_CONFIG) | — |
| 路由測試(漏列,review R1 補) | `tests/server/test_corr_routes.py:33,35,50`、`tests/server/test_river_routes.py:33,83` | `create_app` 不傳 path → `_make_corr` 讀 repo 真檔;鎖六腿集合 / 訂閱數 5 → **該紅** | — |
| 前端表 | `frontend/src/components/corr/CorrPanel.tsx:45,71` | 依 `state.legs` 動態列;零改 | — |
| 前端 river | `RiverPanel.tsx:62-66,104-113`、`RiverCards.tsx:29-32,98-106`、`RiverOverlay.tsx:71,128,135` | `colorIndex % RIVER_*.length` 取模 → 第 7 腿會撞 river-1(base 近白粗線色) | — |
| 調色盤 | `frontend/src/components/corr/river-colors.ts:11-35` | 三組 6 常數(stroke/fill/text),註解明寫「腿數超過調色盤時取模循環」;class 字面值供 Tailwind v4 靜態掃描 | 只被上三檔 import |
| CSS token | `frontend/src/index.css:23-31` | `--color-river-1..6`;註解「其餘五色相互可辨且都不是紅/綠」 | `stroke-river-N` 等 utility 由 Tailwind 從 token 產生 |
| 前端測試 | `frontend/src/hooks/useRiver.test.ts` 不碰色數;grep `river-[1-6]` 無測試鎖 6 | — |
| SKILL | `.claude/skills/tc4-market-facts/SKILL.md:138-159` 海外節 | 未記日經 / 韓指事實 | — |
| Catalog 事實 | `spikes/catalog_dump/catalog_Fut.json:12542-12570`(OSE HOT:NK225/NK225M/NK225MC/NK400)、`:11272-11304`(SGX NK);`summary.json` 17 段無 KRX(2026-06-30) | 快照舊 → 探測項 1 重 dump 比對 | — |
| next-time | `docs/next-time.md:758` 跨 UTC 06/22 邊界推播未驗 | 探測項 4 順帶觀察(20:1x 起跑,不跨 06/22 邊界 → 本輪觀察不到,誠實記帳) | — |

## 2. 現況 vs 目標

| 項 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| legs | 六腿 | 七腿(+NK225M 小日經,source tc4) | 引擎零改;前端動態列 | 舊 config 讀者不受影響;server 重啟後才生效(config 啟動時讀一次) |
| river 色 | 6 組 | 7 組(+river-7) | 三 import 檔零改(取模) | 前六色不動 |
| SKILL 海外節 | 無日經/韓指 | 加「日經有 / 韓指無(KRX 段不存在)」一句 | — | — |
| DEFAULT_CONFIG | 六腿 | **不動**(spec 拍板) | 六腿測試不動 | 設定檔壞掉降級仍是六腿 |

## 3. 風險 / 未驗

- OSE 段 `FilledTime` / `PreciseTime` 欄寬、`Bid/Ask` 欄名、1K `Time` 欄是否與 CME/SGX 同 →
  探測項 3/4 用專案 parse 函式實跑(不是只看欄位存不存在)。
- 日經 OSE 交易時段(JST 08:45–15:45 日盤 / 17:00–06:00 夜盤 = 台北 07:45–14:45 / 16:00–05:00)
  幾乎全天有價;台指日盤 08:45–13:45 與 OSE 日盤重疊 → 相關係數三窗在台股盤中有樣本。
- 第 7 色須避開紅/綠(漲跌語意)且與前六色可辨。
