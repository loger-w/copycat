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
  o: Partial<Pick<Props, "signals" | "rules" | "notifPermission" | "soundOn">> = {},
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

  it("帶 rule_name 的列副標顯示規則名(同 kind 多規則靠它辨識來源)", () => {
    renderRail({ signals: [sig({ rule_id: "r-1-002", rule_name: "早盤鎖板" })] });
    const [text = ""] = rowTexts();
    expect(text).toContain("早盤鎖板");
  });

  it("rule_name 缺值(升級當日的舊 jsonl)→ 退回既有 kind 文案", () => {
    renderRail({ signals: [sig({ kind: "surge", direction: null, pct: 2.5 })] });
    const [text = ""] = rowTexts();
    expect(text).toContain("爆拉 +2.50%");
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
