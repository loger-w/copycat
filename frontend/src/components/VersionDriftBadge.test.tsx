/** @vitest-environment jsdom */
/** 版本落差膠囊(SC-4)與 console.warn once per pair(SC-5)。
 *
 *  dev 路徑的判定來源是 middleware 的 `behind`(design C3 range 判別),不是 sha 等值 ——
 *  fixture 因此要同時餵 `/api/health`(後端 sha)與 `/__build/sha`(git_sha + behind)。 */
import { act, cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VersionDriftBadge } from "@/components/VersionDriftBadge";
import { wrap } from "@/test-utils";

interface Fixture {
  /** /api/health 的 git_sha */
  be?: string | null;
  beStatus?: number;
  /** /__build/sha 的回應 body */
  build?: { git_sha: string | null; behind: boolean | null };
  buildStatus?: number;
}

let fixture: Fixture;
let fetchMock: ReturnType<typeof vi.fn>;
let warnSpy: ReturnType<typeof vi.spyOn>;

/** 讀 `fixture` 的**當下**值 → 測試中途改 fixture,下一輪輪詢就會拿到新答案。 */
function installFetch() {
  fetchMock = vi.fn((url: string) => {
    const u = String(url);
    if (u.includes("/api/health")) {
      return Promise.resolve(
        new Response(JSON.stringify({ git_sha: fixture.be ?? null, git_dirty: false }), {
          status: fixture.beStatus ?? 200,
        }),
      );
    }
    if (u.includes("/__build/sha")) {
      return Promise.resolve(
        new Response(JSON.stringify(fixture.build ?? { git_sha: null, behind: null }), {
          status: fixture.buildStatus ?? 200,
        }),
      );
    }
    return Promise.resolve(new Response("{}", { status: 404 }));
  });
  vi.stubGlobal("fetch", fetchMock);
}

function callsTo(frag: string): number {
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes(frag)).length;
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
  fixture = {};
  installFetch();
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("VersionDriftBadge 落差態(SC-4/SC-5)", () => {
  it("behind=true(後端落後 copycat/ 的新 commit)→ 膠囊出現,title 帶兩邊 sha", async () => {
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
    const badge = await screen.findByTestId("version-drift-badge");
    expect(badge.textContent).toContain("版本落差");
    const title = badge.getAttribute("title") ?? "";
    expect(title).toContain("aaaaaaa");
    expect(title).toContain("bbbbbbb");
    expect(title).toContain("重啟");
  });

  it("console.warn 恰一次,訊息含兩邊 sha 與「重啟」(SC-5)", async () => {
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
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
  it("behind=false(前端 commit 沒動到 copycat/)→ 不掛任何 DOM、不 warn", async () => {
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: false } };
    const { container } = wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(container.textContent).toBe("");
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("behind=null(middleware 不判定:since 非法 / git 失敗)→ 不誤報", async () => {
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: null } };
    wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("後端 git_sha 為 null(非 git checkout)→ 連問都不問,不誤報", async () => {
    fixture = { be: null, build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(callsTo("/__build/sha")).toBe(0);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("/api/health 500 → 不誤報(後端沒回答不等於版本不同)", async () => {
    fixture = { be: "bbbbbbb", beStatus: 500, build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("/__build/sha 500(transient)→ 不誤報,也不退回 define 等值比對(C1)", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fixture = { be: "bbbbbbb", buildStatus: 500 };
    wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});

describe("VersionDriftBadge build 產物語意(/__build/sha 404 → define 等值比對)", () => {
  it("define ≠ 後端 sha → 膠囊出現", async () => {
    vi.stubGlobal("__GIT_SHA__", "aaaaaaa");
    fixture = { be: "bbbbbbb", buildStatus: 404 };
    wrap(<VersionDriftBadge />);
    const badge = await screen.findByTestId("version-drift-badge");
    expect(badge.getAttribute("title")).toContain("aaaaaaa");
  });

  it("define = 後端 sha → 零 DOM", async () => {
    vi.stubGlobal("__GIT_SHA__", "bbbbbbb");
    fixture = { be: "bbbbbbb", buildStatus: 404 };
    wrap(<VersionDriftBadge />);
    await settle();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();
  });
});

describe("VersionDriftBadge warn 去重(SC-5:per pair)", () => {
  /** 推進一輪 60s 輪詢並把 promise chain 排乾。
   *
   *  尾巴補兩次 1ms 是必要的:health 與 `/__build/sha` 是**兩段式**(後者的 since 來自
   *  前者的回應),一次 advance 只推得動第一段;而且步進必須 > 0ms ——
   *  `advanceTimersByTimeAsync(0)` 推不動第二段(實測 5 輪 0ms 後膠囊仍未出現,改 1ms
   *  第一輪就到位)。 */
  async function poll(ms = 60_000) {
    for (const step of [ms, 1, 1]) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(step);
      });
    }
  }

  it("落差 → 消失 → 同一組 sha 再現:warn 仍只有一次(C2 載重路徑)", async () => {
    vi.useFakeTimers();
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
    await poll(1);
    expect(screen.queryByTestId("version-drift-badge")).toBeTruthy();
    expect(warnSpy).toHaveBeenCalledTimes(1);

    // 後端重啟到同步 → 膠囊消失
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: false } };
    await poll();
    expect(screen.queryByTestId("version-drift-badge")).toBeNull();

    // 又落後回同一組 sha:去重是 pair 級,drift 消失時不清 ref,所以不該再吵
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: true } };
    await poll();
    expect(screen.queryByTestId("version-drift-badge")).toBeTruthy();
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("sha 組合變了 → 再 warn 一次(換了一組落差就是新事實)", async () => {
    vi.useFakeTimers();
    fixture = { be: "bbbbbbb", build: { git_sha: "aaaaaaa", behind: true } };
    wrap(<VersionDriftBadge />);
    await poll(1);
    expect(warnSpy).toHaveBeenCalledTimes(1);

    fixture = { be: "ccccccc", build: { git_sha: "aaaaaaa", behind: true } };
    await poll();
    expect(warnSpy).toHaveBeenCalledTimes(2);
    expect(String(warnSpy.mock.calls[1]?.[0])).toContain("ccccccc");
  });
});
