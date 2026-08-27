import { ALLDAY_GAP, alldayIndexOfStamp } from "@/lib/allday";
import type { Bar } from "@/lib/candle";
import type { MinuteAgg, StockAccum, VpCell } from "@/lib/stock-accum";
import { snapDown, tickOf } from "@/lib/stock-tick";

/** 期貨 1K bars → `StockAccum`,讓期貨 tab 的分時圖直接吃個股同一份
 *  `IntradayChartCore`(mode="futures";change-spec §3.2)。
 *
 *  **key = 近全軸索引不是分鐘數**:呼叫端把 `ALLDAY_WINDOW` 當 `xWindow` 注進 core,
 *  幾何對 key 的唯一要求就是「落在窗內的整數、可排序」。用分鐘數的話夜盤 00:00–05:00
 *  會排到日盤之前,而畫面上只是「線的順序怪怪的」,沒有任何錯誤訊號。
 *
 *  這裡填的每一個值都有來源,唯二的佔位是 `last.t` / `last.cum_vol`(core 只讀 `last.p`,
 *  同 `index-accum-adapter`)與 live 分鐘的 `v = 0`(見下)。
 *
 *  純函式、零 IO;caller(`FuturesChart`)以 `useMemo` 依 slice / live 純量折。 */

export interface FuturesLive {
  /** live 點的軸索引(牆上時鐘 +1 分,已過空檔 / 錨定日 / 時鐘落後三道 gate) */
  index: number;
  /** WS 現價(毫元) */
  p: number;
}

interface Input {
  /** 已 `sliceCurrentAllday` 的當前錨定日 bars(升冪) */
  bars: readonly Bar[];
  /** 已過四道 gate 的 live 點;null = 不合(不追加、不覆寫) */
  live: FuturesLive | null;
  ref: number | null;
  name: string;
  code: string;
}

