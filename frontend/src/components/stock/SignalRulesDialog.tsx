/** 訊號規則管理 Dialog(signal-rules SC-7)。
 *
 *  dialog 樣板逐條沿用 `WatchlistManagerDialog`(showModal effect / display 隨 open 切 /
 *  原生 close 拉回 prop / m-auto)—— 那三個坑都是真瀏覽器實測踩出來的,見該檔註解。 */

import { useEffect, useRef, useState } from "react";

import {
  CDP_LEVELS,
  MAX_RULES,
  RULE_KINDS,
  errText,
  useDeleteRule,
  useSaveRule,
  type RuleDraft,
  type RuleKind,
  type SignalRule,
} from "@/hooks/useSignalRules";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<RuleKind, string> = {
  cdp_cross: "CDP 穿越",
  surge_crash: "爆拉爆跌",
  vol_burst: "爆量",
  limit_lock: "鎖漲跌停",
};

/** CDP 線顯示名。`cdp` 顯示「中軸」而不是「CDP」—— 與 `signal-model.LEVEL_LABEL` 同款。 */
const LEVEL_LABEL: Record<string, string> = {
  ah: "AH",
  nh: "NH",
  cdp: "中軸",
  nl: "NL",
  al: "AL",
};

interface ParamField {
  key: string;
  label: string;
  step: string;
}

/** 逐 kind 的參數欄位 —— 鍵集必須與後端 `PARAM_SPECS` **完全相同**(多鍵 / 缺鍵
 *  同樣是 INVALID_RULE)。`vol_burst.window_secs` 對到後端的 `surge_window_secs`,
 *  那是 detector 的共用欄,per-rule detector 讓兩者得以各自獨立。 */
const PARAM_FIELDS: Record<RuleKind, readonly ParamField[]> = {
  cdp_cross: [
    { key: "rearm_ticks", label: "重新武裝 tick 數", step: "1" },
    // 距離門檻(tick)與時間門檻(秒)是同一個 rearm 的兩半 —— 擺在一起才看得出
    // 「離線 N tick 且撐滿 M 秒才解除」是一句話,不是兩條獨立設定
    { key: "rearm_dwell_secs", label: "線外駐留秒數", step: "1" },
  ],
  surge_crash: [
    { key: "pct", label: "漲跌幅 %", step: "0.1" },
    { key: "window_secs", label: "時間窗(秒)", step: "1" },
  ],
  vol_burst: [
    { key: "ratio", label: "量能倍率", step: "0.1" },
    { key: "window_secs", label: "時間窗(秒)", step: "1" },
    { key: "min_elapsed_min", label: "開盤後最少分鐘", step: "1" },
    { key: "min_window_lots", label: "窗內最少張數", step: "1" },
    { key: "min_day_lots", label: "當日最少張數", step: "1" },
  ],
  limit_lock: [],
};

const PARAM_DEFAULTS: Record<RuleKind, Record<string, string>> = {
  cdp_cross: { rearm_ticks: "2", rearm_dwell_secs: "300" },
  surge_crash: { pct: "1.5", window_secs: "60" },
  vol_burst: {
    ratio: "3",
    window_secs: "60",
    min_elapsed_min: "5",
    min_window_lots: "100",
    min_day_lots: "500",
  },
  limit_lock: {},
};

const COOLDOWN_MIN = 60;
const COOLDOWN_MAX = 86_400;

/** 數字欄位一律以**字串**存在表單裡:存 number 的話「清空欄位重打」會在中途變成
 *  0 或 NaN,使用者看到的值跳來跳去;轉型與值域檢查全收在送出那一刻。 */
interface FormState {
  id?: string;
  name: string;
  kind: RuleKind;
  enabled: boolean;
  notify_discord: boolean;
  cooldown: string;
  params: Record<string, string>;
  levels: string[];
}

function blankForm(): FormState {
  return {
    name: "",
    kind: "cdp_cross",
    enabled: true,
    notify_discord: true,
    cooldown: "300",
    params: { ...PARAM_DEFAULTS.cdp_cross },
    levels: [...CDP_LEVELS],
  };
}

