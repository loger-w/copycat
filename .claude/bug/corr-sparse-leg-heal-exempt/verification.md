# fix/corr-sparse-leg-heal-exempt — verification

主 tree 直做;branch 自 master `8200f210` 開。working tree 另有他 session 未提交的
`.claude/skills/ops-discipline/SKILL.md` 與 repo root 六份 `pr-11N-review*.md`,不碰不 commit。

## 0. 入口證據(2026-08-27,prod `51b93006` 08:14 起的 log)

```
grep "零推播自癒" logs/server-20260827-0814.log | grep -oE "TC\.[A-Z]+\.[A-Z]+\.[A-Z0-9.]+" | sort | uniq -c
    172 TC.S.TWS.6949
     10 TC.F.TWF.SXF.HOT      (+ 13:01 一發 = 11)
      2 TC.F.SGX.TWN.HOT
SXF 時戳:09:45 09:52 10:14 10:22 10:26 10:39 10:44 10:52 11:04 11:08 13:01 —— 全「靜默 24xs → 重掛(attempt 1, window_variant=0)」
休市段(08:45 前 / 13:45 後):0 發 → N051 逐腿閘 PASS;M0 3 小時 8 發是休市段,與本輪不同一件事。
```

## 1. Phase 1 feedback loop(紅先行,commit 60ce1395)

```
.venv\Scripts\python -m pytest -q tests/live/test_tc4.py -k TestHealSparseSymbol
→ TypeError: TC4QuoteSource.__init__() got an unexpected keyword argument 'heal_sparse_symbols'(3 failed)
```
當時三條:R2 豁免(只重掛非稀疏腿)/ R1 仍整批含稀疏腿 / 稀疏腿靜默不誤觸 R1(HEAL_A 活著 → 零請求);第四條
`r1_takes_over_when_the_population_is_only_sparse_symbols` 為 PR #120 review 追加,現為 4 條(四條都在建構子帶
`heal_sparse_symbols=`,今天照原版 stash 手法重跑會是 4 failed —— pr-130 F-06)。
秒級(0.14 s)、確定性、FakeApi 記全 REQ 序。

## 2. Phase 2 最小重現

兩個 symbol、一個標 sparse、`_last_push` 皆早於門檻、單次 `_heal_tick(100.0)`。每個元素 load-bearing:
拿掉非稀疏腿就分不出「R2 只跳過 sparse」與「R2 整個沒跑」;拿掉 R1 案就驗不到「仍在母體」。

## 3. Phase 3 假說(單一;attempt 全 1 直接證實)

| # | 假說 | 預測 | 結果 |
|---|---|---|---|
| A | R2 240 s 對日盤常態靜默 4 分鐘的稀疏腿是假警報(不是死訂閱) | 每發 attempt 1、間隔 ≥ 240 s 且中間有真推播 | 成立(11/11) |
| 排除 | 休市段閘失效(N051) | 休市段應有發 | 不成立(0 發) |

## 4. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `60ce1395` | test | tc4 三條 + corr_source 透傳 + config 解析 / parity + app 接線 |
| `4982f392` | 🔴 | `TC4QuoteSource(heal_sparse_symbols=)` R2 `continue`;`CorrQuoteSource` 透傳;`Leg.sparse` + `_parse_legs` 只認字面 true;DEFAULT_CONFIG / JSON SXF 標;`app._default_corr_source(calendar, config)`、`_make_corr` 同一份 config |
| `3446f71d` | chore | CLAUDE.md §4 契約條、tc4-market-facts SXF 事實、next-time N051 改口 + 三條留尾、spec |

## 5. 反向驗證(PASS;pr-120 F-05 校正為 mutation 級,2026-08-27 晚實跑)

原版 `git stash push copycat/live/tc4.py` 把建構子參數與 `_heal_tick` 的 `continue` 一起撤掉,(當時)三條全炸在 TypeError
(review 追加第四條後為 4 條,同樣全炸)——
與 §1 紅先行同一個紅,證不到那行 `continue` 是 load-bearing。改成只註解掉 `_heal_tick` 的
`if sym in self._heal_sparse: continue` 兩行(簽名不動):

