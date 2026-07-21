import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: { error?: string } };
    return body.detail?.error ?? `HTTP_${res.status}`;
  } catch {
    return `HTTP_${res.status}`;
  }
}

async function fetchWatchlist(): Promise<string[]> {
  const res = await fetch("/api/stock/watchlist");
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { codes: string[] };
  return body.codes;
}

export function useStockWatchlist() {
  return useQuery({ queryKey: ["stock-watchlist"], queryFn: fetchWatchlist, retry: 1 });
}

export function useSaveWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (codes: string[]): Promise<string[]> => {
      const res = await fetch("/api/stock/watchlist", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codes }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return ((await res.json()) as { codes: string[] }).codes;
    },
    onSuccess: (codes) => {
      queryClient.setQueryData(["stock-watchlist"], codes);
    },
  });
}
