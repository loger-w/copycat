/** 閃電武裝狀態的共用 hook(自三座梯上提;flash-arm-lock 包 1)。
 *
 *  上提前:PriceLadder / StkfutLadder / FuturesLadder **各自**持有 `useReducer(reduceArm)`
 *  + 閒置計時 ref + Esc / conn_lost 監聽,而「離開畫面即解除武裝」靠元件 unmount 讓 state
 *  一起消滅(RightRail 對閃電 tab 的 ladder 一律條件 render;D-13)。
 *
 *  上提後 state 由 **RightRail** 持有 → ladder 卸載不再消滅 state,「離開畫面即解除」改由
 *  ladder 的卸載 effect 顯式 dispatch `left_view` 完成(語意與舊的 unmount 等價)。
 *
 *  `active=false` = ladder 拿到外部 `armCtl` 時的**本地備援**:reducer 仍建(型別與獨立
 *  使用路徑齊全),但不掛 Esc / conn_lost 監聽、`touch` 不排計時 —— 同一個畫面上有兩份
 *  window 監聽的話,一次 Esc 會被兩個 reducer 各收一遍。
 */
import { useCallback, useEffect, useReducer, useRef, type Dispatch } from "react";

import { useCapitalWsStatus, type WsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS, initialArm, reduceArm, type ArmEvent, type ArmState } from "@/lib/flash-arm";

export interface FlashArmControl {
  state: ArmState;
  /** **useReducer 的原始 dispatch**,identity 恆定。ladder 的 `left_view` 卸載 effect 以它
   *  作 deps —— 包裝一層(例如依 `active` 分支)會讓 identity 每 render 都變,cleanup 於是
   *  每次 re-render 都跑一次 = 每收一則報價就解除一次武裝。 */
  dispatch: Dispatch<ArmEvent>;
  /** 閒置計時重新起算。identity 恆定(`useCallback([])` + timer ref),同上理由。 */
  touch: () => void;
  /** capital WS 連線狀態(鎖定鈕 disabled 判定等;讀自 module store)。 */
  wsStatus: WsStatus;
}

export function useFlashArm(active = true): FlashArmControl {
  const [state, dispatch] = useReducer(reduceArm, undefined, initialArm);
  const idleTimer = useRef<number | undefined>(undefined);
  // touch 的 identity 必須恆定 → `active` 只能經 ref 讀,不能進 useCallback deps
  const activeRef = useRef(active);
  activeRef.current = active;

  const wsStatus = useCapitalWsStatus();

  const touch = useCallback(() => {
    window.clearTimeout(idleTimer.current);
    if (!activeRef.current) return;
    idleTimer.current = window.setTimeout(() => dispatch({ type: "idle_timeout" }), ARM_IDLE_MS);
  }, []);

  // 自動解除:capital WS 斷線
  useEffect(() => {
    if (!active) return;
    if (wsStatus === "closed") dispatch({ type: "conn_lost" });
  }, [active, wsStatus]);

  // Esc = 鍵盤解除(只在武裝期間掛 window 監聽)
  useEffect(() => {
    if (!active || !state.armed) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") dispatch({ type: "disarm" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, state.armed]);

  // unmount 清閒置計時器
  useEffect(() => {
    return () => window.clearTimeout(idleTimer.current);
  }, []);

  return { state, dispatch, touch, wsStatus };
}
