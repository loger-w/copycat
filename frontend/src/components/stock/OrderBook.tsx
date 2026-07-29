import { DepthBar } from "@/components/quote/DepthBar";

/** 個股五檔 —— 水平版式與量 bar 全在 `DepthBar`(與期貨共用,SC-4/D-5)。
 *  本檔只剩個股專屬接線:把點價轉成 `stock-price-click` CustomEvent。 */

interface Props {
  code: string;
  book: { bids: [number, number][]; asks: [number, number][] } | null;
  last: { p: number; t: string; cum_vol: number } | null;
  ref_: number | null; // 參考價(漲跌色基準)
  upper?: number | null; // 漲停價(鎖停 badge 判定;SC-5)
  lower?: number | null;
}

function emitPriceClick(priceMilli: number, side: "bid" | "ask", code: string): void {
  // PriceLadder 監聽 → 該價置中(不送單;design §11:五檔誤觸面大,送單集中在梯上)
  window.dispatchEvent(
    new CustomEvent("stock-price-click", { detail: { priceMilli, side, code } }),
  );
}

export function OrderBook({ code, book, last, ref_, upper = null, lower = null }: Props) {
  return (
    <DepthBar
      bids={book?.bids ?? []}
      asks={book?.asks ?? []}
      last={last?.p ?? null}
      ref_={ref_}
      upper={upper}
      lower={lower}
      onPriceClick={(priceMilli, side) => emitPriceClick(priceMilli, side, code)}
    />
  );
}
