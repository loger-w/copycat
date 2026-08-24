/** 訊號規則的 per-kind 參數欄位表(自 `components/stock/SignalRulesDialog.tsx` 搬出)。
 *
 *  搬出來的理由有兩個:元件檔只放元件(react-doctor `only-export-components`),以及
 *  這張表是**跨語言契約的一半**,parity 測試要拿得到它而不必掛載 Dialog。 */
import type { RuleKind } from "@/hooks/useSignalRules";

export interface ParamField {
  key: string;
  label: string;
  /** `<input type="number">` 的 step(顯示精度,不是值域) */
  step: string;
  /** 閉區間值域,**與後端 `copycat/signal_rules.py::PARAM_SPECS` 同源**(N055)。
   *  重抄一份會漂,而漂掉沒有錯誤訊號:前端寬於後端 → 使用者只拿得到一句
   *  INVALID_RULE(N055 修的就是這個);前端窄於後端 → 合法值被擋掉,畫面上的說明
   *  還寫著錯的界。所以以共用 fixture `tests/fixtures/signal_param_specs.json` 釘住兩邊
   *  (`signal-param-parity.test.ts` + `tests/test_signal_rules.py`)。 */
  min: number;
  max: number;
}

/** 逐 kind 的參數欄位 —— 鍵集必須與後端 `PARAM_SPECS` **完全相同**(多鍵 / 缺鍵
 *  同樣是 INVALID_RULE)。`vol_burst.window_secs` 對到後端的 `surge_window_secs`,
 *  那是 detector 的共用欄,per-rule detector 讓兩者得以各自獨立。 */
export const PARAM_FIELDS: Record<RuleKind, readonly ParamField[]> = {
  cdp_cross: [
    { key: "rearm_ticks", label: "重新武裝 tick 數", step: "1", min: 0, max: 50 },
    // 距離門檻(tick)與時間門檻(秒)是同一個 rearm 的兩半 —— 擺在一起才看得出
    // 「離線 N tick 且撐滿 M 秒才解除」是一句話,不是兩條獨立設定
    { key: "rearm_dwell_secs", label: "線外駐留秒數", step: "1", min: 0, max: 3600 },
  ],
  surge_crash: [
    { key: "pct", label: "漲跌幅 %", step: "0.1", min: 0.1, max: 50 },
    { key: "window_secs", label: "時間窗(秒)", step: "1", min: 10, max: 3600 },
  ],
  vol_burst: [
    { key: "ratio", label: "量能倍率", step: "0.1", min: 1, max: 100 },
    { key: "window_secs", label: "時間窗(秒)", step: "1", min: 10, max: 3600 },
    { key: "min_elapsed_min", label: "開盤後最少分鐘", step: "1", min: 0, max: 240 },
    { key: "min_window_lots", label: "窗內最少張數", step: "1", min: 0, max: 1e6 },
    { key: "min_day_lots", label: "當日最少張數", step: "1", min: 0, max: 1e7 },
  ],
  limit_lock: [],
};
