/** 個股前端累算:snapshot 為基底 + tick 增量(design v4 §4;與後端 StockDayState 等值)。 */

import { X_END_MIN, X_START_MIN } from "@/lib/stock-intraday-svg";
import { isMarketLevel, snapDown } from "@/lib/stock-tick";

export interface StockTickMsg {
  type: "tick";
  code: string;
  t: string; // 台北 HH:MM:SS.fff
  p: number; // 毫元
  q: number;
  side: "outer" | "inner" | "neutral";
  seq: number;
  /** 成交當下最佳買賣價;缺欄位(舊後端)一律當 null */
  b?: number | null;
  a?: number | null;
  /** 當日高低(毫元)。掛在 tick 而不是另立 meta 訊息型別:engine 只發
   *  tick / book / watchlist_quote 三種,而當日高低本來就只在成交時才會變 */
  h?: number | null;
  l?: number | null;
}

export interface MinuteAgg {
  c: number;
  v: number;
  i: number;
  o: number;
  u: number;
  /** 分鐘內高 / 低(round4 項 1;與後端 `MinuteAgg.high_milli/low_milli` 等值)。
   *
   *  **選填且 `null` 有意義** —— `null` = 「這一分鐘的高低不可知」(舊後端 snapshot 沒給),
   *  不是「等於收盤價」。拿 `c` 頂替會讓分時圖的等值反查(`minute.h === accum.high`)
   *  命中錯的分鐘 → 標記畫在錯的時間點,而且完全靜默。 */
  h?: number | null;
  l?: number | null;
}

/** 逐筆明細一列的**線上形狀**(snapshot / group-state 的 `ticks` 元素)。
 *
 *  與 `TickRow` 分開是因為序號 `n` 是**前端指派**的:後端不發它,把它寫進線上形狀
 *  等於宣告一條不存在的契約,而 tsc 只會在「誰忘了補」時指著錯的那一端。 */
export interface WireTickRow {
  t: string;
  p: number;
  q: number;
  side: string;
  /** 成交當下最佳買 / 賣價(毫元);**選填** —— 舊 snapshot 與既有測試 fixture 都沒有 */
  b?: number | null;
  a?: number | null;
}

export interface TickRow extends WireTickRow {
  /** 逐筆列的單調序號 —— **唯一用途是 React key**(N120)。
   *
   *  改前 `TickTape` 用「尾端回推索引」當 key,前插時不動,但 `ticks` 觸到
   *  `TAPE_MAX` 之後陣列每來一筆就整體左移一格 → 回推索引同樣逐筆 −1,整個 tbody
   *  (30–200 列)卸載重掛,而畫面上只是「明細偶爾閃一下」,沒有任何錯誤訊號。
   *
   *  **兩個產生點同一把尺**(`fromSnapshot` 由 `snap.seq` 往前回推 / `applyTick` 取
   *  `msg.seq`):後端的 `seq` 每收下一筆成交 +1,所以「同一筆成交在兩條路徑上拿到
   *  同一個號」—— 全量 refetch 之後既有列的 key 因此也不變。
   *
   *  值**不保證等於該筆自己的 state seq**:`apply_backfill` 會讓 seq 一次跳增
   *  (`_BACKFILL_SEQ_MARGIN`),回補後由尾回推的號整段平移。key 要的是「單調 + 同批
   *  唯一 + 既有列不變」,這三件事在跳增後仍成立(號只會往上長,不會與舊號相撞)。 */
  n: number;
}

export interface StockMeta {
  name: string;
  ref: number | null;
  upper: number | null;
  lower: number | null;
  y_vol: number | null;
}

export interface StockBook {
  bids: [number, number][];
  asks: [number, number][];
}

/** 一個價位檔位的當日成交量:總張 / 外盤 / 內盤。
 *
 *  `t` 不等於 `o + i` —— 未分類(neutral,開盤集合競價無 Bid/Ask 可比)只進 `t`,
 *  與 `MinuteAgg` 的 `u` 同一語意。 */
