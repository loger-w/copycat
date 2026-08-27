import type { HandoverProgress } from "@/components/ConnectionBadge";

export type SnapshotStatus =
  | "connecting"
  | "backfilling"
  | "live"
  | "reconnecting"
  | "disconnected"
  | "degraded"
  | "replay";

/** 8 支 WS hook 共用的連線狀態(R4 N034 自 7 份同值宣告收斂到此):
 *  `connecting` = 建 socket 中(含每次重連)/ `open` = onopen 後 / `closed` = 斷線或 watchdog 放棄後。 */
export type WsStatus = "connecting" | "open" | "closed";

export interface SnapshotTotals {
  call_net_qty: number;
  put_net_qty: number;
  contracts_active: number;
  ticks: number;
  unclassified_ticks: number;
  unclassified_qty: number;
  overlap_risk_ticks: number;
  dropped_foreign_ticks: number;
  queue_dropped: number;
}

export interface ContractRow {
  symbol: string;
  cp: "C" | "P";
  strike: number;
  net_qty: number;
  volume: number;
  outer_qty: number;
  inner_qty: number;
  /** 最近成交價(點;snapshot 契約只加不改)。缺值時 OrderPanel 鎖市價選項。 */
  last_price?: number | null;
}

export interface Snapshot {
  series_id: string | null;
  series_name?: string;
  status: SnapshotStatus | string;
  accumulated_from?: string;
  generated_at?: string;
  spot?: { symbol: string; price: number | null };
  curve: [number, number][];
  beps?: number[];
  max_profit?: { x: number; y: number } | null;
  max_loss?: { x: number; y: number } | null;
  spot_pnl?: number | null;
  contracts?: ContractRow[];
  totals?: SnapshotTotals;
  /** 交接(回補)觀測欄;後端 `EngineRuntime._handover`。形狀定義在**唯一的讀者**
   *  `ConnectionBadge` 那邊(review F4:badge 不該為了拿型別而 import 一份它不消費的
   *  TXO 快照),這裡只是目前其中一條運送管道。 */
  handover?: HandoverProgress | null;
}

export interface SeriesItem {
  series_id: string;
  name: string;
  expiry: string;
}

// ---- capital(群益;對應 backend copycat/capital/models.py + client.status_view)----

/** GET /api/capital/status;未啟用時只有 {status:"disabled"},其餘欄位 optional。 */
export interface CapitalStatus {
  status: "starting" | "ok" | "degraded" | "error" | "disabled" | (string & {});
  env?: string;
  account_masked?: string | null;
  futures_account_masked?: string | null;
  order_enabled?: boolean;
}

/** OrderRecord asdict(委託清單一列;qty 已換算顯示單位)。 */
export interface CapitalOrder {
  seq_no: string;
  stock_no: string | null;
  name: string;
  market: string | null;
  buy_sell: string | null; // "B"/"S"
  flag_label: string | null;
  book_no: string | null;
  status_raw: string | null;
  status_label: string | null;
  price: number | null;
  avg_fill_price: number | null;
  order_qty: number;
  filled_qty: number;
  unit: string;
  date: string | null; // YYYYMMDD
  time: string | null; // HH:MM:SS
  pre_order: boolean;
  error_msg: string | null;
  actionable: boolean; // store 算好;前端不要自己抄狀態表
  /** 價格別:**本 app 送出才知道**(群益回報無此欄)→ 群益 APP 下的單 / 跨日的單恆 null。 */
  price_type: "limit" | "market" | null;
  raw: string;
}

/** 即時庫存種類(平倉可指定的值域)。後端 PositionKind 同字彙。 */
export type PositionKind = "cash" | "margin" | "short";

/** 後端 `AvgSource` 同字彙(models.py):均價語意來源。執行期白名單(`ladder-position.ts::isAvgSource`)
 * 與型別**同源** —— 加值只改這一列;`positionEcon` 的 exhaustive switch 會逼你補 case(pr-119 F-02 / review S2)。 */
