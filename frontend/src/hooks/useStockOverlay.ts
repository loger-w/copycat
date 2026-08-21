import { useQuery } from "@tanstack/react-query";

import type { StockOverlay } from "@/lib/stock-intraday-svg";
import { isoLocalDate } from "@/lib/trading-calendar";

async function fetchOverlay(code: string): Promise<StockOverlay> {
  const res = await fetch(`/api/stock/overlay/${code}`);
  if (!res.ok) throw new Error(`HTTP_${res.status}`);
  return (await res.json()) as StockOverlay;
}

export function useStockOverlay(code: string | null, enabled: boolean) {
  return useQuery({
    // 本機日界 = 台北(部署綁本機;design R13);跨日換 queryKey 自然失效(R9)
    queryKey: ["stock-overlay", code, isoLocalDate(new Date())],
    queryFn: () => fetchOverlay(code!),
    enabled: enabled && code !== null,
    staleTime: Infinity,
    retry: 1,
  });
}
