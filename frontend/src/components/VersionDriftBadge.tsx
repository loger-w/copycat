import { useEffect, useRef } from "react";

import { useFrontendSha, useServerBuild } from "@/hooks/useServerBuild";
import { versionDrift } from "@/lib/version-drift";

/** warn 與 title 共用同一句(PLAN §6「title 同 warn 文案」)—— 兩處各寫一份就會漂。 */
function driftMessage(fe: string, be: string): string {
  return `前後端版本落差:前端 ${fe} / 後端 ${be} — 舊的一邊該重啟`;
}

/** 前後端版本落差膠囊(SC-4)+ console.warn once per pair(SC-5)。
 *
 *  健康態**零 DOM**:版面不留位、無膠囊 = 一切同步,不需要人去分辨「灰色的沒事」。
 *  任一邊 sha 不可得也視為健康(見 versionDrift)—— 誤報一次就會被當雜訊無視。
 *
 *  `feSha` 是測試注入縫(design R2):不給時走 `useFrontendSha()`,測試不必依賴
 *  跑測試那台機器的 git 狀態。 */
export function VersionDriftBadge({ feSha }: { feSha?: string | null }) {
  const live = useFrontendSha();
  const fe = feSha !== undefined ? feSha : live;
  const { data } = useServerBuild();
  const drift = versionDrift(fe, data?.git_sha);

  // hooks 順序:warn 的 ref/effect 必須宣告在下面的 early return 之前
  const warnedPair = useRef<string | null>(null);
  const driftFe = drift?.fe ?? null;
  const driftBe = drift?.be ?? null;
  useEffect(() => {
    if (driftFe === null || driftBe === null) return;
    const pair = `${driftFe}|${driftBe}`;
    // per pair 去重:同一組落差只吵一次(60s 輪詢會一直重算),換一組 sha 是新事實。
    // 落差消失時不清 ref —— 清掉就會讓「重啟前 / 重啟後又回到同一組」再吵一次。
    if (warnedPair.current === pair) return;
    warnedPair.current = pair;
    console.warn(driftMessage(driftFe, driftBe));
  }, [driftFe, driftBe]);

  if (drift === null) return null;
  return (
    <span
      data-testid="version-drift-badge"
      title={driftMessage(drift.fe, drift.be)}
      className="inline-flex items-center gap-1.5 rounded-sm border border-warn/40 bg-warn/15 px-2.5 py-1 font-mono text-xs text-warn"
    >
      版本落差
    </span>
  );
}
