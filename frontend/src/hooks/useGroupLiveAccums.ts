/** 群組卡片的 live accum(mod/group-grid-ticks T4,#185)。
 *
 *  卡片改吃逐筆:以 group-state 快照**播種**(`seq` 錨點 + `vwap × vwap_vol` 分子),之後
 *  訂閱 tick 匯流排,per-code `seq === acc.seq + 1` 才 `applyTick`;跳號(含回退:rollover /
 *  回補 +1000 / 佇列丟包)那一檔**單飛**重拉 `group-state?codes=X`(不 set_main、不動別檔),
 *  在飛期間到的 tick 進 pending、落地後只重放 `seq > snap.seq` 的 —— 沿 `useStockStream`
 *  主圖的同一套時序保護。60 s 輪詢的新快照到 → 全體重播種(快照是後端真相,live 進度以它為準)。
 *
 *  形狀 = `seeded`(由快照 useMemo 現算)+ `live`(收過 tick / 重拉過的檔的覆蓋層)。live 以
 *  「它是對哪一份 seeded 疊的」記帳,快照換了就整層作廢(render 期調整 state 的官方 pattern,
 *  不用 effect)。**一則打包 = 一次 setState**:同則多檔各套各的,合成一份 map 一次 commit。
 *
 *  只有收到 tick 的檔換 identity —— 沒動的卡拿到同一個 `StockAccum` 物件,`GroupCard` 的
 *  memo 才擋得住(50 張卡教訓)。`quotes` 只在播種當下讀一次(ref,不進 deps):每秒換 identity
 *  的報價若進 deps,整牆每秒重播種,memo 形同虛設。 */

import { useEffect, useMemo, useRef, useState } from "react";

import { fetchGroupState, type GroupSnapshot } from "@/hooks/useGroupSnapshots";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import {
  accumFromGroupSnapshot,
  applyTick,
  type StockAccum,
  type StockTickItem,
} from "@/lib/stock-accum";
import { subscribeTicks } from "@/lib/tick-stream";

/** 單檔重拉失敗後的冷卻:跳號會在**每一則**後續打包重現,不冷卻就是每 0.1 s 打一發 502。 */
const REFETCH_COOLDOWN_MS = 2_000;

type AccumMap = Record<string, StockAccum>;

interface Live {
  /** 這層覆蓋是對哪一份 seeded 疊的;不相等 = 快照已換,整層作廢 */
  base: AccumMap;
  map: AccumMap;
}

