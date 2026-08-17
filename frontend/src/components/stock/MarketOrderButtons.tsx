/** 梯頂「市價買 / 市價賣」兩顆鈕(三座梯共用的表現層;SC-1)。
 *
 *  **外框、不填色**是安全需求不是品味(R-A / R-H):武裝鈕在武裝態是實心 `bg-loss`,
 *  兩顆恆常可見的送單鈕若也填色,梯頂就出現三顆同型色塊,「已經武裝了嗎」在餘光裡
 *  分不出來 —— 而這兩顆是三梯上第一個「遠價 + 無確認框」的路徑(KL-3)。
 *
 *  三態(disabled / title)全由 `lib/flash-send.ts::marketButtonState` 算,本元件零判斷:
 *  「什麼時候該鎖」是安全規則,不該分散在三座梯的 JSX 裡。
 */
import type { MarketBtnState } from "@/lib/flash-send";

interface Props {
  onMarket: (side: "buy" | "sell") => void;
  state: MarketBtnState;
}

export function MarketOrderButtons({ onMarket, state }: Props) {
  return (
    <div
      data-testid="ladder-market-buttons"
      className="flex items-stretch gap-1 border-b border-line px-1 py-1"
    >
      <button
        type="button"
        disabled={state.buyDisabled}
        title={state.buyTitle}
        onClick={() => onMarket("buy")}
        className="flex-1 rounded border border-bull py-1 text-xs font-bold text-bull hover:bg-bull/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        市價買
      </button>
      <button
        type="button"
        disabled={state.sellDisabled}
        title={state.sellTitle}
        onClick={() => onMarket("sell")}
        className="flex-1 rounded border border-bear py-1 text-xs font-bold text-bear hover:bg-bear/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        市價賣
      </button>
    </div>
  );
}
