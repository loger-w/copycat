/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignalRail } from "@/components/stock/SignalRail";
import type { SignalRule } from "@/hooks/useSignalRules";
import type { SignalMsg } from "@/lib/signal-model";

type Props = ComponentProps<typeof SignalRail>;

afterEach(cleanup);

function sig(o: Partial<SignalMsg> = {}): SignalMsg {
  return {
    type: "signal",
    id: "2026-08-04|r-1-000|2330|limit_lock|up|1",
    kind: "limit_lock",
    code: "2330",
    name: "台積電",
    price: 1_050_000,
    time: "09:31:22",
    levels: [],
    direction: "up",
    pct: null,
    touch_count: 1,
    ...o,
  };
}

function rule(o: Partial<SignalRule> = {}): SignalRule {
  return {
    id: "r-1-000",
    name: "鎖漲跌停",
    kind: "limit_lock",
    enabled: true,
    notify_discord: true,
    cooldown_secs: 300,
    params: {},
    cdp_levels: [],
    ...o,
  };
}

/** 資料 props 可覆寫;回呼固定是 spy(覆寫回呼的話回傳的就不是實際掛上去的那顆)。 */
function renderRail(
  o: Partial<
    Pick<
      Props,
      | "signals"
      | "rules"
      | "notifPermission"
      | "soundOn"
      | "rulesError"
      | "toggleError"
      | "tradeDate"
      | "today"
    >
  > = {},
) {
  const spies = {
    onToggleRule: vi.fn<Props["onToggleRule"]>(),
    onOpenManager: vi.fn<Props["onOpenManager"]>(),
    onSelect: vi.fn<Props["onSelect"]>(),
    onRequestNotif: vi.fn<Props["onRequestNotif"]>(),
    onToggleSound: vi.fn<Props["onToggleSound"]>(),
  };
  render(
    <SignalRail
      signals={[]}
      rules={[]}
      rulesError={false}
      toggleError={null}
      notifPermission="granted"
      soundOn
      {...spies}
      {...o}
    />,
  );
  return spies;
}

function rowTexts(): string[] {
  return [...within(screen.getByTestId("signal-rail-list")).getAllByRole("listitem")].map(
    (li) => li.textContent ?? "",
  );
}

describe("SignalRail 訊號列", () => {
  it("列格式:HH:MM 代號 名稱 + 訊號中文名 價格", () => {
    renderRail({ signals: [sig()] });
    const [text = ""] = rowTexts();
    expect(text).toContain("09:31");
    expect(text).not.toContain("09:31:22"); // 秒不顯示(窄欄)
    expect(text).toContain("2330");
    expect(text).toContain("台積電");
    expect(text).toContain("鎖漲停");
    expect(text).toContain("1050");
  });

  // review B1:規則名**蓋掉** kind 文案時,盤中最重要的兩個資訊(發生什麼事 / 幾 %)
  // 只剩 hover 才看得到,而規則名可以取成任意字串 —— 列表可能整片是「我的規則1」。
  it("副標並列:kind 文案為主 + 規則名為次(同 kind 多規則靠它辨識來源)", () => {
    renderRail({
      signals: [sig({ kind: "surge", direction: null, pct: 2.5, rule_name: "早盤急拉" })],
    });
    const [text = ""] = rowTexts();
    expect(text).toContain("爆拉 +2.50%"); // 主文:事件本身
    expect(text).toContain("早盤急拉"); // 次級:哪條規則發的
  });

  it("rule_name 缺值(升級當日的舊 jsonl)→ 只有 kind 文案,不留空分隔", () => {
    renderRail({ signals: [sig({ kind: "surge", direction: null, pct: 2.5 })] });
    const [text = ""] = rowTexts();
    expect(text).toContain("爆拉 +2.50%");
    expect(text).not.toContain("・"); // 分隔符不得單獨留下
  });

  it("最新在上:signals 的順序即 DOM 序", () => {
    renderRail({
      signals: [
        sig({ id: "new", code: "2454", name: "聯發科" }),
        sig({ id: "old", code: "2317", name: "鴻海" }),
      ],
    });
    const texts = rowTexts();
    expect(texts[0]).toContain("2454");
    expect(texts[1]).toContain("2317");
  });

  it("點列 → onSelect(code)", () => {
    const { onSelect } = renderRail({ signals: [sig({ code: "2317", name: "鴻海" })] });
    fireEvent.click(screen.getByText("2317"));
    expect(onSelect.mock.calls).toEqual([["2317"]]);
  });

  // 🔴 R14a:filterKinds 移除的行為改動。關掉規則後**不再**隱藏它今天已經發過的列
  // (那些列帶規則名,來源可辨識);原本的隱藏語意取消。
  it("關閉規則的歷史列仍顯示(R14a 行為改動)", () => {
    renderRail({
      signals: [
        sig({ id: "a", kind: "limit_lock", code: "2330", rule_name: "鎖漲跌停" }),
        sig({ id: "b", kind: "vol_burst", code: "2317", pct: 3.5, direction: null }),
      ],
      rules: [rule({ enabled: false })],
    });
    const texts = rowTexts();
    expect(texts.length).toBe(2);
    expect(texts[0]).toContain("2330");
  });

  it("訊號漲跌方向著色(bull / bear)", () => {
    renderRail({
      signals: [
        sig({ id: "a", kind: "surge", direction: null, pct: 1.2 }),
        sig({ id: "b", kind: "crash", direction: null, pct: -1.2 }),
      ],
    });
    // scope 收在清單內:規則區的規則名同樣可能含這些詞
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText(/爆拉/).className).toContain("text-bull");
    expect(list.getByText(/爆跌/).className).toContain("text-bear");
  });

  it("空態顯示尚無訊號", () => {
    renderRail({ signals: [] });
    expect(screen.getByText("尚無訊號")).toBeTruthy();
  });
});

