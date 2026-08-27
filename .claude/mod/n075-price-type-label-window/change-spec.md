# mod/n075-price-type-label-window — N075 市價單標籤:程式不封洞,文件改口 + 釘現況 + 保險絲降級

日期:2026-08-28。來源:`docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.4 Standards 1 / Spec 1 / Spec 7、§5 A2;
08-28 user 拍板(memory `do-batch-batch2-decisions-0828`):程式不封洞、文件改口、夜盤遠價市價單實驗 user 親做。
小活分流(單一函式級、無對外 API、無 migration):跳 spec issue / tickets。

## 1. 現況 vs 目標

| 項 | 現況 | 目標 |
|---|---|---|
| `_Agg.date` 語意 | `store.py` / `client.py` docstring 稱「委託建立日 / 委託日」 | 改口「最新事件日」(tc4-market-facts 群益節);推演寫明語意錯位不拉寬誤標窗 |
| 同檔同方向撞同 seq 誤標窗 | docstring 已改口「非零誤標」,但處置寫「待 user 拍板」、無測試點名 | 寫明 08-28 拍板不封洞 + 關窗條件(日界與 seq 重置同口徑才是只記單一候選日);既有 `test_store` s3 案 docstring 註明它就是窗(review Spec F-04:新案與 s3 輸入逐字相同 = 零新覆蓋,不另加) |
| `_trade_ymd` 保險絲 | `next_trading_day` 60 天找不到 → RuntimeError 穿出 `_note_price_type`;晚到路徑在 `_audit` 之前 → late 審計行整行不見;送單路徑 → route 500 而單已在市場上 | catch `RuntimeError` → WARNING + 退回只記本機日(N075 前口徑),審計行與送單結果照常 |
| review §5 A2 / A3 / A5 / A7 / C 類 | 處置欄空 | 回填 08-28 拍板 |
| N099 rounds 條目 | `[ ]` 待確認 | `[x]` 維持鎖(user 不持該兩種倉) |

## 2. Caller map

- `CapitalClient._note_price_type`(`client.py`):三個 caller —— `_on_late_result`(:378,晚到補記)、`submit_stock_order`(:917)、
  `submit_future_order`(:957)。無動態用法(grep `note_price_type` 全 repo 只 client / store / tests / models 註解)。
- `_trade_ymd`:唯一 caller = `_note_price_type`;測試 `TestTradeYmd` 直呼。
- `CapitalStore.note_price_type` / `forget_price_type` / `_price_type_of`:client 與 tests 專用;前端只讀 `price_type` 欄位
  (`CapitalOrdersList.tsx` 等),不參與判定。

## 3. 既有行為白名單(逐 bit 不變)

1. 送單成功且有 seq → 記兩個候選日(本機日 + 所屬交易日)+ 標的 + 方向;拒單 / timeout 不記。
2. 晚到結果(`_on_late_result`)補記標籤 + late 審計行,順序不變(標籤先、審計後)。
3. 改價成功 → `forget_price_type`。
4. 日曆壞檔 / 讀檔錯 → `_calendar()` 降級 WEEKEND_ONLY + WARNING(既有 `test_broken_calendar_degrades_to_weekend_only`)。
5. store 比對規則(候選日集合 ∩、標的 / 方向等值、prune 不相交)逐字不變;同檔同方向撞同 seq **仍誤標**(現況,刻意保留)。
6. 三道下單閘(`safety.py` / 確認窗 / 審計 append-only)零改動。

## 4. 唯一行為改動(🔴)

`_trade_ymd()` 拋 `RuntimeError`(日曆資料錯的保險絲)時:改動前整個 `_note_price_type` 炸出;改動後 WARNING
「價格別標籤只記本機日(seq=…):交易日推算失敗」+ `trade_date=None` → store 只記 `(本機日,)`。
catch 只收 `RuntimeError`(`last_trading_day` / `next_trading_day` 兩把保險絲的唯一 raise 型別,日盤 / 夜盤分支各走一把;`_calendar()` 已把 OSError / ValueError 降級),不吞其他錯。

## 5. Seams / 測試

- `tests/capital/test_client.py::test_late_result_audit_survives_trade_day_fuse`(紅先行:改動前 late 行不見)
- `tests/capital/test_client.py::test_submit_result_survives_trade_day_fuse`(紅先行:改動前 `_drive` 炸 RuntimeError)
- `tests/capital/test_store.py::test_price_type_binding_rejects_same_seq_different_order` s3 案 docstring 註明 = 窗(不另加案)

## 6. 留尾

- 夜盤遠價市價單實驗(user 親做)→ 定案回報日界 + 群益 seq 重置口徑 → 同口徑才是只記單一候選日關窗,不同口徑才需補丁(`docs/next-time.md` 08-28 節)。
- 知情殘留(review Spec F-06 / Standards F-2):try 只收 `RuntimeError` 且只包 `_trade_ymd()`;`store.note_price_type` 若日後拋別的錯,late 審計行仍會不見(spec §4 明示取捨);非日曆來源的 RuntimeError 也會被降級成一行 WARNING。