function toForm(rule: SignalRule): FormState {
  const params: Record<string, string> = {};
  for (const field of PARAM_FIELDS[rule.kind]) {
    params[field.key] = String(rule.params[field.key] ?? PARAM_DEFAULTS[rule.kind][field.key] ?? "");
  }
  return {
    id: rule.id,
    name: rule.name,
    kind: rule.kind,
    enabled: rule.enabled,
    notify_discord: rule.notify_discord,
    cooldown: String(rule.cooldown_secs),
    params,
    levels: [...rule.cdp_levels],
  };
}

function num(value: number | undefined): string {
  return value === undefined ? "-" : String(value);
}

/** 列表用的一行摘要:規則之間的差別幾乎都在參數上,只印名稱與種類等於看不出差異。 */
function ruleSummary(rule: SignalRule): string {
  const cooldown = `冷卻 ${rule.cooldown_secs} 秒`;
  const p = rule.params;
  if (rule.kind === "cdp_cross") {
    const levels = rule.cdp_levels.map((x) => LEVEL_LABEL[x] ?? x.toUpperCase()).join("+");
    return `${levels} · 重新武裝 ${num(p.rearm_ticks)} tick · 駐留 ${num(p.rearm_dwell_secs)} 秒 · ${cooldown}`;
  }
  if (rule.kind === "surge_crash") {
    return `±${num(p.pct)}% / ${num(p.window_secs)} 秒 · ${cooldown}`;
  }
  if (rule.kind === "vol_burst") {
    return `${num(p.ratio)} 倍 / ${num(p.window_secs)} 秒 · 開盤後 ${num(p.min_elapsed_min)} 分 · ${cooldown}`;
  }
  return cooldown;
}

/** 參數數字欄位。真元件而不是「回傳 JSX 的函式」—— 函式呼叫產出的 JSX 掛在呼叫端
 *  的 element type 底下,React 無法以元件為單位 reconcile,DevTools 也看不到它。 */
function NumberField({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: string;
  step: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      <span className="shrink-0">{label}</span>
      <input
        type="number"
        step={step}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-24 rounded border border-line bg-bg px-1 py-0.5 text-right font-mono text-xs text-ink outline-none focus:border-accent"
      />
    </label>
  );
}

interface Props {
  open: boolean;
  rules: SignalRule[];
  /** rules GET 失敗:空陣列有兩種意思,不分開的話「載入失敗」長得像「零規則」。 */
  rulesError: boolean;
  onClose: () => void;
}

