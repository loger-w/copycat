/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchlistManagerDialog } from "@/components/stock/WatchlistManagerDialog";
import type { Watchlist } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";

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
    { code: "2331", name: "精英" }, // 不在自選 —— 右欄搜尋要能加進來
  ],
  count: 4,
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

function open(wl: Watchlist = WL) {
  const onClose = vi.fn();
  const onGroupDeleted = vi.fn();
  wrap(
    <WatchlistManagerDialog open wl={wl} onClose={onClose} onGroupDeleted={onGroupDeleted} />,
  );
  return { onClose, onGroupDeleted };
}

/** PUT 卡 gate 逐發放行(成功 echo / 400 失敗可選):製造「第一發在途時做第二個動作」
 *  的視窗。gate 的 resolver 在 push body 的同一個同步區塊註冊 —— putBodies 長度到位時
 *  對應 resolver 必已存在,release 不會撲空。隔離靠 `gatePuts()` 每條測試開頭重設 `gated`
 *  (實測三份閉包收成單例 51/51 仍綠 —— per-describe 各持一份純屬防禦,pr-160 review F-09);
 *  `gatePuts()` 換掉的 `fetchMock` 實作由 `beforeEach` 的 echo 版在下一條測試自動復原。
 *  原本三個 describe 各抄一份逐字複本(next-time 08-26 A4 留尾)。 */
function makeGate(): {
  gatePuts: () => void;
  releaseOk: () => void;
  releaseFail: () => void;
} {
  // 刻意不給初值:忘了先 gatePuts() 就 release 會炸在 undefined.shift(訊息比吞空 shift 準)
  let gated: Array<{ body: Watchlist; resolve: (r: Response) => void }>;
  function gatePuts(): void {
    gated = [];
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Watchlist;
        putBodies.push(body);
        return new Promise<Response>((resolve) => gated.push({ body, resolve }));
      }
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response(JSON.stringify(WL));
    });
  }
  function releaseOk(): void {
    const g = gated.shift()!;
    g.resolve(new Response(JSON.stringify(g.body)));
  }
  function releaseFail(): void {
    gated
      .shift()!
      .resolve(new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 }));
  }
  return { gatePuts, releaseOk, releaseFail };
}

describe("關閉時不佔版面(round6 bug)", () => {
  /** f46cc29 把 dialog 的 className 從「無 display utility」改成含 `flex`。
   *
   *  UA stylesheet 的 `dialog:not([open]) { display: none }` 屬瀏覽器層,Tailwind 的
   *  `.flex { display:flex }` 屬 author 層 —— author 勝,關閉的 dialog 照樣 `display:flex`,
   *  變成一個 896×480 的空盒子壓在圖表上(2026-07-31 真瀏覽器實測 computed display = flex)。
   *
   *  **jsdom 測不到 computed display**(不載入 Tailwind CSS、`HTMLDialogElement` 是空 class),
   *  所以這裡鎖的是「關閉時不得帶會覆蓋 UA display:none 的 utility」這條契約本身。
   *  class 必須隨 `open` 變化才鎖得住 —— 用 Tailwind 的 `open:` variant 的話 class 字串恆定,
   *  斷言只能確認「有這個 class」,回歸時抓不到。 */
  function dialogEl(): HTMLDialogElement {
    return screen.getByLabelText("管理群組與股票") as HTMLDialogElement;
  }

  it("open=false 時帶 hidden、不帶 flex", () => {
    wrap(
      <WatchlistManagerDialog open={false} wl={WL} onClose={vi.fn()} onGroupDeleted={vi.fn()} />,
    );
    const el = dialogEl();
    expect(el.classList.contains("hidden")).toBe(true);
    expect(el.classList.contains("flex")).toBe(false);
  });

  it("open=true 時帶 flex、不帶 hidden", () => {
    open();
    const el = dialogEl();
    expect(el.classList.contains("flex")).toBe(true);
    expect(el.classList.contains("hidden")).toBe(false);
  });

  it("m-auto 與 flex-col 兩態都保留(W-21:preflight 覆蓋 UA margin:auto 會貼左上角)", () => {
    wrap(
      <WatchlistManagerDialog open={false} wl={WL} onClose={vi.fn()} onGroupDeleted={vi.fn()} />,
    );
    expect(dialogEl().classList.contains("m-auto")).toBe(true);
    expect(dialogEl().classList.contains("flex-col")).toBe(true);
  });
});