export const AVG_SOURCES = ["broker", "fill"] as const;
export type AvgSource = (typeof AVG_SOURCES)[number];

/** Position asdict(sec=股號;fut=期交所契約碼;空方 qty 為負)。 */
export interface CapitalPosition {
  market: string; // sec/fut
  stock_no: string;
  qty: number;
  name: string;
  avg_price: number | null;
  // 後端 Position.kind 值域是 TradeKind(另含 daytrade_sell 無券空單),比 PositionKind 寬
  kind: string;
  pnl_base: number | null;
  pnl_base_price: number | null;
  pnl_cost: number | null;
  /** `avg_price` 的語意來源(後端 `Position.avg_source`):`broker` = 群益損益試算均價,
   *  **已含買進手續費**;`fill` = 成交回報樂觀套用的純成交價;null = 來源未知(均價缺值、
   *  或產生點沒標 —— 例如期貨 OI 列)。打平線 / 損益依此決定要不要再加買費
   *  (`ladder-position::positionEcon`:null 走修前口徑當純價加買費,不當假數字)。 */
  avg_source: AvgSource | null;
  /** 今天成交淨進來的張數(後端已 clamp 到 [0, |qty|];fut 恆 0)—— 現股當沖賣出稅 0.15% 只套這一段。 */
  today_qty: number;
  /** 後端在 API 邊界附的衍生欄(非 Position dataclass 欄位):sec = stock_no;
   *  fut = 契約碼反查到的股號,反查不到(未知產品 / 除權息調整碼)= null。
   *  前端沒有契約碼→股號的反查,以股號為鍵的顯示只能靠這欄。 */
  code: string | null;
}

/** OrderResult asdict(寫入動作共同回傳形)。 */
export interface OrderResult {
  ok: boolean;
  code: number;
  message: string;
  seq_no: string | null;
}

export type CapitalMarket = "sec" | "fut";

export interface CapitalStockOrderBody {
  stock_no: string;
  buy_sell: "buy" | "sell";
  price: number;
  qty: number; // 張
  price_type?: "limit" | "market";
  time_in_force?: "ROD" | "IOC" | "FOK";
  trade_kind?: "cash" | "margin" | "short" | "daytrade_sell";
  source?: string;
}

export interface CapitalFutureOrderBody {
  tc4_symbol: string;
  buy_sell: "buy" | "sell";
  price: number;
  qty: number; // 口
  price_type?: "limit" | "market";
  time_in_force?: "ROD" | "IOC" | "FOK";
  day_trade?: boolean;
  source?: string;
}

export interface CapitalCancelBody {
  seq_no: string;
  market: CapitalMarket;
}

export interface CapitalCorrectPriceBody {
  seq_no: string;
  market: CapitalMarket;
  price: number;
}

export interface CapitalDecreaseBody {
  seq_no: string;
  market: CapitalMarket;
  qty: number;
}

export interface CapitalCloseBody {
  market: CapitalMarket;
  key: string;
  price: number; // 市價單也必帶(閘用估價)
  qty?: number | null; // null=全部
  price_type?: "limit" | "market";
  source?: string;
  /** sec 庫存種類 — 同檔資+集保並存時的第二把鍵(未帶且多列 → 後端阻擋);fut 不送。 */
  kind?: PositionKind;
}

// ---- futures 行情(對應 copycat/server/futures_engine.py state())----

export interface FuturesProductState {
  product: string; // TXF/MXF/TMF
  name: string;
  p: number | null; // 毫點
  q: number | null;
  cum_vol: number | null;
  t: string | null;
  date: string | null;
  bids: [number, number][]; // [price_milli, qty] 最佳在前
  asks: [number, number][];
  ref: number | null;
  upper: number | null;
  lower: number | null;
  resolved_contract: string | null; // HOT → YYYYMM;null=未解析(送單層拒單)
}

