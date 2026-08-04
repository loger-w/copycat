import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { SeriesItem, Snapshot } from "@/types";

async function fetchSeries(): Promise<SeriesItem[]> {
  const res = await fetch("/api/txo/series");
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { series: SeriesItem[] };
  return body.series;
}

export function useSeries() {
  return useQuery({ queryKey: ["txo-series"], queryFn: fetchSeries, retry: 1 });
}

export function useSelectSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (seriesId: string): Promise<Snapshot> => {
      const res = await fetch("/api/txo/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ series_id: seriesId }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return (await res.json()) as Snapshot;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["txo-series"] });
    },
  });
}
