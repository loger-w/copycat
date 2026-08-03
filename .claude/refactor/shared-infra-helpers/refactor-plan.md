# Refactor Plan — shared-infra-helpers

**動機(Phase 1)**:三組基建樣板重複已造成實際 drift:分位數三份演算法分岔(round vs
truncate)、_fmt 兩份語意分岔(int/str 處理不同)、atomic write 27 處手刻任一處漏
`os.replace` 語意即損檔風險。統一收斂降低未來輪次(fade round 6+)加新報告 / 新資料集
時的複製錯誤面。

**不可違反前提**:行為零差異 — 所有報告數字、檔案輸出 byte-level 不變。
User 拍板(2026-07-20):分位數收斂單一模組**保留兩種演算法**;atomic write **全 27 處**換。

## 新模組落點

| 模組 | 內容 | 理由 |
|---|---|---|
| `copycat/fileio.py`(root) | `atomic_write_text(path, content)`(write_text 版,預設 newline 翻譯不變)+ `atomic_open_text(path)` context manager(`open("w", encoding="utf-8", newline="")` 版,csv 用) | data/ 與 backtest/ 都用 → root。兩 helper 精確對應既有兩種形狀,**不合併**(newline 語意不同) |
| `copycat/configio.py`(root) | `load_dataclass_json(path, cls, *, tuple_keys, unknown_label)` | 三份 loader 樣板唯一差異 = 錯誤字串 + tuple_keys → 參數化。fade 版事後 validate 留在 caller |
| `copycat/backtest/quantiles.py` | `quantile_round(values, q)`(= 現 _pctl)、`quantiles_round(values)`(= 現 _quantiles dict 版,內用 quantile_round)、`quantile_trunc(vals, p)`(= 現 fade_diagnose._quantile) | 只有 backtest 用 → 子包。兩演算法**並存**,docstring 註明差異與「統一即改數字」警告 |
| `copycat/backtest/report_fmt.py` | `fmt_cell(v)`(= report._fmt)、`fmt_num(v, fmt=".4f")`(= fade_report._fmt)、`fmt_quantiles(q, spec=".2%")`(= 兩份逐字相同的 _fmtq) | 語意不同的兩份 _fmt **並存不合併**;_fmtq 是逐字重複 → 真合併。**追加項(review R2 留痕)**:_fmtq 非 user 原三組點名項,係盤點時新發現的逐字重複,已於 2026-07-20 盤點回報時向 user 揭露(「另外發現 _fmtq 也有兩份」),與 _fmt 同屬 format helper 收斂;最終回報再列明 |

範圍外:`backtest/search.py:_quantile`(契約不同:吃 sorted 輸入、無 None、ceil 演算法,
GA 搜索熱路徑)→ 記 docs/next-time.md,不動。
`fade_entry_anatomy._fmt_rate`(單份無重複)不動。
`server/engine._fmt_precise_time`、`data/models` 的 fmt(語意無關)不動。

## 步驟(每步單獨綠、單獨 commit)

| # | 類型 | 內容 | 檔數 | 驗證 |
|---|---|---|---|---|
| 1 | 🟢 | characterization tests:三份分位數(含 n=6 p=0.5 分歧點)、兩份 _fmt(int/str/None 差異)、兩份 _fmtq(逐字相同)、**三份 loader unknown-key 錯誤訊息逐字斷言 `str(exc.value)`(review R1:字串鎖進測試,防步驟 4 label 打錯)** | +1 test 檔 | pytest 新檔綠 + 全綠 |
| 2 | 🔵 | 新增 `copycat/fileio.py` + 換 data/ 6 檔 12 處 | 7 | pytest data/ + 全綠 |
| 3 | 🔵 | 換 backtest/ 7 檔 15 處(fileio) | 7 | pytest backtest/ + 全綠 |
| 4 | 🔵 | 新增 `copycat/configio.py` + 換 3 份 loader | 4 | config 相關測試 + 全綠 |
| 5 | 🔵 | 新增 `quantiles.py` + `report_fmt.py`,舊私有函式刪除、call site 改 import。逐檔改點清單(review R3):<br>- fade_anatomy.py:刪 `_quantiles`(37-45)+ `_fmtq`(490-497),站內呼叫改 import<br>- fade_entry_anatomy.py:**兩條線**:改第 16 行 `from fade_anatomy import _quantiles` → 新模組;刪本地 `_fmtq`(451-458)改 import(`_fmt_rate` 不動)<br>- fade_cells.py:刪 `_pctl`(477-482)改 import `quantile_round`<br>- fade_diagnose.py:刪 `_quantile`(32-37)改 import `quantile_trunc`<br>- report.py:刪 `_fmt`(11-16)改 import `fmt_cell`<br>- fade_report.py:刪 `_fmt`(9-10)改 import `fmt_num`<br>- tests characterization 檔:import 改指新位置(**斷言值一字不改**) | ~9 | pytest 全綠 |
| 6 | 🟢 | 新 helper 模組直接單元測試(fileio atomic 語意、configio unknown/tuple) | +1~2 test 檔 | 全綠 |

每步 diff 預估 < 100 行(步驟 2/3 為機械替換,每處 3 行 → 2 行)。

## 站點清單(步驟 2/3 執行時逐一核對形狀)

write_text 形:store:41、fade_anatomy:480,628、fade_diagnose:490,542、fade_cells:1174,1414,1892,1966,2058、
fade_report:264,271、pipeline:191,313,537、fade_entry_anatomy:441,595、fade_pipeline:732、
backfill_finmind:162、backfill_daytrade:167、backfill_brokers:161(manifest 形狀執行時確認)
csv handle 形:label_events:107、scan_events:38、backfill_finmind:100、backfill_daytrade:79、
backfill_brokers:150、pipeline:178

執行時規則:任一站點形狀偏離兩種標準形(不同 tmp 命名、不同 encoding、寫後有額外動作)
→ 保持原樣不硬套,記入 plan 附註。

## 風險與對策

- **R1 tmp 檔命名**:全部站點沿用 `path.with_suffix(".tmp")` → helper 同式,無變。
- **R2 例外路徑**:現行為 = 寫 tmp 中途炸 → tmp 殘留、不 replace。helper 不加 cleanup(加了才是行為變)。
- **R3 newline**:write_text 版(預設 newline=None,Windows 翻譯 os.linesep)與 csv 版(newline="")**不可互換** — 兩 helper 分開,逐站點按原形選。
- **R4 characterization 測試在步驟 5 改 import**:僅 import 行變,golden 斷言值凍結;任何斷言值需要改 = 行為變了 = 停。
- **R5 pyright**:`cls(**payload)` 泛型化後的 type ignore 沿用既有寫法。

## 完成判準

pytest 612+新增 全綠、ruff、pyright、`copycat validate` PASS(four/five replay 先跑)、
每 commit 純 🔵 或純 🟢、`git diff master -- '*.py'` 中無任何輸出字串 / 數值運算變更。
