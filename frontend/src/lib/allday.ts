/** 期貨近全時段(夜盤 + 日盤)的 x 軸索引與錨定日 slice(SC-1/SC-3;design §3.1;
 *  mod/futures-day-1500 改成 15:00 夜盤起算)。
 *
 * 純函式無 React —— 元件只負責掛 DOM(對齊 lib/candle.ts / lib/futures-ladder.ts 慣例)。
 *
 * **一天 = 期交所口徑**:15:00 夜盤開 → 05:00 夜盤收 → 05:01–08:45 無交易**空檔**(保留在軸上,
 * 分時圖畫成水平線;user 平時 APP 的畫法)→ 08:46 日盤 → 13:45 收。13:46–15:00 在一天之外,
 * 不佔軸(右緣就是 13:45)。
 *
 * **可交易三段的段界與後端 `futures_source.FUTURES_ALLDAY_DOMAIN` 對齊,改一邊必改另一邊**:
 * 夜盤前半 539 分(1501–2359)、夜盤後半 301 分(0000–0500)、日盤 300 分(0846–1345);
 * 空檔 225 分(0501–0845)只有前端有(後端 bar 不會落在裡面:0501–0505 被 clamp 進 0500)。
 * 合計 1365。分鐘標記是**終點標記**(15:00 開盤的第一根 1K 標 1501、08:45 開盤的標 0846),
 * 與 candle.ts 檔頭同一套語意。
 *
 * **錨定日**(CONTEXT.md):日盤 bar 屬當日曆日;夜盤 bar(D 15:01 → D+1 05:00)屬 **D 的次一交易日**
 * (週五夜盤 → 週一;假日前夜盤 → 假日後首交易日)。次一交易日吃 `lib/trading-calendar.ts`
 * (`/api/calendar` 假日集合;未載入 = 只跳週末)。
 */

import type { Bar } from "@/lib/candle";
import type { XWindow } from "@/lib/stock-intraday-svg";
import { hhmm, type HourTick } from "@/lib/time-labels";
import { nextTradingDayIso, shiftIso } from "@/lib/trading-calendar";

export interface AlldaySegment {
  /** 段首分鐘(HHMM,含) */
  start: string;
  /** 段末分鐘(HHMM,含) */
  end: string;
  /** 段內分鐘數 */
  len: number;
  /** 該段第一分鐘在全域軸上的索引 */
  offset: number;
  /** false = 空檔:佔軸(x 有位置)但沒有 bar / live 點 / 成交點會落在裡面 */
  tradable: boolean;
}

function minuteOf(hhmm: string): number | null {
  if (!/^\d{4}$/.test(hhmm)) return null;
  const h = Number(hhmm.slice(0, 2));
  const m = Number(hhmm.slice(2, 4));
  if (h > 23 || m > 59) return null;
  return h * 60 + m;
}

function segment(start: string, end: string, offset: number, tradable: boolean): AlldaySegment {
  // 段本身不跨午夜(夜盤刻意拆兩段),所以直接相減即可
  const len = minuteOf(end)! - minuteOf(start)! + 1;
  return { start, end, len, offset, tradable };
}

/** 四段近全軸(15:00 起算)。offset 由前段累加,段長改動自動傳導(不留第二份手寫數字)。 */
export const ALLDAY_SEGMENTS: readonly AlldaySegment[] = (() => {
  const raw: [string, string, boolean][] = [
    ["1501", "2359", true], // 夜盤前半(15:00 開盤 → 首根終點標記 1501)
    ["0000", "0500", true], // 夜盤後半(次日凌晨)
    ["0501", "0845", false], // 空檔:無交易,只佔軸
    ["0846", "1345", true], // 日盤(= 後端 FUTURES_MINUTE_DOMAIN)
  ];
  const out: AlldaySegment[] = [];
  let offset = 0;
  for (const [start, end, tradable] of raw) {
    const seg = segment(start, end, offset, tradable);
    out.push(seg);
    offset += seg.len;
  }
  return out;
})();

/** 一整個交易日的軸長度(= 1365,含空檔)。 */
export const ALLDAY_LEN = ALLDAY_SEGMENTS.reduce((a, s) => a + s.len, 0);

/** 空檔段在軸上的索引區間(含兩端)。adapter 用它判「夜盤側 / 日盤側」並在 `end` 補水平橋。 */
export const ALLDAY_GAP: { readonly start: number; readonly end: number } = (() => {
  const gap = ALLDAY_SEGMENTS.find((s) => !s.tradable)!;
  return { start: gap.offset, end: gap.offset + gap.len - 1 };
})();

/** HHMM → 全域軸索引;落在空檔(05:01–08:45)、一天之外(13:46–15:00)或壞值回 null。 */
export function alldayIndexOf(hhmm: string): number | null {
  const m = minuteOf(hhmm);
  if (m === null) return null;
  for (const seg of ALLDAY_SEGMENTS) {
    if (!seg.tradable) continue;
    const lo = minuteOf(seg.start)!;
    if (m >= lo && m <= lo + seg.len - 1) return seg.offset + (m - lo);
  }
  return null;
}

