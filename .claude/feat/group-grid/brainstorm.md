# brainstorm — 群組多檔即時分時圖(題 5,group-grid)

規格來源:`.claude/feat/stock-quintet-discussion/brainstorm.md` 題 5(user 2026-08-05
拍板修正版:**不做三窗相關係數儀表 UI;做多檔 mini 即時分時圖同屏(sub-tab);
Discord 聯動要;領先落後不做**)→ /auto 預核准。
分流判定:**已成形方案**(UI 形式 sub-tab grid + 資料源 per-code snapshot 指名)。

## 目標

一眼看出「同產業群組今天有沒有一起動」:個股頁新增群組檢視(自選群組成員的 mini
即時分時圖牆);訊號的 Discord 通知附同群成員現況(誰還沒動)。

## 現況(master 2bb87a1)

- 自選群組:schema v3 `groups`(題 4 已補齊 Discord 管理);前端 `useStockWatchlist`
- 後端 per-code 完整狀態:`stock_engine._states`(全部自選股);
  `GET /api/stock/state/{code}` snapshot(minutes/last/meta)任一訂閱中 code 可查
- 前端 live:`useStockStream` 收全自選 `watchlist_quote`(p/chg_pct/vol 每秒)
- 訊號:題 1 規則引擎已入;`SignalHub._emit` → `format_signal_text` → Discord
- 分時幾何:`buildIntradayGeometry`(可小尺寸重用;VP/overlay 等重件不需要)

## 成功條件(SC)

- **SC-1** 後端同群摘要(Discord 專用):規則觸發時,若該 code 屬某自選群組,Discord
  文字**文末**追加 `｜同群 {群組名}:{代碼}{名稱} {+x.x%}、…`(同群其他成員,依
  |漲跌幅| 降冪,**最多 4 檔**,無行情者顯示 `-`);code 不屬任何群組 → 不附;
  WS/jsonl payload **零改動**。驗證:pytest `test_signal_hub.py` 同群摘要組(anytime)
- **SC-2** hub 資料接線:群組結構隨 watchlist 變更傳入 hub(`on_watchlist(codes,
  groups)` 擴充或等價 setter);行情快照由 stock_engine 注入 provider callback
  (`quotes_fn() -> dict[code, chg_pct|None]`,讀 `_states` 現值)。
  驗證:pytest(群組變更後摘要跟著變;provider 缺值降級 `-`)(anytime)
- **SC-3** 前端群組檢視(可指認):個股頁圖表區上方新增檢視切換「單檔｜群組」;
  切「群組」後出現群組下拉(自選群組名)+ 成員卡片 grid(自動欄數,約 2-3 欄);
  每張卡片 = 代碼+名稱(左上)、現價與漲跌幅(右上,紅漲綠跌)、mini 分時線
  (平盤虛線 + 紅/綠面積填色,無座標軸);**點卡片 → 切回單檔檢視並選中該股**。
  驗證:vitest + AI 截圖對照 + user 過目
- **SC-4** mini 圖資料鏈:成員 minutes 走既有 snapshot API(TQ per-code query,
  `refetchInterval` 60s)+ `watchlist_quote` 現價延伸最後一點(圖不凍結);
  成員 no_data → 卡片顯示「無資料」占位。驗證:vitest(hook + 延伸邏輯)(anytime)
- **SC-5** 零退化:六 gate 全綠(pytest/ruff/pyright/vitest/tsc/eslint)。(anytime)

## Edge cases

1. code 屬多個群組 → 摘要取**第一個**含它的群組(群組序);前端下拉可自選任一群組
2. 群組成員 1 檔(只有觸發者自己)→ 無「其他成員」→ 不附摘要
3. 成員 >5(含觸發者)→ 摘要取 |chg| 前 4 檔 + 「…共 N 檔」
4. 未分組股觸發 → 不附(未分組是衍生桶不是群組)
5. 群組在檢視中被刪(Discord/另一分頁)→ 下拉 fallback 第一個群組;零群組 → 「尚無群組」空態
6. batch 請求失敗 → **全部**卡片「無資料」(整批一命;[amendment 2026-08-06:
   design R1/R2 改單一 batch 端點後,per-card 隔離語意不再成立 — impl-spec R10 更正])
7. quotes_fn 讀不到某 code(未訂閱瞬間)→ 摘要該檔顯示 `-`

## 決策記錄

- `[auto-default: 同群摘要全規則一律附(有群組即附),不做 per-rule 屬性 | reason:
  user 拍板「可以驅動 discord 通知」未要求分規則;題 1 刻意未預留欄位(YAGNI),
  需要時再加]`
- `[auto-default: 同步率 badge 本輪不做 | reason: user 拍板重點是「即時分時圖同屏」;
  CorrState 掛載留 next-time]`
- `[auto-default: mini 圖資料 = snapshot(60s refetch)+ quote 現價延伸,不做分鐘級
  WS 推播 | reason: 後端零新增廣播;mini 圖精度分鐘級已足,現價點保即時感]`
- `[auto-default: 檢視切換放圖表區頂(與江波圖/分K/日K mode 列同層級),非 nav tab |
  reason: user 說「sub-tab 的方式」— 圖表區內切換最貼近且不動全站 nav]`
- `[auto-default: 疊圖(歸一化多線)本輪不做 | reason: quintet 已列「grid 之外的選配」]`

## Out of scope

- 領先落後(user 拍板不做)、三窗相關係數 UI(user 拍板不做)
- 同步率 badge / CorrState 接線(→ next-time)
- 疊圖檢視、per-rule 同群摘要屬性、分鐘級 WS 推播

## 規模分流

**L**(後端 2-3 檔 + 前端 4-5 檔,跨前後端)→ 完整流程。

## 驗證窗口

SC-1/2/4/5 anytime;SC-3 截圖 anytime(盤後 snapshot 有分時資料;fake server 亦可);
盤中群組同步實看 = user 過目層。
