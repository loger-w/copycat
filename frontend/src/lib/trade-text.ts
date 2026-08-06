// 下單相關繁中文字對照(錯誤碼 / 回報狀態 / 買賣別)。
// OrdStatus 值域為整合驗證項(design §8):未知值一律原樣顯示,不猜。

const TRADE_ERROR_TEXT: Record<string, string> = {
  TOUCHANCE_DOWN: "達錢未連線",
  TRADE_NOT_READY: "交易服務未就緒(請在達錢 4 登入交易帳號)",
  LIVE_DISABLED: "正式戶未啟用(DQ4_LIVE)",
  CONFIRM_REQUIRED: "確認已失效,請重新送單",
  PREVIEW_EXPIRED: "預覽已過期,請重新送單",
  INVALID_ORDER: "下單參數不合法",
  // 個股期兩道閘(stkfut-contracts R2-8)。BAD_TICK 只對 limit 單成立(市價單的
  // price 欄不參與送單);PRODUCT_NOT_ALLOWED = 契約單位非股票期貨規格(ETF 期貨、
  // 除權息調整契約)—— 兩者都是「這一單不會被送出去」,原碼直接顯示等於沒說明白。
  BAD_TICK: "價格非合法檔位",
  PRODUCT_NOT_ALLOWED: "此商品下單暫未開放",
  SYMBOL_NOT_ALLOWED: "商品不可下單",
  BROKER_REJECTED: "券商拒單",
  AUDIT_WRITE_FAILED: "審計寫入失敗,單未送出",
  // capital(群益)— ORDER_BLOCKED 的 reason 走 ":" 後綴(parseCapitalError 契約)
  CAPITAL_DISABLED: "群益未啟用",
  CAPITAL_NOT_READY: "群益連線未就緒",
  ORDER_BLOCKED: "安全閘拒絕",
  CAPITAL_DOWN: "群益連線故障",
};

export function tradeErrorText(code: string): string {
  const [head, ...rest] = code.split(":");
  const mapped = TRADE_ERROR_TEXT[head ?? ""];
  if (mapped === undefined) return code;
  return rest.length > 0 ? `${mapped}(${rest.join(":")})` : mapped;
}

const ORDER_STATUS_TEXT: Record<string, string> = {
  "0": "已委託",
  "1": "部分成交",
  "2": "全部成交",
  "4": "已刪單",
  "8": "已拒單",
  F: "成交",
};

export function orderStatusText(raw: string): string {
  return ORDER_STATUS_TEXT[raw] ?? raw;
}

const SIDE_TEXT: Record<string, string> = { "1": "買", "2": "賣" };

export function orderSideText(raw: string): string {
  return SIDE_TEXT[raw] ?? raw;
}

export function shortSymbol(symbol: string): string {
  return symbol.replace(/^TC\.[FO]\.TWF\./, "");
}