export interface VpCell {
  t: number;
  o: number;
  i: number;
}

export interface StockAccum {
  code: string;
  seq: number;
  last: { p: number; t: string; cum_vol: number } | null;
  vwap: number | null;
  minutes: Map<number, MinuteAgg>;
  ticks: TickRow[];
  /** 價位別成交量(key = `snapDown` 後的毫元檔位)。**必填** —— 硬轉 fixture 漏建時
   *  要在消費端炸掉,不要用 `?? new Map()` 吞成靜默空圖。
   *
   *  來源是 tick 全量(`ticks` 的 200 筆上限是 tape 顯示需求,與這裡無關)。 */
  vp: Map<number, VpCell>;
  book: StockBook | null;
  meta: StockMeta | null;
  noData: boolean;
  /** 試撮 / 緩撮窗內(後端引擎以本機時鐘現算,期貨鍵恆 false)。**必填** ——
   *  同 `WatchlistQuote.trial`:選填會讓漏帶靜默成 false = badge 永遠不亮。
   *  snapshot 缺欄位(舊後端)由 `fromSnapshot` 以 `?? false` 降級。 */
  trial: boolean;
  /** 這份 accum 是 `?tape=0` 取回的(後端 `tape_omitted`):明細與 VP 為空是「省略」不是
   *  「尚無成交」。**必填**(同 noData/trial):選填會讓漏帶靜默成 false = 空態永遠印終態文案。
   *  群組 → 單檔切換時 useStockStream 會補打全量,重建後回到 false。 */
  tapeOmitted: boolean;
  /** 這份 accum 的 VP 折自**被截斷**的 tick 序列(N087)。後端 `StockDayState.ticks` 是
   *  `deque(maxlen=20_000)`,>20k tick 的日子(2026-08-21 M0 實測:2609 陽明 29772 筆)
   *  snapshot 只回最近 20000 筆 → **開盤那一段的量沒進 VP**,單檔頁 POC 與後端增量 VP
   *  (卡片 / 群組)可能不同檔。
   *
   *  **選填**(與 `trial` / `tapeOmitted` 的「必填」紀律刻意不同):唯一產生點是
   *  `fromSnapshot`,而漏帶的後果是「少一個 tooltip」而不是「印出錯的終態文案」——
   *  false 是安全側。其餘 accum 來源(期貨 / 指數 adapter、群組 snapshot)本來就不折
   *  tick,沒有這件事可講。 */
  vpTruncated?: boolean;
  /** 當日最高 / 最低成交價(毫元,後端 running max/min)。**top-level 不掛 meta** ——
   *  meta 是 TC4 來的靜態盤別資料,把「由成交推導的當日狀態」塞進去語意錯位,
   *  而且只跑過回補、未收 REALTIME 時 meta 為 null,高低照樣要有值 */
  high: number | null;
  low: number | null;
  /** VWAP 內部分子(毫元 × 張);由 vwap × 總量還原後續算 */
  amountMilli: number;
  volume: number;
}

const TAPE_MAX = 200;

/** 後端 tick deque 的上限(`copycat/live/stock_state.py::_TICKS_MAXLEN`)。snapshot 的
 *  `ticks` 筆數觸到它 = 更早的成交已被丟掉 → VP 偏小(見 `StockAccum.vpTruncated`)。
 *
 *  **不是 §4 那種必須同步改的跨檔契約**:後端若把上限調大,這裡只是不再標示(旗標恆
 *  false),不會生出錯的陳述 —— 失效方向是「少講一句」而不是「講錯」。 */
export const VP_TICK_CAP = 20_000;

export function minuteKey(t: string): number {
  return Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
}

