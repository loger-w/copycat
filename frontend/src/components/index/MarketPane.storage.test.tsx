/** @vitest-environment jsdom */
/** MarketPane 的 localStorage 失效面(N022)。
 *
 *  **與 MarketPane.test.tsx / .size.test.tsx 拆開**:本檔把 `Storage.prototype` 的
 *  `getItem` / `setItem` 換成「存取即拋」,那是整檔唯一需要的失效態 —— 混進主檔會讓
 *  所有既有測試的存檔還原語意靜默改變(先例:`MarketPane.size.test.tsx` 為了 stub
 *  `ResizeObserver` 而拆檔)。
 *
 *  為什麼挑 MarketPane 當元件 seam:它是全站 localStorage 呼叫點最密的一個檔
 *  (2026-08-06 起記著「七個呼叫點裸奔」,2026-08-24 重 grep 已是 10 處),
 *  四個 `useState` 初始器全在 render 路徑上 —— 私密視窗下這一頁是第一個白掉的。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketPane, type PaneStores } from "@/components/index/MarketPane";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";

const TWSE: IndexSeries = {
  p: 42_039_920,
  ref: 43_634_190,
  high: 43_221_930,
  low: 41_815_780,
  stale: false,
  minutes: { "0901": 43_000_000, "0930": 42_039_920 },
};
const OTC: IndexSeries = {
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  stale: false,
  minutes: { "1017": 359_800 },
};
const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: false, fills: true, idxTwse: false, idxOtc: false, idxTxf: false, syncHover: true };
const STORES: PaneStores = {
  key: MARKET_KEY_STORE,
  mode: MARKET_MODE_STORE,
  fut: MARKET_FUT_STORE,
  overlay: INDEX_OVERLAY_STORE,
};

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketPane
        paneId="left"
        twse={TWSE}
        otc={OTC}
        futures={null}
        stores={STORES}
        defaultKey="TWSE"
        toggles={TOGGLES}
        onToggle={() => {}}
      />
    </QueryClientProvider>,
  );
}

function pill(name: string): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

/** jsdom 把 `localStorage` 定義成 window 的自有 configurable accessor → 還原要把原本
 *  那份 descriptor 裝回去(細節見 `lib/storage.test.ts`)。 */
let ownStorageDesc: PropertyDescriptor | undefined;

beforeEach(() => {
  ownStorageDesc = Object.getOwnPropertyDescriptor(window, "localStorage");
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ key: "TWSE", tf: "D", bars: [] }))),
  );
  // storage 失效是**診斷輸出**不是測試訊號:讓 lib/storage 的 warn 不洗測試輸出。
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  if (ownStorageDesc) Object.defineProperty(window, "localStorage", ownStorageDesc);
  vi.unstubAllGlobals();
  // spy 還原放 afterEach:斷言先炸時主體末尾的 restore 不會執行,
  // Storage.prototype 的 spy 會漏到後續測試(review A-2 慣例)。
  vi.restoreAllMocks();
});

// 🔴 N022(a):讀取端住在四個 `useState` 初始器裡,拋出去 = 台股綜合頁整片白
describe("MarketPane:localStorage 存取即拋(私密視窗 / 政策鎖)", () => {
  it("仍掛得起來,標的 / 週期退回預設值", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    });

    expect(() => renderPane()).not.toThrow();
    expect(screen.getByTestId("market-pane-left")).toBeTruthy();
    // defaultKey 與 coerceMode 的 "intraday" 是唯二正確的退路
    expect(pill("加權").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
  });

  // 🔴 SP1:真 Safari 私密視窗拋的是 **`window.localStorage` 這個 getter 本身**,連
  // `Storage` 實例都拿不到 —— 上一條的 `Storage.prototype` spy 量不到這一層。把
  // `window.localStorage` 提到 try 外(或存成 module 級 const)時,上一條仍綠而本條會紅。
  it("連 window.localStorage getter 都拋 → 仍掛得起來,退回預設值", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("The operation is insecure.", "SecurityError");
      },
    });

    expect(() => renderPane()).not.toThrow();
    expect(screen.getByTestId("market-pane-left")).toBeTruthy();
    expect(pill("加權").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
  });
});

// 🔴 N022(b):寫入端在事件處理器上,`setItem` 拋出去就是**整個 handler 從那一行中斷**。
//
// **斷言不能寫 `expect(fireEvent.click(...)).not.toThrow()`** —— jsdom 的 `dispatchEvent`
// 會吞掉 listener 的例外(轉成 uncaught error 報告),那條斷言對現況(裸奔 setItem)
// 一樣綠,是假的鎖。要量的是「handler 後半段有沒有跑完」,而 `selectKey` / `selectFut`
// 都把 `setItem` 排在 `coerceMode` 之前 —— 拋掉的話畫面會停在一個 **disabled 的週期鈕**
// 上(P1-5 那個「空白畫面」的組合),這是使用者看得到的症狀。
describe("MarketPane:localStorage 寫入拋 QuotaExceededError", () => {
  function breakWrites(): void {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
  }

  it("加權+日K → 切櫃買:週期仍被 coerce 到分時(櫃買沒有日/週/月)", () => {
    window.localStorage.setItem(MARKET_KEY_STORE, "TWSE");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    renderPane();
    expect(pill("日K").checked).toBe(true);

    breakWrites();
    fireEvent.click(pill("櫃買"));

    expect(pill("櫃買").checked).toBe(true);
    expect(pill("分時").checked).toBe(true);
  });

  it("加權+分時 → 切台指期:週期仍被 coerce 到 1分(期指沒有分時)", () => {
    renderPane();
    expect(pill("分時").checked).toBe(true);

    breakWrites();
    fireEvent.click(pill("台指期"));

    expect(pill("台指期").checked).toBe(true);
    expect(pill("1分").checked).toBe(true);
  });
});
