# UC 池劇本格子評估 round 3(pre-registered;2026-07-15-round3)

- 宇宙:main n=1621 / 低開 n=955 / cell_b n=1738;停損 = 結構高×(1+b) ∧ 硬線(guard 1.0%);災難 = 回落式(D 6.0% / r 2.0%);b 候選 = [0.025, 0.0375]。
- 判定段 = in-window(< 2026-07-11,候選;b/D/r 參數同源,循環風險註記);forward 段僅複核,門檻 = ≥20 交易日(SC-2)。
- D5 壓測組合 = stress_slippage + guard fill = bar.high 疊加;等日曆 4 段。

## 變體表(in-window)

| cell | variant | b | n | 淨EV | p_win | 壓測EV | 壓測n | 段+ | vs基準線 | 封頂b_capped | D5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| cell_a | inner_0.45 | 0.025 | 804 | -0.0004 | 0.52 | -0.0033 | 804 | 2/4 | -0.0032 | 385 | FAIL |
| cell_a | inner_0.45 | 0.0375 | 804 | -0.0002 | 0.52 | -0.0029 | 804 | 2/4 | -0.0033 | 569 | FAIL |
| cell_b | dist_0.03 | 0.025 | 863 | 0.0003 | 0.45 | -0.0030 | 863 | 1/4 | -0.0027 | 863 | FAIL |
| cell_b | dist_0.03 | 0.0375 | 863 | 0.0003 | 0.45 | -0.0030 | 863 | 1/4 | -0.0031 | 863 | FAIL |
| cell_c | rally_0.03 | 0.025 | 551 | 0.0000 | 0.48 | -0.0033 | 551 | 1/4 | -0.0013 | 84 | FAIL |
| cell_c | rally_0.03 | 0.0375 | 551 | 0.0013 | 0.51 | -0.0019 | 551 | 1/4 | -0.0001 | 160 | FAIL |
| cell_c | rally_0.05 | 0.025 | 365 | 0.0013 | 0.45 | -0.0020 | 365 | 2/4 | 0.0000 | 157 | FAIL |
| cell_c | rally_0.05 | 0.0375 | 365 | 0.0023 | 0.46 | -0.0010 | 365 | 2/4 | 0.0008 | 264 | FAIL |

## forward 段(≥ forward_start;複核輸出)

- cell_a:inner_0.45:b0.025:forward 樣本 0,僅候選
- cell_a:inner_0.45:b0.0375:forward 樣本 0,僅候選
- cell_b:dist_0.03:b0.025:forward 樣本 0,僅候選
- cell_b:dist_0.03:b0.0375:forward 樣本 0,僅候選
- cell_c:rally_0.03:b0.025:forward 樣本 0,僅候選
- cell_c:rally_0.03:b0.0375:forward 樣本 0,僅候選
- cell_c:rally_0.05:b0.025:forward 樣本 0,僅候選
- cell_c:rally_0.05:b0.0375:forward 樣本 0,僅候選

## 底倉臂 + Q2(吃法可行;in-window 候選判定)

### b0.025(主變體(判定用))— Q2:候選 FAIL(in-window,參數同源)

- tiger 合併:n=1621 淨EV=-0.0001 SE=0.0020 z=-0.07 p=1.0000
- forward:forward 樣本 0,僅候選

| 格(分點數:gap 桶) | n | 淨EV | z | p | 開放 |
|---|---:|---:|---:|---:|---|
| 1:gap_0.01_0.03 | 530 | -0.0024 | -0.94 | 1.0000 | 否 |
| 1:gap_0.03_0.055 | 470 | -0.0006 | -0.20 | 1.0000 | 否 |
| 1:gap_0.055_0.075 | 204 | 0.0008 | 0.20 | 0.4209 | 否 |
| 2plus:gap_0.01_0.03 | 166 | -0.0020 | -0.49 | 1.0000 | 否 |
| 2plus:gap_0.03_0.055 | 185 | 0.0056 | 1.20 | 0.1153 | 否 |
| 2plus:gap_0.055_0.075 | 66 | 0.0070 | 0.88 | 0.1886 | 否 |

### b0.0375(敏感度列)— Q2:候選 FAIL(in-window,參數同源)

