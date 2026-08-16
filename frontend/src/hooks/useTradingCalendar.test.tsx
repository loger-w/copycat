/** @vitest-environment jsdom */
/** `/api/calendar` → 模組級假日集合的接線(SC-9)。
 *
 *  這裡鎖的是「線有沒有接上」:純函式面在 lib/trading-calendar.test.ts,少了這一根線
 *  那邊照樣全綠、畫面上假日卻整天不進前端。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTradingCalendar } from "@/hooks/useTradingCalendar";
import { clearHolidays, isTradingDay } from "@/lib/trading-calendar";

const HOLIDAY = new Date(2026, 9, 9, 10, 0); // 2026-10-09 週五

const PAYLOAD = {
  today: "2026-08-16",
  trade_date: "2026-08-14",
  calendar_trade_date: "2026-08-14",
  backfill_env: null,
  holidays: ["2026-10-09", "2026-12-25"],
  years_loaded: [2026],
  calendar_loaded: true,
};

let fetchMock: ReturnType<typeof vi.fn>;

function stubFetch(body: unknown, status = 200): void {
  fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  clearHolidays();
  stubFetch(PAYLOAD);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearHolidays();
});

describe("useTradingCalendar", () => {
  it("取數成功後把 holidays 灌進模組級集合", async () => {
    // 前提自檢:灌進去之前該日仍是交易日,否則下面的斷言對「本來就 false」也會通過
    expect(isTradingDay(HOLIDAY)).toBe(true);

    const { result } = renderHook(() => useTradingCalendar(), { wrapper });
    await waitFor(() => expect(result.current.data?.calendar_loaded).toBe(true));
    await waitFor(() => expect(isTradingDay(HOLIDAY)).toBe(false));
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toContain("/api/calendar");
  });

  it("HTTP 失敗 → 集合不動(退回只擋週末,不是整組日期判定崩掉)", async () => {
    stubFetch({ detail: { error: "BOOM" } }, 500);
    const { result } = renderHook(() => useTradingCalendar(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(isTradingDay(HOLIDAY)).toBe(true);
  });

  it("後端未載日曆(holidays 空)→ 集合清空,只擋週末", async () => {
    stubFetch({ ...PAYLOAD, holidays: [], years_loaded: [], calendar_loaded: false });
    const { result } = renderHook(() => useTradingCalendar(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(isTradingDay(HOLIDAY)).toBe(true);
  });
});
