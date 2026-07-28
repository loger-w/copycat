import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface Group {
  name: string;
  codes: string[];
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: { error?: string } };
    return body.detail?.error ?? `HTTP_${res.status}`;
  } catch {
    return `HTTP_${res.status}`;
  }
}

async function fetchWatchlist(): Promise<Group[]> {
  const res = await fetch("/api/stock/watchlist");
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { groups: Group[] };
  return body.groups;
}

export function useStockWatchlist() {
  return useQuery({ queryKey: ["stock-watchlist"], queryFn: fetchWatchlist, retry: 1 });
}

export function useSaveWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (groups: Group[]): Promise<Group[]> => {
      const res = await fetch("/api/stock/watchlist", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ groups }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return ((await res.json()) as { groups: Group[] }).groups;
    },
    onSuccess: (groups) => {
      queryClient.setQueryData(["stock-watchlist"], groups);
    },
  });
}
