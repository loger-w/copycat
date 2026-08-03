import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** `useId()` 產出 → 合法 id token。
 *
 *  React 19 的 useId 是 «r0» 形態,含非識別字元 —— 直接拼進 `url(#…)` 或 `aria-controls`
 *  時的解析行為未實測,而 SVG 規範下 `url(#…)` 解析失敗是**該元素不繪製**,完全靜默。 */
export function safeIdToken(raw: string): string {
  return raw.replace(/[^a-zA-Z0-9]/g, "");
}
