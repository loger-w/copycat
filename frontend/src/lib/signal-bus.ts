/** 訊號事件匯流排(design §8.1;SC-9/10/11)。
 *
 *  module-level `EventTarget` 薄殼:WS 只有 `useStockStream` 一條連線(App 生命週期),
 *  但訊號的消費端散在各處(ToastStack 在 App 常駐、SignalRail 在個股頁、feed hook),
 *  且 toast 必須**跨 tab** 出現 —— 用 bus 把「一條 WS」與「多個消費端」解耦,免得為了
 *  傳訊號而把 state 提到 App 再逐層 props 往下穿。
 *
 *  兩個事件互不共用型別;每個 `on*` 回傳解除函式(唯一退訂路徑,呼叫端 effect cleanup 用)。 */

import type { SignalMsg } from "@/lib/signal-model";

const bus = new EventTarget();

const SIGNAL = "copycat:signal";
const WS_OPEN = "copycat:ws-open";

function subscribe(name: string, handler: EventListener): () => void {
  bus.addEventListener(name, handler);
  return () => bus.removeEventListener(name, handler);
}

export function emitSignal(sig: SignalMsg): void {
  bus.dispatchEvent(new CustomEvent<SignalMsg>(SIGNAL, { detail: sig }));
}

export function onSignal(cb: (sig: SignalMsg) => void): () => void {
  return subscribe(SIGNAL, (ev) => cb((ev as CustomEvent<SignalMsg>).detail));
}

/** WS(重)連線成功。斷線期間 WS 丟掉的訊號要靠 feed 重抓當日 jsonl 補回(自癒)。 */
export function emitWsOpen(): void {
  bus.dispatchEvent(new Event(WS_OPEN));
}

export function onWsOpen(cb: () => void): () => void {
  return subscribe(WS_OPEN, () => cb());
}
