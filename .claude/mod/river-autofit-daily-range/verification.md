# verification:江波圖 autofit y 域改為「含當日高低」

## pre-impl 紅測試證據(Phase 4 step 2b,實作前跑)

指令:`npm test -- --run`(frontend/,2026-08-05)

```
 Test Files  2 failed | 70 passed (72)
      Tests  6 failed | 1007 passed (1013)
```

新測試 11 支(lib 10 + 元件 1),既有 1002 支全綠(1013 − 11 = 1002)。
紅綠分佈與 change-spec 測試影響總表**逐支相符**:

### 🔴 紅先行(6 支,spec 預期必紅)

| 測試 | 失敗訊息 |
|---|---|
| lib 1 `長上影極端分鐘 → 域含 high,highMark 可畫(SC-1/SC-3)` | `AssertionError: expected 2224200 to be greater than or equal to 2600000` |
| lib 2 `low 低於收盤群 → 域含 low,lowMark 可畫(SC-2)` | `AssertionError: expected 2175800 to be less than or equal to 1900000` |
| lib 5a `不變式:域必含當日極值 — (a) high 在收盤群之上且舊域外` | `AssertionError: expected 2600000 to be less than or equal to 2224200` |
| lib 5b `不變式:域必含當日極值 — (b) low 在收盤群之下且舊域外` | `AssertionError: expected 2175800 to be less than or equal to 1900000` |
| lib 6 `疊線裁切門檻隨域放寬(舊域外、新域內的 ma5 由不給變成給)` | `AssertionError: expected [] to deeply equal [ 'ma5' ]` |
| 元件 1 `無漲跌停 + 當日高遠離收盤群 → 域跟著擴,標記仍畫得出來` | `AssertionError: expected null to be truthy` |

紅的數字即現況域:SPIKE fixture 舊域 `[2_175_800, 2_224_200]`(ref = 首筆收盤 2_200_000,
半幅 = ref×1%×1.1 = 24_200);元件 fixture 舊域 `[2_243_000, 2_397_000]`(half = 70_000×1.1)。

### 守門綠(5 支,spec 預期改動前後皆綠)

- lib 3 `low = 0 → 視為不可得,域同未傳且下緣仍 > 0`(0 值歸一慣例)
- lib 4 `含極值後域仍以 ref 為中心(SC-4)`
- lib 5c `(c) high/low 皆在收盤群內`
- lib 5d `(d) high === ref`
- lib 5e `(e) low = 0(不可得)`

## post-impl gate(Phase 4 step 2d,實作後跑;frontend/)

| 指令 | 結果 | exit code |
|---|---|---|
| `npm test -- --run` | `Test Files 72 passed (72)` / `Tests 1013 passed (1013)` | 0 |
| `npx tsc -b` | 無輸出 | 0 |
| `npx eslint src` | 無輸出 | 0 |

1013 = 既有 1002 + 新增 11,既有測試零變紅(白名單 1-7 皆守住:漲跌停分支域、
autofit 未傳 high/low 的域、markFor 域外 guard、high===low 只留高標、反查落空不畫、
yTicks 3 點 fallback 與 kind、0 值歸一)。

---

## 自評修復(Phase 5 的 7 條 accepted findings)

同分支一個 🔴 commit。內容:F5 行為修正(code)+ F5/F1/F2/F3 守門測試 4 支 + F4/WL-1 註解修正。

### 修復前紅綠實測(新測試 4 支,在**未做 F5 code 改動的 HEAD** 上跑)

指令:`npx vitest run src/lib/stock-intraday-svg.test.ts` → `Tests 1 failed | 60 passed (61)`

| 新測試 | finding | HEAD 上結果 | 訊息 |
|---|---|---|---|
| `ref = 0(無 meta ref 且收盤全 0)→ 域不受 high/low 影響,標記皆不畫` | F5 | 🔴 紅 | `AssertionError: expected [ -2860000, 2860000 ] to deeply equal [ -1, 1 ]` |
| `有漲跌停 → 域恰為 [lower, upper],完全不受 high/low 影響` | F1 | 綠(守門) | — |
| `low = 0 且有分鐘的 l 為 0(退化域)→ 仍不畫假標記` | F2 | 綠(守門) | — |
| `實例回歸:域上緣差 0.5 元裝不下當日高(2330 2026-07-30)` | F3 | 綠(回歸鎖) | — |

**F2 一項與 coordinator 訊息中的臨場推測(「4 應紅」)不符,但與 F2 finding 本文一致** ——
finding 寫的是「raw 版會畫出假標記;**norm 版提前擋掉**」,而 norm 已在前一個 🔴 commit
(`b46eb88`)裡,所以此測試在 HEAD 上本就該綠:它的作用是**釘住 norm 不被改回 raw**
(唯一測得出 norm/raw 差別的形狀 = 退化域 [−1, 1] 含 0,正常域下 0 會被域外 guard
自然擋掉,兩版無差別)。與 finding 描述無矛盾,照做未停。

F5 紅的數字即該 finding 的失效樣態本身:`ref = 0` 時域被 high 撐成 `[−1.1×high, 1.1×high]`
(−2_860_000 ~ 2_860_000),而正確的退化域是 `[−1, 1]`。

### 修復後 gate(frontend/)

| 指令 | 結果 | exit code |
|---|---|---|
| `npm test -- --run` | `Test Files 72 passed (72)` / `Tests 1017 passed (1017)` | 0 |
| `npx tsc -b` | 無輸出 | 0 |
| `npx eslint src` | 無輸出 | 0 |

1017 = 1013 + 新增 4,既有測試(含本輪先前新增的 11 支)零變紅。

## Phase 6 全套 gate(main session,2026-08-05 11:4x)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | 1691 passed | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed | 0 |
| `.venv\Scripts\python -m pyright` | 0 errors | 0 |
| `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| frontend `npm test -- --run` | 1017 passed | 0 |
| frontend `npx tsc -b` / `npx eslint src` | 無輸出 | 0 / 0 |

## Phase 7/8 真實環境驗證(2026-08-05 盤中)

- prod server(8721,sha 8ef1346)在跑 → 依 CLAUDE.md §8 盤中紀律,只起 vite dev(port 5174,proxy 8721,零新增 TC4 訂閱)。
- 白名單畫面層:個股頁 3481 群創江波圖走漲跌停分支如常 — y 域恰為 [43.05, 52.5]、當日高 50.5 標記在對應分鐘、CDP 疊線/量副圖/五檔/閃電梯無異狀。截圖:docs/specs/river-autofit-daily-range/screenshots/2026-08-05-intraday-limit-branch-whitelist.png。
- 新行為(autofit + 極值超出收盤群)的畫面情境 = 盤後無 meta,盤中不可達;以 SC-3 臨界形狀回歸測試(2330 2026-07-30 實例數字)+ 元件測試(day-high circle 由不畫變畫)代替,user 盤後過目即可實看。
- 白名單 7 條:測試層 1017 全綠零變紅 + 白名單 lens 逐條對照(邊界值窮舉無差異)+ 畫面層漲跌停分支如常 → 全保留。
- Migration:無(純前端計算,無持久化);Input 介面不變,caller 零改動。
