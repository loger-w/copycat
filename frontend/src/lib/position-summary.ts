/** 三處倉位顯示(自選列 chip / 單檔 header / 群組卡)的聚合與文字格式(零 React 純函式)。
 *
 *  **為什麼集中在一支 lib**:同一筆部位會同時出現在閃電梯部位列、側欄 chip、圖牆卡片
 *  與 header 上。四個地方各算一次的失效樣態不是崩潰而是「同一檔在畫面上有兩個損益」——
 *  使用者無從判斷哪個才對,而這是真錢那一側。所以:
 *
 *  - 證券損益一律走 `ladder-position::positionEcon`(含手續費 / 證交稅 / 借券費,折數
 *    來自 `fee-discount`),與現股閃電梯同一函式同一折數;
 *  - 個股期損益一律走群益回報的 `pnl_base`(名目、報告時點快照),與個股期閃電梯同一
 *    數字 —— **不自創期貨費稅口徑**(期交稅 + 每口手續費是另一套規則,算錯比不算更糟);
 *  - 缺值 / 正負號 / 千分位 / 賺紅賠綠一律走 `pnl-format`,百分比走 `format::fmtPct`。
 */
import { fmt, fmtPct } from "@/lib/format";
import { positionEcon, secPositionsOf } from "@/lib/ladder-position";
import { DASH, pnlText, pnlTone } from "@/lib/pnl-format";
import { kindLabel } from "@/lib/trade-kinds";
import type { CapitalPosition } from "@/types";

/** 無倉的 code 一律拿這一個(identity 穩定)—— 每次現做 `[]` 會讓吃它的 `memo` 元件
 *  每輪都比不過,50 張卡片照樣每秒全部重畫(同 `fill-marks::EMPTY_FILLS` 的理由)。 */
export const EMPTY_POSITIONS: readonly CapitalPosition[] = [];

/** 聚合後的證券部位(同股號、跨交易別)。 */
export interface SecSummary {
  /** 帶號張數和(多 − 空)。對鎖時是 0,顯示層另走 `secQtyText`。 */
  qty: number;
  /** 多方張數合計 */
  long: number;
  /** 空方張數合計(正數) */
  short: number;
  /** 含費稅損益合計。**嚴格制**:任一列算不出來就是 null(見 `secSummary`)。 */
  pnl: number | null;
  /** 損益 / 成本 × 100;pnl null 時 null。 */
  pct: number | null;
  kinds: SecKind[];
}

export interface SecKind {
  /** 群益原始交易別(顯示 key 用,標籤走 `label`) */
  kind: string;
  label: string;
  qty: number;
  /** 均價(元);缺值 / ≤0 → null */
  avg: number | null;
  pnl: number | null;
  pct: number | null;
}

/** 同股號的個股期部位(**逐契約不聚合**:標準與小型的契約單位差 20 倍)。 */
export interface FutSummary {
  /** 各契約 `pnl_base` 之和;任一契約缺值 → null(不當 0 加)。 */
  pnl: number | null;
  rows: FutRow[];
}

export interface FutRow {
  /** 期交所契約碼(CDFI6 / QFFI6) */
  contract: string;
  qty: number;
  avg: number | null;
  pnl: number | null;
}

/** 單檔 header 的一段(逐 kind / 逐契約)。`pnl` 給呼叫端上色,`key` 給 React ——
 *  用陣列索引當 key 的話,新開一筆排在前面的部位會讓整排段落重掛。 */
export interface HeaderSegment {
  key: string;
  text: string;
  pnl: number | null;
}

/** 均價的缺值判定與 `positionEcon` 同一條規則(0 不是價格)。 */
function px(v: number | null): number | null {
  return v !== null && v > 0 ? v : null;
}

/** 成本基準報酬率(AD-3):`pnl / (均價 × |張數| × 1000) × 100`。 */
function pctOf(pnl: number | null, cost: number | null): number | null {
  if (pnl === null || cost === null || cost <= 0) return null;
  return (pnl / cost) * 100;
}

/** 股號 → 該股號的部位列(sec 以股號為鍵;fut 以後端在 API 邊界附的 `code` 為鍵)。
 *
 *  `code` 是唯一的反查來源:前端只有「股號 + 選月 → 契約碼」的正向組法,沒有反向。
 *  `code` null(未知產品 / 除權息調整碼)的期貨列直接跳過 —— 猜一個股號會把部位掛到
 *  別檔頭上,比不顯示糟得多。`qty === 0` 的列不是部位(同 `secPositionsOf`)。 */
export function positionsByCode(
  positions: CapitalPosition[] | undefined,
): Map<string, CapitalPosition[]> {
  const map = new Map<string, CapitalPosition[]>();
  for (const p of positions ?? []) {
    if (p.qty === 0) continue;
    const key = p.market === "sec" ? p.stock_no : p.code;
    if (key === null || key === "") continue;
    const cur = map.get(key);
    if (cur === undefined) map.set(key, [p]);
    else cur.push(p);
  }
  return map;
}

