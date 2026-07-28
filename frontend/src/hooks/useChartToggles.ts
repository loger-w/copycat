import { useState } from "react";

const KEY = "copycat-chart-toggles";

export interface ChartToggles {
  vwap: boolean;
  cdp: boolean;
  ma: boolean;
}

const DEFAULTS: ChartToggles = { vwap: true, cdp: false, ma: false };

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

  function set(key: keyof ChartToggles, value: boolean): void {
    setToggles((prev) => {
      const next = { ...prev, [key]: value };
      window.localStorage.setItem(KEY, JSON.stringify(next));
      return next;
    });
  }

  return { toggles, set };
}
