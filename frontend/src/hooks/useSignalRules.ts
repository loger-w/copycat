/** 訊號規則 CRUD(signal-rules design SC-7)。
 *
 *  真值在後端 `signal_rules.json`(重啟保留),前端只讀寫不快取到 localStorage ——
 *  規則同時管 Discord 推播與盤中評估,兩份來源會漂。
 *
 *  四鍵開關(`useSignalsConfig`)已退役:一條規則就是一顆 detector,開關 = 該條的
 *  `enabled`。「切開關」與「改參數」因此走同一條 PUT,不再有部分更新的第二條路。 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";

/** 與後端 `signal_rules.RULE_KINDS` 逐字對應(改一邊要改兩邊)。 */
export const RULE_KINDS = ["cdp_cross", "surge_crash", "vol_burst", "limit_lock"] as const;
export type RuleKind = (typeof RULE_KINDS)[number];

/** 與後端 `signal_rules.CDP_LEVELS` 同序 —— 送出的 `cdp_levels` 依此固定序,
 *  不用使用者的點擊序(後端會正規化,前後端不同序會讓 diff 看起來一直有變動)。 */
export const CDP_LEVELS = ["ah", "nh", "cdp", "nl", "al"] as const;

export interface SignalRule {
  id: string;
  name: string;
  kind: RuleKind;
  enabled: boolean;
  notify_discord: boolean;
  cooldown_secs: number;
  /** 鍵集依 kind(後端 `PARAM_SPECS`):多鍵 / 缺鍵一律 INVALID_RULE。 */
  params: Record<string, number>;
  /** cdp_cross 非空 ⊆ 五線;其他 kind 必空。 */
  cdp_levels: string[];
}

/** 送出用:新增沒有 id(由後端的單調計數配),編輯才有。 */
export type RuleDraft = Omit<SignalRule, "id"> & { id?: string };

const RULES_KEY = ["signal-rules"];
const RULES_URL = "/api/stock/signals/rules";

/** 錯誤碼中文文案(跨檔契約)。Dialog 與呼叫端共用**同一份**,複製兩份會漂。 */
export function errText(message: string): string {
  if (message === "INVALID_RULE") return "規則設定不合法";
  if (message === "RULE_NOT_FOUND") return "找不到該規則";
  if (message === "RULE_SAVE_FAILED") return "規則儲存失敗";
  return "儲存失敗";
}

async function fetchRules(): Promise<SignalRule[]> {
  const res = await fetch(RULES_URL);
  if (!res.ok) throw new Error(await parseError(res));
  // 缺 `rules` 欄退回空陣列而不是 undefined:消費端(rail / dialog)一律 `.map`,
  // 少了這步「成功之後才炸」——最難察覺的那種。
  return ((await res.json()) as { rules?: SignalRule[] }).rules ?? [];
}

export function useSignalRules() {
  return useQuery({ queryKey: RULES_KEY, queryFn: fetchRules, retry: 1 });
}

export function useSaveRule() {
  const queryClient = useQueryClient();
  return useMutation({
    /** 有 id → PUT 到該 id(**path 為準**,後端對 body 帶不一致 id 回 400);
     *  無 id → POST 新增。單一入口讓「切開關」與「編輯表單」走同一條路。 */
    mutationFn: async (rule: RuleDraft): Promise<SignalRule> => {
      const editing = rule.id !== undefined;
      const res = await fetch(editing ? `${RULES_URL}/${rule.id}` : RULES_URL, {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rule),
      });
      if (!res.ok) throw new Error(await parseError(res));
      return (await res.json()) as SignalRule;
    },
    // invalidate 而非 setQueryData:POST 的 id 是後端配的,PUT 也可能被正規化
    // (名稱 strip / levels 去重),回寫自己那份會讓畫面與真值悄悄分岔。
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ruleId: string): Promise<void> => {
      const res = await fetch(`${RULES_URL}/${ruleId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await parseError(res));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  });
}
