/** 江波圖資料流:`GET /api/river/state` 全量 + `/ws/river` 每秒 delta(design v2 §5)。
 *
 * 與 `useCorrelation` 的關鍵差異:corr 每秒推**全量快照**,river 不能 —— 滿窗夜盤 840 分鐘
 * × 6 腿 ≈ 5,000 個數字(60–80 KB),每秒推等於每分鐘 4.8 MB。所以這裡是
 * 「全量取一次 + 每秒增量」,合併規則兩種訊息各自不同:
 *
 * | 訊息 | 合併 | seq |
 * |---|---|---|
 * | `river`(REST 初載 / WS 首則) | **union**:既有 offset 不覆蓋,只補缺的 | 取 max,不因較舊而丟棄 |
 * | `river_delta`(每秒) | 各腿當前分鐘寫入 | `seq < 已見` → 丟棄該則 |
 *
 * snapshot 走 union 而非覆蓋,是因為 REST 回應可能比已收到的 delta 舊 —— 若照 delta 的
 * seq 規則整份丟掉,1K 回補的歷史分鐘永遠進不了畫面(design review P1-1)。
 */
import { useEffect, useRef, useState } from "react";

import { connectWithRetry } from "@/lib/ws-reconnect";
import type { RiverDelta, RiverLeg, RiverState } from "@/types";

export type WsStatus = "connecting" | "open" | "closed";

export interface RiverStreamState {
  state: RiverState | null;
  wsStatus: WsStatus;
}

/** union 合併:既有 offset 優先(較新的 delta 不被較舊的 snapshot 蓋掉)。 */
function mergeLeg(prev: RiverLeg | undefined, next: RiverLeg): RiverLeg {
  if (prev === undefined) return next;
  const minutes = { ...next.minutes, ...prev.minutes };
  return { ...next, minutes, ...lastOf(minutes) };
}

function lastOf(minutes: Record<string, number>): {
  last: number | null;
  last_minute: number | null;
} {
  const offsets = Object.keys(minutes).map(Number);
  if (offsets.length === 0) return { last: null, last_minute: null };
  const last_minute = Math.max(...offsets);
  return { last: minutes[String(last_minute)] ?? null, last_minute };
}

function mergeSnapshot(prev: RiverState | null, next: RiverState): RiverState {
  if (prev === null || prev.session !== next.session) return next;
  const legs: Record<string, RiverLeg> = {};
  for (const [key, leg] of Object.entries(next.legs)) {
    legs[key] = mergeLeg(prev.legs[key], leg);
  }
  return { ...next, seq: Math.max(prev.seq, next.seq), legs };
}

function applyDelta(prev: RiverState, msg: RiverDelta): RiverState {
  const legs: Record<string, RiverLeg> = {};
  for (const [key, leg] of Object.entries(prev.legs)) {
    const point = msg.legs[key];
    if (point == null) {
      legs[key] = leg;
      continue;
    }
    const minutes = { ...leg.minutes, [String(point.m)]: point.p };
    legs[key] = { ...leg, minutes, ...lastOf(minutes) };
  }
  return { ...prev, seq: msg.seq, legs };
}

/** 盤別換場:清空各腿分鐘、換窗(舊場的點與新場 x 軸無關)。 */
function resetForSession(prev: RiverState, msg: RiverDelta): RiverState {
  const legs: Record<string, RiverLeg> = {};
  for (const [key, leg] of Object.entries(prev.legs)) {
    legs[key] = { ...leg, minutes: {}, last: null, last_minute: null };
  }
  return { ...prev, session: msg.session, window: msg.window, seq: msg.seq, legs };
}

export function useRiver(): RiverStreamState {
  const [state, setState] = useState<RiverState | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const seqRef = useRef<number>(-1);
  /** 目前已知的盤別;`null` = 還沒有任何 snapshot。換場判定讀它而不是讀 `state` ——
   *  判定的後果是 `load()`(REST 副作用),不能放在 `setState` 的 updater 內:updater
   *  契約是純函式,而全站包在 StrictMode(main.tsx)下 dev 會 double-invoke,一次換場
   *  打兩份全量快照(滿窗夜盤 60–80 KB)。先例:`useStockStream.ts` 的 statusRef(F-1)。 */
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    // `alive` 只剩 `load()` 的在途守門(WS 重連守門已移進 helper 的 `stopped`)
    let alive = true;

    const applySnapshot = (next: RiverState): void => {
      // 直接採用 snapshot 的 seq(不取 max):snapshot 一律反映 server 當下狀態,
      // 而 server 重啟後 river_seq 從 0 起算 —— 取 max 會讓之後每一則 delta 都被當舊訊息
      // 丟掉,畫面凍在 snapshot 那一刻直到 seq 追上舊值(Phase 4 自評 finding)。
      // 資料不會因此倒退:snapshot 走 union 合併,舊值蓋不掉新值。
      seqRef.current = next.seq;
      sessionRef.current = next.session;
      setState((prev) => mergeSnapshot(prev, next));
    };

    const load = async (): Promise<void> => {
      try {
        const res = await fetch("/api/river/state");
        if (!res.ok) return; // 503 = 引擎未就緒,等推播或下次重連
        const snap = (await res.json()) as RiverState;
        if (alive) applySnapshot(snap);
      } catch (err) {
        // 初次載入失敗不致命 —— WS 首則就是全量 snapshot
        console.warn("river: state 載入失敗", err);
      }
    };

    void load();

    // 順序固定,三段各自有理由:
    // 1. seq 守衛先行 —— 舊 seq 的跨場 delta 整則丟掉,不觸發 load、不動 sessionRef
    //    (與舊版等價:舊版的 updater 也看不到它)。
    // 2. 換場判定與 `load()`(副作用)在 setState **之前**,ref 同步更新使同一場的
    //    後續 delta 不再重複觸發回補。
    // 3. updater 純函式:清空換窗仍以 `prev.session` 判定(state 才是畫面真相,
    //    ref 只負責副作用的去重)。
    const onDelta = (msg: RiverDelta): void => {
      if (msg.seq < seqRef.current) return;
      seqRef.current = msg.seq;
      if (sessionRef.current !== null && sessionRef.current !== msg.session) {
        sessionRef.current = msg.session;
        void load(); // 換場:先本地清空換窗,再補抓新場的回補資料
      }
      setState((prev) => {
        if (prev === null) return prev; // 還沒有 snapshot,delta 無處可併
        if (prev.session !== msg.session) return applyDelta(resetForSession(prev, msg), msg);
        return applyDelta(prev, msg);
      });
    };

    const conn = connectWithRetry(
      () => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/ws/river`;
      },
      {
        onConnecting: () => setWsStatus("connecting"),
        onOpen: () => setWsStatus("open"),
        onMessage: (raw) => {
          const msg = raw as RiverState | RiverDelta;
          if (msg.type === "river") applySnapshot(msg as RiverState);
          else if (msg.type === "river_delta") onDelta(msg as RiverDelta);
        },
        onClose: () => setWsStatus("closed"),
      },
      { label: "river ws" },
    );

    return () => {
      alive = false;
      conn.close();
    };
  }, []);

  return { state, wsStatus };
}
