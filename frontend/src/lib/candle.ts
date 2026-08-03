/** K 線純函式(毫元整數運算;無 React 依賴,元件只負責掛 DOM)。
 *
 * 時間標記語意 = **終點標記**,沿用 TC4 1K 慣例(`stock_source.fetch_day_minutes`:
 * 當日第一根為 09:01)。因此 5 分桶界為 (09:00, 09:05]、(09:05, 09:10]…,
 * 一根 09:01 的 1 分 bar 屬於標記 09:05 的 5 分桶(change-spec amendment P2-14)。 */

import { snapNearest } from "@/lib/stock-tick";

export interface Bar {
  /** 日 K:`YYYY-MM-DD`;分 K:`YYYY-MM-DD HH:MM`(台北) */
  t: string;
  o: number; // 毫元
  h: number;
  l: number;
  c: number;
  v: number;
}

const X_ORIGIN_MIN = 9 * 60; // 09:00 = 桶界原點

function splitStamp(t: string): { date: string; minute: number | null } {
  const sp = t.indexOf(" ");
  if (sp < 0) return { date: t, minute: null };
  const date = t.slice(0, sp);
  const hhmm = t.slice(sp + 1);
  const h = Number(hhmm.slice(0, 2));
  const m = Number(hhmm.slice(3, 5));
  if (!Number.isFinite(h) || !Number.isFinite(m)) return { date, minute: null };
  return { date, minute: h * 60 + m };
}