- tiger 合併:n=1621 淨EV=0.0001 SE=0.0020 z=0.07 p=0.4717
- forward:forward 樣本 0,僅候選

| 格(分點數:gap 桶) | n | 淨EV | z | p | 開放 |
|---|---:|---:|---:|---:|---|
| 1:gap_0.01_0.03 | 530 | -0.0021 | -0.82 | 1.0000 | 否 |
| 1:gap_0.03_0.055 | 470 | -0.0002 | -0.07 | 1.0000 | 否 |
| 1:gap_0.055_0.075 | 204 | 0.0008 | 0.21 | 0.4161 | 否 |
| 2plus:gap_0.01_0.03 | 166 | -0.0012 | -0.31 | 1.0000 | 否 |
| 2plus:gap_0.03_0.055 | 185 | 0.0054 | 1.16 | 0.1240 | 否 |
| 2plus:gap_0.055_0.075 | 66 | 0.0070 | 0.88 | 0.1886 | 否 |

## 保險精算表(SC-4;in-window)

| 變體 | 機制 | 觸發 n | 觸發率 | 均pnl | 砍對(收盤鎖死) | 砍錯 |
|---|---|---:|---:|---:|---:|---:|
| cell_a:inner_0.45:b0.025 | hardline | 129 | 16.0% | -0.0545 | 58.9% | 41.1% |
| cell_a:inner_0.45:b0.025 | struct_fixed | 83 | 10.3% | -0.0529 | 22.9% | 77.1% |
| cell_a:inner_0.45:b0.025 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_a:inner_0.45:b0.025 | disaster_retrace | 30 | 3.7% | -0.0482 | 13.3% | 86.7% |
| cell_a:inner_0.45:b0.025 | disaster_x | 0 | 0.0% | — | — | — |
| cell_a:inner_0.45:b0.0375 | hardline | 154 | 19.2% | -0.0561 | 55.2% | 44.8% |
| cell_a:inner_0.45:b0.0375 | struct_fixed | 23 | 2.9% | -0.0645 | 30.4% | 69.6% |
| cell_a:inner_0.45:b0.0375 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_a:inner_0.45:b0.0375 | disaster_retrace | 46 | 5.7% | -0.0475 | 15.2% | 84.8% |
| cell_a:inner_0.45:b0.0375 | disaster_x | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.025 | hardline | 385 | 44.6% | -0.0392 | 50.4% | 49.6% |
| cell_b:dist_0.03:b0.025 | struct_fixed | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.025 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.025 | disaster_retrace | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.025 | disaster_x | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.0375 | hardline | 385 | 44.6% | -0.0392 | 50.4% | 49.6% |
| cell_b:dist_0.03:b0.0375 | struct_fixed | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.0375 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.0375 | disaster_retrace | 0 | 0.0% | — | — | — |
| cell_b:dist_0.03:b0.0375 | disaster_x | 0 | 0.0% | — | — | — |
| cell_c:rally_0.03:b0.025 | hardline | 66 | 12.0% | -0.0362 | 45.5% | 54.5% |
| cell_c:rally_0.03:b0.025 | struct_fixed | 164 | 29.8% | -0.0467 | 28.7% | 71.3% |
| cell_c:rally_0.03:b0.025 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_c:rally_0.03:b0.025 | disaster_retrace | 1 | 0.2% | -0.0419 | 0.0% | 100.0% |
| cell_c:rally_0.03:b0.025 | disaster_x | 0 | 0.0% | — | — | — |
| cell_c:rally_0.03:b0.0375 | hardline | 96 | 17.4% | -0.0440 | 49.0% | 51.0% |
| cell_c:rally_0.03:b0.0375 | struct_fixed | 84 | 15.2% | -0.0590 | 33.3% | 66.7% |
| cell_c:rally_0.03:b0.0375 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_c:rally_0.03:b0.0375 | disaster_retrace | 4 | 0.7% | -0.0462 | 25.0% | 75.0% |
| cell_c:rally_0.03:b0.0375 | disaster_x | 0 | 0.0% | — | — | — |
| cell_c:rally_0.05:b0.025 | hardline | 114 | 31.2% | -0.0350 | 53.5% | 46.5% |
| cell_c:rally_0.05:b0.025 | struct_fixed | 51 | 14.0% | -0.0475 | 29.4% | 70.6% |
| cell_c:rally_0.05:b0.025 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_c:rally_0.05:b0.025 | disaster_retrace | 0 | 0.0% | — | — | — |
| cell_c:rally_0.05:b0.025 | disaster_x | 0 | 0.0% | — | — | — |
| cell_c:rally_0.05:b0.0375 | hardline | 123 | 33.7% | -0.0368 | 52.0% | 48.0% |
| cell_c:rally_0.05:b0.0375 | struct_fixed | 22 | 6.0% | -0.0612 | 50.0% | 50.0% |
| cell_c:rally_0.05:b0.0375 | struct_ratchet | 0 | 0.0% | — | — | — |
| cell_c:rally_0.05:b0.0375 | disaster_retrace | 1 | 0.3% | -0.0424 | 0.0% | 100.0% |
| cell_c:rally_0.05:b0.0375 | disaster_x | 0 | 0.0% | — | — | — |
| base_arm:b0.025 | hardline | 538 | 33.2% | -0.0501 | 55.9% | 44.1% |
| base_arm:b0.025 | struct_fixed | 0 | 0.0% | — | — | — |
| base_arm:b0.025 | struct_ratchet | 51 | 3.1% | -0.0525 | 27.5% | 72.5% |
| base_arm:b0.025 | disaster_retrace | 63 | 3.9% | -0.0460 | 25.4% | 74.6% |
| base_arm:b0.025 | disaster_x | 0 | 0.0% | — | — | — |
| base_arm:b0.0375 | hardline | 572 | 35.3% | -0.0508 | 54.7% | 45.3% |
| base_arm:b0.0375 | struct_fixed | 0 | 0.0% | — | — | — |
| base_arm:b0.0375 | struct_ratchet | 4 | 0.2% | -0.0532 | 25.0% | 75.0% |
| base_arm:b0.0375 | disaster_retrace | 69 | 4.3% | -0.0460 | 24.6% | 75.4% |
| base_arm:b0.0375 | disaster_x | 0 | 0.0% | — | — | — |

