import { CorrPanel } from "@/components/corr/CorrPanel";
import { RiverPanel } from "@/components/corr/RiverPanel";
import { useCorrelation } from "@/hooks/useCorrelation";
import { useRiver } from "@/hooks/useRiver";

/** 頂層相關係數 tab 的 lazy body(2026-08-16 R2 升回頂層;首訪後 hidden 保留 DOM,
 * 兩條 WS 常駐 —— 與其他 lazy tab 同慣例)。兩條 WS 都在此建立,沒點進來過就不 mount,
 * 也就沒有每秒推播的流量(gate 在 App 的 `visited.corr`)。
 *
 * 版面:上半 六腿江波圖(方向與時點)/ 下半 相關係數表(連動強度)。兩者互補 ——
 * 係數是數字,看不出哪條腿先動;圖看得出時點,看不出強度。
 */
export default function CorrPage() {
  const { state, wsStatus } = useCorrelation();
  const river = useRiver();
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      <RiverPanel state={river.state} />
      <CorrPanel state={state} wsStatus={wsStatus} />
    </div>
  );
}
