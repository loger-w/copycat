/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignalRulesDialog } from "@/components/stock/SignalRulesDialog";
import type { SignalRule } from "@/hooks/useSignalRules";
import { wrap } from "@/test-utils";

const CDP: SignalRule = {
  id: "r1",
  name: "我的 CDP",
  kind: "cdp_cross",
  enabled: true,
  notify_discord: true,
  cooldown_secs: 300,
  params: { rearm_ticks: 2, rearm_dwell_secs: 300 },
  cdp_levels: ["ah", "nl"],
};

const VOL: SignalRule = {
  id: "r2",
  name: "開盤爆量",
  kind: "vol_burst",
  enabled: false,
  notify_discord: false,
  cooldown_secs: 600,
  params: {
    ratio: 3,
    window_secs: 60,
    min_elapsed_min: 5,
    min_window_lots: 100,
    min_day_lots: 500,
  },
  cdp_levels: [],
};

let calls: { url: string; init: RequestInit }[];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} });
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      if (init?.method === "POST" || init?.method === "PUT") {
        return new Response(String(init.body));
      }
      return new Response(JSON.stringify({ rules: [CDP, VOL] }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function open(rules: SignalRule[] = [CDP, VOL], isOpen = true, rulesError = false) {
  return wrap(
    <SignalRulesDialog open={isOpen} rules={rules} rulesError={rulesError} onClose={vi.fn()} />,
  );
}

/** 寫入型呼叫(GET 不算)—— 「零送出」斷言要排除清單重抓那些。 */
function writes(): { url: string; init: RequestInit }[] {
  return calls.filter((c) => c.init.method !== undefined);
}

/** **逐 token 比對不用子字串**:`flex-col` 恆在 class 上,`toContain("flex")`
 *  在關閉狀態下同樣為真 —— 那條斷言鎖不到 display 是否跟著 `open` 切。 */
function displayClasses(): string[] {
  return (screen.getByTestId("signal-rules-dialog").className ?? "").split(/\s+/);
}

describe("SignalRulesDialog 開關", () => {
  it("open=false → display 是 hidden 且內容不渲染", () => {
    open([CDP], false);
    expect(displayClasses()).toContain("hidden");
    expect(displayClasses()).not.toContain("flex");
    expect(screen.queryByText("我的 CDP")).toBeNull();
  });

  it("open=true → display 是 flex", () => {
    open();
    expect(displayClasses()).toContain("flex");
    expect(displayClasses()).not.toContain("hidden");
  });

  it("關閉鈕呼叫 onClose", () => {
    const onClose = vi.fn();
    wrap(<SignalRulesDialog open rules={[CDP]} rulesError={false} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("關閉"));
    expect(onClose.mock.calls.length).toBe(1);
  });
});

describe("SignalRulesDialog 列表", () => {
  it("每列 = 規則名 + 種類中文 + 一行摘要", () => {
    open();
    const row = within(screen.getByTestId("rule-row-r1"));
    expect(row.getByText("我的 CDP")).toBeTruthy();
    expect(row.getByText("CDP 穿越")).toBeTruthy();
    const text = screen.getByTestId("rule-row-r1").textContent ?? "";
    expect(text).toContain("AH+NL"); // 監看線
    expect(text).toContain("重新武裝 2 tick");
    // 🔴 SC-7:駐留秒數是 rearm 能不能解除的另一半門檻,摘要不印它 = 兩條規則
    // 只差在這一欄時列表上長得一模一樣
    expect(text).toContain("駐留 300 秒");
    expect(text).toContain("冷卻 300 秒");
  });

  it("爆量列摘要含倍率 / 窗長", () => {
    open();
    const text = screen.getByTestId("rule-row-r2").textContent ?? "";
    expect(text).toContain("爆量");
    expect(text).toContain("3 倍");
    expect(text).toContain("60 秒");
  });

  it("零規則 → 空態文案", () => {
    open([]);
    expect(screen.getByText("尚無規則 —— 用下方「新增規則」建立第一條")).toBeTruthy();
  });

  // review A5:載入失敗與「真的零規則」在畫面上一樣 → 使用者照著空態去新增,
  // 而真值可能是四條規則好好跑著(新增只會撞名失敗)
  it("規則載入失敗 → 失敗文案而非零規則空態", () => {
    open([], true, true);
    expect(screen.getByText(/規則載入失敗/)).toBeTruthy();
    expect(screen.queryByText("尚無規則 —— 用下方「新增規則」建立第一條")).toBeNull();
  });

  // review B6:MAX_RULES = 30 是後端硬上限,按得下去只會拿到一句 INVALID_RULE,
  // 而畫面上完全看不出「是因為滿了」
  it("規則數達上限 30 → 新增規則鈕停用並說明原因", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ ...CDP, id: `r${i}`, name: `規則${i}` }));
    open(many);
    const btn = screen.getByRole("button", { name: "新增規則" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain("30");
  });
});