/** 反查不到股號的個股期部位筆數(N065)。
 *
 *  `positionsByCode` 跳過這些列是對的 —— 猜一個股號會把部位掛到別檔頭上。但三處顯示
 *  (自選 chip / 單檔 header / 群組卡)於是**完全靜默**:使用者手上壓著一筆部位,
 *  畫面上一個字都沒有。這支只回計數,讓側欄底掛一行「n 筆個股期倉位無法對映」。
 *
 *  **不加後端欄位**:`code: string | null` 已經在 wire 上(`GET /api/capital/positions`
 *  的衍生欄),再回一個 `code_missing` 聚合數就是同一事實兩個來源、多一條會漂的跨檔契約。
 *  篩選條件與 `positionsByCode` 逐條對齊(`qty === 0` 不是部位;sec 列的 `code` 恆為股號,
 *  語意不同、不計)。 */
export function unmappedFutCount(positions: CapitalPosition[] | undefined): number {
  let n = 0;
  for (const p of positions ?? []) {
    if (p.market !== "fut" || p.qty === 0) continue;
    if (p.code === null || p.code === "") n += 1;
  }
  return n;
}

/**
 * 同股號的證券部位聚合;沒有 sec 列 → `null`(呼叫端據此決定整段渲不渲染)。
 *
 * **嚴格制**(AD-4):任一列的 pnl 算不出來(均價缺 / 現價缺),聚合 pnl 與 pct 就是
 * null。只加算得出來的那幾列會端出一個「看起來完整」的合計,而它少了一整筆部位 ——
 * 破折號至少誠實。
 */
export function secSummary(
  rows: readonly CapitalPosition[],
  lastMilli: number | null,
  discount: number,
): SecSummary | null {
  // 過濾與排序都借 `secPositionsOf`(閃電梯部位列同一支):兩處各寫一份 KIND_ORDER
  // 會靜默漂成不同順序。`rows` 依 `positionsByCode` 的建構已是同一股號。
  const code = rows.find((p) => p.market === "sec")?.stock_no;
  if (code === undefined) return null;
  const secRows = secPositionsOf([...rows], code);
  if (secRows.length === 0) return null;

  let qty = 0;
  let long = 0;
  let short = 0;
  let pnl: number | null = 0;
  let cost = 0;
  const kinds = secRows.map((p) => {
    const econ = positionEcon(p.qty, p.avg_price, lastMilli, discount, p.kind, {
      avgSource: p.avg_source,
      todayQty: p.today_qty,
    });
    const avg = px(p.avg_price);
    const rowCost = avg === null ? null : avg * Math.abs(p.qty) * 1000;
    qty += p.qty;
    if (p.qty > 0) long += p.qty;
    else short += -p.qty;
    if (econ.pnl === null || rowCost === null) pnl = null;
    else if (pnl !== null) {
      pnl += econ.pnl;
      cost += rowCost;
    }
    return {
      kind: p.kind,
      label: kindLabel(p.kind),
      qty: p.qty,
      avg,
      pnl: econ.pnl,
      pct: pctOf(econ.pnl, rowCost),
    };
  });

  return { qty, long, short, pnl, pct: pctOf(pnl, cost), kinds };
}

/** 同股號的個股期部位,依契約碼排序;沒有 fut 列 → `null`。 */
export function futSummary(rows: readonly CapitalPosition[]): FutSummary | null {
  const futRows = rows
    .filter((p) => p.market === "fut" && p.qty !== 0)
    .sort((a, b) => a.stock_no.localeCompare(b.stock_no));
  if (futRows.length === 0) return null;
  const pnl = futRows.some((p) => p.pnl_base === null)
    ? null
    : futRows.reduce((sum, p) => sum + (p.pnl_base ?? 0), 0);
  return {
    pnl,
    rows: futRows.map((p) => ({
      contract: p.stock_no,
      qty: p.qty,
      avg: px(p.avg_price),
      pnl: p.pnl_base,
    })),
  };
}

/** `3張` / `空2張` / `多2口` 這類量詞。空方以「空」字標,不用負號 —— `-2張` 在盤中
 *  一眼會被讀成「跌了 2」。 */
function lotText(qty: number, unit: string): string {
  return `${qty < 0 ? "空" : ""}${Math.abs(qty)}${unit}`;
}

/** 期貨口數的**明細**寫法:`多2口` / `空1口`。chip 上的 `期 2口` 省略「多」是因為
 *  多方是常態、側欄要省字;tooltip 與 header 兩側都寫全,那裡是拿來核對方向的。 */
function futLotText(qty: number): string {
  return `${qty < 0 ? "空" : "多"}${Math.abs(qty)}口`;
}

