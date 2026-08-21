/** 訊號提示:toast + 桌面通知 + 短嗶(design §8.3;SC-10)。
 *
 *  掛在 App 常駐(與 tab 無關)—— 訊號涵蓋整個自選池,人在看期貨頁時個股鎖漲停
 *  一樣要跳出來。 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getSoundOn, useSignalSound } from "@/hooks/useSignalSound";
import { onSignal } from "@/lib/signal-bus";
import { formatGroupToastText, type SignalGroup, type SignalMsg } from "@/lib/signal-model";

/** 同時顯示上限(design R7):再多就疊成一片沒人讀得完,其餘走「+N」計數。 */
const VISIBLE = 4;
const TTL_MS = 5_000;
/** 併入既有 toast 的最低 TTL 剩餘。低於它就另開新張:後到的那則若併進一張再 0.3 秒
 *  就消失的 toast,等於根本沒顯示過(spec A2;後到者最短可見 1500ms)。 */
const MERGE_MIN_REMAIN_MS = 1_500;

export interface SignalToast {
  /** React key。**不是 `sig.id`** —— 重啟後 cooldown 不持久,同 id 會重發,
   *  拿 id 當 key 會撞。同一組後續併入時**不換 key**(換 key = 整張卸載重掛閃爍)。 */
  key: string;
  /** 組內**最早到**那則(錨):文案的價格與名稱都取它,與 Discord 合併訊息 rows[0] 同口徑。 */
  sig: SignalMsg;
  /** 組內全部訊號,**新在前**(沿 `SignalGroup.items` 慣例)。 */
  items: SignalMsg[];
  text: string;
}

/** 由 toast 的 items 組出 `SignalGroup` 餵文案函式。錨(`key`/`name`/`price`)取
 *  **最早到**那則 = `items` 的最後一則(items 新在前)。 */
function toGroup(anchor: SignalMsg, items: SignalMsg[]): SignalGroup {
  return {
    key: anchor.id,
    code: anchor.code,
    name: anchor.name,
    time: anchor.time,
    price: anchor.price,
    items,
  };
}

/** Web Audio 單例。每次嗶都開新 AudioContext 會撞瀏覽器的並存數上限(Chrome 約 6 個),
 *  爆量時後面幾聲直接失敗。 */
let audioCtx: AudioContext | null = null;

/** resume 進行中旗標:autoplay 未解鎖時 resume() 會 pending 到取得手勢為止,
 *  每則訊號都排一次會累積 pending promise(review F2)—— 同時間只留一發。 */
let resuming = false;

/** 短嗶。**任何失敗都吞掉**:提示音是附加價值,自動播放政策 / 無 Web Audio /
 *  context 被系統回收都不該影響 toast 出現。 */
