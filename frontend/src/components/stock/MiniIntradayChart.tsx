import { useId, useMemo } from "react";

import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  R_AXIS_W,
  X_END_MIN,
  X_LABEL_H,
  X_START_MIN,
  Y_AXIS_W,
} from "@/lib/stock-intraday-svg";
import { pts } from "@/lib/svg-points";
import { safeIdToken } from "@/lib/utils";

/** 群組卡片內的迷你分時圖(group-grid SC-3)。
 *
 *  **重用 `buildIntradayGeometry` 而不是另寫一份小尺寸幾何**:y 域(漲跌停 vs 對稱
 *  autofit)、`hasRef` 的紅綠語意、0 = 不可得的歸一,這幾條規則各自漂一份的代價是
 *  「主圖與卡片對同一檔股票畫出不同的圖」,而且沒有任何測試比得到兩者。
 *
 *  代價是那份幾何自帶左右軸帶(`Y_AXIS_W` / `R_AXIS_W`)與底部時間帶(`X_LABEL_H`)
 *  ——卡片只有 15rem 寬,軸帶會吃掉近半。**幾何補償(design R5/R13)**:
 *  傳進去的尺寸把三條帶都加回去,再用 viewBox 把它們裁掉。
 *
 *    width  = MINI_W + Y_AXIS_W + R_AXIS_W  → `plotWidth` 恰為 MINI_W,x ∈ [Y_AXIS_W, Y_AXIS_W+MINI_W]
 *    height = MINI_H + X_LABEL_H            → `plotH` = MINI_H − 2·PAD_Y,y ∈ [PAD_Y, MINI_H−PAD_Y]
 *    viewBox = "Y_AXIS_W 0 MINI_W MINI_H"
 *
 *  `height` 的 `+ X_LABEL_H` 是必要的(R13 修正 v2):不加的話上下留邊變成
 *  「上緣 0、下緣 PAD_Y」的不對稱,漲停那根貼頂的 stroke 會被裁掉半條。 */

export const MINI_W = 220;
export const MINI_H = 76;

interface Props {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
  /** `watchlist_quote` 的現價(毫元);null / ≤0 = 不延伸 */
  liveP: number | null;
}

/** 現價延伸(design R10)。分鐘級 snapshot 每 60s 才更新一次,不延伸的話卡片上的線
 *  最久會停在一分鐘前 —— 而群組檢視的用途就是「現在有沒有一起動」。
 *
 *  三道限制都不是防禦性補丁:
 *  - 分鐘鍵取**本機時鐘**(部署綁台北),窗外(盤前 / 盤後 / 隔天早上還開著頁面)
 *    一律不延伸 —— 幾何的窗是 [09:00, 13:30],延伸到窗外的點會被 `windowedEntries`
 *    濾掉,但延伸到**窗內錯的分鐘**(例如隔日 09:05 用的是昨天的 minutes)會靜默
 *    畫出一條假的尾巴。
 *  - `liveP > 0`:TC4 會送 0 表示「不可得」(鎖漲跌停的市價佇列同理),毫元價恆 > 0。
 *  - 既有 bucket **只覆寫 `c`**:量 / 內外盤 / 高低都是後端聚合的真值,拿現價去改
 *    它們等於偽造成交明細。無 bucket 才新建,且 `h`/`l` 給 `null` = 「這一分鐘的
 *    高低不可知」而不是冒充等於現價。
 *
 *  不就地改傳入的 Map(淺拷後寫):來源是 TQ cache 的物件,污染它會讓下一次
 *  render 拿到被改過的「快取」而看不出來。 */
export function extendMinutes(
  minutes: Map<number, MinuteAgg>,
  liveP: number | null,
  now: Date = new Date(),
): Map<number, MinuteAgg> {
  if (liveP === null || liveP <= 0) return minutes;
  const key = now.getHours() * 60 + now.getMinutes();
  if (key < X_START_MIN || key > X_END_MIN) return minutes;
  const next = new Map(minutes);
  const prev = next.get(key);
  next.set(
    key,
    prev === undefined
      ? { c: liveP, v: 0, i: 0, o: 0, u: 0, h: null, l: null }
      : { ...prev, c: liveP },
  );
  return next;
}

