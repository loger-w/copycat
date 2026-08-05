import { useEffect, useRef } from "react";

import { useBuildDrift, useServerBuild, type BuildDrift } from "@/hooks/useServerBuild";
import { versionDrift, type Drift } from "@/lib/version-drift";

/** warn 與 title 共用同一句(PLAN §6「title 同 warn 文案」)—— 兩處各寫一份就會漂。 */
function driftMessage(fe: string, be: string): string {
  return `前後端版本落差:前端 ${fe} / 後端 ${be} — 舊的一邊該重啟`;
}

/** 依比對模式決定要不要亮燈(design C1/C3)。
 *
 *  `range` 是 dev 的正解:`behind === true` 才亮 —— 只有後端 code(`copycat/`)真的前進了
 *  才叫「該重啟」。`behind === null` 是 middleware 說「我不知道」,同樣不亮。
 *  `equal` 是 build 產物語意的退路;`unknown` 一律不判定。 */
function driftOf(cmp: BuildDrift, be: string | null): Drift | null {
  if (cmp.mode === "unknown") return null;
  if (cmp.mode === "equal") return versionDrift(cmp.fe, be);
  return cmp.behind === true && cmp.fe && be ? { fe: cmp.fe, be } : null;
}

/** 前後端版本落差膠囊(SC-4)+ console.warn once per pair(SC-5)。
 *
 *  健康態**零 DOM**:版面不留位、無膠囊 = 一切同步,不需要人去分辨「灰色的沒事」。
 *  任一邊不可得也視為健康 —— 誤報一次就會被當雜訊無視,之後真的落差也不會有人看。 */
export function VersionDriftBadge() {
  const { data } = useServerBuild();
  const be = data?.git_sha ?? null;
  const cmp = useBuildDrift(be);
  const drift = driftOf(cmp, be);

  // hooks 順序:warn 的 ref/effect 必須宣告在下面的 early return 之前
  const warnedPair = useRef<string | null>(null);
  const driftFe = drift?.fe ?? null;
  const driftBe = drift?.be ?? null;
  useEffect(() => {
    if (driftFe === null || driftBe === null) return;
    const pair = `${driftFe}|${driftBe}`;
    // per pair 去重:同一組落差只吵一次(60s 輪詢會一直重算),換一組 sha 是新事實。
    // 落差消失時**不清** ref —— 清掉的話,一次 behind 翻回 false 再翻回 true
    // (輪詢邊界、暫時性的 git 狀態)就會重吵同一句。
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