describe("WatchlistManagerDialog 開關(SC-13)", () => {
  it("開啟時標題與左右兩欄都在", () => {
    open();
    expect(screen.getByText("管理群組與股票")).toBeTruthy();
    expect(screen.getByLabelText("群組")).toBeTruthy();
    expect(screen.getByLabelText("股票")).toBeTruthy();
  });

  // 🔴 round4 項 4(B-8):Tailwind v4 的 preflight 把 `margin: 0` 套到所有元素(含
  // dialog),覆蓋掉 UA stylesheet 給 modal dialog 的 `margin: auto` → 貼到左上角。
  // jsdom 沒有版面引擎,這個 bug 只能用 class 守。
  it("dialog 帶 m-auto(否則被 preflight 的 margin:0 釘在左上角)", () => {
    open();
    const dlg = screen.getByLabelText("管理群組與股票");
    expect(dlg.className).toContain("m-auto");
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

// 🔴 round4 項 4(B-8):checkbox 矩陣(N 檔 × M 群組)改成「左選一組、右列該組股票」。
// 矩陣在 3 組 20 檔時就是 60 個 checkbox,而且會橫向換行。
describe("WatchlistManagerDialog 左右兩欄(round4 項 4)", () => {
  function stocks(): HTMLElement {
    return screen.getByLabelText("股票");
  }

  it("畫面上沒有任何 checkbox(矩陣已移除)", () => {
    const { container } = wrap(
      <WatchlistManagerDialog open wl={WL} onClose={vi.fn()} onGroupDeleted={vi.fn()} />,
    );
    expect(container.querySelectorAll('input[type="checkbox"]').length).toBe(0);
  });

  it("預設選中「未分組」偽群組,右欄列出不屬任何群組的股票", async () => {
    open();
    expect(screen.getByRole("button", { name: "未分組" })).toBeTruthy();
    expect(within(stocks()).getByText("2317")).toBeTruthy();
    expect(within(stocks()).queryByText("5483")).toBeNull(); // 已屬主力
    await waitFor(() => expect(within(stocks()).getByText("鴻海")).toBeTruthy());
  });

  it("「未分組」列沒有改名 / 刪除鈕(它不是真群組)", () => {
    open();
    expect(screen.queryByLabelText("改名 未分組")).toBeNull();
    expect(screen.queryByLabelText("刪除群組 未分組")).toBeNull();
  });

  it("點左欄群組 → 右欄換成該組股票,並標示選中態", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    expect(within(stocks()).getByText("5483")).toBeTruthy();
    expect(within(stocks()).queryByText("2317")).toBeNull();
    // 選中態的邊條掛在列的容器上(button 只承載名稱與點擊)
    expect(screen.getByRole("button", { name: "主力" }).parentElement!.className).toContain(
      "border-l-accent",
    );
  });

  it("一檔多組 → 右欄標示它還屬於哪些別組(矩陣資訊不憑空消失)", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    const row = within(stocks()).getByTestId("mgr-row-2330");
    expect(within(row).getByText("觀察")).toBeTruthy();
  });

  it("右欄搜尋加入該組 → **PUT 恰一筆**,codes 與該組同時含該檔", async () => {
    open();
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy()); // 名冊載入
    fireEvent.click(screen.getByRole("button", { name: "觀察" }));
    const box = screen.getByPlaceholderText(/加入股票到/);
    fireEvent.change(box, { target: { value: "5483" } });
    fireEvent.click(screen.getByLabelText("加入 5483 到 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[1]!.codes).toEqual(["2330", "5483"]);
    expect(putBodies[0]!.codes).toEqual(WL.codes); // 已在自選 → codes 不變
  });

  it("加入非自選股 → codes 與群組同時多出該檔(單次 PUT)", async () => {
    open();
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "觀察" }));
    fireEvent.change(screen.getByPlaceholderText(/加入股票到/), { target: { value: "2331" } });
    fireEvent.click(screen.getByLabelText("加入 2331 到 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual([...WL.codes, "2331"]);
    expect(putBodies[0]!.groups[1]!.codes).toEqual(["2330", "2331"]);
  });

  // review F6:未分組視圖的 rows 不含「已屬別組」的檔 —— 只看 rows 會顯示成可加入,
  // 點下去卻是零 PUT 早退,唯一可見變化是搜尋框被清空 = 看起來成功實際沒事發生
  it("未分組視圖:已在自選(但屬別組)的候選也要停用,文案為「已在自選」", async () => {
    open();
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/加入自選/), { target: { value: "5483" } });
    const btn = screen.getByLabelText("加入 5483 到 未分組") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain("已在自選");
  });

  // review F1:PUT 未回前 wl 仍是舊值,commit() 的零 PUT 早退擋不住重複送出
  // (算出來的 next 與舊 wl 內容確實不同)—— 只能靠 save.isPending 停用建議列
  it("PUT pending 期間重複加入同一檔到同一組 → 建議列停用,仍只送一筆 PUT", async () => {
    const gate: { release?: () => void } = {};
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)) as Watchlist);
        await new Promise<void>((r) => { gate.release = r; }); // 卡住 → wl 不刷新
        return new Response(String(init.body));
      }
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response(JSON.stringify(WL));
    });
    open();
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "觀察" }));
    fireEvent.change(screen.getByPlaceholderText(/加入股票到/), { target: { value: "5483" } });
    fireEvent.click(screen.getByLabelText("加入 5483 到 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.change(screen.getByPlaceholderText(/加入股票到/), { target: { value: "5483" } });
    const again = screen.getByLabelText("加入 5483 到 觀察") as HTMLButtonElement;
    expect(again.disabled).toBe(true);
    fireEvent.click(again);
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
    gate.release?.();
  });

  it("已在本組的候選為停用 + 尾綴說明", async () => {
    open();
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    fireEvent.change(screen.getByPlaceholderText(/加入股票到/), { target: { value: "2330" } });
    const btn = screen.getByLabelText("加入 2330 到 主力") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain("已在此群組");
  });

  it("群組列的 − 只離開該組(code 留在 codes)", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    fireEvent.click(screen.getByLabelText("從 主力 移出 5483"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[0]!.codes).toEqual(["2330"]);
    expect(putBodies[0]!.codes).toEqual(WL.codes);
  });

  // B-8 登記:舊版股票區列 wl.codes 全體、每列一顆「從自選移除」。改成分組視圖後
  // 若真群組只有「移出本組」,已分組的股票就沒有任何一步刪除入口 = 功能退化。
  it("群組列仍有「從自選移除」(一步刪除的入口不得消失)", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    fireEvent.click(screen.getByLabelText("從自選移除 5483"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(["2330", "2317"]);
    expect(putBodies[0]!.groups[0]!.codes).toEqual(["2330"]);
  });

  it("未分組列的 × → codes 與所有群組都少掉該檔", async () => {
    open();
    fireEvent.click(screen.getByLabelText("從自選移除 2317"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(["2330", "5483"]);
  });

  it("空群組顯示引導文案", () => {
    open({ codes: ["2330"], groups: [{ name: "空組", codes: [] }] });
    fireEvent.click(screen.getByRole("button", { name: "空組" }));
    expect(screen.getByText(/還沒有股票/)).toBeTruthy();
  });

  it("零自訂群組 → 左欄仍有未分組,並提示可在下方新增", () => {
    open({ codes: ["2330"], groups: [] });
    expect(screen.getByRole("button", { name: "未分組" })).toBeTruthy();
    expect(screen.getByText("尚無群組,可在下方新增")).toBeTruthy();
  });
});

// 🔴 docs/next-time.md 2026-08-11:Dialog 單顆 mutation observer,per-call callbacks 會被
// 第二發 mutate 覆蓋(TQ v5 契約:per-call callbacks 只 fire 最新一次 mutate);且 commit
// 一律以 render 閉包的 stale wl 算 next。兩缺陷共用同一觸發窗:第一發 PUT 在途時做第二個動作。
describe("WatchlistManagerDialog 連續操作(吞 callback / stale 基底)", () => {
  const { gatePuts, releaseOk, releaseFail } = makeGate();

  it("連刪兩組:第二發 PUT 以第一發結果為基底,不把第一組還原回去", async () => {
    gatePuts();
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("刪除群組 主力")); // 第一發仍在途
    // 序列化本身也是契約(review W-4):第二發不得在第一發回應前上路 ——
    // 後端 last-write-wins,唯有序列化能保證套用順序
    expect(putBodies).toHaveLength(1);
    releaseOk();
    await waitFor(() => expect(putBodies).toHaveLength(2));
    releaseOk();
    // 第二發必須含第一刪的結果:groups 全空 ——「觀察」以 stale wl 計算時會在這裡復活
    expect(putBodies[1]!.groups).toEqual([]);
  });

  it("連刪兩組:兩發 onGroupDeleted 都執行(W-20 折疊孤兒清理不漏)", async () => {
    gatePuts();
    const { onGroupDeleted } = open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("刪除群組 主力"));
    expect(putBodies).toHaveLength(1); // 序列化(review W-4)
    releaseOk();
    await waitFor(() => expect(putBodies).toHaveLength(2));
    releaseOk();
    await waitFor(() => expect(onGroupDeleted).toHaveBeenCalledTimes(2));
    expect(onGroupDeleted.mock.calls).toEqual([["觀察"], ["主力"]]);
  });

  // review W-5 lock:連點兩次同一顆刪除鈕(不耐煩的真實使用者)。第二個佇列項輪到時
  // 基底已不含該組,deleteGroup 恆回新物件但內容相同 → 深度比對 dedup 零 PUT、
  // onGroupDeleted 恰一次。dedup 改成 identity 比對會退化成兩發 PUT,本條要紅。
  it("連點兩次同一刪除鈕 → 只送一筆 PUT、onGroupDeleted 恰一次", async () => {
    gatePuts();
    const { onGroupDeleted } = open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("刪除群組 觀察")); // 第一發在途,列還在畫面上
    releaseOk();
    await waitFor(() => expect(onGroupDeleted).toHaveBeenCalledTimes(1));
    // 第二個佇列項是靜默 dedup,無事件可等 → 短 settle 後斷言零第二發
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
    expect(onGroupDeleted.mock.calls).toEqual([["觀察"]]);
  });

  // review C-3/W-1:佇列前一發失敗時,錯誤必須可見、已排隊的後續動作必須作廢 ——
  // 否則下一發 mutateAsync 立刻重設 save.error,失敗文案一幀未渲染就被洗掉,
  // 且後續動作靜默跳過失敗那一步繼續套用,使用者以為全部成功。
  it("第一發失敗 → 已排隊的第二發作廢、錯誤文案可見;之後的新動作照常送出", async () => {
    gatePuts();
    const { onGroupDeleted } = open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("刪除群組 主力")); // 排隊在失敗發之後
    releaseFail();
    // 短路:第二發不上路(靜默 no-op,無事件可等 → 短 settle 後斷言)
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
    expect(onGroupDeleted).not.toHaveBeenCalled();
    // 失敗後的「新」動作是新意圖,不受短路影響;基底未推進 →「觀察」仍在
    fireEvent.click(screen.getByLabelText("刪除群組 主力"));
    await waitFor(() => expect(putBodies).toHaveLength(2));
    expect(putBodies[1]!.groups.map((g) => g.name)).toEqual(["觀察"]);
    releaseOk();
    await waitFor(() => expect(onGroupDeleted.mock.calls).toEqual([["主力"]]));
  });
});

