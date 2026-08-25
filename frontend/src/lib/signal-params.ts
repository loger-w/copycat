/** 訊號規則的 per-kind 參數欄位表(自 `components/stock/SignalRulesDialog.tsx` 搬出)。
 *
 *  搬出來的理由有兩個:元件檔只放元件(react-doctor `only-export-components`),以及
 *  這張表是**跨語言契約的一半**,parity 測試要拿得到它而不必掛載 Dialog。
 *
 *  review A8(#101 parity 補完)起,契約的另外幾格也住這裡:整數鍵(`integer`,對後端
 *  `INT_PARAM_KEYS`)、冷卻界(`COOLDOWN_MIN/MAX`,對後端同名常數)、以及**前端自己的**
 *  「新規則」預設值(`default`,後端沒有對應概念,不進 fixture,由 parity 測試釘「落在值域內、
 *  整數鍵為整數」)。預設值併進同一個物件而不是另立一張表:鍵集相同因此是型別事實,不是
 *  測試事實 —— 分居兩檔時漏改一鍵,「按新增 → 表單那格空白 → 泛用 INVALID_RULE」零訊號。 */
import type { RuleKind } from "@/hooks/useSignalRules";

/** `cooldown_secs` 的閉區間,**與後端 `copycat/signal_rules.py::COOLDOWN_MIN/MAX` 同源**,
 *  由 `tests/fixtures/signal_param_specs.json` 的 `cooldown` 釘住(兩邊 parity 各一條)。 */
export const COOLDOWN_MIN = 60;
export const COOLDOWN_MAX = 86_400;

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
  /** 後端 `INT_PARAM_KEYS`:非整數拒收(2.5 個 tick / 半張不存在)。前端送出前擋並指出欄位,
   *  否則使用者填 2.9 只拿到泛用 INVALID_RULE。同 fixture 的 `int_keys` 釘住。 */
  integer: boolean;
  /** 「新規則」表單初值(表單慣例:數字欄以字串存)。必須落在 [min, max],整數鍵須為整數。 */
  default: string;
}

/** 逐 kind 的參數欄位 —— 鍵集必須與後端 `PARAM_SPECS` **完全相同**(多鍵 / 缺鍵
 *  同樣是 INVALID_RULE)。`vol_burst.window_secs` 對到後端的 `surge_window_secs`,
 *  那是 detector 的共用欄,per-rule detector 讓兩者得以各自獨立。 */
export const PARAM_FIELDS: Record<RuleKind, readonly ParamField[]> = {
  cdp_cross: [
    { key: "rearm_ticks", label: "重新武裝 tick 數", step: "1", min: 0, max: 50, integer: true, default: "2" },
    // 距離門檻(tick)與時間門檻(秒)是同一個 rearm 的兩半 —— 擺在一起才看得出
    // 「離線 N tick 且撐滿 M 秒才解除」是一句話,不是兩條獨立設定
    { key: "rearm_dwell_secs", label: "線外駐留秒數", step: "1", min: 0, max: 3600, integer: false, default: "300" },
  ],
  surge_crash: [
    { key: "pct", label: "漲跌幅 %", step: "0.1", min: 0.1, max: 50, integer: false, default: "1.5" },
    { key: "window_secs", label: "時間窗(秒)", step: "1", min: 10, max: 3600, integer: false, default: "60" },
  ],
  vol_burst: [
    { key: "ratio", label: "量能倍率", step: "0.1", min: 1, max: 100, integer: false, default: "3" },
    { key: "window_secs", label: "時間窗(秒)", step: "1", min: 10, max: 3600, integer: false, default: "60" },
    { key: "min_elapsed_min", label: "開盤後最少分鐘", step: "1", min: 0, max: 240, integer: false, default: "5" },
    { key: "min_window_lots", label: "窗內最少張數", step: "1", min: 0, max: 1e6, integer: true, default: "100" },
    { key: "min_day_lots", label: "當日最少張數", step: "1", min: 0, max: 1e7, integer: true, default: "500" },
  ],
  limit_lock: [],
};

/** 「新規則」表單的 params 初值(逐欄 `default`)。 */
export function paramDefaults(kind: RuleKind): Record<string, string> {
  return Object.fromEntries(PARAM_FIELDS[kind].map((f) => [f.key, f.default]));
}