export interface FuturesState {
  seq: number;
  products: Record<string, FuturesProductState>;
}

/** 相關係數面板(realtime-correlation SC-6/7)。 */
export interface CorrLegState {
  label: string; // 繁中顯示名(後端帶,前端不寫死對照表)
  mid: number | null; // 毫點中價;stale 或無報價 → null
  stale: boolean;
}

/** 一條腿對 base 的各窗結果:`w<秒>` = 相關係數(樣本不足/常數序列 → null)、`n<秒>` = 樣本數。 */
export type CorrPairState = Record<string, number | null>;

export interface CorrState {
  type: string; // "corr"
  seq: number;
  session: string; // "day" | "night"
  base: string; // 基準腿 key(其餘各腿與它配對)
  windows: number[]; // 秒;前端據此產欄,後端改設定時自動跟上
  legs: Record<string, CorrLegState>;
  pairs: Record<string, CorrPairState>;
}

// ---- 江波圖(對應 copycat/live/river_state.py;index-river-chart)----

/** 當場盤別的 x 軸窗(台北 minute-of-day;夜盤 end_min > 1440 = 跨午夜展開)。 */
export interface RiverWindow {
  start_min: number;
  end_min: number;
}

/** 一條腿的分鐘序列。`minutes` 鍵是窗內 offset,但 **JSON 物件鍵恆為字串** → 幾何層 Number(k)。 */
export interface RiverLeg {
  label: string; // 繁中顯示名(後端帶)
  minutes: Record<string, number>; // offset → 該分鐘收盤毫點
  last: number | null; // 最大 offset 的價;本場無資料 → null
  last_minute: number | null;
}

export interface RiverState {
  type: string; // "river"
  seq: number;
  session: string; // "day" | "night"
  base: string; // 基準腿 key(重疊圖畫粗線)
  window: RiverWindow;
  legs: Record<string, RiverLeg>;
}

// ---- TXO 月契約 OI 撐壓(對應 copycat/server/oi_levels.py;futures-allday SC-11)----

/** 單一履約價的雙邊 OI(口)。缺該邊的列由後端填 0。 */
export interface OiStrikeRow {
  strike: number;
  call_oi: number;
  put_oi: number;
}

/** `GET /api/futures/oi-levels`。降級一律 200 + `{date:null, contract:null, strikes:[]}`
 *  —— token 未設 / 契約未解析 / FinMind 掛了都是同一種空 shape(SC-11 語意)。 */
export interface OiLevelsResponse {
  date: string | null; // 資料日 YYYY-MM-DD
  contract: string | null; // YYYYMM
  strikes: OiStrikeRow[]; // strike 升冪
}

// ---- 交易日曆(對應 copycat/trading_calendar.py;mod/trading-calendar SC-6)----

/** `GET /api/calendar`(恆 200,純 config 推導、不依賴任何引擎 → boot 窗內也答得出來)。
 *
 *  **兩個日期刻意分開**:`trade_date` = stock / index / signals hub 實際採用的日別
 *  (`TXO_BACKFILL_DATE` 有值時就是它);`calendar_trade_date` = 純日曆推導 = breadth
 *  一律採用的日別。env 模式下兩者會不一致(KR-5)。
 *
 *  前端只吃 `holidays`(灌進 `lib/trading-calendar`);其餘欄位是可視化 / 診斷用
 *  (`years_loaded` 不含當年 = 日曆過期,此後只擋週末)。 */
export interface CalendarState {
  today: string; // 牆鐘 YYYY-MM-DD
  trade_date: string;
  calendar_trade_date: string;
  backfill_env: string | null;
  holidays: string[]; // YYYY-MM-DD 升冪
  /** 補班交易日(週末仍開盤),升冪。**optional**:後端 2026-08-25 才 additive 加上,
   *  舊 payload / 舊治具沒有這格 —— 讀取端一律 `?? []`(失效方向 = 退回改動前行為)。 */
  extra_trading_days?: string[];
  years_loaded: number[];
  calendar_loaded: boolean;
}

