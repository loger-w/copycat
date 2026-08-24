import { describe, expect, it, vi } from "vitest";

import {
  BLOCKED_TEXT,
  flashSource,
  marketButtonState,
  settleFlashSend,
  type FlashSendCtx,
} from "@/lib/flash-send";

const flush = () => new Promise<void>((r) => setTimeout(r, 0));

function ctxOf(alive = true) {
  const dispatch = vi.fn();
  const showHint = vi.fn();
  const ctx: FlashSendCtx = {
    alive: () => alive,
    dispatch,
    showHint,
    okText: "已送 2330 市價買 × 1",
  };
  return { ctx, dispatch, showHint };
}

/** 拋非 Error 值的來源(`String(err)` 分支);繞開 reject literal 的 lint 規則。 */
function rejectWith(v: unknown): Promise<{ ok: boolean; message: string }> {
  return Promise.resolve().then<{ ok: boolean; message: string }>(() => {
    throw v;
  });
}

describe("settleFlashSend 閃電送單尾段守門", () => {
  it("成功且元件仍在 → send_ok + okText", async () => {
    const { ctx, dispatch, showHint } = ctxOf(true);
    settleFlashSend(Promise.resolve({ ok: true, message: "" }), ctx);
    await flush();
    expect(dispatch.mock.calls).toEqual([[{ type: "send_ok" }]]);
    expect(showHint.mock.calls).toEqual([["已送 2330 市價買 × 1"]]);
  });

  it("成功但元件已卸載 → 不 dispatch、不 hint(遲到的成功不洗斷路器)", async () => {
    const { ctx, dispatch, showHint } = ctxOf(false);
    settleFlashSend(Promise.resolve({ ok: true, message: "" }), ctx);
    await flush();
    expect(dispatch).not.toHaveBeenCalled();
    expect(showHint).not.toHaveBeenCalled();
  });

  it("ok:false → 無條件 send_fail + message(卸載後照樣計數)", async () => {
    const { ctx, dispatch, showHint } = ctxOf(false);
    settleFlashSend(Promise.resolve({ ok: false, message: "群益拒單" }), ctx);
    await flush();
    expect(dispatch.mock.calls).toEqual([[{ type: "send_fail" }]]);
    expect(showHint.mock.calls).toEqual([["群益拒單"]]);
  });

  it("ok:false 且 message 空 → hint「送單失敗」", async () => {
    const { ctx, showHint } = ctxOf(true);
    settleFlashSend(Promise.resolve({ ok: false, message: "" }), ctx);
    await flush();
    expect(showHint.mock.calls).toEqual([["送單失敗"]]);
  });

  it("throw → 無條件 send_fail + tradeErrorText 繁中文案", async () => {
    const { ctx, dispatch, showHint } = ctxOf(false);
    settleFlashSend(rejectWith(new Error("BROKER_REJECTED")), ctx);
    await flush();
    expect(dispatch.mock.calls).toEqual([[{ type: "send_fail" }]]);
    expect(showHint.mock.calls).toEqual([["券商拒單"]]);
  });

  /** IMPL-3:`.then().catch()` 串接下,成功分支自己拋的例外會落進 catch → 同一次送單
   *  既 send_ok 又 send_fail,武裝斷路器被一張**成功**的單往連敗推(第 3 次就自動解除)。 */
  it("成功分支的 showHint 拋 → dispatch 恰一次 send_ok,不得補 send_fail", async () => {
    const { ctx, dispatch, showHint } = ctxOf(true);
    showHint.mockImplementation(() => {
      throw new Error("setState 炸了");
    });
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    settleFlashSend(Promise.resolve({ ok: true, message: "" }), ctx);
    await flush();
    expect(dispatch.mock.calls).toEqual([[{ type: "send_ok" }]]);
    expect(showHint).toHaveBeenCalledTimes(1);
    // 不靜默:回呼自身的例外走 console.error(unhandled rejection 會炸掉整個測試檔)
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it("throw 非 Error 值 → String(err) 進 tradeErrorText", async () => {
    const { ctx, showHint } = ctxOf(true);
    settleFlashSend(rejectWith("怪東西"), ctx);
    await flush();
    expect(showHint.mock.calls).toEqual([["怪東西"]]);
  });
});

// ---------------------------------------------------------------------------
// 市價鈕三態(SC-6 / SC-7 / SC-8)。文案逐字鎖:title 是使用者按下「掃到成交」那一鍵
// 之前唯一的說明,而市價鈕是三梯上第一個「遠價 + 無確認框」的路徑(KL-3)。
// ---------------------------------------------------------------------------

/** 現股可用態(SC-8 後半):成交價 = 對手價,估價只餵金額閘(KL-1)。 */
const STOCK_OK = "以市價送出:掃對手方(簿薄時可能以漲/跌停價成交);估價 = 最近成交價";
/** 個股期 / 期貨可用態(SC-8 前半):限價貼漲跌停 + IOC(D3a)。 */
const EDGE_OK =
  "市價 = 限價貼漲/跌停 + IOC:掃對手方至成交完(簿薄時可能以漲/跌停價成交),餘量取消";
const MISSING = "無成交價,市價鈕鎖定";
const NO_SHORT = "無券當沖不可買進";

describe("marketButtonState 市價鈕三態", () => {
  it("BLOCKED_TEXT 常數字面值(StkfutLadder 與本檔同源)", () => {
    expect(BLOCKED_TEXT).toBe("此契約規格暫未開放下單");
  });

  it("現股可用 → 兩顆皆可按,title 為現股文案", () => {
    expect(marketButtonState({ kind: "stock", estimateMissing: false })).toEqual({
      buyDisabled: false,
      sellDisabled: false,
      buyTitle: STOCK_OK,
      sellTitle: STOCK_OK,
    });
  });

  it("個股期 / 期貨可用 → title 為貼漲跌停 + IOC 文案(兩 kind 同字串)", () => {
    expect(marketButtonState({ kind: "stkfut", estimateMissing: false })).toEqual({
      buyDisabled: false,
      sellDisabled: false,
      buyTitle: EDGE_OK,
      sellTitle: EDGE_OK,
    });
    expect(marketButtonState({ kind: "futures", estimateMissing: false })).toEqual({
      buyDisabled: false,
      sellDisabled: false,
      buyTitle: EDGE_OK,
      sellTitle: EDGE_OK,
    });
  });

  it("估價缺 → 三種 kind 皆兩顆 disabled + 鎖定文案(fail-safe)", () => {
    for (const kind of ["stock", "stkfut", "futures"] as const) {
      expect(marketButtonState({ kind, estimateMissing: true })).toEqual({
        buyDisabled: true,
        sellDisabled: true,
        buyTitle: MISSING,
        sellTitle: MISSING,
      });
    }
  });

  it("現股無券 → 只鎖買側,賣側維持可用態(SC-7)", () => {
    expect(marketButtonState({ kind: "stock", estimateMissing: false, buyLocked: true })).toEqual({
      buyDisabled: true,
      sellDisabled: false,
      buyTitle: NO_SHORT,
      sellTitle: STOCK_OK,
    });
  });

  it("blocked 契約 → 兩顆 disabled + BLOCKED_TEXT,且優先於估價缺", () => {
    expect(marketButtonState({ kind: "stkfut", estimateMissing: false, blocked: true })).toEqual({
      buyDisabled: true,
      sellDisabled: true,
      buyTitle: BLOCKED_TEXT,
      sellTitle: BLOCKED_TEXT,
    });
    expect(marketButtonState({ kind: "stkfut", estimateMissing: true, blocked: true })).toEqual({
      buyDisabled: true,
      sellDisabled: true,
      buyTitle: BLOCKED_TEXT,
      sellTitle: BLOCKED_TEXT,
    });
  });

  it("估價缺優先於無券:買側文案不得退成「無券」而讓人以為賣得出去", () => {
    expect(marketButtonState({ kind: "stock", estimateMissing: true, buyLocked: true })).toEqual({
      buyDisabled: true,
      sellDisabled: true,
      buyTitle: MISSING,
      sellTitle: MISSING,
    });
  });
});

// 🔴 N082:鎖定態(換標的 / 換梯 / 閒置都不解除武裝)是誤送風險最高的狀態,
// 而審計檔的 `source` 只有 panel / flash 兩值 —— 事後查「這張單是不是在鎖定態下按出去的」
// 沒有任何線索。值域擴一個,三座梯共用同一支(各寫一份必然漂成兩種字串)。
describe("flashSource(N082:鎖定態的稽核 source)", () => {
  it("未鎖定 → flash(既有值,不得改)", () => {
    expect(flashSource(false)).toBe("flash");
  });

  it("鎖定中 → flash-locked", () => {
    expect(flashSource(true)).toBe("flash-locked");
  });
});
