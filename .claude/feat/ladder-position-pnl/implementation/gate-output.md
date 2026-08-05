# gate-output:閃電梯部位列 + 未實現損益 + 含成本打平價

跑於 `frontend/`,分支 `feat/ladder-position-pnl`,HEAD `a2dbb95`(2026-08-05,含 Phase 4 review fix + Phase 6 real-env fix)。

## 三 gate 摘要(全 PASS)

| gate | 指令 | 結果 |
|---|---|---|
| 測試 | `npm test -- --run` | **73 files / 1069 tests passed**,0 failed |
| 型別 | `npx tsc -b` | exit 0(零輸出) |
| Lint | `npx eslint src` | exit 0(零輸出) |

```
 Test Files  73 passed (73)
      Tests  1069 passed (1069)
--- tsc ---
exit=0
--- eslint ---
exit=0
```

## 本輪新增 / 變動的測試檔

| 檔案 | 數字 |
|---|---|
| `src/lib/ladder-position.test.ts`(新) | 28 passed(初版 27 + CALC-2) |
| `src/components/stock/PriceLadder.test.tsx` | 24 → **45 passed**(+21) |
| `src/components/rail/RightRail.test.tsx` | +1(LP-5) |

## 紅→綠對照

| 階段 | commit | 紅證據 → 綠證據 |
|---|---|---|
| lib | `04e3e8c` [red] → `e582349` [green] | `Cannot find module "@/lib/ladder-position"`(1 failed suite / no tests)→ 27 passed |
| 元件 | `ef6cea1` [red] → `cc9ccbb` [green] | 14 failed / 22 passed(缺 `ladder-position-bar` / `ladder-be-mark` / `ladder-avg-mark` / label「手續費折數」)→ 39 passed |
| Phase 4 review fix | `cf54cf1` [red] → `9a316f5` | 7 failed / 65 passed(qty=0 得 `{pnl:-0}`、無 `border-line/20`、找不到「均價」、row title 為 null、`aria-invalid` 恆 null、折數框仍在武裝列)→ 72 passed |

## 既有測試變紅情形

零。兩處既有斷言依明列授權改動:

1. dimmed opacity characterization(PLAN §3「該變」)—— 兩段式:`98d8b1d` 先鎖現況、`ca7e6cb` 移欄後改斷言。
2. 標記 `title` 斷言(design [amendment 2026-08-05] LP-1)—— 由「標記帶 title」改為「row 容器帶 title、標記不帶」,同一則 it 內兩段都明寫。

## Phase 4 review fix 對照

| finding | 落點 | 守門測試 |
|---|---|---|
| CALC-1 | 折數 raw 非法 → `aria-invalid="true"` + `border-loss` | 「非法折數 → aria-invalid + 紅框;改回合法即消失」 |
| CALC-2 | `positionEcon` qty=0 → 全 null | 「qty = 0 → 全 null」 |
| CALC-3 | 均價色點只給標籤不給數字 | 「第二行兩顆色點…」內 `not.toContain("均價 1")` |
| ORD-1 / LP-7 | 折數框移標題列,武裝列回復原樣 | 「折數框在標題列(跟隨置中鈕左側),武裝列零折數框」 |
| LP-1 | title 掛 row 容器、標記不帶;第二行補 ma20 色點 | 「title 掛 row 容器、標記本身不帶」+「同一列同時有打平與均價 → row title 併成一句」 |
| LP-2 | (現況)標記 `pointer-events-none` | 「標記不吃點擊」 |
| LP-3 | (現況)部位條在卡片最底 | 「部位條在卡片最底 —— 價格梯 scroll 區之後」 |
| LP-4 | 反灰列分隔線降階 `border-line/20` | 「反灰列的分隔線降階到 border-line/20,一般列維持 /50」 |
| LP-5 | (現況)RightRail 整合面 | 「閃電 tab + 本檔部位 → 部位條出現且價格列仍在」 |
| LP-6 | (現況)pnl 隨現價重算 | 「現價前進 → pnl 隨之重算」,102→`+3,284`、103→`+5,278` |

## Phase 6 real-env fix

| finding | 落點 | commit |
|---|---|---|
| 折數框 `w-10` 在真 Chrome 截字(number input 右側恆留 spinner 空間,「1.8」只顯示「1.」) | 改 `w-12`(與張數框同寬,該格實證不截字) | `a2dbb95` |

jsdom 沒有 Chrome 的 spinner 保留寬 → 這條在單元測試層測不到,無對應 class 斷言需同步;
gate 數字不變(73 files / 1069 tests passed)。

## 未跑

backend 四項(`pytest` / `ruff` / `pyright` / `copycat validate`)—— 本輪零 `.py` 改動。
真實環境取證(PLAN §5 的 vite dev + claude-in-chrome 假部位截圖)不在本 task 範圍。
