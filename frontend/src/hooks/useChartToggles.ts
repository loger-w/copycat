import { useState } from "react";

const KEY = "copycat-chart-toggles";

export interface ChartToggles {
  vwap: boolean;
  cdp: boolean;
  ma: boolean;
  /** 布林通道(K 線專用) */
  bb: boolean;
}

/** 存檔 schema 版本。**storage-only,不屬 `ChartToggles`** —— 洩進 toggles 物件會讓
 *  「整包比對」的測試與 memo 比較多一個非布林欄位。 */
const TOGGLES_VERSION = 2;

/** `cdp` 預設開(SC-3,user 拍板);`bb` 預設開(round4 項 6,user 拍板)。
 *
 *  `load()` 的 `{...DEFAULTS, ...saved}` 讓存檔覆蓋預設 —— 對「使用者選過」的項目是
 *  對的,但對**新改的預設**是錯的:舊存檔裡的 `bb: false` 是「當時的預設」而不是
 *  「使用者選了關」,照樣覆蓋的話 user 的畫面永遠不會變成新預設。
 *  故只對 `bb` 做一次性升級(見 `load`),其餘欄位維持「存檔優先、不強制升級」。 */
const DEFAULTS: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true };

interface Stored extends Partial<ChartToggles> {
  v?: number;
}

function persist(toggles: ChartToggles): void {
  window.localStorage.setItem(KEY, JSON.stringify({ ...toggles, v: TOGGLES_VERSION }));
}

function load(): ChartToggles {
  let saved: Stored;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    saved = JSON.parse(raw) as Stored;
  } catch {
    return DEFAULTS;
  }
  const { v, ...flags } = saved;
  const merged: ChartToggles = { ...DEFAULTS, ...flags };
  if ((v ?? 1) < TOGGLES_VERSION) {
    // 一次性升級。**必須立刻落檔**:只回傳不寫回的話,使用者升級後把 BB 關掉,
    // 下次 load 又看到 v<2 而再打開一次 —— 變成「關不掉」(白名單 W-11)。
    const upgraded: ChartToggles = { ...merged, bb: true };
    persist(upgraded);
    return upgraded;
  }
  return merged;
}

export function useChartToggles() {
  const [toggles, setToggles] = useState<ChartToggles>(load);

  // merge 的基底必須是**重讀的 localStorage**,不是自己那份 prev:本 hook 是純 useState,
  // 每個呼叫端各持一份。StockChart(管 bb)與 StockIntradayChart(管 vwap/cdp/ma)同時
  // 存活,用 stale prev 整包寫回會讓後寫的一方回滾對方剛做的變更 ——
  // 實際症狀是「江波圖把 CDP 關掉、去 K 線按了 BB、切回來 CDP 自己亮回來」。
  function set(key: keyof ChartToggles, value: boolean): void {
    const next = { ...load(), [key]: value };
    persist(next);
    setToggles(next);
  }

  return { toggles, set };
}
