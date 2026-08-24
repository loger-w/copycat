// 閃電武裝開關狀態機。武裝=點價直送(無確認彈窗),是唯一繞過二次確認的路徑,
// 所以解除要寬鬆觸發:換標的/斷線/閒置 5 分鐘/連 3 次失敗。切分頁 = ladder 卸載 → `left_view`
// (state 已上提到 RightRail,不再靠 unmount 自然消失 —— 見 hooks/useFlashArm.ts)。
//
// **鎖定(locked)**= 使用者明示「我要一路盯著下單」:換標的 / 換梯 / 閒置都不解除。
// 它放大了武裝的時間 × 空間範圍,所以進入路徑只有一顆鈕,而**清除路徑一條都不減**:
// 斷線 / 連 3 敗 / Esc / 手動解除一律連 locked 一起清(清得比進入寬,是刻意的不對稱)。
export const ARM_IDLE_MS = 5 * 60 * 1000;
const FAIL_LIMIT = 3;

/** 鎖定鈕的常態 tooltip。放這裡不放元件:LadderView(現股 / 個股期)與 FuturesLadder
 *  自帶的第三份武裝列 JSX 是兩處渲染點,文案漂掉時畫面不會有任何訊號。 */
export const LOCK_TITLE =
  "鎖定:換標的 / 換梯 / 閒置不解除;斷線 / 連 3 敗 / Esc / 解除仍會解除";
/** capital WS 非 `open` 時鎖定鈕 disabled 的說明(SC-13)。 */
export const LOCK_WS_TITLE = "連線未就緒,無法鎖定";
/** capital WS 非 `open` 時**武裝**鈕 disabled 的說明(N081)。
 *  與 `LOCK_WS_TITLE` 分開兩句:同一列上兩顆鈕、兩種動作,共用一句話會讓使用者
 *  以為自己按錯了哪一顆。 */
export const ARM_WS_TITLE = "連線未就緒,無法武裝";

export interface ArmState {
  armed: boolean;
  /** 鎖定中:換標的 / 換梯 / 閒置不解除。恆隨 armed 一起被清,不會有 armed=false + locked=true。 */
  locked: boolean;
  failStreak: number;
}

export type ArmEvent =
  | { type: "toggle" }
  | { type: "disarm" }
  | { type: "symbol_changed" }
  | { type: "conn_lost" }
  | { type: "idle_timeout" }
  | { type: "send_ok" }
  | { type: "send_fail" }
  /** ladder 離開畫面(卸載)。state 上提到 RightRail 後 unmount 不再消滅它,
   *  這個事件就是舊「unmount = state 消失」語意的顯式版本。 */
  | { type: "left_view" }
  /** 一鍵「武裝 + 鎖定」 */
  | { type: "lock" }
  /** 只收回「免解除」特權,武裝保留(要解除有解除鈕 / Esc,兩顆鈕語意各自單一) */
  | { type: "unlock" };

export function initialArm(): ArmState {
  return { armed: false, locked: false, failStreak: 0 };
}

export function reduceArm(s: ArmState, e: ArmEvent): ArmState {
  switch (e.type) {
    case "toggle":
      // 解除方向連 locked 一起清:解除鈕是鎖定態的主要 UI 出口,留著 locked 等於解不掉
      return s.armed
        ? { armed: false, locked: false, failStreak: 0 }
        : { armed: true, locked: false, failStreak: 0 };
    case "lock":
      // 鎖定是一次新的武裝意圖 → failStreak 歸零(沿 toggle 武裝語意)
      return { armed: true, locked: true, failStreak: 0 };
    case "unlock":
      return { ...s, locked: false };
    case "disarm":
    case "conn_lost":
      return { ...s, armed: false, locked: false };
    case "symbol_changed":
    case "idle_timeout":
      return s.locked ? s : { ...s, armed: false };
    case "left_view":
      return s.locked ? s : initialArm();
    case "send_ok":
      return { ...s, failStreak: 0 };
    case "send_fail": {
      // 鎖定態的 failStreak **跨梯累積、不隨換梯歸零**(E-7):換梯歸零的話,一直換梯
      // 就能無限重試,而連 3 敗自動解除正是為了擋「後端在拒單、使用者在連點」。
      const n = s.failStreak + 1;
      if (n >= FAIL_LIMIT) return { armed: false, locked: false, failStreak: 0 };
      return { ...s, failStreak: n };
    }
  }
}
