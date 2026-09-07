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
  | "surge_pullback"
  | "vol_burst"
  | "limit_lock"
  | "limit_open"
  | "sweep_cluster"
  | "policy";

/** 四條影子政策的標記(spec #192;後端 `signal_policy.POLICIES` 同字面)。 */
export type PolicyTag = "P" | "B-a" | "B-b" | "S";

/** 政策列的族群同伴快照一筆(後端 `_emit_policies` 的 `peers[]`)。 */
export interface PeerSnap {
  code: string;
  name: string;
  chg_pct: number | null;
  touched_upper: boolean | null;
  locked_up: boolean | null;
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
  /** surge/crash 實際漲跌幅(%);vol_burst 實際倍率;surge_pullback 自峰值回落幅度(正);
   *  其他 null。 */
  pct: number | null;
  touch_count: number;
  /** 產生這則訊號的規則(signal-rules SC-8)。**選填**:升級當日已存 jsonl 的舊行
   *  沒有這兩欄,消費端要能退回 kind 文案而不是顯示空白。 */
  rule_id?: string;
  rule_name?: string;
  /** spec #192:「通知」閘(Discord + 瀏覽器 toast / 嗶 / 桌面通知)。一般列 = 規則通知開關;
   *  政策列 = 當日首筆且 ≤ 12:30。**缺欄視為 true**(舊後端 / 舊 jsonl 列)—— 判定走
   *  `shouldNotify`,不要直接比 `=== false` 以外的形。jsonl / WS / rail 不受它影響。 */
  notify?: boolean;
  /** 掃單簇列的參數 {n30, levels, qty, up_pct}(其他 kind 沒有這欄)。**wire 存證、前端不讀**。 */
  detail?: Record<string, number>;
  // ---- 以下只有 kind === "policy" 的列才有(後端 `signal_hub._emit_policies`)----
  // `sweep` / `screen_member` / `peer_max` / `t1_*` / `t2_*` 與上面的 `detail` 一樣是 **wire 存證欄、
  // 前端不讀**(review F-19):只是把後端形狀抄過來對齊型別,讀者是 jsonl 對帳;缺了不是漏功能。
  policy?: PolicyTag;
  first_of_day?: boolean;
  late?: boolean;
  tod?: string;
  sweep?: { n30: number; levels: number; qty: number; up_pct: number };
  self?: {
    chg_pct: number | null;
    to_limit_pct: number | null;
    touched_upper: boolean;
    locked_up: boolean;
  };
  groups?: string[];
  screen_member?: boolean;
  peers?: PeerSnap[];
  peers_up?: number;
  peer_max?: { code: string; name: string; chg_pct: number } | null;
  leader?: boolean;
  peer_touched?: boolean;
  t1_open?: number | null;
  t1_date?: string | null;
  t2_open?: number | null;
  t2_date?: string | null;
}

/** 通知閘:`notify === false` 才靜音;true / 缺欄一律提示(CLAUDE.md §4 契約:缺欄 = true)。 */
export function shouldNotify(sig: SignalMsg): boolean {
  return sig.notify !== false;
}

export function isPolicy(sig: SignalMsg): boolean {
  return sig.kind === "policy";
}

/** 掃單簇文案(raw 掃單簇列與政策列共用:政策列的 `pct` 就是 60 s 漲幅);pct 缺值只印名。 */
function sweepLabel(pct: number | null): string {
  return pct === null ? "掃單簇" : `掃單簇 ${fmtPct(pct)}`;
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
  if (kind === "surge_pullback") {
    // pct = 自峰值回落幅度(正數);與後端 `signal_hub._kind_text` 逐字對齊(design §7)
    return sig.pct === null ? "爆拉回檔" : `爆拉回檔 ${sig.pct.toFixed(2)}%`;
  }
  if (kind === "vol_burst") {
    return sig.pct === null ? "爆量" : `爆量 ${sig.pct.toFixed(1)} 倍`;
  }
  // spec #192:與後端 `_kind_text` 逐字對齊(「掃單簇 +0.80%」/「政策 P」)
  if (kind === "sweep_cluster") return sweepLabel(sig.pct);
  if (kind === "policy") return sig.policy === undefined ? "政策" : `政策 ${sig.policy}`;
  // 與後端 `signal_hub._kind_text` 逐字對齊(design §7):同一則事件在 WS 列、jsonl
  // 與 Discord 上的文案漂掉時,對帳會變成人工比對。
  if (kind === "limit_lock") return sig.direction === "up" ? "鎖漲停" : "鎖跌停";
  if (kind === "limit_open") return sig.direction === "up" ? "漲停打開" : "跌停打開";
  return kind;
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

/** 組內訊號的**到達序**(`items` 是「新在前」→ 反序)。四個 group* 函式共用同一把尺:
 *  段序 / 標記序 / 規則名序都是到達序,與 Discord 合併訊息 `rows[0]` = 最早到同口徑。 */
function arrivalOrder(group: SignalGroup): SignalMsg[] {
  return [...group.items].reverse();
}

/** 列 / toast 上的 kind 段文案:政策列顯示為**掃單簇文案**(標記另走 chip / 【】前綴),
 *  所以同 tick 的 raw 掃單簇列與政策列會去重成一段;其餘 kind = `kindLabel`。
 *  `kindLabel(policy)` 本身仍是「政策 P」(後端文案表的對齊項,單則路徑用)。 */
function displayLabel(sig: SignalMsg): string {
  return isPolicy(sig) ? sweepLabel(sig.pct) : kindLabel(sig);
}

/** 組內 kind 文案分段(**到達序**的首見順序),**同文案只留一段**:同 kind 兩條規則
 *  在同一 tick 各發一則時文案一模一樣,印兩段只是雜訊(規則名另外列)。
 *
 *  `items` 是「新在前」,反序即到達序 —— 與 Discord 合併訊息(`rows[0]` = 最早到)
 *  同一個口徑;段序跟著到達序後,新訊號前插只會在尾端多一段,已顯示的段不重排。 */
export function groupKindLabels(group: SignalGroup): KindSegment[] {
  const seen = new Set<string>();
  const out: KindSegment[] = [];
  for (const sig of arrivalOrder(group)) {
    const label = displayLabel(sig);
    if (seen.has(label)) continue;
    seen.add(label);
    out.push({ label, sig });
  }
  return out;
}

/** 組內政策標記(到達序去重;非政策列不算)。Discord 卡「【P・B-a】」與 toast / rail chip 同源。 */
export function groupPolicyTags(group: SignalGroup): PolicyTag[] {
  const seen = new Set<PolicyTag>();
  const out: PolicyTag[] = [];
  for (const sig of arrivalOrder(group)) {
    const tag = sig.policy;
    if (!isPolicy(sig) || tag === undefined || seen.has(tag)) continue;
    seen.add(tag);
    out.push(tag);
  }
  return out;
}

/** 組內**最早到**的政策列(脈絡欄位的來源;同 tick 各政策列脈絡相同,只有標記不同)。 */
export function groupPolicyAnchor(group: SignalGroup): SignalMsg | undefined {
  return arrivalOrder(group).find(isPolicy);
}

function pct1(v: number | null | undefined, signed: boolean): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "-";
  return signed ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : `${v.toFixed(1)}%`;
}