/** SC-5:同一 tick 常常同時打出 CDP 穿越 + 爆拉/爆跌,逐則一列時同一個時間點就吃掉
 *  三四列 —— 200px 寬的欄位一眼看過去全是同一秒同一檔。 */
describe("SignalRail 同 tick 合併列(SC-5)", () => {
  const CDP = sig({
    id: "a",
    kind: "cdp_cross",
    levels: ["cdp"],
    direction: "from_below",
    pct: null,
    rule_name: "CDP 穿越",
  });
  const CRASH = sig({ id: "b", kind: "crash", direction: null, pct: -2.1, rule_name: "爆拉爆跌" });

  it("同 code 同 time 的多則 → 一列,kind 文案以「・」串接", () => {
    renderRail({ signals: [CDP, CRASH] });
    const texts = rowTexts();
    expect(texts.length).toBe(1);
    // 段序 = 到達序(輸入新在前 → 反序),與 Discord 合併訊息 rows[0] 同一則
    expect(texts[0]).toContain("爆跌 -2.10%・突破 CDP 中軸");
    expect(texts[0]).toContain("爆拉爆跌・CDP 穿越"); // 規則名段序與 kind 段一致(到達序)
  });

  // T-12:「・」只是視覺分隔,讀螢幕器唸出來會把兩段文案黏成一句聽不懂的字串
  it("段間分隔符對輔助技術隱藏(aria-hidden)", () => {
    renderRail({ signals: [CDP, CRASH] });
    const list = within(screen.getByTestId("signal-rail-list"));
    // kind 段與規則名段各自一個分隔符(B3 起規則名段也逐段 span),各自都要藏
    const kindSpan = list.getByText("突破 CDP 中軸").parentElement!;
    const ruleSpan = list.getByText("CDP 穿越").parentElement!;
    for (const span of [kindSpan, ruleSpan]) {
      const seps = within(span).getAllByText("・");
      expect(seps.length).toBe(1);
      expect(seps[0]?.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("合併列每段各自著色(整段套同一色會把爆跌畫成紅的)", () => {
    renderRail({ signals: [CDP, CRASH] });
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText("突破 CDP 中軸").className).toContain("text-bull");
    expect(list.getByText("爆跌 -2.10%").className).toContain("text-bear");
  });

  it("合併列的價格 / 時間取組內最早到的那則,點列仍 onSelect(code)", () => {
    const { onSelect } = renderRail({
      signals: [sig({ ...CDP, price: 1_050_000 }), sig({ ...CRASH, price: 999_000 })],
    });
    const [text = ""] = rowTexts();
    expect(text).toContain("999"); // 最早到(輸入末筆)的價格,不是最新到的 1050
    expect(text).not.toContain("1050");
    fireEvent.click(screen.getByText("2330"));
    expect(onSelect.mock.calls).toEqual([["2330"]]);
  });

  it("同 code 不同 time → 各自成列(不跨秒合併)", () => {
    renderRail({
      signals: [
        sig({ id: "t1", time: "09:31:24" }),
        sig({ id: "t2", time: "09:31:23" }),
        sig({ id: "t3", time: "09:31:22" }),
      ],
    });
    expect(rowTexts().length).toBe(3);
  });

  // edge 7:被別檔同秒 row 隔開的同 (code, time) 不跨列搜尋(顯示保守正確)
  it("同 (code, time) 但不相鄰 → 不合併", () => {
    renderRail({
      signals: [CDP, sig({ id: "x", code: "2317", name: "鴻海" }), CRASH],
    });
    expect(rowTexts().length).toBe(3);
  });
});

describe("SignalRail 合併列可讀性(B3:換行 + 逐段 title)", () => {
  // 2026-08-20 prod 實錄:「跌破 CDP 中軸・爆跌 -2.06%」在 189px 列內只分到 95px
  const CDP_DOWN = sig({
    id: "a",
    kind: "cdp_cross",
    levels: ["cdp"],
    direction: "from_above",
    pct: null,
    rule_name: "CDP 穿越",
  });
  const CRASH = sig({ id: "b", kind: "crash", direction: null, pct: -2.06, rule_name: "爆拉爆跌" });

  it("SC-1 合併列 kind 段不 truncate,改 clamp 2 行;單則列維持 truncate", () => {
    renderRail({ signals: [CRASH, CDP_DOWN, sig({ id: "s", code: "2317", name: "鴻海" })] });
    const list = within(screen.getByTestId("signal-rail-list"));
    const mergedKind = list.getByText("跌破 CDP 中軸").parentElement;
    expect(mergedKind?.className).toContain("line-clamp-2");
    expect(mergedKind?.className).not.toContain("truncate");
    const singleKind = list.getByText("鎖漲停").parentElement;
    expect(singleKind?.className).toContain("truncate");
    expect(singleKind?.className).not.toContain("line-clamp-2");
    // D2 堆疊:合併列 wrapper 走 flex-col(規則名另起一行),單則列仍並排
    expect(mergedKind?.parentElement?.className).toContain("flex-col");
    expect(singleKind?.parentElement?.className).not.toContain("flex-col");
    // 規則名段固定 truncate(堆疊後已有整行寬;列高上限 = 1 + 2 + 1 行)
    expect(list.getByText("CDP 穿越").parentElement?.className).toContain("truncate");
  });

  it("SC-1 edge:三段合併(cdp+crash+vol_burst)→ 仍 clamp 2、三段 title 各自完整、分隔符 2 個", () => {
    const VOL = sig({ id: "v", kind: "vol_burst", direction: null, pct: 3.5, rule_name: "我的爆量" });
    renderRail({ signals: [VOL, CRASH, CDP_DOWN] });
    const list = within(screen.getByTestId("signal-rail-list"));
    const kindSpan = list.getByText("跌破 CDP 中軸").parentElement!;
    expect(kindSpan.className).toContain("line-clamp-2");
    expect(within(kindSpan).getAllByText("・").length).toBe(2);
    expect(list.getByText("爆量 3.5 倍").getAttribute("title")).toBe("爆量 3.5 倍(我的爆量)");
    expect(list.getByText("爆跌 -2.06%").getAttribute("title")).toBe("爆跌 -2.06%(爆拉爆跌)");
    expect(list.getByText("跌破 CDP 中軸").getAttribute("title")).toBe("跌破 CDP 中軸(CDP 穿越)");
  });

  it("SC-2 逐段 title:kind span = label(rule);規則名 span = rule:kind labels", () => {
    renderRail({ signals: [CRASH, CDP_DOWN] });
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText("跌破 CDP 中軸").getAttribute("title")).toBe("跌破 CDP 中軸(CDP 穿越)");
    expect(list.getByText("爆跌 -2.06%").getAttribute("title")).toBe("爆跌 -2.06%(爆拉爆跌)");
    expect(list.getByText("CDP 穿越").getAttribute("title")).toBe("CDP 穿越:跌破 CDP 中軸");
    expect(list.getByText("爆拉爆跌").getAttribute("title")).toBe("爆拉爆跌:爆跌 -2.06%");
  });

  it("SC-2 edge:rule_name 缺值(undefined / 空字串)→ title 只有 label、無規則名段、kind 仍 clamp 2", () => {
    renderRail({
      signals: [sig({ ...CRASH, rule_name: "" }), sig({ ...CDP_DOWN, rule_name: undefined })],
    });
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText("跌破 CDP 中軸").getAttribute("title")).toBe("跌破 CDP 中軸");
    expect(list.getByText("爆跌 -2.06%").getAttribute("title")).toBe("爆跌 -2.06%"); // 不是「爆跌 -2.06%()」
    expect(list.queryByText("CDP 穿越")).toBeNull();
    expect(list.getByText("跌破 CDP 中軸").parentElement?.className).toContain("line-clamp-2");
    expect(list.getAllByText("・").length).toBe(1); // 只剩 kind 段那一個
  });

  it("SC-2 edge:同 kind 兩規則 → kind 段一段、規則名兩段各指回同一 label", () => {
    renderRail({
      signals: [sig({ ...CRASH, id: "c2", rule_name: "爆跌備援" }), CRASH],
    });
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getAllByText("爆跌 -2.06%").length).toBe(1);
    expect(list.getByText("爆拉爆跌").getAttribute("title")).toBe("爆拉爆跌:爆跌 -2.06%");
    expect(list.getByText("爆跌備援").getAttribute("title")).toBe("爆跌備援:爆跌 -2.06%");
    // kind span title 取首見(最早到 = 輸入末筆 CRASH)的 rule_name
    expect(list.getByText("爆跌 -2.06%").getAttribute("title")).toBe("爆跌 -2.06%(爆拉爆跌)");
    // 規則名兩段 = 真合併列:同樣走堆疊版型,不然兩規則名與 kind 並排照樣被切
    expect(list.getByText("爆跌 -2.06%").parentElement?.parentElement?.className).toContain("flex-col");
  });

  it("SC-2 edge:單一規則同 tick 兩 kind → 規則名 title 依到達序列出、同 label 去重", () => {
    renderRail({
      signals: [
        sig({ ...CDP_DOWN, id: "dup", rule_name: "組合規則" }), // 最新到:與下一則同 label → 去重
        sig({ ...CDP_DOWN, id: "k2", rule_name: "組合規則" }),
        sig({ ...CRASH, id: "k1", rule_name: "組合規則" }), // 最早到
      ],
    });
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText("組合規則").getAttribute("title")).toBe("組合規則:爆跌 -2.06%・跌破 CDP 中軸");
  });
});

