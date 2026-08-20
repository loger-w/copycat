# 現況(2026-08-21)

## Caller map
- `SignalRail` 唯一 caller:`frontend/src/components/stock/StockPage.tsx:184`(props 餵入,無動態用法;
  grep `SignalRail\b` 其餘命中為 test / hook 註解)。
- 合併口徑 `groupSignals` / `groupKindLabels` / `groupRuleNames` 在 `lib/signal-model.ts`(本案不動)。

## 合併列現況(`SignalRail.tsx` 第二行)
| 項目 | 現況 | 目標 |
|---|---|---|
| kind 段容器 | `min-w-0 truncate text-xs`(單行,overflow 省略) | 合併列(segments>1)允許換行 clamp 2 行 |
| 規則名段 | `min-w-0 truncate text-[0.625rem]`,與 kind 段同一 flex 列並排 | 合併列改堆疊於 kind 段下方,clamp 2 行 |
| title | 整列單一 `kindText(ruleText)` | 逐段:kind span 帶 `label(rule_name)`;規則名 span 帶 `rule(對應 kind labels)` |
| 單則列 | 同上 truncate | **不變**(out of scope) |

## 行為契約(不得動)
- 合併組 key = 最早到 id;段序 = 到達序;分隔符「・」aria-hidden;逐段著色 toneOf。
- 無動畫 / 無 ResizeObserver 依賴;rail 寬 `w-52`(208px;實測內容 189px)。

## Backward compat
純前端展示層;無 API / 資料格式 / migration。
