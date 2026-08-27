# /bug corr-sparse-leg-heal-exempt — spec(originating bug description)

## 症狀

2026-08-27 日盤 `logs/server-20260827-0814.log`:`TC.F.TWF.SXF.HOT`(費半)「TC4 REALTIME 零推播自癒 … 靜默 24xs →
重掛(attempt 1, window_variant=0)」09:45–13:01 共 11 發,每發 = UNSUBQUOTE + SUBQUOTE 一對(TC4 refcount 掀一遍)。
全部 attempt 1 = 每發之間都有真推播把計數清掉 → 不是死訂閱,是稀疏腿的常態靜默撞到 R2 240 s 門檻。
(next-time 08-26 N051 待核項寫「應大幅少於 M0 3 小時 8 發」—— M0 那 8 發是**休市段**,08-27 核過休市段零發 = 逐腿閘 PASS;
日盤這 11 發是另一件事。)

## 根因

`tc4.TC4QuoteSource._heal_tick` R2 對「曾有推播、之後靜默 > t2」的 symbol 一律重掛;corr session t2 = 240 s。
SXF 日盤 94.4% 時間沒成交(tc4-market-facts),4 分鐘零推播是常態 → 每次都是假警報。既有兩個開關都不對:
`heal_symbol_silence_secs=None` 是 session 級(會把 10 條海外腿一起關);`heal_symbol_active` 閘掉的 symbol
**連 R1 母體都扣掉**(整條 session 死時 SXF 永遠沒人救)。

## 要求(user 08-27 拍板「直接修」)

1. `TC4QuoteSource(heal_sparse_symbols: frozenset[str])`:集合內 symbol **只**跳過 R2,R1 母體照算(max of last push,
   稀疏腿常靜默不會誤觸 R1;整批重掛時跟著重掛)。
2. `CorrQuoteSource` 透傳;`corr_config.Leg.sparse: bool = False`,`_parse_legs` 只認 JSON 字面 `true`;`DEFAULT_CONFIG`
   與 `configs/correlation.json` 的 SXF 皆標 sparse,parity 測試鎖兩邊集合一致。
3. `app._default_corr_source(calendar, config)` 從設定檔算 `heal_sparse_symbols`;`_make_corr` 只 load 一次同一份 config。
4. 既有行為白名單:R1 判定式、`heal_symbol_active` 閘的母體扣除、退避 / 換窗階梯、`_heal_resub`、個股 / TXO / futures
   source 的自癒參數逐字不動;`_EXPECTED_LEGS` 四欄逐字契約與腿序不動。

## 驗證 seam

- `tests/live/test_tc4.py::TestHealSparseSymbol`(R2 豁免 / R1 仍整批 / 稀疏腿不誤觸 R1)。
- `tests/live/test_corr_source.py::TestHealDefaults`(透傳)、`tests/test_corr_config.py`(解析 + parity)、
  `tests/server/test_main_wiring.py::test_corr_sparse_legs_come_from_the_config_file`(app 接線)。
- 真實環境:prod 重啟後次一交易日 `grep "零推播自癒" logs/server-*.log | grep SXF` 日盤段應 0 筆;
  `grep "零推播自癒" | grep -v SXF` 其他腿行為不變。

## 非目標

- 6949 冷門個股每分鐘一發(自選動態集合無設定檔可標,走 08-26 節退避條)。
- IX0001 13:25–13:35 收盤段 19 發(閘上界拍板題,另案)。
- 稀疏腿改長門檻而非豁免(要先量最長真靜默,next-time)。