export function SignalRulesDialog({ open, rules, rulesError, onClose }: Props) {
  const save = useSaveRule();
  const del = useDeleteRule();
  const dlgRef = useRef<HTMLDialogElement | null>(null);
  /** null = 顯示列表;非 null = 顯示編輯表單(新增或編輯) */
  const [form, setForm] = useState<FormState | null>(null);
  /** 二次確認中的規則 id —— 刪除規則不可逆(cooldown/latch 也一併沒了) */
  const [confirming, setConfirming] = useState<string | null>(null);
  /** 前端就擋下來的錯誤:存**已翻好的文案**(mutation 那條才是錯誤碼,要過 `errText`)
   *  —— 本地錯誤要能比「規則設定不合法」更精確地指出是哪一格。 */
  const [localError, setLocalError] = useState<string | null>(null);

  // 開關只走這一條路徑,`open` **不進 JSX**(React 在 commit 階段寫入的 open 屬性會讓
  // 之後的 showModal() 依標準拋 InvalidStateError,而 jsdom 沒有 showModal 會跳過
  // feature-detect → 測試全綠、真瀏覽器第一次點就白畫面)。見 WatchlistManagerDialog。
  useEffect(() => {
    const el = dlgRef.current;
    if (el === null) return;
    if (typeof el.showModal === "function") {
      if (open) {
        if (!el.open) el.showModal();
      } else {
        el.close();
      }
      return;
    }
    if (open) el.setAttribute("open", "");
    else el.removeAttribute("open");
  }, [open]);

  // 常駐掛載(呼叫端只切 `open`)→ 每次開啟都要把暫態歸零,否則上次編輯到一半的
  // 表單 / 刪除確認 / 錯誤文案會殘留到下一次開啟。render 期間調整 state 的官方
  // pattern,不用 effect(專案有 react-you-might-not-need-an-effect lint)。
  const [prevOpen, setPrevOpen] = useState(open);
  if (prevOpen !== open) {
    setPrevOpen(open);
    if (open) {
      setForm(null);
      setConfirming(null);
      setLocalError(null);
    }
  }

  function patch(next: Partial<FormState>): void {
    setForm((cur) => (cur === null ? cur : { ...cur, ...next }));
  }

  /** 換種類 = 換一整組參數鍵:沿用舊 kind 的 params 會讓後端以「多鍵 / 缺鍵」拒收,
   *  而畫面上完全看不出來是哪個欄位的錯。 */
  function changeKind(kind: RuleKind): void {
    patch({
      kind,
      params: { ...PARAM_DEFAULTS[kind] },
      levels: kind === "cdp_cross" ? [...CDP_LEVELS] : [],
    });
  }

  /** 參數欄位一律走 functional updater(review A6(4)):`{...form.params}` 讀的是
   *  render 當下那份快照,同一輪內連改兩個欄位(受控 input 的 change 可以連發)時
   *  後寫的會把前一次的改動蓋掉,而畫面只是「有一格沒改到」。 */
  function patchParam(key: string, value: string): void {
    setForm((cur) => (cur === null ? cur : { ...cur, params: { ...cur.params, [key]: value } }));
  }

  function toggleLevel(level: string): void {
    setForm((cur) =>
      cur === null
        ? cur
        : {
            ...cur,
            levels: cur.levels.includes(level)
              ? cur.levels.filter((x) => x !== level)
              : [...cur.levels, level],
          },
    );
  }

  /** 送出前在本地擋掉「空欄 / 非數字」:那些送出去只會拿到一句 INVALID_RULE,
   *  使用者不知道是哪一格。各參數的值域仍以後端為準(前端不重抄一份會漂的表),
   *  唯獨冷卻秒數的界另外擋:它是每張表都有的欄位,且 `COOLDOWN_MIN/MAX` 已經為了
   *  input 的 min/max 抄在這裡了 —— 抄了卻不擋等於把 60/86400 當裝飾。 */
  function submit(): void {
    if (form === null) return;
    const name = form.name.trim();
    const fields = PARAM_FIELDS[form.kind];
    const params: Record<string, number> = {};
    let bad = name === "";

    const cooldown = Number(form.cooldown);
    if (form.cooldown.trim() === "" || !Number.isFinite(cooldown)) bad = true;
    else if (cooldown < COOLDOWN_MIN || cooldown > COOLDOWN_MAX) {
      setLocalError(`冷卻秒數須在 ${COOLDOWN_MIN}–${COOLDOWN_MAX} 之間`);
      return;
    }
    for (const field of fields) {
      const raw = form.params[field.key] ?? "";
      const value = Number(raw);
      if (raw.trim() === "" || !Number.isFinite(value)) bad = true;
      else params[field.key] = value;
    }
    // cdp_cross 一條線都沒勾 = 這條規則永遠不會發 —— 後端也拒
    if (form.kind === "cdp_cross" && form.levels.length === 0) bad = true;

    if (bad) {
      setLocalError(errText("INVALID_RULE"));
      return;
    }
    setLocalError(null);
    const draft: RuleDraft = {
      ...(form.id === undefined ? {} : { id: form.id }),
      name,
      kind: form.kind,
      enabled: form.enabled,
      notify_discord: form.notify_discord,
      cooldown_secs: cooldown,
      params,
      // 固定序(後端 CDP_LEVELS 同序),不是使用者的點擊序
      cdp_levels: form.kind === "cdp_cross" ? CDP_LEVELS.filter((x) => form.levels.includes(x)) : [],
    };
    save.mutate(draft, { onSuccess: () => setForm(null) });
  }

  const mutationError = save.error?.message ?? del.error?.message ?? null;
  const errorMessage =
    localError ?? (mutationError === null ? null : errText(mutationError));

  return (
    <dialog
      ref={dlgRef}
      data-testid="signal-rules-dialog"
      aria-label="訊號規則"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      // 原生 close 一定要拉回 prop:`display` 由 `open` prop 選,前提是「prop 永遠等於
      // 元素真實狀態」;瀏覽器對 modal dialog 的原生 cancel/close 擋不掉(見
      // WatchlistManagerDialog 的長註解)。
      onClose={() => {
        if (open) onClose();
      }}
      className={cn(
        open ? "flex" : "hidden",
        "m-auto h-[min(30rem,80vh)] w-[min(48rem,92vw)] flex-col overflow-hidden rounded border border-line bg-bg p-0 text-ink backdrop:bg-black/50",
      )}
    >
      {/* 關閉時不渲染內容:RTL 的 getAllBy* 不過濾隱藏元素,常駐渲染會讓呼叫端
          (訊號欄)的計數型斷言在 Dialog 掛上去之後莫名變多 */}
      {open ? (
        <>
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-line px-3">
            <h2 className="text-sm text-ink">訊號規則</h2>
            <button
              type="button"
              aria-label="關閉"
              onClick={onClose}
              className="px-1 text-xs text-ink-dim hover:text-ink"
            >
              ×
            </button>
          </div>

          {errorMessage !== null ? (
            <p className="shrink-0 border-b border-line px-3 py-1 text-xs text-bear">
              {errorMessage}
            </p>
          ) : null}

          {form === null ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <ul className="min-h-0 flex-1 overflow-y-auto">
                {rules.map((rule) => (
                  <li
                    key={rule.id}
                    data-testid={`rule-row-${rule.id}`}
                    className="flex items-center gap-2 border-b border-line px-3 py-2 text-xs"
                  >
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="flex items-baseline gap-2">
                        <span className={cn("truncate", rule.enabled ? "text-ink" : "text-ink-dim")}>
                          {rule.name}
                        </span>
                        <span className="shrink-0 rounded border border-line px-1 text-[0.625rem] text-ink-dim">
                          {KIND_LABEL[rule.kind]}
                        </span>
                        {rule.enabled ? null : (
                          <span className="shrink-0 text-[0.625rem] text-ink-dim">已停用</span>
                        )}
                        {rule.notify_discord ? (
                          <span className="shrink-0 text-[0.625rem] text-ink-dim">Discord</span>
                        ) : null}
                      </span>
                      <span className="truncate font-mono text-[0.625rem] text-ink-muted">
                        {ruleSummary(rule)}
                      </span>
                    </span>
                    {confirming === rule.id ? (
                      <>
                        <button
                          type="button"
                          aria-label={`確定刪除 ${rule.name}`}
                          onClick={() => {
                            setConfirming(null);
                            setLocalError(null);
                            del.mutate(rule.id);
                          }}
                          className="shrink-0 rounded border border-bear px-1 py-0.5 text-xs text-bear"
                        >
                          確定刪除
                        </button>
                        <button
                          type="button"
                          aria-label={`取消刪除 ${rule.name}`}
                          onClick={() => setConfirming(null)}
                          className="shrink-0 rounded border border-line px-1 py-0.5 text-xs text-ink-dim"
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          aria-label={`編輯 ${rule.name}`}
                          onClick={() => {
                            setLocalError(null);
                            setConfirming(null);
                            setForm(toForm(rule));
                          }}
                          className="shrink-0 rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
                        >
                          編輯
                        </button>
                        <button
                          type="button"
                          aria-label={`刪除 ${rule.name}`}
                          onClick={() => setConfirming(rule.id)}
                          className="shrink-0 rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:border-bear hover:text-bear"
                        >
                          ×
                        </button>
                      </>
                    )}
                  </li>
                ))}
                {/* 載入失敗 ≠ 零規則:後者會讓使用者照著空態去新增,而真值可能是
                    規則都好好跑著(新增只會撞名失敗) */}
                {rules.length === 0 ? (
                  <li className={cn("px-3 py-3 text-xs", rulesError ? "text-bear" : "text-ink-dim")}>
                    {rulesError
                      ? "規則載入失敗 —— 重新整理後再試"
                      : "尚無規則 —— 用下方「新增規則」建立第一條"}
                  </li>
                ) : null}
              </ul>
              <div className="shrink-0 border-t border-line p-2">
                <button
                  type="button"
                  // 上限是後端硬規則:按得下去只會拿到一句 INVALID_RULE,而畫面上
                  // 完全看不出「是因為滿了」
                  disabled={rules.length >= MAX_RULES}
                  title={
                    rules.length >= MAX_RULES ? `規則數已達上限 ${MAX_RULES} 條,請先刪除` : undefined
                  }
                  onClick={() => {
                    setLocalError(null);
                    setConfirming(null);
                    setForm(blankForm());
                  }}
                  className="rounded border border-line px-2 py-1 text-xs text-ink hover:border-accent disabled:opacity-50"
                >
                  新增規則
                </button>
              </div>
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
                <label className="flex items-center gap-1 text-xs text-ink-muted">
                  <span className="shrink-0">名稱</span>
                  <input
                    aria-label="名稱"
                    value={form.name}
                    onChange={(e) => patch({ name: e.target.value })}
                    className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-xs text-ink outline-none focus:border-accent"
                  />
                </label>

                <label className="flex items-center gap-1 text-xs text-ink-muted">
                  <span className="shrink-0">種類</span>
                  <select
                    aria-label="種類"
                    value={form.kind}
                    onChange={(e) => changeKind(e.target.value as RuleKind)}
                    className="rounded border border-line bg-bg px-1 py-1 text-xs text-ink outline-none focus:border-accent"
                  >
                    {RULE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {KIND_LABEL[kind]}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="flex flex-wrap gap-3">
                  {PARAM_FIELDS[form.kind].map((field) => (
                    <NumberField
                      key={field.label}
                      label={field.label}
                      value={form.params[field.key] ?? ""}
                      step={field.step}
                      onChange={(v) => patchParam(field.key, v)}
                    />
                  ))}
                </div>

                {form.kind === "cdp_cross" ? (
                  <div className="flex flex-wrap items-center gap-3 text-xs text-ink-muted">
                    <span className="shrink-0">監看線</span>
                    {CDP_LEVELS.map((level) => (
                      <label key={level} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          aria-label={`監看 ${LEVEL_LABEL[level]}`}
                          checked={form.levels.includes(level)}
                          onChange={() => toggleLevel(level)}
                        />
                        <span>{LEVEL_LABEL[level]}</span>
                      </label>
                    ))}
                  </div>
                ) : null}

                <label className="flex items-center gap-1 text-xs text-ink-muted">
                  <span className="shrink-0">冷卻秒數</span>
                  <input
                    type="number"
                    aria-label="冷卻秒數"
                    min={COOLDOWN_MIN}
                    max={COOLDOWN_MAX}
                    step="1"
                    value={form.cooldown}
                    onChange={(e) => patch({ cooldown: e.target.value })}
                    className="w-24 rounded border border-line bg-bg px-1 py-0.5 text-right font-mono text-xs text-ink outline-none focus:border-accent"
                  />
                </label>

                <div className="flex flex-wrap gap-4 text-xs text-ink-muted">
                  <label className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      aria-label="啟用"
                      checked={form.enabled}
                      onChange={(e) => patch({ enabled: e.target.checked })}
                    />
                    <span>啟用</span>
                  </label>
                  <label className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      aria-label="Discord 通知"
                      checked={form.notify_discord}
                      onChange={(e) => patch({ notify_discord: e.target.checked })}
                    />
                    <span>Discord 通知</span>
                  </label>
                </div>
              </div>

              <div className="flex shrink-0 gap-2 border-t border-line p-2">
                <button
                  type="button"
                  disabled={save.isPending}
                  onClick={submit}
                  className="rounded border border-accent px-2 py-1 text-xs text-accent disabled:opacity-50"
                >
                  儲存
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setForm(null);
                    setLocalError(null);
                  }}
                  className="rounded border border-line px-2 py-1 text-xs text-ink-dim hover:text-ink"
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </>
      ) : null}
    </dialog>
  );
}
