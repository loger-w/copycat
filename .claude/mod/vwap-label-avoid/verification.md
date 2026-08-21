# verification — mod/vwap-label-avoid

| gate | 結果 |
|---|---|
| vitest 全套 | 137 files / 2526 passed |
| tsc -b | 0(fixture `as const` 一度紅,test-infra-fix 已修) |
| eslint src | 0 |
| react-doctor --scope changed | 2 files scanned, No issues |
| mutation | 拿掉 `vwapLabel.x + VWAP_LABEL_W > maLabelLeft` 條件 → 守門案(末點中段不位移)紅;還原綠 |

## SC-1 真環境(devtools MCP,1600×900,prod 8721 週六 = 週五全日資料,2330,MA+均價開)
- before(preview 4173 舊 dist):VWAP `2394.28` y=146.43 / MA5 `2380` y=155.70 → 中心距 **9.27 < 10**,bbox 重疊。
- after(dev 5173 本分支):VWAP y=146.43 不動 / MA5 y=**156.43**(= +EDGE_LABEL_H)/ MA20 170.05 不動。
- 截圖 `docs/specs/mod-vwap-label-avoid/screenshots/SC-1-{before,after}-2330-{preview,dev}(-closeup).png`。
  誠實註記:今日真資料 before 只差 0.7px,肉眼近拍幾乎相同;幾何差距由 vitest fixture(4.3 → ≥10)鎖住。
  PR #78 當日 2330 那組(白 2387.74 壓琥珀 2380)差距更大,待下一交易日盤後 user 過目。

## 白名單
1. VWAP x/y/anchor/class:SC-2 三案未動,全綠;真環境 x=720 (= 800−40−40) y 同 before。
2. MA x=w−R_AXIS_W−2 / 口徑 / toggle 關:SC-1 五案未動,全綠。
3. 極值 / pegs obstacle 原樣(只 concat 一項)。
4. `bandLabels` / `pegs.test` 未動,全綠。
