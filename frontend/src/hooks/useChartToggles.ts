import { useState } from "react";

const KEY = "copycat-chart-toggles";

export interface ChartToggles {
  vwap: boolean;
  cdp: boolean;
  ma: boolean;
  /** 布林通道(K 線專用) */
  bb: boolean;
}

/** `cdp` 預設開(SC-3,user 拍板)。已寫入 localStorage 的使用者維持自己的選擇 ——
 *  `load()` 的 `{...DEFAULTS, ...saved}` 讓存檔覆蓋預設,刻意不做強制升級。 */
const DEFAULTS: ChartToggles = { vwap: true, cdp: true, ma: false, bb: false };

function load(): ChartToggles {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<ChartToggles>) };
  } catch {
    return DEFAULTS;
  }
}

export function useChartToggles() {
  const [toggles, setToggles] = useState<ChartToggles>(load);

  // merge 的基底必須是**重讀的 localStorage**,不是自己那份 prev:本 hook 是純 useState,
  // 每個呼叫端各持一份。StockChart(管 bb)與 StockIntradayChart(管 vwap/cdp/ma)同時
  // 存活,用 stale prev 整包寫回會讓後寫的一方回滾對方剛做的變更 ——
  // 實際症狀是「江波圖把 CDP 關掉、去 K 線按了 BB、切回來 CDP 自己亮回來」。
  function set(key: keyof ChartToggles, value: boolean): void {
    const next = { ...load(), [key]: value };
    window.localStorage.setItem(KEY, JSON.stringify(next));
    setToggles(next);
  }

  return { toggles, set };
}
