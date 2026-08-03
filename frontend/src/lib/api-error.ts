/** 非 2xx 回應 → 錯誤碼字串(跨檔契約:`{ detail: { error } }`)。
 *
 *  非 JSON body、或 body 形狀不合(存取 detail 就炸)一律退回 `HTTP_<status>` ——
 *  這裡吐出的字串是畫面文案的來源(errText / tradeErrorText),不可讓解析失敗
 *  變成拋出去的 TypeError。 */
export async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: { error?: string } };
    return body.detail?.error ?? `HTTP_${res.status}`;
  } catch {
    return `HTTP_${res.status}`;
  }
}
