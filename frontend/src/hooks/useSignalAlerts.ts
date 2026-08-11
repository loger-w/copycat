/** 訊號提示:toast + 桌面通知 + 短嗶(design §8.3;SC-10)。
 *
 *  掛在 App 常駐(與 tab 無關)—— 訊號涵蓋整個自選池,人在看期貨頁時個股鎖漲停
 *  一樣要跳出來。 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getSoundOn, useSignalSound } from "@/hooks/useSignalSound";
import { onSignal } from "@/lib/signal-bus";
import { formatToastText, isMarketKind, type SignalMsg } from "@/lib/signal-model";

/** 同時顯示上限(design R7):再多就疊成一片沒人讀得完,其餘走「+N」計數。 */
const VISIBLE = 4;
const TTL_MS = 5_000;

export interface SignalToast {
  /** React key。**不是 `sig.id`** —— 重啟後 cooldown 不持久,同 id 會重發,
   *  拿 id 當 key 會撞。 */
  key: string;
  sig: SignalMsg;
  text: string;
}

/** Web Audio 單例。每次嗶都開新 AudioContext 會撞瀏覽器的並存數上限(Chrome 約 6 個),
 *  爆量時後面幾聲直接失敗。 */
let audioCtx: AudioContext | null = null;

/** 短嗶。**任何失敗都吞掉**:提示音是附加價值,自動播放政策 / 無 Web Audio /
 *  context 被系統回收都不該影響 toast 出現。 */
export function playBeep(): void {
  try {
    // 每次重讀全域:舊瀏覽器沒有 Web Audio(jsdom 也沒有)→ 靜默略過
    const Ctor = globalThis.AudioContext as typeof AudioContext | undefined;
    if (Ctor === undefined) return;
    audioCtx ??= new Ctor();
    const ctx = audioCtx;
    if (ctx.state === "suspended") void ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.04; // 看盤整天都在響,音量要低
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
  } catch {
    // 出不了聲就算了
  }
}

/** 分頁在背景時才發桌面通知 —— 前景有 toast,兩個一起跳是重複打擾。 */
function notifyDesktop(text: string, tag: string): void {
  try {
    const Ctor = globalThis.Notification as typeof Notification | undefined;
    if (Ctor === undefined || Ctor.permission !== "granted") return;
    new Ctor(text, { tag }); // tag:同一則訊號重發時系統自行取代,不疊成一排
  } catch {
    // 通知被瀏覽器 / 作業系統擋掉不影響其他提示
  }
}

export function useSignalAlerts() {
  const [queue, setQueue] = useState<SignalToast[]>([]);
  // 開關的真值在 `useSignalSound`(localStorage 直讀)—— SignalRail 的切換鈕與這裡是
  // 不同元件樹的兩個訂閱者,各自 useState 會漂(關掉後這裡照嗶)
  const { soundOn, setSoundOn } = useSignalSound();

  const seqRef = useRef(0);
  const timersRef = useRef(new Map<string, number>());

  /** deps **必須恆為 `[]`**:函式體只碰 `timersRef` 與 `setQueue`(兩者恆定),而下面的
   *  bus 訂閱 effect 以它為 dep —— 只要 `drop` 換身分,effect 就會重跑並在 cleanup 清光
   *  還在倒數的 TTL timer。 */
  const drop = useCallback((key: string): void => {
    const timer = timersRef.current.get(key);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timersRef.current.delete(key);
    }
    setQueue((prev) => prev.filter((t) => t.key !== key));
  }, []);

  useEffect(() => {
    const off = onSignal((sig) => {
      // 全市場廣度事件不打擾(market-overview R4 SC-8):它是看盤背景資訊,不是自選池的
      // 提醒 —— 漲停潮日一分鐘上百則,toast 會蓋滿畫面、嗶聲會連成一片,連帶把真正該
      // 注意的自選訊號淹掉。要看這些事件請去綜合 tab 的訊號時間軸。
      if (isMarketKind(sig.kind)) return;
      seqRef.current += 1;
      const key = `${sig.id}#${seqRef.current}`;
      const text = formatToastText(sig);
      setQueue((prev) => [{ key, sig, text }, ...prev]);
      timersRef.current.set(
        key,
        window.setTimeout(() => drop(key), TTL_MS),
      );
      // 分頁在背景就發桌面通知,**不受靜音影響**(review MFS-1):靜音的語意是
      // 「不要出聲」不是「不要通知」(design §8.3 / SC-10)—— 人離開分頁時桌面通知
      // 是唯一的抵達路徑,被音效開關順帶關掉等於整條提示鏈斷掉。
      if (document.hidden) notifyDesktop(text, sig.id);
      // 靜音只關音效。bus 訂閱只做一次(deps 恆定),故讀當下值而不是閉包捕捉的 soundOn
      if (getSoundOn()) playBeep();
    });
    const timers = timersRef.current;
    return () => {
      off();
      for (const timer of timers.values()) window.clearTimeout(timer);
      timers.clear();
    };
  }, [drop]);

  const toasts = useMemo(() => queue.slice(0, VISIBLE), [queue]);
  return {
    toasts,
    overflow: Math.max(0, queue.length - VISIBLE),
    dismiss: drop,
    soundOn,
    setSoundOn,
  };
}