/** 把一筆成交折進價位別直方圖(就地寫入傳入的 map;呼叫端負責先淺拷)。
 *
 *  兩道過濾都是「與畫面其他數字對得上」的必要條件,不是防禦性補丁:
 *  - `isMarketLevel(p)`:鎖漲跌停時 TC4 會在簿的第一檔推市價佇列,價格欄是 `0`。
 *    `snapDown(0)` 是合法運算,會憑空長出一個 0 元檔位。判定走 `stock-tick.ts` 的
 *    **單一定義**而不是自己再寫一次 `p <= 0`(review B4):兩份規則各自漂移的失效樣態
 *    是「閃電梯把某個價欄當市價、VP 卻把它當成一個檔位」,純數字不一致沒有測試會紅。
 *  - `[X_START_MIN, X_END_MIN]` 窗:與 `windowedEntries` / `sideSummary` 同一把尺。
 *    寫成**正向條件的否定**(`!(m >= START && m <= END)`)而不是 `m < START || m > END`
 *    —— 後者對 `NaN`(時間戳解不出分鐘)的兩個比較都是 false,壞掉的 tick 會整筆
 *    漏進 VP(review A3)。
 *
 *  **在全部 tick 皆 `p > 0`、且後端未觸及 20k tick deque 截斷的前提下**,
 *  「VP 全部 bar 的總張 = 說明列 外+內+未分類 三數之和」成立(可互驗)。前提不成立時
 *  VP 是偏小的那一邊 —— 截斷的簽名見 `stock-accum.test.ts` 的 B1 characterization。
 *
 *  cell 一律重建不就地改:memo 比較與時間旅行安全。
 *
 *  **export 是給後端 parity fixture 用的**(change-spec AD-2):後端 `StockDayState._vp`
 *  折的是同一份規則,兩份各漂各的樣態是「同一檔在單檔頁與卡片上 POC 不同」,零錯誤訊號。 */
export function foldVp(
  vp: Map<number, VpCell>,
  t: string,
  p: number,
  q: number,
  side: string,
): void {
  if (isMarketLevel(p)) return;
  const m = minuteKey(t);
  if (!(m >= X_START_MIN && m <= X_END_MIN)) return;
  const key = snapDown(p);
  const cell = vp.get(key) ?? { t: 0, o: 0, i: 0 };
  vp.set(key, {
    t: cell.t + q,
    o: cell.o + (side === "outer" ? q : 0),
    i: cell.i + (side === "inner" ? q : 0),
  });
}

interface SnapshotShape {
  code?: string;
  seq: number;
  last: { p: number; t: string; cum_vol: number } | null;
  vwap: number | null;
  minutes: Record<string, MinuteAgg>;
  ticks: WireTickRow[];
  book: StockBook | null;
  meta: StockMeta | null;
  high?: number | null;
  low?: number | null;
  /** vwap 的分母(後端 `_volume` = 去重剔試撮後的 Σqty);**選填** —— 舊後端沒給。
   *  名字不叫 `vol`:WS `watchlist_quote` 的 `vol` 是 TC4 當日累積量(= `last.cum_vol`),
   *  同名反義的兩個欄位同時在前端手上,誤用不會報錯只會讓 VWAP 靜默偏移(FC-2)。 */
  vwap_vol?: number | null;
  no_data?: boolean;
  tape_omitted?: boolean;
  /** 緩撮旗標;**選填** —— 舊後端沒給(全 additive 契約),缺欄位一律當窗外。 */
  trial?: boolean;
}

/** 後端 minutes(JSON 物件,key 是分鐘字串)→ 前端 Map。
 *
 *  **兩份消費者共用這一份**:`fromSnapshot`(主圖 `/api/stock/state/{code}`)與群組檢視的
 *  batch(`/api/stock/group-state`)。各自寫一次的話漂移的樣態是「其中一邊的 `h`/`l`
 *  沒有正規化成 `null`」——`undefined` 與 `null` 在 `?? null` 之後才等價,而
 *  `buildIntradayGeometry` 的極值等值反查(`m.h === target`)對兩者都是 false,
 *  結果是標記靜默消失,沒有任何測試會紅。 */
export function minutesFromRecord(rec: Record<string, MinuteAgg> | undefined | null): Map<number, MinuteAgg> {
  const minutes = new Map<number, MinuteAgg>();
  for (const [k, v] of Object.entries(rec ?? {})) {
    minutes.set(Number(k), { ...v, h: v.h ?? null, l: v.l ?? null });
  }
  return minutes;
}

