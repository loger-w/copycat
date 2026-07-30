import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Group, Watchlist } from "@/lib/watchlist-model";

export type { Group, Watchlist };

/** 群組聯集(首見序去重)—— 與後端 v2→v3 讀時遷移同一條規則。 */
function unionCodes(groups: Group[]): string[] {
  const seen: string[] = [];
  for (const g of groups) {
    for (const code of g.codes) if (!seen.includes(code)) seen.push(code);
  }
  return seen;
}

/** 回應缺 `codes`(舊後端)→ 用聯集補。少了這步,存檔成功之後 cache 的 codes 才變
 *  undefined,下一次 render 讀 `wl.codes` 就崩 —— 「成功之後才炸」最難察覺。 */
function toWatchlist(body: { codes?: string[]; groups?: Group[] }): Watchlist {
  const groups = body.groups ?? [];
  return { codes: body.codes ?? unionCodes(groups), groups };
}

/** 三個錯誤碼的中文文案(跨檔契約 W-2)。側欄與管理 Dialog 共用**同一份**,
 *  複製兩份會漂而白名單只釘了「文案不變」。 */
export function errText(message: string): string {
  if (message === "WATCHLIST_FULL") return "自選已達 30 檔上限";
  if (message === "BAD_CODE") return "股號格式不正確";
  if (message === "BAD_GROUP") return "群組名稱不合法";
  return "儲存失敗";
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: { error?: string } };
    return body.detail?.error ?? `HTTP_${res.status}`;
  } catch {
    return `HTTP_${res.status}`;
  }
}

async function fetchWatchlist(): Promise<Watchlist> {
  const res = await fetch("/api/stock/watchlist");
  if (!res.ok) throw new Error(await parseError(res));
  return toWatchlist((await res.json()) as { codes?: string[]; groups?: Group[] });
}

export function useStockWatchlist() {
  return useQuery({ queryKey: ["stock-watchlist"], queryFn: fetchWatchlist, retry: 1 });
}

export function useSaveWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (wl: Watchlist): Promise<Watchlist> => {
      const res = await fetch("/api/stock/watchlist", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(wl),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return toWatchlist((await res.json()) as { codes?: string[]; groups?: Group[] });
    },
    onSuccess: (wl) => {
      queryClient.setQueryData(["stock-watchlist"], wl);
    },
  });
}