export interface AlldayTick {
  index: number;
  label: string;
}

/** 軸標籤。**index 由「段內偏移」直接算,不經 `alldayIndexOf` 查值** ——
 *  15:00 是開盤時刻而非任何 bar 的終點標記(域內首根是 1501),查值會回 null;
 *  標籤要釘在軸起點(index 0)才不會整個消失(design §3.1 D11)。
 *  空檔保留在軸上後 05:00 與 09:00 相距 240 格,九顆標籤不再撞字。 */
export const ALLDAY_TICKS: readonly AlldayTick[] = (() => {
  const [night1, night2, , day] = ALLDAY_SEGMENTS as [
    AlldaySegment,
    AlldaySegment,
    AlldaySegment,
    AlldaySegment,
  ];
  const at = (seg: AlldaySegment, hhmm: string): number =>
    seg.offset + (minuteOf(hhmm)! - minuteOf(seg.start)!);
  return [
    { index: night1.offset, label: "15:00" }, // 段起點,非 at(night1, "1500")(那會是 −1)
    { index: at(night1, "1800"), label: "18:00" },
    { index: at(night1, "2100"), label: "21:00" },
    { index: night2.offset, label: "00:00" },
    { index: at(night2, "0300"), label: "03:00" },
    { index: at(night2, "0500"), label: "05:00" },
    { index: at(day, "0900"), label: "09:00" },
    { index: at(day, "1100"), label: "11:00" },
    { index: at(day, "1300"), label: "13:00" },
  ];
})();

/** 近全軸當 `IntradayChartCore` 的 x 窗:**key = 軸索引**(0..ALLDAY_LEN−1)不是分鐘數。
 *
 *  core 的幾何(`minuteToX` / `minuteOf` / `windowedEntries` / `sideSummary` / `barW`)
 *  對 key 的唯一要求是「落在 `[xw.start, xw.end]` 的整數、可排序」—— 近全軸的索引正好
 *  滿足;一天之外的 13:46–15:00 自然不佔 x,空檔 05:01–08:45 則佔 x 但沒有 key。
 *
 *  **模組層常數不是行內字面值**:窗物件會直接進 `memo` 子元件的 props,行內 `{...}`
 *  每次 render 都是新 identity,靜態圖層的 memo 會被整層打穿(同 `STKFUT_WINDOW`)。 */
export const ALLDAY_WINDOW: XWindow = { start: 0, end: ALLDAY_LEN - 1 };

/** `ALLDAY_TICKS` 換成 core 的 `HourTick` 形狀(`minute` 欄放的是**軸索引**)。
 *
 *  兩份標籤表不各寫一次:index 的推導(15:00 釘在軸起點)只此一處,
 *  漏同步的樣態是「軸標籤與線各自對一套刻度」,目視幾乎抓不到。identity 同上。 */
export const ALLDAY_HOUR_TICKS: readonly HourTick[] = ALLDAY_TICKS.map(({ index, label }) => ({
  minute: index,
  label,
}));

/** 軸索引 → `HH:MM`(軸位置的反演;含空檔索引 —— hover 到空檔底標印真時刻,不印 ""）。
 *  域外 / 非整數 → `""`。
 *
 *  core 的 readout 首欄與 hover 底部標籤吃這一支(`timeText` 注入)—— 不注入的話印出來的
 *  是把索引當分鐘數換算的假時刻(index 0 → 「00:00」,真值是 15:01)。
 *
 *  **不夾制、不猜**:域外回空字串而不是最近的合法時刻 —— 索引本來就只在 [0, 1364]
 *  有意義,回一個「看起來對」的時刻會讓錯位完全靜默(同 `alldayIndexOf` 的空檔回 null)。 */
export function alldayHhmmOf(index: number): string {
  if (!Number.isInteger(index)) return "";
  for (const seg of ALLDAY_SEGMENTS) {
    if (index >= seg.offset && index < seg.offset + seg.len) {
      return hhmm(minuteOf(seg.start)! + (index - seg.offset));
    }
  }
  return "";
}

/** `(from, to]` 之間有幾個**可交易**索引(= 缺了幾根 1K)。`to ≤ from` → 0。
 *
 *  live gate 5 的「分時資料落後 N 根」用它而不是裸差值:尾根 05:00(839)對 08:47 的成交
 *  (1066)裸差 227,真正缺的只有 0846 / 0847 兩根 —— 空檔不是「TC4 回補中」。 */
export function alldayBarsBetween(from: number, to: number): number {
  if (to <= from) return 0;
  let n = 0;
  for (const seg of ALLDAY_SEGMENTS) {
    if (!seg.tradable) continue;
    const lo = Math.max(seg.offset, from + 1);
    const hi = Math.min(seg.offset + seg.len - 1, to);
    if (hi >= lo) n += hi - lo + 1;
  }
  return n;
}

