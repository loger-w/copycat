import { cn } from "@/lib/utils";
import type { WsStatus } from "@/hooks/useTxoSnapshot";

/** 後端交接(回補)進度;產生點 `EngineRuntime._handover`(copycat/server/engine.py)。
 *
 *  **型別住在這裡、由 `Snapshot` 反過來引用**(review F4):唯一的讀者是本 badge,而
 *  TXO 的 `Snapshot` 只是目前**其中一條**運送管道 —— 個股 / 期貨面日後要送同一份進度時,
 *  badge 不該為了拿型別而 import 一個它不消費的 TXO 快照。
 *
 *  **全欄選填**:交接還沒跑過時整份是 `null`,而每個 attempt **開頭**那則刻意不帶五個
 *  統計欄(後端 D1'':上一輪的 backfill_secs 掛在新一輪的進度上是假資料)。 */
export interface HandoverProgress {
  attempt?: number;
  attempts_max?: number;
  phase?: string;
  backfill_secs?: number;
  buffer_used?: number;
  buffer_cap?: number;
  buffer_warned?: boolean;
  overflows?: number;
}

const WARN_TONE = "bg-bull/15 text-bull border-bull/40";
const DEFAULT_TONE = "bg-surface text-ink-muted border-line";

const STATUS: Record<string, { label: string; tone?: string }> = {
  connecting: { label: "連線中" },
  backfilling: { label: "回補中", tone: "bg-profit/15 text-profit border-profit/40" },
  live: { label: "即時連線中", tone: "bg-bear/15 text-bear border-bear/40" },
  reconnecting: { label: "重連中" },
  disconnected: { label: "已斷線", tone: WARN_TONE },
  degraded: { label: "資料降級", tone: WARN_TONE },
  replay: { label: "回放模式" },
};

export function ConnectionBadge({
  status,
  wsStatus,
  handover = null,
}: {
  status: string;
  wsStatus: WsStatus;
  /** 後端交接進度(選填):`attempt` ≥ 2 時 badge 講到第幾次。 */
  handover?: HandoverProgress | null;
}) {
  const broken = wsStatus !== "open";
  // 只在**回補中**才帶次數:attempt 是上一次交接留下的值,live / degraded 時掛著
  // 「第 3 次」等於把已經結束的事講成正在發生。第 1 次不帶 —— 那是正常開盤路徑,
  // 每次都印「(第 1 次)」只是噪音,而「第 2 次起」正是使用者該注意的異常。
  const attempt = handover?.attempt;
  const retrying = status === "backfilling" && attempt !== undefined && attempt > 1;
  const label = broken
    ? wsStatus === "connecting"
      ? "連線中"
      : "連線中斷,重試中"
    : retrying
      ? `回補中(第 ${attempt} 次)`
      : (STATUS[status]?.label ?? status);
  const tone = broken ? WARN_TONE : (STATUS[status]?.tone ?? DEFAULT_TONE);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 font-mono text-xs",
        tone,
      )}
    >
      <span className="inline-block size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </span>
  );
}
