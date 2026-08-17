/** 閃電送單 promise 尾段的唯一守門(三座梯共用;零 React 依賴)。
 *
 * 語意逐字沿三梯 `clickPrice` 原本各自複製的 then/catch(PriceLadder 為原本):
 * arm 事件的守門**刻意不對稱**(change-spec review R3 + code review r1 S1):
 *   失敗 → 無條件 dispatch(state 已上提,卸載後 dispatch 到父層 reducer 合法)。
 *     鎖定態下「送出後切走、回應才到」的失敗漏計 = 連 3 敗那道閘永遠關不上。
 *   成功 → 留 `alive()` 守門。遲到的成功來自**已經離開的那座梯**,對「現在這座梯
 *     還能不能送」不構成證據,計進去等於讓一發舊單把斷路器洗回 0。
 * showHint 兩邊都在守門內(它碰的是元件自己的 state)。
 */
import { tradeErrorText } from "@/lib/trade-text";

export interface FlashSendCtx {
  /** aliveRef.current — 元件是否仍掛載 */
  alive: () => boolean;
  dispatch: (a: { type: "send_ok" | "send_fail" }) => void;
  showHint: (text: string) => void;
  /** 成功 hint 文案(帶標的 / 價格 / 張口數,由 caller 組) */
  okText: string;
}

export function settleFlashSend(
  p: Promise<{ ok: boolean; message: string }>,
  ctx: FlashSendCtx,
): void {
  p.then((r) => {
    if (r.ok) {
      if (!ctx.alive()) return;
      ctx.dispatch({ type: "send_ok" });
      ctx.showHint(ctx.okText);
    } else {
      ctx.dispatch({ type: "send_fail" });
      ctx.showHint(r.message !== "" ? r.message : "送單失敗");
    }
  }).catch((err: unknown) => {
    ctx.dispatch({ type: "send_fail" });
    ctx.showHint(tradeErrorText(err instanceof Error ? err.message : String(err)));
  });
}
