# change-spec — mod/ladder-pills-avgpct(R6)

來源 batch2 spec §2 R6(user 撰寫 → 預核准);現況 `current-state.md`;規模 S+S(同輪分 commit);分流:已成形方案(指名檔案 / 樣板 / 口徑)→ 逐題 `[auto-default]`,無方向性抉擇。
UI 輪:已載入 `bencium-controlled-ux-designer`(其「先問再做」由 /auto 覆寫為 auto-default);`frontend-design` 未載入 —
`[auto-default: 不載入 frontend-design | reason: user 指示「沿既有 pill 樣板不另造」,該 skill 目的是造新視覺語言,與指示相反]`。

## SC
| # | 成功條件(畫面可指認) | 驗證 |
|---|---|---|
| SC-1 | 現股閃電梯武裝列:交易別由 `<select>` 改為四顆並列 pill「現股 / 融資 / 融券 / 無券」(容器 `role="group" aria-label="交易別"`),單選;選中 = `border-accent text-accent` + `aria-pressed=true`,未選 = `border-line text-ink-dim`;位置仍在鎖定鈕右側同列(288px 不換行) | vitest PriceLadder:四顆 button 存在、點「融券」→ aria-pressed 轉移;截圖 `evidence/SC-1_pills_288.png` |
| SC-2 | 選「無券」→ 買側鎖(既有 buyLocked)、賣側 payload `trade_kind:"daytrade_sell"`;點 pill 觸發 `touchIdle` | vitest PriceLadder:401 改寫(該變) |
| SC-3 | RightRail 持有 tradeKind:選融券 → 切 tab 再回 → 「融券」仍 aria-pressed(R2-10) | vitest RightRail:258-261 改寫(該變) |
| SC-4 | 自選清單每個**群組**標題列:組名右側顯示等權平均漲幅 `+x.xx%`(fmtPct),色:>0 bull / <0 bear / 0 或無資料 ink-dim;分母排除 `p==null`(含只有 ref 的)與 `chg_pct==null`;全組無成交 → 不顯示(或 `-`?→ `[auto-default: 不渲染 | reason: 標題列已有檔數,空值再佔一格是噪音]`);**未分組列不顯示** | vitest WatchlistSidebar:quotes fixture(兩檔 +2 / −1、一檔 p null)→ 群組列含 `+0.50%`、未分組列無 %;截圖 `evidence/SC-4_group_avg.png` |
| SC-5 | 白名單:群組展開收合 / 全部展開收合 / 底色帶 / 檔數 / 上限 50 文案 / 拖曳排序 / 個股列三態不變;交易別送出值與無券鎖買側不變 | 既有測試全綠(除 §該變 2 處) |

## 設計(diff 級)
- (a) 🔴 `PriceLadder.tsx`:`armControls` 換成 `<div role="group" aria-label="交易別" className="flex shrink-0 items-center gap-0.5">` + `TRADE_KINDS.map` 四顆 `<button type="button" aria-pressed onClick={() => { touchIdle(); setTradeKind(v); }} className={cn("rounded border px-1 py-0.5 text-xs", active ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink")}>`。`[auto-default: gap-0.5 / px-1(比 StockPage 樣板 px-2 收窄)| reason: 288px 右欄要容 武裝(flex-1 min-w-0)+ 鎖定 + 四顆 pill;`shrink-0` 交給 pill 群,武裝鈕吸收壓縮(R5 SC-1 同策略)]`。
- (b) 🟢 `WatchlistSidebar.tsx`:`sectionHeader` 加 `avgPct?: number | null`;插在組名 span 與檔數 span 之間 `<span className={cn("shrink-0 font-mono text-[0.625rem]", tone)}>{fmtPct(avgPct)}</span>`;群組呼叫點傳 `groupAvgPct(g.codes, quotes)`(純函式,放同檔頂層或 `lib/watchlist-avg.ts`;`[auto-default: 抽到 lib/watchlist-avg.ts 純函式並單測 | reason: 分母規則(排除 p==null)是口徑,純函式測試最直接]`);未分組不傳。
- 該變測試:PriceLadder.test:401(`fireEvent.change` → `fireEvent.click(getByRole("button",{name:"無券"}))`)、RightRail.test:258/261(click 融券 → 斷 aria-pressed)。其餘 `getByLabelText("交易別")` 存在性斷言不該紅(容器 aria-label 沿用)。
- 三類:🔴 (a) 一對 [red]/[green](先改 401/258 該變 + 新增 SC-1 案 → 紅);🟢 (b) 一對 [red]/[green];互不混。

## Edge / Out of scope
- E-1 群組全部只有 ref(盤前)→ 不渲染平均;E-2 單檔群組 → 平均 = 該檔;E-3 pill 在 RightRail 未傳 tradeKind 時走內部 state(既有測試路徑)。
- Out:Stkfut / Futures 梯當沖 checkbox 不動;pill 鍵盤方向鍵切換 / radiogroup 語意(a11y 半套同 next-time tablist 條;review A3);零態 ink-dim 對比(review A6,系統性 chore)。

## Review round 1 amendments(2026-08-17;`code-review-round-1.json`)
- `[amendment: C1]` 非現股選中 pill = `border-warn text-warn`(琥珀),現股 = accent;`[auto-default: 採 (b) 視覺而非 (a) 切交易別即解除 | reason: (a) 與 R5 鎖定語意衝突且既有 select 也不解除]`。
- `[amendment: C2]` pill `px-0.5`;SC-1 補 armed+locked 態 288px 截圖(實測 arm 69px 無溢出)。
- `[amendment: C3/C4/C5/C6/A4]` `groupAvgPct` 回 `{avg,n,total,trial}`;徽章 tone 依顯示精度、`aria-label`「平均漲幅 +x%」、`title`「(n/N 檔有成交[,含 k 檔試撮])」;`[auto-default: 不設覆蓋率門檻、不隱藏 | reason: 等權 + hover 可查證;盤前少數檔先動本身是資訊]`。
- `[amendment: A1/A2/A5/A7/C7]` 測試補強(mutation-verified 兩案)。

## self_review_head
d56f99f8(code review r1:2 lens,P1×2 / P2×12 全處置,2 條 next-time)
