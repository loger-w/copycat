/** 交易別值域與標籤(自 `components/stock/PriceLadder.tsx` 搬出,**行為零變更**)。
 *
 *  閃電梯之外,自選列 / 單檔 header / 群組卡也要把 `Position.kind` 印成人看得懂的
 *  標籤 —— 值域與標籤表只能有一份。`PriceLadder` 仍 re-export `TRADE_KINDS` 與
 *  `TradeKind`,既有 import 路徑(`RightRail` 等)不變。
 */

import type { PositionKind } from "@/types";

export const TRADE_KINDS = [
  ["cash", "現股"],
  ["margin", "融資"],
  ["short", "融券"],
  ["daytrade_sell", "無券"],
] as const;
export type TradeKind = (typeof TRADE_KINDS)[number][0];

/** kind → 顯示標籤,查表未命中就顯示原字串:群益 `Position.kind` 的值域比本檔的
 *  交易別寬(D13),不認得的部位寧可標籤怪也不要靜默消失。 */
export function kindLabel(kind: string): string {
  return TRADE_KINDS.find(([v]) => v === kind)?.[1] ?? kind;
}

/** 各交易別的行為特性 —— 散落 `=== "daytrade_sell"` 逐點比較的唯一收斂點
 *  (refactor/daytrade-sell-kind-table;review 2026-08-30 F-09 Shotgun Surgery)。
 *  加新種類時:值域(`TRADE_KINDS`)+ 這張表 + `types.ts::PositionKind`(wire 型別,
 *  跨語言 parity 測試逐字讀,不可搬)三處一起動 —— 漏表 / 漏型別由下面的
 *  `Record` 交集型別在 tsc 紅出來,不是 runtime 才發現。 */
export interface KindTraits {
  /** 買側鎖:無券只有賣向,回補走平倉的現股買(後端同一把尺 = `safety.py`
   *  「daytrade_sell 不可買進」gate;閃電梯 UI disabled + 程式雙保險都吃這格)。 */
  buyLocked: boolean;
  /** 今日成交(`today_qty`)段賣出稅減半 0.15%(現股當沖法規;`positionEcon`)。 */
  halfTaxToday: boolean;
  /** 融券借券費 0.08%(`positionEcon`)。 */
  borrowFee: boolean;
  /** 部位列顯示順序(`secPositionsOf`);未知字串殿後(`UNKNOWN_KIND_TRAITS`)。 */
  order: number;
}

/** `Record` 交集:表**漏列 / 多列**鍵時 tsc 紅(pr-166 F-02 實測三方向)。它蓋不住的
 *  兩向 —— 補了表但 `types.ts` 沒跟(A2)、`TRADE_KINDS` 單邊減值(B)—— 由下面的
 *  `_KindDomainsMatch` 雙向斷言接手;「前端單一型別」的機驗合起來才完整,零 runtime 產物。 */
export const KIND_TRAITS: Record<TradeKind, KindTraits> & Record<PositionKind, KindTraits> = {
  cash: { buyLocked: false, halfTaxToday: true, borrowFee: false, order: 0 },
  margin: { buyLocked: false, halfTaxToday: false, borrowFee: false, order: 1 },
  short: { buyLocked: false, halfTaxToday: false, borrowFee: true, order: 2 },
  daytrade_sell: { buyLocked: true, halfTaxToday: true, borrowFee: false, order: 3 },
};

type AssertEqual<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
type Expect<T extends true> = T;
/** 值域雙向相等機驗:`TradeKind`(標籤表推導)⇄ `PositionKind`(wire 型別)。
 *  單邊加值 / 減值不跟,這行 TS2344(pr-166 F-02;實測同域編過、兩向皆紅。
 *  `_SameDomain<A extends B, B extends A = A>` 型式是 circular constraint 編不過,不要換回)。 */
export type _KindDomainsMatch = Expect<AssertEqual<TradeKind, PositionKind>>;

/** 值域外字串(舊 dist / 舊後端 / 未來新 kind)的預設政策:全稅、無借券費、不鎖買側、
 *  殿後 —— 與收斂前各散點的 else 分支逐一相同(ladder-position characterization 釘住)。 */
export const UNKNOWN_KIND_TRAITS: KindTraits = {
  buyLocked: false,
  halfTaxToday: false,
  borrowFee: false,
  order: 3,
};

/** kind(裸 wire 字串)→ 特性;查無 → `UNKNOWN_KIND_TRAITS`。
 *  未知值政策收斂在這一點,消費端不各自寫 else。`Object.hasOwn` 不直接索引:
 *  kind 是後端字串直傳,原型鏈鍵("toString")不可當表命中(`close-order.ts::kindOf`
 *  同一書面決定;pr-166 F-03)。 */
export function kindTraits(kind: string): KindTraits {
  return Object.hasOwn(KIND_TRAITS, kind)
    ? KIND_TRAITS[kind as TradeKind]
    : UNKNOWN_KIND_TRAITS;
}
