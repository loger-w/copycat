/** @vitest-environment jsdom */
import { act, cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarBadges } from "@/components/CalendarBadges";
import { wrap } from "@/test-utils";
import type { CalendarState } from "@/types";

/** 三顆膠囊全部吃同一份 `/api/calendar` payload(N016 / N090 / N091),所以測試也只餵這一份。
 *
 *  既有那顆(休市)的行為契約在 `App.test.tsx` 的 nav 整鏈測試裡;這一檔測的是**元件本身**
 *  的三個判定式,不重測掛載位置。 */
const BASE: CalendarState = {
  today: "2026-10-09", // 週五
  trade_date: "2026-10-09",
  calendar_trade_date: "2026-10-09",
  backfill_env: null,
  holidays: [],
  extra_trading_days: [],
  years_loaded: [2026],
  calendar_loaded: true,
};

function serve(over: Partial<CalendarState> = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ ...BASE, ...over }))),
  );
}

/** 負例的 settle 點:等 fetch 真的回過並排乾 promise chain —— 否則「還沒回」與
 *  「判定成不顯示」在 `queryBy` 下同形(把整個判定刪掉照樣綠)。 */
async function settled(): Promise<void> {
  await waitFor(() =>
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0),
  );
  // TQ observer 走 notifyManager 的 macrotask 排程:光排乾 microtask 不足以讓
  // 「資料到了、元件也重繪過」成立(frontend-testing skill 的 TQ 條目)
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

beforeEach(() => {
  // 本機今日 = payload 的 today,否則既有的「跨午夜保險絲」會把休市膠囊否決掉
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 9, 12, 0, 0));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  cleanup();
});

describe("CalendarBadges 健康態", () => {
  it("日曆載到、今天有開盤、無 env → 零 DOM(誤報一次就沒人看第二次)", async () => {
    serve();
    const { container } = wrap(<CalendarBadges />);
    await settled();
    expect(container.textContent).toBe("");
  });
});

describe("交易日曆過期膠囊(N016)", () => {
  it("years_loaded 不含今年 → 亮,title 指到要更新的檔", async () => {
    serve({ years_loaded: [2025] });
    wrap(<CalendarBadges />);
    const badge = await screen.findByTestId("calendar-stale-badge");
    expect(badge.textContent).toBe("交易日曆過期");
    expect(badge.getAttribute("title")).toContain("2026");
    expect(badge.getAttribute("title")).toContain("configs/trading_holidays.json");
  });

  it("years_loaded 含今年 → 不亮", async () => {
    serve({ years_loaded: [2025, 2026, 2027] });
    wrap(<CalendarBadges />);
    await settled();
    expect(screen.queryByTestId("calendar-stale-badge")).toBeNull();
  });

  it("後端沒載日曆 → 不亮(空 years_loaded 講的是「沒有日曆」不是「日曆過期」)", async () => {
    serve({ calendar_loaded: false, years_loaded: [] });
    wrap(<CalendarBadges />);
    await settled();
    expect(screen.queryByTestId("calendar-stale-badge")).toBeNull();
  });
});

describe("TXO 回補日鎖定膠囊(N091)", () => {
  it("backfill_env 有值 → 亮並印出那一天(忘了清 env = 整盤凍結,現況零提示)", async () => {
    serve({ backfill_env: "2026-08-10", trade_date: "2026-08-10" });
    wrap(<CalendarBadges />);
    const badge = await screen.findByTestId("calendar-backfill-env-badge");
    expect(badge.textContent).toBe("TXO 回補日鎖定 2026-08-10");
    expect(badge.getAttribute("title")).toContain("TXO_BACKFILL_DATE");
  });

  it("backfill_env=null → 不亮", async () => {
    serve();
    wrap(<CalendarBadges />);
    await settled();
    expect(screen.queryByTestId("calendar-backfill-env-badge")).toBeNull();
  });
});

describe("休市膠囊的週末守門(N090)", () => {
  it("普通週末 → 仍靜音(AR8:常駐兩週就沒人看得見它)", async () => {
    vi.setSystemTime(new Date(2026, 9, 10, 12, 0, 0)); // 週六
    serve({ today: "2026-10-10", trade_date: "2026-10-09", calendar_trade_date: "2026-10-09" });
    wrap(<CalendarBadges />);
    await settled();
    expect(screen.queryByTestId("calendar-holiday-badge")).toBeNull();
  });

  it("今天列在 extra_trading_days 卻仍被後端判非交易日 → 亮(補班日沒生效)", async () => {
    vi.setSystemTime(new Date(2026, 9, 10, 12, 0, 0)); // 週六
    serve({
      today: "2026-10-10",
      trade_date: "2026-10-09",
      calendar_trade_date: "2026-10-09",
      extra_trading_days: ["2026-10-10"],
    });
    wrap(<CalendarBadges />);
    const badge = await screen.findByTestId("calendar-holiday-badge");
    expect(badge.textContent).toBe("日曆判今日休市");
  });

  it("舊 payload(無 extra_trading_days 欄)→ 逐字退回週末靜音", async () => {
    vi.setSystemTime(new Date(2026, 9, 10, 12, 0, 0));
    const legacy: Record<string, unknown> = { ...BASE };
    delete legacy.extra_trading_days; // 舊 payload:這一格根本不存在(不是空陣列)
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...legacy,
              today: "2026-10-10",
              trade_date: "2026-10-09",
              calendar_trade_date: "2026-10-09",
            }),
          ),
      ),
    );
    wrap(<CalendarBadges />);
    await settled();
    expect(screen.queryByTestId("calendar-holiday-badge")).toBeNull();
  });
});