## 基準線(同宇宙同風控:ratchet b + 災難 + 硬線)

| universe:b | in-window n | 淨EV | forward |
|---|---:|---:|---|
| cellb:b0.025 | 1560 | 0.0030 | forward 樣本 0,僅候選 |
| cellb:b0.0375 | 1560 | 0.0034 | forward 樣本 0,僅候選 |
| low:b0.025 | 944 | 0.0013 | forward 樣本 0,僅候選 |
| low:b0.0375 | 944 | 0.0014 | forward 樣本 0,僅候選 |
| main:b0.025 | 1486 | 0.0028 | forward 樣本 0,僅候選 |
| main:b0.0375 | 1486 | 0.0031 | forward 樣本 0,僅候選 |

限制:D=0.060 為 0.5% 步進中點 banker's tie-break;D 以開盤錨校準、套用為進場錨
(entry×(1+D)),盤中進場臂武裝偏早(保守向)。

## 敏感度補充(D=0.065 tie-break;跑於 out/fade_cells_r3_d065,不入判定)

D=0.065 重跑:Q2 主變體 tiger 合併 −0.00%(vs −0.01%)、8 變體 D5 全 FAIL 不變、
各 EV 差 ±0.02pp 內——結論對 D tie-break **不敏感**(change-spec §5a R8 義務完成)。

## 對照註記

- Q1(池子有肉)不在本檔:見 `fade_round3_sec0_sensitivity_2026-07-15.md`
  (誠實區間 +0.13~+0.85%)與 `uc_pool_fade_2026-07-15-noguard-lockgrid.md`;
  引用 noguard +0.85% 必附上界警語。
- 白名單迴歸:round 2 config 重跑輸出與 `uc_cells_2026-07-15.md` 完全一致
  (out/fade_cells_r2_regression,除標題日期)。
- 與 round 2 對照(同宇宙底倉/無條件近似):guarded 淨 EV −0.40% → 本輪 ≈0,
  停損語意重錨吃回約 0.4pp;距 noguard 同宇宙上界 +0.68% 仍差約 0.7pp,
  全數為硬線保費(見精算表:底倉硬線觸發 33.2%、每次 −5.0%、砍對 55.9%)。
