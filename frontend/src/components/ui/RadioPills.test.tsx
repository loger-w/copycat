/** @vitest-environment jsdom */
/** SC-1'(D1' / D1''):`RadioPills` = 單選 pill 群的共用元件。
 *
 *  鎖的是**語意層**:radio 數 = 選項數、恰一顆 checked、同組 `name` 一致且跨組互異
 *  (否則兩組互搶選取)、點已選項不發 change、Enter 不觸發外層 form 的 implicit submit。
 *  方向鍵 / roving tabindex 是原生 radio 行為,**jsdom 不實作** → 不在此鎖(靠 SC-5' 真環境)。
 *
 *  視覺零變靠 `pillClass` 逐字回傳呼叫端原 button 的 class,這裡只鎖「回傳值有掛上 label」
 *  與「額外補的 focus ring class 在」—— 兩者任一漏掉都是靜默的外觀退化。 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RadioPills, type RadioPillItem } from "@/components/ui/RadioPills";

afterEach(cleanup);

type Kind = "cash" | "margin" | "short";

const ITEMS: RadioPillItem<Kind>[] = [
  { value: "cash", label: "現股" },
  { value: "margin", label: "融資" },
  { value: "short", label: "無券" },
];

const RING =
  "has-focus-visible:ring-1 has-focus-visible:ring-inset has-focus-visible:ring-accent";

function pill(item: RadioPillItem<Kind>, checked: boolean): string {
  return checked ? "border-accent text-accent" : "border-line text-ink-dim";
}

/** 受控殼:呼叫端一律自己持有 value,元件不自帶 state。 */
function Harness({
  onChange,
  items = ITEMS,
  initial = "cash",
}: {
  onChange?: (v: Kind) => void;
  items?: RadioPillItem<Kind>[];
  initial?: Kind;
}) {
  const [v, setV] = useState<Kind>(initial);
  return (
    <RadioPills<Kind>
      ariaLabel="交易別"
      value={v}
      onChange={(next) => {
        setV(next);
        onChange?.(next);
      }}
      items={items}
      pillClass={pill}
      className="flex shrink-0 items-center gap-0.5"
    />
  );
}

describe("RadioPills", () => {
  it("radiogroup 內 radio 數 = 選項數,且恰一顆 checked", () => {
    render(<Harness initial="margin" />);
    const group = screen.getByRole("radiogroup", { name: "交易別" });
    const radios = within(group).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.length).toBe(3);
    expect(radios.filter((r) => r.checked).length).toBe(1);
    expect((within(group).getByRole("radio", { name: "融資" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((within(group).getByRole("radio", { name: "現股" }) as HTMLInputElement).checked).toBe(
      false,
    );
  });

  it("容器逐字沿用呼叫端 class,label 掛 pillClass + focus ring", () => {
    render(<Harness initial="cash" />);
    const group = screen.getByRole("radiogroup", { name: "交易別" });
    expect(group.className).toBe("flex shrink-0 items-center gap-0.5");
    const checked = screen.getByRole("radio", { name: "現股" });
    const label = checked.closest("label");
    expect(label).toBeTruthy();
    expect(label?.className).toContain("border-accent");
    expect(label?.className).toContain("text-accent");
    for (const cls of RING.split(" ")) {
      expect(label?.className).toContain(cls);
    }
    const other = screen.getByRole("radio", { name: "融資" }).closest("label");
    expect(other?.className).toContain("border-line");
    expect(other?.className).not.toContain("border-accent");
  });

  it("同組 name 全同;兩組同時掛載時 name 互異(不互搶選取)", () => {
    render(
      <>
        <Harness />
        <Harness />
      </>,
    );
    const [g1, g2] = screen.getAllByRole("radiogroup", { name: "交易別" });
    const names1 = (within(g1!).getAllByRole("radio") as HTMLInputElement[]).map((r) => r.name);
    const names2 = (within(g2!).getAllByRole("radio") as HTMLInputElement[]).map((r) => r.name);
    expect(new Set(names1).size).toBe(1);
    expect(new Set(names2).size).toBe(1);
    expect(names1[0]).toBeTruthy();
    expect(names1[0]).not.toBe(names2[0]);
  });

  it("點未選中的 radio 觸發一次 onChange 並換選", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const target = screen.getByRole("radio", { name: "無券" }) as HTMLInputElement;
    fireEvent.click(target);
    expect(onChange.mock.calls).toEqual([["short"]]);
    expect(target.checked).toBe(true);
    expect((screen.getByRole("radio", { name: "現股" }) as HTMLInputElement).checked).toBe(false);
  });

  it("點已 checked 的 radio 不觸發 onChange", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(screen.getByRole("radio", { name: "現股" }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("disabled 項:input disabled、label aria-disabled + cursor-not-allowed、點擊不觸發", () => {
    const onChange = vi.fn();
    render(
      <Harness
        onChange={onChange}
        items={[ITEMS[0]!, { value: "margin", label: "融資", disabled: true }]}
      />,
    );
    const radio = screen.getByRole("radio", { name: "融資" }) as HTMLInputElement;
    expect(radio.disabled).toBe(true);
    const label = radio.closest("label");
    expect(label?.getAttribute("aria-disabled")).toBe("true");
    expect(label?.className).toContain("cursor-not-allowed");
    fireEvent.click(radio);
    expect(onChange).not.toHaveBeenCalled();
    expect(radio.checked).toBe(false);
    // 未 disabled 的項不掛 aria-disabled(否則整組被 AT 讀成不可用)
    expect(
      screen.getByRole("radio", { name: "現股" }).closest("label")?.getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("焦點在 radio 按 Enter → defaultPrevented(不送出外層 form)", () => {
    render(<Harness />);
    const radio = screen.getByRole("radio", { name: "現股" });
    expect(fireEvent.keyDown(radio, { key: "Enter" })).toBe(false);
    // 其餘按鍵不攔(方向鍵要留給瀏覽器原生 roving)
    expect(fireEvent.keyDown(radio, { key: "ArrowRight" })).toBe(true);
  });

  it("title 掛在 label(hover 提示與 disabled 理由同一個元素)", () => {
    render(
      <Harness
        items={[ITEMS[0]!, { value: "margin", label: "融資", title: "此合約尚無成交估價" }]}
      />,
    );
    const label = screen.getByRole("radio", { name: "融資" }).closest("label");
    expect(label?.getAttribute("title")).toBe("此合約尚無成交估價");
    expect(screen.getByRole("radio", { name: "現股" }).closest("label")?.getAttribute("title")).toBe(
      null,
    );
  });

  it("leading / trailing slot 渲染在容器內、radio 前後(不新增層)", () => {
    render(
      <RadioPills<Kind>
        ariaLabel="交易別"
        value="cash"
        onChange={() => {}}
        items={ITEMS}
        pillClass={pill}
        className="flex items-center gap-2"
        leading={<span>群組</span>}
        trailing={<span>重疊</span>}
      />,
    );
    const group = screen.getByRole("radiogroup", { name: "交易別" });
    expect(within(group).getByText("群組")).toBeTruthy();
    expect(within(group).getByText("重疊")).toBeTruthy();
    const kids = [...group.children];
    expect(kids[0]?.textContent).toBe("群組");
    expect(kids.at(-1)?.textContent).toBe("重疊");
    expect(within(group).getAllByRole("radio").length).toBe(3);
  });
});