describe("SignalRulesDialog 刪除", () => {
  it("刪除要二次確認,確認後才 DELETE", async () => {
    open();
    fireEvent.click(screen.getByLabelText("刪除 開盤爆量"));
    expect(writes()).toHaveLength(0); // 第一下只是問
    fireEvent.click(screen.getByLabelText("確定刪除 開盤爆量"));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]?.url).toBe("/api/stock/signals/rules/r2");
    expect(writes()[0]?.init.method).toBe("DELETE");
  });

  it("取消刪除 → 零送出", async () => {
    open();
    fireEvent.click(screen.getByLabelText("刪除 開盤爆量"));
    fireEvent.click(screen.getByLabelText("取消刪除 開盤爆量"));
    expect(screen.queryByLabelText("確定刪除 開盤爆量")).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect(writes()).toHaveLength(0);
  });
});

describe("SignalRulesDialog 編輯表單", () => {
  it("新增規則 → 表單出現,種類 select 四類中文", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    const select = screen.getByLabelText("種類") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "CDP 穿越",
      "爆拉爆跌",
      "爆量",
      "鎖漲跌停",
    ]);
    expect(screen.getByLabelText("名稱")).toBeTruthy();
    expect(screen.getByLabelText("冷卻秒數")).toBeTruthy();
    expect(screen.getByLabelText("Discord 通知")).toBeTruthy();
  });

  it("冷卻秒數輸入框帶後端值域(min 60 / max 86400)", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    const input = screen.getByLabelText("冷卻秒數") as HTMLInputElement;
    expect(input.getAttribute("min")).toBe("60");
    expect(input.getAttribute("max")).toBe("86400");
  });

  /** 🔴 N055:參數欄原本一律只有 `step`,值域全交給後端 —— 使用者填 `rearm_dwell_secs`
   *  = 99999 送出去只拿到一句「規則設定不合法」,不知道是哪一格、也不知道界在哪。
   *  冷卻秒數早就有 min/max(既有慣例),參數欄同款補齊(表與後端 PARAM_SPECS 同源,
   *  parity 由 `signal-param-parity.test.ts` 釘)。 */
  it("參數欄位帶後端值域(min/max)", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    const dwell = screen.getByLabelText("線外駐留秒數") as HTMLInputElement;
    expect([dwell.getAttribute("min"), dwell.getAttribute("max")]).toEqual(["0", "3600"]);
    const ticks = screen.getByLabelText("重新武裝 tick 數") as HTMLInputElement;
    expect([ticks.getAttribute("min"), ticks.getAttribute("max")]).toEqual(["0", "50"]);

    fireEvent.change(screen.getByLabelText("種類"), { target: { value: "surge_crash" } });
    const win = screen.getByLabelText("時間窗(秒)") as HTMLInputElement;
    expect([win.getAttribute("min"), win.getAttribute("max")]).toEqual(["10", "3600"]);
    const pct = screen.getByLabelText("漲跌幅 %") as HTMLInputElement;
    expect([pct.getAttribute("min"), pct.getAttribute("max")]).toEqual(["0.1", "50"]);
  });

  it("參數超出值域 → 零送出並指出是哪一格(N055)", async () => {
    open();
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    fireEvent.change(screen.getByLabelText("線外駐留秒數"), { target: { value: "99999" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(screen.getByText("線外駐留秒數須在 0–3600 之間")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("線外駐留秒數"), { target: { value: "300" } });
    fireEvent.change(screen.getByLabelText("重新武裝 tick 數"), { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(screen.getByText("重新武裝 tick 數須在 0–50 之間")).toBeTruthy();

    await new Promise((r) => setTimeout(r, 20));
    expect(writes()).toHaveLength(0);
  });

  it("值域邊界值(恰等於 min / max)照樣送得出去(閉區間,與後端同)", async () => {
    open();
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    fireEvent.change(screen.getByLabelText("線外駐留秒數"), { target: { value: "3600" } });
    fireEvent.change(screen.getByLabelText("重新武裝 tick 數"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    const body = JSON.parse(String(writes()[0]!.init.body)) as Record<string, unknown>;
    expect(body.params).toEqual({ rearm_ticks: 0, rearm_dwell_secs: 3600 });
  });

  it("kind 專屬數字欄位隨種類切換(爆量五欄 / 鎖漲跌停零欄)", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    const select = screen.getByLabelText("種類");

    fireEvent.change(select, { target: { value: "vol_burst" } });
    expect(screen.getByLabelText("量能倍率")).toBeTruthy();
    expect(screen.getByLabelText("時間窗(秒)")).toBeTruthy();
    expect(screen.getByLabelText("開盤後最少分鐘")).toBeTruthy();
    expect(screen.getByLabelText("窗內最少張數")).toBeTruthy();
    expect(screen.getByLabelText("當日最少張數")).toBeTruthy();

    fireEvent.change(select, { target: { value: "limit_lock" } });
    expect(screen.queryByLabelText("量能倍率")).toBeNull();
    expect(screen.queryByLabelText("時間窗(秒)")).toBeNull();
  });

  it("CDP 五線勾選只在 cdp_cross 顯示", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    for (const label of ["監看 AH", "監看 NH", "監看 中軸", "監看 NL", "監看 AL"]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    fireEvent.change(screen.getByLabelText("種類"), { target: { value: "surge_crash" } });
    expect(screen.queryByLabelText("監看 AH")).toBeNull();
  });

  it("編輯既有規則 → 欄位帶入現值,儲存送 PUT 到該 id", async () => {
    open();
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    expect((screen.getByLabelText("名稱") as HTMLInputElement).value).toBe("我的 CDP");
    expect((screen.getByLabelText("冷卻秒數") as HTMLInputElement).value).toBe("300");
    expect((screen.getByLabelText("監看 AH") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("監看 NH") as HTMLInputElement).checked).toBe(false);

    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "改名後" } });
    fireEvent.click(screen.getByLabelText("監看 NH"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const put = writes()[0]!;
    expect(put.url).toBe("/api/stock/signals/rules/r1");
    expect(put.init.method).toBe("PUT");
    const body = JSON.parse(String(put.init.body)) as SignalRule;
    expect(body.name).toBe("改名後");
    expect(body.cdp_levels).toEqual(["ah", "nh", "nl"]); // 固定序,不是點擊序
  });

  it("新增後儲存送 POST(無 id),數字欄位轉成 number", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    fireEvent.change(screen.getByLabelText("種類"), { target: { value: "surge_crash" } });
    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "急拉" } });
    fireEvent.change(screen.getByLabelText("漲跌幅 %"), { target: { value: "2.5" } });
    fireEvent.change(screen.getByLabelText("時間窗(秒)"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("冷卻秒數"), { target: { value: "600" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const post = writes()[0]!;
    expect(post.url).toBe("/api/stock/signals/rules");
    expect(post.init.method).toBe("POST");
    const body = JSON.parse(String(post.init.body)) as Record<string, unknown>;
    expect(body.id).toBeUndefined();
    expect(body.name).toBe("急拉");
    expect(body.kind).toBe("surge_crash");
    expect(body.cooldown_secs).toBe(600);
    expect(body.params).toEqual({ pct: 2.5, window_secs: 90 });
    expect(body.cdp_levels).toEqual([]);
  });

  // SC-7:CDP 的 rearm 加了「線外駐留」門檻,params 鍵集必須與後端 PARAM_SPECS
  // 完全相同(缺鍵同樣是 INVALID_RULE)—— 欄位在畫面上、值在 payload 裡各釘一次
  it("CDP 規則有「線外駐留秒數」欄位(預設 300),送出 payload 帶 rearm_dwell_secs", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    const dwell = screen.getByLabelText("線外駐留秒數") as HTMLInputElement;
    expect(dwell.value).toBe("300");

    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "CDP 新規" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const body = JSON.parse(String(writes()[0]!.init.body)) as Record<string, unknown>;
    expect(body.params).toEqual({ rearm_ticks: 2, rearm_dwell_secs: 300 });
  });

  it("名稱空白 / 數字欄位非數字 → 零送出並顯示文案", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    fireEvent.click(screen.getByRole("button", { name: "儲存" })); // 名稱空
    expect(screen.getByText("規則設定不合法")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "壞數字" } });
    fireEvent.change(screen.getByLabelText("冷卻秒數"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    await new Promise((r) => setTimeout(r, 20));
    expect(writes()).toHaveLength(0);
  });

  // review B6:值域交給後端時,使用者拿到的是一句「規則設定不合法」,不知道是哪一格
  it("冷卻秒數超出 60–86400 → 零送出並指出是哪一格", async () => {
    open();
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    fireEvent.change(screen.getByLabelText("冷卻秒數"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(screen.getByText("冷卻秒數須在 60–86400 之間")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("冷卻秒數"), { target: { value: "90000" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(screen.getByText("冷卻秒數須在 60–86400 之間")).toBeTruthy();

    await new Promise((r) => setTimeout(r, 20));
    expect(writes()).toHaveLength(0);
  });

  it("後端 400 INVALID_RULE → 顯示中文文案(點了不能像沒反應)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method !== undefined) {
          return new Response(JSON.stringify({ detail: { error: "INVALID_RULE" } }), {
            status: 400,
          });
        }
        return new Response(JSON.stringify({ rules: [CDP] }));
      }),
    );
    open([CDP]);
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(screen.getByText("規則設定不合法")).toBeTruthy());
  });

  it("儲存成功 → 收起表單回到列表", async () => {
    open();
    fireEvent.click(screen.getByLabelText("編輯 我的 CDP"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(screen.queryByLabelText("名稱")).toBeNull());
  });

  it("取消 → 收起表單且零送出", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "新增規則" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByLabelText("名稱")).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect(writes()).toHaveLength(0);
  });
});
