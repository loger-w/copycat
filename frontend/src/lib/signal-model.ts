/** 訊號純函數與型別(design §7 WS 契約 / §8;SC-9/10)。
 *
 *  **欄名刻意是長名**(design R19):訊號同時是 WS 訊息、jsonl row 與歷史 API 的形狀,
 *  與 tick/quote 的短欄名分屬不同語族,不共用解析器 —— 不要為了「跟 tick 一致」而縮寫。
 *
 *  全部純函數,無 React 依賴。 */

import { fmt, fmtPct } from "@/lib/format";

export type SignalKind =
  | "cdp_cross"
  | "surge"
  | "crash"
  | "vol_burst"
  | "limit_lock"
  | "limit_open"
  /** 全市場廣度事件(market-overview R4 SC-6):來源是 FinMind 快照 diff,不是自選池的
   *  tick —— 精度 5-10s、量可達自選訊號的百倍,消費端一律先分族再處理。 */
  | "market_limit_lock"
  | "market_limit_open";

/** 全市場廣度事件的判別子。**前綴約定是唯一依據**(不是列舉):後端之後補新的廣度
 *  kind 時,前端不必同步改就能維持「不進 toast、不進自選 rail」的分族語意。 */
export function isMarketKind(kind: string): boolean {
  // **runtime guard 不是多餘的**(review round-2 FE-2):型別上 `kind` 是 string,但這份
  // 資料的來源是 jsonl 檔的一行與 WS 訊息 —— runtime 沒有任何人保證。裸 `startsWith`
  // 對非字串會拋,而呼叫點在 `useSignalFeed` 的 useMemo 內、上頭沒有 ErrorBoundary
  // → 整頁白屏,且壞行還留在檔案裡,重整也不會自癒。後端對應的 `app._is_market_kind`
  // 就是先 `isinstance(kind, str)`,兩邊同一道防禦。
  return typeof kind === "string" && kind.startsWith("market_");
}

export interface SignalMsg {
  type: "signal";
  /** 決定性鍵 `trade_date-rule_id-code-kind-(levels+ | direction | "-")-time_key`:
   *  重啟後同訊號重發時靠它去重(後端 `signal_hub._event_id`)。
   *
   *  `rule_id` 是必要的一段:同 kind 兩條規則同一 tick 各發一則,少了它兩則同 id,
   *  這裡的 `mergeSignals` 會把第二則整個吃掉。 */
  id: string;
  kind: SignalKind;
  code: string;
  /** 後端從 state.meta 取,缺 "" —— 不是 null。 */
  name: string;
  /** 毫元 int(簿路訊號無成交價時 = 漲跌停價)。 */
  price: number;
  /** 台北 HH:MM:SS(簿路訊號是伺服器時刻,非成交時刻)。 */
  time: string;
  /** cdp_cross:同 tick 穿越的全部線(後端固定序);其他 kind 空陣列。 */
  levels: string[];
  /** cdp_cross:from_below|from_above;limit_*:up|down;其他 null。 */
  direction: string | null;
  /** surge/crash 實際漲跌幅(%);vol_burst 實際倍率;其他 null。 */
  pct: number | null;
  touch_count: number;
  /** 產生這則訊號的規則(signal-rules SC-8)。**選填**:升級當日已存 jsonl 的舊行
   *  沒有這兩欄,消費端要能退回 kind 文案而不是顯示空白。 */
  rule_id?: string;
  rule_name?: string;
}

/** CDP 五線顯示名。`cdp` 顯示「中軸」而不是「CDP」—— 否則標籤變「突破 CDP CDP」。 */
const LEVEL_LABEL: Record<string, string> = {
  cdp: "中軸",
  ah: "AH",
  nh: "NH",
  nl: "NL",
  al: "AL",
};

/** 訊號中文短名(rail 列與 toast 共用同一份;兩份會漂)。
 *
 *  未知 kind 原樣回傳:後端先上線新類型時,前端寧可顯示英文代號也不要顯示空白。 */
export function kindLabel(sig: SignalMsg): string {
  const kind: string = sig.kind;
  if (kind === "cdp_cross") {
    const label = sig.levels.map((x) => LEVEL_LABEL[x] ?? x.toUpperCase()).join("+");
    const verb = sig.direction === "from_below" ? "突破" : "跌破";
    return label === "" ? `${verb} CDP` : `${verb} CDP ${label}`;
  }
  if (kind === "surge" || kind === "crash") {
    const name = kind === "surge" ? "爆拉" : "爆跌";
    // pct 缺值不印 NaN:壞行 / 舊後端的訊號寧可少一段數字也不要顯示 "爆拉 NaN%"
    return sig.pct === null ? name : `${name} ${fmtPct(sig.pct)}`;
  }
  if (kind === "vol_burst") {
    return sig.pct === null ? "爆量" : `爆量 ${sig.pct.toFixed(1)} 倍`;
  }
  if (kind === "limit_lock") return sig.direction === "up" ? "鎖漲停" : "鎖跌停";
  if (kind === "limit_open") return sig.direction === "up" ? "漲停打開" : "跌停打開";
  // 與後端 `signal_hub._kind_text` 逐字對齊(design §7):同一則事件在 WS 列、jsonl
  // 與 Discord 上的文案漂掉時,對帳會變成人工比對。
  if (kind === "market_limit_lock") return sig.direction === "up" ? "全市場鎖漲停" : "全市場鎖跌停";
  if (kind === "market_limit_open") {
    return sig.direction === "up" ? "全市場漲停打開" : "全市場跌停打開";
  }
  return kind;
}

/** toast 一行文字:`代號 名稱 訊號名 價格`(名稱缺值時不留雙空格)。 */
export function formatToastText(sig: SignalMsg): string {
  return [sig.code, sig.name, kindLabel(sig), fmt(sig.price)].filter((x) => x !== "").join(" ");
}

/** live 訊號 + 當日 baseline 合併,輸出依 `time` 降冪(新在前)。
 *
 *  **兩份輸入都是「新在前」**(呼叫端負責把 jsonl 的舊在前反轉);同 id 取 live 那筆。
 *  重啟後同訊號會重發一次(cooldown/latch 不持久,design §9),去重就是靠 id。
 *
 *  **去重後一定要重排(review CC-3)**:單純「live 全前 + baseline 後」時,WS 重連
 *  補回的訊號(baseline)會被埋在斷線前那堆較舊的 live 之下 —— 自癒有作用但畫面上
 *  完全看不出來。`time` 是台北 `HH:MM:SS` 定寬字串,字典序即時序。
 *
 *  排序是**穩定**的(ES2019 起規範保證):同秒併列維持插入相對序,亦即 live 那筆在
 *  baseline 之前。cap 在**排序之後**才套用,否則截掉的可能正是最新那幾則。 */
export function mergeSignals(
  baseline: SignalMsg[],
  live: SignalMsg[],
  cap = 200,
): SignalMsg[] {
  const seen = new Set<string>();
  const out: SignalMsg[] = [];
  for (const sig of [...live, ...baseline]) {
    if (seen.has(sig.id)) continue;
    seen.add(sig.id);
    out.push(sig);
  }
  out.sort((a, b) => (a.time === b.time ? 0 : a.time > b.time ? -1 : 1));
  return out.length > cap ? out.slice(0, cap) : out;
}