/** 均價顯示(同 `PriceLadder` 的 avgText):`avg_price` 是**元**,`fmt` 吃毫元。 */
function avgText(avg: number | null): string {
  return avg === null ? DASH : fmt(Math.round(avg * 1000));
}

/** `損益 +12,345 (+1.20%)`;pnl 缺 → `損益 —`,pct 缺 → 不印括號。 */
function pnlPart(pnl: number | null, pct: number | null): string {
  return `損益 ${pnlText(pnl)}${pct === null ? "" : ` (${fmtPct(pct)})`}`;
}

/** 聚合張數。**對鎖(多空相抵成 0)另印 `多3/空3張`** —— 印成 `0張` 會像「沒有部位」,
 *  而手上其實壓著兩筆、任一腿的價格都在動。 */
export function secQtyText(sec: SecSummary): string {
  if (sec.qty === 0) return `多${sec.long}/空${sec.short}張`;
  return lotText(sec.qty, "張");
}

/** `期 2口` / `期 空1口` / 多契約 `期 2口/空1口`(依契約碼排序)。 */
export function futQtyText(fut: FutSummary): string {
  return `期 ${fut.rows.map((r) => lotText(r.qty, "口")).join("/")}`;
}

/** 自選列 chip(240px 側欄,只放得下一行):`3張 +1.20%` + 有期倉再接 ` · 期 2口`。
 *  期貨段**不印百分比**:保證金制沒有成本基準,拿名目損益除一個假分母只會騙人。 */
export function chipText(sec: SecSummary | null, fut: FutSummary | null): string {
  const parts: string[] = [];
  if (sec !== null) parts.push(`${secQtyText(sec)} ${sec.pct === null ? DASH : fmtPct(sec.pct)}`);
  if (fut !== null) parts.push(futQtyText(fut));
  return parts.join(" · ");
}

/** chip 的 `title`:逐 kind / 逐契約列出明細(chip 上只有聚合值,細節靠停留看)。 */
export function chipTitle(sec: SecSummary | null, fut: FutSummary | null): string {
  const lines: string[] = [];
  for (const k of sec?.kinds ?? []) {
    lines.push(`${k.label} ${lotText(k.qty, "張")} 均價 ${avgText(k.avg)} ${pnlPart(k.pnl, k.pct)}`);
  }
  for (const r of fut?.rows ?? []) {
    // 「群益名目,報告時點」不可省:這個數字既不含期交稅也不是即時的,與上面幾行
    // 的含費稅即時損益混在同一個 tooltip 裡,不標就會被當成同一種數字看
    lines.push(`${r.contract} ${futLotText(r.qty)} 損益 ${pnlText(r.pnl)}(群益名目,報告時點)`);
  }
  return lines.join("\n");
}

/** chip / 卡片的字色。有證券倉時看證券損益(那是含費稅的真答案),否則退期貨名目損益。 */
export function chipTone(sec: SecSummary | null, fut: FutSummary | null): string {
  return pnlTone(sec !== null ? sec.pnl : (fut?.pnl ?? null));
}

/** 群組卡標題列下那一行:`現 3張 +12,345 (+1.20%) · 期 2口 +500`。
 *  卡片比側欄寬一點,放得下絕對金額 —— 圖牆上要比較的是「哪一檔在賺」。 */
export function cardText(sec: SecSummary | null, fut: FutSummary | null): string {
  const parts: string[] = [];
  if (sec !== null) {
    parts.push(
      `現 ${secQtyText(sec)} ${pnlText(sec.pnl)}${sec.pct === null ? "" : ` (${fmtPct(sec.pct)})`}`,
    );
  }
  if (fut !== null) parts.push(`${futQtyText(fut)} ${pnlText(fut.pnl)}`);
  return parts.join(" · ");
}

/** 單檔 header:**逐 kind / 逐契約各一段**(不聚合)—— header 旁邊就是右欄閃電梯的
 *  部位列,一對一才能並排核對數字。 */
export function headerSegments(
  sec: SecSummary | null,
  fut: FutSummary | null,
): HeaderSegment[] {
  const segs: HeaderSegment[] = [];
  for (const k of sec?.kinds ?? []) {
    segs.push({
      key: `sec:${k.kind}`,
      pnl: k.pnl,
      text: `${k.label} ${lotText(k.qty, "張")} · 均價 ${avgText(k.avg)} · ${pnlPart(k.pnl, k.pct)}`,
    });
  }
  for (const r of fut?.rows ?? []) {
    segs.push({
      key: `fut:${r.contract}`,
      pnl: r.pnl,
      text: `期 ${r.contract} ${r.qty < 0 ? "空" : "多"} ${Math.abs(r.qty)}口 · 均價 ${avgText(r.avg)} · 損益 ${pnlText(r.pnl)}`,
    });
  }
  return segs;
}
