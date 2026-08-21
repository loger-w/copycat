/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RiverPanel } from "@/components/corr/RiverPanel";
// 共檔 fixture(`river-test-fixtures.ts`):與 `RiverPanel.memo.test.tsx` 同一組數字。
import { mockRect, riverState as state, xAt } from "@/components/corr/river-test-fixtures";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("RiverPanel", () => {
  it("預設並排:兩顆鈕都在,並排為 accent,各腿名皆出現", () => {
    render(<RiverPanel state={state()} />);

    const side = screen.getByRole("button", { name: "並排" });
    const overlay = screen.getByRole("button", { name: "重疊" });
    expect(side.className).toContain("text-accent");
    expect(overlay.className).not.toContain("text-accent");
    expect(screen.getAllByText("台指").length).toBeGreaterThan(0);
    expect(screen.getAllByText("富台").length).toBeGreaterThan(0);
    expect(screen.getAllByText("道瓊").length).toBeGreaterThan(0);
  });

  it("並排卡片顯示現價與相對窗首 %,漲用 bull 色", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("40400.00")).toBeTruthy();
    const pct = screen.getByText("+1.00%");
    expect(pct.className).toContain("text-bull");
  });

  it("跌的腿用 bear 色", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("-1.00%").className).toContain("text-bear");
  });

  it("無資料的腿顯示「無資料」而非 0", () => {
    render(<RiverPanel state={state()} />);

    expect(screen.getByText("無資料")).toBeTruthy();
  });

  it("點重疊 → 模式切換並寫入 localStorage,勾選列出現", () => {
    render(<RiverPanel state={state()} />);

    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    expect(window.localStorage.getItem("copycat-river-mode")).toBe("overlay");
    expect(screen.getByRole("checkbox", { name: "台指" })).toBeTruthy();
  });

  it("取消勾選 → 記進 localStorage 且該腿線消失", () => {
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    fireEvent.click(screen.getByRole("checkbox", { name: "富台" }));

    expect(JSON.parse(window.localStorage.getItem("copycat-river-legs") ?? "[]")).toEqual(["TWN"]);
    expect(screen.getByRole("checkbox", { name: "富台" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    // 圖上腿名標籤消失(SVG 內的 text),checkbox 上的字不算
    const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
    expect(svg.textContent).not.toContain("富台");
    expect(svg.textContent).toContain("台指");
  });

  it("重疊圖 % 軸標籤(characterization:域上下緣)", () => {
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    const svg = screen.getByRole("img", { name: "各腿重疊走勢" });
    expect(svg.textContent).toContain("+1.05%");
    expect(svg.textContent).toContain("-1.05%");
  });

  it("重疊圖:首筆晚於最早腿的腿標示「自 HH:MM 起算 0%」(基準時點分歧;小日經 16:00 開盤)", () => {
    const s = state();
    // 納指 09:55 才有第一筆(offset 70 → 525+70),台指 / 富台 08:55(offset 10)
    s.legs.NQ = {
      label: "納指",
      minutes: { "70": 30_000_000, "80": 30_300_000 },
      last: 30_300_000,
      last_minute: 80,
    };
    render(<RiverPanel state={s} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));

    expect(screen.getByText("納指 自 09:55 起算 0%")).toBeTruthy();
    // 同時起算的腿不標
    expect(screen.queryByText(/台指 自 .* 起算/)).toBeNull();
    expect(screen.queryByText(/富台 自 .* 起算/)).toBeNull();
  });

  it("重掛後模式與勾選狀態復原", () => {
    window.localStorage.setItem("copycat-river-mode", "overlay");
    window.localStorage.setItem("copycat-river-legs", JSON.stringify(["TWN"]));

    render(<RiverPanel state={state()} />);

    expect(screen.getByRole("button", { name: "重疊" }).className).toContain("text-accent");
    expect(screen.getByRole("checkbox", { name: "富台" }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("localStorage 壞值不崩(降回預設)", () => {
    window.localStorage.setItem("copycat-river-mode", "garbage");
    window.localStorage.setItem("copycat-river-legs", "{not json");

    render(<RiverPanel state={state()} />);

    expect(screen.getByRole("button", { name: "並排" }).className).toContain("text-accent");
  });

  it("state 為 null → 等待文案", () => {
    render(<RiverPanel state={null} />);

    expect(screen.getByText("等待各腿資料…")).toBeTruthy();
  });

  it("盤別顯示在標題", () => {
    render(<RiverPanel state={state({ session: "night" })} />);

    expect(screen.getByText(/夜盤/)).toBeTruthy();
  });

  it("全腿無點 → 顯示等待該盤別資料", () => {
    const empty = state();
    for (const leg of Object.values(empty.legs)) {
      leg.minutes = {};
      leg.last = null;
      leg.last_minute = null;
    }

    render(<RiverPanel state={empty} />);

    expect(screen.getByText("等待日盤資料…")).toBeTruthy();
  });
});

/** S3 memo 邊界的前置 characterization(refactor-plan R1/R17)。
 *
 *  拍的是**改動前的現狀**:重疊圖游標移動 → 讀值列即時換成該分鐘的各腿 %。
 *  之所以要先拍:S3 要把 `buildOverlayGeometry` 與其衍生量包進 `useMemo([entries, win])`,
 *  只要順手把 `readout`(唯一依賴 `cursor` 的量)一起包進去,讀值列就會被凍在
 *  `cursor === null` 的那一刻 —— 線照畫、時間照走,只有讀值永遠是「—」,
 *  而既有 14 條測試沒有任何一條碰過 mouseMove(零訊號)。
 *
 *  jsdom 坑:`handleMouseMove` 先取 `getBoundingClientRect()`,jsdom 恆回 0 →
 *  `rect.width === 0` 早退 → cursor 永遠 null、斷言恆假綠。必須 spy 出真實寬高
 *  (先例 `MarketChart.test.tsx` hover 節);座標換算假設 svg 等比渲染。
 */
describe("RiverOverlay hover 讀值列(S3 characterization)", () => {
  function overlay(): SVGElement {
    render(<RiverPanel state={state()} />);
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));
    return screen.getByRole("img", { name: "各腿重疊走勢" }) as unknown as SVGElement;
  }

  it("游標移入 → 讀值列出現各腿 % 與該分鐘時刻", () => {
    mockRect();
    const svg = overlay();
    // 自檢:移入前是提示文案(移入後才會被讀值列取代)
    expect(screen.getByText("游標移入圖內看各腿讀值")).toBeTruthy();

    fireEvent.mouseMove(svg, { clientX: xAt(20), clientY: 100 });

    expect(screen.getByText("09:05")).toBeTruthy(); // window.start_min 525 + 20
    expect(screen.getByText("台指 +1.00%")).toBeTruthy();
    expect(screen.getByText("富台 -1.00%")).toBeTruthy();
    expect(screen.queryByText("游標移入圖內看各腿讀值")).toBeNull();
  });

  it("游標移到另一分鐘 → 讀值跟著換(讀值不得被幾何 useMemo 凍住)", () => {
    mockRect();
    const svg = overlay();

    fireEvent.mouseMove(svg, { clientX: xAt(20), clientY: 100 });
    expect(screen.getByText("台指 +1.00%")).toBeTruthy();

    fireEvent.mouseMove(svg, { clientX: xAt(10), clientY: 100 });

    expect(screen.getByText("08:55")).toBeTruthy();
    expect(screen.getByText("台指 0.00%")).toBeTruthy();
    expect(screen.getByText("富台 0.00%")).toBeTruthy();
    expect(screen.queryByText("台指 +1.00%")).toBeNull();
  });

  it("全窗無值的腿也進讀值列印「—」", () => {
    mockRect();
    const svg = overlay();

    fireEvent.mouseMove(svg, { clientX: xAt(15), clientY: 100 });

    expect(screen.getByText("台指 —")).toBeTruthy();
    expect(screen.getByText("富台 —")).toBeTruthy();
    // 道瓊全窗無值 → `buildOverlayGeometry` 照舊不收它(不畫線,免得看成 0% 直線),但讀值列
    // **要**列出來:讀值列由 `entries` 產生,使用者才看得到「這一腿沒資料」而非這一腿憑空消失。
    expect(screen.getByText("道瓊 —")).toBeTruthy();
    // 圖上仍只有兩條線,右緣腿名標籤也沒有道瓊(勾選鈕上的字不在 svg 內,不算)
    expect(svg.querySelectorAll("polyline").length).toBe(2);
    const svgTexts = Array.from(svg.querySelectorAll("text")).map((t) => t.textContent);
    expect(svgTexts).not.toContain("道瓊");
    // 讀值列順序 = entries 順序(legs 鍵序,與勾選列 / 顏色序位一致),不是幾何回傳的順序
    const row = screen.getByText("台指 —").parentElement!;
    const readout = Array.from(row.querySelectorAll("span"))
      .map((s) => s.textContent ?? "")
      .filter((t) => /^(台指|富台|道瓊) /.test(t));
    expect(readout).toEqual(["台指 —", "富台 —", "道瓊 —"]);
  });

  it("游標移出 → 讀值列收回提示文案", () => {
    mockRect();
    const svg = overlay();
    fireEvent.mouseMove(svg, { clientX: xAt(20), clientY: 100 });

    fireEvent.mouseLeave(svg);

    expect(screen.getByText("游標移入圖內看各腿讀值")).toBeTruthy();
    expect(screen.queryByText("台指 +1.00%")).toBeNull();
  });
});