// 🔴 N115 / N118:撞名判定與交錯覆蓋的其餘組合。
describe("WatchlistManagerDialog 佇列視窗內的撞名與交錯(N115 / N118)", () => {
  const { gatePuts, releaseOk, releaseFail } = makeGate();

  function addGroupNamed(name: string): void {
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: name } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
  }

  /** N115 的核心:eager 檢查在 render 閉包的 `wl` 上,佇列前段剛建好的同名組它看不到 →
   *  **驗證放行**。舊實作套用時 `addGroup` 回原物件 → 深度比對 dedup → 零 PUT、**零文案**,
   *  而輸入框已經清空了 = 看起來完全成功。修法:撞名判定搬進 transform(回 null)。 */
  it("N115:佇列視窗內建同名組 → 第二發零 PUT **且有 BAD_GROUP 文案**", async () => {
    gatePuts();
    open();
    addGroupNamed("當沖");
    await waitFor(() => expect(putBodies).toHaveLength(1));
    addGroupNamed("當沖"); // 第一發仍在途,render 閉包的 wl 還沒有「當沖」→ eager 放行
    releaseOk();
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
  });

  it("N115:佇列視窗內把 A 改成 B,而 B 是佇列前段剛建好的組 → 零 PUT + 文案", async () => {
    gatePuts();
    open();
    addGroupNamed("當沖");
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力");
    fireEvent.change(input, { target: { value: "當沖" } });
    fireEvent.keyDown(input, { key: "Enter" }); // eager 看不到在途的「當沖」→ 放行
    releaseOk();
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
  });

  /** N118(1):刪組 + 改名交錯。改名那一發若以 stale 基底算,會把剛刪掉的組還原回去。 */
  it("N118:刪組在途 → 排隊的改名以刪組後的基底重算(被刪的組不復活)", async () => {
    gatePuts();
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力");
    fireEvent.change(input, { target: { value: "強勢" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(putBodies).toHaveLength(1); // 序列化
    releaseOk();
    await waitFor(() => expect(putBodies).toHaveLength(2));
    expect(putBodies[1]!.groups).toEqual([{ name: "強勢", codes: ["2330", "5483"] }]);
    releaseOk();
  });

  /** N118(2):刪組 + 移除股交錯。移除那一發若以 stale 基底算,PUT body 會帶著
   *  「觀察」整組一起回去 —— 使用者剛刪掉的組默默復活,而畫面上兩步都成功了。
   *  (「加入股票」那條走不到這個窗:建議列在 `isPending` 期間停用,review F1。) */
  it("N118:刪組在途 → 排隊的移除股以刪組後的基底重算(被刪的組不復活)", async () => {
    gatePuts();
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("從自選移除 2317")); // 未分組列,不受 isPending 停用
    expect(putBodies).toHaveLength(1); // 序列化
    releaseOk();
    await waitFor(() => expect(putBodies).toHaveLength(2));
    expect(putBodies[1]!.groups.map((g) => g.name)).toEqual(["主力"]);
    expect(putBodies[1]!.codes).toEqual(["2330", "5483"]);
    releaseOk();
  });

  /** N118(3):失敗短路之後的**新**動作,基底必須停在「失敗前」(未推進)。
   *  既有測試只驗了刪組那條路徑,這裡換一個動作型別(移除股)避免同義反覆。 */
  it("N118:失敗短路後的新動作以未推進的基底重算", async () => {
    gatePuts();
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    releaseFail();
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());

    fireEvent.click(screen.getByLabelText("從自選移除 2317"));
    await waitFor(() => expect(putBodies).toHaveLength(2));
    // 基底未推進 →「觀察」還在;失敗那一步不得被「順便帶上」
    expect(putBodies[1]!.groups.map((g) => g.name)).toEqual(["主力", "觀察"]);
    releaseOk();
  });
});

