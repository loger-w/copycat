/** 逐筆匯流排 + 檢視集合 store(mod/group-grid-ticks T3,#183)。
 *
 *  WS 只有 `useStockStream` 一條連線(App 生命週期),但逐筆的消費端有兩個:主圖(hook 自己)
 *  與群組卡片(`useGroupLiveAccums`,住在個股頁深處)。沿 `signal-bus` 的 module-level
 *  `EventTarget` 薄殼把「一條 WS」與「多個消費端」解耦,免得為了傳 tick 把 state 提到 App
 *  再逐層 props 往下穿(50 張卡的 memo 邊界會被打穿)。
 *
 *  反向也走這裡:群組檢視「正在看哪些檔」由 `setTickView` 記在 module store,`useStockStream`
 *  訂閱它把 `{"type":"view","codes"}` 送給後端(CLAUDE.md §4「view 入站訊息」契約),並在
 *  每次 onopen **重送**當下集合 —— 後端以連線為 token 登記,重連即新 token。
 *
 *  每個 `subscribe*` 回傳解除函式(唯一退訂路徑,呼叫端 effect cleanup 用)。 */

import type { StockTickItem } from "@/lib/stock-accum";

const bus = new EventTarget();

const TICKS = "copycat:ticks";
const VIEW = "copycat:tick-view";

let view: readonly string[] = [];

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((code, i) => code === b[i]);
}

function subscribe(name: string, handler: EventListener): () => void {
  bus.addEventListener(name, handler);
  return () => bus.removeEventListener(name, handler);
}

/** 目前登記的檢視集合(onopen 重送用)。 */
export function getTickView(): readonly string[] {
  return view;
}

/** 群組檢視掛載 / 換組 / 卸載時呼叫;**同序同內容不重送**(卸載請傳 `[]`,後端才除名)。
 *  主圖不必塞進來:後端恆把主圖當收件人。 */
export function setTickView(codes: readonly string[]): void {
  if (sameList(view, codes)) return;
  view = [...codes];
  bus.dispatchEvent(new CustomEvent<readonly string[]>(VIEW, { detail: view }));
}

export function subscribeTickView(cb: (codes: readonly string[]) => void): () => void {
  return subscribe(VIEW, (ev) => cb((ev as CustomEvent<readonly string[]>).detail));
}

/** `useStockStream` 把一則 `ticks` 打包中**非主圖**的 items 原序丟進來;空陣列不發。 */
export function emitTicks(items: readonly StockTickItem[]): void {
  if (items.length === 0) return;
  bus.dispatchEvent(new CustomEvent<readonly StockTickItem[]>(TICKS, { detail: items }));
}

export function subscribeTicks(cb: (items: readonly StockTickItem[]) => void): () => void {
  return subscribe(TICKS, (ev) => cb((ev as CustomEvent<readonly StockTickItem[]>).detail));
}

/** 測試用:清掉 module store 的檢視集合(listener 由各測試自己解除)。 */
export function resetTickStream(): void {
  view = [];
}