```
pytest tests/live/test_tc4.py -k HealSparse
FAILED TestHealSparseSymbol::test_sparse_symbol_is_exempt_from_r2
FAILED TestHealSparseSymbol::test_sparse_symbol_does_not_trigger_r1_while_another_leg_is_alive(原名 …_keep_r1_from_firing)
2 failed, 2 passed
git checkout -- copycat/live/tc4.py → 4 passed(兩行以 `# MUTANT` 佔位取代,還原後 grep MUTANT = 0)
```
紅的兩條:`is_exempt_from_r2` 直接釘 R2 豁免;`…while_another_leg_is_alive` 是另一腿活著 → R1 結構上不成立,
唯一可能的重掛只剩 R2 —— 撤掉 `continue` 後稀疏腿走 R2 被重掛,所以也紅。R1 仍救稀疏腿那條照綠
(R1 路徑不經 `continue`)—— `continue` 是 load-bearing。
簽名層的紅由 §1 涵蓋不重複計。

## 9. Blast radius

- `TC4QuoteSource(` 直接建構:`app.py:349`(stock / txo 預設)—— 新參數預設 `frozenset()`,行為不變。
- `Leg(` 建構點 19 處皆 4 位置參數,新欄預設 False;`_EXPECTED_LEGS` 四欄逐字契約未動、腿序未動。
- `tc4_legs()` 讀者:`corr_engine` 三處(訂閱集合)不看 sparse。
- `_heal_symbol_silence` 讀者只在 `_heal_tick`;個股 / TXO / futures source 未帶 sparse → 逐字舊行為。

## 6. 真實環境

- 入口證據(§0)= 真環境紅燈:prod 08-27 日盤 SXF 11 發全 attempt 1。
- 綠燈判準(prod 重啟後**次一交易日**;08-27 收盤後 8721 尚未重新起來,本輪無法當日驗):
  `grep "零推播自癒" logs/server-<次日>.log | grep SXF` **全日 0 筆**;若非 0,同一秒必須有其他腿一起出現(R1 整批)才算
  PASS,單獨出現 = FAIL。`grep "零推播自癒" | grep -v SXF` 其他腿行為不變(6949 冷門檔每分鐘一發是另一條,不變)。
- 未改功能抽查(自動化代):`tests/live/test_tc4.py` 全綠含 R1 / R2 / 階梯 / 換窗 / 時段閘既有 20+ 條;`test_corr_engine`
  訂閱集合不看 sparse;`test_main_wiring` 時段閘三條原封。
- 盤中不起第二台 corr session(同 symbol 跨 session 只推一邊,CLAUDE.md §8 / tc4-market-facts)。

## 7. 自動化 gate(最終 HEAD a8473ef2,主 tree)

```
3115 passed, 1 warning in 182.18s (0:03:02)
All checks passed!
0 errors, 0 warnings, 0 informations
42/42 PASS
 Test Files  151 passed (151)
      Tests  2829 passed (2829)
tsc exit=0
eslint exit=0
```
react-doctor:--scope changed 掃描無 finding(react-doctor 行未列 = 0 issues,見 gates.log 原文)。

## 7a. two-axis review round 1(`code-review-round-1.json`)

Standards 7 條(1 P2 judgement:heal_* Data Clump → next-time;6 P3:折行 / import / 註解引 skill / base 腿誤標 WARNING / as-is ×2);
Spec 7 條(2 P2:母體只剩稀疏腿 R1 接手 → 註解 + 測試釘住、真實環境判準改「全日 0 / 同秒成批」;P3 ×4 收修;P5 反駁)。
收修 commit `ffade4c8`(test)/ `a95a8e3d`(🔴)/ `a8473ef2`(chore)。

## 8. 需 user 過目 / 拍板

- 無 UI 變更。次一交易日盤後 §6 判準一句話回報即可。
- 仍待拍板:IX0001 收盤段閘上界 13:35 → 13:31(next-time 08-27 節)。

## 10. 留尾(`docs/next-time.md` 2026-08-27 節)

sparse 是人工標記非量測(SXF 真死時只剩 R1)/ 6949 冷門個股同型走退避條 / IX0001 收盤段拍板 / `HealPolicy` 收攏六參數。
