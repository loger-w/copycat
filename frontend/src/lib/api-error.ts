/** 非 2xx 回應的 detail 形狀(跨檔契約:`{ detail: { error } }`)。
 *  `reason` / `err_code` 是 capital 路的擴充欄(ORDER_BLOCKED / BROKER_REJECTED)。 */
export interface ErrorDetail {
  error?: string;
  reason?: string;
  err_code?: string;
}

/** 非 2xx 回應 → detail 物件(缺 / 解析失敗 / 形狀不合一律 `{}`,never-raise)。
 *
 *  非 JSON body、或 body 形狀不合(存取 detail 就炸)一律退回空物件 ——
 *  這裡的產物是畫面文案的來源(errText / tradeErrorText),不可讓解析失敗
 *  變成拋出去的 TypeError。
 *
 *  detail 實際上不保證是物件:FastAPI 422 回 array、Starlette 404 回字串。
 *  runtime 守門讓宣告的 `ErrorDetail` 誠實(否則字串 / array 會原樣外洩給
 *  呼叫端,而型別上看起來是物件)。 */
export async function parseErrorDetail(res: Response): Promise<ErrorDetail> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    const d: unknown = body.detail;
    return typeof d === "object" && d !== null && !Array.isArray(d) ? (d as ErrorDetail) : {};
  } catch {
    return {};
  }
}

/** 非 2xx 回應 → 錯誤碼字串;detail 沒帶 error 時退回 `HTTP_<status>`。 */
export async function parseError(res: Response): Promise<string> {
  const detail = await parseErrorDetail(res);
  return detail.error ?? `HTTP_${res.status}`;
}
