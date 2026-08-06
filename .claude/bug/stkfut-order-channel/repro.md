# repro — stkfut-order-channel(quintet review C-1 P0 / C-2 P1)

來源:`.claude/review/2026-08-06-quintet/findings.md`(2026-08-06 五題整體 review)。
branch:`fix/stkfut-order-channel`(基準 f9fff6a0 = origin/master)。

## Bug 1(C-1,P0):個股期送單被路由到 SendOptionOrder

### 最小重現(2026-08-06,worktree,deterministic)

```
$ .venv python -c "…exchange_product_of / _FUTURE_PRODUCTS…"
module path check: …worktree…\copycat\capital\mapping.py   ← 驗的是本分支 code
tc4_symbol = TC.F.TWF.CDF.202609
exchange contract = CDFI6
exchange_product_of = CDF
_FUTURE_PRODUCTS = ['MXF', 'TMF', 'TXF']
is_option = True          ← BUG:個股期被判成選擇權
multiplier_of = 2000      ← 對照:金額閘的乘數查找有為個股期接 stkfut_map,放行無阻
```

觸發鏈(靜態 trace,主 session 逐行覆核):
- 送單:`capital_api.py:207-215`(兩道閘 + 乘數全過)→ `client.submit_future_order`
  → `client.py:678` `is_option = exchange_product_of(contract) not in _FUTURE_PRODUCTS`
  → `com.py:164` `if is_option: SendOptionOrder`。
- 平倉:`client.close_position` fut 分支 → 同一支 `submit_future_order` → 同中。

### 影響範圍

- 個股期**送單 + 平倉**兩條路全部走選擇權通道。最好情況群益/期交所退單
  (功能整條不可用、既有部位無法從 App 平倉);最壞情況選擇權通道解讀
  FUTUREORDER struct 造成非預期委託。真錢面,P0。
- 指數期貨(TXF/MXF/TMF)與 TXO/週選不受影響(測試有鎖)。

### Root cause

`_FUTURE_PRODUCTS`(`client.py:94`)是「什麼是期貨」的封閉白名單,預設方向是
**未知 → 選擇權**。#28 加個股期時只擴充了乘數查找(`multiplier_of` 接
`stkfut_map.lookup_product`),分流白名單沒有同步 —— 系統裡「什麼是期貨」有了
兩份不一致的定義。`tests/capital/test_client.py:287` 註解甚至把「非 {TXF,MXF,TMF}
一律 option」寫成不變量,該前提在 #28 之後已失效。

### 修法(拍板)

分類收斂回 `mapping.py` 單一定義:新增 `is_option_contract(contract)` 純函式 ——
已知選擇權產品({TXO} ∪ 週選家族)→ True;已知指數期貨({TXF,MXF,TMF})→ False;
`lookup_product` 查得到(個股期)→ False;其餘未知產品以結構判別
(選擇權契約碼必含履約價數字,body 純字母 = 期貨形)。`client.py:678` 改用之,
廢止 `_FUTURE_PRODUCTS` 直接比對。

## Bug 2(C-2,P1):correct-price 路徑沒有 BAD_TICK 閘

### 重現(靜態結構,紅測試為執行證據)

- 送單 route `capital_api.py:207` 有 `_stkfut_gates`(BAD_TICK 檔位閘,
  `test_illegal_tick_rejected` 鎖住);改價 route(`:226-232`)直接組
  `CorrectPriceRequest` → `client.correct_price` 只過總開關 + price>0 + 名目金額
  (`client.py:744-766`),全程無檔位驗證。
- 前端可達:個股期合約態 `RightRail.tsx:94` market="fut" →
  `CapitalOrdersList.tsx:168` inline 改價。
- 失效樣態:改成 1180.5(1000 元段 tick=5)期交所退單,畫面只剩「委託失敗」——
  正是 BAD_TICK 閘要消滅的樣態(`test_illegal_tick_rejected` docstring 逐字)。

### Root cause

SC-6 的 BAD_TICK 閘只掛在送單 route,同一 blast radius 的改價 route 漏掛。
改價時 contract 可由 `client.store.orders()` 以 seq_no 反查(`rec.stock_no`,
乘數反查 `_fut_multiplier` 已用同一條路),資訊不缺,單純是覆蓋缺口。

### 修法(拍板)

- 檔位檢查從 `_stkfut_gates` 抽成共用 helper(單一定義,防第二份漂移規則)。
- correct-price route:market="fut" 時以 seq_no 反查 store 得 contract;
  **store 查無 → 放行**(R3 逃生口慣例:斷線 store 空仍要能刪改單);
  查到且為個股期(`lookup_product` 命中)→ limit 檔位驗證,非法 → 400 BAD_TICK。
- Scope 與送單面一致:僅個股期。指數期權改價不驗(現股 tick 表不適用)。

## 實驗記錄

- 2026-08-06 exp-1(C-1):一次一變數 —— 同一條 `exchange_product_of` 對
  TXFI6(→TXF,in whitelist)vs CDFI6(→CDF,not in)對照,唯一差異 = product
  家族 → 確認分流判準是 root cause,而非 to_exchange_symbol / 閘層。
  執行輸出見上;既有測試 `test_client.py:251-260`(TXFI6→False)為對照組。

## Phase 7|重現步驟重走(修復後)

`is_option_contract`:CDFI6 / QFFI6 / TXFI6 → False;TXO20000I6 / TX422000T6 →
True;SXFI6(未知純字母)→ False。原重現(CDF → is_option=True)消滅。
HTTP 層證據(側車 server + curl)見 `verification.md` 與 `evidence/curl-transcript.txt`。

## Phase 8|反向驗證(2026-08-06)

- `git revert --no-commit 09a67a91 b5d0ec6a`(兩個 fix 一起還原)→ 跑
  `tests/capital/test_client.py + tests/server/test_capital_api.py`:
  **7 failed, 126 passed**,失敗恰為本輪 7 條新紅測試,且樣態 = 原始 bug:
  - C-1 ×6:`assert is_option is False` → `True is False`
    (CDF 送單 / QFF 送單 / close CDFI6 / SXFI6 結構判別 / route 標準腿 / route 小型腿)
  - C-2 ×1:`test_illegal_tick_rejected` → `assert 200 == 400`(1180.5 直通)
- `git reset --hard HEAD` 還原修復 + sleep 1(§8 同秒 pycache 陷阱)→ 重跑同兩檔:
  **133 passed**。反向驗證 PASS:測試確實抓得住 bug。
