# refactor/tc4-shared-helper

動機(Phase 1):docs/next-time.md:60(2026-07-18)— TC4_APPID/TC4_SKEY 與 QryIndex 分頁迴圈
在 data/backfill_tc4.py 與 live/tc4.py 重複;dq4-order-phase1 又新增第三份分頁迴圈
(tc4_trade._restore)。為什麼是現在:user 點名執行;重複已實證隨每個新 TC4 消費者擴散,
下一批(個股行情/下單)會抄第四份。

## 重複地圖(Phase 2 盤點)

| 實體 | 位置 | 差異 |
|---|---|---|
| TC4_APPID/TC4_SKEY | backfill_tc4.py:17 / tc4.py:37(tc4_trade 從 tc4 import) | 完全相同 |
| QryIndex 分頁 | backfill_tc4._fetch_1k(1K)| start="0",nxt 無 str cast |
| QryIndex 分頁 | tc4._fetch_symbol_ticks(TICKS)| start="0",nxt 無 str cast |
| QryIndex 分頁 | tc4_trade._restore(回報)| start="",nxt 有 str() cast,rows key="Orders" |

測試覆蓋:
- _fetch_1k:分頁到空頁 ✓ 停滯防呆 ✓ parse/零量 ✓(tests/data/test_backfill_tc4.py)— 已足
- _restore:停滯 ✓ 空首頁 ✓ 空 QryIndex ✓(tests/live/test_tc4_trade.py)— 已足
- _fetch_symbol_ticks:僅分頁攤平 ✓;**停滯防呆 ✗、空 QryIndex 終止 ✗ → 步驟 1 補**

## 步驟(每步單獨綠)

1. 🟢 characterization:tests/live/test_tc4.py 補 _fetch_symbol_ticks 停滯防呆 + 空 QryIndex
   終止兩測(拍現狀,應直接綠)。獨立 commit。
2. 🔵 新增 `copycat/tc4common.py`(stdlib-only,data/ 與 live/ 皆可 import 而不拉進 zmq):
   TC4_APPID/TC4_SKEY 單一定義 + `iter_qry_pages(fetch, *, start)` 分頁 helper;
   backfill_tc4 改用(常數 import + _fetch_1k 迴圈改走 helper)。commit。
3. 🔵 live/tc4.py 常數改 import + re-export(__all__ 不動,tc4_trade 既有 import 路徑不破);
   _fetch_symbol_ticks 改走 helper;tc4_trade 常數改直接 import tc4common、_restore 改走 helper。commit。

[auto-default: helper 的 nxt 統一為 `str(page[-1].get("QryIndex", "") or "")`(None/缺值 → 終止)
 | reason: 三份原碼在「QryIndex 為 None」上行為不一致(backfill/tc4 終止、trade 的 str() 會變
 "None" 字串繼續抓)— 真實 TC4 資料 QryIndex 恆為 str 不會踩到,統一取最保守語意(終止、防
 無限迴圈),與既有停滯防呆測試相容]

[auto-default: helper 落點 = 新 top-level `copycat/tc4common.py` | reason: data/ 不可 import
 live/tc4(模組頂層 import zmq,backfill 需在無 [live] extras 環境可跑);live/ import data/
 語意顛倒;與 market.py/strategy_config.py 同層慣例]

[auto-default: 不為 helper 寫獨立單元測試 | reason: 三個 call site 的既有 + 步驟 1 測試已
 覆蓋空頁/停滯/多頁/空 QryIndex 全路徑,獨立測試屬重複]

## Blast radius(Phase 5 預查)

TC4_APPID/TC4_SKEY 引用點僅 copycat/ 內 3 檔(grep 全 repo 含 tests/spikes 無其他);
無動態用法。收尾跑全 suite + ruff + pyright + copycat validate。
