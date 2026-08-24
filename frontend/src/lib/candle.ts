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
  /** 外盤量(TC4 1K `UpVolume`);DK 路徑不帶欄 —— 缺欄與 0 是兩件事(SC-8) */
  uv?: number;
  /** 內盤量(TC4 1K `DownVolume`) */
  dv?: number;
}

const X_ORIGIN_MIN = 9 * 60; // 09:00 = 桶界原點
const DAY_MIN = 24 * 60;

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

/** `YYYY-MM-DD` ± n 天。夜盤桶溢過午夜時要真的進位到次日日曆日(跨月/跨年才會對)。 */
function shiftDate(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

/** 1 分 bar → n 分 bar。桶以終點標記對齊 09:00 原點;跨日不合併。
 *
 * **跨午夜正規化(SC-2)**:夜盤 23:5x 的桶終點會算到 ≥1440,直接 `stampOf` 會產出
 * "24:00" 這個不存在的時戳,而且與次日 00:00 的桶各成一根 —— 兩者其實是同一根。
 * 因此 bucketEnd ≥ 1440 時把日期進位、分鐘減 1440,桶 key 也用正規化後的值 →
 * 23:56–23:59 與次日 00:00 自然合併。日盤-only 資料(個股/大盤)的 minute 永遠
 * 不會讓 bucketEnd 溢位,行為零變化。
 *
 * **uv/dv(SC-8)**:缺欄與 0 是兩件事(DK 路徑不帶欄)。只要桶內任一根有欄就設欄、
 * 缺值視 0;全桶皆缺則不設 —— 幾何層據此判「這份資料沒有內外盤」。 */
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
    let bucketEnd = X_ORIGIN_MIN + Math.ceil((minute - X_ORIGIN_MIN) / n) * n;
    let bucketDate = date;
    while (bucketEnd >= DAY_MIN) {
      bucketEnd -= DAY_MIN;
      bucketDate = shiftDate(bucketDate, 1);
    }
    const hasDelta = b.uv !== undefined || b.dv !== undefined;
    const key = `${bucketDate} ${bucketEnd}`;
    if (key !== curKey) {
      if (cur !== null) out.push(cur);
      cur = { t: stampOf(bucketDate, bucketEnd), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v };
      if (hasDelta) {
        cur.uv = b.uv ?? 0;
        cur.dv = b.dv ?? 0;
      }
      curKey = key;
    } else if (cur !== null) {
      cur.h = Math.max(cur.h, b.h);
      cur.l = Math.min(cur.l, b.l);
      cur.c = b.c;
      cur.v += b.v;
      if (hasDelta) {
        cur.uv = (cur.uv ?? 0) + (b.uv ?? 0);
        cur.dv = (cur.dv ?? 0) + (b.dv ?? 0);
      }
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

/** 內外盤雙柱高度(SC-8)。x / 柱寬走同索引的 `VolBar`,這裡只給兩段高度 ——
 *  幾何來源單一,元件不必自己重算 slot 與量區比例(同 `priceBottom` 的理由)。 */
export interface DeltaVolBar {
  /** 外盤(uv)柱高 */
  uvH: number;
  /** 內盤(dv)柱高 */
  dvH: number;
}

export interface CandleGeometry {
  candles: Candle[];
  volBars: VolBar[];
  /** 內外盤雙柱高度,與 `candles` / `volBars` 同索引對位。
   *  分母 = 視窗內 `max(uv + dv)`;視窗內全無 uv/dv(或全為 0)→ null = 該回退主量柱。 */
  deltaVol: DeltaVolBar[] | null;
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
/** 矮圖的 y 刻度數(N027)。 */
const Y_TICKS_TIGHT = 3;
/** 降階門檻(svg 高)。可用高 = `(h − X_LABEL_H) × (1 − VOL_RATIO) − 2 × PAD_Y`:
 *  h=140 → 86.3px,5 條的間距 21.6px ≈ 2× 字高(0.625rem ≈ 10px);再矮就開始相接
 *  (1:1 viewBox 後群組卡 / 窄 pane 的 h 可以低到 96 → 可用高 52、間距只剩 13px)。 */
const Y_TICKS_MIN_H = 140;

/** 這張圖的 y 刻度數。**由高度單一決定**,不看域寬 —— 域窄時的去重由下面的
 *  `seen` 收(那是「刻度撞同價」,與「字擠在一起」是兩件事)。 */
function yTickCount(height: number): number {
  return height < Y_TICKS_MIN_H ? Y_TICKS_TIGHT : Y_TICKS;
}

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
      deltaVol: null,
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
  let maxDelta = 0;
  for (const b of bars) {
    const delta = (b.uv ?? 0) + (b.dv ?? 0);
    if (delta > maxDelta) maxDelta = delta;
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

  // maxDelta === 0 涵蓋「全無欄」與「有欄但全 0」兩種:前者是 DK 路徑,後者是零成交
  // 視窗。兩者都不該畫雙柱(也順帶避開除以零),由呼叫端回退主量柱。
  const deltaVol: DeltaVolBar[] | null =
    maxDelta > 0
      ? bars.map((b) => ({
          uvH: ((b.uv ?? 0) / maxDelta) * volH,
          dvH: ((b.dv ?? 0) / maxDelta) * volH,
        }))
      : null;

  // span=0(全平盤)只給一條刻度 — 否則 5 條同價位重疊(且會撞 React key)
  const yTicks: { y: number; priceMilli: number }[] = [];
  if (span <= 0) {
    yTicks.push({ y: toY(hi), priceMilli: snapNearest(hi) });
  } else {
    // 等分後 snap 到合法檔位:等分值是任意整數,直接顯示會吐出 2547.32 這種下不了
    // 單的價位(round3 項 10)。snap 後可能溢出 [lo, hi] —— lo/hi 本身不必然合法
    // (extraSeries 的 MA/布林是 Math.floor 的任意整數),端點被 snap 出界是常態。
    const seen = new Set<number>();
    const ticks = yTickCount(size.height);
    for (let i = 0; i < ticks; i += 1) {
      const raw = Math.round(lo + (span * i) / (ticks - 1));
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

  return { candles, volBars, deltaVol, yTicks, toY, priceAtY, indexOf, priceBottom };
}

/** 水平 overlay 線(持倉均價 / OI 撐壓)的 y;**超出當前 y 視窗回 null 不畫**。
 *
 *  clamp 到邊緣會把「圖外的價位」畫成「圖緣的價位」,那是誤導 —— 均價線貼在圖頂時
 *  看起來像剛好在最高點,實際可能差好幾百點。
 *
 *  超窗判定借 `priceAtY`(它本來就把域外夾回 [lo, hi]):夾制生效 = 原價不在域內。
 *  這樣寫不必再把 hi/lo 洩到幾何介面上,也不會與 `toY` 各留一份域邊界而漂移
 *  —— 既有的 round-trip 測試同時守住這兩支。 */
export function hlineYOf(priceMilli: number, g: CandleGeometry): number | null {
  if (g.candles.length === 0) return null;
  const y = g.toY(priceMilli);
  if (!Number.isFinite(y)) return null;
  // ±1 毫元 = priceAtY 的四捨五入誤差(與 round-trip 測試同一容差)
  return Math.abs(g.priceAtY(y) - priceMilli) <= 1 ? y : null;
}
