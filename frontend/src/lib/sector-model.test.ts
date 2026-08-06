/** 類股強弱取數層(market-overview R4 SC-3;design §9.1)。
 *
 *  兩支 fetcher 的重點各只有一個:URL 形狀與錯誤碼解析。`sub` 空字串**一律不送** ——
 *  後端把「`sub` 空字串」當未指定,但送出去的 `?sub=` 會讓 query key / 網路面板 /
 *  server log 三處各多一種形狀,而畫面上完全看不出差別。 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSectorMembers, fetchSectorState } from "@/lib/sector-model";

let urls: string[] = [];

function stubFetch(body: unknown, status = 200): void {
  urls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return new Response(JSON.stringify(body), { status });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchSectorState", () => {
  it("打 /api/market/sector 並原樣回傳 state", async () => {
    stubFetch({
      enabled: true,
      trade_date: "2026-08-06",
      as_of: "10:31:00",
      stale: false,
      rotation: { industries: [] },
    });
    const state = await fetchSectorState();
    expect(urls).toEqual(["/api/market/sector"]);
    expect(state.trade_date).toBe("2026-08-06");
    expect(state.rotation).toEqual({ industries: [] });
  });

  it("非 2xx → 拋出 detail.error", async () => {
    stubFetch({ detail: { error: "BOOM" } }, 500);
    await expect(fetchSectorState()).rejects.toThrow("BOOM");
  });
});

describe("fetchSectorMembers", () => {
  it("sub 為 null → URL 只帶 industry(不得出現 sub 參數)", async () => {
    stubFetch({ industry: "航運", sub_industry: null, members: [] });
    await fetchSectorMembers("航運", null);
    expect(urls.length).toBe(1);
    const url = decodeURIComponent(urls[0]!);
    expect(url).toBe("/api/market/sector/members?industry=航運");
    expect(url).not.toContain("sub=");
  });

  it("sub 空字串同樣不送(後端把空字串當未指定,前端不製造第二種形狀)", async () => {
    stubFetch({ industry: "航運", sub_industry: null, members: [] });
    await fetchSectorMembers("航運", "");
    expect(decodeURIComponent(urls[0]!)).toBe("/api/market/sector/members?industry=航運");
  });

  it("sub 有值 → 兩個參數都帶", async () => {
    stubFetch({ industry: "半導體", sub_industry: "IC設計", members: [] });
    await fetchSectorMembers("半導體", "IC設計");
    expect(decodeURIComponent(urls[0]!)).toBe(
      "/api/market/sector/members?industry=半導體&sub=IC設計",
    );
  });

  it("404 → 拋出 SECTOR_NOT_FOUND", async () => {
    stubFetch({ detail: { error: "SECTOR_NOT_FOUND" } }, 404);
    await expect(fetchSectorMembers("查無", null)).rejects.toThrow("SECTOR_NOT_FOUND");
  });
});
