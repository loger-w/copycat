/** 訊號提示:toast + 桌面通知 + 短嗶(design §8.3;SC-10)。
 *
 *  掛在 App 常駐(與 tab 無關)—— 訊號涵蓋整個自選池,人在看期貨頁時個股鎖漲停
 *  一樣要跳出來。 */

import { useEffect, useMemo, useRef, useState } from "react";

import { onSignal } from "@/lib/signal-bus";
import { formatToastText, type SignalMsg } from "@/lib/signal-model";

/** 同時顯示上限(design R7):再多就疊成一片沒人讀得完,其餘走「+N」計數。 */
const VISIBLE = 4;
const TTL_MS = 5_000;
const SOUND_KEY = "copycat-signal-sound";

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

function loadSoundOn(): boolean {
  try {
    return window.localStorage.getItem(SOUND_KEY) !== "off";
  } catch {
    return true; // 預設開;storage 被鎖時偏好設定不落檔,不是關掉音效
  }
}

export function useSignalAlerts() {
  const [queue, setQueue] = useState<SignalToast[]>([]);
  const [soundOn, setSoundOnState] = useState<boolean>(loadSoundOn);

  const seqRef = useRef(0);
  const timersRef = useRef(new Map<string, number>());
  // bus 訂閱只做一次(見下方 effect),靜音狀態靠 ref 讀當下值而不是重訂閱
  const soundOnRef = useRef(soundOn);
  soundOnRef.current = soundOn;

  function drop(key: string): void {
    const timer = timersRef.current.get(key);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timersRef.current.delete(key);
    }
    setQueue((prev) => prev.filter((t) => t.key !== key));
  }

  const dropRef = useRef(drop);
  dropRef.current = drop;

  useEffect(() => {
    const off = onSignal((sig) => {
      seqRef.current += 1;
      const key = `${sig.id}#${seqRef.current}`;
      const text = formatToastText(sig);
      setQueue((prev) => [{ key, sig, text }, ...prev]);
      timersRef.current.set(
        key,
        window.setTimeout(() => dropRef.current(key), TTL_MS),
      );
      // 靜音同時關掉音效與桌面通知(design §8.3);toast 不受靜音影響
      if (!soundOnRef.current) return;
      playBeep();
      if (document.hidden) notifyDesktop(text, sig.id);
    });
    const timers = timersRef.current;
    return () => {
      off();
      for (const timer of timers.values()) window.clearTimeout(timer);
      timers.clear();
    };
  }, []);

  function setSoundOn(next: boolean): void {
    soundOnRef.current = next;
    setSoundOnState(next);
    try {
      window.localStorage.setItem(SOUND_KEY, next ? "on" : "off");
    } catch {
      // 存不進去就算了 —— 本次 session 仍照設定走
    }
  }

  const toasts = useMemo(() => queue.slice(0, VISIBLE), [queue]);
  return {
    toasts,
    overflow: Math.max(0, queue.length - VISIBLE),
    dismiss: (key: string) => dropRef.current(key),
    soundOn,
    setSoundOn,
  };
}