export function futuresBarsToAccum(input: Input): StockAccum {
  const rows = new Map<number, MinuteAgg>();
  const vp = new Map<number, VpCell>();

  for (const b of input.bars) {
    // 一天之外(13:46–15:00)/ 空檔(05:01–08:45)與日 K 時戳:軸上沒有那一格 → 整根略過。
    // **minutes 與 vp 同一道閘**:畫不出來的量不該進價位別直方圖,否則 VP 的總張與
    // 說明列的「外 + 內 + 未分類」對不上,而兩個數字都是純數字,沒有測試會紅。
    const index = alldayIndexOfStamp(b.t);
    if (index === null) continue;
    // `c <= 0`:TC4 偶發送 "0",後端原樣轉 0 不轉 null;毫元價恆 > 0 → 0 = 不可得。
    // 不在這裡收口的話它會把 low / vwap / y 域一起拉走(同 index adapter 的 0 收口)。
    if (b.c <= 0) continue;
    const uv = b.uv ?? 0;
    const dv = b.dv ?? 0;
    rows.set(index, {
      c: b.c,
      v: b.v,
      o: uv,
      i: dv,
      // 未分類 = 總量扣掉已判定的兩側。`uv/dv` 缺欄(DK 路徑)→ u = v,說明列的判定率
      // 印 0% 是**誠實呈現**不是壞掉;夾制 0 是防畸形資料在畫面上長出負數量。
      u: Math.max(0, b.v - uv - dv),
      // h / l 與 c 同一把「> 0 才是價」的尺(code review A-2):TC4 只壞一欄時 l=0 會
      // 進 `accum.low` → 幾何的 `norm` 把它擋成 null,日低標記靜默消失、對稱域也少摺
      // 真實低點。頂替值取該分鐘收盤(= 沒有更好的資訊時最保守的極值)。
      h: b.h > 0 ? b.h : b.c,
      l: b.l > 0 ? b.l : b.c,
    });
    // 價位別成交量:1K 沒有逐筆價量,分鐘收盤 × 該分鐘總量是唯一可得的折法。
    // key = **5 點桶的桶心** `snapDown(c) + tickOf(c)/2` —— `buildVpBars` 的帶界取
    // 與相鄰檔位的中點,桶心當 key 時帶恰為 `[k, k+5)`,與桶區間一致(不偏 2.5 點)。
    const key = snapDown(b.c) + tickOf(b.c) / 2;
    const cell = vp.get(key);
    if (cell === undefined) vp.set(key, { t: b.v, o: uv, i: dv });
    else vp.set(key, { t: cell.t + b.v, o: cell.o + uv, i: cell.i + dv });
  }

  // live 合入:同索引 → 覆寫收盤並擴張該分鐘高低(量不動,量只來自 1K);
  // 新索引 → 補一格 **v = 0** 的佔位格。0 不是「這分鐘零成交」而是「這分鐘的 1K 還沒回」
  // —— bars 是 60s 輪詢、live 走牆上時鐘,最新那一分鐘常態上就是佔位。core 的 futures 態
  // 依 `v === 0` 把 readout 的量 / 外 / 內印成「-」,副圖該格高 0。
  if (input.live !== null) {
    const { index, p } = input.live;
    const cur = rows.get(index);
    rows.set(
      index,
      cur === undefined
        ? { c: p, v: 0, o: 0, i: 0, u: 0, h: p, l: p }
        : {
            ...cur,
            c: p,
            h: cur.h == null ? p : Math.max(cur.h, p),
            l: cur.l == null ? p : Math.min(cur.l, p),
          },
    );
  }

  // 空檔水平橋(mod/futures-day-1500 Q9(a)):05:00 → 08:45 無交易,x 軸保留這 225 格,
  // 線要畫成**水平**(user 平時 APP 的畫法)。core 的單條 polyline 只會直線連相鄰 key,
  // 所以在空檔末格(08:45,`ALLDAY_GAP.end`)補一格取夜盤末格收盤的橋:05:00 → 08:45 平走、
  // 08:46 再跳到日盤價。**只在兩側都有格時補**(日盤第一筆 bar 或 live 到了才畫;日盤未開時
  // 線停在 05:00、右側留白 —— 拍板不跟牆鐘延伸)。橋不是成交:v=0、h/l=null(等值反查
  // 不會命中它),下面的 Σ / high-low 一律跳過;vp 更早就沒收它。
  let nightLast: number | null = null;
  let hasDay = false;
  for (const k of rows.keys()) {
    if (k < ALLDAY_GAP.start) nightLast = nightLast === null || k > nightLast ? k : nightLast;
    else if (k > ALLDAY_GAP.end) hasDay = true;
  }
  if (nightLast !== null && hasDay) {
    rows.set(ALLDAY_GAP.end, { c: rows.get(nightLast)!.c, v: 0, o: 0, i: 0, u: 0, h: null, l: null });
  }

  // 依軸索引升冪:core 的 `windowedEntries` 會自己排序,但 `last` 取的是**序列末格**,
  // 兩處對「末格是誰」的答案必須是同一個(live 補在中間、bars 亂序時才不會岔開)。
  const sorted = [...rows.entries()].sort((a, b) => a[0] - b[0]);
  const minutes = new Map<number, MinuteAgg>(sorted);

  let amountMilli = 0;
  let volume = 0;
  let high: number | null = null;
  let low: number | null = null;
  for (const [k, m] of sorted) {
    if (k === ALLDAY_GAP.end) continue; // 橋:不是成交,不進 Σ 與高低
    amountMilli += m.c * m.v;
    volume += m.v;
    // 高低取 per-minute 的 `h` / `l`(tick 級極值)—— core 的極值標記走等值反查
    // (`m.h === accum.high`),拿收盤極值當 accum.high 會讓反查落空 = 標記靜默缺席。
    const h = m.h ?? m.c;
    const l = m.l ?? m.c;
    high = high === null || h > high ? h : high;
    low = low === null || l < low ? l : low;
  }

  const lastRow = sorted[sorted.length - 1];
  return {
    code: input.code,
    seq: 0,
    // 現價圈的語意是「線走到哪」,不是「現在有沒有推播」—— live gate 擋下時圈落在
    // 末根 bar 上是正確語意(同個股收盤後行為)。`t` / `cum_vol` 無來源 → 空值佔位。
    last: input.live !== null ? { p: input.live.p, t: "", cum_vol: 0 }
      : lastRow === undefined ? null
      : { p: lastRow[1].c, t: "", cum_vol: 0 },
    // Σc·v / Σv = **真量加權**,與 core `vwapLine` 末點同源同值(均價線的標籤文字唯一
    // 來源就是這個欄位)。Σv = 0(只有 live 佔位格)→ null,不編一個 0/0 出來。
    vwap: volume > 0 ? Math.round(amountMilli / volume) : null,
    minutes,
    ticks: [],
    vp,
    book: null,
    // `upper / lower` 一律 null:期指的 ±10% 漲跌停域會把日內線壓成一條平線 →
    // 走以昨收置中的對稱 autofit(同 index adapter),也不亮漲跌停燈。
    meta: { name: input.name, ref: input.ref, upper: null, lower: null, y_vol: null },
    noData: false,
    tapeOmitted: false,
    trial: false,
    high,
    low,
    amountMilli,
    volume,
  };
}
