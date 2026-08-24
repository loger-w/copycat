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
  // **兩參數 then,不是 `.then().catch()`**(code review r1 IMPL-3):串接時成功分支自己
  // 拋出的例外(showHint 內 setState 炸)會掉進 catch → 同一次送單既 send_ok 又 send_fail,
  // 一張成功的單把武裝斷路器往「連敗」推。錯誤處理只該看 promise 本身的結果。
  p.then(
    (r) => {
      if (r.ok) {
        if (!ctx.alive()) return;
        ctx.dispatch({ type: "send_ok" });
        ctx.showHint(ctx.okText);
      } else {
        ctx.dispatch({ type: "send_fail" });
        ctx.showHint(r.message !== "" ? r.message : "送單失敗");
      }
    },
    (err: unknown) => {
      ctx.dispatch({ type: "send_fail" });
      ctx.showHint(tradeErrorText(err instanceof Error ? err.message : String(err)));
    },
  ).catch((err: unknown) => {
    // 只有上面兩個回呼**自己**拋才會到這裡:送單結果已處理完,不得回頭補 send_fail。
    // 無從補救(state 已 dispatch),但也不能靜默 —— 留 console.error 讓它在 devtools 可見。
    console.error("閃電送單尾段回呼例外(送單結果已處理,不改判成敗)", err);
  });
}

/** 送單 payload 的稽核 `source`(N082)。
 *
 *  鎖定態 = 換標的 / 換梯 / 閒置都不解除武裝,是誤送半徑最大的狀態。舊值域只有
 *  `panel` / `flash` 兩種,事後翻審計檔(`capital-YYYYMMDD.jsonl`)查「這張單是不是
 *  在鎖定態下按出去的」完全沒有線索。
 *
 *  **六個送單點共用這一支**(三座梯 × 點價 / 市價鈕):各寫一次三元式的話,失效樣態是
 *  其中一處漂成別的字串,而審計檔上看起來只是「少了幾筆 flash-locked」—— 沒有訊號。
 *  後端 `source: str` 值域本就可擴,舊值語意逐字不變。 */
export function flashSource(locked: boolean): "flash" | "flash-locked" {
  return locked ? "flash-locked" : "flash";
}

// ---------------------------------------------------------------------------
// 梯頂市價鈕的三態(SC-6 / SC-7 / SC-8)。三座梯各自算一次的話,「什麼時候鎖」這條
// 安全規則會有三份且必然漂移 —— 純函式收在這裡,元件只餵判準。
// ---------------------------------------------------------------------------

/** 個股期前置閘的唯一說明。文案不點名 ETF —— 除權息調整契約(單位 2,157)也走同一條,
 *  寫死「ETF」會讓那類標的的提示變成假訊息。`StkfutLadder` 的武裝鈕與市價鈕同源。 */
export const BLOCKED_TEXT = "此契約規格暫未開放下單";

/** 估價不可得 = fail-safe 鎖鈕。**不用假想界**:現股缺漲跌停時 buildLadder 會用 ±10%
 *  假想界畫梯,拿它送單就是把一個猜出來的價格當真錢價位(current-state §4)。 */
const MISSING_TEXT = "無成交價,市價鈕鎖定";
const BUY_LOCKED_TEXT = "無券當沖不可買進";
/** 現股:群益 `nSpecialTradeType=1` 真市價,估價只餵名目金額閘(KL-1)。 */
const STOCK_OK_TEXT = "以市價送出:掃對手方(簿薄時可能以漲/跌停價成交);估價 = 最近成交價";
/** 個股期 / 期貨:後端 fut market 映射是 `"M"` literal(OrderPanel 在用),本路徑改由
 *  前端直送限價貼漲跌停 + IOC(D3a / current-state §3)。 */
const EDGE_OK_TEXT =
  "市價 = 限價貼漲/跌停 + IOC:掃對手方至成交完(簿薄時可能以漲/跌停價成交),餘量取消";

export interface MarketBtnState {
  buyDisabled: boolean;
  sellDisabled: boolean;
  buyTitle: string;
  sellTitle: string;
}

/** 市價買 / 市價賣兩顆鈕的 disabled + title。
 *
 *  優先序 **blocked > estimateMissing > buyLocked**:前兩者兩顆全鎖,無券只鎖買側。
 *  順序不可調 —— 估價缺時若讓「無券」文案蓋過去,使用者會以為只是買不了、賣得出去。 */
export function marketButtonState(input: {
  kind: "stock" | "stkfut" | "futures";
  /** 現股 last===null;個股期 last===null || edge===null;期貨 center/edge/contract 任一缺 */
  estimateMissing: boolean;
  /** 現股無券當沖(`tradeKind === "daytrade_sell"`) */
  buyLocked?: boolean;
  /** 個股期非標準契約單位(後端 `_stkfut_gates` 必拒) */
  blocked?: boolean;
}): MarketBtnState {
  if (input.blocked === true) {
    return {
      buyDisabled: true,
      sellDisabled: true,
      buyTitle: BLOCKED_TEXT,
      sellTitle: BLOCKED_TEXT,
    };
  }
  if (input.estimateMissing) {
    return {
      buyDisabled: true,
      sellDisabled: true,
      buyTitle: MISSING_TEXT,
      sellTitle: MISSING_TEXT,
    };
  }
  const okText = input.kind === "stock" ? STOCK_OK_TEXT : EDGE_OK_TEXT;
  const buyLocked = input.buyLocked === true;
  return {
    buyDisabled: buyLocked,
    sellDisabled: false,
    buyTitle: buyLocked ? BUY_LOCKED_TEXT : okText,
    sellTitle: okText,
  };
}
