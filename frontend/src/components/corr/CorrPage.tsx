import { CorrPanel } from "@/components/corr/CorrPanel";
import { RiverPanel } from "@/components/corr/RiverPanel";
import { useCorrelation } from "@/hooks/useCorrelation";
import { useRiver } from "@/hooks/useRiver";

/** 台股綜合頁 CorrSection 收合區塊的 lazy body:兩條 WS 都在此建立 —— 收合狀態下
 * 本元件不 mount,就不會有每秒推播的流量(gate 在 CorrSection 的展開狀態)。
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
