/** 六腿江波圖面板:模式鈕(並排 / 重疊)+ 勾選列 + 兩種呈現的容器(SC-7/SC-8)。
 *
 * 吃 props 不自己呼叫 `useRiver` —— 與 `CorrPanel` 同款(資料流留在 `CorrPage`),
 * 元件測試才能直接餵狀態(`[phase-3 補註]`:design §2 原寫 RiverPanel 內呼叫 hook)。
 */
import { useState } from "react";

import type { OverlayEntry } from "@/lib/river-chart-svg";
import { cn } from "@/lib/utils";
import type { RiverState } from "@/types";

import { RiverCards } from "./RiverCards";
import { RIVER_TEXTS } from "./river-colors";
import { RiverOverlay } from "./RiverOverlay";

const MODE_KEY = "copycat-river-mode";
/** 存「**關掉**哪些腿」而非「開哪些」:設定檔日後加第七腿時,舊值不會讓新腿默默隱形。 */
const OFF_KEY = "copycat-river-legs";

type Mode = "side" | "overlay";

function initialMode(): Mode {
  return window.localStorage.getItem(MODE_KEY) === "overlay" ? "overlay" : "side";
}

function initialOff(): string[] {
  try {
    const raw = window.localStorage.getItem(OFF_KEY);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((k): k is string => typeof k === "string") : [];
  } catch {
    return []; // 壞值降回預設(never-raise)
  }
}

interface Props {
  state: RiverState | null;
}

export function RiverPanel({ state }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [off, setOff] = useState<string[]>(initialOff);

  function switchMode(next: Mode): void {
    setMode(next);
    window.localStorage.setItem(MODE_KEY, next);
  }

  function toggleLeg(key: string): void {
    const next = off.includes(key) ? off.filter((k) => k !== key) : [...off, key];
    setOff(next);
    window.localStorage.setItem(OFF_KEY, JSON.stringify(next));
  }

  if (state === null) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-ink-muted">
        等待六腿資料…
      </div>
    );
  }

  const order = Object.keys(state.legs);
  const sessionText = state.session === "day" ? "日盤" : "夜盤";
  const hasAnyPoint = order.some((key) => Object.keys(state.legs[key]?.minutes ?? {}).length > 0);
  const entries: OverlayEntry[] = order
    .map((key, i) => ({ key, colorIndex: i, leg: state.legs[key]!, label: state.legs[key]!.label }))
    .filter((entry) => !off.includes(entry.key));

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm text-ink">六腿走勢</h3>
        <span className="font-mono text-xs text-ink-dim">{sessionText}</span>
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
        {mode === "overlay" ? (
          <div className="flex flex-wrap items-center gap-2">
            {order.map((key, i) => {
              const on = !off.includes(key);
              return (
                <button
                  key={key}
                  type="button"
                  role="checkbox"
                  aria-checked={on}
                  aria-label={state.legs[key]!.label}
                  onClick={() => toggleLeg(key)}
                  className={cn(
                    "rounded border px-2 py-0.5 font-mono text-xs",
                    on
                      ? cn("border-line", RIVER_TEXTS[i % RIVER_TEXTS.length])
                      : "border-line text-ink-dim line-through",
                  )}
                >
                  {state.legs[key]!.label}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
      {!hasAnyPoint ? (
        <div className="flex items-center justify-center py-8 text-sm text-ink-muted">
          {`等待${sessionText}資料…`}
        </div>
      ) : mode === "side" ? (
        <RiverCards order={order} legs={state.legs} window={state.window} />
      ) : (
        <RiverOverlay entries={entries} window={state.window} baseKey={state.base} />
      )}
    </section>
  );
}

export default RiverPanel;
