/** @vitest-environment jsdom */
/** 🔒 lock(spec review P1-1):`dropCollapsed` 的呼叫者是 PUT mutation 的 `onSuccess`,
 *  **不是事件路徑** —— 同一個 tick 內連續執行兩次時,render 閉包的 `collapsed` 還是舊的。
 *  持久化若改成「直接讀閉包值算 next」,第二次會把第一次已清掉的組名原樣寫回 localStorage
 *  (使用者日後建同名群組會意外呈折疊,W-20 的復發)。現況(updater 內 persist)與修法
 *  (collapsedRef imperative 配對)都該綠,這條是防退化的鎖。
 *
 *  為什麼要 stub Dialog 而不從真實 UI 連按兩次刪除:實測(2026-08-11)側欄的 Dialog 只有
 *  **一顆** `useSaveWatchlist` mutation observer,第二發 `mutate` 會覆蓋 observer 的
 *  per-call callbacks,第一發的 `onSuccess` 因此根本不會執行 —— 真實 UI 連刪兩組只會走到
 *  一次 `dropCollapsed`,測不到本條要守的不變式(那個 callback 遺失是另一個 pre-existing
 *  問題,不在本批 scope)。所以這裡直接以 stub 打「同一 tick 兩次回呼」這個契約。
 *
 *  vi.mock 是檔案級 + hoisted → 必須獨立成檔,`WatchlistSidebar.test.tsx` 的 Dialog
 *  相關測試(管理入口 / W-20 單組刪除)仍跑真身。 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import { WL_COLLAPSED_KEY } from "@/lib/constants";
import type { Group } from "@/lib/watchlist-model";

vi.mock("@/components/stock/WatchlistManagerDialog", () => ({
  WatchlistManagerDialog: ({ onGroupDeleted }: { onGroupDeleted: (name: string) => void }) => (
    <button
      type="button"
      onClick={() => {
        // 兩發 PUT 同批 resolve 的形狀:兩個 onSuccess 在同一個 tick 連續執行
        onGroupDeleted("觀察");
        onGroupDeleted("主力");
      }}
    >
      連刪兩組
    </button>
  ),
}));

const GROUPS: Group[] = [
  { name: "主力", codes: ["2330"] },
  { name: "觀察", codes: ["3231"] },
];

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).includes("/api/stock/names")
        ? new Response(JSON.stringify({ names: [], count: 0 }))
        : new Response(JSON.stringify({ codes: ["2330", "3231"], groups: GROUPS })),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WatchlistSidebar dropCollapsed 同批回呼(P1-1 lock)", () => {
  it("同一 tick 連刪兩組 → localStorage 兩組名皆不留", async () => {
    window.localStorage.setItem(WL_COLLAPSED_KEY, JSON.stringify(["觀察", "主力"]));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <WatchlistSidebar active={null} onSelect={() => {}} quotes={{}} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "連刪兩組" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "連刪兩組" }));

    expect(JSON.parse(window.localStorage.getItem(WL_COLLAPSED_KEY)!)).toEqual([]);
  });
});
