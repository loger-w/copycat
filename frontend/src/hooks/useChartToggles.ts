import { useState } from "react";

import { CHART_TOGGLES_KEY } from "@/lib/constants";

export interface ChartToggles {
  vwap: boolean;
  cdp: boolean;
  ma: boolean;
  /** 布林通道(K 線專用) */
  bb: boolean;
  /** 價位別成交量長條(江波圖專用) */
  vp: boolean;
}

/** 存檔 schema 版本。**storage-only,不屬 `ChartToggles`** —— 洩進 toggles 物件會讓
 *  「整包比對」的測試與 memo 比較多一個非布林欄位。 */
const TOGGLES_VERSION = 2;

/** `cdp` 預設開(SC-3,user 拍板);`bb` 預設開(round4 項 6,user 拍板);
 *  `vp` 預設開(價位別成交量 SC-3,**auto-default**,brainstorm 決策記錄 —— 與上面
 *  兩項不同,這個預設沒有經過 user 逐項拍板,改動門檻相應較低)。
 *
 *  **`vp` 不需要 bump `TOGGLES_VERSION`**:版本升級要處理的是「**既有**鍵的預設改了」
 *  —— 舊存檔裡那個值是當時的預設而不是使用者的選擇,不強制升級就永遠蓋掉新預設。
 *  `vp` 是全新的鍵,舊存檔根本沒有它,下面的 `{...DEFAULTS, ...flags}` 自然就補上。
 *  無謂 bump 的代價是所有人的 `bb` 會被再打開一次(升級分支不分辨是誰觸發的)。
 *
 *  `load()` 的 `{...DEFAULTS, ...saved}` 讓存檔覆蓋預設 —— 對「使用者選過」的項目是
 *  對的,但對**新改的預設**是錯的:舊存檔裡的 `bb: false` 是「當時的預設」而不是
 *  「使用者選了關」,照樣覆蓋的話 user 的畫面永遠不會變成新預設。
 *  故只對 `bb` 做一次性升級(見 `load`),其餘欄位維持「存檔優先、不強制升級」。 */
const DEFAULTS: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: true };

interface Stored extends Partial<ChartToggles> {
  v?: number;
}

/** 寫入失敗**不可以往外拋**:一次性升級是在 `load()` 裡寫的,而 `load()` 是
 *  `useState` 的 initializer —— setItem 在 Safari 私密視窗 / storage 被政策鎖時會拋
 *  `QuotaExceededError`,拋出去就是圖表元件首次 render 直接掛掉(白畫面)。
 *  記憶體內的 toggles 照常生效,只是這次沒落檔。 */
function persist(toggles: ChartToggles): void {
  try {
    window.localStorage.setItem(
      CHART_TOGGLES_KEY,
      JSON.stringify({ ...toggles, v: TOGGLES_VERSION }),
    );
  } catch {
    // 存不進去就算了 —— 偏好設定不落檔遠好於整個看盤畫面崩掉
  }
}

function load(): ChartToggles {
  let saved: Stored;
  try {
    const raw = window.localStorage.getItem(CHART_TOGGLES_KEY);
    if (!raw) return DEFAULTS;
    const parsed: unknown = JSON.parse(raw);
    // `JSON.parse("null")` 成功且回 null;陣列 / 字串同樣是合法 JSON。
    // 解構那行若在 try 之外,對 null 解構是 TypeError,一樣炸掉 initializer。
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return DEFAULTS;
    saved = parsed as Stored;
  } catch {
    return DEFAULTS;
  }
  const { v, ...flags } = saved;
  const merged: ChartToggles = { ...DEFAULTS, ...flags };
  if ((v ?? 1) < TOGGLES_VERSION) {
    // 一次性升級。**必須立刻落檔**:只回傳不寫回的話,使用者升級後把 BB 關掉,
    // 下次 load 又看到 v<2 而再打開一次 —— 變成「關不掉」(白名單 W-11)。
    const upgraded: ChartToggles = { ...merged, bb: true };
    persist(upgraded);
    return upgraded;
  }
  return merged;
}

export function useChartToggles() {
  const [toggles, setToggles] = useState<ChartToggles>(load);

  // merge 的基底必須是**重讀的 localStorage**,不是自己那份 prev:本 hook 是純 useState,
  // 每個呼叫端各持一份。StockChart(管 bb)與 StockIntradayChart(管 vwap/cdp/ma)同時
  // 存活,用 stale prev 整包寫回會讓後寫的一方回滾對方剛做的變更 ——
  // 實際症狀是「江波圖把 CDP 關掉、去 K 線按了 BB、切回來 CDP 自己亮回來」。
  function set(key: keyof ChartToggles, value: boolean): void {
    const next = { ...load(), [key]: value };
    persist(next);
    setToggles(next);
  }

  return { toggles, set };
}
