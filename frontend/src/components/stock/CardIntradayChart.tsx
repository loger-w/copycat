import { useMemo } from "react";

import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useContainerSize } from "@/hooks/useContainerSize";
import { cardSvgBox } from "@/lib/chart-frame";
import { accumFromGroupSnapshot, type GroupLikeSnapshot } from "@/lib/stock-accum";

/** 群組卡片內的分時圖 = **單檔頁同一份渲染碼**的 card 變體(D4)。
 *
 *  這一層只做三件事:量卡片圖區、把 group-state 的精簡 snapshot 折成 `StockAccum`、
 *  把量到的尺寸換成主 / 副圖的 viewBox。圖形語彙(價線 / VP / 高低標 / hover 十字線)
 *  一律由 `IntradayChartCore` 供給 —— 卡片另寫一份小尺寸幾何的代價是「同一檔股票在
 *  卡片與單檔頁上是兩張不一樣的圖」,而且沒有任何測試比得到兩者。 */

interface Props {
  code: string;
  snap: GroupLikeSnapshot;
  /** `watchlist_quote` 的現價(毫元);末點延伸與現價圈同源(AD-9) */
  liveP: number | null;
  /** 圖牆頂那一份(SC-2)。**卡片不持有 storage 狀態** —— 50 張卡各持一份會同時讀寫
   *  同一個 localStorage key,而 `set` 每次 render 都是新 identity,傳進來還會打穿 memo。 */
  toggles: ChartToggles;
}

export function CardIntradayChart({ code, snap, liveP, toggles }: Props) {
  const [ref, size] = useContainerSize<HTMLDivElement>();
  const box = cardSvgBox(size);
  // **必經 useMemo**(review R4):就地建一個 accum 的話,父層每秒隨報價 re-render 時
  // `accum` 每輪都是新 identity → core 內所有吃 accum 的 useMemo(幾何 / 量副圖 / VP)
  // 全部重算,memo 護欄形同虛設。deps 只列真正的輸入。
  const accum = useMemo(() => accumFromGroupSnapshot(code, snap, liveP), [code, snap, liveP]);
  return (
    // 恆存 wrapper(useContainerSize 契約 1):量測分支與繪圖分支都掛在它底下,
    // 只掛「量到之後」那一支的話冷載入會永遠停在 0×0。
    // 高度由外層指派(契約 2):`flex-1 min-h-0` 吃卡片扣掉標題列的剩餘高,
    // 不是由內容撐出來 —— 由內容決定會形成「量到多高 → 設多高」的回饋迴圈。
    <div ref={ref} className="flex min-h-0 flex-1 flex-col">
      {/* 量到之前不畫(AD-3 / R12):先用 800 寬的預設 viewBox 畫一幀再跳回 1:1,
          畫面上是每次進圖牆都閃一下的縮放跳動。空白一幀不會有人看見。 */}
      {box.usable ? (
        <IntradayChartCore
          accum={accum}
          toggles={toggles}
          variant="card"
          width={box.width}
          mainHeight={box.mainH}
          subHeight={box.subH}
        />
      ) : null}
    </div>
  );
}
