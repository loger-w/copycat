import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useContainerSize } from "@/hooks/useContainerSize";
import { cardSvgBox } from "@/lib/chart-frame";
import type { FillPoint } from "@/lib/fill-marks";
import type { IndexOverlaySeries } from "@/lib/index-overlay-lines";
import type { StockAccum } from "@/lib/stock-accum";

/** 群組卡片內的分時圖 = **單檔頁同一份渲染碼**的 card 變體(D4)。
 *
 *  這一層只做兩件事:量卡片圖區、把量到的尺寸換成主 / 副圖的 viewBox。圖形語彙(價線 /
 *  VP / 高低標 / hover 十字線)一律由 `IntradayChartCore` 供給 —— 卡片另寫一份小尺寸幾何
 *  的代價是「同一檔股票在卡片與單檔頁上是兩張不一樣的圖」,而且沒有任何測試比得到兩者。
 *
 *  T4 #185 起 `accum` 由圖牆層的 `useGroupLiveAccums` 供給(快照播種 + 逐筆 applyTick),
 *  本層不再自己折 snapshot、也不再每秒拿報價延伸末點:identity 由那支 hook 管,只有收到
 *  成交的卡才換 —— 這正是 core 內幾何 useMemo 護欄成立的前提。 */

interface Props {
  code: string;
  /** 該檔的 live accum(圖牆層一份;沒動的卡拿到同一個物件) */
  accum: StockAccum;
  /** 圖牆頂那一份(SC-2)。**卡片不持有 storage 狀態** —— 50 張卡各持一份會同時讀寫
   *  同一個 localStorage key,而 `set` 每次 render 都是新 identity,傳進來還會打穿 memo。 */
  toggles: ChartToggles;
  /** 這一檔今天的成交點(SC-6)。圖牆層一次折完所有 code 再分給每卡 —— 卡片各折一次
   *  的話同一份 orders 會被走 50 遍。零筆時是 `EMPTY_FILLS`(單一 identity),否則
   *  無成交的卡每秒都會因為新陣列而打穿 `GroupCard` 的 memo(W-5)。 */
  fills: readonly FillPoint[];
  /** 加權 / 櫃買即時序列(F1);圖牆層只在指數 toggle 開著時才傳(關著恆 null,memo 不被打穿) */
  indexSeries: IndexOverlaySeries | null;
  /** 同步十字線(F3):圖牆層的共同 hover 分鐘 / 回報口(關著時恆 null / 模組層 noop) */
  syncHoverMin: number | null;
  onHoverMinute: (minute: number | null) => void;
}

export function CardIntradayChart({
  accum,
  toggles,
  fills,
  indexSeries,
  syncHoverMin,
  onHoverMinute,
}: Props) {
  const [ref, size] = useContainerSize<HTMLDivElement>();
  const box = cardSvgBox(size);
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
          fills={fills}
          indexSeries={indexSeries}
          syncHoverMin={syncHoverMin}
          onHoverMinute={onHoverMinute}
        />
      ) : null}
    </div>
  );
}
