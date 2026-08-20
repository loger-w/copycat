# verification(2026-08-21)

## 自動化 gate(frontend/)
| step | command | exit |
|---|---|---|
| vitest | `npx vitest run` → 134 files / 2346 tests passed(review 後重跑) | 0 |
| tsc | `npx tsc -b` | 0 |
| eslint | `npx eslint src` | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` → No issues found | 0 |
(後端未動;pytest / ruff / pyright / validate 不在觸及範圍)

## 真實環境(SC-3)
- 通道:claude-in-chrome 未連線、chrome-devtools-mcp profile 被他 session 鎖 → 退 headless Chrome
  `--screenshot` 對 vite dev(5173)臨時 host(`b3-host.html`,已刪)渲染 08-20 prod jsonl 真實兩組合併列
  (3189 09:06:09 cdp_cross+crash / 8358 09:04:39 cdp_cross+surge)+ 單則列 2408 對照。
- 證據:`evidence/SC-3-b3-host.png`(畫面)、`evidence/SC-3-b3-host-probe.png`(DOM 量測讀數)。
- 量測(rail clientWidth 207):3189 kind 段 client=154 / scroll=154(零裁切;改前 95/154)、clamp=true;
  8358 149/149;單則列 2408 clamp=false(truncate 保留)69/69。
- 逐段 title 真 DOM:「爆跌 -2.06%(爆拉爆跌)」「跌破 CDP 中軸(CDP 穿越)」「爆拉爆跌:爆跌 -2.06%」「CDP 穿越:跌破 CDP 中軸」。
- 未改功能抽 2:規則區空態「尚無規則」、提示區「提示音 關」皆正常渲染(同截圖)。

## round-2 截圖(review 後,`evidence/SC-3-b3-host-round2.png`)
- 合成三段列(8358 + vol_burst 同 tick):kind 段 rows=2、client=scroll=154、li 高 80;價格 top 與 kind 首行 top 差 1px(baseline 對齊,L1-1 refuted)。
- 兩段列 3189:rows=1、li 高 64;單則列 2408:clamp=false、li 高 48。

## 白名單
W1 段序到達序(測試 SC-5 節綠)/ W2 aria-hidden + tone(綠)/ W3 key(groupSignals 未動)/ W4 onSelect(綠)/
W5 rule_name 缺值無段(新 edge 測試綠)/ W6 單則列結構:仍 `flex` 並排 + truncate(量測 clamp=false)。
## Migration:無。
