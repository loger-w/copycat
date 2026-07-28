import { useState } from "react";

import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import {
  buildIndexGeometry,
  buildOverlayGeometry,
  X_END_MIN,
  X_START_MIN,
} from "@/lib/index-chart-svg";
import { cn } from "@/lib/utils";

const MODE_KEY = "copycat-index-mode";
const SIZE = { width: 640, height: 220 };

const X_LABELS = [540, 600, 660, 720, 780].map((m) => ({
  minute: m,
  label: `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`,
}));

function toX(minute: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * SIZE.width;
}

function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function pts(line: { x: number; y: number }[]): string {
  return line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function Axis({ height }: { height: number }) {
  return (
    <>
      {X_LABELS.map(({ minute, label }) => (
        <g key={minute}>
          <line x1={toX(minute)} x2={toX(minute)} y1={0} y2={height - 12} className="stroke-line" strokeWidth={0.4} />
          <text x={toX(minute) + 2} y={height - 2} className="fill-ink-dim" fontSize="0.625rem">
            {label}
          </text>
        </g>
      ))}
    </>
  );
}

function IndexCard({ name, s }: { name: string; s: IndexSeries }) {
  const g = buildIndexGeometry(
    { minutes: s.minutes, ref: s.ref, high: s.high, low: s.low },
    SIZE,
  );
  const chgPts = s.p !== null && s.ref !== null ? (s.p - s.ref) / 1000 : null;
  const chgPct = s.p !== null && s.ref ? ((s.p - s.ref) / s.ref) * 100 : null;
  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <div className="flex items-baseline gap-3">
        <h3 className="text-sm font-bold text-ink">{name}</h3>
        <span className="font-mono text-2xl text-ink">{s.p !== null ? fmt(s.p) : "-"}</span>
        {chgPts !== null && chgPct !== null ? (
          <span
            className={cn(
              "font-mono text-sm",
              chgPts > 0 ? "text-bull" : chgPts < 0 ? "text-bear" : "text-ink",
            )}
          >
            {`${chgPts > 0 ? "+" : ""}${chgPts.toFixed(2)} (${chgPct > 0 ? "+" : ""}${chgPct.toFixed(2)}%)`}
          </span>
        ) : null}
        {s.stale ? <span className="text-xs text-ink-dim">資料中斷</span> : null}
      </div>
      <p className="mt-0.5 font-mono text-xs text-ink-dim">
        {`高 ${s.high !== null ? fmt(s.high) : "-"} 低 ${s.low !== null ? fmt(s.low) : "-"} 昨收 ${s.ref !== null ? fmt(s.ref) : "-"}`}
      </p>
      <svg viewBox={`0 0 ${SIZE.width} ${SIZE.height}`} className="mt-2 w-full" role="img" aria-label={`${name}分時走勢`}>
        <Axis height={SIZE.height} />
        <line x1={0} x2={SIZE.width} y1={g.refY} y2={g.refY} className="stroke-line" strokeDasharray="2 3" strokeWidth={1} />
        {g.yTicks.map((t) => (
          <text key={t.priceMilli} x={2} y={Math.min(Math.max(t.y - 2, 8), SIZE.height - 14)} className="fill-ink-dim" fontSize="0.625rem">
            {fmt(t.priceMilli)}
          </text>
        ))}
        {g.line.length > 0 ? (
          <polyline points={pts(g.line)} fill="none" className="stroke-accent" strokeWidth={1.4} />
        ) : null}
      </svg>
    </figure>
  );
}

function OverlayCard({ twse, otc }: { twse: IndexSeries; otc: IndexSeries }) {
  const g = buildOverlayGeometry(
    [
      { minutes: twse.minutes, ref: twse.ref },
      { minutes: otc.minutes, ref: otc.ref },
    ],
    SIZE,
  );
  const colors = ["stroke-profit", "stroke-idx-otc"];
  const labels = ["加權", "櫃買"];
  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <div className="flex items-baseline gap-4">
        <h3 className="text-sm font-bold text-ink">加權 vs 櫃買(相對昨收 %)</h3>
        <span className="font-mono text-xs text-profit">─ 加權</span>
        <span className="font-mono text-xs text-idx-otc">─ 櫃買</span>
      </div>
      <svg viewBox={`0 0 ${SIZE.width} ${SIZE.height}`} className="mt-2 w-full" role="img" aria-label="指數重疊走勢">
        <Axis height={SIZE.height} />
        <line x1={0} x2={SIZE.width} y1={g.zeroY} y2={g.zeroY} className="stroke-line" strokeDasharray="2 3" strokeWidth={1} />
        {g.lines.map((l, i) => (
          <g key={labels[i]}>
            <polyline points={pts(l.pts)} fill="none" className={colors[i]} strokeWidth={1.4} />
            {l.pts.length > 0 ? (
              <text
                x={Math.min(l.pts[l.pts.length - 1]!.x + 4, SIZE.width - 28)}
                y={l.pts[l.pts.length - 1]!.y + 3}
                className={colors[i]!.replace("stroke-", "fill-")}
                fontSize="0.625rem"
              >
                {labels[i]}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </figure>
  );
}

interface Props {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  txf: TxfQuote | null;
}

export function IndexPage({ twse, otc, txf }: Props) {
  const [mode, setMode] = useState<"side" | "overlay">(
    () => (window.localStorage.getItem(MODE_KEY) === "overlay" ? "overlay" : "side"),
  );

  function switchMode(next: "side" | "overlay"): void {
    setMode(next);
    window.localStorage.setItem(MODE_KEY, next);
  }

  const basis = txf !== null && twse?.p != null ? (txf.p - twse.p) / 1000 : null;

  return (
    <div className="flex flex-1 flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="font-mono text-sm text-ink">
          台指期 <span className="text-ink">{txf !== null ? fmt(txf.p) : "-"}</span>{" "}
          <span
            className={cn(
              basis !== null && basis > 0 ? "text-bull" : basis !== null && basis < 0 ? "text-bear" : "text-ink-dim",
            )}
          >
            {basis !== null ? `價差 ${basis > 0 ? "+" : ""}${basis.toFixed(2)}` : "價差 -"}
          </span>
          {txf?.time ? (
            <span className="ml-2 text-xs text-ink-dim">至 {txf.time.slice(0, 5)}</span>
          ) : null}
        </p>
        <div className="flex gap-1">
          {(
            [
              ["side", "並排"],
              ["overlay", "重疊"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => switchMode(id)}
              className={cn(
                "rounded border px-2 py-0.5 text-xs",
                mode === id ? "border-accent text-accent" : "border-line text-ink-dim",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {twse === null || otc === null ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">等待指數資料…</p>
        </div>
      ) : mode === "side" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <IndexCard name="加權指數" s={twse} />
          <IndexCard name="櫃買指數" s={otc} />
        </div>
      ) : (
        <OverlayCard twse={twse} otc={otc} />
      )}
    </div>
  );
}

export default IndexPage;