describe("SignalRail 規則區", () => {
  const RULES = [
    rule({ id: "r1", name: "CDP 穿越", kind: "cdp_cross", cdp_levels: ["ah"] }),
    rule({ id: "r2", name: "我的爆量", kind: "vol_burst", enabled: false }),
  ];

  it("每條規則一列:規則名 + 開關(反映 enabled)", () => {
    renderRail({ rules: RULES });
    const rules = within(screen.getByTestId("signal-rail-rules"));
    expect(rules.getAllByRole("switch").length).toBe(2);
    expect(rules.getByRole("switch", { name: /CDP 穿越/ }).getAttribute("aria-checked")).toBe(
      "true",
    );
    expect(rules.getByRole("switch", { name: /我的爆量/ }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("點規則開關 → onToggleRule(整條規則)", () => {
    const { onToggleRule } = renderRail({ rules: RULES });
    const rules = within(screen.getByTestId("signal-rail-rules"));
    fireEvent.click(rules.getByRole("switch", { name: /我的爆量/ }));
    expect(onToggleRule.mock.calls).toEqual([[RULES[1]]]);
  });

  it("欄頂「規則」鈕 → onOpenManager", () => {
    const { onOpenManager } = renderRail({ rules: RULES });
    fireEvent.click(screen.getByRole("button", { name: "管理訊號規則" }));
    expect(onOpenManager.mock.calls.length).toBe(1);
  });

  it("零規則 → 空態文案(不是空白區塊)", () => {
    renderRail({ rules: [] });
    expect(within(screen.getByTestId("signal-rail-rules")).getByText("尚無規則")).toBeTruthy();
  });

  // review A5:GET 失敗與「真的沒有規則」在畫面上一模一樣 —— 使用者會照著空態去新增,
  // 而真值可能是四條規則好好跑著,新增只會撞名失敗
  it("規則載入失敗 → 失敗文案,不是「尚無規則」", () => {
    renderRail({ rules: [], rulesError: true });
    const rules = within(screen.getByTestId("signal-rail-rules"));
    expect(rules.getByText("規則載入失敗")).toBeTruthy();
    expect(rules.queryByText("尚無規則")).toBeNull();
  });

  // review B7:PUT 失敗時開關會彈回原位,沒有文案的話看起來就是「點了沒反應」
  it("規則開關失敗 → 規則區一行錯誤文案(共用 errText)", () => {
    renderRail({ rules: RULES, toggleError: "RULE_SAVE_FAILED" });
    expect(
      within(screen.getByTestId("signal-rail-rules")).getByText("規則儲存失敗"),
    ).toBeTruthy();
  });
});

describe("SignalRail 提示區", () => {
  it("音效 toggle 反轉 soundOn", () => {
    const { onToggleSound } = renderRail({ soundOn: true });
    fireEvent.click(screen.getByRole("switch", { name: /提示音/ }));
    expect(onToggleSound.mock.calls).toEqual([[false]]);
  });

  it("提示音 / 允許通知在獨立的「提示」區,不與規則同組(review MFS-5)", () => {
    renderRail({
      notifPermission: "default",
      rules: [rule({ id: "r1", name: "CDP 穿越", kind: "cdp_cross", cdp_levels: ["ah"] })],
    });
    const rules = within(screen.getByTestId("signal-rail-rules"));
    const alerts = within(screen.getByTestId("signal-rail-alerts"));

    expect(screen.getByTestId("signal-rail-alerts").textContent).toContain("提示");
    expect(alerts.getByRole("switch", { name: /提示音/ })).toBeTruthy();
    expect(alerts.getByText(/允許通知/)).toBeTruthy();
    // 規則區只剩規則列(提示音不在其中,否則會被讀成第五條規則)
    expect(rules.getAllByRole("switch").length).toBe(1);
    expect(rules.queryByRole("switch", { name: /提示音/ })).toBeNull();
    expect(rules.queryByText(/允許通知/)).toBeNull();
  });

  it("permission default 才出現允許通知鈕,點擊觸發 onRequestNotif", () => {
    const { onRequestNotif } = renderRail({ notifPermission: "default" });
    fireEvent.click(screen.getByText(/允許通知/));
    expect(onRequestNotif.mock.calls.length).toBe(1);
  });

  it("permission granted / denied 不出現允許通知鈕", () => {
    renderRail({ notifPermission: "granted" });
    expect(screen.queryByText(/允許通知/)).toBeNull();
    cleanup();
    renderRail({ notifPermission: "denied" });
    expect(screen.queryByText(/允許通知/)).toBeNull();
  });
});

// 🔴 SC-2(D3' / AR5):標題帶資料日。假日 / 盤前開站時 rail 掛的是**上一交易日**的
// jsonl,而「今日訊號」四個字會讓人把昨天的鎖漲停當成剛剛發生的。日期一律由後端
// 兩欄(hub 的 engine 日 vs 牆鐘日)決定 —— 瀏覽器時鐘與後端日別是兩回事。
describe("SignalRail 標題資料日(SC-2)", () => {
  function titleText(): string {
    return screen.getByRole("heading", { name: /訊號$/ }).textContent ?? "";
  }
  function railLabel(): string | null {
    return screen.getByTestId("signal-rail").getAttribute("aria-label");
  }

  it("兩欄皆不傳(既有呼叫端 / 舊後端)→ 今日訊號", () => {
    renderRail();
    expect(titleText()).toBe("今日訊號");
    expect(railLabel()).toBe("今日訊號");
  });

  it("tradeDate = today(當日盤中)→ 今日訊號(W2 逐字不變)", () => {
    renderRail({ tradeDate: "2026-08-21", today: "2026-08-21" });
    expect(titleText()).toBe("今日訊號");
    expect(railLabel()).toBe("今日訊號");
  });

  it("tradeDate ≠ today(假日 / 盤前)→ 「MM-DD 訊號」,aria-label 同步", () => {
    renderRail({ tradeDate: "2026-08-20", today: "2026-08-21" });
    expect(titleText()).toBe("08-20 訊號");
    expect(railLabel()).toBe("08-20 訊號");
  });

  it("任一欄為 null(payload 缺欄)→ 今日訊號(不拿單邊猜)", () => {
    renderRail({ tradeDate: "2026-08-20", today: null });
    expect(titleText()).toBe("今日訊號");
    cleanup();
    renderRail({ tradeDate: null, today: "2026-08-21" });
    expect(titleText()).toBe("今日訊號");
  });

  // review C-6:`!= null` 放空字串過去 —— 後端欄位存在但為 ""(hub 未就緒 / 舊 jsonl
  // 的空日別)時 `monthDay("")` 回 ""、標題變成「 訊號」,那是誰都讀不懂的字串,
  // 而且與「今日」在畫面上只差一個空格。缺值的兩種形(null / "")要走同一條退路。
  it("任一欄為空字串 → 今日訊號(空字串與缺欄同義,不印「 訊號」)", () => {
    renderRail({ tradeDate: "", today: "2026-08-21" });
    expect(titleText()).toBe("今日訊號");
    expect(railLabel()).toBe("今日訊號");
    cleanup();
    renderRail({ tradeDate: "2026-08-20", today: "" });
    expect(titleText()).toBe("今日訊號");
  });
});