// 🟢 N266:組內排序的鍵盤路徑(拖拉握把是 pointer-only 且已 aria-hidden)。
describe("WatchlistManagerDialog 組內排序上移 / 下移(N266)", () => {
  function codesOf(): string[] {
    return within(screen.getByLabelText("股票"))
      .getAllByTestId(/^mgr-row-/)
      .map((el) => el.getAttribute("data-testid")!.replace("mgr-row-", ""));
  }

  it("群組內下移 → 該組 codes 換位,其餘不動", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    expect(codesOf()).toEqual(["2330", "5483"]);
    fireEvent.click(screen.getByLabelText("下移 2330"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[0]!.codes).toEqual(["5483", "2330"]);
    expect(putBodies[0]!.groups[1]).toEqual(WL.groups[1]); // 對照組:別組不動
    expect(putBodies[0]!.codes).toEqual(WL.codes); // codes 順序是另一個維度
  });

  it("群組內上移 → 與上一列對調(不是一路跳到頂)", async () => {
    open({ codes: ["A", "B", "C"], groups: [{ name: "組", codes: ["A", "B", "C"] }] });
    fireEvent.click(screen.getByRole("button", { name: "組" }));
    fireEvent.click(screen.getByLabelText("上移 C"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.groups[0]!.codes).toEqual(["A", "C", "B"]);
  });

  it("未分組內下移 → 改寫 codes 順序(群組成員的相對位置不動)", async () => {
    // 2317 / 2331 未分組,2330 屬「主力」夾在中間 —— codes 的絕對 index 換算才有鑑別力
    open({ codes: ["2317", "2330", "2331"], groups: [{ name: "主力", codes: ["2330"] }] });
    expect(codesOf()).toEqual(["2317", "2331"]);
    fireEvent.click(screen.getByLabelText("下移 2317"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    expect(putBodies[0]!.codes).toEqual(["2330", "2331", "2317"]);
  });

  it("界上的那一顆停用(第一列不能上移 / 最後一列不能下移)", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    expect((screen.getByLabelText("上移 2330") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("下移 2330") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByLabelText("上移 5483") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByLabelText("下移 5483") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("WatchlistManagerDialog selected 收斂(round4 項 4)", () => {
  it("右欄用 derived 值渲染:改名失敗留下的懸空 selected 不會讓右欄空白", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)) as Watchlist);
        return new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 });
      }
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response(JSON.stringify(WL));
    });
    open();
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力");
    fireEvent.change(input, { target: { value: "強勢" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(putBodies).toHaveLength(1));
    // PUT 失敗 → wl 仍是舊值 → 右欄照樣顯示主力的成員(不是空白)
    await waitFor(() => expect(within(screen.getByLabelText("股票")).getByText("5483")).toBeTruthy());
  });

  it("「未分組」是保留名:新增同名群組 → 零 PUT + 錯誤文案", async () => {
    open();
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: "未分組" } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(putBodies).toEqual([]);
  });

  it("關閉再開 → selected 回到未分組(不殘留上次選的組)", async () => {
    const onClose = vi.fn();
    const { rerender } = wrap(
      <WatchlistManagerDialog open wl={WL} onClose={onClose} onGroupDeleted={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "主力" }));
    expect(within(screen.getByLabelText("股票")).getByText("5483")).toBeTruthy();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <WatchlistManagerDialog open={false} wl={WL} onClose={onClose} onGroupDeleted={vi.fn()} />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <WatchlistManagerDialog open wl={WL} onClose={onClose} onGroupDeleted={vi.fn()} />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(within(screen.getByLabelText("股票")).getByText("2317")).toBeTruthy(),
    );
    expect(within(screen.getByLabelText("股票")).queryByText("5483")).toBeNull();
  });

  // review F8:重置一次做四件事,原本只有 selected 被間接驗到 —— 刪掉另外三行測試仍全綠
  it("關閉再開 → 改名輸入框 / 搜尋文字 / 錯誤文案都不殘留", async () => {
    const props = { wl: WL, onClose: vi.fn(), onGroupDeleted: vi.fn() };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <WatchlistManagerDialog open {...props} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("鴻海")).toBeTruthy());
    // 製造三種殘留:改名編輯態 / 搜尋框文字 / BAD_GROUP 錯誤文案
    fireEvent.click(screen.getByLabelText("改名 主力"));
    expect(screen.getByDisplayValue("主力")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/加入自選/), { target: { value: "2317" } });
    fireEvent.change(screen.getByPlaceholderText("群組名稱"), { target: { value: "觀察" } });
    fireEvent.keyDown(screen.getByPlaceholderText("群組名稱"), { key: "Enter" });
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());

    const view = (open: boolean) => (
      <QueryClientProvider client={client}>
        <WatchlistManagerDialog open={open} {...props} />
      </QueryClientProvider>
    );
    rerender(view(false));
    rerender(view(true));
    expect(screen.queryByDisplayValue("主力")).toBeNull(); // 改名態已離開
    expect((screen.getByPlaceholderText(/加入自選/) as HTMLInputElement).value).toBe("");
    expect(screen.queryByText("群組名稱不合法")).toBeNull();
  });
});

