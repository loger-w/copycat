/** 期貨近全時段(日盤 + 夜盤)的 x 軸索引與錨定日 slice(SC-1/SC-3;design §3.1)。
 *
 * 純函式無 React —— 元件只負責掛 DOM(對齊 lib/candle.ts / lib/futures-ladder.ts 慣例)。
 *
 * **段定義與後端 `futures_source.FUTURES_ALLDAY_DOMAIN` 對齊,改一邊必改另一邊**:
 * 日盤 300 分(0846–1345)、夜盤前半 539 分(1501–2359)、夜盤後半 301 分(0000–0500),
 * 合計 1140。分鐘標記是**終點標記**(08:45 開盤的第一根 1K 標 0846、15:00 開盤的標 1501),
 * 與 candle.ts 檔頭同一套語意。
 */

import type { Bar } from "@/lib/candle";
import type { XWindow } from "@/lib/stock-intraday-svg";
import { hhmm, type HourTick } from "@/lib/time-labels";

export interface AlldaySegment {
  /** 段首分鐘(HHMM,含) */
  start: string;
  /** 段末分鐘(HHMM,含) */
  end: string;
  /** 段內分鐘數 */
  len: number;
  /** 該段第一分鐘在全域軸上的索引 */
  offset: number;
}

function minuteOf(hhmm: string): number | null {
  if (!/^\d{4}$/.test(hhmm)) return null;
  const h = Number(hhmm.slice(0, 2));
  const m = Number(hhmm.slice(2, 4));
  if (h > 23 || m > 59) return null;
  return h * 60 + m;
}

function segment(start: string, end: string, offset: number): AlldaySegment {
  // 段本身不跨午夜(夜盤刻意拆兩段),所以直接相減即可
  const len = minuteOf(end)! - minuteOf(start)! + 1;
  return { start, end, len, offset };
}

/** 三段近全軸。offset 由前段累加,段長改動自動傳導(不留第二份手寫數字)。 */
export const ALLDAY_SEGMENTS: readonly AlldaySegment[] = (() => {
  const raw: [string, string][] = [
    ["0846", "1345"], // 日盤(= 後端 FUTURES_MINUTE_DOMAIN)
    ["1501", "2359"], // 夜盤前半
    ["0000", "0500"], // 夜盤後半(次日凌晨)
  ];
  const out: AlldaySegment[] = [];
  let offset = 0;
  for (const [start, end] of raw) {
    const seg = segment(start, end, offset);
    out.push(seg);
    offset += seg.len;
  }
  return out;
})();

/** 一整個交易日的軸長度(= 1140)。 */
export const ALLDAY_LEN = ALLDAY_SEGMENTS.reduce((a, s) => a + s.len, 0);