/** `YYYY-MM-DD HH:MM` → 軸索引;非分 K 時戳(日 K:無空格)/ 空檔 / 一天之外 → null。
 *
 *  自 `FuturesChart.indexOfBar` 搬入(行為逐字同):adapter 與 live gate 兩處都要用,
 *  留在元件裡的話 lib 側就得再寫一份,而兩份對「日 K 時戳」的處理一旦漂掉,
 *  症狀是日 K bars 被當成 index 0 全部堆在開盤那一分鐘。 */
export function alldayIndexOfStamp(t: string): number | null {
  const sp = t.indexOf(" ");
  if (sp < 0) return null;
  const hm = t.slice(sp + 1);
  return alldayIndexOf(`${hm.slice(0, 2)}${hm.slice(3, 5)}`);
}

/** 夜盤前半的第一分鐘(15:01)與夜盤後半的最後一分鐘(05:00),以分鐘數表示。
 *  由段表推導,不另寫一份數字。 */
const NIGHT_FIRST_MIN = minuteOf(ALLDAY_SEGMENTS[0]!.start)!;
const NIGHT_LAST_MIN = minuteOf(ALLDAY_SEGMENTS[1]!.end)!;

/** 錨定日只由「日曆日 + 三分類」決定:`n1` 夜盤前半(≥ 15:01)/ `n2` 夜盤後半(≤ 05:00)/
 *  `d` 其餘(日盤與兩段空檔;壞時刻也歸這類 = 回當日)。純日期(無時刻)→ null。
 *  `anchorDateOf` 與 `sliceCurrentAllday` 的 memo 鍵**共用這一支** —— 分界改在一處,
 *  快取鍵不會與錨定日規則分家。 */
function anchorClassOf(t: string): { date: string; cls: "n1" | "n2" | "d" } | null {
  const sp = t.indexOf(" ");
  if (sp < 0) return null;
  const m = Number(t.slice(sp + 1, sp + 3)) * 60 + Number(t.slice(sp + 4, sp + 6));
  const cls = m >= NIGHT_FIRST_MIN ? "n1" : m <= NIGHT_LAST_MIN ? "n2" : "d";
  return { date: t.slice(0, sp), cls };
}

/** bar 時戳 → 錨定日(期交所口徑):
 *  - 日盤(08:46–13:45)與空檔(13:46–15:00 / 05:01–08:45)→ 當日曆日;
 *  - 夜盤前半(D 15:01–23:59)→ D 的次一交易日;
 *  - 夜盤後半(D+1 00:00–05:00)→ D 的次一交易日(= 同一個)。
 *
 *  `holidays` 顯式帶入時用那一份算(元件把 `/api/calendar` query data 當 memo dep 那條路),
 *  否則讀 `lib/trading-calendar` 模組集合(未載入 = 只跳週末)。
 *
 *  分時圖的 slice(§3.1)、live 點的 gate(§3.2)與成交點的日期界共用這一支 —— 三處各算
 *  一份必漂移,而漂移的表現是「開盤瞬間拉出一條橫貫整圖的假線」這種只在特定分鐘出現的症狀。 */
export function anchorDateOf(t: string, holidays?: ReadonlySet<string>): string {
  const c = anchorClassOf(t);
  if (c === null) return t;
  if (c.cls === "n1") return nextTradingDayIso(c.date, holidays);
  if (c.cls === "n2") return nextTradingDayIso(shiftIso(c.date, -1), holidays);
  return c.date;
}

/** 取「當前交易日」那一段 bars(升冪輸入):錨定日 == 末根 bar 的錨定日。
 *
 *  不依賴 15:01 那根存在 —— 該分鐘無成交時 TC4 不給 bar,用「找 15:01 的 index」會錯位。
 *  13:45–15:00 之間末根是 13:45 → 整個剛收的一天;15:01 首根一到 → 翻頁(前一天整段落出)。
 *  逐 bar 算錨定日,同日曆日 + 同盤別的結果以 map 記住(5 日 ≈ 5,700 根,次一交易日查詢
 *  最多十來次)。 */
export function sliceCurrentAllday(bars: readonly Bar[], holidays?: ReadonlySet<string>): Bar[] {
  const last = bars[bars.length - 1];
  if (last === undefined) return [];
  const memo = new Map<string, string>();
  const anchorOf = (t: string): string => {
    const c = anchorClassOf(t);
    if (c === null) return t;
    const key = `${c.date}|${c.cls}`;
    let a = memo.get(key);
    if (a === undefined) {
      a = anchorDateOf(t, holidays);
      memo.set(key, a);
    }
    return a;
  };
  const anchor = anchorOf(last.t);
  return bars.filter((b) => anchorOf(b.t) === anchor);
}
