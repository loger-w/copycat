// 下單相關繁中文字對照(錯誤碼 / 回報狀態 / 買賣別)。
// OrdStatus 值域為整合驗證項(design §8):未知值一律原樣顯示,不猜。

const TRADE_ERROR_TEXT: Record<string, string> = {
  TOUCHANCE_DOWN: "達錢未連線",
  TRADE_NOT_READY: "交易服務未就緒(請在達錢 4 登入交易帳號)",
  LIVE_DISABLED: "正式戶未啟用(DQ4_LIVE)",
  CONFIRM_REQUIRED: "確認已失效,請重新送單",
  PREVIEW_EXPIRED: "預覽已過期,請重新送單",
  INVALID_ORDER: "下單參數不合法",
  SYMBOL_NOT_ALLOWED: "商品不可下單",
  BROKER_REJECTED: "券商拒單",
  AUDIT_WRITE_FAILED: "審計寫入失敗,單未送出",
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