// ---- 全市場家數帶 / 騰落線(對應 copycat/server/breadth_engine.py;market-overview R2)----

/** 一格分鐘的五桶計數,桶序固定 `[limit_up, up, flat, down, limit_down]`
 *  —— 與後端 `_series_list()` 同一份順序,前端不得重排。 */
export type BreadthBuckets = [number, number, number, number, number];

/** 當下家數(scalar);上市 / 上櫃各一組。 */
export interface BreadthCounts {
  twse: { limit_up: number; up: number; flat: number; down: number; limit_down: number };
  tpex: { limit_up: number; up: number; flat: number; down: number; limit_down: number };
}

/** 序列一格。`t` = 台北分鐘鍵 `HHMM`(終點標記,域 0901–1330,與指數分時圖同語意)。 */
export interface BreadthPoint {
  t: string;
  twse: BreadthBuckets;
  tpex: BreadthBuckets;
}

/** `GET /api/market/breadth` 全量(恆 200 三態):
 *  `enabled=false` = FinMind 未設定 / 引擎缺席;`enabled=true` 且 `counts=null` = 載入中。 */
export interface BreadthState {
  enabled: boolean;
  trade_date: string | null;
  as_of: string | null; // HH:MM:SS
  stale: boolean;
  counts: BreadthCounts | null;
  series: BreadthPoint[];
}

// ---- 漲跌停列表(對應 breadth_engine.rows_state();market-overview R3)----

/** 列表一列(design §4 契約)。
 *
 *  `total_amount` 是**元**口徑(2026-08-06 真快照算術實證:2330@12:19 15339 張 ×
 *  均價 2375.78 × 1000 ≈ 3.644e10 == 36442215000),不是千元也不是億元。
 *
 *  `streak` 三值語意:number = **含今日**的連續漲停日數(只會出現在 `limit_up` 列)/
 *  null = 非漲停列、連板未就緒、連板停用、或 rows 資料日與連板基準日關係異常。
 *  **連板算術全在後端**(design R1):前端不做任何日期推理或 +1,拿到什麼印什麼。
 *  `streak_capped` = 該 streak 撞到後端回看窗邊緣(顯示「N+ 板」而非「連 N 板」)。 */
export interface BreadthRow {
  stock_id: string;
  name: string;
  market: "twse" | "tpex";
  close: number | null;
  change_rate: number; // 百分比(9.98 = +9.98%)
  volume_ratio: number | null;
  total_amount: number | null; // 元
  limit_up: boolean;
  limit_down: boolean;
  touched_limit_up: boolean; // 盤中觸及漲停、收盤未鎖(已鎖列為 false,不重複歸類)
  touched_limit_down: boolean;
  streak: number | null;
  streak_capped: boolean;
}

/** `GET /api/market/breadth/rows` 全量(恆 200)。
 *
 *  **載入判別子是 `as_of` 不是 `stale`**(design R18):`stale` 在冷啟動 degraded 下
 *  恆為 true,拿它判「載入中」會讓「載入中」與「有資料但延遲」兩態顛倒。
 *  `as_of` 只在首輪取數成功後才有值,才是誠實的 sentinel。
 *
 *  `trade_date` = **rows 的資料日**(與列表內容同源),與 `/api/market/breadth` 的
 *  `trade_date`(序列日)語意不同,屬設計刻意。 */
export interface BreadthRowsState {
  enabled: boolean;
  trade_date: string | null;
  as_of: string | null; // HH:MM:SS
  stale: boolean;
  streaks_ready: boolean;
  rows: BreadthRow[];
}

/** 每秒增量:各腿最後寫入的那一分鐘;該腿本場尚無 live 點 → null。 */
export interface RiverDelta {
  type: string; // "river_delta"
  seq: number;
  session: string;
  window: RiverWindow;
  legs: Record<string, { m: number; p: number } | null>;
}
