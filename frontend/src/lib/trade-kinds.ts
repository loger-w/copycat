/** 交易別值域與標籤(自 `components/stock/PriceLadder.tsx` 搬出,**行為零變更**)。
 *
 *  閃電梯之外,自選列 / 單檔 header / 群組卡也要把 `Position.kind` 印成人看得懂的
 *  標籤 —— 值域與標籤表只能有一份。`PriceLadder` 仍 re-export `TRADE_KINDS` 與
 *  `TradeKind`,既有 import 路徑(`RightRail` 等)不變。
 */

export const TRADE_KINDS = [
  ["cash", "現股"],
  ["margin", "融資"],
  ["short", "融券"],
  ["daytrade_sell", "無券"],
] as const;
export type TradeKind = (typeof TRADE_KINDS)[number][0];

/** kind → 顯示標籤,查表未命中就顯示原字串:群益 `Position.kind` 的值域比本檔的
 *  交易別寬(D13),不認得的部位寧可標籤怪也不要靜默消失。 */
export function kindLabel(kind: string): string {
  return TRADE_KINDS.find(([v]) => v === kind)?.[1] ?? kind;
}
