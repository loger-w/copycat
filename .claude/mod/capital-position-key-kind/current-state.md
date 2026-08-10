# current-state:部位 store 鍵位改造 (stock_no, kind)(2026-08-05)

Baseline:master b437128 全 gate 綠(本 session:pytest 1678 / ruff / pyright 0 /
validate 42/42);capital 子集 `pytest tests/capital tests/server/test_capital_api.py -q`
= **317 passed**。分支 mod/capital-position-key-kind。

## 現況(單鍵設計 + 兩個補償層)

- `store.py::CapitalStore._positions: dict[str, Position]`(:74),鍵 = stock_no:
  - `set_positions`(:219-230):全量替換;同 (stock_no) 沿用舊均價/損益基底的條件是
    `prev.kind == p.kind`(單鍵下的 kind 防呆)。
  - `apply_profit_rows`(:232-246):`get(r.stock_no)` 回填(dataclasses.replace 發布新物件)。
  - `position_for(stock_no)`(:252-254):平倉查找。
- `balance.py` 兩個補償層(docstring 自承「寧少不錯」「store 以 stock_no 為鍵」):
  - `dedupe_positions`(:70-88):sec 同檔多種庫存(集保+融資並存)→ **留張數大者**,
    被捨棄種類平倉鍵不到。debug log(資+集保並存是穩定狀態,每 60s 都會走到)。
  - `merge_fut_positions`(:92-112):fut 同契約多列 → 淨額合併(B 正 S 負相加),
    合併時 warning;淨額 0 不佔列;avg_price 取首列。
- `client.py` 套用點:
  - `_on_balance_complete`(:346-355):`self._pending_sec = dedupe_positions(positions)`。
  - `_on_profit_complete`(:357-377):`by_no = {p.stock_no: p for p in pending}` 回填
    (kind 不符 warning 略過)— **單鍵 dict,pending 若含同檔兩種類會丟一筆**(現況因
    dedupe 先做掉所以不會發生)。
  - `_on_oi_complete`(:398-399):`merge_fut_positions(rows)`。
  - `close_position`(:807-841):sec/fut 皆 `store.position_for(req.key)`(:809/:824),
    req.key = 股號/契約碼。
  - `_close_inflight` 防重送(:800)與 `_close_dup_reason`(:782-785,活躍委託同向查重)
    都以 `req.key`(stock_no)為鍵。
- `models.py::Position`(:129-138):有 `kind: str = "cash"`(cash/margin/short;
  fut 列由 `parse_open_interest_line` 建構,不帶 kind → 恆 "cash")。
  `PositionCloseRequest`(:85-91):market / key / price / qty / price_type / source —
  **無 kind**。
- `close.py::build_close_order`(:32-55):`(pos.kind, pos.qty > 0)` 查 `_CLOSE_MAP`
  決定 side + trade_kind(融資部位 → 融資賣);`build_future_close_order`(:58-86)
  不看 kind。
- REST:`GET /api/capital/positions`(capital_api.py:135-138)= `asdict` 列表(rows 已含
  kind 欄);`POST /api/capital/position/close`(:209-220)`PositionCloseBody`(:94-100)
  無 kind。
- 前端:
  - `types.ts::CapitalPosition`(:92-102)已有 `kind: string`;`CapitalCloseBody`
    (useCapital.ts)無 kind。
  - `CapitalPositionsList.tsx`:React key = `p.stock_no`(:68)、`closingKey` 存 stock_no
    (:22,:29 以 `find(p => p.stock_no === closingKey)` 找列)、close mutate body 帶
    `key: closing.stock_no`(:40)。**UI 不顯示 kind** — 同檔兩列時使用者無法分辨。
  - 消費端:RightRail(sec/fut 各一份列表)、FuturesPage、futures-ladder.ts(結構子集,
    只用 stock_no/qty)。

## Caller map(grep 完整)

- `dedupe_positions`:唯一 caller client.py:348;tests/capital/test_balance.py。
- `merge_fut_positions`:唯一 caller client.py:399;tests/capital/test_balance.py。
- `position_for`:client.py:809/:824;tests(test_store.py/test_client.py/test_capital_api.py)。
- `set_positions` / `apply_profit_rows` / `positions()`:client.py(_finalize/_stale_fut)、
  capital_api.py:138、測試多處(test_store/test_client/test_capital_api:224,438)。
- 動態用法:grep `position_for|set_positions|apply_profit_rows` 無字串拼接 / reflection。
- wire 消費:前端 useCapitalPositions → CapitalPositionsList / RightRail / FuturesPage /
  futures-ladder(後三者只讀 stock_no/qty/market,不受同檔多列影響 — 待 spec 確認
  futures-ladder 對 fut 是否可能同契約多列:fut 淨額合併保留則不會)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| store 鍵 | stock_no 單鍵 | (stock_no, kind) 複合鍵;同檔資+集保並存各佔一列 |
| sec dedupe | 留張數大者(補償層) | **移除** — 全部種類入 store |
| fut 淨額合併 | merge_fut_positions | **保留**(淨額 = 可平倉曝險;同契約同 kind 在複合鍵下仍會互蓋,合併仍必要)— spec 拍板 |
| profit 回填 | by_no 單鍵 dict + kind 不符略過 | 複合鍵對映(同檔兩種類各自回填) |
| 平倉請求 | key = stock_no | + kind 欄(backward compat 策略 spec 拍板) |
| close inflight/dup guard | 以 stock_no 為鍵 | inflight 鍵含 kind;dup guard 語意 spec 拍板 |
| REST positions | rows 含 kind,同檔至多一列 | 形狀不變,同檔可多列(additive 語意變化) |
| 前端列表 | key/closing/close body 以 stock_no | 複合鍵 + **UI 顯示種類標籤**(否則同檔兩列不可分辨) |
| migration | — | 無持久化;wire body 加 optional 欄位 |

## 既有測試盤點(爆點)

- tests/capital/test_balance.py:dedupe_positions 的測試(移除補償層 → 該紅/該刪,spec 標)。
- tests/capital/test_store.py::test_set_positions_carries_profit_same_kind_only(:298-312):
  單鍵下「換 kind 不沿用」的行為 — 複合鍵下語意變為「不同 kind 是不同列」,測試該改寫。
- tests/capital/test_client.py 多處 set_positions + close_position(:748-)。
- tests/server/test_capital_api.py:224,438。
- 前端 CapitalPositionsList.test.tsx(close body 斷言 :142)、RightRail.test.tsx、
  FuturesPage.test.tsx、useCapital.test.tsx。
