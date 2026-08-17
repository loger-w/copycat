import { describe, expect, it, vi } from "vitest";

import { settleFlashSend, type FlashSendCtx } from "@/lib/flash-send";

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

  it("throw 非 Error 值 → String(err) 進 tradeErrorText", async () => {
    const { ctx, showHint } = ctxOf(true);
    settleFlashSend(rejectWith("怪東西"), ctx);
    await flush();
    expect(showHint.mock.calls).toEqual([["怪東西"]]);
  });
});
