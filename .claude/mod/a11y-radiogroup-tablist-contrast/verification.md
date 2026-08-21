# verification — mod/a11y-radiogroup-tablist-contrast(R2)

## 自動化(frontend/,2026-08-21 15:0x,fix 波後由 implementer 跑、主 session 收尾前複跑)
| step | command | exit | 結果 |
|---|---|---|---|
| vitest | npx vitest run | 0 | 136 files / 2447 passed(baseline 2382 → +65) |
| tsc | npx tsc -b | 0 | OK |
| eslint | npx eslint src | 0 | OK |
| react-doctor | --scope changed | 0 | 1 warning only-export-components GroupGridView.tsx:78(存量,git show master 同在)→ 0 新增 |

## SC 對照
- SC-1' radiogroup:RadioPills.test(sr-only / name 互異 / click / disabled / Enter defaultPrevented / title / leading+trailing / cursor / id token / onInteract)+ 各站點測試 PASS。
- SC-2'/SC-2'' tablist:RightRail.test 6 案 + App.test tablist describe(含 visited 閘門互指與跳過數對帳)+ tablist-keys.test 23 案 PASS;manual activation。
- SC-3 對比:WatchlistSidebar 零漲跌兩處 / GroupGridView 無成交 tone → ink-muted;反向 lock(參考價 / 倉位 chip dim、有成交零漲跌 text-ink)PASS。
- SC-4' 側欄:wl-select button、aria-current、名稱由內容計算、加入群組 / 移除不觸發 onSelect PASS。
- SC-5' 畫面:docs/specs/mod-a11y-radiogroup-tablist-contrast/screenshots/ before(preview 4173 master)vs after(dev 5173)1600/1536 × 四頁,
  PIL 像素差異僅 header 即時指數 / 五檔 / 走勢活資料區 → pill 列 / 分頁列 / 側欄零差異。**游標形狀(cursor-default)與 Tab focus ring 截圖抓不到,待 user 過目。**

## 白名單
W1 onChange / persist 不變(各站測試)/ W2 toggle aria-pressed 斷言全數未動(reviewer 反向確認)/ W3 MarketPane.size.test 未動且綠 /
W4 D-13 條件 render 不變 / W5 拖曳 window listener 幾何命中不受影響 / W6 doctor 0 新增 / W7 像素對照 / W8 title 掛 label / W9 Enter defaultPrevented。
抽 2 個未改功能:GroupGridView toggle(GroupGridView.toggle.test)綠;FuturesLadder 武裝 / 鎖定(FuturesLadder.test)綠。

## Migration:無。self_review_head = cb1579af
