/** 指數快照源的健康判別(N108;零 React 依賴,獨立單元測)。 */

/** 判別子吃得到的最小形狀。**不 import `IndexSeries`**(`@/hooks/useIndexStream`)——
 *  lib 反向依賴 hooks 會把純函式綁上 WS hook 那一層,而這裡只需要「現價」與「分鐘格」
 *  兩欄,結構相容就夠了(同 `stock-accum.ts::GroupLikeSnapshot` 的取捨)。 */
export interface SourceLiveness {
  p: number | null;
  minutes: Record<string, number>;
}

/** 「櫃買快照源(MIS)中斷」的判定寬限:加權要先累積這麼多分鐘格,才開始認為
 *  「櫃買一格都沒有」是壞掉而不是還沒輪到(MIS 是 5s poll,加權是 TC4 push)。
 *  2 格 ≈ 開盤後兩分鐘 —— 比 poll 週期大兩個量級,又短到整天空的日子一眼看得到。 */
export const OTC_DEAD_MIN_TWSE_MINUTES = 2;

/** 櫃買快照源是否已中斷(N108)。
 *
 *  MIS(`copycat/server/mis.py`)是非契約的公開端點,壞掉時 `_mis_loop` 拿到 None 就
 *  跳過 —— 從開盤即死透的日子 otc 的 `p`/`ref` 恆 null、`minutes` 恆空,而 **otc 不吃
 *  `stale`**(watchdog 只看加權 TC4 推播),畫面因此是一條沒有任何說明的空線。
 *
 *  判別子刻意**不看時鐘**(不引進交易時段 / 日曆判斷,也就沒有跨日、假日、盤前的誤報):
 *  拿同一條 WS 上的加權當對照 —— 加權都已經有分鐘格了而櫃買一格都沒有,只可能是櫃買
 *  這一路壞了。盤前兩者皆空 → 恆 false。
 *
 *  這是**啟發式**不是真訊號:MIS 若在盤中才壞(已經有格),這裡判不出來(留尾記
 *  docs/next-time.md 2026-08-24 節)。安全側 = 少講一句,不會冤枉活著的源。 */
export function otcSourceDead(
  twse: SourceLiveness | null,
  otc: SourceLiveness | null,
): boolean {
  if (otc === null || twse === null) return false;
  if (otc.p !== null || Object.keys(otc.minutes).length > 0) return false;
  return Object.keys(twse.minutes).length >= OTC_DEAD_MIN_TWSE_MINUTES;
}