export function playBeep(): void {
  try {
    // 每次重讀全域:舊瀏覽器沒有 Web Audio(jsdom 也沒有)→ 靜默略過
    const Ctor = globalThis.AudioContext as typeof AudioContext | undefined;
    if (Ctor === undefined) return;
    audioCtx ??= new Ctor();
    const ctx = audioCtx;
    if (ctx.state !== "running") {
      if (ctx.state === "closed") {
        // 系統回收後 context 永不復活、resume 必 reject(review F4)——
        // 回收單例,下一則訊號重建新 context 恢復出聲。
        audioCtx = null;
        return;
      }
      // suspended 時 currentTime 凍結,排出去的 osc.stop 永不執行 → 已 start 的節點
      // 不可 GC,整天累積(handoff R4)。這一聲直接放棄,resume 讓後續訊號恢復出聲;
      // 被 autoplay / 系統拒絕就吞掉(提示音是附加價值)。
      if (!resuming) {
        resuming = true;
        ctx
          .resume()
          .catch(() => {})
          .finally(() => {
            resuming = false;
          });
      }
      return;
    }
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

/** 固定 tag:全部訊號共用一格 OS 通知,跨窗的新通知覆蓋前一則、不疊成一排;
 *  同一節流窗內至多發一則(handoff R4 / review F3)。 */
const NOTIFY_TAG = "copycat-signal";
/** 通知節流窗:固定 tag 已在 OS 層合併,節流只防通知系統 churn。 */
const NOTIFY_MIN_INTERVAL_MS = 5_000;
/** 合併窗:同一 tick 的數則(ms 級間隔)先併起來再發,OS 上只出現一則完整文案。
 *
 *  **真實背景分頁量不到 300ms**(review C1):瀏覽器對隱藏分頁的 setTimeout 有最低
 *  1s 的 clamp,而這個 timer 恰好只在 `document.hidden` 時才排 —— 實際合併窗 ≈1s。
 *  對本用途是可接受的(甚至更能把同 tick 收齊);要縮短得換 Web Worker 或
 *  `requestIdleCallback` 之類的載體,不成比例。首則通知的延遲觀感留 user 過目量測。 */
const COALESCE_MS = 300;

/** 分頁在背景時才發桌面通知 —— 前景有 toast,兩個一起跳是重複打擾。
 *  回傳「是否真的發出」供節流記帳:permission 擋掉的不該消耗窗口。 */
function notifyDesktop(text: string): boolean {
  try {
    const Ctor = globalThis.Notification as typeof Notification | undefined;
    if (Ctor === undefined || Ctor.permission !== "granted") return false;
    new Ctor(text, { tag: NOTIFY_TAG });
    return true;
  } catch {
    // 通知被瀏覽器 / 作業系統擋掉不影響其他提示
    return false;
  }
}

export function useSignalAlerts() {
  const [queue, setQueue] = useState<SignalToast[]>([]);
  // 開關的真值在 `useSignalSound`(localStorage 直讀)—— SignalRail 的切換鈕與這裡是
  // 不同元件樹的兩個訂閱者,各自 useState 會漂(關掉後這裡照嗶)
  const { soundOn, setSoundOn } = useSignalSound();

  const seqRef = useRef(0);
  const timersRef = useRef(new Map<string, number>());
  /** 上次真的發出桌面通知的時刻;hook 常駐 App 單掛載,ref 即全域節流狀態。 */
  const lastNotifyRef = useRef(-Infinity);
  /** 合併真值:`code|time` → 目前承接該組的 toast。**放 ref 不放 state** ——
   *  `setQueue` 的 updater 必須是純函式(StrictMode 會 double-invoke),累加 items
   *  這種副作用得在 updater 之外先算完。
   *
   *  `expiresAt` 是**牆鐘**(`Date.now() + TTL_MS`),真正讓 toast 消失的卻是
   *  `setTimeout`(單調時鐘)—— 兩把尺(review C4)。NTP 回跳時「TTL 剩餘」會被高估
   *  幾秒,後果僅止於該組多併一則進去(舊那張仍照原時間消失,合併分支不重排 timer)。
   *  取捨與 `lastNotifyRef` 同一套:改用 `performance.now()` 得把 fake timer 之外
   *  再假造一支時鐘,測試成本不成比例。 */
  const groupIndexRef = useRef(
    new Map<string, { key: string; items: SignalMsg[]; expiresAt: number }>(),
  );
  /** 待發桌面通知的文案(**全域單槽**:固定 tag 本來就只有一格,後到者覆寫)。 */
  const pendingRef = useRef<string | null>(null);
  const notifyTimerRef = useRef<number | undefined>(undefined);

  /** deps **必須恆為 `[]`**:函式體只碰 ref 與 `setQueue`(兩者恆定),而下面的
   *  bus 訂閱 effect 以它為 dep —— 只要 `drop` 換身分,effect 就會重跑並在 cleanup 清光
   *  還在倒數的 TTL timer。 */
  const drop = useCallback((key: string): void => {
    const timer = timersRef.current.get(key);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timersRef.current.delete(key);
    }
    // A3 stale drop 守衛:同鍵可能已經另開新張(TTL 剩餘不足時),舊張的 TTL 到期
    // **不得**把新張的索引刪掉 —— 反查 `entry.key === key` 才刪,等價於「先取該 toast
    // 的 groupKey 再比對」,但不必額外維護一張 toastKey → groupKey 表。
    for (const [groupKey, entry] of groupIndexRef.current) {
      if (entry.key === key) {
        groupIndexRef.current.delete(groupKey);
        break;
      }
    }
    setQueue((prev) => prev.filter((t) => t.key !== key));
  }, []);

  useEffect(() => {
    /** 合併窗尾:把單槽裡的最後一則推到 OS。 */
    const fire = (): void => {
      notifyTimerRef.current = undefined;
      const text = pendingRef.current;
      pendingRef.current = null;
      if (text === null) return;
      // 排程時是背景、到期時人已回到前景 → 丟棄且**不記帳**(前景有 toast,
      // 再跳一則 OS 通知是重複打擾;spec Edge 4a)。
      if (!document.hidden) return;
      // 牆鐘記帳:NTP 回跳只會讓通知靜默多擋跳幅秒數,一次性可接受;
      // 換 performance.now 的測試成本不成比例(review F5 rejected)。
      if (notifyDesktop(text)) lastNotifyRef.current = Date.now();
    };

    const off = onSignal((sig) => {
      const now = Date.now();
      const index = groupIndexRef.current;
      const groupKey = `${sig.code}|${sig.time}`;
      const entry = index.get(groupKey);
      let text: string;

      // 合併條件(spec D1''):同鍵那張還在,且 TTL 剩餘夠久值得併進去。
      // 條件只寫一次 —— 拆成 `const merge = …` 再 `if (entry !== undefined && merge)`
      // 時,兩處都得跟著改才不會漂,而後者的 `entry !== undefined` 只是為了讓
      // TypeScript 收斂型別、讀起來像是又多一個條件(review C8)。
      if (entry !== undefined && entry.expiresAt - now >= MERGE_MIN_REMAIN_MS) {
        const items = [sig, ...entry.items];
        const anchor = items.at(-1) ?? sig;
        const toastKey = entry.key;
        entry.items = items;
        text = formatGroupToastText(toGroup(anchor, items));
        // 純 reorder:key / TTL 不變(D3),但被擠進 overflow 的那張要浮回可見區,
        // 否則新到的那則等於沒顯示。
        setQueue((prev) => {
          const hit = prev.find((t) => t.key === toastKey);
          if (hit === undefined) return prev;
          return [{ ...hit, items, text }, ...prev.filter((t) => t.key !== toastKey)];
        });
      } else {
        seqRef.current += 1;
        const key = `${sig.id}#${seqRef.current}`;
        const items = [sig];
        text = formatGroupToastText(toGroup(sig, items));
        index.set(groupKey, { key, items, expiresAt: now + TTL_MS });
        setQueue((prev) => [{ key, sig, items, text }, ...prev]);
        timersRef.current.set(
          key,
          window.setTimeout(() => drop(key), TTL_MS),
        );
        // 靜音只關音效。bus 訂閱只做一次(deps 恆定),故讀當下值而不是閉包捕捉的
        // soundOn。**每新組一聲**(D4):併入既有那張不再嗶,同 tick 三則只響一次。
        if (getSoundOn()) playBeep();
      }

      // 分頁在背景就發桌面通知,**不受靜音影響**(review MFS-1):靜音的語意是
      // 「不要出聲」不是「不要通知」(design §8.3 / SC-10)—— 人離開分頁時桌面通知
      // 是唯一的抵達路徑,被音效開關順帶關掉等於整條提示鏈斷掉。
      if (document.hidden) {
        // trailing(latest-wins):窗內只留最後一則的合併文案,窗尾才推出去。
        // leading 會把「還沒併完的首則」送進 OS,而固定 tag 在 5s 節流內無法更新 ——
        // 人看到的永遠是最舊那則。排程時刻同時吃合併窗與節流窗:兩者取晚的那個。
        pendingRef.current = text;
        if (notifyTimerRef.current === undefined) {
          const at = Math.max(now + COALESCE_MS, lastNotifyRef.current + NOTIFY_MIN_INTERVAL_MS);
          notifyTimerRef.current = window.setTimeout(fire, at - now);
        }
      }
    });
    const timers = timersRef.current;
    const index = groupIndexRef.current;
    // 清 timer / index / pending,**刻意不清 `queue`**(review C5):deps 恆定 →
    // 這個 effect 一輩子只掛一次,cleanup 只在真的卸載(整個 App 收掉)或 StrictMode
    // 的模擬重掛時跑。前者清了也沒人看,後者清掉反而會把重掛前那一瞬收到的 toast
    // 洗掉。清 timer / index 是必要的(它們會外溢到重掛後的那條命)。
    return () => {
      off();
      for (const timer of timers.values()) window.clearTimeout(timer);
      timers.clear();
      index.clear();
      if (notifyTimerRef.current !== undefined) window.clearTimeout(notifyTimerRef.current);
      notifyTimerRef.current = undefined;
      pendingRef.current = null;
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