/** HHMM → 全域軸索引;落在死區(13:46–15:00 / 05:01–08:45)或壞值回 null。 */
export function alldayIndexOf(hhmm: string): number | null {
  const m = minuteOf(hhmm);
  if (m === null) return null;
  for (const seg of ALLDAY_SEGMENTS) {
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
 *  標籤要釘在夜盤段起點(index 300)才不會整個消失(design §3.1 D11)。 */
export const ALLDAY_TICKS: readonly AlldayTick[] = (() => {
  const [day, night1, night2] = ALLDAY_SEGMENTS as [
    AlldaySegment,
    AlldaySegment,
    AlldaySegment,
  ];
  const at = (seg: AlldaySegment, hhmm: string): number =>
    seg.offset + (minuteOf(hhmm)! - minuteOf(seg.start)!);
  return [
    { index: at(day, "0900"), label: "09:00" },
    { index: at(day, "1100"), label: "11:00" },
    { index: at(day, "1300"), label: "13:00" },
    { index: night1.offset, label: "15:00" }, // 段起點,非 at(night1, "1500")(那會是 −1)
    { index: at(night1, "1800"), label: "18:00" },
    { index: at(night1, "2100"), label: "21:00" },
    { index: night2.offset, label: "00:00" },
    { index: at(night2, "0300"), label: "03:00" },
    { index: at(night2, "0500"), label: "05:00" },
  ];
})();

/** 近全軸當 `IntradayChartCore` 的 x 窗:**key = 軸索引**(0..ALLDAY_LEN−1)不是分鐘數。
 *
 *  core 的幾何(`minuteToX` / `minuteOf` / `windowedEntries` / `sideSummary` / `barW`)
 *  對 key 的唯一要求是「落在 `[xw.start, xw.end]` 的整數、可排序」—— 近全軸的索引正好
 *  滿足,而且死區自然不佔 x(13:45 與 15:01 相鄰)。
 *
 *  **模組層常數不是行內字面值**:窗物件會直接進 `memo` 子元件的 props,行內 `{...}`
 *  每次 render 都是新 identity,靜態圖層的 memo 會被整層打穿(同 `STKFUT_WINDOW`)。 */
export const ALLDAY_WINDOW: XWindow = { start: 0, end: ALLDAY_LEN - 1 };

/** `ALLDAY_TICKS` 換成 core 的 `HourTick` 形狀(`minute` 欄放的是**軸索引**)。
 *
 *  兩份標籤表不各寫一次:index 的推導(15:00 釘在夜盤段起點)只此一處,
 *  漏同步的樣態是「軸標籤與線各自對一套刻度」,目視幾乎抓不到。identity 同上。 */
export const ALLDAY_HOUR_TICKS: readonly HourTick[] = ALLDAY_TICKS.map(({ index, label }) => ({
  minute: index,
  label,
}));

/** 軸索引 → `HH:MM`(`alldayIndexOf` 的反函式)。域外 / 非整數 → `""`。
 *
 *  core 的 readout 首欄與 hover 底部標籤吃這一支(`timeText` 注入)—— 不注入的話印出來的
 *  是把索引當分鐘數換算的假時刻(index 300 → 「05:00」,真值是 15:01)。
 *
 *  **不夾制、不猜**:域外回空字串而不是最近的合法時刻 —— 索引本來就只在 [0, 1139]
 *  有意義,回一個「看起來對」的時刻會讓錯位完全靜默(同 `alldayIndexOf` 的死區回 null)。 */
export function alldayHhmmOf(index: number): string {
  if (!Number.isInteger(index)) return "";
  for (const seg of ALLDAY_SEGMENTS) {
    if (index >= seg.offset && index < seg.offset + seg.len) {
      return hhmm(minuteOf(seg.start)! + (index - seg.offset));
    }
  }
  return "";
}

/** `YYYY-MM-DD HH:MM` → 軸索引;非分 K 時戳(日 K:無空格)/ 死區 → null。
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

function shiftDate(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

/** bar 時戳 → 交易錨定日:夜盤後半(≤05:00)屬**前一日**的交易日,其餘為當日。
 *
 *  分時圖的 slice(§3.1)與 live 點的 gate(§3.2)共用這一支 —— 兩處各算一份必漂移,
 *  而漂移的表現是「開盤瞬間拉出一條橫貫整圖的假線」這種只在特定分鐘出現的症狀。 */
export function anchorDateOf(t: string): string {
  const sp = t.indexOf(" ");
  if (sp < 0) return t;
  const date = t.slice(0, sp);
  const hhmm = t.slice(sp + 1);
  const m = Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
  if (!Number.isFinite(m)) return date;
  return m <= 5 * 60 ? shiftDate(date, -1) : date;
}

/** 取「當前交易日」那一段 bars(升冪輸入)。
 *
 *  以**最後一根 bar** 反推錨定日,再取 `t >= "{anchor} 08:46"` 的尾段(字串比較)。
 *  不依賴 08:46 那根存在 —— 該分鐘無成交時 TC4 不給 bar,用「找 08:46 的 index」會錯位。 */
export function sliceCurrentAllday(bars: readonly Bar[]): Bar[] {
  const last = bars[bars.length - 1];
  if (last === undefined) return [];
  const floor = `${anchorDateOf(last.t)} ${ALLDAY_SEGMENTS[0]!.start.slice(0, 2)}:${ALLDAY_SEGMENTS[0]!.start.slice(2, 4)}`;
  return bars.filter((b) => b.t >= floor);
}
