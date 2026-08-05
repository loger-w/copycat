/** 後端 build 資訊輪詢(SC-2)與 dev range 判別的來源選擇(SC-6 / design C1~C6)。
 *
 *  `/api/health` 回的是**跑著的那個後端行程**的 sha(CLAUDE.md §1 那條「跑著的 server
 *  是哪一版」的機器版);dev 下把它當 `since` 丟給 vite plugin,由 middleware 現算
 *  `git log <since>..HEAD -- copycat/` 得出 `behind`。build 產物沒有那條路徑(404),
 *  語意退回 define 凍結 sha 與後端 sha 的等值比對。 */
import { useQuery } from "@tanstack/react-query";

import { frontendSha } from "@/lib/version-drift";

export interface ServerBuild {
  git_sha: string | null;
  git_dirty: boolean | null;
  started_at: string;
}

export const HEALTH_POLL_MS = 60_000;

/** 聚焦 / 重掛的去重窗(C6)。60s 輪詢之外,TQ 還會在 window focus 與元件重掛時重取;
 *  沒有 staleTime 的話切回分頁就是一次 git 子行程,切來切去會變成 execFileSync 風暴。 */
const BUILD_STALE_MS = 5_000;

interface HttpError extends Error {
  status?: number;
}

/** 本檔自寫的 local fetch(design R6):`lib/api-error` 的 parseError 解的是
 *  `{detail:{error}}` 契約,`/api/health` 與 `/__build/sha` 都沒有那個 shape。
 *  status 掛在 Error 上是必要的 —— 來源選擇要分辨 404(路徑不存在)與其它錯誤(C1)。 */
async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw Object.assign(new Error(String(res.status)), { status: res.status });
  }
  return (await res.json()) as T;
}

export function useServerBuild() {
  return useQuery({
    queryKey: ["server-build"],
    queryFn: () => getJson<ServerBuild>("/api/health"),
    refetchInterval: HEALTH_POLL_MS,
    staleTime: BUILD_STALE_MS,
    // 60s 後的下一輪就是重試;retry 反而會在測試 teardown 後才打真 fetch(flake 源)
    retry: false,
  });
}

/** 比對模式:
 *  - `range` —— dev + middleware 答過:以 `behind` 判(唯一能表達「後端落後」的來源)
 *  - `equal` —— build 產物語意:define 凍結 sha vs 後端 sha 等值比對
 *  - `unknown` —— 冷態或 transient 失敗:**不判定**(不是「沒落差」) */
export type DriftMode = "range" | "equal" | "unknown";

export interface BuildDrift {
  mode: DriftMode;
  fe: string | null;
  behind: boolean | null;
}

/** 前端與後端的比對素材;`beSha` 來自 `/api/health`。
 *
 *  **data-first**(C4):問到過就一路沿用最後一次現算值 —— 暖態下偶發 500 不該讓膠囊
 *  閃掉再閃回。**只有 404 才降級 define**(C1):404 是「這個 vite middleware 不存在」
 *  = 真的在跑 build 產物;500 / 網路錯只是 transient,拿 define 頂替會用「vite 啟動當時」
 *  的舊 sha 去比,dev 下那本來就常常不等於 HEAD → 假落差。
 *
 *  沒有 `beSha` 就不問(C5):沒有 since 就沒有 range 可判,問了也只是白跑一次子行程。 */
export function useBuildDrift(beSha: string | null): BuildDrift {
  const dev = import.meta.env.DEV;
  const q = useQuery({
    // key 帶 beSha:後端換版就是另一個問題,不能沿用上一版的答案
    queryKey: ["build-drift", beSha],
    queryFn: () =>
      getJson<{ git_sha: string | null; behind: boolean | null }>(
        `/__build/sha?since=${encodeURIComponent(beSha ?? "")}`,
      ),
    refetchInterval: HEALTH_POLL_MS,
    staleTime: BUILD_STALE_MS,
    retry: false,
    enabled: dev && beSha !== null,
  });

  if (!dev) return { mode: "equal", fe: frontendSha(), behind: null };
  if (q.data !== undefined) return { mode: "range", fe: q.data.git_sha, behind: q.data.behind };
  if (q.status === "error" && (q.error as HttpError | null)?.status === 404) {
    return { mode: "equal", fe: frontendSha(), behind: null };
  }
  return { mode: "unknown", fe: null, behind: null };
}
