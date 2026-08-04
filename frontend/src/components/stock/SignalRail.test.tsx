/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignalRail } from "@/components/stock/SignalRail";
import type { SignalEnabled, SignalMsg } from "@/lib/signal-model";

type Props = ComponentProps<typeof SignalRail>;

afterEach(cleanup);

const ALL_ON: SignalEnabled = {
  cdp_cross: true,
  surge_crash: true,
  vol_burst: true,
  limit_lock: true,
};

function sig(o: Partial<SignalMsg> = {}): SignalMsg {
  return {
    type: "signal",
    id: "2026-08-04|2330|limit_lock|up|1",
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

/** 資料 props 可覆寫;四個回呼固定是 spy(覆寫回呼的話回傳的就不是實際掛上去的那顆)。 */
function renderRail(
  o: Partial<Pick<Props, "signals" | "enabled" | "notifPermission" | "soundOn">> = {},
) {
  const spies = {
    onToggle: vi.fn<Props["onToggle"]>(),
    onSelect: vi.fn<Props["onSelect"]>(),
    onRequestNotif: vi.fn<Props["onRequestNotif"]>(),
    onToggleSound: vi.fn<Props["onToggleSound"]>(),
  };
  render(
    <SignalRail
      signals={[]}
      enabled={ALL_ON}
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

describe("SignalRail", () => {
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

  it("停用的 kind 不入列(SC-9)", () => {
    renderRail({
      signals: [
        sig({ id: "a", kind: "limit_lock", code: "2330" }),
        sig({ id: "b", kind: "vol_burst", code: "2317", pct: 3.5, direction: null }),
      ],
      enabled: { ...ALL_ON, limit_lock: false },
    });
    const texts = rowTexts();
    expect(texts.length).toBe(1);
    expect(texts[0]).toContain("2317");
  });

  it("訊號漲跌方向著色(bull / bear)", () => {
    renderRail({
      signals: [
        sig({ id: "a", kind: "surge", direction: null, pct: 1.2 }),
        sig({ id: "b", kind: "crash", direction: null, pct: -1.2 }),
      ],
    });
    // scope 收在清單內:下半的「爆拉爆跌」toggle 標籤同樣含這兩個詞
    const list = within(screen.getByTestId("signal-rail-list"));
    expect(list.getByText(/爆拉/).className).toContain("text-bull");
    expect(list.getByText(/爆跌/).className).toContain("text-bear");
  });

  it("空態顯示尚無訊號", () => {
    renderRail({ signals: [] });
    expect(screen.getByText("尚無訊號")).toBeTruthy();
  });

  it("四個 toggle 各自呼叫 onToggle(鍵, 反轉值)", () => {
    const { onToggle } = renderRail({ enabled: { ...ALL_ON, vol_burst: false } });
    for (const label of ["CDP 穿越", "爆拉爆跌", "爆量", "鎖漲跌停"]) {
      fireEvent.click(screen.getByRole("switch", { name: new RegExp(label) }));
    }
    expect(onToggle.mock.calls).toEqual([
      ["cdp_cross", false],
      ["surge_crash", false],
      ["vol_burst", true],
      ["limit_lock", false],
    ]);
  });

  it("音效 toggle 反轉 soundOn", () => {
    const { onToggleSound } = renderRail({ soundOn: true });
    fireEvent.click(screen.getByRole("switch", { name: /提示音/ }));
    expect(onToggleSound.mock.calls).toEqual([[false]]);
  });

  it("提示音 / 允許通知在獨立的「提示」區,不與四鍵同組(review MFS-5)", () => {
    renderRail({ notifPermission: "default" });
    const kinds = within(screen.getByTestId("signal-rail-kinds"));
    const alerts = within(screen.getByTestId("signal-rail-alerts"));

    expect(screen.getByTestId("signal-rail-alerts").textContent).toContain("提示");
    // 提示音與允許通知都在提示區
    expect(alerts.getByRole("switch", { name: /提示音/ })).toBeTruthy();
    expect(alerts.getByText(/允許通知/)).toBeTruthy();
    // 監聽訊號區只剩四鍵(提示音不在其中,否則會被讀成第五種訊號類型)
    expect(kinds.getAllByRole("switch").length).toBe(4);
    expect(kinds.queryByRole("switch", { name: /提示音/ })).toBeNull();
    expect(kinds.queryByText(/允許通知/)).toBeNull();
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
