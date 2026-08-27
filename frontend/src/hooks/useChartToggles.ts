import { useSyncExternalStore } from "react";

import { CHART_TOGGLES_KEY } from "@/lib/constants";
import { readLocal, readLocalJson, writeLocal } from "@/lib/storage";

export interface ChartToggles {
  vwap: boolean;
  cdp: boolean;
  ma: boolean;
  /** 布林通道(K 線專用) */
  bb: boolean;
  /** 價位別成交量長條(江波圖專用) */
  vp: boolean;
  /** 分時圖上「我當日有成交的委託」▲/▼ 標記(個股 / 個股期單檔頁 + 群組圖牆) */
  fills: boolean;
  /** 個股分時圖疊加權指數即時走勢(相對昨收 % 映到個股價格軸;F1) */
  idxTwse: boolean;
  /** 同上,櫃買指數 */
  idxOtc: boolean;
  /** 同上,台指期(相對結算價 %;feat/txf-intraday-overlay)。App 層另拿它閘控 TXF bars 的輪詢 */
  idxTxf: boolean;
  /** 群組圖牆 hover 一張卡 → 全部卡片同步十字線(F3;只在圖牆 toggle 列出現) */
  syncHover: boolean;
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
 *  故只對 `bb` 做一次性升級(見 `load`),其餘欄位維持「存檔優先、不強制升級」。
 *
 *  `fills` 預設開(成交點 SC-2,D8 user 拍板)。**同樣不 bump `TOGGLES_VERSION`** ——
 *  理由與 `vp` 那條逐字相同:它是全新的鍵,舊存檔沒有它,`{...DEFAULTS, ...flags}` 自然
 *  補上;bump 反而會讓所有人的 `bb` 被再打開一次(升級分支不分辨是誰觸發的)。 */
const DEFAULTS: ChartToggles = {
  vwap: true,
  cdp: true,
  ma: false,
  bb: true,
  vp: true,
  fills: true,
  // 指數疊線預設**關**(F1,auto-default):疊線是加在價線上的視覺噪音,user 要的是
  // 「可以開關」不是常駐;新鍵同樣不 bump TOGGLES_VERSION(理由與 `vp` 逐字相同)。
  idxTwse: false,
  idxOtc: false,
  idxTxf: false, // 台指期同款(feat/txf-intraday-overlay;新鍵免 bump)
  // 同步十字線預設**開**(F3,auto-default):user 要的功能預設就看得到,可關。同樣不 bump 版本。
  syncHover: true,
};

interface Stored extends Partial<ChartToggles> {
  v?: number;
}

/** 寫入失敗**不可以往外拋**(由 `lib/storage.ts::writeLocal` 承擔):一次性升級是在
 *  `load()` 裡寫的,而 `load()` 是 `useState` 的 initializer —— setItem 在 Safari 私密
 *  視窗 / storage 被政策鎖時會拋 `QuotaExceededError`,拋出去就是圖表元件首次 render
 *  直接掛掉(白畫面)。記憶體內的 toggles 照常生效,只是這次沒落檔。 */
function persist(toggles: ChartToggles): void {
  writeLocal(CHART_TOGGLES_KEY, JSON.stringify({ ...toggles, v: TOGGLES_VERSION }));
}

function load(): ChartToggles {
  // `readLocalJson` 已把「未設 / 空字串 / 存取即拋 / 壞 JSON」收成同一個 null;
  // 這裡只剩形狀檢查 —— `JSON.parse("null")` 成功且回 null,陣列 / 字串同樣是合法
  // JSON,少了這一行對 null 解構就是 TypeError,一樣炸掉 initializer。
  const parsed = readLocalJson(CHART_TOGGLES_KEY);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return DEFAULTS;
  const { v, ...flags } = parsed as Stored;
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

// ---- 模組層 store(feat/txf-intraday-overlay Q8,user 拍板)----
//
// 改動前每個呼叫端各持一份 `useState`,別處按了鈕要到自己下次 `set` 才重讀存檔 —— 三個畫面
// (K 線 / 江波圖 / 圖牆)之間的 toggle 狀態只在「誰寫入」那一刻對齊。App 層因此拿不到
// 「台指期鈕開著沒」,無法閘控 TXF bars 的輪詢(鈕關著也每分鐘打 TC4)。
//
// **真相源仍是 localStorage,不是這份快取**:`getSnapshot` 以存檔的原始字串為鍵,字串變了
// (外部清空 / 升級寫回)就重載;字串沒變就回同一個物件 —— `useSyncExternalStore` 要求快照
// identity 穩定,否則每次 render 都被當成新值而無限重繪。`getSnapshot` 是**冪等**的(同一字串
// 第二次呼叫直接回快取),唯一的寫入是 v<2 一次性升級 —— 改動前它就在 `useState(load)` 的
// initializer 裡、同樣落在 render 期,不是本輪新增的副作用。不掛 `storage` 事件:跨分頁同步
// 不在需求內,兩個分頁各自 set 時 `setToggle` 重讀存檔再 merge 已足夠不互相覆蓋。
// 寫入失敗(私密視窗 / 政策鎖)時 `persist` 不拋、存檔不變 → 快取直接換成 next,記憶體內照常生效。
let cachedRaw: string | null | undefined; // undefined = 尚未載入過
let cached: ChartToggles = DEFAULTS;
const listeners = new Set<() => void>();

function getSnapshot(): ChartToggles {
  const raw = readLocal(CHART_TOGGLES_KEY);
  if (cachedRaw === undefined || raw !== cachedRaw) {
    cached = load();
    // `load()` 的一次性升級會寫回 → 以寫回後的字串為鍵,下一次才不會再重載一遍
    cachedRaw = readLocal(CHART_TOGGLES_KEY);
  }
  return cached;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** merge 的基底是**重讀的 localStorage**而不是快取:兩個分頁各自按鈕時,快取可能落後存檔。 */
function setToggle(key: keyof ChartToggles, value: boolean): void {
  const next: ChartToggles = { ...load(), [key]: value };
  persist(next);
  cached = next;
  cachedRaw = readLocal(CHART_TOGGLES_KEY);
  for (const listener of listeners) listener();
}

export function useChartToggles() {
  const toggles = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  // `set` 是模組層函式 → 身分天然穩定(memo 節點收 onToggle 不被打穿),不需 useCallback
  return { toggles, set: setToggle };
}
