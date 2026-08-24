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
  | "limit_open";

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
  // 與後端 `signal_hub._kind_text` 逐字對齊(design §7):同一則事件在 WS 列、jsonl
  // 與 Discord 上的文案漂掉時,對帳會變成人工比對。
  if (kind === "limit_lock") return sig.direction === "up" ? "鎖漲停" : "鎖跌停";
  if (kind === "limit_open") return sig.direction === "up" ? "漲停打開" : "跌停打開";
  return kind;
}

/** toast 一行文字:`代號 名稱 訊號名 價格`(名稱缺值時不留雙空格)。
 *
 *  **prod 已無讀者**(N013,2026-08-24 覆查):`useSignalAlerts` 自合併 toast(D1'')起
 *  一律走 `formatGroupToastText`。留著的唯一理由是它是那支的**參照組** ——
 *  `signal-model.test.ts` 鎖「單則組的 `formatGroupToastText` 輸出與本函式逐字相同」,
 *  刪掉等於把那條欄位口徑的 lock 一併刪掉。要刪請連同該 lock 一起想清楚。 */
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

/** 同一 tick(同 code、同 `time`)的一組訊號 —— 清單上顯示成一列(SC-5)。 */
export interface SignalGroup {
  /** 組內**最早到**那則的 id(輸入是「新在前」,即 `items` 的最後一則)。
   *
   *  **用它當 list key**:新訊號插在組首,取組首 id(或「id 串接」)當 key 時,
   *  同一列每多一則就換一次 key = 整列卸載重掛(review C-4 / T-11)。 */
  key: string;
  code: string;
  name: string;
  time: string;
  /** 組內最早到那則的價格 —— 與 Discord 合併訊息的 `rows[0]` 同一則。 */
  price: number;
  items: SignalMsg[];
}

/** kind 文案的一段 + 產生它的訊號(著色要的是**該段自己**的 tone,不是整組的)。 */
export interface KindSegment {
  label: string;
  sig: SignalMsg;
}

/** 相鄰且同 (code, time) 的訊號併成一組;輸入即輸出序(不排序、不去重)。
 *
 *  **只看相鄰**:輸入是 `mergeSignals` 的輸出(依 time 降冪、同秒維持插入序),
 *  同一秒兩檔交錯時(edge 7)跨列搜尋會把中間那檔的列吃掉 —— 顯示上寧可多一列
 *  也不要把不同標的的訊號併進同一列。 */
export function groupSignals(signals: SignalMsg[]): SignalGroup[] {
  const groups: SignalGroup[] = [];
  for (const sig of signals) {
    const last = groups.at(-1);
    if (last !== undefined && last.code === sig.code && last.time === sig.time) {
      last.items.push(sig);
      // 輸入是「新在前」→ 後接上來的反而是**更早到**的那則,錨點(key / 名稱 / 價格)
      // 跟著換成它:錨在最早到的那則,新訊號前插時 key 才不會變(review C-4 / T-11)。
      last.key = sig.id;
      last.name = sig.name;
      last.price = sig.price;
      continue;
    }
    groups.push({
      key: sig.id,
      code: sig.code,
      name: sig.name,
      time: sig.time,
      price: sig.price,
      items: [sig],
    });
  }
  return groups;
}

/** 組內 kind 文案分段(**到達序**的首見順序),**同文案只留一段**:同 kind 兩條規則
 *  在同一 tick 各發一則時文案一模一樣,印兩段只是雜訊(規則名另外列)。
 *
 *  `items` 是「新在前」,反序即到達序 —— 與 Discord 合併訊息(`rows[0]` = 最早到)
 *  同一個口徑;段序跟著到達序後,新訊號前插只會在尾端多一段,已顯示的段不重排。 */
export function groupKindLabels(group: SignalGroup): KindSegment[] {
  const seen = new Set<string>();
  const out: KindSegment[] = [];
  for (const sig of [...group.items].reverse()) {
    const label = kindLabel(sig);
    if (seen.has(label)) continue;
    seen.add(label);
    out.push({ label, sig });
  }
  return out;
}

/** 合併 toast 一行文字:`代號 名稱 <kind 段以「・」串接> 價格`。
 *
 *  與 `formatToastText` 同一套欄位口徑(單則組輸出逐字相同,signal-model.test lock)——
 *  toast 只有一行,**不含規則名**(規則名在 rail 另起一行放得下)。kind 段沿
 *  `groupKindLabels` 的到達序去重;價格取組錨(最早到那則),與 Discord 合併訊息
 *  `rows[0]` 同口徑。 */
export function formatGroupToastText(group: SignalGroup): string {
  const kinds = groupKindLabels(group)
    .map((s) => s.label)
    .join("・");
  return [group.code, group.name, kinds, fmt(group.price)].filter((x) => x !== "").join(" ");
}

/** 組內規則名去重(**到達序**的首見順序)。缺值 / 空字串 = 升級當日的舊 jsonl 行,
 *  整段略過 —— 留下來只會變成一個沒有內容的分隔符。
 *
 *  **口徑必須與 `groupKindLabels` 同為到達序**(`items` 反序):同一列上 kind 段與
 *  規則名段並排顯示,兩段順序相反時讀起來對不上號(「突破 CDP AH・爆量」配
 *  「爆量・CDP 穿越」)。 */
export function groupRuleNames(group: SignalGroup): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const sig of [...group.items].reverse()) {
    const name = sig.rule_name;
    if (name === undefined || name === "" || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}