export function fromSnapshot(snap: SnapshotShape): StockAccum {
  const minutes = minutesFromRecord(snap.minutes);
  // vwap 的分子要由 `vwap × 分母` 還原,分母是後端的 `vwap_vol`(去重剔試撮後的 Σqty)
  // —— **不是** `last.cum_vol`(TC4 當日累積量)。兩者在有 tick 被去重或試撮丟棄時
  // 就會岔開,拿錯的當分母不會報錯,只會讓增量 VWAP 靜默偏移到下次全量 refetch。
  // `?? cum_vol` 是舊後端(還沒送 vwap_vol)的相容路徑。
  const volume = snap.vwap_vol ?? snap.last?.cum_vol ?? 0;
  // VP fold 走**原始全量** ticks —— 在 `slice(-TAPE_MAX)` 之前。tape 的 200 筆上限是
  // 逐筆明細的顯示需求,VP 要的是「全日」,兩者共用來源但截斷點不同。
  const srcTicks = snap.ticks ?? [];
  const vp = new Map<number, VpCell>();
  for (const row of srcTicks) foldVp(vp, row.t, row.p, row.q, row.side);
  // key 用的單調序號(N120):由 `snap.seq`(= 最後一筆的號)**往前回推**,而不是自
  // 0 起編 —— 自 0 起編的話每次全量 refetch 都把同一筆成交換一個號,既有列全部重掛。
  const kept = srcTicks.slice(-TAPE_MAX);
  const firstN = snap.seq - (kept.length - 1);
  return {
    code: snap.code ?? "",
    seq: snap.seq,
    last: snap.last,
    vwap: snap.vwap,
    minutes,
    ticks: kept.map((row, i) => ({ ...row, n: firstN + i })),
    vp,
    book: snap.book,
    meta: snap.meta,
    high: snap.high ?? null,
    low: snap.low ?? null,
    noData: snap.no_data ?? false,
    trial: snap.trial ?? false,
    tapeOmitted: snap.tape_omitted ?? false,
    // 觸頂 = 後端 deque 已丟掉更早的成交(N087)。`tape=0` 的空 ticks 不會命中這條。
    vpTruncated: srcTicks.length >= VP_TICK_CAP,
    amountMilli: snap.vwap != null ? snap.vwap * volume : 0,
    volume,
  };
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

/** 群組卡片的 snapshot 形狀。**結構型別不 import `GroupSnapshot`** —— lib 反向依賴
 *  hooks 會讓純函式綁上 TanStack Query 那一層;結構相容就夠了,後端補鍵時
 *  `useGroupSnapshots` 那邊加欄位即可,本檔的選填欄位自動接上。 */
export interface GroupLikeSnapshot {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
  noData: boolean;
  /** 以下四鍵為後端 light_snapshot 的加鍵;**選填** —— 舊後端缺 → 降級不畫那幾層 */
  vwap?: number | null;
  high?: number | null;
  low?: number | null;
  vp?: Map<number, VpCell>;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** group-state 的精簡 snapshot → `StockAccum`(卡片變體的分時圖吃的型別)。
 *
 *  **缺鍵一律降級成「不可得」而不是近似**:拿分鐘資料折一份前端版 VWAP / VP 出來,
 *  畫面上會與單檔頁的同一檔對不上(單檔頁走後端逐筆),而兩個數字都「看起來對」——
 *  沒有任何錯誤訊號。少畫一層是誠實的降級。
 *
 *  `ticks` 恆空(group-state 刻意不送:50 檔 × 數千筆 = 頻寬炸彈),故 `amountMilli`
 *  / `volume` / `seq` 全取零值 —— 這份 accum 是**唯讀渲染輸入**,不會再吃 `applyTick`。
 *
 *  `last` 兩分支(edge 10):`liveP` 是每秒更新的那一份,現價圈與末點同源;不可得時
 *  退回**最大分鐘鍵**那格的收盤(不是第一格,也不是 null —— 60s 快照間的空窗照樣要有
 *  現價圈)。 */
export function accumFromGroupSnapshot(
  code: string,
  snap: GroupLikeSnapshot,
  liveP: number | null,
): StockAccum {
  const minutes = extendMinutes(snap.minutes, liveP);
  let last: StockAccum["last"] = null;
  if (liveP !== null && liveP > 0) {
    const now = new Date();
    last = {
      p: liveP,
      t: `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`,
      cum_vol: 0,
    };
  } else if (minutes.size > 0) {
    const lastMin = Math.max(...minutes.keys());
    const agg = minutes.get(lastMin)!;
    last = { p: agg.c, t: `${pad2(Math.floor(lastMin / 60))}:${pad2(lastMin % 60)}:00`, cum_vol: 0 };
  }
  return {
    code,
    seq: 0,
    last,
    vwap: snap.vwap ?? null,
    minutes,
    ticks: [],
    vp: snap.vp ?? new Map(),
    book: null,
    meta: snap.meta,
    noData: snap.noData,
    trial: false,
    tapeOmitted: false,
    high: snap.high ?? null,
    low: snap.low ?? null,
    amountMilli: 0,
    volume: 0,
  };
}

export function applyTick(acc: StockAccum, msg: StockTickMsg): StockAccum {
  const key = minuteKey(msg.t);
  const minutes = new Map(acc.minutes);
  const prev = minutes.get(key) ?? { c: 0, v: 0, i: 0, o: 0, u: 0 };
  // 分鐘高低三條路徑:新分鐘(v=0)→ 本筆;已知高低 → max/min;
  // **高低不可知(舊 snapshot:h 為 null 但已有量)→ 維持 null** ——
  // 只用「本次載入後看到的 tick」算出來的極值不是整分鐘的極值,不可冒充。
  const unknown = prev.v > 0 && prev.h == null;
  const agg: MinuteAgg = {
    c: msg.p,
    v: prev.v + msg.q,
    i: prev.i + (msg.side === "inner" ? msg.q : 0),
    o: prev.o + (msg.side === "outer" ? msg.q : 0),
    u: prev.u + (msg.side === "neutral" ? msg.q : 0),
    h: unknown ? null : Math.max(prev.h ?? msg.p, msg.p),
    l: unknown ? null : Math.min(prev.l ?? msg.p, msg.p),
  };
  minutes.set(key, agg);
  const amountMilli = acc.amountMilli + msg.p * msg.q;
  const volume = acc.volume + msg.q;
  const ticks = [
    ...acc.ticks,
    // `n` 取 `msg.seq`:與 `fromSnapshot` 的回推同一把尺(N120),丟頭時倖存列的號不動。
    { t: msg.t, p: msg.p, q: msg.q, side: msg.side, b: msg.b ?? null, a: msg.a ?? null, n: msg.seq },
  ].slice(-TAPE_MAX);
  // 淺拷後折本筆:O(當日成交過的檔位數)。**不是固定的 ~200** —— 有漲跌停時域是
  // [lower, upper](± 10%),autofit 的低價股(tick 0.01 元)可以近千檔。仍遠小於
  // 每秒 tick 數的量級,Map 淺拷在這個尺度上不是熱點。cell 由 foldVp 重建不就地改。
  const vp = new Map(acc.vp);
  foldVp(vp, msg.t, msg.p, msg.q, msg.side);
  return {
    ...acc,
    seq: msg.seq,
    last: { p: msg.p, t: msg.t, cum_vol: (acc.last?.cum_vol ?? acc.volume) + msg.q },
    vwap: volume > 0 ? Math.round(amountMilli / volume) : null,
    minutes,
    ticks,
    vp,
    // 缺欄位 → 保留原值(舊後端不發 h/l 時,線不該閃掉)
    high: msg.h ?? acc.high,
    low: msg.l ?? acc.low,
    amountMilli,
    volume,
  };
}
