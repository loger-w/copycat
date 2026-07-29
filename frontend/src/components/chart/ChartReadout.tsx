import { cn } from "@/lib/utils";

/** 圖表頂列資訊條(江波圖 / K 線共用;純 presentational,無資料依賴)。
 *
 * 取代原本「跟著游標跑的浮窗」:固定停靠、零遮圖、零抖動。**沒 hover 時顯示即時資料**
 * (江波圖 = 最新分鐘、K 線 = 最後一根),不是空白 —— 預設態有內容才不會閃爍。
 *
 * 欄位順序與數量由呼叫端固定給,缺值給 "-" 而非移除欄位(防寬度跳動)。
 * 高度由外層容器決定(B8 的 chrome 對稱要求:兩張圖頂列同為 h-[1.375rem])。 */

export type ReadoutTone = "bull" | "bear" | "muted";

export interface ReadoutField {
  /** 前綴標籤;空字串 = 只顯示值(時間欄用) */
  label: string;
  value: string;
  tone?: ReadoutTone;
}

function toneClass(tone: ReadoutTone | undefined): string {
  if (tone === "bull") return "text-bull";
  if (tone === "bear") return "text-bear";
  if (tone === "muted") return "text-ink-dim";
  return "text-ink";
}

interface Props {
  fields: ReadoutField[];
  /** 十字線在場 → 第一欄(時間)轉 accent,作為「hover 態 vs 即時態」的零位移提示 */
  hovering: boolean;
}

export function ChartReadout({ fields, hovering }: Props) {
  return (
    <div
      data-testid="chart-readout"
      data-hovering={hovering ? "true" : "false"}
      className="flex min-w-0 items-center gap-x-3 overflow-hidden font-mono text-xs"
    >
      {fields.map((f, i) => (
        <span
          key={f.label !== "" ? f.label : `f-${i}`}
          className={cn(
            "whitespace-nowrap",
            i === 0 ? (hovering ? "text-accent" : "text-ink-muted") : toneClass(f.tone),
          )}
        >
          {f.label !== "" ? <span className="text-ink-dim">{f.label} </span> : null}
          {f.value}
        </span>
      ))}
    </div>
  );
}
