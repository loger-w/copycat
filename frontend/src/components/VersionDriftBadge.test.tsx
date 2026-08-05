/** @vitest-environment jsdom */
/** 版本落差膠囊(SC-4)與 console.warn once per pair(SC-5)。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VersionDriftBadge } from "@/components/VersionDriftBadge";
import { wrap } from "@/test-utils";

let fetchMock: ReturnType<typeof vi.fn>;
let warnSpy: ReturnType<typeof vi.spyOn>;

/** health 的 git_sha 與 /__build/sha 的回應;`status` 用於 500 負例。 */
function mockFetch(opts: { health?: unknown; healthStatus?: number; buildSha?: string | null }) {
  fetchMock = vi.fn((url: string) => {
    const u = String(url);
    if (u.includes("/api/health")) {
      return Promise.resolve(
        new Response(JSON.stringify(opts.health ?? {}), { status: opts.healthStatus ?? 200 }),
      );
    }
    if (u.includes("/__build/sha")) {
      return Promise.resolve(JSON.stringify({ git_sha: opts.buildSha ?? null })).then(
        (b) => new Response(b),
      );
    }
    return Promise.resolve(new Response("{}", { status: 404 }));
  });
  vi.stubGlobal("fetch", fetchMock);
}

/** 負例的 settle 點(design R9):先確認 fetch 真的發生,再把 promise chain 排乾
 *  ——「還沒 fetch 就斷言沒膠囊」會恆綠。 */
async function settle() {
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

beforeEach(() => {
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("VersionDriftBadge 落差態(SC-4/SC-5)", () => {
  it("前後端 sha 不同 → 膠囊出現,title 帶兩邊 sha", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" } });
    wrap(<VersionDriftBadge feSha="aaaaaaa" />);
    const badge = await screen.findByTestId("version-drift-badge");
    expect(badge.textContent).toContain("版本落差");
    const title = badge.getAttribute("title") ?? "";
    expect(title).toContain("aaaaaaa");
    expect(title).toContain("bbbbbbb");
    expect(title).toContain("重啟");
  });

  it("console.warn 恰一次,訊息含兩邊 sha 與「重啟」(SC-5)", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" } });
    wrap(<VersionDriftBadge feSha="aaaaaaa" />);
    await screen.findByTestId("version-drift-badge");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(warnSpy).toHaveBeenCalledTimes(1);
    const msg = String(warnSpy.mock.calls[0]?.[0]);
    expect(msg).toContain("aaaaaaa");
    expect(msg).toContain("bbbbbbb");
    expect(msg).toContain("重啟");
  });
});

describe("VersionDriftBadge 健康態(零 DOM 零噪音)", () => {
  it("兩邊 sha 相同 → 不掛任何 DOM、不 warn", async () => {
    mockFetch({ health: { git_sha: "aaaaaaa" } });
    const { container } = wrap(<VersionDriftBadge feSha="aaaaaaa" />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(container.textContent).toBe("");
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("後端 git_sha 為 null(非 git checkout)→ 不誤報", async () => {
    mockFetch({ health: { git_sha: null } });
    wrap(<VersionDriftBadge feSha="aaaaaaa" />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("/api/health 500 → 不誤報(後端沒回答不等於版本不同)", async () => {
    mockFetch({ health: {}, healthStatus: 500 });
    wrap(<VersionDriftBadge feSha="aaaaaaa" />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("前端 sha 未知(live 未回、prop 為 null)→ 不誤報", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" } });
    wrap(<VersionDriftBadge feSha={null} />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});

describe("VersionDriftBadge warn 去重(SC-5:per pair)", () => {
  // 這兩條要 rerender 同一個元件實例(去重的 ref 掛在實例上),必須自己持有 client ——
  // `wrap()` 不外露 client,rerender 時重建 provider 會連元件一起換掉。
  // 形態沿用 PriceLadder.test.tsx 的 `ladder()` helper。
  function badge(feSha: string, client: QueryClient) {
    return (
      <QueryClientProvider client={client}>
        <VersionDriftBadge feSha={feSha} />
      </QueryClientProvider>
    );
  }

  it("同一組 sha 重繪不重複 warn", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(badge("aaaaaaa", client));
    await screen.findByTestId("version-drift-badge");
    rerender(badge("aaaaaaa", client));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("sha 組合變了 → 再 warn 一次(換了一組落差就是新事實)", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(badge("aaaaaaa", client));
    await screen.findByTestId("version-drift-badge");
    rerender(badge("ccccccc", client));
    await waitFor(() => expect(warnSpy).toHaveBeenCalledTimes(2));
    expect(String(warnSpy.mock.calls[1]?.[0])).toContain("ccccccc");
  });
});

describe("VersionDriftBadge 前端 sha 來源(SC-6)", () => {
  it("未給 prop 時走 /__build/sha 現算值(dev live 優先於 define)", async () => {
    mockFetch({ health: { git_sha: "bbbbbbb" }, buildSha: "aaaaaaa" });
    wrap(<VersionDriftBadge />);
    const badge = await screen.findByTestId("version-drift-badge");
    expect(badge.getAttribute("title")).toContain("aaaaaaa");
  });
});
