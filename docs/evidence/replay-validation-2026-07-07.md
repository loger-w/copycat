# Replay characterization 驗證存證(2026-07-07)

- 產生方式:`python -m copycat validate`(spec SC-2~SC-6 golden gate);golden 出處 `docs/evidence/`(intraday_playbook §2d / open_gap_definition §2-3 / strategy.md §5)。
- Run:`out/five_tigers`(SC-2/3/6)與 `out/four_tigers`(SC-4/5),config = 預設(strategy-v1 baseline)。
- **SC-1 事件覆蓋**:五虎 1029 事件 T 日 1K 覆蓋 **100%**(missing_t = 0,`data/manifest.json` 同值);T+1 缺 1K 者(處置股/對照組未抓,虎事件 6 筆)以日線 fallback 補部分訊號並在 events.jsonl `skip` 欄明列。對照組 2482 事件 T+1 1K 缺 2068 筆(strategy.md §9 已知:對照組 T+1 尚未抓齊)。
- **SC-7**(watchlist 可替換):同一份 code 以 four/five watchlist 重跑,cohort 各為 542 / 1029、excluded 487 / 0 — 零 code 改動。**SC-8**(無 lookahead):結構測試於 test suite(56 passed)。
- 修復記錄:gap 源改日線 open(權威競價價)、競價量改 tick 首筆(golden 同源)、T+1 無效 1K 走日線 fallback、SC-4 事件集歸屬修正(四虎 core)— 皆為定義對齊,未放寬任何容忍度。

| SC | 項目 | golden | actual | 容忍 | 結果 |
|---|---|---|---|---|---|
| SC-2 | 鎖板 <09:05 n | 175 | 175 | ±5% | PASS |
| SC-2 | 鎖板 <09:05 med gap | +7.40% | +7.41% | ±0.5pp | PASS |
| SC-2 | 鎖板 <09:05 續鎖 | +18.30% | +18.29% | ±1pp | PASS |
| SC-2 | 鎖板 09:05-10:00 n | 322 | 322 | ±5% | PASS |
| SC-2 | 鎖板 09:05-10:00 med gap | +3.50% | +3.50% | ±0.5pp | PASS |
| SC-2 | 鎖板 09:05-10:00 續鎖 | +5.60% | +5.59% | ±1pp | PASS |
| SC-2 | 鎖板 10:00-12:00 n | 311 | 311 | ±5% | PASS |
| SC-2 | 鎖板 10:00-12:00 med gap | +2.40% | +2.37% | ±0.5pp | PASS |
| SC-2 | 鎖板 10:00-12:00 續鎖 | +6.80% | +6.75% | ±1pp | PASS |
| SC-2 | 鎖板 12:00-13:00 n | 125 | 125 | ±5% | PASS |
| SC-2 | 鎖板 12:00-13:00 med gap | +1.50% | +1.51% | ±0.5pp | PASS |
| SC-2 | 鎖板 12:00-13:00 續鎖 | +11.20% | +11.20% | ±1pp | PASS |
| SC-2 | 鎖板 13:00+ n | 90 | 90 | ±5% | PASS |
| SC-2 | 鎖板 13:00+ med gap | +0.60% | +0.57% | ±0.5pp | PASS |
| SC-2 | 鎖板 13:00+ 續鎖 | +4.40% | +4.44% | ±1pp | PASS |
| SC-3 | violent med gap | +6.20% | +4.03% | ±3pp | PASS |
| SC-3 | violent 續鎖 | +3.30% | +5.63% | ±3pp | PASS |
| SC-3 | natural_early 續鎖 | +18.30% | +18.71% | ±3pp,且 natural≫violent | PASS |
| SC-4 | 早盤鎖 >=40% med gap | +6.00% | +6.00% | ±0.5pp | PASS |
| SC-4 | 早盤鎖 >=40% 續鎖 | +13.20% | +13.23% | ±1pp | PASS |
| SC-4 | 早盤鎖 <15% 續鎖 | +0.00% | +0.00% | ±1pp | PASS |
| SC-5 | gap <0% n | 92 | 92 | ±5% | PASS |
| SC-5 | gap <0% E[開→收] | +0.72% | +0.72% | ±0.5pp | PASS |
| SC-5 | gap <0% 續鎖 | +2.20% | +2.17% | ±1pp | PASS |
| SC-5 | gap 0-1% n | 63 | 63 | ±5% | PASS |
| SC-5 | gap 0-1% E[開→收] | +0.26% | +0.26% | ±0.5pp | PASS |
| SC-5 | gap 0-1% 續鎖 | +4.80% | +4.76% | ±1pp | PASS |
| SC-5 | gap 1-3% n | 96 | 96 | ±5% | PASS |
| SC-5 | gap 1-3% E[開→收] | -1.60% | -1.60% | ±0.5pp | PASS |
| SC-5 | gap 1-3% 續鎖 | +0.00% | +0.00% | ±1pp | PASS |
| SC-5 | gap 3-7% n | 170 | 170 | ±5% | PASS |
| SC-5 | gap 3-7% E[開→收] | -1.64% | -1.64% | ±0.5pp | PASS |
| SC-5 | gap 3-7% 續鎖 | +9.40% | +9.41% | ±1pp | PASS |
| SC-5 | gap 7-9.5% n | 45 | 45 | ±5% | PASS |
| SC-5 | gap 7-9.5% E[開→收] | -3.47% | -3.47% | ±0.5pp | PASS |
| SC-5 | gap 7-9.5% 續鎖 | +6.70% | +6.67% | ±1pp | PASS |
| SC-5 | gap 漲停開 n | 76 | 76 | ±5% | PASS |
| SC-5 | gap 漲停開 E[開→收] | -1.26% | -1.26% | ±0.5pp | PASS |
| SC-5 | gap 漲停開 續鎖 | +26.30% | +26.32% | ±1pp | PASS |
| SC-6 | 競價 <3% med gap | +1.80% | +1.70% | ±0.5pp | PASS |
| SC-6 | 競價 3-8% med gap | +2.70% | +2.50% | ±0.5pp | PASS |
| SC-6 | 競價 >=8% med gap | +9.00% | +8.53% | ±0.5pp | PASS |

42/42 PASS