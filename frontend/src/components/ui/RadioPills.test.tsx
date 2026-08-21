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

function pill(_item: RadioPillItem<Kind>, checked: boolean): string {
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

  // TC-4:「視覺零變」的前提是 radio 本體看不見 —— `sr-only` 掉了的話畫面上每顆 pill
  // 前面會多一個原生圓鈕(而所有語意測試照樣全綠)。反向也要鎖:label 不能是 sr-only,
  // 否則整組 pill 從畫面上消失。
  it("radio 本體 sr-only、label 不是(視覺零變的前提)", () => {
    render(<Harness />);
    const radio = screen.getByRole("radio", { name: "現股" });
    expect(radio.className).toBe("sr-only");
    expect(radio.closest("label")!.className).not.toContain("sr-only");
  });

  // TC-5:使用者點的是 **label**(radio 本體 sr-only,滑鼠根本點不到)—— 只測
  // `fireEvent.click(radio)` 等於從來沒走過真實路徑。
  it("點 label(不是 radio 本體)也換選;disabled 的 label 點了沒事", () => {
    const onChange = vi.fn();
    render(
      <Harness
        onChange={onChange}
        items={[ITEMS[0]!, ITEMS[1]!, { value: "short", label: "無券", disabled: true }]}
      />,
    );
    const margin = screen.getByRole("radio", { name: "融資" }) as HTMLInputElement;
    fireEvent.click(margin.closest("label")!);
    expect(onChange.mock.calls).toEqual([["margin"]]);
    expect(margin.checked).toBe(true);

    const off = screen.getByRole("radio", { name: "無券" }) as HTMLInputElement;
    fireEvent.click(off.closest("label")!);
    expect(onChange.mock.calls).toEqual([["margin"]]); // 沒有第二次
    expect(off.checked).toBe(false);
    expect(margin.checked).toBe(true);
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

  // 🔴 A11Y-3:`<label>` 沒有 UA cursor —— 改前每顆 pill 都是 I-beam 游標且文字可被
  // 反白選取(原 `<button>` 兩者皆無)。整排 pill 上拖一下就選出一片藍是可見的退化。
  it("一般態 label 補 cursor-default select-none;disabled 仍是 cursor-not-allowed", () => {
    render(
      <Harness items={[ITEMS[0]!, { value: "margin", label: "融資", disabled: true }]} />,
    );
    const normal = screen.getByRole("radio", { name: "現股" }).closest("label")!;
    expect(normal.className).toContain("cursor-default");
    expect(normal.className).toContain("select-none");
    expect(normal.className).not.toContain("cursor-not-allowed");
    const off = screen.getByRole("radio", { name: "融資" }).closest("label")!;
    expect(off.className).toContain("cursor-not-allowed");
    expect(off.className).not.toContain("cursor-default");
  });

  // 🔴 A11Y-5:id 改前是 `useId() 原字 + 使用者可控的 value` —— React 19 的 useId 是
  // «r0» 形態,而 value 可能帶空白(合約鍵 / 群組名)。兩者都讓 id 不是合法 token,
  // 拼進 `querySelector("#…")` / CSS 選擇器就是語法錯誤,而畫面完全正常。
  it("id 是合法 token:不含 useId 的 «»,也不含 value 的空白", () => {
    render(
      <RadioPills<string>
        ariaLabel="標的"
        value="TX 1"
        onChange={() => {}}
        items={[
          { value: "TX 1", label: "台指 1" },
          { value: "TX 2", label: "台指 2" },
        ]}
        pillClass={() => "border-line"}
      />,
    );
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    // 兩顆 id 必須互異(按 index 編號,不靠 value)
    expect(new Set(radios.map((r) => r.id)).size).toBe(2);
    for (const r of radios) {
      expect(r.id).toMatch(/^[A-Za-z0-9_-]+$/);
      // htmlFor 必須跟著同一份 token,否則 label ↔ input 的顯式關聯斷掉
      expect(r.closest("label")?.getAttribute("for")).toBe(r.id);
      expect(r.name).toMatch(/^[A-Za-z0-9_-]+$/);
    }
  });

  // 🔴 A11Y-6:PriceLadder 用「點交易別」當作使用者還在的訊號(touchIdle),但點**已選中**
  // 的那顆不發 change → 武裝閒置計時不重置,使用者明明在操作卻被解除武裝。
  // 所以互動訊號要走 label 的 click(每次點都有),不是 change。
  it("onInteract:點已選中的項也觸發(change 不發也算互動)", () => {
    const onChange = vi.fn();
    const onInteract = vi.fn();
    render(
      <RadioPills<Kind>
        ariaLabel="交易別"
        value="cash"
        onChange={onChange}
        onInteract={onInteract}
        items={ITEMS}
        pillClass={pill}
      />,
    );
    const label = screen.getByRole("radio", { name: "現股" }).closest("label")!;
    fireEvent.click(label);
    expect(onChange).not.toHaveBeenCalled();
    expect(onInteract).toHaveBeenCalled();
  });

  it("onInteract:點未選中的項也觸發;disabled 項不觸發", () => {
    const onInteract = vi.fn();
    render(
      <RadioPills<Kind>
        ariaLabel="交易別"
        value="cash"
        onChange={() => {}}
        onInteract={onInteract}
        items={[ITEMS[0]!, ITEMS[1]!, { value: "short", label: "無券", disabled: true }]}
        pillClass={pill}
      />,
    );
    fireEvent.click(screen.getByRole("radio", { name: "融資" }).closest("label")!);
    expect(onInteract).toHaveBeenCalled();
    onInteract.mockClear();
    // 停用項不是「使用者在操作」的訊號(原 `<button disabled>` 連 click 都不派)
    fireEvent.click(screen.getByRole("radio", { name: "無券" }).closest("label")!);
    expect(onInteract).not.toHaveBeenCalled();
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
