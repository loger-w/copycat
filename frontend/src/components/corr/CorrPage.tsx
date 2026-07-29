import { CorrPanel } from "@/components/corr/CorrPanel";
import { useCorrelation } from "@/hooks/useCorrelation";

/** 相關係數分頁:WS 連線在此建立 —— 沒開過這個 tab 就不會有每秒推播的流量。 */
export default function CorrPage() {
  const { state, wsStatus } = useCorrelation();
  return <CorrPanel state={state} wsStatus={wsStatus} />;
}
