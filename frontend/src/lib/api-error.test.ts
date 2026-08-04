import { describe, expect, it } from "vitest";

import { parseError, parseErrorDetail } from "@/lib/api-error";

/** 跨檔契約(CLAUDE.md §4)`{ detail: { error } }` 的**唯一**解析點,而它吐出的字串
 *  直接是畫面文案來源 —— 解析失敗必須降級成 `HTTP_<status>`,不可讓 TypeError 逃出去
 *  (逃出去的樣態是錯誤畫面自己也炸掉,使用者連 status code 都看不到)。
 *  原本只有各 hook 的整合測試間接覆蓋,這裡直接釘三種 body 形狀。 */
describe("parseError", () => {
  it("非 JSON body → HTTP_<status>(res.json() 拋出時的降級)", async () => {
    const res = new Response("<html>502 Bad Gateway</html>", { status: 500 });
    await expect(parseError(res)).resolves.toBe("HTTP_500");
  });

  it("契約形狀 { detail: { error } } → 錯誤碼原樣", async () => {
    const res = new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 });
    await expect(parseError(res)).resolves.toBe("NOT_READY");
  });

  it("detail 是字串(FastAPI 預設 404 形狀)→ HTTP_404,不把 detail 當錯誤碼", async () => {
    // `"Not Found".error` 是 undefined 不是拋錯 —— 這條路徑走的是 `??` 而非 catch,
    // 兩者都要回 HTTP_<status>,但只有這條會在 body 合法時觸發。
    const res = new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    await expect(parseError(res)).resolves.toBe("HTTP_404");
  });
});

/** `parseErrorDetail` 是本分支新 export(原本只是 parseError 的內部步驟),
 *  對外承諾的型別是 `ErrorDetail` 物件 —— 但 detail 實際上可能是字串
 *  (Starlette 404)或 array(FastAPI 422 validation),沒有 runtime 守門的話
 *  那些值會原樣外洩給呼叫端而型別上看起來是物件。這兩條釘的是守門本身;
 *  對既有兩個消費者(parseError / capital 的 errText)輸出零差異。 */
describe("parseErrorDetail", () => {
  it("detail 是字串 → {}(不把字串當 ErrorDetail 外洩)", async () => {
    const res = new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    await expect(parseErrorDetail(res)).resolves.toEqual({});
  });

  it("detail 是 array(FastAPI 422)→ {}", async () => {
    const body = { detail: [{ loc: ["body", "qty"], msg: "field required" }] };
    const res = new Response(JSON.stringify(body), { status: 422 });
    await expect(parseErrorDetail(res)).resolves.toEqual({});
  });
});