// 🔴 review A4(#101 §2.3 Spec 1):N115 收修把撞名判定搬進 transform 之後,`submitRename` 仍在
// commit **之前**無條件 `setRenaming(null)` —— 撞名時文案是非同步從佇列冒出來的,而編輯框已經關了、
// 使用者打的字消失。change-spec 說 eager「降級為純 UX(決定要不要清輸入框)」,那一半沒留下。
describe("WatchlistManagerDialog 改名被拒時保留編輯框(review A4)", () => {
  const { gatePuts, releaseOk } = makeGate();
  function startRename(to: string): HTMLInputElement {
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const input = screen.getByDisplayValue("主力") as HTMLInputElement;
    fireEvent.change(input, { target: { value: to } });
    fireEvent.keyDown(input, { key: "Enter" });
    return input;
  }

  it("改名撞既有名 → 文案出來時編輯框仍在、輸入不消失", async () => {
    open();
    startRename("觀察");
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    // 最常見的路徑:使用者看得到錯誤,也看得到自己剛打的字,直接改就好
    expect((screen.getByDisplayValue("觀察") as HTMLInputElement).value).toBe("觀察");
    expect(putBodies).toEqual([]);
  });

  it("改名 PUT 失敗(4xx)→ 編輯框保留可重試", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)) as Watchlist);
        return new Response(JSON.stringify({ detail: { error: "BAD_GROUP" } }), { status: 400 });
      }
      if (url.includes("/api/stock/names")) return new Response(JSON.stringify(NAMES));
      return new Response(JSON.stringify(WL));
    });
    open();
    startRename("強勢");
    await waitFor(() => expect(screen.getByText("群組名稱不合法")).toBeTruthy());
    expect(screen.getByDisplayValue("強勢")).toBeTruthy();
    // 重試:同一個編輯框再按 Enter 要能再送一發(守門在結果回來後解除)
    fireEvent.keyDown(screen.getByDisplayValue("強勢"), { key: "Enter" });
    await waitFor(() => expect(putBodies).toHaveLength(2));
  });

  it("改名成功 → 編輯框才關閉(既有行為,鎖住「不是永遠不關」)", async () => {
    open();
    startRename("強勢");
    await waitFor(() => expect(putBodies).toHaveLength(1));
    await waitFor(() => expect(screen.queryByDisplayValue("強勢")).toBeNull());
  });

  /** 編輯框在途仍開著之後的新失效樣態:不耐煩連按 Enter,第二發輪到時 `from` 已改名 →
   *  transform 看不到原組 → 不是假 BAD_GROUP 就是靜默 no-op。守門:在途期間忽略重送。 */
  it("改名在途連按 Enter → 只送一筆 PUT、無錯誤文案、成功後關框", async () => {
    gatePuts();
    open();
    const input = startRename("強勢");
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.keyDown(input, { key: "Enter" }); // 第一發在途,框還開著
    fireEvent.keyDown(input, { key: "Enter" });
    releaseOk();
    await waitFor(() => expect(screen.queryByDisplayValue("強勢")).toBeNull());
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
    expect(screen.queryByText("群組名稱不合法")).toBeNull();
  });

  /** review round-1 SP1:守門的解除不能只掛在 `onError` / `onDone` —— 佇列有零回呼的早退
   *  (`isSameWatchlist` 深比對 / 世代作廢 / 基底未載入)。最實的一條 = 刪組在途改名(N118 情境):
   *  輪到時 `from` 已不在,`renameGroup` 回同內容新物件 → 零 PUT 零回呼 → 守門永久卡死,之後
   *  每次 ✎ + Enter 全無反應、零訊號。守門必須在**這一發 settle**(不論哪條路)時解除。 */
  it("刪組在途改名(from 已消失)→ 零 PUT,之後改別組仍送得出去(守門一定解除)", async () => {
    gatePuts();
    open();
    fireEvent.click(screen.getByLabelText("刪除群組 觀察"));
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.click(screen.getByLabelText("改名 觀察")); // 列還在(wl prop 未更新),排隊在刪組後面
    const doomed = screen.getByDisplayValue("觀察");
    fireEvent.change(doomed, { target: { value: "舊組新名" } });
    fireEvent.keyDown(doomed, { key: "Enter" });
    releaseOk(); // 刪組落地 → 改名輪到時 from 已不在 → 深比對早退,零 PUT 零回呼
    await new Promise((r) => setTimeout(r, 30));
    expect(putBodies).toHaveLength(1);
    // 使用者放棄那個框,改去改另一組:守門若沒解除,這一發被靜默吞掉
    fireEvent.keyDown(doomed, { key: "Escape" });
    fireEvent.click(screen.getByLabelText("改名 主力"));
    const next = screen.getByDisplayValue("主力");
    fireEvent.change(next, { target: { value: "強勢" } });
    fireEvent.keyDown(next, { key: "Enter" });
    await waitFor(() => expect(putBodies).toHaveLength(2));
    expect(putBodies[1]!.groups.map((g) => g.name)).toEqual(["強勢"]);
    releaseOk();
  });

  it("A 組改名在途,Escape 後改 B 組 → B 那一發照送(守門綁單一動作,不是全窗)", async () => {
    gatePuts();
    open();
    const a = startRename("強勢"); // 主力 → 強勢,在途
    await waitFor(() => expect(putBodies).toHaveLength(1));
    fireEvent.keyDown(a, { key: "Escape" });
    fireEvent.click(screen.getByLabelText("改名 觀察"));
    const b = screen.getByDisplayValue("觀察");
    fireEvent.change(b, { target: { value: "追蹤" } });
    fireEvent.keyDown(b, { key: "Enter" });
    releaseOk();
    await waitFor(() => expect(putBodies).toHaveLength(2));
    expect(putBodies[1]!.groups.map((g) => g.name)).toEqual(["強勢", "追蹤"]);
    releaseOk();
  });
});
