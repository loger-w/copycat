# stock-ui-round3 — 真實環境驗證(Phase 7)

## 狀態總表

| SC | 驗證方式 | 狀態 |
|---|---|---|
| SC-1 江波圖右緣無 % | user 對照過目 + 截圖 | ⏳ 待 TC4 |
| SC-2 CDP 印價位 + 五色 | user 對照過目 + 截圖 | ⏳ 待 TC4 |
| SC-3 價位皆合法檔位 | 截圖對照 tick 表 | ⏳ 待 TC4 |
| SC-4 無漲跌停虛線 | user 對照過目 | ⏳ 待 TC4 |
| SC-5 兩側 border | user 對照過目 | ⏳ 待 TC4 |
| SC-6 無捲軸 + 貼底 | devtools `main.scrollHeight === clientHeight` @ 1440×900 / 1920×1080 / 1366×768 | ⏳ 待 TC4 |
| SC-6b 90 筆明細不溢出 | devtools 同上 + tick-tape 捲到底 | ⏳ 待 TC4 |
| SC-7 時間黃 | ✅ **build 已證** `.fill-time{fill:var(--color-time)}` + `--color-time:#f0b429` 都在 production CSS;畫面確認待 TC4 |
| SC-8 量刻度 | user 對照過目 | ⏳ 待 TC4 |
| SC-9 分 K 耗時 | curl `time_total` | ⚠ **改前已量,改後待 TC4** |
| SC-10 K 線刻度合法 | 截圖 + `snapNearest` 冪等 sweep | ✅ **算式已證**(見下),畫面確認待 TC4 |
| SC-11 左緣 11 刻度不變 | 截圖 | ⏳ 待 TC4 |

**阻塞原因**:2026-07-30 00:1x 起達錢 4(Touchance)已關閉 —— 無 50774 listener、
無 Touchance process,`:8721` server 也已停止。所有需要真實行情的驗收項都要等 user
重新開啟達錢 4 + `python -m copycat.server`。

---

## 已完成的非阻塞證據

### 1. Tailwind utility 真的生成(SC-2 / SC-7 的前置)

`npm run build` 後對 `dist/assets/index-*.css` 檢查 —— class 名寫錯或 token 沒註冊時
畫面會靜默無色,測試只斷言 class 字串抓不到:

| class | 結果 |
|---|---|
| `stroke-bull` / `stroke-bull\/55` | ✓ |
| `stroke-profit` | ✓ |
| `stroke-bear\/55` / `stroke-bear` | ✓ |
| `fill-bull\/70` / `fill-bear\/70` / `fill-profit` | ✓ |
| `.fill-time{fill:var(--color-time)}` + `--color-time:#f0b429` | ✓ |

### 2. `snapNearest` 級距邊界 sweep(SC-3 / SC-10 的正確性根據)

程式碼註解假設「up 候選可能跨進更粗級距,但它本身仍是合法檔位」。獨立 sweep 18 個
邊界值驗證該假設成立 —— 跨越值恆為級距地板(10000 / 50000 / 100000 / 500000 /
1000000 毫元),而那些本身就是粗 tick 的倍數:

```
     9999 ->     10000  tick(p)=  10 tick(s)=  50  legal=OK
    49990 ->     50000  tick(p)=  50 tick(s)= 100  legal=OK
    99990 ->    100000  tick(p)= 100 tick(s)= 500  legal=OK
   499900 ->    500000  tick(p)= 500 tick(s)=1000  legal=OK
   999900 ->   1000000  tick(p)=1000 tick(s)=5000  legal=OK
```
(全 18 case `isLegal(s) && snapNearest(s) === s` 皆真)

### 3. 自動化 gate 全綠

| gate | 結果 |
|---|---|
| `pytest -q` | 1200 passed |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors, 0 warnings |
| `npm test` (frontend) | 53 files / 514 tests passed |
| `npx tsc -b` | 0 |
| `npx eslint src` | 0 |
| `npm run build` | ✓ 793ms |
| `check_feat_tags.py` | PASS(flow=mod,19 commits) |

---

## SC-9:改前基準(已量,TC4 在線時)

2026-07-29 23:5x,`:8721` server + TC4 在線,`curl -o /dev/null -w "%{time_total}"`:

