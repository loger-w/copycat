/** 後端 build 資訊輪詢(SC-2)與前端 sha 來源選擇(SC-6)。
 *
 *  `/api/health` 回的是**跑著的那個後端行程**的 sha(CLAUDE.md §1 那條「跑著的 server
 *  是哪一版」的機器版);前端 sha 在 dev 下走 vite plugin 的 `/__build/sha` 現算 HEAD,
 *  build 產物下退回 `define` 凍結值。 */
import { useQuery } from "@tanstack/react-query";

import { frontendSha } from "@/lib/version-drift";

export interface ServerBuild {
  git_sha: string | null;
  git_dirty: boolean | null;
  started_at: string;
}

export const HEALTH_POLL_MS = 60_000;

/** 本檔自寫的 local fetch(design R6):`lib/api-error` 的 parseError 解的是
 *  `{detail:{error}}` 契約,`/api/health` 與 `/__build/sha` 都沒有那個 shape,
 *  借過來只會讓錯誤訊息更難讀。這兩條路徑只需要「成功 / 不成功」。 */
async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as T;
}

export function useServerBuild() {
  return useQuery({
    queryKey: ["server-build"],
    queryFn: () => getJson<ServerBuild>("/api/health"),
    refetchInterval: HEALTH_POLL_MS,
    // 60s 後的下一輪就是重試;retry 反而會在測試 teardown 後才打真 fetch(flake 源)
    retry: false,
  });
}

/** 前端 sha:dev 走 `/__build/sha` 現算(與 health 同節奏輪詢),非 dev 或該路徑
 *  不可得(404 / 失敗)才降級 `frontendSha()` 常數。
 *
 *  **pending 回 null 是關鍵**(design R1):live 值未回前拿 define 舊值頂替,會在首幀
 *  閃現一次假落差 + 假 warn —— dev 下 define 是「vite 啟動當時」的 sha,跟當下 HEAD
 *  本來就常常不同。不知道就回不知道。 */
export function useFrontendSha(): string | null {
  const dev = import.meta.env.DEV;
  const q = useQuery({
    queryKey: ["frontend-sha"],
    queryFn: () => getJson<{ git_sha: string | null }>("/__build/sha"),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
    enabled: dev,
  });
  if (!dev) return frontendSha();
  if (q.status === "success") return q.data.git_sha ?? frontendSha();
  if (q.status === "error") return frontendSha();
  return null;
}
