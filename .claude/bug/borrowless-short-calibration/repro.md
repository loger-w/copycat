# /bug 無券空單校準 — repro(diagnosing-bugs Phase 1–3)

分支 `fix/borrowless-short-calibration`(worktree `../copycat-wt-borrowless-short`,自 master 09cc3e63)。
來源:handoff `%TEMP%\copycat-handoff-2026-08-29-work-queue.md` §1a;next-time 08-28 節第 2 條(L151 / L394 併)。

## 實錄(2026-08-28 prod,`logs/server-20260828-0814.log`)

- :2417 09:23:38 `Capital reply seq=2313212869643 stock=8358 status=成交 qty=1000`(audit :13–14
  `sell 512 trade_kind=daytrade_sell`)→ :2418 store「成交種類 '無券' 不在樂觀套用表,等回查鏈」。
- :2425 09:23:39 balance「負股數 … 平倉暫鎖,整列 `8358,T,…,-1000,…,-1000,…`」→ 現股 T 列負股數,**不是融券 L 列**。
- :2427 損益段 4 列收齊、**沒有**「種類不符略過」→ 8358 損益列標籤「現股」與 kind=cash 配對成功(avg_source=broker)。
- :3650–3660 09:52:07 現股買 1 張 @523(audit :35–36)樂觀套用 → 部位歸零。

## Phase 1 loop(紅)

```
C:/side-project/copycat/.venv/Scripts/python -m pytest -q -p no:cacheprovider tests/capital/test_store.py -k borrowless
→ 2 failed, 1 passed in 0.19s
  FAILED test_borrowless_short_counts_today_qty_after_broker_snapshot   (today_qty 0 ≠ 1)
  FAILED test_borrowless_short_position_is_closable_with_cash_buy      (ValueError 部位種類 cash 與方向不符,無法平倉)
  PASSED test_borrowless_short_buyback_fill_nets_to_zero_without_phantom_rows(現況 cash 鍵下回補能沖掉;改鍵後的守門)

cd frontend && npx vitest run src/lib/ladder-position.test.ts
→ 1 failed | 39 passed (1.16s)
  positionEcon 無券空單(kind === 'daytrade_sell'):breakEvenMilli 510201.8 ≠ 510969.6(差 767.8 毫元 ≈ 0.77 元 ≈ 1 檔 —— 與 user 08-28 目視偏差同量級)
```

治具 = `tests/capital/balance_rows.py::RAW_T_BORROWLESS_SHORT`(實錄列去敏)+ `_evt(bs="S08R2")`(reply idx6 S08 = 無券)。
每個元素都 load-bearing:拿掉成交回報 → today_qty 本來就 0;拿掉負股數列 → 無部位可查。

## Phase 3 假說(排序)

H1(確定,handoff 已指認):`store._FILL_KIND` 沒「無券」→ `_today_net_lots_locked` 跳過該成交 → `today_qty=0`
  → 前端 `positionEcon` 空單那段用 0.3% 非 0.15%。預測:補對映後 loop 第 1 條轉綠。
H2(確定):`balance.parse_balance_line` 負現股列 kind=cash,`_CLOSE_MAP` 無 `(cash, False)` → 鎖。
  預測:歸 `daytrade_sell`(user 拍板方向;`("daytrade_sell", False)` 鍵已備)後 loop 第 2 條轉綠。
H3(H2 的連帶,本 session 新發現):位置鍵改成 `(8358, "daytrade_sell")` 後
  (a) 回補是現股買(idx6 B00 → cash)→ 樂觀套用會**另開** `(8358, "cash")` +1 列而不是沖掉空單列 → 約 2 s 幽靈雙列
      (快照落地才蓋掉);loop 第 3 條會轉紅。
  (b) 損益列標籤「現股」→ `_PNL_KIND` cash → `client._on_profit_complete` 以 `(stock_no, kind)` 精確配對 → 配不到
      → 「profit row 種類不符略過」→ 空單 avg / pnl 全 null —— **比 08-28 現況退步**(那天配對成功、avg_source=broker)。
H4(前端):`ladder-position.ts::positionEcon` `todayLots = kind === "cash" ? …` → `daytrade_sell` 永遠 0 → 即使後端補了 today_qty 也不減半。
  預測:改成 cash | daytrade_sell 後 vitest 轉綠。
H5(排除):`_with_today_qty_locked` 空方符號 —— 讀 code `-net` 已對空方取淨賣出;既有測試
  `test_today_qty_nets_same_day_sells…` 覆蓋,非本 bug。