| 情境 | 改前 | SC-9 目標 |
|---|---|---|
| 暖 cache(2330 / 1101 二訪) | 0.004–0.026s | — |
| 冷載入有資料(1101 / 2603 / 3037) | **2.12 / 2.13 / 2.12s** | (c) ≤ 1.6s |
| 無資料(9999)首次 `tf=1&days=30` | **60.1s** | (a) ≤ 25s |
| 無資料(9999)15s 內二訪 | **60.1s**(完全沒快取) | (b) ≤ 0.1s |
| 無資料 `tf=D` | 未量(原 DK 10s + 1K fallback 30s 路徑) | (d) ≤ 25s |

三檔冷載入耗時幾乎完全相同(2.12–2.13s)是關鍵證據:主導成本是**固定等待**
(首輪 poll 落空後睡滿 `poll_wait` 1.0s),不是資料量。

## SC-9:改後量測步驟(待 user 執行前置)

前置:開啟達錢 4,然後 repo root:

```
.venv\Scripts\python -m copycat.server
```

另一個 shell:

```
# (a) 無資料首次 —— 期望 ≤25s(改前 60.1s)
curl -s -m 120 -o /dev/null -w "a: %{time_total}s\n" "http://127.0.0.1:8721/api/stock/bars/9999?tf=1&days=30"
# (b) 15s 內二訪 —— 期望 ≤0.1s(改前 60.1s)
curl -s -m 120 -o /dev/null -w "b: %{time_total}s\n" "http://127.0.0.1:8721/api/stock/bars/9999?tf=1&days=30"
# (c) 冷載入有資料 —— 期望 ≤1.6s(改前 2.13s);換沒被暖過的股號
for c in 1102 2882 1216; do curl -s -m 120 -o /dev/null -w "c $c: %{time_total}s\n" "http://127.0.0.1:8721/api/stock/bars/$c?tf=1&days=30"; done
# (d) 無資料 tf=D —— 期望 ≤25s
curl -s -m 120 -o /dev/null -w "d: %{time_total}s\n" "http://127.0.0.1:8721/api/stock/bars/9998?tf=D"
```

註:(b) 必須在 (a) 之後 **15 秒內**發出,否則負向快取已過期(那本身也是 W-15 的
「可恢復」驗證 —— 過 15s 後應該又變慢,而不是永久回空)。

## Phase 2 白名單:code 層對照已完成

Phase 5 的白名單 lens 對 W-1 ~ W-18 **逐條**檢查,結論 **18/18 held、零 finding**
(`code-review-round-1.json` 的 `whitelist_check`)。其中三條值得記錄:

- **W-5 memo 邊界**:逐一追蹤新增的 `w` / `h` props 來源 —— 全為純量(模組常數 /
  `prop ?? 常數` / `svgBox` 算出的數字),無新建 object / array / inline 函式跨越 memo 邊界。
- **W-12 切模式高度不跳**:手算 `CHART_FRAME` chrome = 32+2+26+20 = 80 與兩元件實際 DOM
  逐項對應無漏項;`svgBox` 的 `renderPx` 不依賴 `viewBoxWidth`(測試明確驗 800 與 1400
  得同值),`subH` 用減法保證相加恰等於總高。1200×600 下兩模式總高差 ≈0.6px。
- **W-17**:新的退避輪詢迴圈沒有新增 try/except,`_req` 的 `ConnectionError` 仍原樣往上冒。

畫面 / 行為層的逐條檢查一併等 TC4(Phase 7)。

## Phase 5 自評結果

| round | 內容 |
|---|---|
| 1 | 2 lens(白名單 / 正確性+測試缺口)→ 1 P0 + 1 P1 + 2 P2,全數 accepted 並修畢 |
| 2 | 限縮對抗驗證(opus)→ 兩個修復皆判定 **closed**(含 1.2M 點暴力掃描 + 175,943,319 組域掃描);新增 1 個 P2(`_today` 存空 entry 後同日內不 evict)已修畢 |

**P0 值得記錄**:K 線窄域保底刻度沒 snap —— 域窄於一個 tick 時 5 個等分候選全被域外
過濾,保底走 `(lo+hi)/2` 而那個值不是合法檔位(實算 1001.55 元)。**change-spec 的
R-7 也寫了同一個錯誤**,已標 amendment。round 2 誠實補充:該分支實務上不可達
(TC4 成交價恆為合法檔位 → i=0 候選必然通過過濾),屬防禦分支的正確性瑕疵。
