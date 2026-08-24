# 現股市價單全數被 1068 拒單 — repro / root cause(2026-08-24)

## 症狀(user 實錄)
2026-08-24 09:02–09:10,閃電梯市價單 7 筆(5608 市價賣 ×6、6770 市價買 ×1)全被群益拒(review C3 更正筆數):
code 1068 `SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO`。
audit:`data/audit/capital-20260824.jsonl`(req 帶 price 19.0/19.05/19.1/71.0 + price_type=market)。
其後 user 手動改限價的單全部 SK_SUCCESS —— 只有市價路徑壞。

## Root cause
`copycat/capital/mapping.py::to_stockorder_fields` 無視 `price_type`,一律
`bstrPrice = f"{req.price:.2f}"`;SKCOM 現股市價單(`nSpecialTradeType=1`)要求委託價為 0。
期貨端 `to_futureorder_fields` 對市價已有特判(`bstrPrice="M"` + ROD 升 IOC),現股端漏了。
`req.price` 本身不能拿掉 —— safety 金額閘 `_check_qty_amount` 靠它估名目金額(models.py 註明
「market=閘用估價(前端帶)」),只有 SKCOM 映射欄要歸零。

## 紅 loop
`tests/capital/test_mapping.py::test_stock_market_order_price_field_must_be_zero`
修前:`1 failed, 85 passed`(assert "590.00" != "0")。

## 修(最小,一行)
`bstrPrice = "0" if req.price_type == "market" else f"{req.price:.2f}"` + 對照組限價測試。

## 反向驗證
`git stash -- copycat/capital/mapping.py` → 紅測試紅回(1 failed, 85 passed)→ `stash pop` → 全綠。

## Blast radius
- `to_stockorder_fields` 唯一 caller = `capital/client.py:760`(send_stock_order),grep 全 repo 無其他。
- safety 閘走 `req.price`(不經此欄),行為不變;限價路徑對照組測試鎖住。
- 改價(modify):市價單**有**改價場景(鎖停日市價 ROD 留存簿中可改)—— 程式面由
  `forget_price_type` 正確處理且有測試鎖(review C3 更正理由,結論不變:不受本修影響)。
- **現股「一鍵平倉」同走 market 路徑,同壞同修**(review C2):`closeBodyOf` 不帶 price_type
  → route 預設 market → 同一 mapping。audit 全史(0818–0824)market 現股單 7 筆全失敗、
  close 0 筆 —— 平倉市價路徑**從未成功過**,本修是它首次成立。
- 前端「市價」標籤鍵 = `price_type`,不受影響。
- 期貨市價 `"M"` 路徑未動(prod 首發仍待 user,next-time N076)。

## 真環境驗收(待 prod 重啟)
兩筆(review C2 擴充):
1. 低價股 1 張市價買/賣 → audit `price_type=market` + SK_SUCCESS;群益 APP 核對成交型別;
2. 一鍵平倉(市價路徑)一筆 → 同上核對。
**字面 "0" 為推定**(review C1):若首單仍 1068 → 改試 "0.00" 再驗(不會錯價成交,見 mapping 註解)。