export function useGroupLiveAccums(
  codes: readonly string[],
  snapshots: Record<string, GroupSnapshot> | undefined,
  quotes: Record<string, WatchlistQuote>,
): AccumMap {
  // tick handler 是 deps `[]` 的閉包,讀的必須是「當下」的 codes / quotes / seeded / merged,
  // 而不是掛載當時那份 → 走 ref;**在 effect 同步**(不在 render 期寫 ref:doctor
  // no-ref-current-in-render)。effect 在 commit 後、任何後續 WS 事件之前跑完,handler 讀到的
  // 恆是最新一次 commit 的值;同一則打包內的連續套用另靠 `overlay` 即時回寫 mergedRef。
  const codesRef = useRef(codes);
  const quotesRef = useRef(quotes);

  // 播種:只在快照 identity / 成員變時重算。報價走 `quotesRef`(上一次 commit 的那份,最多舊
  // 一拍)而**不是** `quotes` prop 進 deps:每秒換 identity 的報價若進 deps,整牆每秒重播種、
  // memo 形同虛設。播種要的本來就是「快照換的那一刻」的現價,舊一拍不改語意。
  const csv = codes.join(",");
  const seeded = useMemo<AccumMap>(() => {
    const out: AccumMap = {};
    if (snapshots === undefined) return out;
    const liveQuotes = quotesRef.current;
    for (const code of csv.split(",")) {
      if (code === "") continue;
      const snap = snapshots[code];
      if (snap === undefined) continue;
      out[code] = accumFromGroupSnapshot(code, snap, liveQuotes[code]?.p ?? null);
    }
    return out;
  }, [snapshots, csv]);
  const seededRef = useRef(seeded);

  const [live, setLive] = useState<Live>({ base: seeded, map: {} });
  // 快照換了 → live 整層作廢:**不 setState、只在合成時忽略**(`live.base !== seeded` 就當空層)。
  // render 期 `setLive` 重設看似更乾淨,但 seeded 若每 render 換 identity(呼叫端把 snapshots
  // 現建、或 mock 回新物件)就是 setState → re-render → 再 setState 的無限迴圈;忽略法零風險,
  // 舊層留到下一則 tick 的 `overlay` 以當下的 seeded 為 base 重建。

  const merged = useMemo<AccumMap>(
    () => (live.base === seeded ? { ...seeded, ...live.map } : seeded),
    [seeded, live],
  );
  // handler 讀「最新已套用」的 accum:同一個 act 內連來兩則打包,第二則要接在第一則之後,
  // 不能等 re-render(否則第二則對舊 seq 判跳號、白打一次重拉)。
  const mergedRef = useRef(merged);
  // 四支 ref 的唯一同步點(每次 commit 後;見上方說明)
  useEffect(() => {
    codesRef.current = codes;
    quotesRef.current = quotes;
    seededRef.current = seeded;
    mergedRef.current = merged;
  });

  const refetchingRef = useRef(new Set<string>());
  const pendingRef = useRef(new Map<string, StockTickItem[]>());
  const retryAfterRef = useRef(new Map<string, number>());
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    /** 疊一批新 accum 到 live 層(同時同步 mergedRef,見上)。 */
    const overlay = (next: AccumMap): void => {
      mergedRef.current = { ...mergedRef.current, ...next };
      setLive((prev) => ({
        base: seededRef.current,
        map: prev.base === seededRef.current ? { ...prev.map, ...next } : { ...next },
      }));
    };

    const refetch = async (code: string): Promise<void> => {
      try {
        const states = await fetchGroupState(code);
        const snap = states[code];
        if (!mountedRef.current || snap === undefined || !codesRef.current.includes(code)) return;
        let acc = accumFromGroupSnapshot(code, snap, quotesRef.current[code]?.p ?? null);
        for (const item of pendingRef.current.get(code) ?? []) {
          if (item.seq > snap.seq) acc = applyTick(acc, item);
        }
        overlay({ [code]: acc });
      } catch (err) {
        // 502 / 503(TC4 斷線 / 後端還沒起)從正常操作可達:留舊 accum、冷卻後下一筆再試
        console.warn("group live: 單檔重拉失敗", code, err);
        retryAfterRef.current.set(code, Date.now() + REFETCH_COOLDOWN_MS);
      } finally {
        refetchingRef.current.delete(code);
        pendingRef.current.delete(code);
      }
    };

    const startRefetch = (code: string): boolean => {
      if (Date.now() < (retryAfterRef.current.get(code) ?? 0)) return false;
      refetchingRef.current.add(code);
      pendingRef.current.set(code, []);
      void refetch(code);
      return true;
    };

    const off = subscribeTicks((items) => {
      const allowed = new Set(codesRef.current);
      const next: AccumMap = {};
      for (const item of items) {
        if (!allowed.has(item.code)) continue;
        if (refetchingRef.current.has(item.code)) {
          pendingRef.current.get(item.code)?.push(item);
          continue;
        }
        const acc = next[item.code] ?? mergedRef.current[item.code];
        if (acc === undefined) continue; // 尚未播種(快照未到):等快照,不重拉
        if (item.seq !== acc.seq + 1) {
          if (startRefetch(item.code)) pendingRef.current.get(item.code)?.push(item);
          continue;
        }
        next[item.code] = applyTick(acc, item);
      }
      if (Object.keys(next).length > 0) overlay(next);
    });

    return () => {
      mountedRef.current = false;
      off();
    };
  }, []);

  return merged;
}
