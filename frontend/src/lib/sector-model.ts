/** 類股強弱的型別與取數(market-overview R4 SC-3;design §9.1)。
 *
 *  **兩支 fetcher 放 `lib/` 不放 hook**:成員層是 lazy 鑽取(query key 隨鑽取目標變),
 *  包成 hook 只會多一層轉手 —— 元件自己組 query key 才看得出「同時只有一個成員表」
 *  這件事(fan-out 是這塊最容易長出來的成本)。
 *
 *  型別逐欄對應後端 `sector_rotation.py`(改一邊要改兩邊)。缺值語意不可省略成 0:
 *  `vol_ratio` null = 分母被剔到 0(不是「量比 0」)、`change_rate` null = 快照沒給
 *  (不是「平盤」)。 */

import { parseError } from "@/lib/api-error";

/** 產業 / 子產業共用的統計欄。`members` = `change_rate` 非 null 的成員數。 */
export interface SectorRotationGroup {
  name: string;
  members: number;
  avg_change_rate: number;
  /** 分母(Σ 昨量)被剔到 0 → null。 */
  vol_ratio: number | null;
}

export interface SectorRotationIndustry extends SectorRotationGroup {
  /** 可為空陣列 = 單層產業(該產業沒有子產業,列點擊直接鑽成員)。 */
  subs: SectorRotationGroup[];
}

export interface SectorRotation {
  /** 後端已按 `avg_change_rate` desc 排好 —— 前端不重排。 */
  industries: SectorRotationIndustry[];
}

export interface SectorState {
  enabled: boolean;
  trade_date: string | null;
  as_of: string | null;
  stale: boolean;
  /** null = 產業鏈快取未就緒 / 類股停用。**與空 `industries` 不同義**:後者是
   *  「今天所有產業都沒成員」,前者是「還沒有資料」。 */
  rotation: SectorRotation | null;
}

export interface SectorMemberRow {
  stock_id: string;
  name: string;
  change_rate: number | null;
  vol_ratio: number | null;
  total_amount: number | null;
}

export interface SectorMembers {
  industry: string;
  /** null = 該產業所有子產業聯集(未指定子產業的鑽取)。 */
  sub_industry: string | null;
  members: SectorMemberRow[];
}

export async function fetchSectorState(): Promise<SectorState> {
  const res = await fetch("/api/market/sector");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SectorState;
}

/** 成員股鑽取。查無 industry / sub → 404 `SECTOR_NOT_FOUND`(拋出,由消費端顯示)。
 *
 *  `sub` 為 null **或空字串**一律不送:後端把空字串當未指定,兩種形狀在畫面上完全
 *  一樣,但會讓 query key / 網路面板 / server log 各多一種樣態(而「空字串是否等於
 *  未指定」哪天在後端改掉,前端這條路會靜默轉成 404)。 */
export async function fetchSectorMembers(
  industry: string,
  sub: string | null,
): Promise<SectorMembers> {
  const params = new URLSearchParams({ industry });
  if (sub) params.set("sub", sub);
  const res = await fetch(`/api/market/sector/members?${params.toString()}`);
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SectorMembers;
}