/** 「同伴≥3% n・鎖過 有/無」—— rail 第三行與 hover 全文共用同一份(review F-17);缺欄(舊後端)
 *  印 `-`。3% 是拍板門檻的字面,列上不帶門檻,門檻解凍時只改這一處。 */
function peerPhrase(sig: SignalMsg): string {
  const up = sig.peers_up === undefined ? "-" : String(sig.peers_up);
  const touched = sig.peer_touched === undefined ? "-" : sig.peer_touched ? "有" : "無";
  return `同伴≥3% ${up}・鎖過 ${touched}`;
}

/** rail 政策列第三行:「同伴≥3% n・鎖過 有/無・+x.x%/停 y.y%」(spec #192 字面)。缺欄(舊後端)
 *  印 `-`,不印 NaN / undefined。 */
export function policyContextText(sig: SignalMsg): string {
  const chg = pct1(sig.self?.chg_pct, true);
  const limit = pct1(sig.self?.to_limit_pct, false);
  return `${peerPhrase(sig)}・${chg}/停 ${limit}`;
}

/** rail 政策列 hover 全文(Discord 四行卡的同一組資訊攤平成一行)。 */
export function policyTitle(sig: SignalMsg, tags: readonly PolicyTag[]): string {
  const groups = sig.groups ?? [];
  const peers = (sig.peers ?? []).map(
    (p) => `${p.code}${p.name} ${p.chg_pct === null ? "-" : pct1(p.chg_pct, true)}`,
  );
  const chg = sig.self?.chg_pct;
  const chgText =
    chg === null || chg === undefined ? "-" : `${fmtPct(chg)}${sig.leader ? "(族群最強)" : ""}`;
  const limit = sig.self?.to_limit_pct;
  const limitText = limit === null || limit === undefined ? "-" : `${limit.toFixed(2)}%`;
  const when = [sig.tod, sig.first_of_day ? "首筆" : sig.first_of_day === false ? "非首筆" : "", sig.late ? "late" : ""]
    .filter((x) => x !== undefined && x !== "")
    .join("・");
  return [
    `政策 ${tags.join("・")}`,
    groups.length > 0 ? `族群 ${groups.join("、")}` : "盤前篩選名單・無族群濾網",
    peers.length > 0 ? `同伴 ${peers.join("、")}` : "",
    peerPhrase(sig),
    `較前收 ${chgText}・距漲停 ${limitText}`,
    when,
  ]
    .filter((x) => x !== "")
    .join("｜");
}

/** 合併 toast 一行文字:`代號 名稱 <kind 段以「・」串接> 價格`。
 *
 *  欄位口徑沿逐則 toast 舊函式 `formatToastText`(2026-08-31 刪,prod 零讀者;N013):
 *  單則組輸出 = `代號 名稱 訊號名 價格`,由 signal-model.test / useSignalAlerts.test 的
 *  **字面量**釘住,不再有參照組函式 —— toast 只有一行,**不含規則名**(規則名在 rail
 *  另起一行放得下)。kind 段沿 `groupKindLabels` 的到達序去重;價格取組錨(最早到那則),
 *  與 Discord 合併訊息 `rows[0]` 同口徑。 */
export function formatGroupToastText(group: SignalGroup): string {
  const kinds = groupKindLabels(group)
    .map((s) => s.label)
    .join("・");
  const tags = groupPolicyTags(group);
  const body = [group.code, group.name, kinds, fmt(group.price)].filter((x) => x !== "").join(" ");
  // 政策組帶標記前綴(spec #192):「【P】代號 名稱 掃單簇 +0.5% 價」;在別的 tab 也分得出政策
  return tags.length === 0 ? body : `【${tags.join("・")}】${body}`;
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
  for (const sig of arrivalOrder(group)) {
    const name = sig.rule_name;
    if (name === undefined || name === "" || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}