export function MiniIntradayChart({ minutes, meta, liveP }: Props) {
  // clip id 必須全域唯一(SVG id 是 document 範圍)且只含識別字元 —— React 19 的
  // useId 產出 «r0» 形態,而 `url(#…)` 解析失敗在 SVG 規範下是「該元素不繪製」= 全靜默
  const uid = safeIdToken(useId());
  const above = `${uid}-mini-a`;
  const below = `${uid}-mini-b`;
  // 幾何算一次就好(review A6-1):`minutes` 最多 271 格,而群組頁最多 50 張卡片,
  // 父層每秒隨 `quotes` re-render 一次。deps 只列真正的輸入 —— `minutes` / `meta` 來自
  // TQ cache(60s 才換 identity),`liveP` 是每秒可能變的那一個。
  //
  // ⚠ `extendMinutes` 內部讀**本機時鐘**,而時鐘不在 deps 裡:整分鐘一到,只要
  // `liveP` 沒變就不會重算,延伸點會停在上一分鐘的格子裡最多 60 秒。可接受 ——
  // 盤中每秒都有報價的檔 `liveP` 本來就一直在動;真的一分鐘零成交的冷門股,
  // 那條線本來也沒有新資訊可畫。
  const g = useMemo(
    () =>
      buildIntradayGeometry(
        { minutes: extendMinutes(minutes, liveP), meta },
        { width: MINI_W + Y_AXIS_W + R_AXIS_W, height: MINI_H + X_LABEL_H },
      ),
    [minutes, liveP, meta],
  );
  const line = pts(g.priceLine);
  return (
    // `preserveAspectRatio="none"` = 非等比拉伸:卡片寬度隨 grid 欄數變,等比縮放
    // (letterbox)會讓同一列的圖高忽大忽小 —— 這條不變。
    //
    // 變的是尺度:矩陣佈局後卡片高度隨格高走(`grow`,h-20 只剩基準),y 向縮放可達
    // ~3×,原本「尺度差 <5%、線寬失真不可見」的前提不再成立。線寬改由
    // `vectorEffect="non-scaling-stroke"` 釘在螢幕像素,不隨 viewBox 縮放變粗。
    // y 向斜率跟著視覺放大則是「圖吃滿卡片」的本意,不補償。
    <svg
      viewBox={`${Y_AXIS_W} 0 ${MINI_W} ${MINI_H}`}
      preserveAspectRatio="none"
      className="block h-20 w-full grow"
    >
      {g.hasRef ? (
        <defs>
          {/* 平盤上下切兩半:面積與價線共用,紅漲綠跌與主圖同一套語彙 */}
          <clipPath id={above}>
            <rect x={Y_AXIS_W} y={0} width={MINI_W} height={Math.max(0, g.refY)} />
          </clipPath>
          <clipPath id={below}>
            <rect
              x={Y_AXIS_W}
              y={g.refY}
              width={MINI_W}
              height={Math.max(0, MINI_H - g.refY)}
            />
          </clipPath>
        </defs>
      ) : null}
      {g.hasRef ? (
        <line
          data-testid="mini-ref"
          x1={Y_AXIS_W}
          x2={Y_AXIS_W + MINI_W}
          y1={g.refY}
          y2={g.refY}
          className="stroke-line"
          strokeDasharray="2 3"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      {g.hasRef && g.areaPolygon !== "" ? (
        <>
          <polygon
            data-testid="mini-area"
            points={g.areaPolygon}
            className="fill-bull"
            fillOpacity="0.15"
            clipPath={`url(#${above})`}
          />
          <polygon
            data-testid="mini-area"
            points={g.areaPolygon}
            className="fill-bear"
            fillOpacity="0.15"
            clipPath={`url(#${below})`}
          />
        </>
      ) : null}
      {g.hasRef ? (
        <>
          <polyline
            data-testid="mini-price"
            points={line}
            fill="none"
            className="stroke-bull"
            strokeWidth={1.4}
            vectorEffect="non-scaling-stroke"
            clipPath={`url(#${above})`}
          />
          <polyline
            data-testid="mini-price"
            points={line}
            fill="none"
            className="stroke-bear"
            strokeWidth={1.4}
            vectorEffect="non-scaling-stroke"
            clipPath={`url(#${below})`}
          />
        </>
      ) : (
        // 沒有昨收就沒有「平盤」可言,紅綠會把「開盤後漲跌」誤指為「相對昨收漲跌」
        <polyline
          data-testid="mini-price"
          points={line}
          fill="none"
          className="stroke-accent"
          strokeWidth={1.4}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}
