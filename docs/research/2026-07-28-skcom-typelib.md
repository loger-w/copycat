# SKCOM typelib probe 結論(capital-order Task 0,2026-07-28)

來源:`C:\Users\USER\CapitalAPI\x64\SKCOM.dll`(2.13.58 元件包)反射 dump +
`spikes/capital_login_probe.py` test 環境實測。原始 dump 重跑
`python spikes/capital_typelib_probe.py --dll-dir <CAPITAL_DLL_DIR>` 再生。

## 定案(回填 PLAN Task 3/5/6)

1. **期權下單共用 `FUTUREORDER` struct**(無 OPTIONORDER):
   `SendFutureOrder(bstrLogInID, bAsyncOrder, FUTUREORDER) -> (bstrMessage, retCode)`、
   `SendOptionOrder(...)` 同簽名。mapping 實際使用欄位:
   `bstrFullAccount / bstrStockNo(期交所碼)/ bstrPrice / sTradeType(TIF:0=ROD,1=IOC,2=FOK)/
   sBuySell(0買/1賣)/ sDayTrade(0/1)/ sNewClose(0新/1平/2自動)/ nQty(口)`;
   其餘欄位(bstrStockNo2/bstrTrigger*/bstrMovingPoint/nOrderPriceType/…)為組合單/
   停損單/移動停損用,一律不設(comtypes struct 未賦值欄位為零值)。
2. **刪改減同證券家族,無獨立期貨版方法**:
   `CancelOrderBySeqNo(loginID, async, bstrAccount, seqNo)`、
   `CorrectPriceBySeqNo(..., bstrPrice, nTradeType)`、
   `DecreaseOrderBySeqNo(..., nDecreaseQty)` — 期權單傳期貨帳號即可。
3. **帳號清單**:`GetUserAccount()` → `OnAccount(bstrLogInID, bstrAccountData)` 逐筆事件
   (bstrAccountData 逗號分隔,含市場別 TS=證券/TF=期貨;實際欄序 prod 登入後驗)。
4. **期貨部位**:`GetOpenInterestGW(loginID, account, nFormat)` →
   `OnOpenInterest(bstrData)` 資料列 + `OnOpenInterestGWStatus(nQueryStatus, bstrErrorMsg)`。
5. **nQty 語意**:證券 = 張 — treading-king 正式環境 2026-06-10 首單核對 + 至今實戰
   使用實證;期貨 = 口(FUTUREORDER)。

## test 沙盒不可用(關鍵環境事實)

`SetAuthority(2)` 登入回 **1097 SK_ERROR_TELNET_LOGINSERVER_FAIL**:

- 2026-06-09(treading-king M1)已隔離證明:prod 全通、官方 SKCOMTester 測試環境同樣
  1097 → **群益端沙盒未對此帳號開通**,非程式/網路/憑證問題
  (`C:\side-project\treading-king\docs\notes\2026-06-09-capital-m1-login-handoff.md`)。
- 2026-07-28 本日重測(`spikes/capital_login_probe.py`,序列 SetAuthority(2)→Login):
  仍 1097,未開通狀態未變。

**影響與決策**:

- 開發期 `CAPITAL_ENV=test` 下 client 登入失敗 → status=error 降級,server 照起
  (routes 回 503 CAPITAL_NOT_READY),前端照常開發。
- Phase 6 送單真環境驗證 → `phase_6_blocked_reason = "群益 test 沙盒帳號未開通(1097)"`,
  降級 = FakeCom 全鏈測試 + **user prod 安全首單程序**(treading-king
  `docs/notes/2026-06-10-capital-prod-golive-handoff.md` 同款:遠價 1 單位限價單 →
  群益 APP 核對 → 刪單;與 brainstorm 拍板驗收一致)。
- **市價 literal(bstrPrice="M"/"P")無法先驗** → design amendment:期貨平倉改
  「**限價貼漲跌停 + IOC**」(與一般限價送單同鏈路,遠價單驗收即覆蓋);
  `price_type=market` 映射 `bstrPrice="M"` + 強制 IOC 保留但標示未實測,UI 預設限價。
- OnAccount 事件時序(pump+timeout 設計)只能 prod 驗;get_user_accounts 的 3s timeout
  設計不變。

## 關鍵 COMMETHOD 摘錄

```
SendStockOrder / SendFutureOrder / SendOptionOrder:
  (bstrLogInID: BSTR, bAsyncOrder: VARIANT_BOOL, pAsyncOrder: STOCKORDER|FUTUREORDER)
  -> (bstrMessage: BSTR, retCode: int)
CancelOrderBySeqNo(bstrLogInID, bAsyncOrder, bstrAccount, bstrSeqNo) -> (msg, code)
CorrectPriceBySeqNo(bstrLogInID, bAsyncOrder, bstrAccount, bstrSeqNo, bstrPrice, nTradeType)
DecreaseOrderBySeqNo(bstrLogInID, bAsyncOrder, bstrAccount, bstrSeqNo, nDecreaseQty)
GetUserAccount() -> retCode;OnAccount(bstrLogInID, bstrAccountData)
GetOpenInterestGW(bstrLogInID, bstrAccount, nFormat) -> retCode;
  OnOpenInterest(bstrData);OnOpenInterestGWStatus(nQueryStatus, bstrErrorMsg)
GetRealBalanceReport(bstrLogInID, bstrAccount);OnRealBalanceReport(bstrData)
GetProfitLossGWReport(bstrLogInID, TSPROFITLOSSGWQUERY);OnProfitLossGWReport(bstrData)
```

STOCKORDER 14 欄 / FUTUREORDER 36 欄完整清單:重跑 typelib probe 再生。
