/** 四鍵訊號開關(design §8.2;SC-12)。
 *
 *  真值在後端 configs(重啟保留),前端只讀寫不快取到 localStorage —— 開關同時管
 *  Discord 推播,兩份來源會漂。 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { SignalEnabled } from "@/lib/signal-model";

const ENABLED_KEY = ["stock-signals-enabled"];

/** **fail-open**:載入中 / hub 未就緒時當全開,與 `filterKinds` 同一條理由 ——
 *  誤判成全關會讓整條訊號流靜默清空,比多顯示幾則難察覺得多。 */
const ALL_ON: SignalEnabled = {
  cdp_cross: true,
  surge_crash: true,
  vol_burst: true,
  limit_lock: true,
};

/** 缺鍵(舊後端 / 新增類型)補全開,理由同上。 */
function toEnabled(body: { enabled?: Partial<SignalEnabled> }): SignalEnabled {
  return { ...ALL_ON, ...(body.enabled ?? {}) };
}

async function fetchEnabled(): Promise<SignalEnabled> {
  const res = await fetch("/api/stock/signals/enabled");
  if (!res.ok) throw new Error(await parseError(res));
  return toEnabled((await res.json()) as { enabled?: Partial<SignalEnabled> });
}

export function useSignalsConfig() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ENABLED_KEY, queryFn: fetchEnabled, retry: 1 });

  const save = useMutation({
    // 部分更新:只送被切的那一鍵。整包送會把「別的 client 剛改的鍵」用自己這份
    // 可能已過期的快取蓋回去。
    mutationFn: async (patch: Partial<SignalEnabled>): Promise<SignalEnabled> => {
      const res = await fetch("/api/stock/signals/enabled", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: patch }),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return toEnabled((await res.json()) as { enabled?: Partial<SignalEnabled> });
    },
    // 回應本身就是合併後的完整四鍵 → 直接回寫,不必再 GET 一次
    onSuccess: (enabled) => {
      queryClient.setQueryData(ENABLED_KEY, enabled);
    },
  });

  return { enabled: query.data ?? ALL_ON, save };
}
