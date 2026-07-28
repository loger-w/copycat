import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import { cn } from "@/lib/utils";

function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function chgPct(s: IndexSeries): number | null {
  if (s.p === null || s.ref === null || s.ref === 0) return null;
  return ((s.p - s.ref) / s.ref) * 100;
}

function IndexCell({ label, s }: { label: string; s: IndexSeries | null }) {
  const usable = s !== null && !s.stale && s.p !== null;
  const chg = usable ? chgPct(s) : null;
  return (
    <span className="font-mono text-xs text-ink-dim">
      {label}{" "}
      <span className="text-ink">{usable ? fmt(s.p!) : "-"}</span>{" "}
      <span
        className={cn(
          chg !== null && chg > 0 ? "text-bull" : chg !== null && chg < 0 ? "text-bear" : "text-ink-dim",
        )}
      >
        {chg !== null ? `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%` : "-"}
      </span>
    </span>
  );
}

interface Props {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  txf: TxfQuote | null;
}

/** 頂部指數 bar(SC-1):加權/櫃買 chg%、台指基差(相對加權;design IR9)。 */
export function IndexBar({ twse, otc, txf }: Props) {
  const twseUsable = twse !== null && !twse.stale && twse.p !== null;
  const basis = txf !== null && twseUsable ? (txf.p - twse.p!) / 1000 : null;
  return (
    <div className="ml-auto flex items-baseline gap-3">
      <IndexCell label="加權" s={twse} />
      <IndexCell label="櫃買" s={otc} />
      <span className="font-mono text-xs text-ink-dim">
        台指 <span className="text-ink">{txf !== null ? fmt(txf.p) : "-"}</span>{" "}
        <span
          className={cn(
            basis !== null && basis > 0 ? "text-bull" : basis !== null && basis < 0 ? "text-bear" : "text-ink-dim",
          )}
        >
          {basis !== null ? `${basis > 0 ? "+" : ""}${basis.toFixed(2)}` : "-"}
        </span>
      </span>
    </div>
  );
}
