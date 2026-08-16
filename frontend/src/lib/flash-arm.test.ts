import { describe, expect, it } from "vitest";

import { ARM_IDLE_MS, initialArm, reduceArm, type ArmState } from "@/lib/flash-arm";

describe("武裝開關狀態機", () => {
  it("預設未武裝", () => expect(initialArm().armed).toBe(false));

  it("toggle 開/關,開時失敗計數歸零", () => {
    let s = reduceArm({ armed: false, locked: false, failStreak: 2 }, { type: "toggle" });
    expect(s).toEqual({ armed: true, locked: false, failStreak: 0 });
    s = reduceArm(s, { type: "toggle" });
    expect(s.armed).toBe(false);
  });

  it("換標的 / 連線斷 / 閒置逾時 → 解除武裝", () => {
    const armed = { armed: true, locked: false, failStreak: 0 };
    for (const t of ["symbol_changed", "conn_lost", "idle_timeout"] as const) {
      expect(reduceArm(armed, { type: t }).armed).toBe(false);
    }
  });

  it("連續 3 次送單失敗 → 自動解除;成功會重置計數", () => {
    let s = { armed: true, locked: false, failStreak: 0 };
    s = reduceArm(s, { type: "send_fail" });
    s = reduceArm(s, { type: "send_fail" });
    expect(s.armed).toBe(true);
    s = reduceArm(s, { type: "send_ok" }); // 重置
    s = reduceArm(s, { type: "send_fail" });
    s = reduceArm(s, { type: "send_fail" });
    expect(s.armed).toBe(true); // 只累積 2
    s = reduceArm(s, { type: "send_fail" });
    expect(s.armed).toBe(false); // 第 3 次 → 解除
    expect(s.failStreak).toBe(0);
  });

  it("disarm 只會解除、不會反向武裝(與 toggle 的差異所在)", () => {
    expect(
      reduceArm({ armed: true, locked: false, failStreak: 1 }, { type: "disarm" }).armed,
    ).toBe(false);
    // 已解除時冪等 — 解除列/Esc 連按絕不能把狀態翻回武裝
    expect(
      reduceArm({ armed: false, locked: false, failStreak: 0 }, { type: "disarm" }).armed,
    ).toBe(false);
  });

  it("閒置時限 = 5 分鐘", () => expect(ARM_IDLE_MS).toBe(5 * 60 * 1000));
});

// 鎖定 = 「換標的 / 換梯 / 閒置都不解除」的武裝。放大了武裝的時間 × 空間範圍,所以
// **清除路徑必須比進入路徑寬**:斷線 / 連 3 敗 / Esc / 手動解除一律連 locked 一起清。
describe("武裝鎖定(R5)", () => {
  const ARMED_LOCKED = { armed: true, locked: true, failStreak: 0 } as const;

  it("預設未鎖定", () => expect(initialArm().locked).toBe(false));

  it("lock = 一鍵「武裝 + 鎖定」且失敗計數歸零(同 toggle 武裝語意)", () => {
    expect(reduceArm({ armed: false, locked: false, failStreak: 2 }, { type: "lock" })).toEqual({
      armed: true,
      locked: true,
      failStreak: 0,
    });
  });

  it("unlock 只收回「免解除」特權,武裝保留(要解除有解除鈕 / Esc)", () => {
    expect(reduceArm(ARMED_LOCKED, { type: "unlock" })).toEqual({
      armed: true,
      locked: false,
      failStreak: 0,
    });
  });

  it("鎖定中:換標的 / 閒置逾時 / 離開畫面 皆 no-op(state 原樣)", () => {
    for (const t of ["symbol_changed", "idle_timeout", "left_view"] as const) {
      expect(reduceArm(ARMED_LOCKED, { type: t })).toEqual(ARMED_LOCKED);
    }
  });

  it("鎖定中:斷線 / 手動解除 / 按解除鈕 一律清 armed **且**清 locked", () => {
    for (const t of ["conn_lost", "disarm", "toggle"] as const) {
      const s = reduceArm(ARMED_LOCKED, { type: t });
      expect(s.armed).toBe(false);
      expect(s.locked).toBe(false);
    }
  });

  it("鎖定中連 3 次送單失敗 → 解除且清鎖定", () => {
    let s: ArmState = ARMED_LOCKED;
    s = reduceArm(s, { type: "send_fail" });
    s = reduceArm(s, { type: "send_fail" });
    expect(s).toEqual({ armed: true, locked: true, failStreak: 2 }); // 鎖定態 failStreak 照累積
    s = reduceArm(s, { type: "send_fail" });
    expect(s).toEqual({ armed: false, locked: false, failStreak: 0 });
  });

  it("鎖定中 send_ok 不動鎖定,只歸零失敗計數", () => {
    expect(reduceArm({ ...ARMED_LOCKED, failStreak: 2 }, { type: "send_ok" })).toEqual(
      ARMED_LOCKED,
    );
  });

  // 未鎖定的 left_view = 舊「unmount 讓 state 消滅」語意:連 failStreak 一起歸零(E-6)
  it("未鎖定時 left_view 整份重置(等價舊 unmount)", () => {
    expect(reduceArm({ armed: true, locked: false, failStreak: 2 }, { type: "left_view" })).toEqual(
      initialArm(),
    );
  });
});
