/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistManagerDialog } from "@/components/stock/WatchlistManagerDialog";
import type { Watchlist } from "@/lib/watchlist-model";

/** 2317 在自選但不屬任何群組(未分組桶) */
const WL: Watchlist = {
  codes: ["2330", "5483", "2317"],
  groups: [
    { name: "主力", codes: ["2330", "5483"] },
    { name: "觀察", codes: ["2330"] },
  ],
};

const NAMES = {
  names: [
    { code: "2330", name: "台積電" },
    { code: "5483", name: "中美晶" },
    { code: "2317", name: "鴻海" },
  ],
  count: 3,
};

let fetchMock: ReturnType<typeof vi.fn>;
let putBodies: Watchlist[];

beforeEach(() => {
  putBodies = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as Watchlist;
      putBodies.push(body);
      return new Response(JSON.stringify(body));
    }
    if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
    return new Response(JSON.stringify(WL));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function open(wl: Watchlist = WL) {
  const onClose = vi.fn();
  const onGroupDeleted = vi.fn();
  wrap(
    <WatchlistManagerDialog open wl={wl} onClose={onClose} onGroupDeleted={onGroupDeleted} />,
  );
  return { onClose, onGroupDeleted };
}

describe("WatchlistManagerDialog 開關(SC-13)", () => {
  it("開啟時標題與兩個區塊都在", () => {
    open();
    expect(screen.getByText("管理群組與股票")).toBeTruthy();
    expect(screen.getByLabelText("群組")).toBeTruthy();
    expect(screen.getByLabelText("股票")).toBeTruthy();
  });

  it("關閉時內容不在 DOM(否則側欄的計數型斷言會被 Dialog 的重複文字打壞)", () => {
    const onClose = vi.fn();
    wrap(
      <WatchlistManagerDialog
        open={false}
        wl={WL}
        onClose={onClose}
        onGroupDeleted={() => {}}
      />,
    );
    expect(screen.queryByText("管理群組與股票")).toBeNull();
    expect(screen.queryByText("2330")).toBeNull();
  });

  it("Esc → onClose(不依賴原生 dialog 行為,jsdom 沒有)", () => {
    const { onClose } = open();
    fireEvent.keyDown(screen.getByLabelText("管理群組與股票"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("WatchlistManagerDialog 群組管理(SC-14)", () => {
  it("新增群組 → PUT 帶新空群組", async () => {
    open();
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: "當沖" } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups).toEqual([...WL.groups, { name: "當沖", codes: [] }]);
  });

  it("改名 → PUT 帶新名字,成員不動", async () => {
    open();
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力");
    fireEvent.change(input, { target: { value: "強勢" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[0]).toEqual({ name: "強勢", codes: ["2330", "5483"] });
  });

  it("改名撞既有名 → 零 PUT + 錯誤文案", async () => {
    open();
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力");
    fireEvent.change(input, { target: { value: "觀察" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(putBodies).toEqual([]);
  });

  it("刪除群組 → PUT 不含該組,成員留在 codes(掉回未分組)", async () => {
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups).toEqual([{ name: "主力", codes: ["2330", "5483"] }]);
    expect(putBodies[0]!.codes).toEqual(WL.codes);
  });

  it("刪除群組成功 → onGroupDeleted(側欄據此清折疊孤兒,W-20)", async () => {
    const { onGroupDeleted } = open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(onGroupDeleted).toHaveBeenCalledWith("觀察"));
  });

  it("刪除群組失敗(PUT 4xx)→ 錯誤文案、無第二次 PUT、不呼叫 onGroupDeleted(W-3)", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)) as Watchlist);
        return new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 });
      }
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response(JSON.stringify(WL));
    });
    const { onGroupDeleted } = open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(putBodies).toHaveLength(1);
    expect(onGroupDeleted).not.toHaveBeenCalled();
    expect(screen.getByLabelText("刪除群組 觀察")).toBeTruthy(); // UI 不先跳
  });
});

describe("WatchlistManagerDialog 股票管理(SC-14 / W-1)", () => {
  it("逐檔列出自選全體(含未分組)與名稱", () => {
    open();
    const section = screen.getByLabelText("股票");
    expect(within(section).getByText("2317")).toBeTruthy(); // 未分組也要能管理
    expect(within(section).getByText("鴻海")).toBeTruthy();
  });

  it("checkbox 反映一檔多組的現況(W-1)", () => {
    open();
    expect((screen.getByLabelText("2330 屬於 主力") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("2330 屬於 觀察") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("2317 屬於 主力") as HTMLInputElement).checked).toBe(false);
  });

  it("勾選 → PUT 帶該組多出這檔(一檔可屬多組)", async () => {
    open();
    fireEvent.click(screen.getByLabelText("2317 屬於 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[1]!.codes).toEqual(["2330", "2317"]);
    expect(putBodies[0]!.groups[0]!.codes).toEqual(["2330", "5483"]); // 另一組不動
  });

  it("取消勾選 → 只離開該組,code 留在 codes", async () => {
    open();
    fireEvent.click(screen.getByLabelText("2330 屬於 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[1]!.codes).toEqual([]);
    expect(putBodies[0]!.codes).toEqual(WL.codes);
  });

  it("× → codes 與所有群組都少掉該檔", async () => {
    open();
    fireEvent.click(screen.getByLabelText("從自選移除 2330"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(["5483", "2317"]);
    expect(putBodies[0]!.groups).toEqual([
      { name: "主力", codes: ["5483"] },
      { name: "觀察", codes: [] },
    ]);
  });
});