function stampOf(date: string, minute: number): string {
  const h = Math.floor(minute / 60);
  const m = minute % 60;
  return `${date} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** 1 分 bar → n 分 bar。桶以終點標記對齊 09:00 原點;跨日不合併。 */
export function aggregateBars(bars: readonly Bar[], n: number): Bar[] {
  if (n <= 1) return [...bars];
  const out: Bar[] = [];
  let curKey: string | null = null;
  let cur: Bar | null = null;
  for (const b of bars) {
    const { date, minute } = splitStamp(b.t);
    // 無分鐘部分(日 K)→ 不聚合,原樣輸出
    if (minute === null) {
      if (cur !== null) {
        out.push(cur);
        cur = null;
        curKey = null;
      }
      out.push({ ...b });
      continue;
    }
    const bucketEnd = X_ORIGIN_MIN + Math.ceil((minute - X_ORIGIN_MIN) / n) * n;
    const key = `${date} ${bucketEnd}`;
    if (key !== curKey) {
      if (cur !== null) out.push(cur);
      cur = { t: stampOf(date, bucketEnd), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v };
      curKey = key;
    } else if (cur !== null) {
      cur.h = Math.max(cur.h, b.h);
      cur.l = Math.min(cur.l, b.l);
      cur.c = b.c;
      cur.v += b.v;
    }
  }
  if (cur !== null) out.push(cur);
  return out;
}

/** 收盤價簡單移動平均(毫元整數除法);前 n-1 根為 null。 */
export function movingAverage(bars: readonly Bar[], n: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i += 1) {
    sum += bars[i]!.c;
    if (i >= n) sum -= bars[i - n]!.c;
    out.push(i >= n - 1 ? Math.floor(sum / n) : null);
  }
  return out;
}

export interface Candle {
  x: number;
  w: number;
  cx: number;
  wickTop: number;
  wickBottom: number;
  bodyTop: number;
  bodyH: number;
  dir: "up" | "down" | "flat";
}

export interface VolBar {
  x: number;
  w: number;
  y: number;
  h: number;
  dir: "up" | "down" | "flat";
}

export interface CandleGeometry {
  candles: Candle[];
  volBars: VolBar[];
  yTicks: { y: number; priceMilli: number }[];
  /** 毫元 → y 像素(反向) */
  toY: (priceMilli: number) => number;
  /** y 像素 → 毫元(`toY` 的逆函數);回傳前夾制進 [lo, hi]。
   *  夾制是必要的:滑鼠移到底部量區(佔 VOL_RATIO)時原式會反演出低於 lo 甚至負的價格。 */
  priceAtY: (y: number) => number;
  /** x 像素 → bar index(hover 用);超界回 null */
  indexOf: (x: number) => number | null;
  /** 價格區底邊(= `height − X_LABEL_H` 再扣掉量區)。
   *
   *  極值標記的文字翻面要以**價格區**底為界,不是整張圖底 —— 拿整張圖底當界的話,
   *  視窗最低點的文字永遠不會翻面、直接落進成交量柱上(常態路徑,BB 關閉時
   *  `toY(windowLow)` 恰在 `priceBottom − PAD_Y`)。
   *  由本函數回傳而不是讓元件端重算 `VOL_RATIO`:兩處各寫一份必漂移(同 W-4)。 */
  priceBottom: number;
}

export interface Size {
  width: number;
  height: number;
}

/** 底部時間標籤帶。**export 給元件端共用** —— 元件的 `plotBottom` 與本檔的幾何必須用
 *  同一個值,各留一份數字就是「幾何算出來的底」與「畫上去的底」靜默錯開。 */
export const X_LABEL_H = 14;
const PAD_Y = 6;
const MIN_BODY_H = 1; // 開收同價仍要看得見
const VOL_RATIO = 0.22; // 量區佔價圖高度比例
const Y_TICKS = 5;

/** bars(升冪)→ 蠟燭幾何。空輸入回空幾何(不崩)。
 *
 * `extraSeries`(選用)= 額外要納入 y 域的序列(布林上下軌等)。不傳 = 行為與未加參數前
 * 完全相同。**呼叫端必須先把序列 slice 成與 `bars` 同一視窗**,否則 y 域會被視窗外的
 * 極值撐開、圖被壓扁且不會報錯(change-spec R4/R20)。 */
export function buildCandleGeometry(
  bars: readonly Bar[],
  size: Size,
  extraSeries?: readonly (readonly (number | null)[])[],
): CandleGeometry {
  const bottom = size.height - X_LABEL_H;
  const volH = bottom * VOL_RATIO;
  const priceBottom = bottom - volH;

  if (bars.length === 0) {
    return {
      candles: [],
      volBars: [],
      yTicks: [],
      toY: () => priceBottom,
      priceAtY: () => 0,
      indexOf: () => null,
      priceBottom,
    };
  }

  let hi = -Infinity;
  let lo = Infinity;
  let maxVol = 1;
  for (const b of bars) {
    // 值域一併吃 o/c:DK 的 Open 欄位名/值域未實測(change-spec §7 Known Risk),
    // 若回 "0.00" 而 h/l 正常,只取 h/l 會讓實體畫到圖框外(review P2-8)
    if (b.h > hi) hi = b.h;
    if (b.o > hi) hi = b.o;
    if (b.c > hi) hi = b.c;
    if (b.l < lo) lo = b.l;
    if (b.o < lo) lo = b.o;
    if (b.c < lo) lo = b.c;
    if (b.v > maxVol) maxVol = b.v;
  }
  for (const series of extraSeries ?? []) {
    for (const v of series) {
      if (v === null) continue;
      if (v > hi) hi = v;
      if (v < lo) lo = v;
    }
  }
  const span = hi - lo;
  const usable = Math.max(1, priceBottom - PAD_Y * 2);
  const toY = (priceMilli: number): number =>
    span <= 0 ? PAD_Y + usable / 2 : PAD_Y + ((hi - priceMilli) / span) * usable;
  // toY 的逆函數。span<=0(全平盤)時 toY 是常數函數、無逆可言 → 回 hi。
  const priceAtY = (y: number): number => {
    if (span <= 0) return hi;
    const raw = hi - ((y - PAD_Y) / usable) * span;
    return Math.min(hi, Math.max(lo, Math.round(raw)));
  };

  const slot = size.width / bars.length;
  // 夾在 slot 內:bars 多到 slot < 1.43 時,max(1, …) 會讓 w > slot 而互相重疊(review P1-1)
  const w = Math.min(Math.max(1, slot * 0.7), slot);

  const candles: Candle[] = [];
  const volBars: VolBar[] = [];
  bars.forEach((b, i) => {
    const x = i * slot + (slot - w) / 2;
    const dir = b.c > b.o ? "up" : b.c < b.o ? "down" : "flat";
    const yOpen = toY(b.o);
    const yClose = toY(b.c);
    const bodyTop = Math.min(yOpen, yClose);
    const bodyH = Math.max(MIN_BODY_H, Math.abs(yClose - yOpen));
    candles.push({
      x,
      w,
      cx: x + w / 2,
      wickTop: Math.min(toY(b.h), bodyTop),
      wickBottom: Math.max(toY(b.l), bodyTop + bodyH),
      bodyTop,
      bodyH,
      dir,
    });
    const h = (b.v / maxVol) * volH;
    volBars.push({ x, w, y: bottom - h, h, dir });
  });

  // span=0(全平盤)只給一條刻度 — 否則 5 條同價位重疊(且會撞 React key)
  const yTicks: { y: number; priceMilli: number }[] = [];
  if (span <= 0) {
    yTicks.push({ y: toY(hi), priceMilli: snapNearest(hi) });
  } else {
    // 等分後 snap 到合法檔位:等分值是任意整數,直接顯示會吐出 2547.32 這種下不了
    // 單的價位(round3 項 10)。snap 後可能溢出 [lo, hi] —— lo/hi 本身不必然合法
    // (extraSeries 的 MA/布林是 Math.floor 的任意整數),端點被 snap 出界是常態。
    const seen = new Set<number>();
    for (let i = 0; i < Y_TICKS; i += 1) {
      const raw = Math.round(lo + (span * i) / (Y_TICKS - 1));
      const priceMilli = snapNearest(raw);
      if (priceMilli < lo || priceMilli > hi) continue;
      if (seen.has(priceMilli)) continue; // tick 粗於等分間距時相鄰刻度會 snap 同價
      seen.add(priceMilli);
      yTicks.push({ y: toY(priceMilli), priceMilli });
    }
    // 保底:域寬 < 一個 tick 且區間內無合法檔位時上面會全部跳過,y 格線與價位標
    // 會整組靜默消失。寧可顯示一根也不要空白 —— 但那一根**也必須是合法檔位**
    // (self-review B1:直接用 (lo+hi)/2 會吐出 1001.55 這種下不了單的價位)。
    //
    // 此時唯一的合法檔位必然落在域外(域本身就窄於一個 tick),所以 y 要夾回繪圖區,
    // 否則刻度線與文字會畫到下方量區裡。這是刻意的取捨:在次-tick 寬的域裡,能誠實
    // 講的只有「這一帶都在某個合法檔位附近」。
    if (yTicks.length === 0) {
      const p = snapNearest(Math.round((lo + hi) / 2));
      yTicks.push({ y: Math.min(Math.max(toY(p), PAD_Y), PAD_Y + usable), priceMilli: p });
    }
  }

  const indexOf = (x: number): number | null => {
    if (x < 0 || x > size.width) return null;
    const i = Math.min(bars.length - 1, Math.floor(x / slot));
    return i >= 0 && i < bars.length ? i : null;
  };

  return { candles, volBars, yTicks, toY, priceAtY, indexOf, priceBottom };
}
