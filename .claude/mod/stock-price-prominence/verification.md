# Verification — mod/stock-price-prominence(2026-08-04)

## 自動化 gate(main session 親跑,最終 HEAD)

| Gate | 指令 | 結果 | Exit |
|---|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | 1497 passed, 1 warning (69.4s) | 0 |
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| 前端測試 | `npm test`(frontend/) | 66 files / **919 passed (919)**(baseline 914 → +5 新測試) | 0 |
| 前端型別 | `npx tsc -b` | 零輸出 | 0 |
| 前端 lint | `npx eslint src` | 零輸出 | 0 |

後端 4 項在 review 修復前跑(後端零改動,diff 不含 .py);前端 3 項在最終 HEAD 親跑。

## 真實環境(盤中,vite dev 5173 → 跑著的 server 8721,零新增 TC4 訂閱)

- SC-1/SC-2:`docs/specs/stock-price-prominence/screenshots/stock-page-1600.png` —
  雷科 6207 現價 105(text-3xl semibold 紅字)明顯大於股名;+8.81% 小一級、非粗體
  (font-normal 修復後重拍)。
- SC-4:`stock-page-1280.png` — 1280px 下 header 仍單列(總量/昨量右對齊同列),
  `<main>` 無垂直捲軸(圖表 flex-1 吸收 header 增高)。1600px 同。
- 白名單 6/8:兩張截圖同時佐證 items-baseline 對齊、其他 header 元素未動。

## 已記錄限制

- SC-3 反白態(漲/跌停 + 大字)無真環境截圖:盤中自選(3481/6207)無鎖停股。
  替代證據:jsdom 三態並存斷言(漲停 text-3xl+bg-bull+text-white+px-1.5+rounded、
  跌停對稱、未觸價 text-bull)+ review finder 以 tailwind-merge 3.6.0 實跑
  cn() 輸出驗證三態 class 集合完整保留(code-review-round-1.json whitelist_check)。
